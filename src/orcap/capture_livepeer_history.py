"""Bounded historical, aggregate-only Livepeer Gateway routing capture.

The public Loki endpoint supports query_range for the same aggregate LogQL
counters used by the live sampler. This module never queries log-stream lines
or labels beyond public region, so it cannot collect client, session, manifest,
or orchestrator identifiers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pyarrow as pa

from .capture_api import write_partition
from .capture_livepeer import (
    DEFAULT_WINDOW_MINUTES,
    LIVEPEER_LOKI_BASE_URL,
    METRICS,
    _count_expression,
    _regions,
)
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_HOURS = 24
MAX_LOOKBACK_HOURS = 168


def _range_query_url(expression: str, start_s: int, end_s: int, step_s: int) -> str:
    """Build a public aggregate query_range URL using nanosecond bounds."""
    return f"{LIVEPEER_LOKI_BASE_URL}/query_range?{
        urlencode(
            {
                'query': expression,
                'start': start_s * 1_000_000_000,
                'end': end_s * 1_000_000_000,
                'step': step_s,
            }
        )
    }"


def _timestamp(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    if timestamp > 10_000_000_000:
        timestamp /= 1_000_000_000
    return int(timestamp)


def _count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        count = int(float(value))
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def range_counts(body: Any) -> dict[tuple[int, str], int]:
    """Parse a Loki matrix response, rejecting malformed aggregate data."""
    if not isinstance(body, dict) or body.get("status") != "success":
        raise ValueError("Livepeer Loki range query did not return status=success")
    data = body.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "matrix":
        raise ValueError("Livepeer Loki range query did not return a matrix")
    counts: dict[tuple[int, str], int] = {}
    for result in data.get("result") or []:
        if not isinstance(result, dict):
            raise ValueError("Livepeer Loki range response contained a non-object result")
        region = (result.get("metric") or {}).get("region")
        values = result.get("values")
        if not isinstance(region, str) or not region or not isinstance(values, list):
            raise ValueError("Livepeer Loki range response omitted region or values")
        for value in values:
            if not isinstance(value, list) or len(value) < 2:
                raise ValueError("Livepeer Loki range response contained an invalid sample")
            timestamp, count = _timestamp(value[0]), _count(value[1])
            if timestamp is None or count is None:
                raise ValueError("Livepeer Loki range response contained an invalid count")
            key = (timestamp, region)
            if key in counts:
                raise ValueError("Livepeer Loki range response contained duplicate region samples")
            counts[key] = count
    return counts


def gateway_history_rows(
    regions: list[str],
    metric_bodies: dict[str, Any],
    capture_run_ts: str,
    dt: str,
    window_minutes: int,
) -> list[dict[str, Any]]:
    """Normalize historical regional counters without retaining stream-level data."""
    if set(metric_bodies) != set(METRICS):
        raise ValueError("Livepeer range response must include every aggregate metric")
    counts = {name: range_counts(body) for name, body in metric_bodies.items()}
    timestamps = sorted({timestamp for metric in counts.values() for timestamp, _ in metric})
    observed_regions = {region for metric in counts.values() for _, region in metric}
    all_regions = sorted(set(regions).union(observed_regions))
    if not timestamps or not all_regions:
        return []
    rows = []
    for timestamp in timestamps:
        observed_at = datetime.fromtimestamp(timestamp, UTC)
        for region in all_regions:
            swaps = counts["swap_events"].get((timestamp, region), 0)
            reuses = counts["reuse_events"].get((timestamp, region), 0)
            inflight_reuses = min(
                counts["inflight_reuse_events"].get((timestamp, region), 0), reuses
            )
            rows.append(
                {
                    "run_ts": capture_run_ts,
                    "dt": dt,
                    "source": "livepeer_gateway",
                    "venue": "livepeer-gateway",
                    "region": region,
                    "source_observed_at": observed_at.isoformat(),
                    "source_window_end_unix_s": timestamp,
                    "rolling_window_minutes": window_minutes,
                    "swap_events": swaps,
                    "reuse_events": reuses,
                    "inflight_reuse_events": inflight_reuses,
                    "decision_events": swaps + reuses,
                    "metric_definition": (
                        "Historical aggregate public Gateway LogQL counts for orchestrator "
                        "swap/reuse routing messages in fixed rolling windows. No stream, "
                        "session, client, manifest, or orchestrator identifier is collected."
                    ),
                    "quality_tier": (
                        "public-gateway-log-aggregate; historical external routing control"
                    ),
                    "record_json": json.dumps(
                        {
                            "source_observed_at": observed_at.isoformat(),
                            "source_window_end_unix_s": timestamp,
                            "region": region,
                            "rolling_window_minutes": window_minutes,
                            "swap_events": swaps,
                            "reuse_events": reuses,
                            "inflight_reuse_events": inflight_reuses,
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                }
            )
    return rows


async def capture_livepeer_gateway_history(
    *,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    step_minutes: int = DEFAULT_WINDOW_MINUTES,
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
    now_s: int | None = None,
) -> dict[str, Any]:
    """Capture a bounded public aggregate history; the hard cap protects Loki."""
    if not 1 <= lookback_hours <= MAX_LOOKBACK_HOURS:
        raise ValueError(f"lookback_hours must be within 1..{MAX_LOOKBACK_HOURS}")
    if not 1 <= step_minutes <= 60:
        raise ValueError("step_minutes must be within 1..60")
    capture_run_ts, dt = run_timestamp(), dt_partition()
    end_s = int(now_s if now_s is not None else time.time())
    start_s = end_s - lookback_hours * 60 * 60
    step_s = step_minutes * 60
    expressions = {
        name: _count_expression(filter_expression, step_minutes)
        for name, filter_expression in METRICS.items()
    }
    regions_url = f"{LIVEPEER_LOKI_BASE_URL}/label/region/values"
    async with make_client() as client:
        fetcher = Fetcher(client, rps=0.5)
        regions_body = await fetcher.get_json(regions_url)
        metric_results = await asyncio.gather(
            *(
                fetcher.get_json(_range_query_url(expression, start_s, end_s, step_s))
                for expression in expressions.values()
            )
        )
        write_raw(fetcher.records, "livepeer_gateway_history", raw_dir, capture_run_ts, dt)
    regions = _regions(regions_body)
    if not regions:
        write_source_run(
            "livepeer_gateway",
            status="failed",
            run_ts=capture_run_ts,
            dt=dt,
            detail={
                "base_url": LIVEPEER_LOKI_BASE_URL,
                "lookback_hours": lookback_hours,
                "step_minutes": step_minutes,
                "error": "no public Gateway regions returned",
            },
            curated_dir=curated_dir,
        )
        raise RuntimeError("Livepeer Loki returned no public Gateway regions")
    metric_bodies = dict(zip(expressions, metric_results, strict=True))
    rows = gateway_history_rows(regions, metric_bodies, capture_run_ts, dt, step_minutes)
    if not rows:
        raise RuntimeError("Livepeer Loki returned no historical aggregate routing rows")
    write_partition(
        pa.Table.from_pylist(rows),
        "livepeer_gateway_metrics",
        capture_run_ts,
        dt,
        curated_dir,
    )
    source_times = [row["source_observed_at"] for row in rows]
    detail = {
        "base_url": LIVEPEER_LOKI_BASE_URL,
        "lookback_hours": lookback_hours,
        "step_minutes": step_minutes,
        "source_start": min(source_times),
        "source_end": max(source_times),
        "regions": regions,
        "queries": sorted(expressions),
        "privacy_boundary": (
            "aggregate LogQL query_range counters only; no raw log lines or client/session/"
            "manifest/orchestrator identifiers"
        ),
    }
    write_source_run(
        "livepeer_gateway",
        status="success",
        rows=len(rows),
        run_ts=capture_run_ts,
        dt=dt,
        detail=detail,
        curated_dir=curated_dir,
    )
    return {"run_ts": capture_run_ts, "dt": dt, "rows": len(rows), **detail}


def main(*, lookback_hours: int = DEFAULT_LOOKBACK_HOURS, step_minutes: int = 5) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(
        capture_livepeer_gateway_history(
            lookback_hours=lookback_hours,
            step_minutes=step_minutes,
        )
    )
    print(json.dumps(result, indent=2, default=str))
    return result
