"""H96 paid calibration of OpenRouter's public shadow-routing model.

The campaign sends a small, preregistered panel of owned requests under four
request shapes.  It contrasts budget-bounded default routing, explicit price
sorting, exact endpoint pins, and a deliberately repeated session.  Prompts,
completions, API keys, and raw session ids are never persisted.

H96 is separate from the frozen H81 release and the running H95 replication.
Its finite campaign window and per-run spend cap are enforced in this module,
not only in the GitHub Actions workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from .capture_api import write_partition
from .capture_probes import CHAT_URL, GENERATION_URL, _headers
from .config import API_V1, CURATED_DIR, dt_partition, run_timestamp
from .route_telemetry import write_attempts

log = logging.getLogger(__name__)

STUDY_ID = "openrouter-route-calibration-v1"
CAMPAIGN_ID = "h96-2026-07-19-two-day-pilot"
CAMPAIGN_START_UTC = "2026-07-19T01:00:00Z"
CAMPAIGN_END_UTC = "2026-07-21T01:00:00Z"
DEFAULT_MAX_RUN_USD = 0.35
DEFAULT_MAX_CAMPAIGN_USD = 4.20
REQUEST_TIMEOUT_SECONDS = 90.0
GENERATION_POLL_ATTEMPTS = 3
GENERATION_POLL_SECONDS = 1.5

MODELS = (
    "deepseek/deepseek-v4-pro",
    "stepfun/step-3.7-flash",
    "xiaomi/mimo-v2.5-pro",
    "openai/gpt-oss-120b",
    "deepseek/deepseek-v3.2",
    "google/gemma-4-31b-it",
)


@dataclass(frozen=True)
class RequestShape:
    shape_id: str
    nominal_input_tokens: int
    conservative_input_tokens: int
    max_output_tokens: int
    required_parameters: tuple[str, ...] = ()


SHAPES = (
    RequestShape("short_chat", 64, 96, 8),
    RequestShape("input_heavy", 2_048, 3_072, 16),
    RequestShape("output_heavy", 128, 192, 128),
    RequestShape("tool_call", 256, 512, 32, ("tools", "tool_choice")),
)

POLICY_COUNTS = {
    "default_budgeted_iid": 3,
    "sort_price": 1,
    "pinned_cheapest": 1,
    "pinned_second": 1,
    "default_sticky_seed": 1,
    "default_sticky_repeat": 1,
}

CALIBRATION_CANDIDATE_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("observed_at", pa.string()),
        ("study_id", pa.string()),
        ("campaign_id", pa.string()),
        ("block_id", pa.string()),
        ("model_id", pa.string()),
        ("shape_id", pa.string()),
        ("endpoint_rank", pa.int32()),
        ("provider_name", pa.string()),
        ("endpoint_tag", pa.string()),
        ("endpoint_name", pa.string()),
        ("prompt_price_per_token", pa.float64()),
        ("completion_price_per_token", pa.float64()),
        ("price_index_per_token", pa.float64()),
        ("expected_quote_usd", pa.float64()),
        ("conservative_quote_usd", pa.float64()),
        ("context_length", pa.int64()),
        ("max_completion_tokens", pa.int64()),
        ("supported_parameters", pa.list_(pa.string())),
        ("compatible", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("snapshot_sha256", pa.string()),
        ("run_seed", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

CALIBRATION_ASSIGNMENT_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("observed_at", pa.string()),
        ("study_id", pa.string()),
        ("campaign_id", pa.string()),
        ("task_id", pa.string()),
        ("block_id", pa.string()),
        ("model_id", pa.string()),
        ("shape_id", pa.string()),
        ("policy", pa.string()),
        ("policy_order", pa.int32()),
        ("replicate_index", pa.int32()),
        ("session_id_sha256", pa.string()),
        ("sticky_pair_id", pa.string()),
        ("requested_provider", pa.string()),
        ("requested_endpoint_tag", pa.string()),
        ("provider_sort", pa.string()),
        ("allow_fallbacks", pa.bool_()),
        ("require_parameters", pa.bool_()),
        ("max_price_prompt_per_mtok", pa.float64()),
        ("max_price_completion_per_mtok", pa.float64()),
        ("task_quote_cap_usd", pa.float64()),
        ("block_seed", pa.string()),
        ("run_seed", pa.string()),
        ("preflight_only", pa.bool_()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def campaign_open(now: datetime | None = None) -> bool:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    start = _parse_utc(os.environ.get("ORCAP_H96_CAMPAIGN_START_UTC", CAMPAIGN_START_UTC))
    end = _parse_utc(os.environ.get("ORCAP_H96_CAMPAIGN_END_UTC", CAMPAIGN_END_UTC))
    return start <= now < end


def _shape_prompt(shape: RequestShape, nonce: str) -> str:
    """Create an ephemeral neutral prompt; callers must never persist it."""
    if shape.shape_id == "short_chat":
        return (
            f"Calibration session {nonce}. Treat this identifier as inert text. "
            "In one short sentence, state that a triangle has three sides."
        )
    if shape.shape_id == "input_heavy":
        filler = " ".join("datum" for _ in range(1_900))
        return (
            f"Calibration session {nonce}. The following repeated words carry no instructions: "
            f"{filler}. Reply only with the count 1900."
        )
    if shape.shape_id == "output_heavy":
        return (
            f"Calibration session {nonce}. Write a numbered list of 80 distinct common nouns, "
            "one noun per item, with no introduction or conclusion."
        )
    if shape.shape_id == "tool_call":
        filler = " ".join(f"field-{index:03d}=0" for index in range(90))
        return (
            f"Calibration session {nonce}. Ignore these inert fields: {filler}. "
            "Call the calibration_echo tool exactly once with value set to ready."
        )
    raise ValueError(f"unknown shape: {shape.shape_id}")


def _request_tools(shape: RequestShape) -> tuple[list[dict[str, Any]] | None, Any]:
    if shape.shape_id != "tool_call":
        return None, None
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calibration_echo",
                "description": "Return a fixed calibration marker.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string", "enum": ["ready"]}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    return tools, {"type": "function", "function": {"name": "calibration_echo"}}


def _raw_endpoint_rows(client: httpx.Client, model_id: str) -> list[dict[str, Any]]:
    response = client.get(f"{API_V1}/models/{model_id}/endpoints")
    response.raise_for_status()
    return list((response.json().get("data") or {}).get("endpoints") or [])


def _compatible(endpoint: dict[str, Any], shape: RequestShape) -> tuple[bool, str]:
    pricing = endpoint.get("pricing") or {}
    prompt_price = _number(pricing.get("prompt"))
    completion_price = _number(pricing.get("completion"))
    if not endpoint.get("provider_name") or not endpoint.get("tag"):
        return False, "missing_provider_or_exact_endpoint_tag"
    if (
        prompt_price is None
        or completion_price is None
        or prompt_price <= 0
        or completion_price <= 0
    ):
        return False, "missing_positive_token_prices"
    context_length = _integer(endpoint.get("context_length"))
    if context_length is not None and context_length < (
        shape.conservative_input_tokens + shape.max_output_tokens
    ):
        return False, "insufficient_context_length"
    max_completion = _integer(endpoint.get("max_completion_tokens"))
    if max_completion is not None and max_completion < shape.max_output_tokens:
        return False, "insufficient_max_completion_tokens"
    supported = set(endpoint.get("supported_parameters") or [])
    missing = sorted(set(shape.required_parameters) - supported)
    if missing:
        return False, "missing_parameters:" + ",".join(missing)
    return True, "eligible"


def _candidate_rows(
    raw_endpoints: list[dict[str, Any]],
    *,
    run_id: str,
    run_seed: int,
    model_id: str,
    shape: RequestShape,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    snapshot = json.dumps(raw_endpoints, separators=(",", ":"), sort_keys=True)
    snapshot_sha256 = _sha256(snapshot)
    observed_at = run_timestamp()
    prepared: list[dict[str, Any]] = []
    for endpoint in raw_endpoints:
        pricing = endpoint.get("pricing") or {}
        prompt_price = _number(pricing.get("prompt"))
        completion_price = _number(pricing.get("completion"))
        ok, reason = _compatible(endpoint, shape)
        expected = conservative = None
        if prompt_price is not None and completion_price is not None:
            expected = (
                prompt_price * shape.nominal_input_tokens
                + completion_price * shape.max_output_tokens
            )
            conservative = (
                prompt_price * shape.conservative_input_tokens
                + completion_price * shape.max_output_tokens
            )
        prepared.append(
            {
                "run_id": run_id,
                "observed_at": observed_at,
                "study_id": STUDY_ID,
                "campaign_id": CAMPAIGN_ID,
                "block_id": f"{STUDY_ID}|{run_id}|{model_id}|{shape.shape_id}",
                "model_id": model_id,
                "shape_id": shape.shape_id,
                "provider_name": endpoint.get("provider_name"),
                "endpoint_tag": endpoint.get("tag"),
                "endpoint_name": endpoint.get("name"),
                "prompt_price_per_token": prompt_price,
                "completion_price_per_token": completion_price,
                "price_index_per_token": (
                    (prompt_price + completion_price) / 2.0
                    if prompt_price is not None and completion_price is not None
                    else None
                ),
                "expected_quote_usd": expected,
                "conservative_quote_usd": conservative,
                "context_length": _integer(endpoint.get("context_length")),
                "max_completion_tokens": _integer(endpoint.get("max_completion_tokens")),
                "supported_parameters": sorted(endpoint.get("supported_parameters") or []),
                "compatible": ok,
                "exclusion_reason": reason,
                "snapshot_sha256": snapshot_sha256,
                "run_seed": str(run_seed),
            }
        )
    prepared.sort(
        key=lambda row: (
            row["expected_quote_usd"] if row["expected_quote_usd"] is not None else float("inf"),
            str(row["provider_name"] or ""),
            str(row["endpoint_tag"] or ""),
        )
    )
    for rank, row in enumerate(prepared, start=1):
        row["endpoint_rank"] = rank
    return prepared, [row for row in prepared if row["compatible"]]


def _distinct_provider_pins(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        provider = str(row["provider_name"])
        if provider.casefold() in seen:
            continue
        pins.append(row)
        seen.add(provider.casefold())
        if len(pins) == 2:
            break
    return pins


def _provider_cap(candidates: list[dict[str, Any]]) -> tuple[float, float]:
    cheapest = candidates[: min(3, len(candidates))]
    return (
        2.0 * max(float(row["prompt_price_per_token"]) for row in cheapest) * 1_000_000,
        2.0 * max(float(row["completion_price_per_token"]) for row in cheapest) * 1_000_000,
    )


def _ordered_policy_specs(
    pins: list[dict[str, Any]], rng: random.Random
) -> list[tuple[str, int, str, str | None, str | None]]:
    """Randomize eight positions while preserving sticky seed before repeat."""
    ordinary = [
        ("default_budgeted_iid", index, secrets.token_hex(16), None, None)
        for index in range(POLICY_COUNTS["default_budgeted_iid"])
    ]
    ordinary.extend(
        [
            ("sort_price", 0, secrets.token_hex(16), None, None),
            (
                "pinned_cheapest",
                0,
                secrets.token_hex(16),
                str(pins[0]["provider_name"]),
                str(pins[0]["endpoint_tag"]),
            ),
            (
                "pinned_second",
                0,
                secrets.token_hex(16),
                str(pins[1]["provider_name"]),
                str(pins[1]["endpoint_tag"]),
            ),
        ]
    )
    rng.shuffle(ordinary)
    sticky_session = secrets.token_hex(16)
    sticky_positions = sorted(rng.sample(range(8), 2))
    output: list[tuple[str, int, str, str | None, str | None]] = []
    ordinary_iter = iter(ordinary)
    for position in range(8):
        if position == sticky_positions[0]:
            output.append(("default_sticky_seed", 0, sticky_session, None, None))
        elif position == sticky_positions[1]:
            output.append(("default_sticky_repeat", 0, sticky_session, None, None))
        else:
            output.append(next(ordinary_iter))
    return output


def build_plan(
    client: httpx.Client,
    *,
    run_id: str,
    run_seed: int,
    preflight_only: bool,
    models: tuple[str, ...] = MODELS,
    shapes: tuple[RequestShape, ...] = SHAPES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Freeze public candidate snapshots and all assignments before outcomes."""
    rng = random.Random(run_seed)
    candidates_out: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    executable: list[dict[str, Any]] = []
    ineligible_blocks: list[dict[str, str]] = []
    raw_by_model: dict[str, list[dict[str, Any]]] = {}
    for model_id in models:
        try:
            raw_by_model[model_id] = _raw_endpoint_rows(client, model_id)
        except httpx.HTTPError as exc:
            log.warning("endpoint fetch failed for %s: %s", model_id, type(exc).__name__)
            raw_by_model[model_id] = []

    blocks = [(model_id, shape) for model_id in models for shape in shapes]
    rng.shuffle(blocks)
    for model_id, shape in blocks:
        block_seed = rng.getrandbits(64)
        candidate_rows, compatible = _candidate_rows(
            raw_by_model[model_id],
            run_id=run_id,
            run_seed=run_seed,
            model_id=model_id,
            shape=shape,
        )
        candidates_out.extend(candidate_rows)
        pins = _distinct_provider_pins(compatible)
        if len(pins) < 2:
            ineligible_blocks.append(
                {
                    "model_id": model_id,
                    "shape_id": shape.shape_id,
                    "reason": "fewer_than_two_distinct_compatible_providers",
                }
            )
            continue
        max_prompt, max_completion = _provider_cap(compatible)
        task_cap = (
            max_prompt / 1_000_000 * shape.conservative_input_tokens
            + max_completion / 1_000_000 * shape.max_output_tokens
        )
        block_id = f"{STUDY_ID}|{run_id}|{model_id}|{shape.shape_id}"
        sticky_pair_id = f"{block_id}|sticky"
        prompt_nonce_by_session: dict[str, str] = {}
        policy_specs = _ordered_policy_specs(pins, random.Random(block_seed))
        for position, (policy, replicate, session_id, provider, endpoint_tag) in enumerate(
            policy_specs
        ):
            prompt_nonce = prompt_nonce_by_session.setdefault(session_id, secrets.token_hex(12))
            task_id = f"{block_id}|{position}|{policy}|{replicate}"
            provider_control: dict[str, Any] = {
                "allow_fallbacks": not policy.startswith("pinned_"),
                "max_price": {"prompt": max_prompt, "completion": max_completion},
            }
            if policy == "sort_price":
                provider_control["sort"] = "price"
            if endpoint_tag is not None:
                provider_control.update(
                    {"order": [endpoint_tag], "only": [endpoint_tag], "allow_fallbacks": False}
                )
            if shape.required_parameters:
                provider_control["require_parameters"] = True
            assignment = {
                "run_id": run_id,
                "observed_at": run_timestamp(),
                "study_id": STUDY_ID,
                "campaign_id": CAMPAIGN_ID,
                "task_id": task_id,
                "block_id": block_id,
                "model_id": model_id,
                "shape_id": shape.shape_id,
                "policy": policy,
                "policy_order": position,
                "replicate_index": replicate,
                "session_id_sha256": _sha256(session_id),
                "sticky_pair_id": sticky_pair_id if policy.startswith("default_sticky_") else None,
                "requested_provider": provider,
                "requested_endpoint_tag": endpoint_tag,
                "provider_sort": "price" if policy == "sort_price" else None,
                "allow_fallbacks": bool(provider_control["allow_fallbacks"]),
                "require_parameters": bool(provider_control.get("require_parameters", False)),
                "max_price_prompt_per_mtok": max_prompt,
                "max_price_completion_per_mtok": max_completion,
                "task_quote_cap_usd": task_cap,
                "block_seed": str(block_seed),
                "run_seed": str(run_seed),
                "preflight_only": preflight_only,
            }
            assignments.append(assignment)
            executable.append(
                assignment
                | {
                    "session_id": session_id,
                    "prompt_nonce": prompt_nonce,
                    "provider_control": provider_control,
                    "shape": shape,
                }
            )

    planned_cap = sum(float(row["task_quote_cap_usd"]) for row in assignments)
    summary = {
        "study_id": STUDY_ID,
        "campaign_id": CAMPAIGN_ID,
        "run_id": run_id,
        "models_requested": len(models),
        "shapes_requested": len(shapes),
        "eligible_blocks": len({row["block_id"] for row in assignments}),
        "ineligible_blocks": ineligible_blocks,
        "candidate_rows": len(candidates_out),
        "planned_requests": len(assignments),
        "planned_quote_cap_usd": planned_cap,
        "maximum_campaign_stop_loss_usd": DEFAULT_MAX_CAMPAIGN_USD,
        "preflight_only": preflight_only,
        "campaign_open": campaign_open(),
        "claim_boundary": (
            "Owned request routing only. Default arms are bounded by a preregistered max-price "
            "menu; they do not observe other users, private router scores, or market-wide flow."
        ),
    }
    return candidates_out, assignments, executable, summary


def limit_plan_blocks(
    candidates: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    executable: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    max_blocks: int,
    selection_seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Keep complete randomized blocks under the remote execution-time budget.

    The original pilot attempted every eligible model-shape block in one
    sequential job.  A block-level shard preserves every within-block policy
    assignment, including the sticky-session ordering, while allowing each
    completed request to be checkpointed before the Actions timeout.
    """
    if max_blocks <= 0:
        raise ValueError("max_blocks must be positive")
    block_ids = sorted({str(row["block_id"]) for row in assignments})
    if len(block_ids) <= max_blocks:
        return (
            candidates,
            assignments,
            executable,
            summary
            | {
                "eligible_blocks_before_limit": len(block_ids),
                "execution_block_limit": max_blocks,
                "execution_block_offset": 0,
            },
        )
    offset = int(selection_seed) % len(block_ids)
    selected = [block_ids[(offset + index) % len(block_ids)] for index in range(max_blocks)]
    selected_set = set(selected)
    limited_candidates = [row for row in candidates if str(row["block_id"]) in selected_set]
    limited_assignments = [row for row in assignments if str(row["block_id"]) in selected_set]
    limited_executable = [row for row in executable if str(row["block_id"]) in selected_set]
    limited_summary = summary | {
        "eligible_blocks_before_limit": len(block_ids),
        "eligible_blocks": len(selected),
        "execution_block_limit": max_blocks,
        "execution_block_offset": offset,
        "selected_block_ids": selected,
        "candidate_rows": len(limited_candidates),
        "planned_requests": len(limited_assignments),
        "planned_quote_cap_usd": sum(
            float(row["task_quote_cap_usd"]) for row in limited_assignments
        ),
    }
    return limited_candidates, limited_assignments, limited_executable, limited_summary


def _fetch_generation(client: httpx.Client, generation_id: str) -> dict[str, Any] | None:
    for _ in range(GENERATION_POLL_ATTEMPTS):
        time.sleep(GENERATION_POLL_SECONDS)
        response = client.get(GENERATION_URL, params={"id": generation_id}, headers=_headers())
        if response.status_code == 200:
            return response.json()
    return None


def _send_task(
    client: httpx.Client, task: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, int | None]:
    shape: RequestShape = task["shape"]
    tools, tool_choice = _request_tools(shape)
    body: dict[str, Any] = {
        "model": task["model_id"],
        "messages": [{"role": "user", "content": _shape_prompt(shape, task["prompt_nonce"])}],
        "max_tokens": shape.max_output_tokens,
        "temperature": 0,
        "usage": {"include": True},
        "session_id": task["session_id"],
        "provider": task["provider_control"],
    }
    if tools is not None:
        body["tools"] = tools
        body["tool_choice"] = tool_choice
    completion = generation = None
    error = None
    status = None
    try:
        response = client.post(CHAT_URL, headers=_headers(), json=body)
        status = response.status_code
        if response.status_code == 200:
            completion = response.json()
            if completion.get("id"):
                generation = _fetch_generation(client, str(completion["id"]))
        else:
            error = f"http_{response.status_code}"
    except httpx.HTTPError as exc:
        error = type(exc).__name__
    return completion, generation, error, status


def _attempt_record(
    task: dict[str, Any],
    completion: dict[str, Any] | None,
    generation: dict[str, Any] | None,
    error: str | None,
    status: int | None,
) -> dict[str, Any]:
    gen = (generation or {}).get("data") or {}
    usage = (completion or {}).get("usage") or {}
    selected = gen.get("provider_name") or (completion or {}).get("provider")
    latency = gen.get("latency")
    event_id = (completion or {}).get("id") or task["task_id"]
    return {
        "event_id": str(event_id),
        "observed_at": run_timestamp(),
        "router": "openrouter",
        "source": "openrouter_generation",
        "study_id": STUDY_ID,
        "request_ref": (completion or {}).get("id"),
        "model_id": task["model_id"],
        "requested_provider": task["requested_provider"],
        "selected_provider": selected,
        "attempt_index": 0,
        "outcome": "succeeded" if completion is not None and error is None else "failed",
        "retry_reason": error,
        "fallback_triggered": bool(
            task["requested_provider"]
            and selected
            and str(task["requested_provider"]).casefold() != str(selected).casefold()
        ),
        "policy": task["policy"],
        "input_tokens": gen.get("native_tokens_prompt") or usage.get("prompt_tokens"),
        "output_tokens": gen.get("native_tokens_completion") or usage.get("completion_tokens"),
        "cost_usd": gen.get("total_cost") or usage.get("cost"),
        "latency_ms": latency,
        "metadata": {
            "scenario": task["shape_id"],
            "request_type": "route_calibration_probe",
            "status_code": status,
            "campaign_id": CAMPAIGN_ID,
            "task_id": task["task_id"],
            "block_id": task["block_id"],
            "policy_order": task["policy_order"],
            "replicate_index": task["replicate_index"],
            "session_id_sha256": task["session_id_sha256"],
            "sticky_pair_id": task["sticky_pair_id"],
            "requested_endpoint_tag": task["requested_endpoint_tag"],
            "provider_sort": task["provider_sort"],
            "allow_fallbacks": task["allow_fallbacks"],
            "require_parameters": task["require_parameters"],
            "max_price_prompt_per_mtok": task["max_price_prompt_per_mtok"],
            "max_price_completion_per_mtok": task["max_price_completion_per_mtok"],
            "task_quote_cap_usd": task["task_quote_cap_usd"],
        },
    }


def execute_plan(
    client: httpx.Client,
    tasks: list[dict[str, Any]],
    *,
    max_run_usd: float,
    jitter: bool = True,
    checkpoint: Callable[[list[dict[str, Any]]], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    planned = sum(float(task["task_quote_cap_usd"]) for task in tasks)
    if planned > max_run_usd:
        raise RuntimeError(
            f"planned H96 quote cap ${planned:.6f} exceeds per-run cap ${max_run_usd:.6f}"
        )
    attempts: list[dict[str, Any]] = []
    realized = 0.0
    stopped_before = None
    for task in tasks:
        task_cap = float(task["task_quote_cap_usd"])
        if realized + task_cap > max_run_usd:
            stopped_before = task["task_id"]
            break
        completion, generation, error, status = _send_task(client, task)
        attempt = _attempt_record(task, completion, generation, error, status)
        attempts.append(attempt)
        realized += float(attempt.get("cost_usd") or 0.0)
        if checkpoint is not None:
            checkpoint(list(attempts))
        if jitter:
            time.sleep(random.uniform(0.25, 0.75))
    return attempts, {
        "attempted_requests": len(attempts),
        "realized_cost_usd": realized,
        "stopped_before_task_id": stopped_before,
        "max_run_usd": max_run_usd,
    }


def _write_rows(
    rows: list[dict[str, Any]],
    schema: pa.Schema,
    table_name: str,
    *,
    run_id: str,
    curated_dir: Path,
) -> Path | None:
    if not rows:
        return None
    dt = dt_partition()
    materialized = [row | {"payload_retained": False, "run_ts": run_id, "dt": dt} for row in rows]
    return write_partition(
        pa.Table.from_pylist(materialized, schema=schema),
        table_name,
        run_id,
        dt,
        curated_dir,
    )


def run(
    *,
    preflight_only: bool,
    curated_dir: Path = CURATED_DIR,
    now: datetime | None = None,
) -> dict[str, Any]:
    run_id = run_timestamp(now)
    seed_text = os.environ.get("ORCAP_H96_RANDOMIZATION_SEED")
    run_seed = int(seed_text, 0) if seed_text else secrets.randbits(64)
    max_run_usd = float(os.environ.get("ORCAP_H96_MAX_RUN_USD", DEFAULT_MAX_RUN_USD))
    max_blocks_text = os.environ.get("ORCAP_H96_MAX_BLOCKS_PER_RUN")
    attempt_dt = dt_partition(now)
    attempts_path: Path | None = None

    def checkpoint(rows: list[dict[str, Any]]) -> None:
        nonlocal attempts_path
        attempts_path = write_attempts(rows, run_ts=run_id, dt=attempt_dt, curated_dir=curated_dir)

    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        candidates, assignments, tasks, summary = build_plan(
            client,
            run_id=run_id,
            run_seed=run_seed,
            preflight_only=preflight_only,
        )
        if max_blocks_text:
            candidates, assignments, tasks, summary = limit_plan_blocks(
                candidates,
                assignments,
                tasks,
                summary,
                max_blocks=int(max_blocks_text),
                selection_seed=run_seed,
            )
        candidates_path = _write_rows(
            candidates,
            CALIBRATION_CANDIDATE_SCHEMA,
            "router_calibration_candidates",
            run_id=run_id,
            curated_dir=curated_dir,
        )
        assignments_path = _write_rows(
            assignments,
            CALIBRATION_ASSIGNMENT_SCHEMA,
            "router_calibration_assignments",
            run_id=run_id,
            curated_dir=curated_dir,
        )
        if not preflight_only and not campaign_open(now):
            raise RuntimeError("paid H96 execution refused outside the frozen campaign window")
        if preflight_only:
            attempts: list[dict[str, Any]] = []
            execution = {
                "attempted_requests": 0,
                "realized_cost_usd": 0.0,
                "stopped_before_task_id": None,
                "max_run_usd": max_run_usd,
            }
        else:
            attempts, execution = execute_plan(
                client,
                tasks,
                max_run_usd=max_run_usd,
                jitter=True,
                checkpoint=checkpoint,
            )
    if attempts and attempts_path is None:
        checkpoint(attempts)
    return (
        summary
        | execution
        | {
            "candidates_path": str(candidates_path) if candidates_path else None,
            "assignments_path": str(assignments_path) if assignments_path else None,
            "attempts_path": str(attempts_path) if attempts_path else None,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="write frozen candidates and assignments without paid requests",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="run paid only inside the frozen window; otherwise exit successfully without I/O",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.scheduled and not campaign_open():
        print(
            json.dumps(
                {
                    "study_id": STUDY_ID,
                    "campaign_id": CAMPAIGN_ID,
                    "skipped": True,
                    "reason": "outside_frozen_campaign_window",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    result = run(preflight_only=args.preflight_only)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
