"""Nightly compaction over the HF dataset repo.

For a target day:
  1. Pull that day's curated partitions plus the derived pricing state from HF.
  2. Repartition every curated table into one zstd file per day.
  3. Fold endpoints_snapshots through the pricing state to derive SCD-2
     price-change events (derived/pricing_changes) and refresh the
     latest-known-price table (derived/pricing_current).
  4. Commit the pricing-critical consolidated file + state, deleting its
     small per-run inputs.

Only one completed day is hydrated remotely. Historical all-table hydration can
require thousands of Hub file requests, while day-bounded consolidation keeps
future analysis downloads tractable.

Endpoint identity for change detection is (model_id, provider_name, tag,
endpoint_fingerprint) — the fingerprint hashes capability fields because a
provider can serve two differently-priced SKUs under one tag.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import CURATED_DIR, DATA_DIR, HF_DATASET_REPO

log = logging.getLogger(__name__)

TRACKED_PRICE_FIELDS = [
    "price_prompt",
    "price_completion",
    "price_request",
    "price_image",
    "price_input_cache_read",
    "price_input_cache_write",
    "price_discount",
]

DERIVED_DIR = DATA_DIR / "derived"
PRICING_CURRENT = DERIVED_DIR / "pricing_current.parquet"


def yesterday_utc() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")


# ------------------------------------------------------------- repartitioning


def consolidate_table_day(table_dir: Path) -> tuple[Path | None, list[Path]]:
    """Merge all per-run parquet files in curated/{table}/dt=D into part-0.parquet.

    An existing part-0 (from a prior compaction of the same day) is folded into
    the merge — otherwise re-compacting a day would drop its rows.
    """
    per_run = sorted(p for p in table_dir.glob("*.parquet") if p.name != "part-0.parquet")
    if not per_run:
        return None, []
    out = table_dir / "part-0.parquet"
    files = ([out] if out.exists() else []) + per_run
    # ParquetFile.read avoids dataset-level hive-partition inference, which would
    # collide with the dt column embedded in the files
    tables = [pq.ParquetFile(f).read() for f in files]
    # permissive: schema inference can flap int64/double across runs for stat columns
    merged = pa.concat_tables(tables, promote_options="permissive")
    pq.write_table(merged, out, compression="zstd")
    return out, per_run


# ------------------------------------------------------- pricing change fold


def _endpoint_key(row: dict[str, Any]) -> str:
    return (
        f"{row.get('model_id')}||{row.get('provider_name')}||{row.get('tag')}"
        f"||{row.get('endpoint_fingerprint') or ''}"
    )


def fold_pricing_changes(
    endpoints_day: pa.Table, state: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fold a day of endpoint snapshots (ordered by run_ts) through the price state.

    Returns (change_events, new_state). state maps endpoint_key -> last-known
    {run_ts, model_id, provider_name, tag, <price fields>}.
    """
    events: list[dict[str, Any]] = []
    if "endpoint_fingerprint" not in endpoints_day.column_names:  # pre-fingerprint captures
        endpoints_day = endpoints_day.append_column(
            "endpoint_fingerprint", pa.array([""] * endpoints_day.num_rows, pa.string())
        )
    cols = [
        "run_ts",
        "model_id",
        "provider_name",
        "tag",
        "endpoint_fingerprint",
        *TRACKED_PRICE_FIELDS,
    ]
    rows = endpoints_day.select(cols).sort_by("run_ts").to_pylist()

    seen_this_day: dict[str, set[str]] = {}
    for row in rows:
        key = _endpoint_key(row)
        seen_this_day.setdefault(row["run_ts"], set()).add(key)
        prev = state.get(key)
        if prev is None:
            events.append(
                {
                    "changed_at_run_ts": row["run_ts"],
                    "model_id": row["model_id"],
                    "provider_name": row["provider_name"],
                    "tag": row["tag"],
                    "endpoint_fingerprint": row["endpoint_fingerprint"],
                    "field": "__endpoint_added__",
                    "old_value": None,
                    "new_value": json.dumps(
                        {f: row[f] for f in TRACKED_PRICE_FIELDS}, sort_keys=True
                    ),
                }
            )
        else:
            for f in TRACKED_PRICE_FIELDS:
                if prev.get(f) != row[f]:
                    events.append(
                        {
                            "changed_at_run_ts": row["run_ts"],
                            "model_id": row["model_id"],
                            "provider_name": row["provider_name"],
                            "tag": row["tag"],
                            "endpoint_fingerprint": row["endpoint_fingerprint"],
                            "field": f,
                            "old_value": None if prev.get(f) is None else str(prev[f]),
                            "new_value": None if row[f] is None else str(row[f]),
                        }
                    )
        state[key] = row

    # endpoints missing from the day's final run are treated as removed
    if rows:
        last_run = rows[-1]["run_ts"]
        present_last = seen_this_day.get(last_run, set())
        for key in list(state):
            if key not in present_last and state[key]["run_ts"] < last_run:
                prev = state.pop(key)
                events.append(
                    {
                        "changed_at_run_ts": last_run,
                        "model_id": prev["model_id"],
                        "provider_name": prev["provider_name"],
                        "tag": prev["tag"],
                        "endpoint_fingerprint": prev.get("endpoint_fingerprint", ""),
                        "field": "__endpoint_removed__",
                        "old_value": json.dumps(
                            {f: prev.get(f) for f in TRACKED_PRICE_FIELDS}, sort_keys=True
                        ),
                        "new_value": None,
                    }
                )
    return events, state


def load_state(path: Path = PRICING_CURRENT) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {_endpoint_key(r): r for r in pq.read_table(path).to_pylist()}


def save_state(state: dict[str, dict[str, Any]], path: Path = PRICING_CURRENT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "run_ts",
        "model_id",
        "provider_name",
        "tag",
        "endpoint_fingerprint",
        *TRACKED_PRICE_FIELDS,
    ]
    schema = pa.schema([pa.field(c, pa.string() if c in cols[:5] else pa.float64()) for c in cols])
    pq.write_table(
        pa.Table.from_pylist(list(state.values()), schema=schema), path, compression="zstd"
    )


CHANGES_SCHEMA = pa.schema(
    [
        pa.field("dt", pa.string()),
        pa.field("changed_at_run_ts", pa.string()),
        pa.field("model_id", pa.string()),
        pa.field("provider_name", pa.string()),
        pa.field("tag", pa.string()),
        pa.field("endpoint_fingerprint", pa.string()),
        pa.field("field", pa.string()),
        pa.field("old_value", pa.string()),
        pa.field("new_value", pa.string()),
    ]
)


# --------------------------------------------------------------- local driver


def compact_local(
    dt: str, data_dir: Path = DATA_DIR, tables: set[str] | None = None
) -> dict[str, Any]:
    """Compact one day in a local data dir. Returns summary incl. deleted files."""
    curated = data_dir / "curated" if data_dir != DATA_DIR else CURATED_DIR
    deleted: list[Path] = []
    row_counts: dict[str, int] = {}

    endpoints_day: pa.Table | None = None
    for table_dir in sorted(curated.glob(f"*/dt={dt}")):
        if tables is not None and table_dir.parent.name not in tables:
            continue
        out, olds = consolidate_table_day(table_dir)
        if out is None:
            continue
        tbl_name = table_dir.parent.name
        row_counts[tbl_name] = pq.read_metadata(out).num_rows
        if tbl_name == "endpoints_snapshots":
            endpoints_day = pq.ParquetFile(out).read()
        for f in olds:
            f.unlink()
            deleted.append(f)

    events: list[dict[str, Any]] = []
    if endpoints_day is not None and endpoints_day.num_rows:
        state_path = data_dir / "derived" / "pricing_current.parquet"
        state = load_state(state_path)
        events, state = fold_pricing_changes(endpoints_day, state)
        save_state(state, state_path)
        changes_dir = data_dir / "derived" / "pricing_changes" / f"dt={dt}"
        changes_dir.mkdir(parents=True, exist_ok=True)
        changes_path = changes_dir / "part-0.parquet"
        event_rows = [{"dt": dt, **e} for e in events]
        # a re-run of an already-folded day computes few/no events (state has
        # absorbed them); merge with the existing file so events aren't lost
        if changes_path.exists():
            existing = pq.ParquetFile(changes_path).read().to_pylist()
            merged = {json.dumps(r, sort_keys=True): r for r in existing + event_rows}
            event_rows = list(merged.values())
        pq.write_table(
            pa.Table.from_pylist(event_rows, schema=CHANGES_SCHEMA),
            changes_path,
            compression="zstd",
        )

    summary = {
        "dt": dt,
        "tables": row_counts,
        "consolidated_files_removed": len(deleted),
        "pricing_change_events": len(events),
        "price_field_changes": sum(1 for e in events if not e["field"].startswith("__")),
    }
    log.info("compaction summary: %s", summary)
    return summary


# ------------------------------------------------------------------ HF driver


def _shard_tables(
    table_names: list[str], *, shard_index: int | None, shard_count: int | None
) -> list[str]:
    """Assign sorted table names deterministically across remote compaction shards."""
    names = sorted(set(table_names))
    if shard_index is None and shard_count is None:
        return names
    if shard_index is None or shard_count is None:
        raise ValueError("shard_index and shard_count must be provided together")
    if shard_count < 1 or shard_index < 0 or shard_index >= shard_count:
        raise ValueError("require shard_count >= 1 and 0 <= shard_index < shard_count")
    return [name for position, name in enumerate(names) if position % shard_count == shard_index]


def compact_hf(
    dt: str,
    repo_id: str = HF_DATASET_REPO,
    workdir: Path | None = None,
    *,
    shard_index: int | None = None,
    shard_count: int | None = None,
) -> dict:
    """Pull day partitions + state from HF, compact, and push adds/deletes."""
    import tempfile

    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, snapshot_download

    from .hf_store import get_api

    api = get_api()
    workdir = workdir or Path(tempfile.mkdtemp(prefix="orcap-compact-"))
    prefix = "curated/"
    marker = f"/dt={dt}/"
    table_names = [
        path[len(prefix) :].split("/", 1)[0]
        for path in api.list_repo_files(repo_id=repo_id, repo_type="dataset")
        if path.startswith(prefix) and marker in path and path.endswith(".parquet")
    ]
    selected_tables = _shard_tables(
        table_names, shard_index=shard_index, shard_count=shard_count
    )
    if not selected_tables:
        return {
            "dt": dt,
            "tables": {},
            "selected_tables": [],
            "shard_index": shard_index,
            "shard_count": shard_count,
            "consolidated_files_removed": 0,
            "pricing_change_events": 0,
            "price_field_changes": 0,
        }
    # One completed day across ALL curated tables is a bounded download, unlike
    # historical all-table hydration. Consolidating every table matters: per-run
    # ledger/collector files otherwise accumulate hundreds of files per day and
    # make the memo job's snapshot_download (one request per file) hang on rate
    # limits. Days whose endpoints partition is already a lone part-0 skip the
    # pricing fold entirely, so re-running old days cannot corrupt the SCD-2 state.
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=workdir,
        allow_patterns=[f"curated/{table}/dt={dt}/*" for table in selected_tables]
        + (
            [
                "derived/pricing_current.parquet",
                f"derived/pricing_changes/dt={dt}/*",
            ]
            if "endpoints_snapshots" in selected_tables
            else []
        ),
        token=api.token,
        # Matrix jobs are serialized because each commit advances one branch.
        # The source ledger is small in bytes but has hundreds of immutable
        # objects per day, so modestly increase request concurrency only for
        # the shard that owns it. Other shards retain the Hub client's default
        # sized pool and avoid unnecessary burst pressure.
        max_workers=16 if "source_runs" in selected_tables else 8,
    )
    def _snapshot() -> dict[Path, tuple[int, float]]:
        return {
            p.relative_to(workdir): (p.stat().st_size, p.stat().st_mtime)
            for p in workdir.rglob("*.parquet")
        }

    before = _snapshot()
    summary = compact_local(dt, data_dir=workdir, tables=set(selected_tables))
    summary["selected_tables"] = selected_tables
    summary["shard_index"] = shard_index
    summary["shard_count"] = shard_count
    after = _snapshot()

    ops: list = [
        CommitOperationDelete(path_in_repo=str(p)) for p in sorted(set(before) - set(after))
    ]
    # push only files consolidation actually rewrote — an already-compacted day
    # would otherwise re-upload every unchanged part-0 in the commit
    changed_or_new = sorted(p for p, sig in after.items() if before.get(p) != sig)
    ops += [
        CommitOperationAdd(path_in_repo=str(p), path_or_fileobj=str(workdir / p))
        for p in changed_or_new
    ]
    if not ops:
        log.info("nothing to compact for %s", dt)
        return summary
    api.create_commit(
        repo_id=repo_id,
        repo_type="dataset",
        operations=ops,
        commit_message=(
            f"compact dt={dt} shard={shard_index if shard_index is not None else 'all'}: "
            f"{summary['pricing_change_events']} pricing events"
        ),
    )
    log.info("pushed compaction commit for %s (%d ops)", dt, len(ops))
    return summary


def main(
    repo: str | None = None,
    dt: str | None = None,
    *,
    shard_index: int | None = None,
    shard_count: int | None = None,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dt = dt or yesterday_utc()
    summary = compact_hf(
        dt,
        repo_id=repo or HF_DATASET_REPO,
        shard_index=shard_index,
        shard_count=shard_count,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
