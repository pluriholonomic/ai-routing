"""High-frequency snapshot job: models + providers + per-provider endpoints,
plus live congestion stats for the hottest models.

Fan-out: 1x /models, 1x /providers, one /models/{slug}/endpoints call per
unique canonical_slug, and — for the top ORCAP_HOTLIST models by weekly
volume — the frontend stats/endpoint call, whose `stats` block carries live
30-minute latency/throughput percentiles and `fortuna` utilization
(recent_peak_rpm vs capacity_ceiling_rpm). That block is the demand-side
panel: it lets us measure how aggressively providers move quotes (and their
shadow price, latency) in response to load.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq

from . import normalize
from .config import API_V1, BASE_URL, CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)

HOTLIST_SIZE = int(os.environ.get("ORCAP_HOTLIST", "40"))
RANKINGS_URL = f"{BASE_URL}/api/frontend/v1/rankings/models?view=week"
STATS_URL = f"{BASE_URL}/api/frontend/v1/stats/endpoint"


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


def _hot_permaslugs(rankings: Any, n: int = HOTLIST_SIZE) -> list[str]:
    rows = (rankings or {}).get("data") or []
    totals: dict[str, int] = {}
    for r in rows:
        slug = r.get("model_permaslug")
        if slug:
            tokens = (r.get("total_prompt_tokens") or 0) + (r.get("total_completion_tokens") or 0)
            totals[slug] = totals.get(slug, 0) + tokens
    return [s for s, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:n]]


def _congestion_rows(body: Any, permaslug: str, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    for ep in (body or {}).get("data") or []:
        st = ep.get("stats") or {}
        f = ep.get("fortuna") or {}
        sh30 = ep.get("status_heuristics") or {}
        sh5 = ep.get("status_heuristics_5m") or {}
        pricing = ep.get("pricing") or {}
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "model_permaslug": permaslug,
                "endpoint_uuid": ep.get("id"),
                "provider_name": ep.get("provider_display_name") or ep.get("provider_name"),
                "price_completion": _sf(pricing.get("completion")),
                "p50_latency_ms": st.get("p50_latency"),
                "p90_latency_ms": st.get("p90_latency"),
                "p99_latency_ms": st.get("p99_latency"),
                "p50_throughput": st.get("p50_throughput"),
                "p90_throughput": st.get("p90_throughput"),
                "request_count_30m": st.get("request_count"),
                "recent_peak_rpm": f.get("recent_peak_rpm"),
                "capacity_ceiling_rpm": f.get("capacity_ceiling_rpm"),
                "success_30m": sh30.get("success"),
                "rate_limited_30m": sh30.get("rateLimited"),
                "derankable_error_30m": sh30.get("derankableError"),
                "success_5m": sh5.get("success"),
                "rate_limited_5m": sh5.get("rateLimited"),
                "is_deranked": bool(ep.get("is_deranked")),
            }
        )
    return rows


def _sf(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


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

        # live congestion stats for the hottest models (demand-side panel)
        congestion_rows: list[dict[str, Any]] = []
        rankings = await fetcher.get_json(RANKINGS_URL)
        hot = _hot_permaslugs(rankings)
        if hot:
            stat_urls = [f"{STATS_URL}?permaslug={quote(s, safe='')}&variant=standard" for s in hot]
            stat_bodies = await asyncio.gather(*(fetcher.get_json(u) for u in stat_urls))
            for slug, body in zip(hot, stat_bodies, strict=True):
                congestion_rows += _congestion_rows(body, slug, run_ts, dt)

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
    if congestion_rows:
        write_partition(
            pa.Table.from_pylist(congestion_rows),
            "congestion_intraday",
            run_ts,
            dt,
            curated_dir,
        )
    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "models": models_tbl.num_rows,
        "endpoints": endpoints_tbl.num_rows,
        "providers": providers_tbl.num_rows,
        "endpoint_fetch_failures": failures,
        "congestion_rows": len(congestion_rows),
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
