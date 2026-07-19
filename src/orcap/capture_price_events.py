"""Detect public quote events and freeze due paid-wave assignments."""

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
    validate_manifest,
)

DEFAULT_MAX_TASKS = 24


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
    previous, current, detected_at = recent_public_menus(data_root)
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
    ledger = _read(data_root, "curated", "paid_spend_ledger")
    attempted = set(ledger.get("task_id", pd.Series(dtype=str)).dropna().astype(str))
    due = [
        row
        for row in all_waves
        if str(row.get("task_id")) not in attempted and wave_status(row, now=now) == "due"
    ][:max_tasks]
    candidates = []
    for (event_id, wave_id, model_id), _ in pd.DataFrame(due).groupby(
        ["event_id", "wave_id", "model_id"], sort=True
    ) if due else []:
        frozen, _ = freeze_candidates(
            client,
            run_id=run_id,
            seed=seed,
            models=(str(model_id),),
            shapes=(next(shape for shape in SHAPES if shape.shape_id == "short_chat"),),
        )
        block_id = f"{EVENT_STUDY_ID}|{event_id}|{wave_id}|{model_id}|short_chat"
        for row in frozen:
            row.update({"study_id": EVENT_STUDY_ID, "block_id": block_id})
        candidates.extend(frozen)
    assignments = _wave_assignments(due, candidates, seed=seed) if due else []
    summary = {
        "study_id": EVENT_STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "source_healthy": bool(source_healthy),
        "source_snapshot_run": detected_at,
        "new_events": len(new_events),
        "new_wave_rows": len(new_waves),
        "due_wave_tasks": len(due),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(
            float(row["task_quote_cap_usd"]) for row in assignments
        ),
        "preflight_only": True,
        "claim_boundary": (
            "Public quote events and owned requests only; no private order flow or intent."
        ),
    }
    manifest = plan_manifest(candidates, assignments, summary)
    return {
        "format": "orcap-price-event-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "event_registry": new_events,
        "wave_plans": new_waves,
        "summary": summary,
        "manifest": manifest,
    }


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
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
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
    execute = sub.add_parser("execute")
    execute.add_argument("--data-root", type=Path, default=DATA_DIR)
    execute.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_PRICE_EVENT_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_PRICE_EVENT_SEED", secrets.randbits(64)))
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_event_bundle(
                client,
                data_root=args.data_root,
                run_id=run_id,
                seed=seed,
                max_tasks=args.max_tasks,
            )
        paths = write_event_bundle(
            bundle,
            bundle_path=args.bundle,
            curated_dir=(args.output_root or args.data_root) / "curated",
        )
        print(json.dumps(bundle["summary"] | bundle["manifest"] | paths, indent=2))
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
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
