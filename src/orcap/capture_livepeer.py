"""Privacy-preserving capture of Livepeer Gateway routing-adjustment aggregates.

Livepeer publishes public Gateway logs through Loki. The raw log stream contains
per-stream identifiers, which this collector deliberately never requests. It
uses only aggregate LogQL count queries by public region and persists those
aggregate responses as the raw provenance record. The result is an external
control for observed decentralized gateway routing adjustments, not an LLM
router tape, provider allocation feed, price quote, or delivery record.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

LIVEPEER_LOKI_BASE_URL = "https://loki.livepeer.report/loki/api/v1"
DEFAULT_WINDOW_MINUTES = 5
METRICS = {
    "swap_events": '|= "Swapping Orchestrator"',
    "reuse_events": '|= "Reusing"',
    "inflight_reuse_events": (
        '|= "Reusing" |= "segments in flight" !~ "no segments in flight"'
    ),
}


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _window_minutes() -> int:
    raw = os.environ.get("ORCAP_LIVEPEER_WINDOW_MINUTES", str(DEFAULT_WINDOW_MINUTES))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WINDOW_MINUTES
    return min(60, max(1, value))


def _query_url(expression: str) -> str:
    return f"{LIVEPEER_LOKI_BASE_URL}/query?{urlencode({'query': expression})}"


def _count_expression(filter_expression: str, window_minutes: int) -> str:
    """Build an aggregate-only query with no stream, session, or client IDs."""
    return (
        'sum by (region) (count_over_time({region=~".+"} '
        f"{filter_expression} [{window_minutes}m]))"
    )


def _regions(body: Any) -> list[str]:
    if not isinstance(body, dict) or body.get("status") != "success":
        return []
    values = body.get("data")
    if not isinstance(values, list):
        return []
    return sorted({str(value) for value in values if isinstance(value, str) and value})


def _vector_counts(body: Any) -> dict[str, int]:
    """Parse a successful Loki instant-vector response into non-negative counts."""
    if not isinstance(body, dict) or body.get("status") != "success":
        raise ValueError("Livepeer Loki query did not return status=success")
    data = body.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        raise ValueError("Livepeer Loki query did not return an instant vector")
    counts: dict[str, int] = {}
    for result in data.get("result") or []:
        if not isinstance(result, dict):
            continue
        region = (result.get("metric") or {}).get("region")
        value = result.get("value")
        if not isinstance(region, str) or not isinstance(value, list) or len(value) < 2:
            continue
        try:
            count = int(float(value[1]))
        except (TypeError, ValueError):
            continue
        counts[region] = max(0, count)
    return counts


def gateway_metric_rows(
    regions: list[str],
    metric_bodies: dict[str, Any],
    run_ts: str,
    dt: str,
    window_minutes: int,
) -> list[dict[str, Any]]:
    """Normalize aggregate Livepeer decision counts by Gateway region.

    A zero in a successful aggregate response means no matching public log in
    the rolling window. It does not mean a Gateway, orchestrator, or worker was
    unavailable, and it does not reveal selected orchestrator identity.
    """
    counts = {name: _vector_counts(metric_bodies[name]) for name in METRICS}
    rows = []
    for region in regions:
        swaps = counts["swap_events"].get(region, 0)
        reuses = counts["reuse_events"].get(region, 0)
        inflight_reuses = min(counts["inflight_reuse_events"].get(region, 0), reuses)
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "livepeer_gateway",
                "venue": "livepeer-gateway",
                "region": region,
                "rolling_window_minutes": window_minutes,
                "swap_events": swaps,
                "reuse_events": reuses,
                "inflight_reuse_events": inflight_reuses,
                "decision_events": swaps + reuses,
                "metric_definition": (
                    "Aggregate public Gateway log counts for orchestrator swap/reuse routing "
                    "messages in a rolling window. No stream/session/client identifier or "
                    "orchestrator identity is collected."
                ),
                "quality_tier": "public-gateway-log-aggregate; external routing control",
                "record_json": _json(
                    {
                        "region": region,
                        "rolling_window_minutes": window_minutes,
                        "swap_events": swaps,
                        "reuse_events": reuses,
                        "inflight_reuse_events": inflight_reuses,
                    }
                ),
            }
        )
    return rows


async def capture_livepeer_gateway(
    raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR
) -> dict[str, Any]:
    """Capture aggregate recent Gateway routing decisions from the public Loki API."""
    run_ts, dt = run_timestamp(), dt_partition()
    window_minutes = _window_minutes()
    regions_url = f"{LIVEPEER_LOKI_BASE_URL}/label/region/values"
    expressions = {
        name: _count_expression(filter_expression, window_minutes)
        for name, filter_expression in METRICS.items()
    }
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        regions_body = await fetcher.get_json(regions_url)
        metric_results = await asyncio.gather(
            *(fetcher.get_json(_query_url(expression)) for expression in expressions.values())
        )
        write_raw(fetcher.records, "livepeer_gateway", raw_dir, run_ts, dt)
    regions = _regions(regions_body)
    if not regions:
        raise RuntimeError("Livepeer Loki returned no public Gateway regions")
    metric_bodies = dict(zip(expressions, metric_results, strict=True))
    rows = gateway_metric_rows(regions, metric_bodies, run_ts, dt, window_minutes)
    if not rows:
        raise RuntimeError("Livepeer Loki returned no aggregate routing rows")
    write_partition(pa.Table.from_pylist(rows), "livepeer_gateway_metrics", run_ts, dt, curated_dir)
    write_source_run(
        "livepeer_gateway",
        status="success",
        rows=len(rows),
        run_ts=run_ts,
        dt=dt,
        detail={
            "base_url": LIVEPEER_LOKI_BASE_URL,
            "regions": regions,
            "rolling_window_minutes": window_minutes,
            "queries": sorted(expressions),
            "privacy_boundary": "aggregate LogQL counters only; no raw stream/session/client IDs",
        },
        curated_dir=curated_dir,
    )
    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "regions": len(regions),
        "rows": len(rows),
        "rolling_window_minutes": window_minutes,
    }
    log.info("Livepeer Gateway aggregate capture: %s", summary)
    return summary


async def capture_loop(samples: int, interval_seconds: float) -> list[dict[str, Any]]:
    if samples < 1:
        raise ValueError("samples must be positive")
    summaries = []
    for index in range(samples):
        started = time.monotonic()
        summaries.append(await capture_livepeer_gateway())
        if index < samples - 1:
            await asyncio.sleep(max(0.0, interval_seconds - (time.monotonic() - started)))
    return summaries


def main(samples: int = 1, interval_seconds: float = 300.0) -> list[dict[str, Any]]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(capture_loop(samples, interval_seconds))


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
