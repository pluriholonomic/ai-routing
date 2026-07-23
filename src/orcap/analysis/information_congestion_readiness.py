"""Data-lineage and integrity gates for information-congestion v1."""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..information_congestion import (
    DEFAULT_CONFIG,
    load_protocol,
    validate_factorial_assignments,
)


def read_table(root: Path, name: str) -> pd.DataFrame:
    frames = []
    for path in sorted((root / "curated" / name).glob("dt=*/*.parquet")):
        try:
            frames.append(pq.ParquetFile(path).read().to_pandas())
        except (OSError, pa.ArrowInvalid):
            continue
    return deduplicate_exact_rows(
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    )


def deduplicate_exact_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse identical checkpoint copies without hiding conflicting IDs."""
    if frame.empty:
        return frame.copy()
    comparable = frame.copy(deep=False)
    replaced = False
    for column in frame.select_dtypes(include=["object"]).columns:
        sample = frame[column].head(128)
        if any(_is_unhashable(value) for value in sample):
            if not replaced:
                comparable = frame.copy()
                replaced = True
            comparable[column] = frame[column].map(_freeze_unhashable)
    try:
        duplicated = comparable.duplicated(keep="first")
    except TypeError:
        # A sparse list/dict column may not appear in the bounded sample.
        # Canonicalize every object column once, then use pandas' vectorized
        # row hashing instead of serializing millions of scalar rows to JSON.
        comparable = frame.copy()
        for column in frame.select_dtypes(include=["object"]).columns:
            comparable[column] = frame[column].map(_freeze_unhashable)
        duplicated = comparable.duplicated(keep="first")
    return frame.loc[~duplicated].reset_index(drop=True)


@dataclass(frozen=True)
class _FrozenUnhashable:
    value_type: str
    payload: str


def _is_unhashable(value: Any) -> bool:
    try:
        hash(value)
    except TypeError:
        return True
    return False


def _freeze_unhashable(value: Any) -> Any:
    if not _is_unhashable(value):
        return value
    return _FrozenUnhashable(
        value_type=f"{type(value).__module__}.{type(value).__qualname__}",
        payload=json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            allow_nan=True,
        ),
    )


def task_id_from_metadata(value: Any) -> str | None:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    task_id = parsed.get("task_id") if isinstance(parsed, dict) else None
    return str(task_id) if task_id else None


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return []


def capture_continuity(
    snapshots: pd.DataFrame,
    *,
    now: datetime,
    lookback_hours: int = 24,
    intended_minutes: int = 5,
) -> dict[str, Any]:
    if snapshots.empty or "run_ts" not in snapshots:
        return {
            "healthy": False,
            "coverage": 0.0,
            "maximum_gap_minutes": None,
            "observed_snapshots": 0,
            "intended_snapshots": int(lookback_hours * 60 / intended_minutes),
            "reason": "no endpoint snapshots",
        }
    times = pd.to_datetime(
        snapshots["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    ).dropna()
    cutoff = pd.Timestamp(now - timedelta(hours=lookback_hours))
    times = pd.Series(sorted(set(times[times.ge(cutoff)])))
    intended = int(lookback_hours * 60 / intended_minutes)
    observed = len(times)
    coverage = min(1.0, observed / intended) if intended else 0.0
    # Include both lookback boundaries. Otherwise a fresh final observation can
    # conceal a long gap at the beginning of the window (and vice versa).
    boundaries = pd.Series(
        [pd.Timestamp(cutoff), *times.tolist(), pd.Timestamp(now)]
    ).sort_values(ignore_index=True)
    gaps = boundaries.diff().dt.total_seconds().div(60).dropna()
    maximum_gap = float(gaps.max()) if not gaps.empty else None
    return {
        "healthy": observed > 0,
        "coverage": float(coverage),
        "maximum_gap_minutes": maximum_gap,
        "observed_snapshots": observed,
        "intended_snapshots": intended,
        "latest_snapshot": times.max().isoformat() if observed else None,
        "reason": "observed" if observed else "no snapshots in lookback",
    }


def reconciliation(
    assignments: pd.DataFrame,
    attempts: pd.DataFrame,
    spend: pd.DataFrame,
    *,
    study_id: str,
    require_paid: bool,
) -> dict[str, Any]:
    selected_assignments = deduplicate_exact_rows(assignments)
    selected_attempts = deduplicate_exact_rows(attempts)
    selected_spend = deduplicate_exact_rows(spend)
    for frame in (selected_assignments, selected_attempts, selected_spend):
        if not frame.empty and "study_id" in frame:
            frame.drop(frame[~frame["study_id"].astype(str).eq(study_id)].index, inplace=True)
    if not selected_attempts.empty and "task_id" not in selected_attempts:
        selected_attempts["task_id"] = selected_attempts.get(
            "metadata_json", pd.Series(index=selected_attempts.index, dtype=object)
        ).map(task_id_from_metadata)
    assignment_ids = selected_assignments.get("task_id", pd.Series(dtype=str)).dropna().astype(str)
    attempt_ids = selected_attempts.get("task_id", pd.Series(dtype=str)).dropna().astype(str)
    spend_ids = selected_spend.get("task_id", pd.Series(dtype=str)).dropna().astype(str)
    duplicate_assignments = int(assignment_ids.duplicated().sum())
    duplicate_attempts = int(attempt_ids.duplicated().sum())
    duplicate_spend = int(spend_ids.duplicated().sum())
    assignment_set, attempt_set, spend_set = set(assignment_ids), set(attempt_ids), set(spend_ids)
    orphan_attempts = sorted(attempt_set - assignment_set)
    orphan_spend = sorted(spend_set - assignment_set)
    attempted_without_spend = sorted(attempt_set - spend_set)
    assigned_without_attempt = sorted(assignment_set - attempt_set)
    integrity = (
        1.0
        if not assignment_set
        else (len(assignment_set & attempt_set) / len(assignment_set))
    )
    healthy = (
        duplicate_assignments == 0
        and duplicate_attempts == 0
        and duplicate_spend == 0
        and not orphan_attempts
        and not orphan_spend
        and not attempted_without_spend
        and (not require_paid or not assigned_without_attempt)
    )
    return {
        "healthy": healthy,
        "require_paid": require_paid,
        "assignments": len(assignment_set),
        "attempts": len(attempt_set),
        "spend_rows": len(spend_set),
        "assignment_integrity": float(integrity),
        "duplicate_assignments": duplicate_assignments,
        "duplicate_attempts": duplicate_attempts,
        "duplicate_spend": duplicate_spend,
        "orphan_attempts": orphan_attempts[:20],
        "orphan_spend": orphan_spend[:20],
        "attempted_without_spend": attempted_without_spend[:20],
        "assigned_without_attempt": assigned_without_attempt[:20],
    }


def privacy_gate(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    failures = []
    forbidden = {"messages", "prompt", "response", "completion_text", "request_body"}
    for name, frame in tables.items():
        leaked_columns = sorted(forbidden & set(frame.columns)) if not frame.empty else []
        retained = 0
        if not frame.empty and "payload_retained" in frame:
            retained = int(frame["payload_retained"].fillna(False).astype(bool).sum())
        if leaked_columns or retained:
            failures.append(
                {"table": name, "forbidden_columns": leaked_columns, "retained_rows": retained}
            )
    return {"healthy": not failures, "failures": failures}


def assignment_support(
    assignments: pd.DataFrame,
    shocks: pd.DataFrame,
    *,
    protocol: dict[str, Any],
    now: datetime,
    run_ledger: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Audit the frozen confirmatory horizon without opening paid outcomes.

    The release decision may depend on intended assignments and public shocks,
    but never on selections, costs, latency, or success.  This function keeps
    those gates in one place so the marker-first release cannot accidentally
    use a weaker operational readiness check.
    """

    study = protocol["study"]
    support = protocol["support"]
    design = protocol["design"]
    study_id = str(study["study_id"])
    frame = assignments.copy()
    if not frame.empty and "study_id" in frame:
        frame = frame[frame["study_id"].astype(str).eq(study_id)].copy()

    start = pd.Timestamp(str(study["prospective_start_utc"]))
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    fixed_end = start + pd.to_timedelta(int(support["confirmatory_days"]), unit="D")
    holdout_start = fixed_end - pd.to_timedelta(
        int(support["minimum_holdout_days"]), unit="D"
    )
    parsed_times = pd.to_datetime(
        frame.get("run_ts", pd.Series(index=frame.index, dtype=str)),
        format="%Y%m%dT%H%M%SZ",
        utc=True,
        errors="coerce",
    )
    ledger = pd.DataFrame() if run_ledger is None else run_ledger.copy()
    if not ledger.empty and "study_id" in ledger:
        ledger = ledger[ledger["study_id"].astype(str).eq(study_id)].copy()
    if not ledger.empty and {"run_id", "created_at"}.issubset(ledger) and "run_id" in frame:
        created = pd.to_datetime(ledger["created_at"], utc=True, errors="coerce")
        run_times = dict(zip(ledger["run_id"].astype(str), created, strict=False))
        parsed_times = parsed_times.fillna(frame["run_id"].astype(str).map(run_times))
    frame["_assignment_time"] = parsed_times
    frame = frame[
        frame["_assignment_time"].ge(start) & frame["_assignment_time"].le(fixed_end)
    ].copy()

    validation_error = None
    try:
        validate_factorial_assignments(frame.to_dict("records"))
    except (KeyError, TypeError, ValueError) as exc:
        validation_error = str(exc)

    now_ts = pd.Timestamp(now).tz_convert("UTC")
    assignment_times = frame["_assignment_time"].dropna()
    assignment_days = set(assignment_times.dt.date)
    holdout_days = set(
        assignment_times[assignment_times.ge(holdout_start)].dt.date
    )
    horizon_gate = bool(
        now_ts >= fixed_end
        and not assignment_times.empty
        and assignment_times.min() < start + pd.to_timedelta(1, unit="D")
        and assignment_times.max() >= fixed_end - pd.to_timedelta(1, unit="D")
    )

    cell_columns = ["target_n", "target_k", "overlap_arm", "router_rule"]
    if not frame.empty and set(cell_columns + ["block_id"]).issubset(frame):
        block_counts = (
            frame.groupby(cell_columns, dropna=False)["block_id"]
            .nunique()
            .sort_index()
        )
    else:
        block_counts = pd.Series(dtype=int)
    minimum_blocks = int(support["minimum_randomized_blocks_per_cell"])
    block_gate = bool(not block_counts.empty and block_counts.min() >= minimum_blocks)

    if not frame.empty and {"target_k", "task_id"}.issubset(frame):
        choices_by_k = frame.groupby("target_k")["task_id"].nunique().sort_index()
    else:
        choices_by_k = pd.Series(dtype=int)
    registered_k = {int(value) for value in design["responsive_counts"]}
    minimum_choices = int(support["minimum_choices_per_multiplicity"])
    choices_gate = bool(
        registered_k
        and registered_k.issubset({int(value) for value in choices_by_k.index})
        and all(int(choices_by_k.get(value, 0)) >= minimum_choices for value in registered_k)
    )

    exact_rows = 0
    if not frame.empty:
        for row in frame.to_dict("records"):
            selected = _list_value(row.get("selected_provider_keys"))
            tags = _list_value(row.get("provider_only_tags"))
            responsive = _list_value(row.get("responsive_provider_keys"))
            target_n = int(row["target_n"])
            target_k = int(row["target_k"])
            exact_rows += int(
                len(selected) == target_n
                and len(tags) == target_n
                and len(responsive) == target_k
                and set(responsive).issubset(selected)
            )
    exact_menu_coverage = exact_rows / len(frame) if len(frame) else 0.0
    exact_menu_gate = exact_menu_coverage >= float(support["minimum_exact_menu_coverage"])

    n_bins = (
        {int(value) for value in frame["target_n"].dropna().unique()}
        if not frame.empty and "target_n" in frame
        else set()
    )
    model_cohorts = (
        {str(value) for value in frame["model_id"].dropna().unique()}
        if not frame.empty and "model_id" in frame
        else set()
    )
    n_gate = len(n_bins) >= int(protocol["rank"]["minimum_market_size_bins"])
    model_gate = len(model_cohorts) >= int(protocol["rank"]["minimum_model_cohorts"])

    provider_pairs: set[tuple[str, str]] = set()
    if not frame.empty and "responsive_provider_keys" in frame:
        for providers in frame["responsive_provider_keys"]:
            values = _list_value(providers)
            provider_pairs.update(itertools.combinations(sorted(set(values)), 2))
    pair_gate = len(provider_pairs) >= int(support["minimum_provider_pair_clusters"])

    clean_shocks = shocks.copy()
    if not clean_shocks.empty and "study_id" in clean_shocks:
        clean_shocks = clean_shocks[
            clean_shocks["study_id"].astype(str).eq(study_id)
        ].copy()
    if not clean_shocks.empty and "placebo" in clean_shocks:
        clean_shocks = clean_shocks[
            ~clean_shocks["placebo"].fillna(False).astype(bool)
        ]
    if not clean_shocks.empty and "contaminated" in clean_shocks:
        clean_shocks = clean_shocks[
            ~clean_shocks["contaminated"].fillna(True).astype(bool)
        ]
    shock_counts: dict[int, int] = {}
    for n in sorted({int(value) for value in design["menu_sizes"]}):
        eligible = clean_shocks
        if not eligible.empty and "eligible_n" in eligible:
            eligible = eligible[pd.to_numeric(eligible["eligible_n"], errors="coerce").ge(n)]
        shock_counts[n] = (
            int(eligible.drop_duplicates(["model_id", "event_ts"]).shape[0])
            if not eligible.empty and {"model_id", "event_ts"}.issubset(eligible)
            else 0
        )
    shock_gate = bool(
        shock_counts
        and min(shock_counts.values()) >= int(support["minimum_clean_shocks_per_size_bin"])
    )

    gates = {
        "assignment_schema_integrity": validation_error is None,
        "fixed_confirmatory_horizon": horizon_gate,
        "randomized_blocks_per_cell": block_gate,
        "choices_per_multiplicity": choices_gate,
        "exact_menu_coverage": exact_menu_gate,
        "market_size_bins": n_gate,
        "model_cohorts": model_gate,
        "provider_pair_clusters": pair_gate,
        "clean_shocks_per_size_bin": shock_gate,
        "holdout_days": len(holdout_days) >= int(support["minimum_holdout_days"]),
    }
    return {
        "healthy": all(gates.values()),
        "gates": gates,
        "validation_error": validation_error,
        "prospective_start": start.isoformat(),
        "fixed_confirmatory_end": fixed_end.isoformat(),
        "observed_assignment_days": len(assignment_days),
        "observed_holdout_days": len(holdout_days),
        "earliest_assignment": (
            assignment_times.min().isoformat() if not assignment_times.empty else None
        ),
        "latest_assignment": (
            assignment_times.max().isoformat() if not assignment_times.empty else None
        ),
        "minimum_blocks_per_cell_observed": (
            int(block_counts.min()) if not block_counts.empty else 0
        ),
        "blocks_by_cell": {
            "|".join(map(str, key if isinstance(key, tuple) else (key,))): int(value)
            for key, value in block_counts.items()
        },
        "choices_by_k": {str(int(key)): int(value) for key, value in choices_by_k.items()},
        "exact_menu_coverage": float(exact_menu_coverage),
        "market_size_bins": sorted(n_bins),
        "model_cohorts": sorted(model_cohorts),
        "provider_pair_clusters": len(provider_pairs),
        "clean_shocks_by_size_bin": {str(key): value for key, value in shock_counts.items()},
    }


def audit(
    data_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    now: datetime | None = None,
    require_paid: bool = False,
    require_confirmatory_support: bool = False,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    protocol, protocol_sha256 = load_protocol(config_path)
    study_id = str(protocol["study"]["study_id"])
    support = protocol["support"]
    snapshots = read_table(data_root, "endpoints_snapshots")
    assignments = read_table(data_root, "ic_assignments")
    attempts = read_table(data_root, "ic_attempts")
    spend = read_table(data_root, "paid_spend_ledger")
    shocks = read_table(data_root, "ic_common_shocks")
    run_ledger = read_table(data_root, "ic_run_ledger")
    continuity = capture_continuity(snapshots, now=now)
    continuity["coverage_gate"] = continuity["coverage"] >= float(
        support["minimum_capture_coverage"]
    )
    maximum_gap = continuity["maximum_gap_minutes"]
    continuity["gap_gate"] = maximum_gap is not None and maximum_gap <= float(
        support["maximum_gap_minutes"]
    )
    rec = reconciliation(
        assignments, attempts, spend, study_id=study_id, require_paid=require_paid
    )
    public_tables = {
        "ic_market_epochs": read_table(data_root, "ic_market_epochs"),
        "ic_provider_roles": read_table(data_root, "ic_provider_roles"),
        "ic_assignments": assignments,
        "ic_quality_assignments": read_table(data_root, "ic_quality_assignments"),
        "ic_run_ledger": run_ledger,
    }
    privacy = privacy_gate(public_tables)
    confirmatory = assignment_support(
        assignments,
        shocks,
        protocol=protocol,
        now=now,
        run_ledger=run_ledger,
    )
    result = {
        "format": "orcap-information-congestion-readiness-v1",
        "checked_at": now.isoformat(),
        "study_id": study_id,
        "protocol_sha256": protocol_sha256,
        "healthy": bool(
            continuity["healthy"]
            and continuity["coverage_gate"]
            and continuity["gap_gate"]
            and rec["healthy"]
            and privacy["healthy"]
            and (not require_confirmatory_support or confirmatory["healthy"])
        ),
        "capture_continuity": continuity,
        "reconciliation": rec,
        "privacy": privacy,
        "confirmatory_support_required": require_confirmatory_support,
        "confirmatory_support": confirmatory,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output", type=Path, default=Path("information-congestion-readiness.json")
    )
    parser.add_argument("--require-paid", action="store_true")
    parser.add_argument("--require-confirmatory-support", action="store_true")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="write a negative readiness report without failing the recurring monitor",
    )
    args = parser.parse_args()
    result = audit(
        args.data_root,
        config_path=args.config,
        require_paid=args.require_paid,
        require_confirmatory_support=args.require_confirmatory_support,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["healthy"] and not args.report_only:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
