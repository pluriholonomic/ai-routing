"""Backfill exact Akash lease-close reasons for the retained public lease tape.

The hourly market collector captures close reasons prospectively. This bounded
backfill recovers the same immutable ``EventLeaseClosed`` objects for leases
already retained in ``market_executions``. It never labels a close as workload
failure or delivery shortfall.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa

from .analysis import data
from .capture_api import write_partition
from .capture_markets import (
    AKASH_RPC_URL,
    _configured_url,
    _integer,
    akash_lease_close_event_rows,
)
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)


def _positive_int_env(name: str, default: int, *, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return min(maximum, max(1, value))


def _existing_ids() -> set[str]:
    try:
        glob = data.table_glob("akash_market_lease_close_events")
        frame = data.q(
            f"select distinct execution_id from read_parquet('{glob}', union_by_name=true)"
        ).df()
    except Exception:
        return set()
    return set(frame["execution_id"].dropna().astype(str))


def missing_close_blocks(max_blocks: int) -> dict[int, set[str]]:
    """Return the earliest missing exact close blocks, deterministically bounded."""
    glob = data.table_glob("market_executions")
    frame = data.q(
        f"""
        select execution_id, event_block_height
        from (
          select execution_id, event_block_height, lease_state,
                 row_number() over (
                   partition by execution_id order by run_ts desc
                 ) as revision_rank
          from read_parquet('{glob}', union_by_name=true)
          where source = 'akash'
        )
        where revision_rank = 1
          and lease_state = 'closed'
          and event_block_height is not null
        order by event_block_height, execution_id
        """
    ).df()
    existing = _existing_ids()
    candidates: dict[int, set[str]] = defaultdict(set)
    for row in frame.itertuples(index=False):
        execution_id = str(row.execution_id)
        height = _integer(row.event_block_height)
        if height is not None and execution_id not in existing:
            candidates[height].add(execution_id)
    return {height: candidates[height] for height in sorted(candidates)[:max_blocks]}


async def _fetch_payloads(
    expected: dict[int, set[str]], rps: int
) -> tuple[list[dict[str, Any]], Fetcher, list[int]]:
    rpc_url = _configured_url("ORCAP_AKASH_RPC_URL", AKASH_RPC_URL).rstrip("/")
    client = make_client()
    await client.__aenter__()
    fetcher = Fetcher(client, rps=float(rps))

    async def fetch(height: int) -> tuple[int, Any]:
        return height, await fetcher.get_json(f"{rpc_url}/block_results?height={height}")

    try:
        results = await asyncio.gather(*(fetch(height) for height in expected))
    except Exception:
        await client.__aexit__(None, None, None)
        raise
    malformed = []
    payloads = []
    for height, body in results:
        result = body.get("result") if isinstance(body, dict) else None
        returned = _integer(result.get("height")) if isinstance(result, dict) else None
        txs = result.get("txs_results") if isinstance(result, dict) else None
        if returned != height or (txs is not None and not isinstance(txs, list)):
            malformed.append(height)
            continue
        payloads.append(
            {
                "block_height": height,
                "expected_lease_ids": sorted(expected[height]),
                "body": body,
            }
        )
    await client.__aexit__(None, None, None)
    return payloads, fetcher, malformed


async def backfill(
    *,
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
    max_blocks: int | None = None,
    rps: int | None = None,
) -> dict[str, Any]:
    run_ts, dt = run_timestamp(), dt_partition()
    max_blocks = max_blocks or _positive_int_env(
        "ORCAP_AKASH_CLOSE_BACKFILL_MAX_BLOCKS", 5000, maximum=10_000
    )
    rps = rps or _positive_int_env("ORCAP_AKASH_CLOSE_BACKFILL_RPS", 8, maximum=10)
    expected = missing_close_blocks(max_blocks)
    if not expected:
        result = {
            "run_ts": run_ts,
            "dt": dt,
            "status": "complete",
            "blocks_requested": 0,
            "expected_leases": 0,
            "rows": 0,
        }
        write_source_run(
            "akash_lease_close_events_backfill",
            status="success",
            rows=0,
            run_ts=run_ts,
            dt=dt,
            detail=result,
            curated_dir=curated_dir,
        )
        return result

    payloads, fetcher, malformed = await _fetch_payloads(expected, rps)
    write_raw(fetcher.records, "akash_lease_close_events", raw_dir, run_ts, dt)
    if malformed:
        raise RuntimeError(
            "Akash close-event backfill received malformed block results at "
            + ",".join(str(height) for height in malformed[:20])
        )
    detail = {
        "coverage_complete": True,
        "start_height_exclusive": min(expected) - 1,
        "end_height_inclusive": max(expected),
        "raw_payload_source": "akash_lease_close_events",
    }
    rows = akash_lease_close_event_rows(payloads, detail, run_ts, dt)
    if rows:
        write_partition(
            pa.Table.from_pylist(rows),
            "akash_market_lease_close_events",
            run_ts,
            dt,
            curated_dir,
        )
    expected_leases = sum(len(ids) for ids in expected.values())
    match_rate = len(rows) / expected_leases if expected_leases else 1.0
    result = {
        "run_ts": run_ts,
        "dt": dt,
        "status": "complete" if match_rate == 1.0 else "source_event_gap",
        "blocks_requested": len(expected),
        "expected_leases": expected_leases,
        "rows": len(rows),
        "exact_event_match_rate": match_rate,
        "minimum_close_block": min(expected),
        "maximum_close_block": max(expected),
        "metric_boundary": (
            "exact public Akash lease-close reasons; on-chain termination path only, not "
            "workload delivery, failure, default, or intent"
        ),
    }
    write_source_run(
        "akash_lease_close_events_backfill",
        status="success" if match_rate == 1.0 else "degraded",
        rows=len(rows),
        watermark=str(max(expected)),
        run_ts=run_ts,
        dt=dt,
        detail=result,
        curated_dir=curated_dir,
    )
    return result


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(backfill())
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    main()
