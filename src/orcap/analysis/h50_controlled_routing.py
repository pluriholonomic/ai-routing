"""H50 — pre-registered, cluster-randomized test of routing mechanisms.

Public routing surfaces cannot identify delivered requests or a causal policy
effect. H50 only analyzes redacted *owned* model-epoch experiments registered
before assignment. It estimates policy contrasts at the randomized epoch level
and refuses a welfare or market-wide routing claim.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from . import data
from .blinding import exclude_outcome_blinded
from .common import DEFAULT_OUT, save, save_json

EPOCH_COLUMNS = [
    "manifest_id",
    "study_id",
    "assignment_id",
    "model_id",
    "epoch_start",
    "epoch_end",
    "treatment_arm",
    "randomization_stratum",
    "assignment_probability",
    "n_attempts",
    "n_completed_attempts",
    "n_succeeded_attempts",
    "attempt_success_rate",
    "fallback_rate",
    "mean_cost_usd",
    "mean_latency_ms",
    "registered_value_net_cost",
    "allocated_requests",
    "served_requests",
    "shortfall_requests",
    "capacity_shortfall_rate",
    "attempt_policy_mismatch_count",
]
EFFECT_COLUMNS = [
    "manifest_id",
    "study_id",
    "baseline_arm",
    "treatment_arm",
    "outcome",
    "is_primary_outcome",
    "estimate_treatment_minus_baseline",
    "cluster_robust_se",
    "ci95_low",
    "ci95_high",
    "normal_approx_p_value",
    "n_strata",
    "n_treatment_epochs",
    "n_baseline_epochs",
    "n_treatment_attempts",
    "n_baseline_attempts",
    "estimator",
]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _text(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series("", index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str)


def _latest(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    if frame.empty or key not in frame:
        return frame.copy()
    sort = [key] + (["run_ts"] if "run_ts" in frame else [])
    return frame.sort_values(sort).drop_duplicates(key, keep="last").copy()


def _load(table: str) -> pd.DataFrame:
    try:
        query = f"select * from read_parquet('{data.table_glob(table)}', union_by_name = true)"
        return data.q(query).df()
    except Exception:
        return pd.DataFrame()


def _parse_json_list(value) -> list:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def design_audit(manifests: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    """Check pre-registration, arm probabilities, and non-overlapping epochs."""
    if assignments.empty:
        return _empty(["assignment_id", "manifest_id", "design_valid", "design_errors"])
    manifests = _latest(manifests, "manifest_id")
    manifest_lookup = {
        str(row.manifest_id): row
        for row in manifests.itertuples(index=False)
        if getattr(row, "manifest_id", None)
    }
    rows = []
    for assignment in _latest(assignments, "assignment_id").itertuples(index=False):
        errors: list[str] = []
        manifest_id = str(getattr(assignment, "manifest_id", ""))
        manifest = manifest_lookup.get(manifest_id)
        if manifest is None:
            errors.append("unknown_manifest")
        start = pd.to_datetime(getattr(assignment, "epoch_start", None), utc=True, errors="coerce")
        end = pd.to_datetime(getattr(assignment, "epoch_end", None), utc=True, errors="coerce")
        assigned_at = pd.to_datetime(
            getattr(assignment, "assigned_at", None), utc=True, errors="coerce"
        )
        if pd.isna(start) or pd.isna(end) or pd.isna(assigned_at):
            errors.append("invalid_timestamp")
        elif start >= end:
            errors.append("nonpositive_epoch")
        elif assigned_at > start:
            errors.append("assigned_after_epoch_start")
        if manifest is not None:
            if str(getattr(assignment, "study_id", "")) != str(manifest.study_id):
                errors.append("study_id_mismatch")
            planned_start = pd.to_datetime(manifest.planned_start_at, utc=True, errors="coerce")
            planned_end = pd.to_datetime(manifest.planned_end_at, utc=True, errors="coerce")
            if not pd.isna(start) and not pd.isna(end) and (
                start < planned_start or end > planned_end
            ):
                errors.append("epoch_outside_registered_window")
            arms = {
                arm.get("name"): arm
                for arm in _parse_json_list(getattr(manifest, "arms_json", "[]"))
                if isinstance(arm, dict)
            }
            arm = arms.get(getattr(assignment, "treatment_arm", None))
            if arm is None:
                errors.append("unregistered_treatment_arm")
            else:
                try:
                    observed_probability = float(assignment.assignment_probability)
                except (TypeError, ValueError):
                    observed_probability = float("nan")
                if not math.isfinite(observed_probability) or not math.isclose(
                    observed_probability,
                    float(arm.get("assignment_probability")),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    errors.append("assignment_probability_mismatch")
        rows.append(
            {
                "assignment_id": getattr(assignment, "assignment_id", None),
                "manifest_id": manifest_id,
                "study_id": getattr(assignment, "study_id", None),
                "model_id": getattr(assignment, "model_id", None),
                "epoch_start": getattr(assignment, "epoch_start", None),
                "epoch_end": getattr(assignment, "epoch_end", None),
                "design_valid": not errors,
                "design_errors": ";".join(errors),
            }
        )
    audit = pd.DataFrame(rows)
    valid = audit[audit["design_valid"]].copy()
    if valid.empty:
        return audit
    valid["_start"] = pd.to_datetime(valid["epoch_start"], utc=True)
    valid["_end"] = pd.to_datetime(valid["epoch_end"], utc=True)
    overlaps: set[str] = set()
    for _, group in valid.groupby(["manifest_id", "study_id", "model_id"], dropna=False):
        ordered = group.sort_values(["_start", "_end"])
        prior_end = None
        prior_id = None
        for assignment_id, start, end in ordered[["assignment_id", "_start", "_end"]].itertuples(
            index=False, name=None
        ):
            if prior_end is not None and start < prior_end:
                overlaps.update({str(prior_id), str(assignment_id)})
            if prior_end is None or end > prior_end:
                prior_end, prior_id = end, assignment_id
    if overlaps:
        matches = audit["assignment_id"].astype(str).isin(overlaps)
        audit.loc[matches, "design_valid"] = False
        audit.loc[matches, "design_errors"] = audit.loc[matches, "design_errors"].map(
            lambda value: ";".join(part for part in [value, "overlapping_assignment"] if part)
        )
    temporary_columns = [column for column in audit if column.startswith("_")]
    return audit.drop(columns=temporary_columns, errors="ignore")


def _assignment_manifest_rows(
    manifests: pd.DataFrame, assignments: pd.DataFrame, audit: pd.DataFrame
) -> pd.DataFrame:
    if manifests.empty or assignments.empty or audit.empty:
        return pd.DataFrame()
    valid_ids = set(audit.loc[audit["design_valid"], "assignment_id"].astype(str))
    assignment_rows = _latest(assignments, "assignment_id").copy()
    assignment_rows = assignment_rows[
        assignment_rows["assignment_id"].astype(str).isin(valid_ids)
    ].copy()
    if assignment_rows.empty:
        return assignment_rows
    manifest_rows = _latest(manifests, "manifest_id").copy()
    return assignment_rows.merge(
        manifest_rows,
        on=["manifest_id", "study_id"],
        how="inner",
        suffixes=("", "_manifest"),
    )


def epoch_outcomes(
    manifests: pd.DataFrame,
    assignments: pd.DataFrame,
    attempts: pd.DataFrame,
    capacity_outcomes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create one outcome row per valid randomized model epoch.

    Route attempts are only included when their recorded policy equals the
    pre-assigned arm. A mismatch is retained as a design failure signal rather
    than silently reclassified as a treated observation.
    """
    audit = design_audit(manifests, assignments)
    enrolled = _assignment_manifest_rows(manifests, assignments, audit)
    if enrolled.empty:
        return _empty(EPOCH_COLUMNS), audit
    attempts = _latest(attempts, "event_id")
    capacity_outcomes = _latest(capacity_outcomes, "outcome_id")
    if not attempts.empty:
        attempts = attempts.copy()
        attempts["_observed_at"] = pd.to_datetime(
            attempts.get("observed_at"), utc=True, errors="coerce"
        )
        for column in ("cost_usd", "latency_ms"):
            attempts[column] = _numeric(attempts, column)
    if not capacity_outcomes.empty:
        capacity_outcomes = capacity_outcomes.copy()
        for column in ("allocated_requests", "served_requests", "shortfall_requests"):
            capacity_outcomes[column] = _numeric(capacity_outcomes, column)
        capacity_outcomes["_epoch_start"] = pd.to_datetime(
            capacity_outcomes.get("epoch_start"), utc=True, errors="coerce"
        )
        capacity_outcomes["_epoch_end"] = pd.to_datetime(
            capacity_outcomes.get("epoch_end"), utc=True, errors="coerce"
        )
    rows = []
    for assignment in enrolled.itertuples(index=False):
        start = pd.to_datetime(assignment.epoch_start, utc=True)
        end = pd.to_datetime(assignment.epoch_end, utc=True)
        if attempts.empty:
            epoch_attempts = pd.DataFrame()
        else:
            epoch_attempts = attempts[
                (attempts["study_id"].astype(str) == str(assignment.study_id))
                & (attempts["model_id"].astype(str) == str(assignment.model_id))
                & (attempts["_observed_at"] >= start)
                & (attempts["_observed_at"] < end)
            ].copy()
        policy = _text(epoch_attempts, "policy")
        mismatch = int(policy.ne(str(assignment.treatment_arm)).sum())
        used = epoch_attempts[policy.eq(str(assignment.treatment_arm))].copy()
        completed = used[_text(used, "outcome").isin({"succeeded", "failed", "cancelled"})]
        n_completed = len(completed)
        n_succeeded = int(_text(completed, "outcome").eq("succeeded").sum())
        success_rate = n_succeeded / n_completed if n_completed else None
        fallback = _numeric(used, "fallback_triggered")
        mean_cost = _numeric(used, "cost_usd").mean()
        mean_latency = _numeric(used, "latency_ms").mean()
        if capacity_outcomes.empty:
            capacity = pd.DataFrame()
        else:
            capacity = capacity_outcomes[
                (capacity_outcomes["study_id"].astype(str) == str(assignment.study_id))
                & (capacity_outcomes["model_id"].astype(str) == str(assignment.model_id))
                & (capacity_outcomes["_epoch_start"] == start)
                & (capacity_outcomes["_epoch_end"] == end)
            ]
        allocated = _numeric(capacity, "allocated_requests").sum(min_count=1)
        served = _numeric(capacity, "served_requests").sum(min_count=1)
        shortfall = _numeric(capacity, "shortfall_requests").sum(min_count=1)
        shortfall_rate = shortfall / allocated if pd.notna(allocated) and allocated > 0 else None
        value = pd.to_numeric(
            pd.Series([getattr(assignment, "value_per_success_usd", None)]), errors="coerce"
        ).iat[0]
        registered_value = (
            success_rate * value - mean_cost
            if pd.notna(value) and success_rate is not None and pd.notna(mean_cost)
            else None
        )
        rows.append(
            {
                "manifest_id": assignment.manifest_id,
                "study_id": assignment.study_id,
                "assignment_id": assignment.assignment_id,
                "model_id": assignment.model_id,
                "epoch_start": assignment.epoch_start,
                "epoch_end": assignment.epoch_end,
                "treatment_arm": assignment.treatment_arm,
                "randomization_stratum": assignment.randomization_stratum,
                "assignment_probability": assignment.assignment_probability,
                "n_attempts": int(len(used)),
                "n_completed_attempts": int(n_completed),
                "n_succeeded_attempts": n_succeeded,
                "attempt_success_rate": success_rate,
                "fallback_rate": fallback.mean() if fallback.notna().any() else None,
                "mean_cost_usd": mean_cost if pd.notna(mean_cost) else None,
                "mean_latency_ms": mean_latency if pd.notna(mean_latency) else None,
                "registered_value_net_cost": registered_value,
                "allocated_requests": allocated if pd.notna(allocated) else None,
                "served_requests": served if pd.notna(served) else None,
                "shortfall_requests": shortfall if pd.notna(shortfall) else None,
                "capacity_shortfall_rate": shortfall_rate,
                "attempt_policy_mismatch_count": mismatch,
            }
        )
    return pd.DataFrame(rows, columns=EPOCH_COLUMNS), audit


def _stratified_effect(
    panel: pd.DataFrame, *, baseline_arm: str, treatment_arm: str, outcome: str
) -> dict | None:
    values = panel.copy()
    values[outcome] = pd.to_numeric(values[outcome], errors="coerce")
    values = values[values[outcome].notna()]
    values = values[values["treatment_arm"].isin({baseline_arm, treatment_arm})]
    if values.empty:
        return None
    components = []
    for _, stratum in values.groupby("randomization_stratum", dropna=False):
        treatment = stratum[stratum["treatment_arm"] == treatment_arm][outcome]
        baseline = stratum[stratum["treatment_arm"] == baseline_arm][outcome]
        if treatment.empty or baseline.empty:
            continue
        difference = float(treatment.mean() - baseline.mean())
        treatment_variance = float(treatment.var(ddof=1)) if len(treatment) > 1 else 0.0
        baseline_variance = float(baseline.var(ddof=1)) if len(baseline) > 1 else 0.0
        variance = treatment_variance / len(treatment) + baseline_variance / len(baseline)
        components.append(
            {
                "weight": len(stratum),
                "difference": difference,
                "variance": variance,
                "treatment_epochs": len(treatment),
                "baseline_epochs": len(baseline),
                "treatment_attempts": int(
                    stratum.loc[stratum["treatment_arm"] == treatment_arm, "n_attempts"].sum()
                ),
                "baseline_attempts": int(
                    stratum.loc[stratum["treatment_arm"] == baseline_arm, "n_attempts"].sum()
                ),
            }
        )
    if not components:
        return None
    total_weight = sum(item["weight"] for item in components)
    estimate = sum(item["weight"] * item["difference"] for item in components) / total_weight
    variance = sum(
        (item["weight"] ** 2) * item["variance"] for item in components
    ) / total_weight**2
    se = math.sqrt(max(variance, 0.0))
    z = estimate / se if se > 0 else None
    return {
        "estimate_treatment_minus_baseline": estimate,
        "cluster_robust_se": se,
        "ci95_low": estimate - 1.96 * se,
        "ci95_high": estimate + 1.96 * se,
        "normal_approx_p_value": math.erfc(abs(z) / math.sqrt(2)) if z is not None else None,
        "n_strata": len(components),
        "n_treatment_epochs": sum(item["treatment_epochs"] for item in components),
        "n_baseline_epochs": sum(item["baseline_epochs"] for item in components),
        "n_treatment_attempts": sum(item["treatment_attempts"] for item in components),
        "n_baseline_attempts": sum(item["baseline_attempts"] for item in components),
        "estimator": "stratum_standardized_cluster_mean_difference",
    }


def treatment_effects(manifests: pd.DataFrame, epoch_panel: pd.DataFrame) -> pd.DataFrame:
    if manifests.empty or epoch_panel.empty:
        return _empty(EFFECT_COLUMNS)
    rows = []
    for manifest in _latest(manifests, "manifest_id").itertuples(index=False):
        panel = epoch_panel[epoch_panel["manifest_id"].astype(str) == str(manifest.manifest_id)]
        if panel.empty:
            continue
        baseline = manifest.baseline_arm
        outcomes = _parse_json_list(manifest.primary_outcomes_json)
        negative = manifest.negative_control_outcome
        for arm in sorted(set(panel["treatment_arm"].dropna()) - {baseline}):
            for outcome in outcomes + [negative]:
                if outcome not in panel:
                    continue
                result = _stratified_effect(
                    panel, baseline_arm=baseline, treatment_arm=arm, outcome=outcome
                )
                if result is None:
                    continue
                rows.append(
                    {
                        "manifest_id": manifest.manifest_id,
                        "study_id": manifest.study_id,
                        "baseline_arm": baseline,
                        "treatment_arm": arm,
                        "outcome": outcome,
                        "is_primary_outcome": outcome in outcomes,
                    }
                    | result
                )
    return pd.DataFrame(rows, columns=EFFECT_COLUMNS)


def study_status(
    manifests: pd.DataFrame,
    audit: pd.DataFrame,
    epoch_panel: pd.DataFrame,
    effects: pd.DataFrame | None = None,
) -> list[dict]:
    results = []
    for manifest in _latest(manifests, "manifest_id").itertuples(index=False):
        manifest_id = str(manifest.manifest_id)
        manifest_audit = (
            audit[audit["manifest_id"].astype(str) == manifest_id] if not audit.empty else audit
        )
        panel = (
            epoch_panel[epoch_panel["manifest_id"].astype(str) == manifest_id]
            if not epoch_panel.empty
            else epoch_panel
        )
        invalid_assignments = (
            int((~manifest_audit["design_valid"]).sum()) if not manifest_audit.empty else 0
        )
        policy_mismatches = (
            int(panel["attempt_policy_mismatch_count"].sum()) if not panel.empty else 0
        )
        arm_counts = {
            str(arm): {
                "epochs": int(len(group)),
                "attempts": int(group["n_attempts"].sum()),
            }
            for arm, group in panel.groupby("treatment_arm")
        } if not panel.empty else {}
        registered_arms = [arm.get("name") for arm in _parse_json_list(manifest.arms_json)]
        complete_power = bool(registered_arms) and all(
            arm_counts.get(arm, {}).get("epochs", 0) >= int(manifest.min_clusters_per_arm)
            and arm_counts.get(arm, {}).get("attempts", 0) >= int(manifest.min_attempts_per_arm)
            for arm in registered_arms
        )
        primary_outcomes = _parse_json_list(manifest.primary_outcomes_json)
        if effects is None:
            missing_policy_comparisons: list[str] = []
            negative_alerts = _empty(EFFECT_COLUMNS)
        else:
            manifest_effects = (
                effects[effects["manifest_id"].astype(str) == manifest_id]
                if not effects.empty
                else _empty(EFFECT_COLUMNS)
            )
            estimable_arms = set(
                manifest_effects.loc[
                    manifest_effects["is_primary_outcome"].eq(True), "treatment_arm"
                ].astype(str)
            )
            missing_policy_comparisons = sorted(
                arm
                for arm in registered_arms
                if arm != manifest.baseline_arm and arm not in estimable_arms
            )
            negative_alerts = manifest_effects[
                manifest_effects["outcome"].eq(manifest.negative_control_outcome)
                & manifest_effects["normal_approx_p_value"].lt(0.05)
            ]
        if manifest_audit.empty:
            status = "not_identified"
        elif invalid_assignments or policy_mismatches:
            status = "invalid_design"
        elif not complete_power or missing_policy_comparisons:
            status = "power_gated"
        elif not negative_alerts.empty:
            status = "randomized_estimate_ready_with_falsification_alert"
        else:
            status = "randomized_estimate_ready"
        results.append(
            {
                "manifest_id": manifest_id,
                "study_id": manifest.study_id,
                "status": status,
                "assignment_rows": int(len(manifest_audit)),
                "invalid_assignment_rows": invalid_assignments,
                "attempt_policy_mismatch_count": policy_mismatches,
                "arm_coverage": arm_counts,
                "min_clusters_per_arm": int(manifest.min_clusters_per_arm),
                "min_attempts_per_arm": int(manifest.min_attempts_per_arm),
                "primary_outcomes": primary_outcomes,
                "missing_policy_comparisons": missing_policy_comparisons,
                "negative_control_outcome": manifest.negative_control_outcome,
                "negative_control_alert_count": int(len(negative_alerts)),
            }
        )
    return results


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    manifests = _load("router_study_manifests")
    assignments = _load("router_study_assignments")
    attempts = _load("router_route_attempts")
    attempts, _ = exclude_outcome_blinded(attempts)
    capacity_outcomes = _load("router_capacity_epoch_outcomes")
    epoch_panel, audit = epoch_outcomes(manifests, assignments, attempts, capacity_outcomes)
    effects = treatment_effects(manifests, epoch_panel)
    statuses = study_status(manifests, audit, epoch_panel, effects)
    save(audit, out_dir, "h50_routing_design_audit")
    save(epoch_panel, out_dir, "h50_routing_epoch_panel")
    save(effects, out_dir, "h50_routing_effects")
    summary = {
        "study_count": int(len(statuses)),
        "statuses": statuses,
        "effect_rows": int(len(effects)),
        "claim_boundary": (
            "H50 identifies an owned, pre-registered randomized model-epoch policy contrast only "
            "when its design and power gates clear. It does not identify market-wide routing, "
            "provider profit, an optimal bond, or welfare without a registered request-value proxy."
        ),
        "required_design": [
            "immutable manifest registered before the first assigned epoch",
            "non-overlapping model-epoch assignments with disclosed arm probabilities",
            "attempt policy equal to the assigned arm",
            "redacted route outcomes and matched capacity aggregates",
        ],
    }
    save_json(summary, out_dir, "h50_summary")
    return summary
