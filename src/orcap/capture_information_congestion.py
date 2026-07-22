"""Plan-first paid capture for the prospective information-congestion study."""

from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .capture_api import write_partition
from .capture_price_response import REQUEST_TIMEOUT_SECONDS, execute_bundle, freeze_candidates
from .capture_route_calibration import SHAPES
from .config import DATA_DIR, dt_partition, run_timestamp
from .information_congestion import (
    DEFAULT_CONFIG,
    IC_ASSIGNMENT_SCHEMA,
    IC_CANDIDATE_SCHEMA,
    IC_MARKET_EPOCH_SCHEMA,
    IC_PROVIDER_ROLE_SCHEMA,
    IC_RUN_SCHEMA,
    build_factorial_assignments,
    canonical_bundle_hash,
    classify_provider_roles,
    load_protocol,
    market_epoch,
    protocol_claim_boundary,
    validate_factorial_assignments,
)
from .price_experiments import plan_manifest, provider_key, validate_manifest


def _read(root: Path, table: str) -> pd.DataFrame:
    frames = []
    for path in sorted((root / "curated" / table).glob("dt=*/*.parquet")):
        try:
            frames.append(pq.ParquetFile(path).read().to_pandas())
        except (OSError, pa.ArrowInvalid):
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _latest_snapshot(snapshots: pd.DataFrame) -> datetime | None:
    if snapshots.empty or "run_ts" not in snapshots:
        return None
    parsed = pd.to_datetime(
        snapshots["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    ).dropna()
    return parsed.max().to_pydatetime() if not parsed.empty else None


def _source_fresh(snapshots: pd.DataFrame, *, now: datetime, maximum_age_minutes: int) -> bool:
    latest = _latest_snapshot(snapshots)
    return bool(latest and now - latest <= timedelta(minutes=maximum_age_minutes))


def _roles_for_live_menu(
    snapshots: pd.DataFrame,
    candidates: list[dict[str, Any]],
    *,
    model_id: str,
    protocol: dict[str, Any],
    protocol_sha256: str,
    run_id: str,
    market_epoch_id: str,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], float]]:
    design = protocol["design"]
    cutoff = pd.Timestamp(protocol["study"]["prospective_start_utc"])
    classified, pair_correlations = classify_provider_roles(
        snapshots,
        model_id,
        cutoff=cutoff,
        minimum_price_changes=int(design["minimum_price_changes"]),
        minimum_history_snapshots=int(design["minimum_history_snapshots"]),
        minimum_provider_coverage=float(design["minimum_provider_coverage"]),
        author_keys={"Z.AI", "Z.ai"},
        innovation_horizon_hours=int(design["innovation_horizon_hours"]),
    )
    by_key = (
        {str(row["provider_key"]): row for row in classified.to_dict("records")}
        if not classified.empty
        else {}
    )
    live = {}
    for row in candidates:
        if str(row.get("model_id")) != model_id or not bool(row.get("compatible", True)):
            continue
        key = provider_key(row.get("provider_name"))
        live.setdefault(key, str(row.get("provider_name") or key))
    rows = []
    for key, name in sorted(live.items()):
        prior = by_key.get(key) or {
            "provider_name": name,
            "provider_key": key,
            "responsive": False,
            "price_change_count": 0,
            "snapshot_coverage": 0.0,
            "median_relative_to_author": None,
            "mean_abs_correlation": None,
            "classification_cutoff": cutoff.isoformat(),
            "payload_retained": False,
        }
        rows.append(
            dict(prior)
            | {
                "study_id": str(protocol["study"]["study_id"]),
                "plan_version": str(protocol["study"]["plan_version"]),
                "run_id": run_id,
                "market_epoch_id": market_epoch_id,
                "model_id": model_id,
                "provider_name": name,
                "provider_key": key,
                "protocol_sha256": protocol_sha256,
                "payload_retained": False,
            }
        )
    return rows, pair_correlations


def _existing_task_ids(data_root: Path, study_id: str) -> set[str]:
    output = set()
    for table in ("ic_assignments", "paid_spend_ledger"):
        frame = _read(data_root, table)
        if frame.empty or "task_id" not in frame:
            continue
        if "study_id" in frame:
            frame = frame[frame["study_id"].astype(str).eq(study_id)]
        output.update(frame["task_id"].dropna().astype(str))
    return output


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
    protocol_claim_boundary(protocol)
    study = protocol["study"]
    design = protocol["design"]
    study_id = str(study["study_id"])
    plan_version = str(study["plan_version"])
    models = tuple(str(item) for item in study["models"])
    shape = next(item for item in SHAPES if item.shape_id == "short_chat")
    snapshots = _read(data_root, "endpoints_snapshots")
    source_fresh = _source_fresh(
        snapshots,
        now=now,
        maximum_age_minutes=int(design["maximum_public_snapshot_age_minutes"]),
    )
    candidates, source_failures = freeze_candidates(
        client,
        run_id=run_id,
        seed=seed,
        models=models,
        shapes=(shape,),
    )
    for row in candidates:
        row.update(
            {
                "study_id": study_id,
                "plan_version": plan_version,
                "block_id": f"{study_id}|{run_id}|{row['model_id']}|short_chat",
            }
        )

    candidate_by_model: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        candidate_by_model.setdefault(str(row["model_id"]), []).append(row)
    epochs = []
    roles = []
    correlations: dict[str, dict[tuple[str, str], float]] = {}
    for model_id, model_candidates in candidate_by_model.items():
        preliminary_roles, pair_corr = _roles_for_live_menu(
            snapshots,
            model_candidates,
            model_id=model_id,
            protocol=protocol,
            protocol_sha256=protocol_sha256,
            run_id=run_id,
            market_epoch_id="pending",
        )
        responsive = {
            str(row["provider_key"]) for row in preliminary_roles if bool(row["responsive"])
        }
        epoch = market_epoch(
            model_candidates,
            study_id=study_id,
            plan_version=plan_version,
            run_id=run_id,
            model_id=model_id,
            responsive_keys=responsive,
            protocol_sha256=protocol_sha256,
        )
        for row in preliminary_roles:
            row["market_epoch_id"] = epoch["market_epoch_id"]
        epochs.append(epoch)
        roles.extend(preliminary_roles)
        correlations[model_id] = pair_corr

    prior = _read(data_root, "ic_assignments")
    assignments, design_summary = build_factorial_assignments(
        candidates,
        roles,
        epochs,
        correlations,
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        run_id=run_id,
        seed=seed,
        prior_assignments=prior.to_dict("records") if not prior.empty else (),
    )
    reserved = _existing_task_ids(data_root, study_id)
    assignments = [row for row in assignments if str(row["task_id"]) not in reserved]
    minimum = int(design["minimum_compatible_providers"])
    healthy_models = sum(int(epoch["eligible_n"]) >= minimum for epoch in epochs)
    # Fixed registries may contain a model that has not launched yet or has
    # temporarily left the surface.  Preserve that failure in the ledger but
    # allow a fresh, supported cohort to accrue rather than silently dropping
    # the whole prospective run.
    source_healthy = bool(source_fresh and healthy_models > 0)
    summary = {
        "study_id": study_id,
        "plan_version": plan_version,
        "run_id": run_id,
        "seed": str(seed),
        "created_at": now.isoformat(),
        "protocol_sha256": protocol_sha256,
        "source_healthy": source_healthy,
        "public_snapshot_fresh": source_fresh,
        "source_failures": source_failures,
        "models_requested": len(models),
        "models_healthy": healthy_models,
        "market_epochs": len(epochs),
        "provider_roles": len(roles),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(
            float(row["task_quote_cap_usd"]) for row in assignments
        ),
        "preflight_only": True,
        "claims": dict(protocol["claims"]),
        "claim_boundary": (
            "Finite-range owned eligible-menu exposure only; asymptotic limits, "
            "market-wide adaptation, provider cost, full welfare, algorithms, "
            "communication, and collusion are not identified."
        ),
        "design": design_summary,
    }
    manifest = plan_manifest(candidates, assignments, summary)
    bundle = {
        "format": "orcap-information-congestion-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "market_epochs": epochs,
        "provider_roles": roles,
        "summary": summary,
        "manifest": manifest,
    }
    bundle["ic_bundle_sha256"] = canonical_bundle_hash(bundle)
    validate_bundle(bundle, config_path=config_path)
    return bundle


def validate_bundle(bundle: dict[str, Any], *, config_path: Path = DEFAULT_CONFIG) -> None:
    protocol, protocol_sha256 = load_protocol(config_path)
    protocol_claim_boundary(protocol)
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    validate_factorial_assignments(bundle["assignments"])
    if str(bundle["summary"]["protocol_sha256"]) != protocol_sha256:
        raise ValueError("information-congestion protocol hash mismatch")
    if bundle.get("ic_bundle_sha256") != canonical_bundle_hash(bundle):
        raise ValueError("information-congestion bundle hash mismatch")
    if any(bool(value) for value in (bundle["summary"].get("claims") or {}).values()):
        raise ValueError("information-congestion claim boundary changed in plan")


def _write_optional(
    rows: list[dict[str, Any]],
    schema: pa.Schema,
    table: str,
    *,
    run_id: str,
    root: Path,
) -> str | None:
    if not rows:
        return None
    dt = dt_partition()
    materialized = pa.Table.from_pylist(
        [row | {"run_ts": run_id, "dt": dt} for row in rows], schema=schema
    )
    return str(write_partition(materialized, table, run_id, dt, root))


def write_plan_bundle(
    bundle: dict[str, Any],
    *,
    bundle_path: Path,
    curated_dir: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    validate_bundle(bundle, config_path=config_path)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    run_id = str(bundle["summary"]["run_id"])
    persisted_assignments = [
        row
        | {
            "manifest_sha256": bundle["manifest"]["manifest_sha256"],
            "preflight_only": True,
        }
        for row in bundle["assignments"]
    ]
    run_row = {
        "study_id": bundle["summary"]["study_id"],
        "plan_version": bundle["summary"]["plan_version"],
        "run_id": run_id,
        "created_at": bundle["summary"]["created_at"],
        "protocol_sha256": bundle["summary"]["protocol_sha256"],
        "source_healthy": bundle["summary"]["source_healthy"],
        "models_requested": bundle["summary"]["models_requested"],
        "models_healthy": bundle["summary"]["models_healthy"],
        "market_epochs": bundle["summary"]["market_epochs"],
        "planned_tasks": bundle["summary"]["planned_tasks"],
        "planned_quote_cap_usd": bundle["summary"]["planned_quote_cap_usd"],
        "payload_retained": False,
    }
    return {
        "bundle_path": str(bundle_path),
        "run_ledger_path": _write_optional(
            [run_row], IC_RUN_SCHEMA, "ic_run_ledger", run_id=run_id, root=curated_dir
        ),
        "market_epoch_path": _write_optional(
            bundle["market_epochs"],
            IC_MARKET_EPOCH_SCHEMA,
            "ic_market_epochs",
            run_id=run_id,
            root=curated_dir,
        ),
        "provider_role_path": _write_optional(
            bundle["provider_roles"],
            IC_PROVIDER_ROLE_SCHEMA,
            "ic_provider_roles",
            run_id=run_id,
            root=curated_dir,
        ),
        "candidate_path": _write_optional(
            bundle["candidates"],
            IC_CANDIDATE_SCHEMA,
            "ic_candidates",
            run_id=run_id,
            root=curated_dir,
        ),
        "assignment_path": _write_optional(
            persisted_assignments,
            IC_ASSIGNMENT_SCHEMA,
            "ic_assignments",
            run_id=run_id,
            root=curated_dir,
        ),
    }


def execute_ic_bundle(
    bundle: dict[str, Any],
    *,
    data_root: Path,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    validate_bundle(bundle, config_path=config_path)
    result = execute_bundle(bundle, curated_dir=data_root / "curated", data_root=data_root)
    attempts_path = result.get("attempts_path")
    dedicated = None
    if attempts_path and Path(attempts_path).is_file():
        table = pq.ParquetFile(attempts_path).read()
        frame = table.to_pandas()
        study_id = str(bundle["summary"]["study_id"])
        frame = frame[frame["study_id"].astype(str).eq(study_id)]
        if not frame.empty:
            dedicated = write_partition(
                pa.Table.from_pandas(frame, schema=table.schema, preserve_index=False),
                "ic_attempts",
                str(bundle["summary"]["run_id"]),
                dt_partition(),
                data_root / "curated",
            )
    return result | {"dedicated_attempts_path": str(dedicated) if dedicated else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--data-root", type=Path, default=DATA_DIR)
    plan.add_argument("--output-root", type=Path)
    plan.add_argument("--bundle", type=Path, default=Path("information-congestion-plan.json"))
    plan.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    execute = commands.add_parser("execute")
    execute.add_argument("--data-root", type=Path, default=DATA_DIR)
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    validate = commands.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_IC_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_IC_SEED", secrets.randbits(64)))
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
            config_path=args.config,
        )
        print(json.dumps(bundle["summary"] | bundle["manifest"] | paths, indent=2))
    elif args.command == "execute":
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        print(
            json.dumps(
                execute_ic_bundle(bundle, data_root=args.data_root, config_path=args.config),
                indent=2,
            )
        )
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_bundle(bundle, config_path=args.config)
        if args.require_tasks and not bundle["assignments"]:
            raise RuntimeError("validated information-congestion plan contains no tasks")
        print(
            json.dumps(
                {
                    "protocol_sha256": bundle["summary"]["protocol_sha256"],
                    "ic_bundle_sha256": bundle["ic_bundle_sha256"],
                    "source_healthy": bundle["summary"]["source_healthy"],
                    "planned_tasks": len(bundle["assignments"]),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
