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
import pyarrow.compute as pc
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
PRICING_STATE_TABLE = "pricing_state"

ENDPOINT_LISTING_KEY = [
    "run_ts",
    "model_id",
    "provider_name",
    "tag",
    "endpoint_fingerprint",
]
ENDPOINT_SOURCE_RECORD_KEY = [*ENDPOINT_LISTING_KEY, "record_json"]

ARTIFACT_OVERLAP_TABLES = {"paid_spend_ledger", "router_route_attempts"}
ARTIFACT_OVERLAP_PREFIXES = (
    "adaptive_router_",
    "glm52_hmp_",
    "glm52_routing_",
    "ic_",
    "market_measurement_",
    "price_event_",
    "price_response_",
    "score_memory_",
)


def _artifact_overlap_table(name: str) -> bool:
    return name in ARTIFACT_OVERLAP_TABLES or name.startswith(ARTIFACT_OVERLAP_PREFIXES)


def yesterday_utc() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")


# ------------------------------------------------------------- repartitioning


def _take_first_by_key(table: pa.Table, key_fields: list[str]) -> pa.Table:
    """Return the first row for each key while preserving source row order."""
    missing = [field for field in key_fields if field not in table.column_names]
    if missing:
        raise ValueError(f"table is missing deduplication fields: {missing}")
    if not table.num_rows:
        return table

    indexed = table.append_column("__source_row", pa.array(range(table.num_rows)))
    grouped = indexed.group_by(key_fields).aggregate([("__source_row", "min")])
    first_rows = grouped["__source_row_min"]
    ordered = pc.take(first_rows, pc.sort_indices(first_rows))
    return indexed.drop(["__source_row"]).take(ordered)


def deduplicate_endpoint_records(table: pa.Table) -> tuple[pa.Table, dict[str, int]]:
    """Remove repeat copies of one raw endpoint record, never distinct variants.

    Artifact overlap can place the same capture file in both ``part-0`` and the
    next ``buffered-part``.  ``record_json`` is the source-record boundary: two
    rows with different raw payloads remain separate even when their public
    listing key is identical.  A repeated source payload must normalize to the
    same scalar fields; otherwise the partition is internally inconsistent and
    compaction fails rather than choosing a version silently.
    """
    if not table.num_rows:
        return table, {
            "physical_rows": 0,
            "distinct_source_records": 0,
            "duplicate_rows_removed": 0,
        }

    missing = [field for field in ENDPOINT_SOURCE_RECORD_KEY if field not in table.column_names]
    if missing:
        raise ValueError(f"endpoint table is missing source-record fields: {missing}")

    # Lists are represented inside record_json already.  Every remaining field
    # is scalar and should be a deterministic normalization of that payload.
    scalar_fields = [
        field
        for field in table.column_names
        if field not in ENDPOINT_SOURCE_RECORD_KEY and field != "supported_parameters"
    ]
    source_records = table.select(ENDPOINT_SOURCE_RECORD_KEY).group_by(
        ENDPOINT_SOURCE_RECORD_KEY
    ).aggregate([])
    normalized_records = table.select([*ENDPOINT_SOURCE_RECORD_KEY, *scalar_fields]).group_by(
        [*ENDPOINT_SOURCE_RECORD_KEY, *scalar_fields]
    ).aggregate([])
    if normalized_records.num_rows != source_records.num_rows:
        raise RuntimeError(
            "identical endpoint source records produced conflicting normalized fields: "
            f"{normalized_records.num_rows} normalized variants for "
            f"{source_records.num_rows} source records"
        )

    deduplicated = _take_first_by_key(table, ENDPOINT_SOURCE_RECORD_KEY)
    audit = {
        "physical_rows": table.num_rows,
        "distinct_source_records": deduplicated.num_rows,
        "duplicate_rows_removed": table.num_rows - deduplicated.num_rows,
    }
    return deduplicated, audit


def deduplicate_exact_records(table: pa.Table) -> tuple[pa.Table, dict[str, int]]:
    """Remove byte-equivalent logical rows from artifact overlap.

    Paid execution artifacts deliberately carry their prior checkpoint so a
    retried job can reconstruct spend and at-most-once reservations.  When
    several such artifacts are assembled for the Hub, the same logical row can
    therefore occur in both an earlier checkpoint and a later one.  Collapse
    only rows whose complete normalized payload is identical; rows sharing an
    identifier but disagreeing on any field remain visible to downstream
    integrity checks.
    """
    if not table.num_rows:
        return table, {"physical_rows": 0, "duplicate_rows_removed": 0}

    seen: set[str] = set()
    keep: list[int] = []
    for index, row in enumerate(table.to_pylist()):
        payload = json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            allow_nan=True,
        )
        if payload in seen:
            continue
        seen.add(payload)
        keep.append(index)
    deduplicated = table.take(pa.array(keep, type=pa.int64()))
    return deduplicated, {
        "physical_rows": table.num_rows,
        "duplicate_rows_removed": table.num_rows - deduplicated.num_rows,
    }


def canonicalize_pricing_endpoints(table: pa.Table) -> pa.Table:
    """Return one price record per listing/time, rejecting ambiguous quotes."""
    if "endpoint_fingerprint" not in table.column_names:  # pre-fingerprint captures
        table = table.append_column(
            "endpoint_fingerprint", pa.array([""] * table.num_rows, pa.string())
        )
    if not table.num_rows:
        return table

    missing = [
        field
        for field in [*ENDPOINT_LISTING_KEY, *TRACKED_PRICE_FIELDS]
        if field not in table.column_names
    ]
    if missing:
        raise ValueError(f"endpoint table is missing pricing fields: {missing}")

    listing_count = table.select(ENDPOINT_LISTING_KEY).group_by(ENDPOINT_LISTING_KEY).aggregate(
        []
    ).num_rows
    price_variant_count = table.select(
        [*ENDPOINT_LISTING_KEY, *TRACKED_PRICE_FIELDS]
    ).group_by([*ENDPOINT_LISTING_KEY, *TRACKED_PRICE_FIELDS]).aggregate([]).num_rows
    if price_variant_count != listing_count:
        raise RuntimeError(
            "conflicting prices for one endpoint listing and capture time: "
            f"{price_variant_count} price variants for {listing_count} listing keys"
        )
    return _take_first_by_key(table, ENDPOINT_LISTING_KEY)


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
    if table_dir.parent.name == "endpoints_snapshots":
        merged, audit = deduplicate_endpoint_records(merged)
        log.info("endpoint consolidation deduplication: %s", audit)
    elif _artifact_overlap_table(table_dir.parent.name):
        merged, audit = deduplicate_exact_records(merged)
        log.info("exact-row consolidation deduplication: %s", audit)
    pq.write_table(merged, out, compression="zstd")
    return out, per_run


def bundle_curated_partitions(
    data_dir: Path,
    *,
    min_dt: str | None = None,
    bundle_name: str = "buffered-part.parquet",
) -> dict[str, Any]:
    """Bundle artifact-backed curated partitions before their first Hub upload.

    ``bundle_name`` is stable across prepare-job reruns, so a later, more
    complete 26-hour artifact assembly overwrites the same remote object rather
    than adding a duplicate copy of the earlier rows. ``min_dt`` is a migration
    guard: partitions already uploaded as per-run files must be left alone and
    compacted remotely once.
    """
    if Path(bundle_name).name != bundle_name or not bundle_name.endswith(".parquet"):
        raise ValueError("bundle_name must be a parquet filename without directories")
    if min_dt is not None:
        datetime.strptime(min_dt, "%Y-%m-%d")

    curated = data_dir / "curated"
    row_counts: dict[str, int] = {}
    duplicate_rows_removed: dict[str, int] = {}
    files_removed = 0
    for table_dir in sorted(curated.glob("*/dt=*")):
        dt = table_dir.name.removeprefix("dt=")
        if min_dt is not None and dt < min_dt:
            continue
        files = sorted(table_dir.glob("*.parquet"))
        if not files:
            continue
        tables = [pq.ParquetFile(path).read() for path in files]
        merged = pa.concat_tables(tables, promote_options="permissive")
        if table_dir.parent.name == "endpoints_snapshots":
            merged, audit = deduplicate_endpoint_records(merged)
        elif _artifact_overlap_table(table_dir.parent.name):
            merged, audit = deduplicate_exact_records(merged)
        else:
            audit = None
        if audit is not None:
            duplicate_rows_removed[f"{table_dir.parent.name}/{table_dir.name}"] = audit[
                "duplicate_rows_removed"
            ]
        target = table_dir / bundle_name
        temporary = table_dir / f".{bundle_name}.tmp"
        pq.write_table(merged, temporary, compression="zstd")
        temporary.replace(target)
        for path in files:
            if path != target and path.exists():
                path.unlink()
                files_removed += 1
        row_counts[f"{table_dir.parent.name}/{table_dir.name}"] = merged.num_rows

    summary = {
        "min_dt": min_dt,
        "bundle_name": bundle_name,
        "partitions": row_counts,
        "source_files_removed": files_removed,
        "duplicate_rows_removed": duplicate_rows_removed,
        # Retain the old summary key for consumers written before exact-row
        # deduplication was extended to every curated table.
        "endpoint_duplicate_rows_removed": {
            key: value
            for key, value in duplicate_rows_removed.items()
            if key.startswith("endpoints_snapshots/")
        },
    }
    log.info("artifact bundle summary: %s", summary)
    return summary


def build_source_runs_baseline(
    data_dir: Path,
    dates: tuple[str, ...],
    output_path: Path,
) -> dict[str, Any]:
    """Materialize exact legacy source-run partitions as one Parquet object.

    The baseline is a migration artifact, not a sample: every input row is
    preserved.  Future capture dates remain separate daily bundles so nightly
    hydration needs one legacy object plus a bounded number of recent objects.
    """
    if not dates:
        raise ValueError("at least one legacy date is required")
    for dt in dates:
        datetime.strptime(dt, "%Y-%m-%d")

    source_dir = data_dir / "curated" / "source_runs"
    files = sorted(
        path
        for dt in dates
        for path in (source_dir / f"dt={dt}").glob("*.parquet")
    )
    if not files:
        raise FileNotFoundError("no legacy source-run files were hydrated")
    tables = [pq.ParquetFile(path).read() for path in files]
    expected_rows = sum(table.num_rows for table in tables)
    merged = pa.concat_tables(tables, promote_options="permissive")
    if merged.num_rows != expected_rows:
        raise RuntimeError(
            f"legacy source-run row mismatch: expected {expected_rows}, got {merged.num_rows}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    pq.write_table(merged, temporary, compression="zstd")
    if pq.read_metadata(temporary).num_rows != expected_rows:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("written legacy source-run baseline failed row-count verification")
    temporary.replace(output_path)
    summary = {
        "dates": list(dates),
        "source_files": len(files),
        "rows": expected_rows,
        "output_path": str(output_path),
    }
    log.info("legacy source-run baseline summary: %s", summary)
    return summary


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
    endpoints_day = canonicalize_pricing_endpoints(endpoints_day)
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


def _state_max_run_ts(state: dict[str, dict[str, Any]]) -> str:
    return max((str(row.get("run_ts") or "") for row in state.values()), default="")


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
    dt: str,
    data_dir: Path = DATA_DIR,
    tables: set[str] | None = None,
    *,
    prior_state_path: Path | None = None,
    require_prior_state: bool = False,
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
        if prior_state_path is not None and prior_state_path.exists():
            state = load_state(prior_state_path)
        elif require_prior_state:
            raise RuntimeError(
                f"no immutable prior-day pricing state is available before {dt}; "
                "run the chronological pricing-state rebuild before compacting this day"
            )
        else:
            state = {}
        events, state = fold_pricing_changes(endpoints_day, state)
        state_path = data_dir / "derived" / PRICING_STATE_TABLE / f"dt={dt}" / "part-0.parquet"
        save_state(state, state_path)
        changes_dir = data_dir / "derived" / "pricing_changes" / f"dt={dt}"
        changes_dir.mkdir(parents=True, exist_ok=True)
        changes_path = changes_dir / "part-0.parquet"
        event_rows = [{"dt": dt, **e} for e in events]
        # The day is a pure function of its endpoint partition and immutable
        # prior-day state. Replace, never merge: merging lets stale events from
        # an out-of-order re-run survive forever.
        pq.write_table(
            pa.Table.from_pylist(event_rows, schema=CHANGES_SCHEMA),
            changes_path,
            compression="zstd",
        )
        current_path = data_dir / "derived" / "pricing_current.parquet"
        current_state = load_state(current_path)
        if _state_max_run_ts(state) >= _state_max_run_ts(current_state):
            save_state(state, current_path)

    summary = {
        "dt": dt,
        "tables": row_counts,
        "consolidated_files_removed": len(deleted),
        "pricing_change_events": len(events),
        "price_field_changes": sum(1 for e in events if not e["field"].startswith("__")),
        "prior_pricing_state": str(prior_state_path) if prior_state_path else None,
        "pricing_state_written": bool(endpoints_day is not None and endpoints_day.num_rows),
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
    exclude_tables: set[str] | None = None,
) -> dict:
    """Pull day partitions + state from HF, compact, and push adds/deletes."""
    import tempfile

    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, snapshot_download

    from .hf_store import get_api

    api = get_api()
    workdir = workdir or Path(tempfile.mkdtemp(prefix="orcap-compact-"))
    prefix = "curated/"
    marker = f"/dt={dt}/"
    repo_files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    table_names = [
        path[len(prefix) :].split("/", 1)[0]
        for path in repo_files
        if path.startswith(prefix) and marker in path and path.endswith(".parquet")
    ]
    excluded_tables = set(exclude_tables or ())
    selected_tables = [
        table
        for table in _shard_tables(
            table_names, shard_index=shard_index, shard_count=shard_count
        )
        if table not in excluded_tables
    ]
    if not selected_tables:
        return {
            "dt": dt,
            "tables": {},
            "selected_tables": [],
            "excluded_tables": sorted(excluded_tables),
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
    prior_state_repo_path: str | None = None
    require_prior_state = False
    if "endpoints_snapshots" in selected_tables:
        endpoint_dates = sorted(
            {
                path.split("/dt=", 1)[1].split("/", 1)[0]
                for path in repo_files
                if path.startswith("curated/endpoints_snapshots/dt=")
                and path.endswith(".parquet")
            }
        )
        require_prior_state = any(candidate < dt for candidate in endpoint_dates)
        state_candidates = sorted(
            (
                path.split("/dt=", 1)[1].split("/", 1)[0],
                path,
            )
            for path in repo_files
            if path.startswith(f"derived/{PRICING_STATE_TABLE}/dt=")
            and path.endswith(".parquet")
            and path.split("/dt=", 1)[1].split("/", 1)[0] < dt
        )
        if state_candidates:
            _, prior_state_repo_path = state_candidates[-1]
        if require_prior_state and prior_state_repo_path is None:
            raise RuntimeError(
                f"endpoint history predates {dt}, but no immutable prior-day pricing state exists; "
                "run the chronological pricing-state rebuild"
            )

    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=workdir,
        allow_patterns=[f"curated/{table}/dt={dt}/*" for table in selected_tables]
        + (
            [
                "derived/pricing_current.parquet",
                f"derived/pricing_changes/dt={dt}/*",
                *([prior_state_repo_path] if prior_state_repo_path else []),
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
    summary = compact_local(
        dt,
        data_dir=workdir,
        tables=set(selected_tables),
        prior_state_path=(workdir / prior_state_repo_path if prior_state_repo_path else None),
        require_prior_state=require_prior_state,
    )
    summary["selected_tables"] = selected_tables
    summary["excluded_tables"] = sorted(excluded_tables)
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
    exclude_tables: set[str] | None = None,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dt = dt or yesterday_utc()
    summary = compact_hf(
        dt,
        repo_id=repo or HF_DATASET_REPO,
        shard_index=shard_index,
        shard_count=shard_count,
        exclude_tables=exclude_tables,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
