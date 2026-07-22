"""Plan-first live capture for the GLM-5.2 market-share HMP experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .capture_api import write_partition
from .capture_price_response import (
    execute_bundle,
    freeze_candidates,
)
from .capture_route_calibration import REQUEST_TIMEOUT_SECONDS, SHAPES
from .config import DATA_DIR, dt_partition, run_timestamp
from .market_share_hmp import (
    EVENT_SCHEMA,
    INPUT_TOKENS,
    MODEL_ID,
    OUTPUT_TOKENS,
    PLAN_VERSION,
    STUDY_ID,
    WAVE_SCHEMA,
    build_paid_assignments,
    build_wave_plans,
    detect_events,
    parse_time,
    routing_shares,
    wave_status,
)
from .price_experiments import (
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
    plan_manifest,
    provider_key,
    sha256_json,
    validate_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "glm52_market_share_hmp_v1.toml"
HMP_ASSIGNMENT_SCHEMA = (
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA.append(pa.field("event_id", pa.string()))
    .append(pa.field("wave_id", pa.string()))
    .append(pa.field("protocol_sha256", pa.string()))
)
RUN_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("run_id", pa.string()),
        ("created_at", pa.string()),
        ("protocol_sha256", pa.string()),
        ("source_healthy", pa.bool_()),
        ("new_events", pa.int32()),
        ("new_wave_rows", pa.int32()),
        ("due_waves", pa.int32()),
        ("planned_tasks", pa.int32()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)
PUBLIC_PANEL_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("model_id", pa.string()),
        ("source_run_ts", pa.string()),
        ("captured_at", pa.string()),
        ("provider_name", pa.string()),
        ("provider_key", pa.string()),
        ("provider_group", pa.string()),
        ("request_quote_usd", pa.float64()),
        ("relative_to_author", pa.float64()),
        ("price_only_shadow_share", pa.float64()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def _read(root: Path, name: str) -> pd.DataFrame:
    frames = []
    for path in sorted((root / "curated" / name).glob("dt=*/*.parquet")):
        try:
            frames.append(pq.ParquetFile(path).read().to_pandas())
        except (OSError, pa.ArrowInvalid):
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _protocol(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    return tomllib.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def _manifest(
    *,
    protocol_sha256: str,
    events: list[dict[str, Any]],
    waves: list[dict[str, Any]],
    public_panel: list[dict[str, Any]],
    price_manifest: dict[str, Any],
) -> dict[str, Any]:
    output = {
        "protocol_sha256": protocol_sha256,
        "event_registry_sha256": sha256_json(events),
        "wave_plans_sha256": sha256_json(waves),
        "public_panel_sha256": sha256_json(public_panel),
        "price_manifest_sha256": str(price_manifest["manifest_sha256"]),
        "event_rows": len(events),
        "wave_rows": len(waves),
        "public_panel_rows": len(public_panel),
    }
    output["hmp_manifest_sha256"] = sha256_json(output)
    return output


def validate_bundle(bundle: dict[str, Any]) -> None:
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    expected = _manifest(
        protocol_sha256=str(bundle["summary"]["protocol_sha256"]),
        events=list(bundle["event_registry"]),
        waves=list(bundle["wave_plans"]),
        public_panel=list(bundle["public_panel"]),
        price_manifest=bundle["manifest"],
    )
    if bundle.get("hmp_manifest") != expected:
        raise ValueError("market-share HMP event or wave manifest mismatch")
    claims = bundle["summary"].get("claims") or {}
    if any(bool(claims.get(key)) for key in claims):
        raise ValueError("non-identification claim boundary changed in paid plan")


def _snapshot_fresh(frame: pd.DataFrame, *, now: datetime) -> bool:
    if frame.empty or "run_ts" not in frame:
        return False
    if "model_id" in frame:
        frame = frame[frame["model_id"].astype(str).eq(MODEL_ID)]
        if frame.empty:
            return False
    try:
        latest = max(parse_time(value) for value in frame["run_ts"].dropna().astype(str))
    except ValueError:
        return False
    return now - latest <= timedelta(minutes=30)


def _existing_tasks(spend: pd.DataFrame, assignments: pd.DataFrame) -> set[str]:
    """Return attempted or already reserved tasks.

    A plan uploaded before execution is an at-most-once reservation. If its
    runner dies after assignment upload, that task is missing rather than
    silently retried and charged twice.
    """
    output: set[str] = set()
    for frame in (spend, assignments):
        if frame.empty or "task_id" not in frame:
            continue
        selected = frame
        if "study_id" in selected:
            selected = selected[selected["study_id"].astype(str).eq(STUDY_ID)]
        output.update(selected["task_id"].dropna().astype(str))
    return output


def _dedupe_records(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    output: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        output[tuple(str(row.get(key) or "") for key in keys)] = row
    return list(output.values())


def _event_state_hash(row: dict[str, Any]) -> str:
    state = {
        key: row.get(key)
        for key in (
            "event_id",
            "event_status",
            "finalized_at",
            "multiplicity",
            "co_cutters",
            "co_cutter_count",
            "co_cutter_share_mass",
            "co_cutter_exposure",
            "preliminary_eligible",
            "contamination_window_complete",
            "clean_event",
            "exclusion_reason",
        )
    }
    co = state.get("co_cutters")
    if hasattr(co, "tolist"):
        state["co_cutters"] = co.tolist()
    return sha256_json(state)


def _public_shadow_rows(snapshots: pd.DataFrame, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    required = {"run_ts", "model_id", "provider_name", "price_prompt", "price_completion"}
    if snapshots.empty or not required.issubset(snapshots.columns):
        return []
    frame = snapshots[snapshots["model_id"].astype(str).eq(MODEL_ID)].copy()
    if frame.empty:
        return []
    for column in ("price_prompt", "price_completion", "price_request"):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["request_quote_usd"] = (
        frame["price_prompt"] * INPUT_TOKENS
        + frame["price_completion"] * OUTPUT_TOKENS
        + frame["price_request"]
    )
    frame = frame[frame["request_quote_usd"].gt(0)].copy()
    frame["provider_key"] = frame["provider_name"].map(provider_key)
    frame = frame.sort_values(
        ["run_ts", "provider_key", "request_quote_usd"], kind="stable"
    ).drop_duplicates(["run_ts", "provider_key"], keep="first")
    active = {provider_key(item) for item in protocol["providers"]["active"]}
    anchors = {provider_key(item) for item in protocol["providers"]["anchors"]}
    authors = {provider_key(item) for item in protocol["providers"]["author"]}
    rows = []
    for source_run, group in frame.groupby("run_ts", sort=False):
        shares = routing_shares(
            group["request_quote_usd"].to_numpy(dtype=float),
            eta=float(protocol["study"]["frozen_eta"]),
        )
        author_quotes = group.loc[group["provider_key"].isin(authors), "request_quote_usd"]
        author_quote = float(author_quotes.median()) if len(author_quotes) else np.nan
        for position, row in enumerate(group.to_dict("records")):
            key = str(row["provider_key"])
            provider_group = (
                "active"
                if key in active
                else "anchor"
                if key in anchors
                else "author"
                if key in authors
                else "other"
            )
            quote = float(row["request_quote_usd"])
            rows.append(
                {
                    "study_id": STUDY_ID,
                    "model_id": MODEL_ID,
                    "source_run_ts": str(source_run),
                    "captured_at": parse_time(source_run).isoformat(),
                    "provider_name": str(row["provider_name"]),
                    "provider_key": key,
                    "provider_group": provider_group,
                    "request_quote_usd": quote,
                    "relative_to_author": quote / author_quote
                    if np.isfinite(author_quote) and author_quote > 0
                    else None,
                    "price_only_shadow_share": float(shares[position]),
                    "payload_retained": False,
                }
            )
    return rows


def _background_wave(
    now: datetime,
    *,
    protocol: dict[str, Any],
    seed: int,
    available_providers: set[str],
) -> dict[str, Any] | None:
    background = protocol.get("background") or {}
    if not bool(background.get("enabled")):
        return None
    cadence = int(background["cadence_minutes"])
    epoch_minutes = int(now.timestamp() // 60)
    bucket_minutes = epoch_minutes - epoch_minutes % cadence
    bucket = datetime.fromtimestamp(bucket_minutes * 60, tz=UTC)
    active = [
        provider
        for provider in protocol["providers"]["active"]
        if provider_key(provider) in available_providers
    ]
    if not active:
        return None
    focal = active[(bucket_minutes // cadence) % len(active)]
    event_id = f"mshmp-background-{bucket.strftime('%Y%m%dT%H%MZ')}"
    return {
        "event_id": event_id,
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "wave_id": "background",
        "target_at": bucket.isoformat().replace("+00:00", "Z"),
        "latest_at": (bucket + timedelta(minutes=int(background["latest_offset_minutes"])))
        .isoformat()
        .replace("+00:00", "Z"),
        "model_id": MODEL_ID,
        "focal_provider": focal,
        "multiplicity": "background",
        "co_cutters": [],
        "assignment_seed": str(seed),
        "event_sha256": sha256_json(
            {"event_id": event_id, "protocol_sha256": protocol["study"]["study_id"]}
        ),
        "payload_retained": False,
    }


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
    protocol, protocol_sha256 = _protocol(config_path)
    study = protocol["study"]
    event_config = protocol["events"]
    providers = protocol["providers"]
    support = protocol["support"]
    snapshots = _read(data_root, "endpoints_snapshots")
    enforcement = _read(data_root, "congestion_intraday")
    source_fresh = _snapshot_fresh(snapshots, now=now)
    detected = detect_events(
        snapshots,
        active_providers=providers["active"],
        author_providers=providers["author"],
        eta=float(study["frozen_eta"]),
        minimum_cut_fraction=float(event_config["minimum_cut_fraction"]),
        comove_window_minutes=int(event_config["comove_window_minutes"]),
        maximum_snapshot_gap_minutes=int(event_config["maximum_snapshot_gap_minutes"]),
        minimum_post_captures=int(event_config["minimum_post_captures"]),
        minimum_unchanged_pre_captures=int(event_config["minimum_unchanged_pre_captures"]),
        contamination_window_minutes=int(event_config["contamination_window_minutes"]),
        enforcement=enforcement,
        minimum_rate_limit_spike_count=int(event_config["minimum_rate_limit_spike_count"]),
        maximum_rate_limit_incidence=float(event_config["maximum_rate_limit_incidence"]),
        minimum_derankable_error_count=int(event_config["minimum_derankable_error_count"]),
        maximum_capacity_ceiling_change_fraction=float(
            event_config["maximum_capacity_ceiling_change_fraction"]
        ),
        now=now,
    )
    prospective = parse_time(study["prospective_start_utc"])
    detected = [row for row in detected if parse_time(row["detected_at"]) >= prospective]
    existing_public = _read(data_root, "glm52_hmp_public_panel")
    existing_source_runs = (
        set(existing_public["source_run_ts"].dropna().astype(str))
        if not existing_public.empty and "source_run_ts" in existing_public
        else set()
    )
    public_panel = [
        row
        for row in _public_shadow_rows(snapshots, protocol)
        if row["source_run_ts"] not in existing_source_runs
        and parse_time(row["captured_at"]) >= prospective
    ]
    existing_events = _read(data_root, "glm52_hmp_events")
    existing_states: dict[str, str] = {}
    if not existing_events.empty and "event_id" in existing_events:
        event_order = existing_events.copy()
        event_order["_row_order"] = range(len(event_order))
        priority = {"provisional": 0, "multiplicity_finalized": 1, "final": 2}
        event_order["_status_priority"] = (
            event_order.get("event_status", pd.Series("final", index=event_order.index))
            .map(priority)
            .fillna(0)
        )
        event_order = event_order.sort_values(
            ["event_id", "_status_priority", "_row_order"], kind="stable"
        )
        for row in event_order.to_dict("records"):
            existing_states[str(row["event_id"])] = _event_state_hash(row)
    new_events = [
        row
        for row in detected
        if existing_states.get(str(row["event_id"])) != _event_state_hash(row)
    ]
    proposed_waves = build_wave_plans(
        new_events,
        offsets_minutes=event_config["waves_minutes"],
        tolerances_minutes=event_config["wave_tolerance_minutes"],
        seed=seed,
    )
    prior_waves = _read(data_root, "glm52_hmp_wave_plans")
    prior_wave_keys = (
        set(
            zip(
                prior_waves["event_id"].astype(str),
                prior_waves["wave_id"].astype(str),
                strict=True,
            )
        )
        if not prior_waves.empty
        else set()
    )
    new_waves = [
        row
        for row in proposed_waves
        if (str(row["event_id"]), str(row["wave_id"])) not in prior_wave_keys
    ]
    available = set()
    if not snapshots.empty and {"model_id", "provider_name"}.issubset(snapshots.columns):
        available = set(
            snapshots.loc[snapshots["model_id"].astype(str).eq(MODEL_ID), "provider_name"].map(
                provider_key
            )
        )
    background_wave = _background_wave(
        now,
        protocol=protocol,
        seed=seed,
        available_providers=available,
    )
    if (
        background_wave is not None
        and now >= prospective
        and now <= parse_time(study["campaign_end_utc"])
        and (
            str(background_wave["event_id"]),
            str(background_wave["wave_id"]),
        )
        not in prior_wave_keys
    ):
        new_waves.append(background_wave)
    all_waves = prior_waves.to_dict("records") if not prior_waves.empty else []
    all_waves = _dedupe_records(all_waves + new_waves, ("event_id", "wave_id"))
    spend = _read(data_root, "paid_spend_ledger")
    prior_assignments = _read(data_root, "glm52_hmp_assignments")
    spent_tasks = _existing_tasks(spend, prior_assignments)
    due_waves = []
    for wave in all_waves:
        replicates = int(
            protocol["background"]["replicates_per_arm"]
            if str(wave.get("multiplicity")) == "background"
            else event_config["replicates_per_arm"]
        )
        expected_tasks = len(protocol["arms"]["names"]) * replicates
        prefix = f"{STUDY_ID}|{wave['event_id']}|{wave['wave_id']}|"
        completed = sum(task.startswith(prefix) for task in spent_tasks)
        if completed < expected_tasks and wave_status(wave, now=now) == "due":
            due_waves.append(wave)
    due_waves.sort(
        key=lambda row: (
            str(row.get("multiplicity")) == "background",
            row["target_at"],
            row["event_id"],
            row["wave_id"],
        )
    )
    selected_wave = due_waves[0] if due_waves else None

    candidates: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    selected_is_background = bool(
        selected_wave is not None and str(selected_wave.get("multiplicity")) == "background"
    )
    # A natural event needs a fresh historical snapshot for event-time state.
    # A background block freezes its exact live menu below, so an older public
    # panel is diagnostic rather than a reason to discard an otherwise current
    # randomized menu measurement.
    public_context_healthy = bool(source_fresh or selected_is_background)
    source_failures: list[Any] = (
        []
        if public_context_healthy
        else [{"model_id": MODEL_ID, "reason": "stale_public_snapshot"}]
    )
    assignment_details: dict[str, Any] = {}
    if selected_wave is not None and public_context_healthy:
        replicates = int(
            protocol["background"]["replicates_per_arm"]
            if str(selected_wave.get("multiplicity")) == "background"
            else event_config["replicates_per_arm"]
        )
        shape = next(item for item in SHAPES if item.shape_id == "short_chat")
        candidates, source_failures = freeze_candidates(
            client,
            run_id=run_id,
            seed=seed,
            models=(MODEL_ID,),
            shapes=(shape,),
        )
        block_id = (
            f"{STUDY_ID}|{selected_wave['event_id']}|{selected_wave['wave_id']}|"
            f"{MODEL_ID}|short_chat"
        )
        for row in candidates:
            row.update(
                {
                    "study_id": STUDY_ID,
                    "plan_version": PLAN_VERSION,
                    "block_id": block_id,
                }
            )
        assignments, assignment_details = build_paid_assignments(
            candidates,
            selected_wave,
            active_providers=providers["active"],
            anchor_providers=providers["anchors"],
            replicates_per_arm=replicates,
            run_id=run_id,
            seed=seed,
        )
        for assignment in assignments:
            assignment["protocol_sha256"] = protocol_sha256
        assignments = [row for row in assignments if row["task_id"] not in spent_tasks]
    source_healthy = bool(public_context_healthy and not source_failures)
    summary = {
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "protocol_sha256": protocol_sha256,
        "created_at": now.isoformat(),
        "source_healthy": source_healthy,
        "public_snapshot_fresh": source_fresh,
        "source_failures": source_failures,
        "new_events": len(new_events),
        "new_clean_events": sum(bool(row["clean_event"]) for row in new_events),
        "new_provisional_events": sum(
            str(row.get("event_status")) == "provisional" for row in new_events
        ),
        "new_wave_rows": len(new_waves),
        "new_public_panel_rows": len(public_panel),
        "due_waves": len(due_waves),
        "selected_wave": (
            {key: selected_wave.get(key) for key in ("event_id", "wave_id", "multiplicity")}
            if selected_wave
            else None
        ),
        "assignment_details": assignment_details,
        "planned_blocks": int(bool(assignments)),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(float(row["task_quote_cap_usd"]) for row in assignments),
        "minimum_menu_coverage": float(support["minimum_menu_coverage"]),
        "preflight_only": True,
        "claims": dict(protocol["claims"]),
        "claim_boundary": (
            "Owned randomized menus and public quote events only; no market-wide share, "
            "provider algorithm, cost, communication, intent, or collusion is identified."
        ),
    }
    price_manifest = plan_manifest(candidates, assignments, summary)
    bundle = {
        "format": "orcap-glm52-market-share-hmp-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "event_registry": new_events,
        "wave_plans": new_waves,
        "public_panel": public_panel,
        "summary": summary,
        "manifest": price_manifest,
    }
    bundle["hmp_manifest"] = _manifest(
        protocol_sha256=protocol_sha256,
        events=new_events,
        waves=new_waves,
        public_panel=public_panel,
        price_manifest=price_manifest,
    )
    return bundle


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


def write_plan_bundle(
    bundle: dict[str, Any], *, bundle_path: Path, curated_dir: Path
) -> dict[str, Any]:
    validate_bundle(bundle)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    run_id = str(bundle["summary"]["run_id"])
    return {
        "bundle_path": str(bundle_path),
        "run_ledger_path": _write_optional(
            [
                {
                    "study_id": STUDY_ID,
                    "plan_version": PLAN_VERSION,
                    "run_id": run_id,
                    "created_at": bundle["summary"]["created_at"],
                    "protocol_sha256": bundle["summary"]["protocol_sha256"],
                    "source_healthy": bundle["summary"]["source_healthy"],
                    "new_events": bundle["summary"]["new_events"],
                    "new_wave_rows": bundle["summary"]["new_wave_rows"],
                    "due_waves": bundle["summary"]["due_waves"],
                    "planned_tasks": bundle["summary"]["planned_tasks"],
                    "payload_retained": False,
                }
            ],
            RUN_SCHEMA,
            "glm52_hmp_run_ledger",
            run_id=run_id,
            root=curated_dir,
        ),
        "event_path": _write_optional(
            bundle["event_registry"],
            EVENT_SCHEMA,
            "glm52_hmp_events",
            run_id=run_id,
            root=curated_dir,
        ),
        "wave_path": _write_optional(
            bundle["wave_plans"],
            WAVE_SCHEMA,
            "glm52_hmp_wave_plans",
            run_id=run_id,
            root=curated_dir,
        ),
        "public_panel_path": _write_optional(
            bundle["public_panel"],
            PUBLIC_PANEL_SCHEMA,
            "glm52_hmp_public_panel",
            run_id=run_id,
            root=curated_dir,
        ),
        "candidate_path": _write_optional(
            bundle["candidates"],
            PRICE_RESPONSE_CANDIDATE_SCHEMA,
            "glm52_hmp_candidates",
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
            HMP_ASSIGNMENT_SCHEMA,
            "glm52_hmp_assignments",
            run_id=run_id,
            root=curated_dir,
        ),
    }


def execute_hmp_bundle(bundle: dict[str, Any], *, data_root: Path) -> dict[str, Any]:
    """Execute the generic redacted plan and materialize an isolated HMP attempt table."""
    validate_bundle(bundle)
    result = execute_bundle(
        bundle,
        curated_dir=data_root / "curated",
        data_root=data_root,
    )
    attempts_path = result.get("attempts_path")
    dedicated_path = None
    if attempts_path and Path(attempts_path).is_file():
        table = pq.ParquetFile(attempts_path).read()
        frame = table.to_pandas()
        frame = frame[frame["study_id"].astype(str).eq(STUDY_ID)]
        if not frame.empty:
            run_id = str(bundle["summary"]["run_id"])
            dedicated_path = write_partition(
                pa.Table.from_pandas(frame, schema=table.schema, preserve_index=False),
                "glm52_hmp_attempts",
                run_id,
                dt_partition(),
                data_root / "curated",
            )
    return result | {"dedicated_attempts_path": str(dedicated_path) if dedicated_path else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--data-root", type=Path, default=DATA_DIR)
    plan.add_argument("--output-root", type=Path)
    plan.add_argument("--bundle", type=Path, default=Path("glm52-hmp-plan.json"))
    plan.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    execute = commands.add_parser("execute")
    execute.add_argument("--data-root", type=Path, default=DATA_DIR)
    execute.add_argument("--bundle", type=Path, required=True)
    validate = commands.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_GLM52_HMP_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_GLM52_HMP_SEED", secrets.randbits(64)))
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
        print(json.dumps(execute_hmp_bundle(bundle, data_root=args.data_root), indent=2))
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_bundle(bundle)
        if args.require_tasks and not bundle["assignments"]:
            raise RuntimeError("validated market-share HMP plan contains no executable tasks")
        print(
            json.dumps(
                {
                    "protocol_sha256": bundle["summary"]["protocol_sha256"],
                    "hmp_manifest_sha256": bundle["hmp_manifest"]["hmp_manifest_sha256"],
                    "source_healthy": bundle["summary"]["source_healthy"],
                    "planned_tasks": len(bundle["assignments"]),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
