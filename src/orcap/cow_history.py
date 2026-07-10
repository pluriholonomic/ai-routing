"""Manual, cost-capped historical CoW finality backfill from BigQuery.

This module deliberately has no scheduled entry point.  It reads the public
Ethereum log table for a *short, explicit UTC window*, first dry-runs the
query, then refuses execution unless the caller supplies ``--execute``.  The
result is an archival input for descriptive, finalized-settlement analysis;
it is not an order-flow, surplus, demand, or routing-allocation feed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .capture_markets import (
    GPV2_SETTLEMENT_ADDRESS,
    GPV2_SETTLEMENT_TOPIC,
    GPV2_TRADE_TOPIC,
    cow_rpc_log_rows,
)
from .config import DATA_DIR, run_timestamp
from .defi_benchmarks import _bq_project

PUBLIC_LOG_TABLE = "bigquery-public-data.crypto_ethereum.logs"
MAX_WINDOW_DAYS = 14
MAX_BYTES_BILLED = 50 * 1024**3


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"expected YYYY-MM-DD, got {value!r}") from exc


def validate_window(start: str, end: str) -> tuple[date, date]:
    """Validate an explicit, end-exclusive UTC date range."""
    start_day, end_day = _parse_day(start), _parse_day(end)
    if end_day <= start_day:
        raise ValueError("end must be after start (the end date is exclusive)")
    if (end_day - start_day).days > MAX_WINDOW_DAYS:
        raise ValueError(
            f"window is {(end_day - start_day).days} days; maximum is {MAX_WINDOW_DAYS}"
        )
    return start_day, end_day


def cow_log_query() -> str:
    """Canonical GPv2 finality query, parameterized by UTC date bounds."""
    return f"""
        SELECT block_timestamp, block_number, block_hash, transaction_hash,
               log_index, address, data, topics
        FROM `{PUBLIC_LOG_TABLE}`
        WHERE block_timestamp >= TIMESTAMP(@start)
          AND block_timestamp < TIMESTAMP(@end)
          AND address = @settlement_address
          AND topics[SAFE_OFFSET(0)] IN UNNEST(@event_topics)
        ORDER BY block_timestamp, transaction_hash, log_index
    """


def query_fingerprint() -> str:
    return hashlib.sha256(cow_log_query().encode()).hexdigest()


def _job_config(bigquery: Any, start: date, end: date, *, dry_run: bool) -> Any:
    config = bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        query_parameters=[
            bigquery.ScalarQueryParameter("start", "DATE", start.isoformat()),
            bigquery.ScalarQueryParameter("end", "DATE", end.isoformat()),
            bigquery.ScalarQueryParameter("settlement_address", "STRING", GPV2_SETTLEMENT_ADDRESS),
            bigquery.ArrayQueryParameter(
                "event_topics", "STRING", [GPV2_TRADE_TOPIC, GPV2_SETTLEMENT_TOPIC]
            ),
        ],
    )
    if not dry_run:
        config.maximum_bytes_billed = MAX_BYTES_BILLED
    return config


def dry_run(start: str, end: str, *, client: Any | None = None) -> dict[str, Any]:
    """Return the projected scan, refusing over-cap ranges before execution."""
    start_day, end_day = validate_window(start, end)
    if client is None:
        from google.cloud import bigquery

        client = bigquery.Client(project=_bq_project())
    else:
        from google.cloud import bigquery

    job = client.query(
        cow_log_query(), job_config=_job_config(bigquery, start_day, end_day, dry_run=True)
    )
    processed = int(job.total_bytes_processed or 0)
    result = {
        "start": start_day.isoformat(),
        "end_exclusive": end_day.isoformat(),
        "window_days": (end_day - start_day).days,
        "public_table": PUBLIC_LOG_TABLE,
        "query_sha256": query_fingerprint(),
        "projected_bytes_processed": processed,
        "projected_gib_processed": processed / 1024**3,
        "maximum_bytes_billed": MAX_BYTES_BILLED,
        "maximum_gib_billed": MAX_BYTES_BILLED / 1024**3,
    }
    if processed > MAX_BYTES_BILLED:
        raise RuntimeError(
            f"backfill would scan {result['projected_gib_processed']:.2f} GiB, "
            f"above the {result['maximum_gib_billed']:.0f} GiB cap; narrow the window"
        )
    return result


def fetch(
    start: str, end: str, *, client: Any | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Execute a cap-checked history query after its mandatory dry run."""
    metadata = dry_run(start, end, client=client)
    start_day, end_day = validate_window(start, end)
    if client is None:
        from google.cloud import bigquery

        client = bigquery.Client(project=_bq_project())
    else:
        from google.cloud import bigquery

    job = client.query(
        cow_log_query(), job_config=_job_config(bigquery, start_day, end_day, dry_run=False)
    )
    frame = job.result().to_dataframe(create_bqstorage_client=False)
    actual = int(job.total_bytes_processed or 0)
    if actual > MAX_BYTES_BILLED:
        raise RuntimeError("BigQuery job exceeded the configured billing cap")
    metadata |= {
        "executed_at": datetime.now(UTC).isoformat(),
        "actual_bytes_processed": actual,
        "actual_gib_processed": actual / 1024**3,
        "raw_log_rows": int(len(frame)),
    }
    return frame, metadata


def _hex(value: Any) -> str:
    if isinstance(value, int):
        return hex(value)
    if not isinstance(value, str):
        raise ValueError("expected hexadecimal/string field in BigQuery log row")
    return value if value.startswith("0x") else f"0x{value}"


def _timestamp(value: Any) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")


def bq_rows_to_rpc_logs(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[int, str]]:
    """Map the public-table schema to the already-tested GPv2 log decoder."""
    required = {
        "block_timestamp",
        "block_number",
        "block_hash",
        "transaction_hash",
        "log_index",
        "data",
        "topics",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"BigQuery result is missing required fields: {sorted(missing)}")
    logs: list[dict[str, Any]] = []
    block_times: dict[int, str] = {}
    for row in frame.to_dict("records"):
        topics = row["topics"]
        if isinstance(topics, (str, bytes)) or not hasattr(topics, "__iter__"):
            continue
        topics = list(topics)
        block_number = int(row["block_number"])
        block_time = _timestamp(row["block_timestamp"])
        block_times[block_number] = block_time
        logs.append(
            {
                "topics": [str(topic).lower() for topic in topics],
                "transactionHash": str(row["transaction_hash"]).lower(),
                "logIndex": _hex(row["log_index"]),
                "blockNumber": _hex(block_number),
                "blockHash": str(row["block_hash"]).lower(),
                "data": _hex(row["data"]),
            }
        )
    return logs, block_times


def normalize(
    frame: pd.DataFrame, *, captured_at: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return canonical finality records with BigQuery-specific provenance."""
    captured_at = captured_at or run_timestamp()
    logs, block_times = bq_rows_to_rpc_logs(frame)
    executions, events = cow_rpc_log_rows(logs, block_times, captured_at, "historical-backfill")
    for rows, time_key in ((executions, "executed_at"), (events, "event_time")):
        for row in rows:
            timestamp = row.get(time_key)
            if timestamp:
                row["dt"] = pd.Timestamp(timestamp).date().isoformat()
            row["backfill_source"] = "bigquery-public-data.crypto_ethereum.logs"
            row["quality_tier"] = (
                "onchain-finalized-public-bigquery; GPv2Settlement event log; "
                "historical backfill, not a live-RPC observation"
            )
    execution_frame = pd.DataFrame(executions)
    event_frame = pd.DataFrame(events)
    return execution_frame, event_frame


def save_backfill(
    raw_logs: pd.DataFrame,
    executions: pd.DataFrame,
    events: pd.DataFrame,
    metadata: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Path]:
    """Persist raw and normalized local-only files with a matching manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"cow_bq_{metadata['start']}_{metadata['end_exclusive']}"
    paths = {
        "raw_logs": output_dir / f"{stem}_raw_logs.parquet",
        "executions": output_dir / f"{stem}_executions.parquet",
        "events": output_dir / f"{stem}_events.parquet",
        "manifest": output_dir / f"{stem}_manifest.json",
    }
    raw_logs.to_parquet(paths["raw_logs"], index=False)
    executions.to_parquet(paths["executions"], index=False)
    events.to_parquet(paths["events"], index=False)
    paths["manifest"].write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="inclusive UTC date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="exclusive UTC date (YYYY-MM-DD)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run after the mandatory dry run (otherwise print cost estimate only)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_DIR / "external" / "cow_bigquery_history",
        help="local-only output directory; this command never uploads",
    )
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dry_run(args.start, args.end), indent=2, sort_keys=True))
        return 0
    frame, metadata = fetch(args.start, args.end)
    executions, events = normalize(frame)
    paths = save_backfill(frame, executions, events, metadata, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                **metadata,
                "normalized_executions": int(len(executions)),
                "normalized_events": int(len(events)),
                "paths": {key: str(value) for key, value in paths.items()},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
