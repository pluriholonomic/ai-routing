"""Plan-first paid execution for the prospective GLM-5.2 routing panel."""

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

from .capture_api import write_partition
from .capture_price_response import (
    _attempt,
    _materialize,
    _send_assignment,
    _spend_rows,
    freeze_candidates,
    reconstruct_spend,
)
from .capture_route_calibration import REQUEST_TIMEOUT_SECONDS, SHAPES
from .config import CURATED_DIR, dt_partition, run_timestamp
from .glm52_routing import (
    MODEL_ID,
    PLAN_VERSION,
    STUDY_ID,
    build_assignments,
    manifest,
)
from .price_experiments import (
    PAID_SPEND_LEDGER_SCHEMA,
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
    BudgetLimits,
    campaign_open,
    check_budget,
    validate_manifest,
)
from .route_telemetry import validate_attempt, write_attempts

DEFAULT_LIMITS = BudgetLimits(per_run_usd=0.10, per_day_usd=5.0, campaign_usd=50.0)


def _short_shape():
    return next(shape for shape in SHAPES if shape.shape_id == "short_chat")


def build_plan_bundle(client: httpx.Client, *, run_id: str, seed: int) -> dict[str, Any]:
    candidates, source_failures = freeze_candidates(
        client,
        run_id=run_id,
        seed=seed,
        models=(MODEL_ID,),
        shapes=(_short_shape(),),
    )
    for row in candidates:
        row["study_id"] = STUDY_ID
        row["plan_version"] = PLAN_VERSION
        row["block_id"] = f"{STUDY_ID}|{run_id}|{MODEL_ID}|short_chat"
    assignments, summary = build_assignments(candidates, run_id=run_id, seed=seed)
    source_healthy = not source_failures and bool(assignments)
    summary = summary | {
        "source_failures": source_failures,
        "source_healthy": source_healthy,
        "preflight_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "claim_boundary": (
            "Owned GLM-5.2 requests under frozen public menus; not market-wide flow, "
            "provider profit, intent, front-running, or collusion."
        ),
    }
    plan = manifest(candidates, assignments, summary)
    return {
        "format": "orcap-glm52-routing-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
        "manifest": plan,
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
        _materialize(bundle["candidates"], PRICE_RESPONSE_CANDIDATE_SCHEMA, run_id=run_id, dt=dt),
        "glm52_routing_candidates",
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
        _materialize(assignments, PRICE_RESPONSE_ASSIGNMENT_SCHEMA, run_id=run_id, dt=dt),
        "glm52_routing_assignments",
        run_id,
        dt,
        curated_dir,
    )
    return {
        "bundle_path": str(bundle_path),
        "candidate_path": str(candidate_path),
        "assignment_path": str(assignment_path),
    }


def execute_bundle(
    bundle: dict[str, Any],
    *,
    curated_dir: Path = CURATED_DIR,
    data_root: Path | None = None,
    now: datetime | None = None,
    send: Any = _send_assignment,
    study_id: str = STUDY_ID,
    enabled_env: str = "ORCAP_GLM52_ROUTING_ENABLED",
    start_env: str = "ORCAP_GLM52_ROUTING_START_UTC",
    end_env: str = "ORCAP_GLM52_ROUTING_END_UTC",
    budget_env_prefix: str = "ORCAP_GLM52_ROUTING",
    campaign_label: str = "GLM-5.2",
) -> dict[str, Any]:
    """Execute an immutable plan once after source, campaign, and spend gates."""
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    assignments = list(bundle["assignments"])
    if not assignments:
        raise RuntimeError("validated GLM-5.2 plan contains no tasks")
    if not bool(bundle["summary"].get("source_healthy")):
        raise RuntimeError("source-health gate failed; refusing paid execution")
    if os.environ.get("ORCAP_PAID_PRICE_STUDIES_ENABLED", "").lower() != "true":
        raise RuntimeError("paid price studies are disabled")
    if os.environ.get(enabled_env, "").lower() != "true":
        raise RuntimeError(f"{campaign_label} routing study is disabled")
    if not os.environ.get("OPENROUTER_PRICE_EXPERIMENT_KEY"):
        raise RuntimeError("dedicated paid experiment key is unavailable")
    start = os.environ.get(start_env)
    end = os.environ.get(end_env)
    if not start or not end or not campaign_open(start, end, now):
        raise RuntimeError(f"paid execution refused outside the {campaign_label} campaign")

    now = (now or datetime.now(UTC)).astimezone(UTC)
    limits = BudgetLimits(
        float(os.environ.get(f"{budget_env_prefix}_MAX_RUN_USD", DEFAULT_LIMITS.per_run_usd)),
        float(os.environ.get(f"{budget_env_prefix}_MAX_DAY_USD", DEFAULT_LIMITS.per_day_usd)),
        float(os.environ.get(f"{budget_env_prefix}_MAX_CAMPAIGN_USD", DEFAULT_LIMITS.campaign_usd)),
    )
    historical = _spend_rows(data_root or curated_dir.parent)
    task_ids = [str(row["task_id"]) for row in assignments]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeError("duplicate task ids in uploaded GLM-5.2 plan")
    existing = {
        str(row.get("task_id") or "")
        for row in historical
        if str(row.get("study_id") or "") == study_id
    }
    overlap = sorted(set(task_ids) & existing)
    if overlap:
        raise RuntimeError(f"refusing to re-execute {len(overlap)} GLM-5.2 task(s)")
    spent_day, spent_campaign = reconstruct_spend(historical, now=now, study_id=study_id)
    check_budget(
        planned_usd=float(bundle["summary"]["planned_quote_cap_usd"]),
        spent_day_usd=spent_day,
        spent_campaign_usd=spent_campaign,
        limits=limits,
    )

    attempts = []
    observed_at = run_timestamp(now)
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
                    manifest_sha256=str(bundle["manifest"]["manifest_sha256"]),
                    study_id=study_id,
                    observed_at=observed_at,
                )
            )
    run_id = str(bundle["summary"]["run_id"])
    dt = dt_partition(now)
    generic_path = write_attempts(attempts, run_ts=run_id, dt=dt, curated_dir=curated_dir)
    dedicated_rows = [validate_attempt(row) | {"run_ts": run_id, "dt": dt} for row in attempts]
    dedicated_path = write_partition(
        pa.Table.from_pylist(dedicated_rows),
        "glm52_routing_attempts",
        run_id,
        dt,
        curated_dir,
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
    result = {
        "study_id": study_id,
        "run_id": run_id,
        "manifest_sha256": bundle["manifest"]["manifest_sha256"],
        "planned_requests": len(assignments),
        "attempted_requests": len(attempts),
        "successful_requests": sum(row["outcome"] == "succeeded" for row in attempts),
        "selected_provider_observed": sum(bool(row.get("selected_provider")) for row in attempts),
        "realized_cost_usd": sum(float(row.get("cost_usd") or 0.0) for row in attempts),
        "generic_attempts_path": str(generic_path) if generic_path else None,
        "dedicated_attempts_path": str(dedicated_path),
        "ledger_path": str(ledger_path),
        "claim_boundary": bundle["summary"]["claim_boundary"],
    }
    report = curated_dir.parent / "analysis" / "glm52-routing-execution.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--bundle", type=Path, default=Path("glm52-routing-plan.json"))
    plan.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    execute = commands.add_parser("execute")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    validate = commands.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_GLM52_ROUTING_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_GLM52_ROUTING_SEED", secrets.randbits(64)))
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_plan_bundle(client, run_id=run_id, seed=seed)
        paths = write_plan_bundle(bundle, bundle_path=args.bundle, curated_dir=args.curated_dir)
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
            raise RuntimeError("public GLM-5.2 source failed health validation")
        if args.require_tasks and not bundle["assignments"]:
            raise RuntimeError("validated GLM-5.2 plan contains no tasks")
        print(
            json.dumps(
                {
                    "manifest_sha256": bundle["manifest"]["manifest_sha256"],
                    "source_healthy": True,
                    "planned_tasks": len(bundle["assignments"]),
                    "planned_quote_cap_usd": bundle["summary"]["planned_quote_cap_usd"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
