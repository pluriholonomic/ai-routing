"""Outcome-free price-event detection and deterministic paid-wave planning."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pyarrow as pa

from .price_experiments import EVENT_STUDY_ID, provider_key, sha256_json

EVENT_PLAN_VERSION = "price-event-plan-v1"
WAVES = {
    "w0": (0, 10),
    "w1": (15, 10),
    "w2": (60, 20),
    "w3": (360, 45),
    "w4": (1_440, 120),
}

PRICE_EVENT_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("detected_at", pa.string()),
        ("model_id", pa.string()),
        ("provider_name", pa.string()),
        ("endpoint_tag", pa.string()),
        ("event_type", pa.string()),
        ("old_prompt_price", pa.float64()),
        ("new_prompt_price", pa.float64()),
        ("old_completion_price", pa.float64()),
        ("new_completion_price", pa.float64()),
        ("old_quote_index", pa.float64()),
        ("new_quote_index", pa.float64()),
        ("relative_change", pa.float64()),
        ("old_rank", pa.int32()),
        ("new_rank", pa.int32()),
        ("source_healthy", pa.bool_()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

PRICE_EVENT_WAVE_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("wave_id", pa.string()),
        ("task_id", pa.string()),
        ("target_at", pa.string()),
        ("latest_at", pa.string()),
        ("arm", pa.string()),
        ("model_id", pa.string()),
        ("moving_provider", pa.string()),
        ("assignment_seed", pa.string()),
        ("event_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def _time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote(row: Mapping[str, Any]) -> float | None:
    prompt = _number(row.get("prompt_price_per_token"))
    completion = _number(row.get("completion_price_per_token"))
    if prompt is None or completion is None or min(prompt, completion) <= 0:
        return None
    return (prompt + completion) / 2.0


def _keys(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    output = {}
    for raw in rows:
        row = dict(raw)
        key = (
            str(row.get("model_id") or ""),
            provider_key(row.get("provider_name")),
            str(row.get("endpoint_tag") or ""),
        )
        if all(key) and _quote(row) is not None:
            output[key] = row
    return output


def _ranks(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], int]:
    by_model: dict[str, list[tuple[tuple[str, str, str], float]]] = {}
    for key, row in _keys(rows).items():
        by_model.setdefault(key[0], []).append((key, float(_quote(row))))
    ranks = {}
    for values in by_model.values():
        for rank, (key, _) in enumerate(sorted(values, key=lambda item: item[1]), start=1):
            ranks[key] = rank
    return ranks


def detect_price_events(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
    *,
    detected_at: str,
    minimum_relative_change: float = 0.05,
    source_healthy: bool = True,
) -> list[dict[str, Any]]:
    """Detect price moves and rank crossings without consulting paid outcomes."""
    if minimum_relative_change <= 0:
        raise ValueError("minimum_relative_change must be positive")
    if not source_healthy:
        return []
    old, new = _keys(previous), _keys(current)
    old_ranks, new_ranks = _ranks(previous), _ranks(current)
    rows = []
    for key in sorted(old.keys() & new.keys()):
        old_quote, new_quote = float(_quote(old[key])), float(_quote(new[key]))
        relative = new_quote / old_quote - 1.0
        crossed = old_ranks.get(key) != new_ranks.get(key)
        if abs(relative) < minimum_relative_change and not crossed:
            continue
        event_type = "price_cut" if relative <= -minimum_relative_change else "price_raise"
        if abs(relative) < minimum_relative_change:
            event_type = "rank_crossing"
        identity = {
            "detected_at": detected_at,
            "model_id": key[0],
            "provider_key": key[1],
            "endpoint_tag": key[2],
            "old_quote": old_quote,
            "new_quote": new_quote,
        }
        event_id = "pev-" + hashlib.sha256(sha256_json(identity).encode()).hexdigest()[:20]
        rows.append(
            {
                "event_id": event_id,
                "study_id": EVENT_STUDY_ID,
                "plan_version": EVENT_PLAN_VERSION,
                "detected_at": detected_at,
                "model_id": key[0],
                "provider_name": new[key].get("provider_name"),
                "endpoint_tag": key[2],
                "event_type": event_type,
                "old_prompt_price": _number(old[key].get("prompt_price_per_token")),
                "new_prompt_price": _number(new[key].get("prompt_price_per_token")),
                "old_completion_price": _number(
                    old[key].get("completion_price_per_token")
                ),
                "new_completion_price": _number(
                    new[key].get("completion_price_per_token")
                ),
                "old_quote_index": old_quote,
                "new_quote_index": new_quote,
                "relative_change": relative,
                "old_rank": old_ranks.get(key),
                "new_rank": new_ranks.get(key),
                "source_healthy": True,
                "payload_retained": False,
            }
        )
    return rows


def build_wave_plan(event: Mapping[str, Any], *, seed: int) -> list[dict[str, Any]]:
    """Freeze all target times and arms for one event before any paid outcome."""
    event_id = str(event.get("event_id") or "")
    if not event_id:
        raise ValueError("event_id is required")
    detected = _time(event["detected_at"])
    rng = random.Random(f"{seed}|{event_id}")
    event_hash = sha256_json(dict(event))
    rows = []
    for wave_id, (offset_minutes, tolerated_minutes) in WAVES.items():
        arms = ["default_fresh"] * 4 + ["sort_price"] + ["moving_provider_pin"]
        rng.shuffle(arms)
        target = detected + timedelta(minutes=offset_minutes)
        latest = target + timedelta(minutes=tolerated_minutes)
        for index, arm in enumerate(arms):
            rows.append(
                {
                    "event_id": event_id,
                    "study_id": EVENT_STUDY_ID,
                    "plan_version": EVENT_PLAN_VERSION,
                    "wave_id": wave_id,
                    "task_id": f"{event_id}|{wave_id}|{index}|{arm}",
                    "target_at": target.isoformat().replace("+00:00", "Z"),
                    "latest_at": latest.isoformat().replace("+00:00", "Z"),
                    "arm": arm,
                    "model_id": str(event.get("model_id") or ""),
                    "moving_provider": str(event.get("provider_name") or ""),
                    "assignment_seed": str(seed),
                    "event_sha256": event_hash,
                    "payload_retained": False,
                }
            )
    return rows


def wave_status(row: Mapping[str, Any], *, now: datetime | None = None) -> str:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if now < _time(row["target_at"]):
        return "pending"
    if now <= _time(row["latest_at"]):
        return "due"
    return "missed"
