"""Plan-first, budget-bounded OpenRouter price-response experiments.

The ``plan`` command uses only public endpoint menus and uploads a complete,
hashed assignment artifact. The ``execute`` command consumes that exact
artifact; it never regenerates assignments and refuses to run unless the paid
feature flag, campaign window, dedicated key, manifest, and spend limits pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from .capture_api import write_partition
from .capture_probes import CHAT_URL, GENERATION_URL
from .capture_route_calibration import (
    MODELS,
    REQUEST_TIMEOUT_SECONDS,
    SHAPES,
    RequestShape,
    _candidate_rows,
    _request_tools,
    _shape_prompt,
)
from .config import API_V1, CURATED_DIR, dt_partition, run_timestamp
from .price_experiments import (
    PAID_SPEND_LEDGER_SCHEMA,
    PLAN_VERSION,
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
    STUDY_ID,
    BudgetLimits,
    build_response_assignments,
    campaign_open,
    check_budget,
    plan_manifest,
    validate_manifest,
)
from .route_telemetry import write_attempts

DEFAULT_LIMITS = BudgetLimits(per_run_usd=1.0, per_day_usd=25.0, campaign_usd=300.0)
DEFAULT_MAX_TASKS = 48
GENERATION_POLL_ATTEMPTS = 5
GENERATION_POLL_SECONDS = 1.5


def _headers() -> dict[str, str]:
    key = os.environ.get("OPENROUTER_PRICE_EXPERIMENT_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_PRICE_EXPERIMENT_KEY is required for paid execution")
    return {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://github.com/pluriholonomic/ai-routing",
        "X-Title": "orcap price-response experiment",
    }


def _raw_endpoints(client: httpx.Client, model_id: str) -> list[dict[str, Any]]:
    response = client.get(f"{API_V1}/models/{model_id}/endpoints")
    response.raise_for_status()
    return list((response.json().get("data") or {}).get("endpoints") or [])


def _selected_models() -> tuple[str, ...]:
    configured = [item.strip() for item in os.environ.get("ORCAP_PRICE_MODELS", "").split(",")]
    selected = tuple(item for item in configured if item)
    return selected or MODELS[:3]


def _selected_shapes() -> tuple[RequestShape, ...]:
    configured = {
        item.strip()
        for item in os.environ.get("ORCAP_PRICE_SHAPES", "short_chat").split(",")
        if item.strip()
    }
    selected = tuple(shape for shape in SHAPES if shape.shape_id in configured)
    if not selected:
        raise ValueError("ORCAP_PRICE_SHAPES selected no known request shape")
    return selected


def freeze_candidates(
    client: httpx.Client,
    *,
    run_id: str,
    seed: int,
    models: tuple[str, ...],
    shapes: tuple[RequestShape, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Freeze public menus while retaining explicit source failures."""
    rows: list[dict[str, Any]] = []
    failures = []
    for model_id in models:
        try:
            raw = _raw_endpoints(client, model_id)
        except httpx.HTTPError as exc:
            failures.append({"model_id": model_id, "reason": type(exc).__name__})
            continue
        for shape in shapes:
            prepared, _ = _candidate_rows(
                raw,
                run_id=run_id,
                run_seed=seed,
                model_id=model_id,
                shape=shape,
            )
            block_id = f"{STUDY_ID}|{run_id}|{model_id}|{shape.shape_id}"
            for row in prepared:
                row.update(
                    {
                        "study_id": STUDY_ID,
                        "plan_version": PLAN_VERSION,
                        "block_id": block_id,
                        "conservative_input_tokens": shape.conservative_input_tokens,
                        "max_output_tokens": shape.max_output_tokens,
                        "payload_retained": False,
                    }
                )
            rows.extend(prepared)
    return rows, failures


def _materialize(
    rows: list[dict[str, Any]], schema: pa.Schema, *, run_id: str, dt: str
) -> pa.Table:
    return pa.Table.from_pylist(
        [row | {"run_ts": run_id, "dt": dt} for row in rows], schema=schema
    )


def build_plan_bundle(
    client: httpx.Client,
    *,
    run_id: str,
    seed: int,
    max_tasks: int = DEFAULT_MAX_TASKS,
    models: tuple[str, ...] | None = None,
    shapes: tuple[RequestShape, ...] | None = None,
) -> dict[str, Any]:
    candidates, source_failures = freeze_candidates(
        client,
        run_id=run_id,
        seed=seed,
        models=models or _selected_models(),
        shapes=shapes or _selected_shapes(),
    )
    assignments, summary = build_response_assignments(
        candidates, run_id=run_id, seed=seed, max_tasks=max_tasks
    )
    summary = summary | {
        "source_failures": source_failures,
        "source_healthy": not source_failures,
        "preflight_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "claim_boundary": (
            "Owned requests only; no cross-user order flow, private router scores, "
            "or provider intent is observed."
        ),
    }
    manifest = plan_manifest(candidates, assignments, summary)
    return {
        "format": "orcap-price-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
        "manifest": manifest,
    }


def write_plan_bundle(
    bundle: dict[str, Any], *, bundle_path: Path, curated_dir: Path = CURATED_DIR
) -> dict[str, str]:
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    run_id = str(bundle["summary"]["run_id"])
    dt = dt_partition()
    candidate_path = write_partition(
        _materialize(
            bundle["candidates"], PRICE_RESPONSE_CANDIDATE_SCHEMA, run_id=run_id, dt=dt
        ),
        "price_response_candidates",
        run_id,
        dt,
        curated_dir,
    )
    persisted_assignments = [
        row
        | {
            "manifest_sha256": bundle["manifest"]["manifest_sha256"],
            "preflight_only": True,
        }
        for row in bundle["assignments"]
    ]
    assignment_path = write_partition(
        _materialize(
            persisted_assignments,
            PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
            run_id=run_id,
            dt=dt,
        ),
        "price_response_assignments",
        run_id,
        dt,
        curated_dir,
    )
    return {
        "bundle_path": str(bundle_path),
        "candidate_path": str(candidate_path),
        "assignment_path": str(assignment_path),
    }


def _spend_rows(data_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in data_root.glob("curated/paid_spend_ledger/dt=*/*.parquet"):
        try:
            rows.extend(pq.ParquetFile(path).read().to_pylist())
        except (OSError, pa.ArrowInvalid):
            continue
    return rows


def reconstruct_spend(
    rows: list[dict[str, Any]], *, now: datetime, study_id: str = STUDY_ID
) -> tuple[float, float]:
    unique = {}
    for row in rows:
        if str(row.get("study_id") or "") != study_id:
            continue
        task_id = str(row.get("task_id") or "")
        if not task_id:
            continue
        try:
            at = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
            cost = float(row.get("cost_usd") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        unique[task_id] = (at.astimezone(UTC), max(cost, 0.0))
    campaign = sum(cost for _, cost in unique.values())
    day_cutoff = now.astimezone(UTC) - timedelta(hours=24)
    day = sum(cost for at, cost in unique.values() if at >= day_cutoff)
    return day, campaign


def _shape(shape_id: str) -> RequestShape:
    for shape in SHAPES:
        if shape.shape_id == shape_id:
            return shape
    raise ValueError(f"unknown planned shape: {shape_id}")


def _session_id(assignment: dict[str, Any]) -> str:
    material = f"{assignment['assignment_seed']}|{assignment['session_group']}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def _fetch_generation(client: httpx.Client, generation_id: str) -> dict[str, Any] | None:
    for _ in range(GENERATION_POLL_ATTEMPTS):
        time.sleep(GENERATION_POLL_SECONDS)
        response = client.get(
            GENERATION_URL, params={"id": generation_id}, headers=_headers()
        )
        if response.status_code == 200:
            return response.json()
    return None


def _send_assignment(
    client: httpx.Client, assignment: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, int | None]:
    shape = _shape(str(assignment["shape_id"]))
    nonce = hashlib.sha256(str(assignment["task_id"]).encode()).hexdigest()[:20]
    tools, tool_choice = _request_tools(shape)
    provider: dict[str, Any] = {
        "allow_fallbacks": bool(assignment["allow_fallbacks"]),
        "max_price": {
            "prompt": float(assignment["max_price_prompt_per_mtok"]),
            "completion": float(assignment["max_price_completion_per_mtok"]),
        },
    }
    if assignment.get("provider_sort"):
        provider["sort"] = assignment["provider_sort"]
    if assignment.get("provider_order_tags"):
        provider["order"] = assignment["provider_order_tags"]
    if assignment.get("provider_only_tags"):
        provider["only"] = assignment["provider_only_tags"]
    if shape.required_parameters:
        provider["require_parameters"] = True
    body: dict[str, Any] = {
        "model": assignment["model_id"],
        "messages": [{"role": "user", "content": _shape_prompt(shape, nonce)}],
        # The immutable assignment owns the execution cap. Falling back to the
        # shape default is retained only for legacy plans that predate the
        # explicit field.
        "max_tokens": int(assignment.get("max_output_tokens") or shape.max_output_tokens),
        "temperature": 0,
        "usage": {"include": True},
        "session_id": _session_id(assignment),
        "provider": provider,
    }
    if tools is not None:
        body["tools"], body["tool_choice"] = tools, tool_choice
    try:
        response = client.post(CHAT_URL, headers=_headers(), json=body)
        if response.status_code != 200:
            return None, None, f"http_{response.status_code}", response.status_code
        completion = response.json()
        generation = (
            _fetch_generation(client, str(completion["id"]))
            if completion.get("id")
            else None
        )
        return completion, generation, None, response.status_code
    except httpx.HTTPError as exc:
        return None, None, type(exc).__name__, None


def _attempt(
    assignment: dict[str, Any],
    completion: dict[str, Any] | None,
    generation: dict[str, Any] | None,
    error: str | None,
    status: int | None,
    *,
    manifest_sha256: str,
    study_id: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    gen = (generation or {}).get("data") or {}
    usage = (completion or {}).get("usage") or {}
    selected = gen.get("provider_name") or (completion or {}).get("provider")
    return {
        "event_id": str((completion or {}).get("id") or assignment["task_id"]),
        "observed_at": observed_at or run_timestamp(),
        "router": "openrouter",
        "source": "openrouter_generation",
        "study_id": study_id,
        "request_ref": (completion or {}).get("id"),
        "model_id": assignment["model_id"],
        "requested_provider": assignment.get("requested_provider"),
        "selected_provider": selected,
        "attempt_index": 0,
        "outcome": "succeeded" if completion is not None and error is None else "failed",
        "retry_reason": error,
        "fallback_triggered": bool(
            assignment.get("requested_provider")
            and selected
            and str(assignment["requested_provider"]).casefold() != str(selected).casefold()
        ),
        "policy": assignment["policy"],
        "input_tokens": gen.get("native_tokens_prompt") or usage.get("prompt_tokens"),
        "output_tokens": gen.get("native_tokens_completion")
        or usage.get("completion_tokens"),
        "cost_usd": gen.get("total_cost") or usage.get("cost"),
        "latency_ms": gen.get("latency"),
        "metadata": {
            "scenario": assignment["shape_id"],
            "request_type": "price_response_probe",
            "status_code": status,
            "task_id": assignment["task_id"],
            "block_id": assignment["block_id"],
            "policy_order": assignment["policy_order"],
            "manifest_sha256": manifest_sha256,
            "protocol_sha256": assignment.get("protocol_sha256"),
            "event_id": assignment.get("event_id"),
            "wave_id": assignment.get("wave_id"),
            "max_price_prompt_per_mtok": assignment["max_price_prompt_per_mtok"],
            "max_price_completion_per_mtok": assignment[
                "max_price_completion_per_mtok"
            ],
        },
    }


def execute_bundle(
    bundle: dict[str, Any],
    *,
    curated_dir: Path = CURATED_DIR,
    data_root: Path | None = None,
    now: datetime | None = None,
    send: Any = _send_assignment,
) -> dict[str, Any]:
    """Validate and execute exactly one uploaded plan; injectable for tests."""
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    assignments = list(bundle["assignments"])
    study_id = str(bundle["summary"].get("study_id") or STUDY_ID)
    task_ids = [str(row["task_id"]) for row in assignments]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeError("duplicate task ids in uploaded plan")
    if not bool(bundle["summary"].get("source_healthy")):
        raise RuntimeError("source-health gate failed; refusing paid execution")
    if os.environ.get("ORCAP_PAID_PRICE_STUDIES_ENABLED", "").lower() != "true":
        raise RuntimeError("paid price studies are disabled")
    if not os.environ.get("OPENROUTER_PRICE_EXPERIMENT_KEY"):
        raise RuntimeError("dedicated paid experiment key is unavailable")
    start = os.environ.get("ORCAP_PRICE_CAMPAIGN_START_UTC")
    end = os.environ.get("ORCAP_PRICE_CAMPAIGN_END_UTC")
    if not start or not end or not campaign_open(start, end, now):
        raise RuntimeError("paid execution refused outside the configured campaign")
    now = (now or datetime.now(UTC)).astimezone(UTC)
    limits = BudgetLimits(
        float(os.environ.get("ORCAP_PRICE_MAX_RUN_USD", DEFAULT_LIMITS.per_run_usd)),
        float(os.environ.get("ORCAP_PRICE_MAX_DAY_USD", DEFAULT_LIMITS.per_day_usd)),
        float(
            os.environ.get("ORCAP_PRICE_MAX_CAMPAIGN_USD", DEFAULT_LIMITS.campaign_usd)
        ),
    )
    historical_spend = _spend_rows(data_root or curated_dir.parent)
    existing_tasks = {
        str(row.get("task_id") or "")
        for row in historical_spend
        if str(row.get("study_id") or "") == study_id
    }
    overlap = sorted(set(task_ids) & existing_tasks)
    if overlap:
        raise RuntimeError(
            f"refusing to re-execute {len(overlap)} task(s) already present in spend ledger"
        )
    day, campaign = reconstruct_spend(historical_spend, now=now, study_id=study_id)
    planned = float(bundle["summary"]["planned_quote_cap_usd"])
    check_budget(
        planned_usd=planned,
        spent_day_usd=day,
        spent_campaign_usd=campaign,
        limits=limits,
    )
    attempts = []
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for assignment in assignments:
            completion, generation, error, status = send(client, assignment)
            attempts.append(
                _attempt(
                    assignment,
                    completion,
                    generation,
                    error,
                    status,
                    manifest_sha256=bundle["manifest"]["manifest_sha256"],
                    study_id=study_id,
                )
            )
    run_id = str(bundle["summary"]["run_id"])
    dt = dt_partition(now)
    attempts_path = write_attempts(
        attempts, run_ts=run_id, dt=dt, curated_dir=curated_dir
    )
    ledger_rows = [
        {
            "study_id": study_id,
            "run_id": run_id,
            "task_id": assignment["task_id"],
            "observed_at": attempt["observed_at"],
            "cost_usd": float(attempt.get("cost_usd") or 0.0),
            "attempted": True,
            "manifest_sha256": bundle["manifest"]["manifest_sha256"],
            "payload_retained": False,
        }
        for assignment, attempt in zip(assignments, attempts, strict=True)
    ]
    ledger_path = write_partition(
        _materialize(ledger_rows, PAID_SPEND_LEDGER_SCHEMA, run_id=run_id, dt=dt),
        "paid_spend_ledger",
        run_id,
        dt,
        curated_dir,
    )
    return {
        "study_id": study_id,
        "run_id": run_id,
        "manifest_sha256": bundle["manifest"]["manifest_sha256"],
        "planned_requests": len(assignments),
        "attempted_requests": len(attempts),
        "realized_cost_usd": sum(float(row.get("cost_usd") or 0.0) for row in attempts),
        "attempts_path": str(attempts_path) if attempts_path else None,
        "ledger_path": str(ledger_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--bundle", type=Path, default=Path("price-plan.json"))
    plan.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    plan.add_argument("--max-tasks", type=int, default=DEFAULT_MAX_TASKS)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    validate = subparsers.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_PRICE_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_PRICE_RANDOMIZATION_SEED", secrets.randbits(64)))
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_plan_bundle(
                client, run_id=run_id, seed=seed, max_tasks=args.max_tasks
            )
        paths = write_plan_bundle(
            bundle, bundle_path=args.bundle, curated_dir=args.curated_dir
        )
        print(json.dumps(bundle["summary"] | bundle["manifest"] | paths, indent=2))
    elif args.command == "execute":
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        print(
            json.dumps(
                execute_bundle(
                    bundle,
                    curated_dir=args.curated_dir,
                    data_root=args.curated_dir.parent,
                ),
                indent=2,
            )
        )
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_manifest(
            bundle["manifest"],
            bundle["candidates"],
            bundle["assignments"],
            bundle["summary"],
        )
        if not bundle["summary"].get("source_healthy"):
            raise RuntimeError("public candidate source failed health validation")
        if args.require_tasks and not bundle["assignments"]:
            raise RuntimeError("validated plan contains no executable assignments")
        print(
            json.dumps(
                {
                    "manifest_sha256": bundle["manifest"]["manifest_sha256"],
                    "source_healthy": True,
                    "planned_tasks": len(bundle["assignments"]),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
