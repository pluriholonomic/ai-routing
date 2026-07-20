"""Detect public quote events and freeze due paid-wave assignments."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .capture_api import write_partition
from .capture_price_response import execute_bundle, freeze_candidates
from .capture_route_calibration import REQUEST_TIMEOUT_SECONDS, SHAPES
from .config import DATA_DIR, dt_partition, run_timestamp
from .price_events import (
    PRICE_EVENT_SCHEMA,
    PRICE_EVENT_WAVE_SCHEMA,
    build_wave_plan,
    detect_price_events,
    wave_status,
)
from .price_experiments import (
    EVENT_STUDY_ID,
    PLAN_VERSION,
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
    broad_cap,
    collapse_provider_candidates,
    plan_manifest,
    provider_key,
    sha256_json,
    validate_manifest,
)

DEFAULT_MAX_TASKS = 24


def event_manifest(
    events: list[dict[str, Any]],
    waves: list[dict[str, Any]],
    price_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Hash event timing separately from the generic price-plan manifest."""
    manifest = {
        "event_registry_sha256": sha256_json(events),
        "wave_plans_sha256": sha256_json(waves),
        "price_manifest_sha256": str(price_manifest["manifest_sha256"]),
        "event_rows": len(events),
        "wave_rows": len(waves),
    }
    manifest["event_manifest_sha256"] = sha256_json(manifest)
    return manifest


def validate_event_bundle(bundle: dict[str, Any]) -> None:
    validate_manifest(
        bundle["manifest"],
        bundle["candidates"],
        bundle["assignments"],
        bundle["summary"],
    )
    expected = event_manifest(bundle["event_registry"], bundle["wave_plans"], bundle["manifest"])
    if bundle.get("event_manifest") != expected:
        raise ValueError("price-event timing manifest mismatch")


def _read(root: Path, layer: str, name: str) -> pd.DataFrame:
    frames = []
    for path in sorted((root / layer / name).glob("dt=*/*.parquet")):
        try:
            frames.append(pq.ParquetFile(path).read().to_pandas())
        except (OSError, pa.ArrowInvalid):
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def recent_public_menus(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    frame = _read(root, "curated", "endpoints_snapshots")
    if frame.empty or frame["run_ts"].nunique() < 2:
        raise RuntimeError("two public endpoint snapshots are required")
    runs = sorted(frame["run_ts"].dropna().astype(str).unique())[-2:]

    def rows(run_id: str) -> list[dict[str, Any]]:
        subset = frame[frame["run_ts"].astype(str).eq(run_id)]
        return [
            {
                "model_id": row.get("model_id"),
                "provider_name": row.get("provider_name"),
                "endpoint_tag": row.get("tag"),
                "prompt_price_per_token": row.get("price_prompt"),
                "completion_price_per_token": row.get("price_completion"),
            }
            for row in subset.to_dict("records")
        ]

    return rows(runs[0]), rows(runs[1]), runs[1]


def _parse_run(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def _task_cap(assignment: dict[str, Any]) -> float:
    return (
        float(assignment["max_price_prompt_per_mtok"]) / 1_000_000 * 96
        + float(assignment["max_price_completion_per_mtok"]) / 1_000_000 * 8
    )


def _wave_assignments(
    wave_rows: list[dict[str, Any]], candidates: list[dict[str, Any]], *, seed: int
) -> list[dict[str, Any]]:
    assignments = []
    by_block = {str(row["block_id"]): [] for row in candidates}
    for row in candidates:
        by_block[str(row["block_id"])].append(row)
    for (event_id, wave_id), group_frame in pd.DataFrame(wave_rows).groupby(
        ["event_id", "wave_id"], sort=True
    ):
        group = group_frame.to_dict("records")
        model_id = str(group[0]["model_id"])
        block_id = f"{EVENT_STUDY_ID}|{event_id}|{wave_id}|{model_id}|short_chat"
        menu = by_block.get(block_id, [])
        collapsed = collapse_provider_candidates(menu)
        if len(collapsed) < 2:
            continue
        cap = broad_cap(menu)
        moving = provider_key(group[0]["moving_provider"])
        pin = next((row for row in collapsed if row["provider_key"] == moving), None)
        for order, planned in enumerate(group):
            arm = str(planned["arm"])
            if arm == "moving_provider_pin" and pin is None:
                continue
            assignment = {
                "study_id": EVENT_STUDY_ID,
                "plan_version": PLAN_VERSION,
                "run_id": str(candidates[0]["run_id"]),
                "event_id": str(event_id),
                "wave_id": str(wave_id),
                "block_id": block_id,
                "task_id": planned["task_id"],
                "model_id": model_id,
                "shape_id": "short_chat",
                "policy": arm,
                "replicate_index": order,
                "policy_order": order,
                "requested_provider": (
                    pin.get("provider_name") if pin and arm.endswith("pin") else None
                ),
                "requested_endpoint_tag": (
                    pin.get("endpoint_tag") if pin and arm.endswith("pin") else None
                ),
                "provider_order_tags": (
                    [str(pin["endpoint_tag"])] if pin and arm.endswith("pin") else None
                ),
                "provider_only_tags": (
                    [str(pin["endpoint_tag"])] if pin and arm.endswith("pin") else None
                ),
                "provider_sort": "price" if arm == "sort_price" else None,
                "allow_fallbacks": arm != "moving_provider_pin",
                "max_price_prompt_per_mtok": float(cap["prompt_per_mtok"]),
                "max_price_completion_per_mtok": float(cap["completion_per_mtok"]),
                "conservative_input_tokens": 96,
                "max_output_tokens": 8,
                "session_group": f"fresh|{planned['task_id']}",
                "assignment_seed": str(seed),
                "payload_retained": False,
            }
            assignment["task_quote_cap_usd"] = _task_cap(assignment)
            assignments.append(assignment)
    return assignments


def _freeze_due_waves(
    client: httpx.Client,
    wave_rows: list[dict[str, Any]],
    *,
    data_root: Path,
    run_id: str,
    seed: int,
    now: datetime,
    max_tasks: int,
    wave_id: str | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    ledger = _read(data_root, "curated", "paid_spend_ledger")
    attempted = set(ledger.get("task_id", pd.Series(dtype=str)).dropna().astype(str))
    due = [
        row
        for row in wave_rows
        if str(row.get("task_id")) not in attempted
        and (wave_id is None or str(row.get("wave_id")) == wave_id)
        and wave_status(row, now=now) == "due"
    ][:max_tasks]
    candidates: list[dict[str, Any]] = []
    failures: list[str] = []
    for (event_id, selected_wave, model_id), _ in (
        pd.DataFrame(due).groupby(["event_id", "wave_id", "model_id"], sort=True) if due else []
    ):
        frozen, block_failures = freeze_candidates(
            client,
            run_id=run_id,
            seed=seed,
            models=(str(model_id),),
            shapes=(next(shape for shape in SHAPES if shape.shape_id == "short_chat"),),
        )
        failures.extend(
            f"{event_id}|{selected_wave}|{model_id}|{failure}" for failure in block_failures
        )
        block_id = f"{EVENT_STUDY_ID}|{event_id}|{selected_wave}|{model_id}|short_chat"
        for row in frozen:
            row.update({"study_id": EVENT_STUDY_ID, "block_id": block_id})
        candidates.extend(frozen)
    assignments = _wave_assignments(due, candidates, seed=seed) if due else []
    return due, candidates, assignments, failures


def build_event_bundle(
    client: httpx.Client,
    *,
    data_root: Path,
    run_id: str,
    seed: int,
    now: datetime | None = None,
    max_tasks: int = DEFAULT_MAX_TASKS,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        previous, current, detected_at = recent_public_menus(data_root)
    except (KeyError, RuntimeError, ValueError) as exc:
        summary = {
            "study_id": EVENT_STUDY_ID,
            "plan_version": PLAN_VERSION,
            "run_id": run_id,
            "seed": str(seed),
            "source_healthy": False,
            "event_detection_source_healthy": False,
            "execution_menu_source_healthy": False,
            "source_failures": [f"public_menu_unavailable:{type(exc).__name__}"],
            "source_snapshot_run": None,
            "new_events": 0,
            "new_wave_rows": 0,
            "due_wave_tasks": 0,
            "planned_tasks": 0,
            "planned_quote_cap_usd": 0.0,
            "preflight_only": True,
            "claim_boundary": (
                "No paid task is issued without two valid public endpoint snapshots."
            ),
        }
        manifest = plan_manifest([], [], summary)
        bundle = {
            "format": "orcap-price-event-plan-v1",
            "candidates": [],
            "assignments": [],
            "event_registry": [],
            "wave_plans": [],
            "summary": summary,
            "manifest": manifest,
        }
        bundle["event_manifest"] = event_manifest([], [], manifest)
        return bundle
    source_healthy = now - _parse_run(detected_at) <= timedelta(minutes=30)
    new_events = detect_price_events(
        previous,
        current,
        detected_at=detected_at,
        source_healthy=source_healthy,
    )
    new_waves = [row for event in new_events for row in build_wave_plan(event, seed=seed)]
    existing_waves = _read(data_root, "curated", "price_event_wave_plans")
    all_waves = existing_waves.to_dict("records") + new_waves
    due, candidates, assignments, menu_failures = _freeze_due_waves(
        client,
        all_waves,
        data_root=data_root,
        run_id=run_id,
        seed=seed,
        now=now,
        max_tasks=max_tasks,
    )
    execution_source_healthy = not menu_failures
    summary = {
        "study_id": EVENT_STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "source_healthy": bool(execution_source_healthy if due else source_healthy),
        "event_detection_source_healthy": bool(source_healthy),
        "execution_menu_source_healthy": bool(execution_source_healthy),
        "source_failures": menu_failures,
        "source_snapshot_run": detected_at,
        "new_events": len(new_events),
        "new_wave_rows": len(new_waves),
        "due_wave_tasks": len(due),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(float(row["task_quote_cap_usd"]) for row in assignments),
        "preflight_only": True,
        "claim_boundary": (
            "Public quote events and owned requests only; no private order flow or intent."
        ),
    }
    manifest = plan_manifest(candidates, assignments, summary)
    bundle = {
        "format": "orcap-price-event-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "event_registry": new_events,
        "wave_plans": new_waves,
        "summary": summary,
        "manifest": manifest,
    }
    bundle["event_manifest"] = event_manifest(new_events, new_waves, manifest)
    return bundle


def build_recovery_bundle(
    client: httpx.Client,
    source_bundle: dict[str, Any],
    *,
    data_root: Path,
    run_id: str,
    seed: int,
    wave_id: str,
    now: datetime | None = None,
    max_tasks: int = DEFAULT_MAX_TASKS,
) -> dict[str, Any]:
    """Freeze a contemporaneous menu for one already-preregistered wave."""
    validate_event_bundle(source_bundle)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    source_waves = list(source_bundle["wave_plans"])
    due, candidates, assignments, menu_failures = _freeze_due_waves(
        client,
        source_waves,
        data_root=data_root,
        run_id=run_id,
        seed=seed,
        now=now,
        max_tasks=max_tasks,
        wave_id=wave_id,
    )
    summary = {
        "study_id": EVENT_STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "recovery_wave_id": wave_id,
        "source_event_manifest_sha256": source_bundle["event_manifest"]["event_manifest_sha256"],
        "source_healthy": not menu_failures,
        "event_detection_source_healthy": None,
        "execution_menu_source_healthy": not menu_failures,
        "source_failures": menu_failures,
        "new_events": 0,
        "new_wave_rows": 0,
        "due_wave_tasks": len(due),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(float(row["task_quote_cap_usd"]) for row in assignments),
        "preflight_only": True,
        "claim_boundary": (
            "Public quote events and owned requests only; no private order flow or intent."
        ),
    }
    manifest = plan_manifest(candidates, assignments, summary)
    bundle = {
        "format": "orcap-price-event-recovery-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "event_registry": [],
        "wave_plans": [],
        "summary": summary,
        "manifest": manifest,
    }
    bundle["event_manifest"] = event_manifest([], [], manifest)
    return bundle


def wait_for_wave(
    source_bundle: dict[str, Any],
    wave_id: str,
    *,
    now: datetime | None = None,
    max_wait_seconds: int,
    sleeper: Any = time.sleep,
) -> float:
    """Wait until the latest target in a wave, bounded before any API call."""
    validate_event_bundle(source_bundle)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    targets = [
        datetime.fromisoformat(str(row["target_at"]).replace("Z", "+00:00"))
        for row in source_bundle["wave_plans"]
        if str(row.get("wave_id")) == wave_id
    ]
    if not targets:
        return 0.0
    seconds = max(0.0, (max(targets) - now).total_seconds())
    if seconds > max_wait_seconds:
        raise RuntimeError(f"wave {wave_id} target is {seconds:.0f}s away, beyond wait cap")
    if seconds:
        sleeper(seconds)
    return seconds


def _write_optional(
    rows: list[dict[str, Any]], schema: pa.Schema, name: str, *, run_id: str, root: Path
) -> str | None:
    if not rows:
        return None
    dt = dt_partition()
    table = pa.Table.from_pylist(
        [row | {"run_ts": run_id, "dt": dt} for row in rows], schema=schema
    )
    return str(write_partition(table, name, run_id, dt, root))


def write_event_bundle(
    bundle: dict[str, Any], *, bundle_path: Path, curated_dir: Path
) -> dict[str, Any]:
    validate_event_bundle(bundle)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    run_id = str(bundle["summary"]["run_id"])
    return {
        "bundle_path": str(bundle_path),
        "event_path": _write_optional(
            bundle["event_registry"],
            PRICE_EVENT_SCHEMA,
            "price_event_registry",
            run_id=run_id,
            root=curated_dir,
        ),
        "wave_path": _write_optional(
            bundle["wave_plans"],
            PRICE_EVENT_WAVE_SCHEMA,
            "price_event_wave_plans",
            run_id=run_id,
            root=curated_dir,
        ),
        "candidate_path": _write_optional(
            bundle["candidates"],
            PRICE_RESPONSE_CANDIDATE_SCHEMA,
            "price_event_candidates",
            run_id=run_id,
            root=curated_dir,
        ),
        "assignment_path": _write_optional(
            [
                row
                | {
                    "manifest_sha256": bundle["manifest"]["manifest_sha256"],
                    "preflight_only": True,
                }
                for row in bundle["assignments"]
            ],
            PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
            "price_event_assignments",
            run_id=run_id,
            root=curated_dir,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--data-root", type=Path, default=DATA_DIR)
    plan.add_argument("--output-root", type=Path)
    plan.add_argument("--bundle", type=Path, default=Path("price-event-plan.json"))
    plan.add_argument("--max-tasks", type=int, default=DEFAULT_MAX_TASKS)
    recover = sub.add_parser("recover")
    recover.add_argument("--data-root", type=Path, default=DATA_DIR)
    recover.add_argument("--output-root", type=Path)
    recover.add_argument("--source-bundle", type=Path, required=True)
    recover.add_argument("--bundle", type=Path, required=True)
    recover.add_argument("--wave-id", choices=("w1", "w2", "w3", "w4"), required=True)
    recover.add_argument("--max-tasks", type=int, default=DEFAULT_MAX_TASKS)
    recover.add_argument("--wait", action="store_true")
    recover.add_argument("--max-wait-seconds", type=int, default=3_600)
    execute = sub.add_parser("execute")
    execute.add_argument("--data-root", type=Path, default=DATA_DIR)
    execute.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.command in {"plan", "recover"}:
        run_id = os.environ.get("ORCAP_PRICE_EVENT_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_PRICE_EVENT_SEED", secrets.randbits(64)))
        source_bundle = None
        if args.command == "recover":
            source_bundle = json.loads(args.source_bundle.read_text(encoding="utf-8"))
            if args.wait:
                wait_for_wave(
                    source_bundle,
                    args.wave_id,
                    max_wait_seconds=args.max_wait_seconds,
                )
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = (
                build_event_bundle(
                    client,
                    data_root=args.data_root,
                    run_id=run_id,
                    seed=seed,
                    max_tasks=args.max_tasks,
                )
                if args.command == "plan"
                else build_recovery_bundle(
                    client,
                    source_bundle,
                    data_root=args.data_root,
                    run_id=run_id,
                    seed=seed,
                    wave_id=args.wave_id,
                    max_tasks=args.max_tasks,
                )
            )
        paths = write_event_bundle(
            bundle,
            bundle_path=args.bundle,
            curated_dir=(args.output_root or args.data_root) / "curated",
        )
        print(json.dumps(bundle["summary"] | bundle["manifest"] | paths, indent=2))
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_event_bundle(bundle)
        print(
            json.dumps(
                execute_bundle(
                    bundle,
                    curated_dir=args.data_root / "curated",
                    data_root=args.data_root,
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
