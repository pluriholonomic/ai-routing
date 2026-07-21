"""Plan-first six-hour quality bank for the prospective score-memory study."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .capture_api import write_partition
from .capture_market_measurement import (
    _public_items,
    _quality_item_map,
    _quality_row,
    _send_quality_assignment,
)
from .capture_price_response import (
    _attempt,
    _materialize,
    _spend_rows,
    freeze_candidates,
    reconstruct_spend,
)
from .capture_route_calibration import REQUEST_TIMEOUT_SECONDS, SHAPES
from .config import CURATED_DIR, dt_partition, run_timestamp
from .glm52_routing import MODEL_ID
from .market_measurement import (
    MARKET_MEASUREMENT_ASSIGNMENT_SCHEMA,
    MARKET_MEASUREMENT_QUALITY_SCHEMA,
    build_market_assignments,
    market_manifest,
    select_quality_items,
)
from .price_experiments import (
    PAID_SPEND_LEDGER_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
    BudgetLimits,
    campaign_open,
    check_budget,
    collapse_provider_candidates,
    validate_manifest,
)
from .route_telemetry import validate_attempt, write_attempts

STUDY_ID = "openrouter-score-memory-quality-v1"
PLAN_VERSION = "score-memory-quality-plan-v1"
DEFAULT_LIMITS = BudgetLimits(per_run_usd=0.25, per_day_usd=2.0, campaign_usd=30.0)


def _short_shape():
    return next(shape for shape in SHAPES if shape.shape_id == "short_chat")


def _history_rows(data_root: Path | None) -> list[dict[str, Any]]:
    if data_root is None:
        return []
    rows = []
    for path in sorted((data_root / "curated" / "score_memory_quality").glob("dt=*/*.parquet")):
        try:
            rows.extend(pq.ParquetFile(path).read().to_pylist())
        except (OSError, pa.ArrowInvalid):
            continue
    return rows


def _policy_orders(
    candidates: list[dict[str, Any]], history: list[dict[str, Any]], *, now: datetime
) -> dict[str, list[str]]:
    collapsed = sorted(
        collapse_provider_candidates(candidates),
        key=lambda row: float(row["expected_quote_usd"]),
    )
    providers = [str(row.get("provider_name") or "").casefold() for row in collapsed]
    tags = {
        str(row.get("provider_name") or "").casefold(): str(row["endpoint_tag"])
        for row in collapsed
    }
    prices = {
        str(row.get("provider_name") or "").casefold(): float(row["expected_quote_usd"])
        for row in collapsed
    }
    weighted: dict[str, list[tuple[float, float]]] = {provider: [] for provider in providers}
    recent_failure: dict[str, bool] = {provider: False for provider in providers}
    for row in history:
        # Policy-arm outcomes are excluded by construction, so all arms see the
        # same exogenous pinned/default quality history.
        if str(row.get("policy") or "").startswith("router_"):
            continue
        provider = str(
            row.get("requested_provider") or row.get("selected_provider") or ""
        ).casefold()
        observed = pd.to_datetime(row.get("observed_at"), utc=True, errors="coerce")
        if provider not in weighted or pd.isna(observed):
            continue
        age_hours = max(0.0, (now - observed.to_pydatetime()).total_seconds() / 3600)
        weight = math.exp(-math.log(2) * age_hours / 24.0)
        success = float(row.get("http_status") == 200)
        fidelity = float(bool(row.get("correct"))) if row.get("correct") is not None else 0.5
        latency = row.get("latency_ms")
        try:
            latency_penalty = 0.05 * math.log1p(max(float(latency), 0.0) / 1000.0)
        except (TypeError, ValueError):
            latency_penalty = 0.0
        weighted[provider].append((weight, success + fidelity - latency_penalty))
        if age_hours <= 24 and (success == 0 or row.get("correct") is False):
            recent_failure[provider] = True
    quality_score = {}
    for provider, values in weighted.items():
        denominator = sum(weight for weight, _ in values)
        quality_score[provider] = (
            sum(weight * value for weight, value in values) / denominator if denominator else 0.0
        )
    price_order = sorted(providers, key=lambda provider: (prices[provider], provider))
    quality_order = sorted(
        providers,
        key=lambda provider: (
            math.log(prices[provider]) - quality_score[provider] / 1.6482780609377246,
            provider,
        ),
    )
    finite_order = sorted(
        providers,
        key=lambda provider: (recent_failure[provider], prices[provider], provider),
    )
    return {
        "router_no_memory": [tags[provider] for provider in price_order],
        "router_geometric_quality": [tags[provider] for provider in quality_order],
        "router_finite_failure": [tags[provider] for provider in finite_order],
    }


def build_plan_bundle(
    client: httpx.Client,
    *,
    run_id: str,
    seed: int,
    quality_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates, source_failures = freeze_candidates(
        client,
        run_id=run_id,
        seed=seed,
        models=(MODEL_ID,),
        shapes=(_short_shape(),),
    )
    block_id = f"{STUDY_ID}|{run_id}|{MODEL_ID}|quality_mmlu"
    for row in candidates:
        row.update({"study_id": STUDY_ID, "plan_version": PLAN_VERSION, "block_id": block_id})
    items = select_quality_items(_public_items(), seed=seed, count=2)
    all_assignments, base_summary = build_market_assignments(
        candidates, items, run_id=run_id, seed=seed
    )
    assignments = []
    for row in all_assignments:
        if row.get("experiment_axis") != "quality":
            continue
        rewritten = dict(row)
        rewritten["study_id"] = STUDY_ID
        rewritten["plan_version"] = PLAN_VERSION
        rewritten["block_id"] = block_id
        rewritten["task_id"] = (
            f"{STUDY_ID}|{run_id}|{rewritten['policy']}|{rewritten['quality_item_id']}"
        )
        rewritten["execution_batch"] = rewritten["task_id"]
        rewritten["session_group"] = f"fresh|{rewritten['task_id']}"
        assignments.append(rewritten)
    if len(assignments) != 8:
        summary = {
            "study_id": STUDY_ID,
            "plan_version": PLAN_VERSION,
            "run_id": run_id,
            "seed": str(seed),
            "planned_blocks": 0,
            "planned_tasks": 0,
            "planned_quote_cap_usd": 0.0,
            "selected_quality_items": base_summary.get("selected_quality_items", []),
            "router_policy_counts": {},
            "router_policy_state_rows": len(quality_history or []),
            "candidate_provider_count": len({row.get("provider_name") for row in candidates}),
            "source_failures": source_failures,
            "source_healthy": False,
            "preflight_only": True,
            "created_at": datetime.now(UTC).isoformat(),
            "skip_reason": "fewer_than_three_compatible_providers_or_no_quality_block",
            "claim_boundary": "No paid request is permitted from an incomplete plan.",
        }
        manifest = market_manifest(candidates, [], summary)
        return {
            "format": "orcap-score-memory-quality-plan-v1",
            "candidates": candidates,
            "assignments": [],
            "summary": summary,
            "manifest": manifest,
        }
    # A randomized complete block applies all three declared router policies to
    # one frozen item. State is computed only from prior non-policy quality rows.
    observed = pd.to_datetime(candidates[0].get("observed_at"), utc=True, errors="coerce")
    policy_time = observed.to_pydatetime() if pd.notna(observed) else datetime.now(UTC)
    orders = _policy_orders(
        candidates,
        list(quality_history or []),
        now=policy_time,
    )
    template = next(
        row
        for row in assignments
        if row["policy"] == "quality_default"
        and row["quality_item_id"] == sorted(base_summary["selected_quality_items"])[0]
    )
    all_tags = [str(row["endpoint_tag"]) for row in collapse_provider_candidates(candidates)]
    for policy, order in orders.items():
        row = dict(template)
        row.update(
            {
                "experiment_axis": "router_policy",
                "policy": policy,
                "task_id": f"{STUDY_ID}|{run_id}|{policy}|{template['quality_item_id']}",
                "execution_batch": f"router-policy|{run_id}",
                "requested_provider": None,
                "requested_endpoint_tag": None,
                "provider_order_tags": order,
                "provider_only_tags": all_tags,
                "allow_fallbacks": True,
            }
        )
        row["session_group"] = f"fresh|{row['task_id']}"
        assignments.append(row)
    random.Random(seed).shuffle(assignments)
    for position, assignment in enumerate(assignments):
        assignment["policy_order"] = position
    source_healthy = not source_failures and len(assignments) == 11
    summary = {
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "planned_blocks": 1 if assignments else 0,
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(float(row["task_quote_cap_usd"]) for row in assignments),
        "selected_quality_items": base_summary.get("selected_quality_items", []),
        "router_policy_counts": {
            policy: sum(row["policy"] == policy for row in assignments) for policy in orders
        },
        "router_policy_state_rows": len(quality_history or []),
        "candidate_provider_count": len({row.get("provider_name") for row in candidates}),
        "source_failures": source_failures,
        "source_healthy": source_healthy,
        "preflight_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "claim_boundary": (
            "Owned, tiny-load fidelity and latency observations under exact pins; not "
            "capacity, market-wide quality, a proprietary score, provider intent, or cost."
        ),
    }
    manifest = market_manifest(candidates, assignments, summary)
    return {
        "format": "orcap-score-memory-quality-plan-v1",
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
    candidates = write_partition(
        _materialize(bundle["candidates"], PRICE_RESPONSE_CANDIDATE_SCHEMA, run_id=run_id, dt=dt),
        "score_memory_quality_candidates",
        run_id,
        dt,
        curated_dir,
    )
    assignment_rows = [
        row
        | {
            "manifest_sha256": bundle["manifest"]["manifest_sha256"],
            "preflight_only": True,
        }
        for row in bundle["assignments"]
    ]
    assignments = write_partition(
        _materialize(
            assignment_rows,
            MARKET_MEASUREMENT_ASSIGNMENT_SCHEMA,
            run_id=run_id,
            dt=dt,
        ),
        "score_memory_quality_assignments",
        run_id,
        dt,
        curated_dir,
    )
    return {
        "bundle_path": str(bundle_path),
        "candidate_path": str(candidates),
        "assignment_path": str(assignments),
    }


def execute_bundle(
    bundle: dict[str, Any],
    *,
    curated_dir: Path = CURATED_DIR,
    data_root: Path | None = None,
    now: datetime | None = None,
    send: Any = None,
) -> dict[str, Any]:
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    assignments = list(bundle["assignments"])
    if len(assignments) != 11 or not bundle["summary"].get("source_healthy"):
        raise RuntimeError("quality source or eleven-task assignment gate failed")
    if os.environ.get("ORCAP_PAID_PRICE_STUDIES_ENABLED", "").lower() != "true":
        raise RuntimeError("paid price studies are disabled")
    if os.environ.get("ORCAP_SCORE_MEMORY_QUALITY_ENABLED", "").lower() != "true":
        raise RuntimeError("score-memory quality bank is disabled")
    if not os.environ.get("OPENROUTER_PRICE_EXPERIMENT_KEY"):
        raise RuntimeError("dedicated paid experiment key is unavailable")
    start = os.environ.get("ORCAP_SCORE_MEMORY_QUALITY_START_UTC")
    end = os.environ.get("ORCAP_SCORE_MEMORY_QUALITY_END_UTC")
    if not start or not end or not campaign_open(start, end, now):
        raise RuntimeError("paid execution refused outside the quality campaign")
    now = (now or datetime.now(UTC)).astimezone(UTC)
    limits = BudgetLimits(
        float(os.environ.get("ORCAP_SCORE_MEMORY_QUALITY_MAX_RUN_USD", DEFAULT_LIMITS.per_run_usd)),
        float(os.environ.get("ORCAP_SCORE_MEMORY_QUALITY_MAX_DAY_USD", DEFAULT_LIMITS.per_day_usd)),
        float(
            os.environ.get(
                "ORCAP_SCORE_MEMORY_QUALITY_MAX_CAMPAIGN_USD", DEFAULT_LIMITS.campaign_usd
            )
        ),
    )
    historical = _spend_rows(data_root or curated_dir.parent)
    task_ids = [str(row["task_id"]) for row in assignments]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeError("duplicate quality task ids")
    existing = {
        str(row.get("task_id") or "")
        for row in historical
        if str(row.get("study_id") or "") == STUDY_ID
    }
    overlap = sorted(set(task_ids) & existing)
    if overlap:
        raise RuntimeError(f"refusing to re-execute {len(overlap)} quality task(s)")
    spent_day, spent_campaign = reconstruct_spend(historical, now=now, study_id=STUDY_ID)
    check_budget(
        planned_usd=float(bundle["summary"]["planned_quote_cap_usd"]),
        spent_day_usd=spent_day,
        spent_campaign_usd=spent_campaign,
        limits=limits,
    )

    item_map = _quality_item_map()
    attempts = []
    quality_rows = []
    manifest_sha = str(bundle["manifest"]["manifest_sha256"])
    observed_at = run_timestamp(now)
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for assignment in assignments:
            item = item_map[str(assignment["quality_item_id"])]
            completion, generation, error, status = (
                send(client, assignment)
                if send is not None
                else _send_quality_assignment(client, assignment, item)
            )
            attempt = _attempt(
                assignment,
                completion,
                generation,
                error,
                status,
                manifest_sha256=manifest_sha,
                study_id=STUDY_ID,
                observed_at=observed_at,
            )
            attempt["metadata"].update(
                {
                    "request_type": "score_memory_quality_probe",
                    "experiment_axis": assignment["experiment_axis"],
                    "quality_item_id": assignment["quality_item_id"],
                }
            )
            attempts.append(attempt)
            quality_rows.append(
                _quality_row(
                    assignment,
                    item,
                    completion,
                    generation,
                    status,
                    manifest_sha256=manifest_sha,
                    observed_at=observed_at,
                )
                | {"study_id": STUDY_ID}
            )
    run_id = str(bundle["summary"]["run_id"])
    dt = dt_partition(now)
    write_attempts(attempts, run_ts=run_id, dt=dt, curated_dir=curated_dir)
    attempts_path = write_partition(
        pa.Table.from_pylist(
            [validate_attempt(row) | {"run_ts": run_id, "dt": dt} for row in attempts]
        ),
        "score_memory_quality_attempts",
        run_id,
        dt,
        curated_dir,
    )
    quality_path = write_partition(
        _materialize(quality_rows, MARKET_MEASUREMENT_QUALITY_SCHEMA, run_id=run_id, dt=dt),
        "score_memory_quality",
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
        "study_id": STUDY_ID,
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "planned_requests": len(assignments),
        "attempted_requests": len(attempts),
        "successful_requests": sum(row["outcome"] == "succeeded" for row in attempts),
        "quality_rows": len(quality_rows),
        "realized_cost_usd": sum(float(row.get("cost_usd") or 0.0) for row in attempts),
        "attempts_path": str(attempts_path),
        "quality_path": str(quality_path),
        "ledger_path": str(ledger_path),
        "claim_boundary": bundle["summary"]["claim_boundary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--bundle", type=Path, default=Path("score-memory-quality-plan.json"))
    plan.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    plan.add_argument("--data-root", type=Path, default=Path("input-data"))
    execute = commands.add_parser("execute")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    validate = commands.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_SCORE_MEMORY_QUALITY_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_SCORE_MEMORY_QUALITY_SEED", secrets.randbits(64)))
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_plan_bundle(
                client,
                run_id=run_id,
                seed=seed,
                quality_history=_history_rows(args.data_root),
            )
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
            bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
        )
        if not bundle["summary"].get("source_healthy"):
            raise RuntimeError("public quality source failed health validation")
        if args.require_tasks and len(bundle["assignments"]) != 11:
            raise RuntimeError("validated quality plan does not contain eleven tasks")
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
