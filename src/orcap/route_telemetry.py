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
    "huggingface_inference_providers",
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
    "api_key",
    "authorization",
    "secret",
    "token",
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
        "reliability_audit_assignment_id": event.get("reliability_audit_assignment_id"),
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


def _value(record: dict[str, Any], *paths: str) -> Any:
    """Return the first non-empty dotted path from a redacted export row."""
    for path in paths:
        current: Any = record
        for key in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if current is not None and current != "":
            return current
    return None


def _source_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Keep a small, explicit allow-list of non-payload observability fields."""
    fields = {
        "scenario",
        "status_code",
        "cache_status",
        "deployment",
        "gateway",
        "region",
        "trace_id",
        "request_type",
    }
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    result = {key: metadata[key] for key in fields if key in metadata}
    for key in fields - {"scenario"}:
        if key in record:
            result[key] = record[key]
    return result


def _outcome(record: dict[str, Any]) -> str:
    raw = str(_value(record, "outcome", "status", "result") or "").lower()
    if raw in OUTCOMES:
        return raw
    status_code = _number(_value(record, "status_code", "response_status"))
    if status_code is not None:
        return "succeeded" if 200 <= status_code < 400 else "failed"
    return "failed" if record.get("error") else "unknown"


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _native_event(
    record: dict[str, Any],
    *,
    source: str,
    study_id: str,
    router: str,
) -> dict[str, Any]:
    """Map a *redacted* source export into the canonical owned-attempt contract.

    The aliases cover common OpenRouter generation and gateway export labels.
    Source exports which retain messages, response bodies, credentials, or raw
    request/response objects are rejected before any record is persisted.
    """
    forbidden = sorted(_forbidden_payload_keys(record))
    if forbidden:
        raise ValueError(
            "native route export must be redacted before import; found: " + ", ".join(forbidden)
        )
    event_id = _value(record, "event_id", "id", "generation_id", "request_id", "trace_id")
    observed_at = _value(record, "observed_at", "created_at", "timestamp", "time")
    model_id = _value(record, "model_id", "model", "request.model", "model_name")
    selected_provider = _value(
        record,
        "selected_provider",
        "provider_name",
        "provider.name",
        "provider",
        "upstream_provider",
    )
    requested_provider = _value(record, "requested_provider", "requested_provider_name")
    return {
        "event_id": event_id,
        "observed_at": observed_at,
        "router": router,
        "source": source,
        "study_id": study_id,
        "request_ref": _value(record, "request_ref", "request_hash", "request_id"),
        "model_id": model_id,
        "requested_provider": requested_provider,
        "selected_provider": selected_provider,
        "attempt_index": _value(record, "attempt_index", "retry_index") or 0,
        "outcome": _outcome(record),
        "retry_reason": _value(record, "retry_reason", "fallback_reason", "error_type"),
        "fallback_triggered": _boolean(
            _value(record, "fallback_triggered", "is_fallback", "fallback") or False
        ),
        "policy": _value(record, "policy", "routing_policy"),
        "quote_snapshot_id": _value(record, "quote_snapshot_id", "pricing_snapshot_id"),
        "reliability_audit_assignment_id": _value(
            record, "reliability_audit_assignment_id", "audit_assignment_id"
        ),
        "input_tokens": _value(record, "input_tokens", "usage.prompt_tokens"),
        "output_tokens": _value(record, "output_tokens", "usage.completion_tokens"),
        "cost_usd": _value(record, "cost_usd", "total_cost", "usage.cost"),
        "latency_ms": _value(record, "latency_ms", "latency", "duration_ms", "response_time_ms"),
        "metadata": _source_metadata(record),
    }


def normalize_export(
    events: list[dict[str, Any]],
    *,
    export_format: str,
    study_id: str | None = None,
    router: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize canonical or redacted native router logs before validation.

    ``canonical`` requires records already conforming to :func:`validate_attempt`.
    The source-specific formats deliberately accept only a narrow, redacted
    common subset.  They are adapters, not raw-log archivers.
    """
    if export_format == "canonical":
        return events
    formats = {
        "openrouter-generation": ("openrouter_generation", "openrouter"),
        "huggingface-inference-providers": (
            "huggingface_inference_providers",
            "huggingface_inference_providers",
        ),
        "cloudflare-ai-gateway": ("cloudflare_ai_gateway", "cloudflare_ai_gateway"),
        "portkey": ("portkey", "portkey"),
        "litellm": ("litellm", "litellm"),
    }
    if export_format not in formats:
        raise ValueError(f"unsupported route export format: {export_format}")
    if not study_id:
        raise ValueError("--study-id is required for non-canonical route exports")
    source, default_router = formats[export_format]
    return [
        _native_event(
            record,
            source=source,
            study_id=study_id,
            router=router or default_router,
        )
        for record in events
    ]
