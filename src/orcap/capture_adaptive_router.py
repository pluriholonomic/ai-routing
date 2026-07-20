"""Plan-first paid execution for emulated adaptive monotone router policies."""

from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from .adaptive_router import (
    ADAPTIVE_ASSIGNMENT_SCHEMA,
    ADAPTIVE_CANDIDATE_SCHEMA,
    FIXED_HORIZON_BLOCKS,
    PLAN_VERSION,
    STUDY_ID,
    adaptive_manifest,
    build_adaptive_assignments,
)
from .capture_api import write_partition
from .capture_price_response import (
    _attempt,
    _materialize,
    _raw_endpoints,
    _send_assignment,
    _spend_rows,
    reconstruct_spend,
)
from .capture_route_calibration import (
    MODELS,
    REQUEST_TIMEOUT_SECONDS,
    SHAPES,
    RequestShape,
    _candidate_rows,
)
from .config import CURATED_DIR, dt_partition, run_timestamp
from .price_experiments import (
    PAID_SPEND_LEDGER_SCHEMA,
    BudgetLimits,
    campaign_open,
    check_budget,
    validate_manifest,
)
from .route_telemetry import validate_attempt

CAMPAIGN_START_UTC = "2026-07-21T00:00:00Z"
CAMPAIGN_END_UTC = "2026-08-04T03:00:00Z"
DEFAULT_MAX_BLOCKS = 3
DEFAULT_LIMITS = BudgetLimits(per_run_usd=0.75, per_day_usd=5.0, campaign_usd=40.0)


def _selected_models() -> tuple[str, ...]:
    configured = tuple(
        item.strip()
        for item in os.environ.get("ORCAP_ADAPTIVE_ROUTER_MODELS", "").split(",")
        if item.strip()
    )
    return configured or MODELS


def _selected_shapes() -> tuple[RequestShape, ...]:
    configured = {
        item.strip()
        for item in os.environ.get(
            "ORCAP_ADAPTIVE_ROUTER_SHAPES", "short_chat,output_heavy"
        ).split(",")
        if item.strip()
    }
    selected = tuple(shape for shape in SHAPES if shape.shape_id in configured)
    if not selected:
        raise ValueError("ORCAP_ADAPTIVE_ROUTER_SHAPES selected no known shape")
    return selected


def freeze_candidates(
    client: httpx.Client,
    *,
    run_id: str,
    seed: int,
    models: tuple[str, ...],
    shapes: tuple[RequestShape, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for model_id in models:
        try:
            raw = _raw_endpoints(client, model_id)
        except httpx.HTTPError as exc:
            failures.append({"model_id": model_id, "reason": type(exc).__name__})
            continue
        raw_by_tag = {str(item.get("tag") or ""): item for item in raw}
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
                source = raw_by_tag.get(str(row.get("endpoint_tag") or ""), {})
                uptime = source.get("uptime_last_30m")
                if row.get("compatible") and uptime is None:
                    row["compatible"] = False
                    row["exclusion_reason"] = "missing_public_uptime_30m"
                row.update(
                    {
                        "study_id": STUDY_ID,
                        "plan_version": PLAN_VERSION,
                        "block_id": block_id,
                        "public_uptime_30m": uptime,
                        "conservative_input_tokens": shape.conservative_input_tokens,
                        "max_output_tokens": shape.max_output_tokens,
                        "payload_retained": False,
                    }
                )
            rows.extend(prepared)
    return rows, failures


def _read_prior_blocks(data_root: Path, *, exclude_run_id: str | None = None) -> set[str]:
    """Return launched blocks, excluding assignment-only preflights."""
    blocks: set[str] = set()
    for path in data_root.glob("curated/adaptive_router_attempts/dt=*/*.parquet"):
        try:
            table = pq.ParquetFile(path).read(columns=["run_ts", "metadata_json"])
        except (OSError, pa.ArrowInvalid, KeyError):
            continue
        for row in table.to_pylist():
            if exclude_run_id and str(row.get("run_ts") or "") == exclude_run_id:
                continue
            try:
                metadata = json.loads(str(row.get("metadata_json") or "{}"))
            except json.JSONDecodeError:
                continue
            block = str(metadata.get("block_id") or "")
            if block:
                blocks.add(block)
    return blocks


def build_plan_bundle(
    client: httpx.Client,
    *,
    run_id: str,
    seed: int,
    data_root: Path,
    max_blocks: int = DEFAULT_MAX_BLOCKS,
    models: tuple[str, ...] | None = None,
    shapes: tuple[RequestShape, ...] | None = None,
) -> dict[str, Any]:
    prior_blocks = _read_prior_blocks(data_root, exclude_run_id=run_id)
    remaining = max(FIXED_HORIZON_BLOCKS - len(prior_blocks), 0)
    candidates, source_failures = freeze_candidates(
        client,
        run_id=run_id,
        seed=seed,
        models=models or _selected_models(),
        shapes=shapes or _selected_shapes(),
    )
    assignments, summary = build_adaptive_assignments(
        candidates,
        run_id=run_id,
        seed=seed,
        max_blocks=min(max_blocks, remaining) if remaining else 1,
    )
    if remaining == 0:
        assignments = []
        summary = summary | {
            "planned_blocks": 0,
            "planned_tasks": 0,
            "planned_quote_cap_usd": 0.0,
            "selected_block_scores": [],
        }
    source_healthy = not source_failures and (bool(assignments) or remaining == 0)
    summary = summary | {
        "source_failures": source_failures,
        "source_healthy": source_healthy,
        "prior_launched_blocks": len(prior_blocks),
        "remaining_blocks_before_plan": remaining,
        "horizon_reached": remaining == 0,
        "preflight_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "claim_boundary": (
            "Owned-request policy emulation with frozen public menus and exact provider "
            "propensities. It does not reveal OpenRouter's private scoring rule, provider "
            "costs or intent, cross-user flow, or a dynamic equilibrium response."
        ),
    }
    manifest = adaptive_manifest(candidates, assignments, summary)
    return {
        "format": "orcap-adaptive-monotone-plan-v1",
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
        _materialize(bundle["candidates"], ADAPTIVE_CANDIDATE_SCHEMA, run_id=run_id, dt=dt),
        "adaptive_router_candidates",
        run_id,
        dt,
        curated_dir,
    )
    assignments = [
        row
        | {
            "manifest_sha256": bundle["manifest"]["manifest_sha256"],
            "preflight_only": True,
        }
        for row in bundle["assignments"]
    ]
    assignment_path = write_partition(
        _materialize(assignments, ADAPTIVE_ASSIGNMENT_SCHEMA, run_id=run_id, dt=dt),
        "adaptive_router_assignments",
        run_id,
        dt,
        curated_dir,
    )
    return {
        "bundle_path": str(bundle_path),
        "candidate_path": str(candidate_path),
        "assignment_path": str(assignment_path),
    }


def _write_checkpoints(
    *,
    attempts: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    manifest_sha: str,
    run_id: str,
    dt: str,
    curated_dir: Path,
) -> tuple[Path, Path]:
    normalized = [validate_attempt(row) | {"run_ts": run_id, "dt": dt} for row in attempts]
    attempts_path = write_partition(
        pa.Table.from_pylist(normalized),
        "adaptive_router_attempts",
        run_id,
        dt,
        curated_dir,
    )
    ledger_rows = [
        {
            "study_id": STUDY_ID,
            "run_id": run_id,
            "task_id": assignment["task_id"],
            "observed_at": attempt["observed_at"],
            "cost_usd": float(attempt.get("cost_usd") or 0.0),
            "attempted": True,
            "manifest_sha256": manifest_sha,
            "payload_retained": False,
        }
        for assignment, attempt in zip(assignments[: len(attempts)], attempts, strict=True)
    ]
    ledger_path = write_partition(
        _materialize(ledger_rows, PAID_SPEND_LEDGER_SCHEMA, run_id=run_id, dt=dt),
        "paid_spend_ledger",
        run_id,
        dt,
        curated_dir,
    )
    return attempts_path, ledger_path


def execute_bundle(
    bundle: dict[str, Any],
    *,
    curated_dir: Path = CURATED_DIR,
    data_root: Path | None = None,
    now: datetime | None = None,
    send: Any = _send_assignment,
) -> dict[str, Any]:
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    assignments = sorted(bundle["assignments"], key=lambda row: int(row["policy_order"]))
    if not assignments:
        raise RuntimeError("validated adaptive-router plan contains no executable assignments")
    if not bool(bundle["summary"].get("source_healthy")):
        raise RuntimeError("source-health gate failed; refusing paid execution")
    if os.environ.get("ORCAP_PAID_PRICE_STUDIES_ENABLED", "").lower() != "true":
        raise RuntimeError("paid price studies are disabled")
    if os.environ.get("ORCAP_ADAPTIVE_ROUTER_ENABLED", "").lower() != "true":
        raise RuntimeError("adaptive router experiment is disabled")
    if not os.environ.get("OPENROUTER_PRICE_EXPERIMENT_KEY"):
        raise RuntimeError("dedicated paid experiment key is unavailable")
    start = os.environ.get("ORCAP_ADAPTIVE_ROUTER_START_UTC", CAMPAIGN_START_UTC)
    end = os.environ.get("ORCAP_ADAPTIVE_ROUTER_END_UTC", CAMPAIGN_END_UTC)
    if not campaign_open(start, end, now):
        raise RuntimeError("paid execution refused outside the configured campaign")

    now = (now or datetime.now(UTC)).astimezone(UTC)
    root = data_root or curated_dir.parent
    run_id = str(bundle["summary"]["run_id"])
    prior_blocks = _read_prior_blocks(root, exclude_run_id=run_id)
    planned_blocks = {str(row["block_id"]) for row in assignments}
    if len(prior_blocks | planned_blocks) > FIXED_HORIZON_BLOCKS:
        raise RuntimeError("plan would exceed the preregistered fixed block horizon")
    task_ids = [str(row["task_id"]) for row in assignments]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeError("duplicate task ids in adaptive-router plan")
    historical = _spend_rows(root)
    existing = {
        str(row.get("task_id") or "")
        for row in historical
        if str(row.get("study_id") or "") == STUDY_ID
    }
    overlap = sorted(set(task_ids) & existing)
    if overlap:
        raise RuntimeError(f"refusing to re-execute {len(overlap)} task(s)")
    limits = BudgetLimits(
        float(os.environ.get("ORCAP_ADAPTIVE_ROUTER_MAX_RUN_USD", DEFAULT_LIMITS.per_run_usd)),
        float(os.environ.get("ORCAP_ADAPTIVE_ROUTER_MAX_DAY_USD", DEFAULT_LIMITS.per_day_usd)),
        float(
            os.environ.get(
                "ORCAP_ADAPTIVE_ROUTER_MAX_CAMPAIGN_USD", DEFAULT_LIMITS.campaign_usd
            )
        ),
    )
    day, campaign = reconstruct_spend(historical, now=now, study_id=STUDY_ID)
    check_budget(
        planned_usd=float(bundle["summary"]["planned_quote_cap_usd"]),
        spent_day_usd=day,
        spent_campaign_usd=campaign,
        limits=limits,
    )

    attempts: list[dict[str, Any]] = []
    manifest_sha = str(bundle["manifest"]["manifest_sha256"])
    dt = dt_partition(now)
    attempts_path = ledger_path = None
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for assignment in assignments:
            completion, generation, error, status = send(client, assignment)
            attempt = _attempt(
                assignment,
                completion,
                generation,
                error,
                status,
                manifest_sha256=manifest_sha,
                study_id=STUDY_ID,
            )
            attempt["metadata"].update(
                {
                    "request_type": "adaptive_router_policy_emulation",
                    "provider_probability": assignment["provider_probability"],
                    "arm_probability": assignment["arm_probability"],
                    "joint_probability": assignment["joint_probability"],
                    "policy_eta": assignment["policy_eta"],
                    "policy_exploration": assignment["policy_exploration"],
                    "policy_reliability_power": assignment["policy_reliability_power"],
                    "candidate_count": assignment["candidate_count"],
                    "menu_sha256": assignment["menu_sha256"],
                    "expected_quote_usd": assignment["expected_quote_usd"],
                    "public_uptime_30m": assignment["public_uptime_30m"],
                    "selection_uniform": assignment["selection_uniform"],
                }
            )
            attempts.append(attempt)
            attempts_path, ledger_path = _write_checkpoints(
                attempts=attempts,
                assignments=assignments,
                manifest_sha=manifest_sha,
                run_id=run_id,
                dt=dt,
                curated_dir=curated_dir,
            )
    result = {
        "study_id": STUDY_ID,
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "planned_blocks": len(planned_blocks),
        "planned_requests": len(assignments),
        "attempted_requests": len(attempts),
        "successful_requests": sum(row["outcome"] == "succeeded" for row in attempts),
        "realized_cost_usd": sum(float(row.get("cost_usd") or 0.0) for row in attempts),
        "attempts_path": str(attempts_path) if attempts_path else None,
        "ledger_path": str(ledger_path) if ledger_path else None,
        "claim_boundary": bundle["summary"]["claim_boundary"],
    }
    report = curated_dir.parent / "analysis" / "adaptive-router-execution.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--bundle", type=Path, default=Path("adaptive-router-plan.json"))
    plan.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    plan.add_argument("--data-root", type=Path, default=None)
    plan.add_argument("--max-blocks", type=int, default=DEFAULT_MAX_BLOCKS)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    validate = subparsers.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()

    if args.command == "plan":
        run_id = os.environ.get("ORCAP_ADAPTIVE_ROUTER_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_ADAPTIVE_ROUTER_SEED", secrets.randbits(64)))
        root = args.data_root or args.curated_dir.parent
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_plan_bundle(
                client,
                run_id=run_id,
                seed=seed,
                data_root=root,
                max_blocks=args.max_blocks,
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
                    "horizon_reached": bundle["summary"]["horizon_reached"],
                    "planned_tasks": len(bundle["assignments"]),
                    "planned_quote_cap_usd": bundle["summary"]["planned_quote_cap_usd"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
