"""H95 fixed-horizon replication analysis.

The gate is the first 120 prospectively planned eligible triplets, not an arm
balance stopping time.  Before that assignment-only gate opens, this module does
not query outcome, cost, latency, selected-provider, or token fields.
"""

from __future__ import annotations

import itertools
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import t as student_t
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

from ..capture_decomposition_probes import POLICIES
from ..capture_decomposition_replication import (
    STUDY_ID,
    TARGET_TRIPLETS,
    tasks_with_assigned_first,
)
from . import data
from .common import DEFAULT_OUT, save, save_json
from .h81_delegation_decomposition import verify_treatment_metadata

COMPARISONS = (
    (
        "fallback_option_value",
        "price_order_fallback",
        "price_only_no_fallback",
        True,
    ),
    (
        "hidden_selection_value",
        "delegated_default",
        "price_order_fallback",
        True,
    ),
    (
        "total_delegation_value",
        "delegated_default",
        "price_only_no_fallback",
        False,
    ),
)
RANDOMIZATION_DRAWS = 100_000
RANDOMIZATION_MC_AUDIT_TOLERANCE = 0.01
PRIMARY_FWER_ALPHA = 0.05
BINARY_OUTCOME_VALUES = {
    "succeeded": 1.0,
    "failed": 0.0,
    "cancelled": 0.0,
}
TREATMENT_METADATA_FIELDS = (
    "requested_order_length",
    "provider_only_count",
    "public_provider_count",
    "allow_fallbacks",
)


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def prepare_assignment_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.loc[frame["study_id"].astype(str).eq(STUDY_ID)].copy()
    if out.empty:
        return out
    out["_observed"] = pd.to_datetime(
        out.get("observed_at", out.get("run_ts")), errors="coerce", utc=True
    )
    out = (
        out.sort_values(["source", "event_id", "_observed", "run_ts"])
        .drop_duplicates(["source", "event_id"], keep="last")
        .reset_index(drop=True)
    )
    metadata = out["metadata_json"].map(_metadata)
    fields = {
        "triplet_id": None,
        "block_id": None,
        "assigned_first_policy": None,
        "policy_order": None,
        "block_seed": None,
        "ranking_position": None,
        "hugging_face_id": None,
        "public_provider_order": None,
        "public_provider_count": None,
        "requested_order_length": None,
        "provider_only_count": None,
        "allow_fallbacks": None,
        "assignment_probability_first": None,
    }
    for field, default in fields.items():
        out[field] = metadata.map(
            lambda item, field=field, default=default: item.get(field, default)
        )
    for field in [
        "policy_order",
        "ranking_position",
        "assignment_probability_first",
        "public_provider_count",
        "requested_order_length",
        "provider_only_count",
    ]:
        out[field] = pd.to_numeric(out[field], errors="coerce")
    return out


def prepare_plans(eligibility: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    empty_selected = pd.DataFrame(
        columns=[
            "triplet_id",
            "triplet_sequence",
            "planned_at",
            "run_id",
            "model_id",
            "assigned_first_policy",
            "block_id",
            "hugging_face_id",
            "ranking_position",
        ]
    )
    if eligibility is None or eligibility.empty:
        return pd.DataFrame(), empty_selected
    frame = eligibility.loc[eligibility["study_id"].astype(str).eq(STUDY_ID)].copy()
    if frame.empty:
        return frame, empty_selected
    frame["_observed"] = pd.to_datetime(
        frame.get("observed_at", frame.get("run_ts")), errors="coerce", utc=True
    )
    frame = (
        frame.sort_values(["run_id", "model_id", "_observed", "run_ts"])
        .drop_duplicates(["run_id", "model_id"], keep="last")
        .reset_index(drop=True)
    )
    for field in ["selected_for_triplet", "eligible"]:
        frame[field] = frame[field].fillna(False).astype(bool)
    selected = frame.loc[
        frame["selected_for_triplet"] & frame["eligible"] & frame["triplet_id"].notna()
    ].copy()
    valid_ids: list[str] = []
    triplet_rows: list[dict[str, Any]] = []
    for triplet_id, group in selected.groupby("triplet_id", sort=False):
        valid = (
            len(group) == 3
            and group["model_id"].nunique() == 3
            and set(group["assigned_first_policy"].astype(str)) == set(POLICIES)
            and group["block_id"].notna().all()
        )
        if valid:
            valid_ids.append(str(triplet_id))
            triplet_rows.append(
                {
                    "triplet_id": str(triplet_id),
                    "planned_at": group["_observed"].min(),
                    "run_id": str(group["run_id"].iloc[0]),
                    "selected_models": int(group["model_id"].nunique()),
                }
            )
    selected = selected.loc[selected["triplet_id"].astype(str).isin(valid_ids)].copy()
    triplets = pd.DataFrame(triplet_rows)
    if not triplets.empty:
        triplets = triplets.sort_values(["planned_at", "triplet_id"]).reset_index(drop=True)
        triplets["triplet_sequence"] = np.arange(1, len(triplets) + 1)
        selected = selected.merge(
            triplets[["triplet_id", "triplet_sequence", "planned_at"]],
            on="triplet_id",
            how="inner",
            validate="many_to_one",
        )
    return frame, selected


def _replay_block(group: pd.DataFrame) -> bool:
    if len(group) != len(POLICIES):
        return False
    first = group.sort_values("policy_order").iloc[0]
    order = first["public_provider_order"]
    if not isinstance(order, list) or len(order) < 2:
        return False
    try:
        seed = int(first["block_seed"])
    except (TypeError, ValueError):
        return False
    endpoints = [
        {"provider": provider, "price": float(index + 1), "input_price": 0.0}
        for index, provider in enumerate(order)
    ]
    expected = tasks_with_assigned_first(
        endpoints,
        str(first["assigned_first_policy"]),
        random.Random(seed),
    )
    observed = group.sort_values("policy_order")["policy"].astype(str).tolist()
    return observed == [task["policy"] for task in expected]


def treatment_metadata_auditable(row: pd.Series) -> bool:
    """Return whether a row contains every provider-control audit field.

    The first H95 triplets predate row-level order-length fields.  Those rows
    are retained under the prospective intent-to-treat horizon and are marked
    legacy-unverified rather than silently passed or discarded.
    """
    return all(field in row.index and pd.notna(row[field]) for field in TREATMENT_METADATA_FIELDS)


def _annotate_treatment_metadata(first: pd.DataFrame) -> pd.DataFrame:
    out = first.copy()
    if out.empty:
        out["treatment_metadata_auditable"] = pd.Series(dtype=bool)
        out["treatment_metadata_pass"] = pd.Series(dtype="boolean")
        return out
    out["treatment_metadata_auditable"] = out.apply(treatment_metadata_auditable, axis=1)
    out["treatment_metadata_pass"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    auditable = out["treatment_metadata_auditable"]
    out.loc[auditable, "treatment_metadata_pass"] = out.loc[auditable].apply(
        verify_treatment_metadata, axis=1
    )
    return out


def assignment_audit(
    attempts: pd.DataFrame,
    selected_plans: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = [
        "triplet_id",
        "triplet_sequence",
        "planned_models",
        "recorded_blocks",
        "complete_assignment",
        "first_policy_balance",
        "plan_compliance",
        "replay_passes",
        "replay_blocks",
        "treatment_metadata_auditable_blocks",
        "treatment_metadata_passes",
        "treatment_metadata_failures",
        "legacy_unverified_blocks",
        "recorded_first_position_blocks",
    ]
    if selected_plans.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame()
    first = attempts.loc[attempts["policy_order"].eq(0)].copy() if not attempts.empty else attempts
    first = _annotate_treatment_metadata(first)
    records: list[dict[str, Any]] = []
    for triplet_id, plan in selected_plans.groupby("triplet_id", sort=False):
        observed = attempts.loc[attempts["triplet_id"].astype(str).eq(str(triplet_id))]
        observed_first = first.loc[first["triplet_id"].astype(str).eq(str(triplet_id))]
        expected_pairs = set(
            zip(
                plan["model_id"].astype(str),
                plan["assigned_first_policy"].astype(str),
                strict=True,
            )
        )
        observed_pairs = set(
            zip(
                observed_first["model_id"].astype(str),
                observed_first["policy"].astype(str),
                strict=True,
            )
        )
        replay = [
            _replay_block(group)
            for _, group in observed.groupby("block_id", sort=False)
            if pd.notna(group["block_id"].iloc[0])
        ]
        complete = (
            observed["block_id"].nunique() == 3
            and len(observed) == 9
            and all(
                len(group) == 3 and set(group["policy"].astype(str)) == set(POLICIES)
                for _, group in observed.groupby("block_id", sort=False)
            )
        )
        auditable = int(observed_first["treatment_metadata_auditable"].sum())
        treatment_passes = int(
            observed_first["treatment_metadata_pass"].fillna(False).astype(bool).sum()
        )
        records.append(
            {
                "triplet_id": str(triplet_id),
                "triplet_sequence": int(plan["triplet_sequence"].iloc[0]),
                "planned_models": int(plan["model_id"].nunique()),
                "recorded_blocks": int(observed["block_id"].nunique()),
                "complete_assignment": bool(complete),
                "first_policy_balance": set(observed_first["policy"].astype(str)) == set(POLICIES),
                "plan_compliance": observed_pairs == expected_pairs,
                "replay_passes": int(sum(replay)),
                "replay_blocks": len(replay),
                "treatment_metadata_auditable_blocks": auditable,
                "treatment_metadata_passes": treatment_passes,
                "treatment_metadata_failures": auditable - treatment_passes,
                "legacy_unverified_blocks": int(len(observed_first) - auditable),
                "recorded_first_position_blocks": int(len(observed_first)),
            }
        )
    return pd.DataFrame(records, columns=columns), first


def _support_summary(plans: pd.DataFrame, eligibility: pd.DataFrame) -> dict[str, Any]:
    if plans.empty:
        return {
            "selected_blocks": 0,
            "unique_models": 0,
            "effective_model_count": 0.0,
            "model_dominance": None,
            "unique_hugging_face_ids": 0,
            "six_hour_bins": 0,
            "max_six_hour_triplet_share": None,
            "structural_transport_gates_pass": False,
        }
    counts = plans["model_id"].astype(str).value_counts()
    shares = counts / counts.sum()
    triplet_times = plans[["triplet_id", "planned_at"]].drop_duplicates("triplet_id")
    triplet_times["planned_at"] = pd.to_datetime(
        triplet_times["planned_at"], errors="coerce", utc=True
    )
    valid_times = triplet_times["planned_at"].dropna()
    six_hour_counts = valid_times.dt.floor("6h").value_counts()
    max_six_hour_share = (
        float(six_hour_counts.max() / len(triplet_times))
        if len(six_hour_counts) and len(valid_times) == len(triplet_times)
        else None
    )
    unique_hugging_face_ids = int(plans["hugging_face_id"].dropna().astype(str).nunique())
    effective_model_count = float(1.0 / np.square(shares).sum())
    model_dominance = float(shares.max())
    structural_gates = {
        "at_least_eight_models": len(counts) >= 8,
        "effective_model_count_at_least_five": effective_model_count >= 5.0,
        "model_dominance_at_most_35pct": model_dominance <= 0.35,
        "at_least_eight_hugging_face_ids": unique_hugging_face_ids >= 8,
        "six_hour_concentration_at_most_20pct": (
            max_six_hour_share is not None and max_six_hour_share <= 0.20
        ),
    }
    return {
        "selected_blocks": int(len(plans)),
        "unique_models": int(len(counts)),
        "effective_model_count": effective_model_count,
        "model_dominance": model_dominance,
        "unique_hugging_face_ids": unique_hugging_face_ids,
        "six_hour_bins": int(len(six_hour_counts)),
        "max_six_hour_triplets": int(six_hour_counts.max()) if len(six_hour_counts) else 0,
        "max_six_hour_triplet_share": max_six_hour_share,
        "structural_transport_gates": structural_gates,
        "structural_transport_gates_pass": all(structural_gates.values()),
        "ranking_position_min": int(pd.to_numeric(plans["ranking_position"]).min()),
        "ranking_position_max": int(pd.to_numeric(plans["ranking_position"]).max()),
        "candidate_rows": int(len(eligibility)),
        "eligible_rows": int(eligibility["eligible"].sum()) if len(eligibility) else 0,
        "open_weight_boundary": (
            "Support uses nonempty OpenRouter Hugging Face ids. A separate license audit is "
            "required before calling every selected model open source."
        ),
        "open_source_language_ready": False,
    }


def gate_summary(
    attempts: pd.DataFrame,
    eligibility: pd.DataFrame,
    *,
    simulations: int = RANDOMIZATION_DRAWS,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_plans, selected = prepare_plans(eligibility)
    triplets = (
        selected[["triplet_id", "triplet_sequence"]].drop_duplicates()
        if not selected.empty
        else pd.DataFrame(columns=["triplet_id", "triplet_sequence"])
    )
    horizon_ids = set(
        triplets.sort_values("triplet_sequence").head(TARGET_TRIPLETS)["triplet_id"].astype(str)
    )
    horizon_plans = selected.loc[selected["triplet_id"].astype(str).isin(horizon_ids)].copy()
    audit, first = assignment_audit(attempts, selected)
    ready = len(triplets) >= TARGET_TRIPLETS
    horizon_audit = audit.loc[audit["triplet_sequence"].le(TARGET_TRIPLETS)].copy()
    planned_horizon_blocks = int(len(horizon_audit) * len(POLICIES))
    metadata_auditable = (
        int(horizon_audit["treatment_metadata_auditable_blocks"].sum()) if len(horizon_audit) else 0
    )
    metadata_passes = (
        int(horizon_audit["treatment_metadata_passes"].sum()) if len(horizon_audit) else 0
    )
    recorded_first_blocks = (
        int(horizon_audit["recorded_first_position_blocks"].sum()) if len(horizon_audit) else 0
    )
    summary = {
        "study_id": STUDY_ID,
        "evidence_status": (
            "fixed_horizon_release_ready" if ready else "fixed_horizon_power_gated"
        ),
        "planned_triplets": int(len(triplets)),
        "planned_first_position_blocks": int(len(triplets) * 3),
        "target_triplets": TARGET_TRIPLETS,
        "target_first_position_blocks": TARGET_TRIPLETS * 3,
        "remaining_triplets": max(0, TARGET_TRIPLETS - len(triplets)),
        "release_ready": ready,
        "outcomes_released": ready,
        "outcome_access": (
            "released_fixed_horizon" if ready else "not_queried_by_fixed_horizon_gate"
        ),
        "complete_assignment_triplets": int(audit["complete_assignment"].sum())
        if len(audit)
        else 0,
        "horizon_complete_assignment_triplets": int(horizon_audit["complete_assignment"].sum())
        if len(horizon_audit)
        else 0,
        "horizon_plan_compliance_rate": float(horizon_audit["plan_compliance"].mean())
        if len(horizon_audit)
        else None,
        "horizon_replay_rate": (
            float(horizon_audit["replay_passes"].sum() / horizon_audit["replay_blocks"].sum())
            if len(horizon_audit) and horizon_audit["replay_blocks"].sum()
            else None
        ),
        "horizon_recorded_first_position_blocks": recorded_first_blocks,
        "horizon_treatment_metadata_auditable_blocks": metadata_auditable,
        "horizon_treatment_metadata_audit_coverage": (
            metadata_auditable / planned_horizon_blocks if planned_horizon_blocks else None
        ),
        "horizon_treatment_metadata_passes": metadata_passes,
        "horizon_treatment_metadata_pass_rate_among_auditable": (
            metadata_passes / metadata_auditable if metadata_auditable else None
        ),
        "horizon_legacy_treatment_metadata_unverified_blocks": int(
            horizon_audit["legacy_unverified_blocks"].sum()
        )
        if len(horizon_audit)
        else 0,
        "horizon_missing_first_position_records": max(
            0, planned_horizon_blocks - recorded_first_blocks
        ),
        "support": _support_summary(horizon_plans if ready else selected, all_plans),
        "randomization_draws": simulations,
        "identification": (
            "The first 120 prospectively planned eligible triplets form a fixed horizon. "
            "Within each triplet, the three policies are assigned once each to three sampled "
            "models, so first-position policy contrasts use blocked randomization."
        ),
        "claim_boundary": (
            "The result identifies owned-account policy effects for sampled eligible models. "
            "It does not identify market-wide flow, router intent, provider cost, or welfare."
        ),
        "legacy_metadata_boundary": (
            "Early triplets without row-level provider-order lengths remain in the fixed "
            "horizon and are reported as legacy-unverified; future collector rows carry all "
            "provider-control counts."
        ),
    }
    return summary, audit, first, horizon_plans


def _triplet_outcome_matrix(outcomes: pd.DataFrame) -> np.ndarray:
    """Return one fixed three-unit outcome vector per randomized triplet."""
    vectors: list[np.ndarray] = []
    for _, group in outcomes.groupby("triplet_id", sort=False):
        if len(group) != len(POLICIES):
            raise RuntimeError("H95 triplet does not contain exactly three planned units")
        if set(group["assigned_first_policy"].astype(str)) != set(POLICIES):
            raise RuntimeError("H95 triplet does not contain one assignment per policy")
        values = group.sort_values("model_id")["primary_success"].to_numpy(dtype=float)
        if not np.isfinite(values).all() or not np.isin(values, (0.0, 1.0)).all():
            raise RuntimeError("exact H95 inference requires complete binary outcomes")
        vectors.append(values)
    return np.stack(vectors) if vectors else np.empty((0, len(POLICIES)))


def _exact_blocked_randomization_pvalues(
    outcomes: pd.DataFrame,
) -> dict[str, tuple[float, float]]:
    """Enumerate each block's six assignments and convolve their exact laws."""
    values = _triplet_outcome_matrix(outcomes)
    if not len(values):
        return {name: (np.nan, np.nan) for name, *_ in COMPARISONS}
    permutations = np.asarray(list(itertools.permutations(range(3))), dtype=np.int8)
    policy_index = {policy: index for index, policy in enumerate(POLICIES)}
    tolerance = 1e-15
    results: dict[str, tuple[float, float]] = {}
    for name, positive, negative, _ in COMPARISONS:
        distribution = np.asarray([1.0])
        pos_index = policy_index[positive]
        neg_index = policy_index[negative]
        for vector in values:
            local = vector[permutations[:, pos_index]] - vector[permutations[:, neg_index]]
            kernel = np.asarray([np.mean(local == value) for value in (-1.0, 0.0, 1.0)])
            distribution = np.convolve(distribution, kernel)
        support = np.arange(-len(values), len(values) + 1)
        observed_sum = float(
            outcomes.loc[outcomes["assigned_first_policy"].eq(positive), "primary_success"].sum()
            - outcomes.loc[outcomes["assigned_first_policy"].eq(negative), "primary_success"].sum()
        )
        support_mass = float(math.fsum(distribution.tolist()))
        if not math.isclose(support_mass, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise RuntimeError(f"exact H95 randomization support has mass {support_mass}")
        greater = float(math.fsum(distribution[support >= observed_sum - tolerance].tolist()))
        two_sided = float(
            math.fsum(distribution[np.abs(support) >= abs(observed_sum) - tolerance].tolist())
        )
        results[name] = greater, two_sided
    return results


def _monte_carlo_randomization_pvalues(
    outcomes: pd.DataFrame,
    *,
    simulations: int,
    seed: int = 20260717,
) -> dict[str, tuple[float, float]]:
    """Retain a fixed Monte Carlo audit without using it for published tails."""
    if simulations <= 0:
        return {name: (np.nan, np.nan) for name, *_ in COMPARISONS}
    values = _triplet_outcome_matrix(outcomes)
    permutations = np.asarray(list(itertools.permutations(range(3))), dtype=np.int8)
    rng = np.random.default_rng(seed)
    policy_sums = np.zeros((simulations, len(POLICIES)), dtype=float)
    for vector in values:
        mapping = permutations[rng.integers(0, len(permutations), size=simulations)]
        policy_sums += vector[mapping]
    policy_means = policy_sums / len(values)
    policy_index = {policy: index for index, policy in enumerate(POLICIES)}
    results: dict[str, tuple[float, float]] = {}
    for name, positive, negative, _ in COMPARISONS:
        observed = float(
            outcomes.loc[outcomes["assigned_first_policy"].eq(positive), "primary_success"].mean()
            - outcomes.loc[outcomes["assigned_first_policy"].eq(negative), "primary_success"].mean()
        )
        null = policy_means[:, policy_index[positive]] - policy_means[:, policy_index[negative]]
        greater = float((1 + np.sum(null >= observed - 1e-15)) / (simulations + 1))
        two_sided = float((1 + np.sum(np.abs(null) >= abs(observed) - 1e-15)) / (simulations + 1))
        results[name] = greater, two_sided
    return results


def _paired_interval(
    differences: pd.Series,
    *,
    alpha: float,
) -> tuple[float, float, float, float]:
    values = pd.to_numeric(differences, errors="coerce")
    if len(values) < 2 or values.isna().any():
        return np.nan, np.nan, np.nan, np.nan
    estimate = float(values.mean())
    standard_error = float(values.std(ddof=1) / math.sqrt(len(values)))
    critical = float(student_t.ppf(1.0 - alpha / 2.0, df=len(values) - 1))
    return (
        estimate,
        standard_error,
        estimate - critical * standard_error,
        estimate + critical * standard_error,
    )


def _leave_one_model_out(
    outcomes: pd.DataFrame,
    contrasts: pd.DataFrame,
) -> pd.DataFrame:
    """Drop every triplet containing a model, preserving randomized blocks."""
    rows: list[dict[str, Any]] = []
    full_estimates = contrasts.set_index("estimand")["success_difference"].to_dict()
    for model_id in sorted(outcomes["model_id"].astype(str).unique()):
        omitted_triplets = set(
            outcomes.loc[outcomes["model_id"].astype(str).eq(model_id), "triplet_id"]
            .astype(str)
            .tolist()
        )
        retained = outcomes.loc[~outcomes["triplet_id"].astype(str).isin(omitted_triplets)]
        wide = retained.pivot(
            index="triplet_id",
            columns="assigned_first_policy",
            values="primary_success",
        )
        for name, positive, negative, primary in COMPARISONS:
            differences = wide[positive] - wide[negative] if len(wide) else pd.Series(dtype=float)
            estimate = (
                float(differences.mean())
                if len(differences) and not differences.isna().any()
                else np.nan
            )
            full = float(full_estimates.get(name, np.nan))
            if np.isfinite(full) and np.isfinite(estimate):
                sign_stable = bool(
                    (full > 0 and estimate > 0)
                    or (full < 0 and estimate < 0)
                    or (full == 0 and estimate == 0)
                )
            else:
                sign_stable = False
            rows.append(
                {
                    "estimand": name,
                    "primary": primary,
                    "omitted_model_id": model_id,
                    "omitted_triplets": len(omitted_triplets),
                    "retained_triplets": int(len(wide)),
                    "full_success_difference": full,
                    "lomo_success_difference": estimate,
                    "sign_stable": sign_stable,
                }
            )
    return pd.DataFrame(rows)


def analyze_released(
    outcome_attempts: pd.DataFrame,
    horizon_plans: pd.DataFrame,
    summary: dict[str, Any],
    *,
    simulations: int = RANDOMIZATION_DRAWS,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    attempts = prepare_assignment_attempts(outcome_attempts)
    if "outcome" not in attempts:
        attempts["outcome"] = pd.NA
    first = _annotate_treatment_metadata(attempts.loc[attempts["policy_order"].eq(0)].copy())
    primary_keys = ["triplet_id", "model_id"]
    if len(first):
        first["duplicate_primary_records"] = first.groupby(primary_keys)["event_id"].transform(
            "size"
        )
        first = first.sort_values(["_observed", "event_id"]).drop_duplicates(
            primary_keys, keep="first"
        )
    else:
        first["duplicate_primary_records"] = pd.Series(dtype=int)
    observed_columns = [
        "triplet_id",
        "model_id",
        "policy",
        "outcome",
        "event_id",
        "duplicate_primary_records",
        "treatment_metadata_auditable",
        "treatment_metadata_pass",
    ]
    observed = first.reindex(columns=observed_columns).rename(
        columns={"policy": "observed_first_policy", "outcome": "recorded_outcome"}
    )
    plan = horizon_plans[
        [
            "triplet_id",
            "triplet_sequence",
            "planned_at",
            "model_id",
            "assigned_first_policy",
            "hugging_face_id",
            "ranking_position",
        ]
    ].copy()
    outcomes = plan.merge(
        observed,
        on=["triplet_id", "model_id"],
        how="left",
        validate="one_to_one",
    )
    outcomes["attempt_recorded"] = outcomes["event_id"].notna()
    outcomes["assignment_compliant"] = (
        outcomes["observed_first_policy"].eq(outcomes["assigned_first_policy"]).fillna(False)
    )
    outcomes["duplicate_primary_record"] = outcomes["duplicate_primary_records"].fillna(0).gt(1)
    outcomes["treatment_metadata_auditable"] = (
        outcomes["treatment_metadata_auditable"].astype("boolean").fillna(False).astype(bool)
    )
    outcomes["treatment_metadata_pass"] = outcomes["treatment_metadata_pass"].astype("boolean")
    outcomes["treatment_metadata_failure"] = outcomes["treatment_metadata_auditable"] & ~outcomes[
        "treatment_metadata_pass"
    ].fillna(False).astype(bool)
    outcomes["legacy_treatment_metadata_unverified"] = (
        outcomes["attempt_recorded"]
        & outcomes["assignment_compliant"]
        & ~outcomes["treatment_metadata_auditable"]
    )
    outcomes["missing_primary_attempt"] = ~outcomes["attempt_recorded"]
    outcomes["structural_failure"] = (
        outcomes["missing_primary_attempt"]
        | ~outcomes["assignment_compliant"]
        | outcomes["duplicate_primary_record"]
        | outcomes["treatment_metadata_failure"]
    )
    outcomes["recorded_outcome"] = outcomes["recorded_outcome"].astype("string").str.lower()
    outcomes["binary_recorded_outcome"] = outcomes["recorded_outcome"].map(BINARY_OUTCOME_VALUES)
    outcomes["measurement_missing"] = (
        ~outcomes["structural_failure"] & outcomes["binary_recorded_outcome"].isna()
    )
    outcomes["primary_success"] = outcomes["binary_recorded_outcome"].astype(float)
    outcomes.loc[outcomes["structural_failure"], "primary_success"] = 0.0
    complete_binary_outcomes = not outcomes["primary_success"].isna().any()

    panel_rows: list[dict[str, Any]] = []
    for policy in POLICIES:
        arm = outcomes.loc[outcomes["assigned_first_policy"].eq(policy)]
        successes = int(arm["primary_success"].fillna(0.0).sum())
        n = len(arm)
        measurement_missing = int(arm["measurement_missing"].sum())
        arm_complete = measurement_missing == 0
        low, high = (
            proportion_confint(successes, n, method="wilson")
            if arm_complete and n
            else (np.nan, np.nan)
        )
        missing_records = int(arm["missing_primary_attempt"].sum())
        legacy = arm["legacy_treatment_metadata_unverified"]
        sensitivity_unknown = arm["measurement_missing"] | legacy
        verified_successes = float(
            arm.loc[~sensitivity_unknown, "primary_success"].fillna(0.0).sum()
        )
        panel_rows.append(
            {
                "policy": policy,
                "assigned_blocks": n,
                "successes_itt_known": successes,
                "success_rate_itt": successes / n if arm_complete else np.nan,
                "success_ci_low": float(low),
                "success_ci_high": float(high),
                "measurement_missing_outcomes": measurement_missing,
                "missing_primary_attempts": missing_records,
                "structural_failures": int(arm["structural_failure"].sum()),
                "success_rate_measurement_lower_bound": successes / n,
                "success_rate_measurement_upper_bound": (successes + measurement_missing) / n,
                "missing_record_sensitivity_lower_bound": successes / n,
                "missing_record_sensitivity_upper_bound": (
                    successes + measurement_missing + missing_records
                )
                / n,
                "treatment_verification_lower_bound": verified_successes / n,
                "treatment_verification_upper_bound": (
                    verified_successes + int(sensitivity_unknown.sum())
                )
                / n,
                "assignment_compliance_rate": float(arm["assignment_compliant"].mean()),
                "treatment_metadata_audit_coverage": float(
                    arm["treatment_metadata_auditable"].mean()
                ),
                "treatment_metadata_pass_rate_among_auditable": (
                    float(
                        arm.loc[
                            arm["treatment_metadata_auditable"],
                            "treatment_metadata_pass",
                        ]
                        .astype(bool)
                        .mean()
                    )
                    if arm["treatment_metadata_auditable"].any()
                    else np.nan
                ),
                "legacy_treatment_metadata_unverified": int(legacy.sum()),
            }
        )
    panel = pd.DataFrame(panel_rows)
    exact_pvalues = (
        _exact_blocked_randomization_pvalues(outcomes)
        if complete_binary_outcomes
        else {name: (np.nan, np.nan) for name, *_ in COMPARISONS}
    )
    monte_carlo_pvalues = (
        _monte_carlo_randomization_pvalues(outcomes, simulations=simulations)
        if complete_binary_outcomes and simulations
        else {name: (np.nan, np.nan) for name, *_ in COMPARISONS}
    )
    contrast_rows: list[dict[str, Any]] = []
    wide = outcomes.pivot(
        index="triplet_id", columns="assigned_first_policy", values="primary_success"
    )
    for name, positive, negative, primary in COMPARISONS:
        differences = wide[positive] - wide[negative]
        if complete_binary_outcomes:
            estimate, standard_error, ci_low, ci_high = _paired_interval(
                differences, alpha=PRIMARY_FWER_ALPHA
            )
            _, _, simultaneous_low, simultaneous_high = _paired_interval(
                differences,
                alpha=(PRIMARY_FWER_ALPHA / 2.0) if primary else PRIMARY_FWER_ALPHA,
            )
        else:
            estimate = standard_error = ci_low = ci_high = np.nan
            simultaneous_low = simultaneous_high = np.nan
        pos = panel.loc[panel["policy"].eq(positive)].iloc[0]
        neg = panel.loc[panel["policy"].eq(negative)].iloc[0]
        greater, two_sided = exact_pvalues[name]
        greater_mc, two_sided_mc = monte_carlo_pvalues[name]
        mc_error = (
            float(max(abs(greater_mc - greater), abs(two_sided_mc - two_sided)))
            if np.isfinite(greater_mc) and np.isfinite(greater)
            else np.nan
        )
        contrast_rows.append(
            {
                "estimand": name,
                "positive_policy": positive,
                "negative_policy": negative,
                "primary": primary,
                "triplets": len(differences),
                "success_difference": estimate,
                "paired_standard_error": standard_error,
                "paired_t_ci_low": ci_low,
                "paired_t_ci_high": ci_high,
                "paired_t_simultaneous_ci_low": simultaneous_low if primary else np.nan,
                "paired_t_simultaneous_ci_high": simultaneous_high if primary else np.nan,
                "measurement_missingness_lower_bound": (
                    pos["success_rate_measurement_lower_bound"]
                    - neg["success_rate_measurement_upper_bound"]
                ),
                "measurement_missingness_upper_bound": (
                    pos["success_rate_measurement_upper_bound"]
                    - neg["success_rate_measurement_lower_bound"]
                ),
                "missing_record_sensitivity_lower_bound": (
                    pos["missing_record_sensitivity_lower_bound"]
                    - neg["missing_record_sensitivity_upper_bound"]
                ),
                "missing_record_sensitivity_upper_bound": (
                    pos["missing_record_sensitivity_upper_bound"]
                    - neg["missing_record_sensitivity_lower_bound"]
                ),
                "treatment_verification_lower_bound": (
                    pos["treatment_verification_lower_bound"]
                    - neg["treatment_verification_upper_bound"]
                ),
                "treatment_verification_upper_bound": (
                    pos["treatment_verification_upper_bound"]
                    - neg["treatment_verification_lower_bound"]
                ),
                "randomization_p_greater": greater,
                "randomization_p_two_sided": two_sided,
                "randomization_p_greater_mc_check": greater_mc,
                "randomization_p_two_sided_mc_check": two_sided_mc,
                "randomization_mc_max_abs_error": mc_error,
                "randomization_mc_audit_pass": (
                    bool(mc_error <= RANDOMIZATION_MC_AUDIT_TOLERANCE)
                    if np.isfinite(mc_error)
                    else np.nan
                ),
            }
        )
    contrasts = pd.DataFrame(contrast_rows)
    primary_mask = contrasts["primary"]
    contrasts["holm_p_greater"] = np.nan
    primary_pvalues = contrasts.loc[primary_mask, "randomization_p_greater"]
    if primary_pvalues.notna().all():
        contrasts.loc[primary_mask, "holm_p_greater"] = multipletests(
            primary_pvalues, method="holm"
        )[1]
    if simulations >= RANDOMIZATION_DRAWS and complete_binary_outcomes:
        audit_pass = contrasts["randomization_mc_audit_pass"].fillna(False).astype(bool)
        if not audit_pass.all():
            worst = float(contrasts["randomization_mc_max_abs_error"].max())
            raise RuntimeError(
                "exact-versus-Monte-Carlo H95 randomization audit failed: "
                f"max absolute error {worst:.6f} exceeds "
                f"{RANDOMIZATION_MC_AUDIT_TOLERANCE:.6f}"
            )

    model_rates = (
        outcomes.groupby(["model_id", "assigned_first_policy"], as_index=False)
        .agg(
            assigned_blocks=("primary_success", "size"),
            successes_known=("primary_success", lambda values: values.fillna(0.0).sum()),
            success_rate=(
                "primary_success",
                lambda values: values.mean() if values.notna().all() else np.nan,
            ),
            measurement_missing_outcomes=("measurement_missing", "sum"),
            missing_primary_attempts=("missing_primary_attempt", "sum"),
            structural_failures=("structural_failure", "sum"),
            legacy_treatment_metadata_unverified=(
                "legacy_treatment_metadata_unverified",
                "sum",
            ),
        )
        .rename(columns={"assigned_first_policy": "policy"})
    )
    lomo = _leave_one_model_out(outcomes, contrasts)
    primary_lomo = lomo.loc[lomo["primary"]].copy()
    lomo_direction_stability = {
        name: bool(group["sign_stable"].all())
        for name, group in primary_lomo.groupby("estimand", sort=False)
    }
    lomo_gate_pass = len(lomo_direction_stability) == 2 and all(lomo_direction_stability.values())
    support = dict(summary.get("support") or {})
    support["lomo_primary_direction_stability"] = lomo_direction_stability
    support["lomo_primary_direction_stability_pass"] = lomo_gate_pass
    support["broad_multi_model_transport_ready"] = bool(
        support.get("structural_transport_gates_pass") and lomo_gate_pass
    )
    summary = summary | {
        "evidence_status": "fixed_horizon_outcomes_released",
        "outcomes_released": True,
        "primary_missing_attempts": int(outcomes["missing_primary_attempt"].sum()),
        "primary_measurement_missing_outcomes": int(outcomes["measurement_missing"].sum()),
        "complete_binary_outcomes": complete_binary_outcomes,
        "point_inference_suppressed_for_measurement_missingness": bool(
            not complete_binary_outcomes
        ),
        "primary_assignment_compliance_rate": float(outcomes["assignment_compliant"].mean()),
        "primary_treatment_metadata_audit_coverage": float(
            outcomes["treatment_metadata_auditable"].mean()
        ),
        "primary_treatment_metadata_pass_rate_among_auditable": (
            float(
                outcomes.loc[
                    outcomes["treatment_metadata_auditable"],
                    "treatment_metadata_pass",
                ]
                .astype(bool)
                .mean()
            )
            if outcomes["treatment_metadata_auditable"].any()
            else None
        ),
        "primary_legacy_treatment_metadata_unverified": int(
            outcomes["legacy_treatment_metadata_unverified"].sum()
        ),
        "randomization_inference": (
            "exact Fisher sharp-null tails from convolution of each triplet's six "
            "allowed assignments; Monte Carlo is an implementation audit only"
        ),
        "randomization_mc_audit_tolerance": RANDOMIZATION_MC_AUDIT_TOLERANCE,
        "randomization_mc_audit_enforced": bool(
            simulations >= RANDOMIZATION_DRAWS and complete_binary_outcomes
        ),
        "descriptive_uncertainty": (
            "paired t intervals over realized triplets; Bonferroni 95% familywise "
            "intervals over the two primary contrasts; not randomization-CI inversion"
        ),
        "support": support,
    }
    audit_columns = [
        "triplet_id",
        "triplet_sequence",
        "planned_at",
        "model_id",
        "assigned_first_policy",
        "observed_first_policy",
        "recorded_outcome",
        "attempt_recorded",
        "assignment_compliant",
        "duplicate_primary_record",
        "treatment_metadata_auditable",
        "treatment_metadata_pass",
        "legacy_treatment_metadata_unverified",
        "structural_failure",
        "measurement_missing",
        "primary_success",
    ]
    return panel, model_rates, contrasts, lomo, outcomes[audit_columns], summary


def _blinded_outputs() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    panel = pd.DataFrame(
        [
            {
                "policy": policy,
                "assigned_blocks": np.nan,
                "successes_itt_known": np.nan,
                "success_rate_itt": np.nan,
            }
            for policy in POLICIES
        ]
    )
    contrasts = pd.DataFrame(
        [
            {
                "estimand": name,
                "positive_policy": positive,
                "negative_policy": negative,
                "primary": primary,
                "success_difference": np.nan,
                "randomization_p_greater": np.nan,
            }
            for name, positive, negative, primary in COMPARISONS
        ]
    )
    return panel, pd.DataFrame(), contrasts, pd.DataFrame(), pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT, *, simulations: int = RANDOMIZATION_DRAWS) -> dict[str, Any]:
    try:
        eligibility = data.q(
            f"""
            select * from read_parquet(
              '{data.table_glob("router_replication_eligibility")}',
              union_by_name=true
            ) where study_id = '{STUDY_ID}'
            """
        ).df()
    except Exception:
        eligibility = pd.DataFrame()
    try:
        assignment_attempts = data.q(
            f"""
            select source, event_id, run_ts, observed_at, study_id, model_id,
                   policy, metadata_json
            from read_parquet(
              '{data.table_glob("router_route_attempts")}',
              union_by_name=true
            ) where study_id = '{STUDY_ID}'
            """
        ).df()
    except Exception:
        assignment_attempts = pd.DataFrame(
            columns=[
                "source",
                "event_id",
                "run_ts",
                "observed_at",
                "study_id",
                "model_id",
                "policy",
                "metadata_json",
            ]
        )
    prepared = prepare_assignment_attempts(assignment_attempts)
    summary, audit, _, horizon_plans = gate_summary(prepared, eligibility, simulations=simulations)
    if not summary["release_ready"]:
        panel, model_rates, contrasts, lomo, outcome_audit = _blinded_outputs()
    else:
        outcome_attempts = data.q(
            f"""
            select * from read_parquet(
              '{data.table_glob("router_route_attempts")}',
              union_by_name=true
            ) where study_id = '{STUDY_ID}'
            """
        ).df()
        panel, model_rates, contrasts, lomo, outcome_audit, summary = analyze_released(
            outcome_attempts,
            horizon_plans,
            summary,
            simulations=simulations,
        )
    save(audit, out_dir, "h95_assignment_audit")
    save(panel, out_dir, "h95_policy_panel")
    save(model_rates, out_dir, "h95_model_policy_panel")
    save(contrasts, out_dir, "h95_contrasts")
    save(lomo, out_dir, "h95_leave_one_model_out")
    save(outcome_audit, out_dir, "h95_primary_outcome_audit")
    save_json(summary, out_dir, "h95_summary")
    return summary
