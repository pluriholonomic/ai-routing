"""Payload-free router decision and aggregate-flow telemetry contracts.

Public quote snapshots and owned request telemetry cannot establish request
ordering at a router.  This module is the separate, private landing zone for
an opt-in router or provider export.  It deliberately refuses prompts,
completions, account identifiers, network identifiers, credentials, and raw
payloads.  It also does not contact a router, issue probes, or alter routing.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, dt_partition, run_timestamp
from .route_telemetry import load_jsonl

DECISION_OUTCOMES = {"succeeded", "failed", "cancelled", "unknown"}
EXPERIMENT_ARMS = {"observational", "provider_visible", "provider_blinded", "decoy_signal"}
ACTION_CLASSES = {"none", "quote", "capacity", "quote_and_capacity", "unknown"}
SOURCES = {"router_decision_export", "provider_router_joint_export"}
FORBIDDEN_PAYLOAD_KEYS = {
    "account",
    "api_key",
    "authorization",
    "completion",
    "content",
    "email",
    "input",
    "ip",
    "messages",
    "output",
    "phone",
    "prompt",
    "raw_request",
    "raw_response",
    "response",
    "secret",
    "token",
    "user",
}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+=-]{1,255}$")


def _forbidden_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = set(value).intersection(FORBIDDEN_PAYLOAD_KEYS)
        for nested in value.values():
            found |= _forbidden_keys(nested)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for nested in value:
            found |= _forbidden_keys(nested)
        return found
    return set()


def _timestamp(value: Any, field: str, *, required: bool = True) -> str | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{field} must be an ISO-8601 timestamp")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _id(value: Any, field: str, *, required: bool = True) -> str | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{field} must be a stable non-payload identifier")
        return None
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} must be a stable non-payload identifier")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a non-negative integer") from exc
    if number < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return number


def validate_decision_event(event: dict[str, Any]) -> dict[str, Any]:
    """Validate one timestamped, redacted router-decision event.

    Quote actions before arrival are retained as valid background actions; the
    later H70 audit labels them as outside the selection window rather than
    pretending that all quote changes were request-triggered.
    """
    if not isinstance(event, dict):
        raise ValueError("router decision event must be an object")
    forbidden = sorted(_forbidden_keys(event))
    if forbidden:
        raise ValueError(
            "router decision event contains forbidden payload fields: " + ", ".join(forbidden)
        )
    source = event.get("source", "router_decision_export")
    if source not in SOURCES:
        raise ValueError(f"unsupported router decision source: {source}")
    outcome = event.get("retry_outcome", "unknown")
    if outcome not in DECISION_OUTCOMES:
        raise ValueError(f"unsupported retry_outcome: {outcome}")
    arm = event.get("experiment_arm", "observational")
    if arm not in EXPERIMENT_ARMS:
        raise ValueError(f"unsupported experiment_arm: {arm}")
    if arm != "observational" and not event.get("assignment_id"):
        raise ValueError("non-observational experiment_arm requires assignment_id")
    action_class = event.get("action_class", "unknown")
    if action_class not in ACTION_CLASSES:
        raise ValueError(f"unsupported action_class: {action_class}")
    arrival_at = _timestamp(event.get("arrival_at"), "arrival_at")
    committed_at = _timestamp(event.get("route_committed_at"), "route_committed_at")
    if pd_timestamp(committed_at) < pd_timestamp(arrival_at):
        raise ValueError("route_committed_at must not precede arrival_at")
    return {
        "event_id": _id(event.get("event_id"), "event_id"),
        "study_id": _id(event.get("study_id"), "study_id"),
        "router": _id(event.get("router"), "router"),
        "source": source,
        "request_ref": _id(event.get("request_ref"), "request_ref", required=False),
        "arrival_at": arrival_at,
        "route_committed_at": committed_at,
        "candidate_set_version": _id(event.get("candidate_set_version"), "candidate_set_version"),
        "selected_endpoint": _id(
            event.get("selected_endpoint"), "selected_endpoint", required=False
        ),
        "retry_outcome": outcome,
        "retry_count": _nonnegative_int(event.get("retry_count", 0), "retry_count"),
        "quote_or_capacity_action_at": _timestamp(
            event.get("quote_or_capacity_action_at"),
            "quote_or_capacity_action_at",
            required=False,
        ),
        "provider_signal_at": _timestamp(
            event.get("provider_signal_at"), "provider_signal_at", required=False
        ),
        "action_class": action_class,
        "experiment_arm": arm,
        "assignment_id": _id(event.get("assignment_id"), "assignment_id", required=False),
        "payload_retained": False,
    }


def pd_timestamp(value: str) -> datetime:
    """Parse a timestamp normalized by :func:`_timestamp` without pandas."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_flow_aggregate(record: dict[str, Any]) -> dict[str, Any]:
    """Validate a fixed-interval, provider-model aggregate for residual-flow work."""
    if not isinstance(record, dict):
        raise ValueError("router flow aggregate must be an object")
    forbidden = sorted(_forbidden_keys(record))
    if forbidden:
        raise ValueError(
            "router flow aggregate contains forbidden payload fields: " + ", ".join(forbidden)
        )
    interval_start = _timestamp(record.get("interval_start"), "interval_start")
    interval_end = _timestamp(record.get("interval_end"), "interval_end")
    if pd_timestamp(interval_end) <= pd_timestamp(interval_start):
        raise ValueError("interval_end must be after interval_start")
    attempted = _nonnegative_int(record.get("attempted_routes"), "attempted_routes")
    selected = _nonnegative_int(record.get("selected_routes"), "selected_routes")
    succeeded = _nonnegative_int(record.get("succeeded_routes"), "succeeded_routes")
    fallback = _nonnegative_int(record.get("fallback_routes", 0), "fallback_routes")
    if selected > attempted or succeeded > selected or fallback > attempted:
        raise ValueError("aggregate route counts must be internally consistent")
    return {
        "aggregate_id": _id(record.get("aggregate_id"), "aggregate_id"),
        "study_id": _id(record.get("study_id"), "study_id"),
        "router": _id(record.get("router"), "router"),
        "source": "router_flow_aggregate",
        "model_id": _id(record.get("model_id"), "model_id"),
        "endpoint": _id(record.get("endpoint"), "endpoint"),
        "candidate_set_version": _id(record.get("candidate_set_version"), "candidate_set_version"),
        "interval_start": interval_start,
        "interval_end": interval_end,
        "public_quote_snapshot_id": _id(
            record.get("public_quote_snapshot_id"), "public_quote_snapshot_id", required=False
        ),
        "attempted_routes": attempted,
        "selected_routes": selected,
        "succeeded_routes": succeeded,
        "fallback_routes": fallback,
        "quote_or_capacity_action_at": _timestamp(
            record.get("quote_or_capacity_action_at"),
            "quote_or_capacity_action_at",
            required=False,
        ),
        "payload_retained": False,
    }


def _write(rows: list[dict[str, Any]], table: str, *, curated_dir: Path) -> Path | None:
    if not rows:
        return None
    run_ts, dt = run_timestamp(), dt_partition()
    return write_partition(
        pa.Table.from_pylist([row | {"run_ts": run_ts, "dt": dt} for row in rows]),
        table,
        run_ts,
        dt,
        curated_dir,
    )


def write_decision_events(
    events: list[dict[str, Any]], *, curated_dir: Path = CURATED_DIR
) -> Path | None:
    rows = [validate_decision_event(event) for event in events]
    if len({row["event_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate event_id router decision events in one batch")
    return _write(rows, "router_decision_events", curated_dir=curated_dir)


def write_flow_aggregates(
    records: list[dict[str, Any]], *, curated_dir: Path = CURATED_DIR
) -> Path | None:
    rows = [validate_flow_aggregate(record) for record in records]
    if len({row["aggregate_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate aggregate_id router flow aggregates in one batch")
    return _write(rows, "router_flow_aggregates", curated_dir=curated_dir)


def decisions_main(path: str) -> None:
    events = load_jsonl(Path(path))
    output = write_decision_events(events)
    print(json.dumps({"rows": len(events), "path": str(output) if output else None}, indent=2))


def flow_aggregates_main(path: str) -> None:
    records = load_jsonl(Path(path))
    output = write_flow_aggregates(records)
    print(json.dumps({"rows": len(records), "path": str(output) if output else None}, indent=2))
