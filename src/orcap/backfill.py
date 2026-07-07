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


def main(source: str = "all", limit: int | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if source in ("wayback", "all"):
        print(json.dumps(asyncio.run(backfill_wayback(limit=limit)), indent=2))
    if source in ("orw", "all"):
        log.warning(
            "orw backfill unavailable: public instance offline, repo has no dump "
            "(see module docstring)"
        )


if __name__ == "__main__":
    main()
