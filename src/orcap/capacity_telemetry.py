"""Redacted provider/model/epoch capacity commitments for H48 counterfactuals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, dt_partition, run_timestamp

REQUIRED = {
    "commitment_id",
    "observed_at",
    "study_id",
    "provider",
    "model_id",
    "epoch_start",
    "epoch_end",
    "committed_requests",
}
OUTCOME_REQUIRED = {
    "outcome_id",
    "observed_at",
    "study_id",
    "provider",
    "model_id",
    "epoch_start",
    "epoch_end",
    "allocated_requests",
    "served_requests",
}
FORBIDDEN = {
    "api_key",
    "authorization",
    "completion",
    "content",
    "input",
    "messages",
    "output",
    "prompt",
    "raw_request",
    "raw_response",
    "response",
    "secret",
    "token",
}


def _forbidden_keys(value: Any) -> set[str]:
    """Return prohibited payload/credential keys, including nested metadata."""
    if isinstance(value, dict):
        found = set(value).intersection(FORBIDDEN)
        for nested in value.values():
            found |= _forbidden_keys(nested)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for nested in value:
            found |= _forbidden_keys(nested)
        return found
    return set()


def _missing_required(record: dict[str, Any], required: set[str]) -> list[str]:
    """Treat zero commitment as valid while rejecting missing/blank identifiers."""
    return sorted(
        field
        for field in required
        if field not in record or record[field] is None or record[field] == ""
    )


def validate_commitment(record: dict[str, Any]) -> dict[str, Any]:
    """Validate one privacy-preserving provider/model/epoch commitment.

    A zero commitment is a valid observed declaration. It can be useful for
    detecting a provider/model that is explicitly unavailable in an epoch, so
    it must not be collapsed into a missing observation.
    """
    missing = _missing_required(record, REQUIRED)
    if missing:
        raise ValueError(f"capacity commitment missing required fields: {', '.join(missing)}")
    forbidden = sorted(_forbidden_keys(record))
    if forbidden:
        raise ValueError(
            "capacity commitment contains forbidden payload fields: " + ", ".join(forbidden)
        )
    try:
        committed = float(record["committed_requests"])
    except (TypeError, ValueError) as exc:
        raise ValueError("committed_requests must be numeric") from exc
    if committed < 0:
        raise ValueError("committed_requests must be non-negative")
    return {
        "commitment_id": str(record["commitment_id"]),
        "observed_at": str(record["observed_at"]),
        "study_id": str(record["study_id"]),
        "provider": str(record["provider"]),
        "model_id": str(record["model_id"]),
        "epoch_start": str(record["epoch_start"]),
        "epoch_end": str(record["epoch_end"]),
        "committed_requests": committed,
        "verification_method": record.get("verification_method"),
        "marginal_cost_usd_per_request": _number(
            record.get("marginal_cost_usd_per_request")
        ),
        "metadata_json": json.dumps(
            record.get("metadata") or {}, separators=(",", ":"), sort_keys=True
        ),
        "payload_retained": False,
    }


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_commitments(
    records: list[dict[str, Any]], *, curated_dir: Path = CURATED_DIR
) -> Path | None:
    if not records:
        return None
    rows = [validate_commitment(record) for record in records]
    if len({row["commitment_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate commitment_id in batch")
    run_ts, dt = run_timestamp(), dt_partition()
    return write_partition(
        pa.Table.from_pylist([row | {"run_ts": run_ts, "dt": dt} for row in rows]),
        "router_capacity_commitments",
        run_ts,
        dt,
        curated_dir,
    )


def validate_outcome(record: dict[str, Any]) -> dict[str, Any]:
    """Validate aggregate allocated/served results for one controlled epoch.

    This is intentionally an epoch-level aggregate. It complements redacted
    route attempts without retaining prompts, completions, or per-request
    content, and makes the capacity mechanism's allocated/served primitive
    observable in a controlled study.
    """
    missing = _missing_required(record, OUTCOME_REQUIRED)
    if missing:
        raise ValueError(f"capacity outcome missing required fields: {', '.join(missing)}")
    forbidden = sorted(_forbidden_keys(record))
    if forbidden:
        raise ValueError(
            "capacity outcome contains forbidden payload fields: " + ", ".join(forbidden)
        )
    try:
        allocated = float(record["allocated_requests"])
        served = float(record["served_requests"])
    except (TypeError, ValueError) as exc:
        raise ValueError("allocated_requests and served_requests must be numeric") from exc
    if allocated < 0 or served < 0:
        raise ValueError("allocated_requests and served_requests must be non-negative")
    if served > allocated:
        raise ValueError("served_requests cannot exceed allocated_requests")
    return {
        "outcome_id": str(record["outcome_id"]),
        "observed_at": str(record["observed_at"]),
        "study_id": str(record["study_id"]),
        "provider": str(record["provider"]),
        "model_id": str(record["model_id"]),
        "epoch_start": str(record["epoch_start"]),
        "epoch_end": str(record["epoch_end"]),
        "allocated_requests": allocated,
        "served_requests": served,
        "shortfall_requests": allocated - served,
        "verification_method": record.get("verification_method"),
        "realized_cost_usd": _number(record.get("realized_cost_usd")),
        "realized_revenue_usd": _number(record.get("realized_revenue_usd")),
        "metadata_json": json.dumps(
            record.get("metadata") or {}, separators=(",", ":"), sort_keys=True
        ),
        "payload_retained": False,
    }


def write_outcomes(
    records: list[dict[str, Any]], *, curated_dir: Path = CURATED_DIR
) -> Path | None:
    """Write one redacted allocated/served aggregate per immutable outcome id."""
    if not records:
        return None
    rows = [validate_outcome(record) for record in records]
    if len({row["outcome_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate outcome_id in batch")
    run_ts, dt = run_timestamp(), dt_partition()
    return write_partition(
        pa.Table.from_pylist([row | {"run_ts": run_ts, "dt": dt} for row in rows]),
        "router_capacity_epoch_outcomes",
        run_ts,
        dt,
        curated_dir,
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row at {path}:{line_number} is not an object")
        rows.append(row)
    return rows
