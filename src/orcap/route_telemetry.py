"""Privacy-preserving contract for owned routing telemetry.

The public quote collectors cannot observe an actual selected provider.  This
module is the common landing contract for *owned* request logs from OpenRouter
generation metadata, Portkey, Cloudflare AI Gateway, or LiteLLM.  It rejects
prompt/completion payload fields by design; do not use it as a raw log archive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, dt_partition, run_timestamp

SUPPORTED_SOURCES = {
    "openrouter_generation",
    "portkey",
    "cloudflare_ai_gateway",
    "litellm",
}
OUTCOMES = {"succeeded", "failed", "cancelled", "unknown"}
FORBIDDEN_PAYLOAD_KEYS = {
    "completion",
    "content",
    "input",
    "messages",
    "output",
    "prompt",
    "raw_request",
    "raw_response",
    "response",
}
REQUIRED_FIELDS = {
    "event_id",
    "observed_at",
    "router",
    "source",
    "study_id",
    "model_id",
    "outcome",
}


def _forbidden_payload_keys(value: Any) -> set[str]:
    """Find common payload keys recursively, including inside metadata."""
    if isinstance(value, dict):
        found = set(value).intersection(FORBIDDEN_PAYLOAD_KEYS)
        for nested in value.values():
            found |= _forbidden_payload_keys(nested)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for nested in value:
            found |= _forbidden_payload_keys(nested)
        return found
    return set()


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_attempt(event: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one redacted route-attempt record.

    ``event_id`` must be immutable within the source.  ``request_ref`` can be
    a provider request id or a salted hash; callers should prefer a hash when
    the original value is customer-identifying.
    """
    missing = sorted(field for field in REQUIRED_FIELDS if not event.get(field))
    if missing:
        raise ValueError(f"route attempt missing required fields: {', '.join(missing)}")
    source = str(event["source"])
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported route telemetry source: {source}")
    outcome = str(event["outcome"])
    if outcome not in OUTCOMES:
        raise ValueError(f"unsupported route attempt outcome: {outcome}")
    present_forbidden = sorted(_forbidden_payload_keys(event))
    if present_forbidden:
        raise ValueError(
            "route telemetry must not contain prompt/completion payload fields: "
            + ", ".join(present_forbidden)
        )
    attempt_index = event.get("attempt_index", 0)
    try:
        attempt_index = int(attempt_index)
    except (TypeError, ValueError) as exc:
        raise ValueError("attempt_index must be an integer") from exc
    if attempt_index < 0:
        raise ValueError("attempt_index must be non-negative")
    return {
        "event_id": str(event["event_id"]),
        "observed_at": str(event["observed_at"]),
        "router": str(event["router"]),
        "source": source,
        "study_id": str(event["study_id"]),
        "request_ref": event.get("request_ref"),
        "model_id": str(event["model_id"]),
        "requested_provider": event.get("requested_provider"),
        "selected_provider": event.get("selected_provider"),
        "attempt_index": attempt_index,
        "outcome": outcome,
        "retry_reason": event.get("retry_reason"),
        "fallback_triggered": bool(event.get("fallback_triggered", False)),
        "policy": event.get("policy"),
        "quote_snapshot_id": event.get("quote_snapshot_id"),
        "input_tokens": _number(event.get("input_tokens")),
        "output_tokens": _number(event.get("output_tokens")),
        "cost_usd": _number(event.get("cost_usd")),
        "latency_ms": _number(event.get("latency_ms")),
        "metadata_json": json.dumps(
            event.get("metadata") or {}, separators=(",", ":"), sort_keys=True
        ),
        "payload_retained": False,
    }


def write_attempts(
    events: list[dict[str, Any]],
    *,
    run_ts: str | None = None,
    dt: str | None = None,
    curated_dir: Path = CURATED_DIR,
) -> Path | None:
    """Write a batch of redacted owned-route attempts at an immutable run id."""
    if not events:
        return None
    run_ts, dt = run_ts or run_timestamp(), dt or dt_partition()
    rows = [validate_attempt(event) | {"run_ts": run_ts, "dt": dt} for event in events]
    ids = [row["source"] + "|" + row["event_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source/event_id route attempts in one batch")
    return write_partition(
        pa.Table.from_pylist(rows), "router_route_attempts", run_ts, dt, curated_dir
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a redacted JSONL export; reject non-object rows before persistence."""
    events = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"route telemetry row at {path}:{line_number} is not an object")
        events.append(item)
    return events
