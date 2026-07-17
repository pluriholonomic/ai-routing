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
        "assignment_probability_first": None,
    }
    for field, default in fields.items():
        out[field] = metadata.map(
            lambda item, field=field, default=default: item.get(field, default)
        )
    for field in ["policy_order", "ranking_position", "assignment_probability_first"]:
        out[field] = pd.to_numeric(out[field], errors="coerce")
    return out


def prepare_plans(eligibility: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    empty_selected = pd.DataFrame(
        columns=[
            "triplet_id",
            "triplet_sequence",
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
        frame["selected_for_triplet"]
        & frame["eligible"]
        & frame["triplet_id"].notna()
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
            triplets[["triplet_id", "triplet_sequence"]],
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
    ]
    if selected_plans.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame()
    first = attempts.loc[attempts["policy_order"].eq(0)].copy() if not attempts.empty else attempts
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
        records.append(
            {
                "triplet_id": str(triplet_id),
                "triplet_sequence": int(plan["triplet_sequence"].iloc[0]),
                "planned_models": int(plan["model_id"].nunique()),
                "recorded_blocks": int(observed["block_id"].nunique()),
                "complete_assignment": bool(complete),
                "first_policy_balance": set(observed_first["policy"].astype(str))
                == set(POLICIES),
                "plan_compliance": observed_pairs == expected_pairs,
                "replay_passes": int(sum(replay)),
                "replay_blocks": len(replay),
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
        }
    counts = plans["model_id"].astype(str).value_counts()
    shares = counts / counts.sum()
    return {
        "selected_blocks": int(len(plans)),
        "unique_models": int(len(counts)),
        "effective_model_count": float(1.0 / np.square(shares).sum()),
        "model_dominance": float(shares.max()),
        "unique_hugging_face_ids": int(plans["hugging_face_id"].nunique()),
        "ranking_position_min": int(pd.to_numeric(plans["ranking_position"]).min()),
        "ranking_position_max": int(pd.to_numeric(plans["ranking_position"]).max()),
        "candidate_rows": int(len(eligibility)),
        "eligible_rows": int(eligibility["eligible"].sum()) if len(eligibility) else 0,
        "open_weight_boundary": (
            "Support uses nonempty OpenRouter Hugging Face ids. A separate license audit is "
            "required before calling every selected model open source."
        ),
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
        "horizon_complete_assignment_triplets": int(
            horizon_audit["complete_assignment"].sum()
        )
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
    }
    return summary, audit, first, horizon_plans


def _randomization_pvalues(
    outcomes: pd.DataFrame,
    *,
    simulations: int,
    seed: int = 20260717,
) -> dict[str, tuple[float, float]]:
    triplet_ids = outcomes["triplet_id"].drop_duplicates().tolist()
    model_outcomes: list[np.ndarray] = []
    for triplet_id in triplet_ids:
        group = outcomes.loc[outcomes["triplet_id"].eq(triplet_id)].sort_values("model_id")
        model_outcomes.append(group["success"].to_numpy(dtype=float))
    values = np.stack(model_outcomes)
    permutations = np.asarray(list(itertools.permutations(range(3))), dtype=np.int8)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(permutations), size=(simulations, len(values)))
    policy_sums = np.zeros((simulations, 3), dtype=float)
    for triplet_index in range(len(values)):
        mapping = permutations[draws[:, triplet_index]]
        for policy_index in range(3):
            policy_sums[:, policy_index] += values[
                triplet_index, mapping[:, policy_index]
            ]
    policy_means = policy_sums / len(values)
    policy_index = {policy: index for index, policy in enumerate(POLICIES)}
    results: dict[str, tuple[float, float]] = {}
    for name, positive, negative, _ in COMPARISONS:
        observed = (
            outcomes.loc[outcomes["assigned_first_policy"].eq(positive), "success"].mean()
            - outcomes.loc[outcomes["assigned_first_policy"].eq(negative), "success"].mean()
        )
        null = policy_means[:, policy_index[positive]] - policy_means[:, policy_index[negative]]
        greater = float((1 + np.sum(null >= observed)) / (simulations + 1))
        two_sided = float((1 + np.sum(np.abs(null) >= abs(observed))) / (simulations + 1))
        results[name] = greater, two_sided
    return results


def analyze_released(
    outcome_attempts: pd.DataFrame,
    horizon_plans: pd.DataFrame,
    summary: dict[str, Any],
    *,
    simulations: int = RANDOMIZATION_DRAWS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    attempts = prepare_assignment_attempts(outcome_attempts)
    attempts["success_recorded"] = attempts["outcome"].astype(str).eq("succeeded")
    first = attempts.loc[attempts["policy_order"].eq(0)].copy()
    observed = first[
        ["triplet_id", "model_id", "policy", "success_recorded", "event_id"]
    ].rename(columns={"policy": "observed_first_policy"})
    plan = horizon_plans[
        [
            "triplet_id",
            "triplet_sequence",
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
    outcomes["assignment_compliant"] = outcomes["observed_first_policy"].eq(
        outcomes["assigned_first_policy"]
    )
    outcomes["success"] = (
        outcomes["success_recorded"].fillna(False) & outcomes["assignment_compliant"]
    ).astype(int)
    outcomes["missing_primary_attempt"] = ~outcomes["attempt_recorded"]

    panel_rows: list[dict[str, Any]] = []
    for policy in POLICIES:
        arm = outcomes.loc[outcomes["assigned_first_policy"].eq(policy)]
        successes = int(arm["success"].sum())
        n = len(arm)
        low, high = proportion_confint(successes, n, method="wilson")
        missing = int(arm["missing_primary_attempt"].sum())
        panel_rows.append(
            {
                "policy": policy,
                "assigned_blocks": n,
                "successes_missing_as_failure": successes,
                "success_rate_missing_as_failure": successes / n,
                "success_ci_low": float(low),
                "success_ci_high": float(high),
                "missing_primary_attempts": missing,
                "success_rate_lower_bound": successes / n,
                "success_rate_upper_bound": (successes + missing) / n,
                "assignment_compliance_rate": float(arm["assignment_compliant"].mean()),
            }
        )
    panel = pd.DataFrame(panel_rows)
    pvalues = _randomization_pvalues(outcomes, simulations=simulations)
    contrast_rows: list[dict[str, Any]] = []
    for name, positive, negative, primary in COMPARISONS:
        wide = outcomes.pivot(
            index="triplet_id", columns="assigned_first_policy", values="success"
        )
        differences = wide[positive] - wide[negative]
        estimate = float(differences.mean())
        standard_error = float(differences.std(ddof=1) / math.sqrt(len(differences)))
        pos = panel.loc[panel["policy"].eq(positive)].iloc[0]
        neg = panel.loc[panel["policy"].eq(negative)].iloc[0]
        greater, two_sided = pvalues[name]
        contrast_rows.append(
            {
                "estimand": name,
                "positive_policy": positive,
                "negative_policy": negative,
                "primary": primary,
                "triplets": len(differences),
                "success_difference": estimate,
                "paired_standard_error": standard_error,
                "normal_ci_low": estimate - 1.96 * standard_error,
                "normal_ci_high": estimate + 1.96 * standard_error,
                "missingness_lower_bound": (
                    pos["success_rate_lower_bound"] - neg["success_rate_upper_bound"]
                ),
                "missingness_upper_bound": (
                    pos["success_rate_upper_bound"] - neg["success_rate_lower_bound"]
                ),
                "randomization_p_greater": greater,
                "randomization_p_two_sided": two_sided,
            }
        )
    contrasts = pd.DataFrame(contrast_rows)
    primary_mask = contrasts["primary"]
    contrasts["holm_p_greater"] = np.nan
    contrasts.loc[primary_mask, "holm_p_greater"] = multipletests(
        contrasts.loc[primary_mask, "randomization_p_greater"], method="holm"
    )[1]

    model_rates = (
        outcomes.groupby(["model_id", "assigned_first_policy"], as_index=False)
        .agg(
            assigned_blocks=("success", "size"),
            success_rate=("success", "mean"),
            missing_primary_attempts=("missing_primary_attempt", "sum"),
        )
        .rename(columns={"assigned_first_policy": "policy"})
    )
    summary = summary | {
        "evidence_status": "fixed_horizon_outcomes_released",
        "outcomes_released": True,
        "primary_missing_attempts": int(outcomes["missing_primary_attempt"].sum()),
        "primary_assignment_compliance_rate": float(
            outcomes["assignment_compliant"].mean()
        ),
    }
    return panel, model_rates, contrasts, summary


def _blinded_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel = pd.DataFrame(
        [
            {
                "policy": policy,
                "assigned_blocks": np.nan,
                "successes_missing_as_failure": np.nan,
                "success_rate_missing_as_failure": np.nan,
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
    return panel, pd.DataFrame(), contrasts


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
    summary, audit, _, horizon_plans = gate_summary(
        prepared, eligibility, simulations=simulations
    )
    if not summary["release_ready"]:
        panel, model_rates, contrasts = _blinded_outputs()
    else:
        outcome_attempts = data.q(
            f"""
            select * from read_parquet(
              '{data.table_glob("router_route_attempts")}',
              union_by_name=true
            ) where study_id = '{STUDY_ID}'
            """
        ).df()
        panel, model_rates, contrasts, summary = analyze_released(
            outcome_attempts,
            horizon_plans,
            summary,
            simulations=simulations,
        )
    save(audit, out_dir, "h95_assignment_audit")
    save(panel, out_dir, "h95_policy_panel")
    save(model_rates, out_dir, "h95_model_policy_panel")
    save(contrasts, out_dir, "h95_contrasts")
    save_json(summary, out_dir, "h95_summary")
    return summary
