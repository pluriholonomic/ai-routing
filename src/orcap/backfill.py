"""Best-effort historical backfill of model-level pricing (per-provider pricing
has no public history anywhere — it starts with our own capture).

Source: Wayback Machine snapshots of https://openrouter.ai/api/v1/models,
which go back to 2023-07. Each distinct snapshot becomes a models_snapshots-
shaped partition under backfill/models_snapshots_wayback/, with `source` and
the snapshot timestamp as run_ts.

fry69/orw (hourly change-log) would be a richer source, but its public
instance is offline and the repo ships no data dump; if you obtain the SQLite
file, load it manually and normalize against the same schema.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import normalize
from .config import DATA_DIR, RAW_DIR
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)

CDX_URL = (
    "https://web.archive.org/cdx/search/cdx"
    "?url=openrouter.ai%2Fapi%2Fv1%2Fmodels&output=json"
    "&filter=statuscode:200&collapse=digest"
)
SNAPSHOT_URL = "https://web.archive.org/web/{ts}id_/https://openrouter.ai/api/v1/models"

BACKFILL_DIR = DATA_DIR / "backfill" / "models_snapshots_wayback"


def _run_ts(wayback_ts: str) -> str:
    # 20230726091203 -> 20230726T091203Z
    return f"{wayback_ts[:8]}T{wayback_ts[8:]}Z"


def _dt(wayback_ts: str) -> str:
    return f"{wayback_ts[:4]}-{wayback_ts[4:6]}-{wayback_ts[6:8]}"


async def backfill_wayback(
    limit: int | None = None, out_dir: Path = BACKFILL_DIR, raw_dir: Path = RAW_DIR
) -> dict[str, Any]:
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.5)  # be polite to archive.org

        index = await fetcher.get_json(CDX_URL)
        if not index or len(index) < 2:
            raise RuntimeError("Wayback CDX query returned nothing")
        header, *rows = index
        ts_col = header.index("timestamp")
        timestamps = [r[ts_col] for r in rows]
        if limit:
            timestamps = timestamps[:limit]
        log.info("found %d distinct wayback snapshots", len(timestamps))

        captured = 0
        skipped: list[str] = []
        for ts in timestamps:
            body = await fetcher.get_json(SNAPSHOT_URL.format(ts=ts))
            models = (body or {}).get("data") if isinstance(body, dict) else None
            if not models or not isinstance(models, list):
                skipped.append(ts)
                continue
            tbl = normalize.models_table(models, _run_ts(ts), _dt(ts))
            tbl = tbl.append_column("source", pa.array(["wayback"] * tbl.num_rows, pa.string()))
            part = out_dir / f"dt={_dt(ts)}"
            part.mkdir(parents=True, exist_ok=True)
            pq.write_table(tbl, part / f"{_run_ts(ts)}.parquet", compression="zstd")
            captured += 1
            if captured % 25 == 0:
                log.info("backfilled %d/%d snapshots", captured, len(timestamps))

        write_raw(fetcher.records, "wayback", raw_dir, "backfill", "backfill")

    summary = {"snapshots": len(timestamps), "captured": captured, "skipped": len(skipped)}
    log.info("wayback backfill done: %s", summary)
    return summary


def backfill_litellm(sample_days: int = 14, workdir: Path | None = None) -> Path:
    """Cross-provider DIRECT price history from the git history of LiteLLM's
    community price file (model_prices_and_context_window.json) — dated price
    observations per (model, litellm_provider) back to 2023. Blobless clone;
    one commit sampled per `sample_days`."""
    import subprocess
    import tempfile

    workdir = workdir or Path(tempfile.mkdtemp(prefix="litellm-"))
    repo = workdir / "litellm"
    fname = "model_prices_and_context_window.json"
    subprocess.run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            "https://github.com/BerriAI/litellm.git",
            str(repo),
        ],
        check=True,
        capture_output=True,
    )
    log_out = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%H %cs", "--", fname],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    # newest-first; keep one commit per sample window
    picked, last_date = [], None
    for line in log_out:
        sha, cs = line.split()
        d = pd.Timestamp(cs)
        if last_date is None or (last_date - d).days >= sample_days:
            picked.append((sha, cs))
            last_date = d
    log.info("litellm: %d commits sampled from %d", len(picked), len(log_out))

    rows = []
    for sha, cs in picked:
        try:
            blob = subprocess.run(
                ["git", "-C", str(repo), "show", f"{sha}:{fname}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            doc = json.loads(blob)
        except Exception as exc:
            log.warning("litellm %s (%s): %s", sha[:8], cs, str(exc)[:80])
            continue
        for model, spec in doc.items():
            if model == "sample_spec" or not isinstance(spec, dict):
                continue
            cin, cout = spec.get("input_cost_per_token"), spec.get("output_cost_per_token")
            if cin is None and cout is None:
                continue
            rows.append(
                {
                    "obs_date": cs,
                    "commit": sha[:12],
                    "model": model,
                    "litellm_provider": spec.get("litellm_provider"),
                    "input_cost_per_token": cin,
                    "output_cost_per_token": cout,
                    "max_tokens": spec.get("max_tokens"),
                }
            )
    out = DATA_DIR / "external" / "litellm_price_history.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out, index=False)
    log.info("litellm history: %d rows -> %s", len(rows), out)
    return out


def main(source: str = "all", limit: int | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if source in ("wayback", "all"):
        print(json.dumps(asyncio.run(backfill_wayback(limit=limit)), indent=2))
    if source in ("litellm", "all"):
        try:
            backfill_litellm()
        except Exception as exc:
            log.error("litellm backfill failed: %s", exc)
    if source in ("orw", "all"):
        log.warning(
            "orw backfill unavailable: public instance offline, repo has no dump "
            "(see module docstring)"
        )


if __name__ == "__main__":
    main()
