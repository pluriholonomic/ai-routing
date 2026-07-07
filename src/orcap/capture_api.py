"""15-minute snapshot job: models + providers + per-provider endpoints.

Fan-out: 1x /models, 1x /providers, then one /models/{author}/{slug}/endpoints
call per unique canonical_slug (the `links.details` path in the models response).
Writes the raw responses (jsonl.gz) and normalized Parquet partitions locally;
a separate step pushes them to the HF dataset repo.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from . import normalize
from .config import API_V1, CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)


def _endpoint_urls(models: list[dict[str, Any]]) -> list[str]:
    """One endpoints URL per unique model, preferring the API-provided details link."""
    seen: set[str] = set()
    urls: list[str] = []
    for m in models:
        slug = m.get("canonical_slug") or m.get("id")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        details = (m.get("links") or {}).get("details")
        url = f"https://openrouter.ai{details}" if details else f"{API_V1}/models/{slug}/endpoints"
        urls.append(url)
    return urls


def write_partition(
    table, name: str, run_ts: str, dt: str, curated_dir: Path = CURATED_DIR
) -> Path:
    out_dir = curated_dir / name / f"dt={dt}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run_ts}.parquet"
    pq.write_table(table, out, compression="zstd")
    return out


async def capture(raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()
    async with make_client() as client:
        fetcher = Fetcher(client)

        models_doc, providers_doc = await asyncio.gather(
            fetcher.get_json(f"{API_V1}/models"),
            fetcher.get_json(f"{API_V1}/providers"),
        )
        if not models_doc or "data" not in models_doc:
            raise RuntimeError("failed to fetch /api/v1/models — aborting run")
        models = models_doc["data"]
        providers = (providers_doc or {}).get("data", [])

        urls = _endpoint_urls(models)
        log.info("fetching endpoints for %d models", len(urls))
        endpoint_docs_raw = await asyncio.gather(*(fetcher.get_json(u) for u in urls))
        endpoint_docs = [d["data"] for d in endpoint_docs_raw if d and "data" in d]
        failures = len(urls) - len(endpoint_docs)

        write_raw(fetcher.records, "api_v1", raw_dir, run_ts, dt)

    models_tbl = normalize.models_table(models, run_ts, dt)
    endpoints_tbl = normalize.endpoints_table(endpoint_docs, run_ts, dt)
    providers_tbl = normalize.providers_table(providers, run_ts, dt)

    paths = {
        "models_snapshots": write_partition(
            models_tbl, "models_snapshots", run_ts, dt, curated_dir
        ),
        "endpoints_snapshots": write_partition(
            endpoints_tbl, "endpoints_snapshots", run_ts, dt, curated_dir
        ),
        "providers_snapshots": write_partition(
            providers_tbl, "providers_snapshots", run_ts, dt, curated_dir
        ),
    }
    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "models": models_tbl.num_rows,
        "endpoints": endpoints_tbl.num_rows,
        "providers": providers_tbl.num_rows,
        "endpoint_fetch_failures": failures,
        "paths": {k: str(v) for k, v in paths.items()},
    }
    log.info("capture complete: %s", summary)
    return summary


async def capture_loop(samples: int, interval_seconds: float) -> list[dict[str, Any]]:
    """Take N snapshots spaced interval_seconds apart within one job.

    GitHub Actions cron below 15 min is unreliable, but OpenRouter exposes
    5-minute rolling windows (uptime_last_5m) — so a */15 job taking 3 samples
    at 5-min spacing yields an effective 5-minute time series.
    """
    import time

    summaries = []
    for i in range(samples):
        start = time.monotonic()
        summaries.append(await capture())
        if i < samples - 1:
            elapsed = time.monotonic() - start
            await asyncio.sleep(max(0.0, interval_seconds - elapsed))
    return summaries


def main(samples: int = 1, interval_seconds: float = 300.0) -> list[dict[str, Any]]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(capture_loop(samples, interval_seconds))


if __name__ == "__main__":
    main()
