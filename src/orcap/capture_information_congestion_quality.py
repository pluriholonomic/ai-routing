"""Balanced, plan-first quality bank for information-congestion v1."""

from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow as pa

from .analysis.information_congestion_readiness import capture_continuity
from .capture_api import write_partition
from .capture_information_congestion import _read, _source_fresh
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
from .config import DATA_DIR, dt_partition, run_timestamp
from .information_congestion import DEFAULT_CONFIG, load_protocol
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
    provider_key,
    validate_manifest,
)
from .route_telemetry import validate_attempt, write_attempts

STUDY_ID = "openrouter-information-congestion-quality-v1"
PLAN_VERSION = "information-congestion-quality-plan-v1"


def _short_shape():
    return next(shape for shape in SHAPES if shape.shape_id == "short_chat")


def _history(data_root: Path) -> pd.DataFrame:
    return _read(data_root, "ic_quality")


def _balanced_candidates(
    candidates: list[dict[str, Any]],
    history: pd.DataFrame,
    *,
    models: list[str],
    seed: int,
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    """Choose the least-measured feasible model and three least-measured providers."""

    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_model.setdefault(str(row.get("model_id") or ""), []).append(row)
    model_counts = (
        history.groupby("model_id")["task_id"].nunique().to_dict()
        if not history.empty and {"model_id", "task_id"}.issubset(history)
        else {}
    )
    feasible = [
        model
        for model in models
        if len(collapse_provider_candidates(by_model.get(model, []))) >= 3
    ]
    if not feasible:
        return [], None, []
    feasible.sort(
        key=lambda model: (
            int(model_counts.get(model, 0)),
            int.from_bytes(f"{seed}|{model}".encode(), "little") % (2**63),
            model,
        )
    )
    selected_model = feasible[0]
    collapsed = collapse_provider_candidates(by_model[selected_model])
    provider_counts: dict[str, int] = {}
    if not history.empty and {"model_id", "requested_provider", "task_id"}.issubset(history):
        relevant = history[history["model_id"].astype(str).eq(selected_model)].copy()
        relevant["provider_key"] = relevant["requested_provider"].map(provider_key)
        provider_counts = relevant.groupby("provider_key")["task_id"].nunique().to_dict()
    collapsed.sort(
        key=lambda row: (
            int(provider_counts.get(str(row["provider_key"]), 0)),
            float(row["expected_quote_usd"]),
            str(row["provider_key"]),
        )
    )
    selected = collapsed[:3]
    return selected, selected_model, [str(row["provider_key"]) for row in selected]


def build_plan_bundle(
    client: httpx.Client,
    *,
    data_root: Path,
    run_id: str,
    seed: int,
    config_path: Path = DEFAULT_CONFIG,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    protocol, protocol_sha256 = load_protocol(config_path)
    design = protocol["design"]
    support = protocol["support"]
    snapshots = _read(data_root, "endpoints_snapshots")
    source_fresh = _source_fresh(
        snapshots,
        now=now,
        maximum_age_minutes=int(design["maximum_public_snapshot_age_minutes"]),
    )
    continuity = capture_continuity(snapshots, now=now)
    continuity["coverage_gate"] = continuity["coverage"] >= float(
        support["minimum_capture_coverage"]
    )
    maximum_gap = continuity["maximum_gap_minutes"]
    continuity["gap_gate"] = maximum_gap is not None and maximum_gap <= float(
        support["maximum_gap_minutes"]
    )
    models = [str(value) for value in protocol["study"]["models"]]
    candidates, source_failures = freeze_candidates(
        client,
        run_id=run_id,
        seed=seed,
        models=tuple(models),
        shapes=(_short_shape(),),
    )
    selected, selected_model, selected_providers = _balanced_candidates(
        candidates,
        _history(data_root),
        models=models,
        seed=seed,
    )
    block_id = f"{STUDY_ID}|{run_id}|{selected_model or 'unavailable'}|quality_mmlu"
    for row in selected:
        row.update(
            {
                "study_id": STUDY_ID,
                "plan_version": PLAN_VERSION,
                "block_id": block_id,
            }
        )
    items = select_quality_items(_public_items(), seed=seed, count=2)
    all_assignments, base_summary = build_market_assignments(
        selected, items, run_id=run_id, seed=seed
    )
    assignments = []
    for row in all_assignments:
        if row.get("experiment_axis") != "quality":
            continue
        rewritten = dict(row)
        rewritten.update(
            {
                "study_id": STUDY_ID,
                "plan_version": PLAN_VERSION,
                "block_id": block_id,
                "task_id": (
                    f"{STUDY_ID}|{run_id}|{row['policy']}|{row['quality_item_id']}"
                ),
            }
        )
        rewritten["execution_batch"] = rewritten["task_id"]
        rewritten["session_group"] = f"fresh|{rewritten['task_id']}"
        assignments.append(rewritten)
    source_healthy = bool(
        selected_model
        and len(assignments) == 8
        and source_fresh
        and continuity["coverage_gate"]
        and continuity["gap_gate"]
    )
    summary = {
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "created_at": now.isoformat(),
        "protocol_sha256": protocol_sha256,
        "selected_model": selected_model,
        "selected_provider_keys": selected_providers,
        "selected_quality_items": base_summary.get("selected_quality_items", []),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(
            float(row["task_quote_cap_usd"]) for row in assignments
        ),
        "source_failures": source_failures,
        "source_healthy": source_healthy,
        "public_snapshot_fresh": source_fresh,
        "capture_continuity": continuity,
        "preflight_only": True,
        "payload_retained": False,
        "claim_boundary": (
            "Owned exact-pin benchmark fidelity, success, latency, and cost only; not "
            "provider marginal cost, market-wide quality, or a proprietary router score."
        ),
    }
    manifest = market_manifest(selected, assignments, summary)
    return {
        "format": "orcap-information-congestion-quality-plan-v1",
        "candidates": selected,
        "assignments": assignments,
        "summary": summary,
        "manifest": manifest,
    }


def validate_bundle(bundle: dict[str, Any], *, require_tasks: bool = False) -> None:
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    if bundle["summary"].get("payload_retained") is not False:
        raise ValueError("quality plan must retain no payload")
    if require_tasks and len(bundle["assignments"]) != 8:
        raise RuntimeError("quality plan does not contain the frozen eight tasks")
    task_ids = [str(row.get("task_id") or "") for row in bundle["assignments"]]
    if any(not value for value in task_ids) or len(task_ids) != len(set(task_ids)):
        raise ValueError("quality task IDs must be nonempty and unique")


def write_plan_bundle(
    bundle: dict[str, Any], *, bundle_path: Path, curated_dir: Path
) -> dict[str, str | None]:
    validate_bundle(bundle)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    run_id = str(bundle["summary"]["run_id"])
    dt = dt_partition()
    candidate_path = None
    assignment_path = None
    if bundle["candidates"]:
        candidate_path = write_partition(
            _materialize(
                bundle["candidates"], PRICE_RESPONSE_CANDIDATE_SCHEMA, run_id=run_id, dt=dt
            ),
            "ic_quality_candidates",
            run_id,
            dt,
            curated_dir,
        )
    if bundle["assignments"]:
        rows = [
            row
            | {
                "manifest_sha256": bundle["manifest"]["manifest_sha256"],
                "preflight_only": True,
            }
            for row in bundle["assignments"]
        ]
        assignment_path = write_partition(
            _materialize(
                rows, MARKET_MEASUREMENT_ASSIGNMENT_SCHEMA, run_id=run_id, dt=dt
            ),
            "ic_quality_assignments",
            run_id,
            dt,
            curated_dir,
        )
    return {
        "bundle_path": str(bundle_path),
        "candidate_path": str(candidate_path) if candidate_path else None,
        "assignment_path": str(assignment_path) if assignment_path else None,
    }


def execute_bundle(
    bundle: dict[str, Any],
    *,
    data_root: Path,
    config_path: Path = DEFAULT_CONFIG,
    now: datetime | None = None,
    send: Any = None,
) -> dict[str, Any]:
    validate_bundle(bundle, require_tasks=True)
    if os.environ.get("ORCAP_PAID_PRICE_STUDIES_ENABLED", "").lower() != "true":
        raise RuntimeError("paid price studies are disabled")
    if os.environ.get("ORCAP_INFORMATION_CONGESTION_QUALITY_ENABLED", "").lower() != "true":
        raise RuntimeError("information-congestion quality bank is disabled")
    if not os.environ.get("OPENROUTER_PRICE_EXPERIMENT_KEY"):
        raise RuntimeError("dedicated paid experiment key is unavailable")
    if not bundle["summary"].get("source_healthy"):
        raise RuntimeError("quality execution refused by capture-continuity gate")
    protocol, protocol_sha256 = load_protocol(config_path)
    if str(bundle["summary"].get("protocol_sha256")) != protocol_sha256:
        raise RuntimeError("quality protocol hash changed after planning")
    start = os.environ.get(
        "ORCAP_INFORMATION_CONGESTION_START_UTC",
        str(protocol["study"]["prospective_start_utc"]),
    )
    end = os.environ.get(
        "ORCAP_INFORMATION_CONGESTION_END_UTC", str(protocol["study"]["campaign_end_utc"])
    )
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if not campaign_open(start, end, now):
        raise RuntimeError("quality execution refused outside the frozen campaign")
    limits = BudgetLimits(
        float(os.environ.get("ORCAP_INFORMATION_CONGESTION_QUALITY_MAX_RUN_USD", "0.50")),
        float(os.environ.get("ORCAP_INFORMATION_CONGESTION_QUALITY_MAX_DAY_USD", "3.00")),
        float(
            os.environ.get(
                "ORCAP_INFORMATION_CONGESTION_QUALITY_MAX_CAMPAIGN_USD",
                str(protocol["budget"]["quality_usd"]),
            )
        ),
    )
    historical = _spend_rows(data_root)
    task_ids = [str(row["task_id"]) for row in bundle["assignments"]]
    existing = {
        str(row.get("task_id") or "")
        for row in historical
        if str(row.get("study_id") or "") == STUDY_ID
    }
    overlap = sorted(set(task_ids) & existing)
    if overlap:
        raise RuntimeError(f"refusing to re-execute {len(overlap)} quality tasks")
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
        for assignment in bundle["assignments"]:
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
                    "request_type": "information_congestion_quality_probe",
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
    write_attempts(attempts, run_ts=run_id, dt=dt, curated_dir=data_root / "curated")
    attempts_path = write_partition(
        pa.Table.from_pylist(
            [validate_attempt(row) | {"run_ts": run_id, "dt": dt} for row in attempts]
        ),
        "ic_quality_attempts",
        run_id,
        dt,
        data_root / "curated",
    )
    quality_path = write_partition(
        _materialize(quality_rows, MARKET_MEASUREMENT_QUALITY_SCHEMA, run_id=run_id, dt=dt),
        "ic_quality",
        run_id,
        dt,
        data_root / "curated",
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
        for assignment, attempt in zip(bundle["assignments"], attempts, strict=True)
    ]
    ledger_path = write_partition(
        _materialize(ledger_rows, PAID_SPEND_LEDGER_SCHEMA, run_id=run_id, dt=dt),
        "paid_spend_ledger",
        run_id,
        dt,
        data_root / "curated",
    )
    return {
        "study_id": STUDY_ID,
        "run_id": run_id,
        "planned_requests": len(bundle["assignments"]),
        "attempted_requests": len(attempts),
        "successful_requests": sum(row["outcome"] == "succeeded" for row in attempts),
        "quality_rows": len(quality_rows),
        "realized_cost_usd": sum(float(row.get("cost_usd") or 0.0) for row in attempts),
        "attempts_path": str(attempts_path),
        "quality_path": str(quality_path),
        "ledger_path": str(ledger_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--data-root", type=Path, default=DATA_DIR)
    plan.add_argument("--output-root", type=Path)
    plan.add_argument("--bundle", type=Path, default=Path("information-congestion-quality.json"))
    plan.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    execute = commands.add_parser("execute")
    execute.add_argument("--data-root", type=Path, default=DATA_DIR)
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    validate = commands.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_IC_QUALITY_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_IC_QUALITY_SEED", secrets.randbits(64)))
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_plan_bundle(
                client,
                data_root=args.data_root,
                run_id=run_id,
                seed=seed,
                config_path=args.config,
            )
        paths = write_plan_bundle(
            bundle,
            bundle_path=args.bundle,
            curated_dir=(args.output_root or args.data_root) / "curated",
        )
        print(json.dumps(bundle["summary"] | bundle["manifest"] | paths, indent=2))
    elif args.command == "execute":
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        print(
            json.dumps(
                execute_bundle(
                    bundle,
                    data_root=args.data_root,
                    config_path=args.config,
                ),
                indent=2,
            )
        )
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_bundle(bundle, require_tasks=args.require_tasks)
        print(
            json.dumps(
                {
                    "manifest_sha256": bundle["manifest"]["manifest_sha256"],
                    "source_healthy": bundle["summary"]["source_healthy"],
                    "planned_tasks": len(bundle["assignments"]),
                    "planned_quote_cap_usd": bundle["summary"]["planned_quote_cap_usd"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
