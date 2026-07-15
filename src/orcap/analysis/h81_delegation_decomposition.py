"""H81 — randomized decomposition of fallback and hidden-selection value."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h80_matched_quote_firmness import first_balanced_prefix, holm_adjust
from .missingness_bounds import bounded_mean, difference_bounds, ht_bounded_mean

STUDY_ID = "openrouter-fallback-selection-decomposition-v1"
POLICIES = (
    "delegated_default",
    "price_only_no_fallback",
    "price_order_fallback",
)
COMPARISONS = (
    ("fallback_option", "price_order_fallback", "price_only_no_fallback", True),
    ("hidden_selection", "delegated_default", "price_order_fallback", True),
    ("total_delegation", "delegated_default", "price_only_no_fallback", False),
)
MIN_FIRST_POSITION_PER_POLICY = 40
RANDOMIZATION_DRAWS = 100_000


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def prepare_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame[frame["study_id"].astype(str).eq(STUDY_ID)].copy()
    if {"source", "event_id"}.issubset(out.columns):
        out = out.sort_values(["source", "event_id", "run_ts"]).drop_duplicates(
            ["source", "event_id"], keep="last"
        )
    metadata = out.get("metadata_json", pd.Series("{}", index=out.index)).map(_metadata)
    keys = (
        "block_id",
        "block_policy_count",
        "policy_order",
        "block_seed",
        "assignment_probability_first",
        "randomized_order",
        "public_provider_count",
        "public_provider_order_sha256",
        "public_cheapest_provider",
        "public_cheapest_completion_price",
        "public_quote_cost_cap_usd",
        "quote_cap_input_tokens",
        "request_timeout_ms",
        "ranking_position",
        "eligibility_run_id",
        "requested_order_length",
        "provider_only_count",
        "allow_fallbacks",
    )
    for key in keys:
        values = [item.get(key) for item in metadata]
        if key == "block_seed":
            out[key] = pd.Series(
                [str(value) if value is not None else None for value in values],
                index=out.index,
                dtype="string",
            )
        else:
            out[key] = pd.Series(values, index=out.index)
    for column in (
        "policy_order",
        "public_quote_cost_cap_usd",
        "quote_cap_input_tokens",
        "request_timeout_ms",
        "ranking_position",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["success"] = out["outcome"].astype(str).eq("succeeded")
    retry_reason = out.get("retry_reason", pd.Series("", index=out.index, dtype="string")).astype(
        "string"
    )
    out["rejected_429"] = (~out["success"]) & retry_reason.fillna("").str.contains("429")
    cost = pd.to_numeric(out.get("cost_usd"), errors="coerce")
    out["observed_spend_usd"] = cost.where(out["success"], 0.0)
    return out


def prepare_eligibility(
    frame: pd.DataFrame | None, attempts: pd.DataFrame
) -> tuple[pd.DataFrame, str]:
    """Normalize outcome-free candidate telemetry, with an attempts-only fallback."""
    if frame is not None and not frame.empty:
        out = frame[frame["study_id"].astype(str).eq(STUDY_ID)].copy()
        if out.empty:
            return out, "eligibility_table_empty_for_study"
        out = out.sort_values(["run_id", "model_id", "run_ts"]).drop_duplicates(
            ["run_id", "model_id"], keep="last"
        )
        for column in (
            "ranking_position",
            "evaluation_order",
            "raw_endpoint_count",
            "positive_quote_count",
            "distinct_provider_count",
            "public_min_completion_price",
            "public_max_completion_price",
            "public_quote_cost_cap_usd",
            "request_timeout_ms",
        ):
            if column in out:
                out[column] = pd.to_numeric(out[column], errors="coerce")
        out["eligible"] = out["eligible"].astype("boolean")
        return out, "candidate_eligibility_table"

    if attempts.empty:
        return pd.DataFrame(), "no_eligibility_telemetry"
    blocks = (
        attempts.sort_values(["block_id", "policy_order"])
        .drop_duplicates("block_id", keep="first")
        .copy()
    )
    if blocks.empty:
        return pd.DataFrame(), "no_eligibility_telemetry"
    run_id = blocks.get("eligibility_run_id", pd.Series(index=blocks.index, dtype=object))
    parsed = blocks["block_id"].astype(str).str.split("|", regex=False).str[1]
    blocks["run_id"] = run_id.where(run_id.notna() & run_id.astype(str).ne(""), parsed)
    blocks["ranking_position"] = pd.to_numeric(blocks.get("ranking_position"), errors="coerce")
    blocks["eligible"] = True
    blocks["exclusion_reason"] = "eligible_attempt_observed"
    blocks["observed_at"] = blocks.get(
        "observed_at", blocks.get("run_ts", pd.Series(index=blocks.index, dtype=object))
    )
    return blocks, "attempts_only_left_truncated"


def eligibility_diagnostics(
    frame: pd.DataFrame | None,
    attempts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build the H81 target-population funnel without touching outcomes."""
    candidates, telemetry_status = prepare_eligibility(frame, attempts)
    if candidates.empty:
        return (
            candidates,
            pd.DataFrame(),
            pd.DataFrame(),
            {
                "telemetry_status": telemetry_status,
                "candidate_rows": 0,
                "eligible_rows": 0,
                "eligibility_rate": None,
            },
        )

    eligible_mask = candidates["eligible"].fillna(False).astype(bool)
    eligible = candidates[eligible_mask].copy()
    model_rows = []
    for model_id, group in candidates.groupby("model_id", sort=True):
        group_eligible = group["eligible"].fillna(False).astype(bool)
        model_rows.append(
            {
                "model_id": str(model_id),
                "candidate_runs": int(group["run_id"].nunique()),
                "eligible_runs": int(group.loc[group_eligible, "run_id"].nunique()),
                "eligibility_rate": float(group_eligible.mean()),
                "minimum_ranking_position": float(
                    pd.to_numeric(group.get("ranking_position"), errors="coerce").min()
                ),
                "maximum_ranking_position": float(
                    pd.to_numeric(group.get("ranking_position"), errors="coerce").max()
                ),
            }
        )
    model_panel = pd.DataFrame(model_rows)

    run_rows = []
    eligible_sets: list[set[str]] = []
    for run_id, group in candidates.groupby("run_id", sort=True):
        group_eligible = group["eligible"].fillna(False).astype(bool)
        support = set(group.loc[group_eligible, "model_id"].astype(str))
        eligible_sets.append(support)
        run_rows.append(
            {
                "run_id": str(run_id),
                "candidate_models": int(group["model_id"].nunique()),
                "eligible_models": int(len(support)),
                "eligibility_rate": float(group_eligible.mean()),
                "eligible_model_ids": json.dumps(sorted(support), separators=(",", ":")),
            }
        )
    run_panel = pd.DataFrame(run_rows)

    if len(eligible):
        shares = eligible["model_id"].astype(str).value_counts(normalize=True).to_numpy()
        dominance = float(shares.max())
        effective_models = float(1.0 / np.square(shares).sum())
        normalized_entropy = (
            float(-(shares * np.log(shares)).sum() / math.log(len(shares)))
            if len(shares) > 1
            else 0.0
        )
    else:
        dominance = effective_models = normalized_entropy = None
    jaccards = []
    for previous, current in zip(eligible_sets, eligible_sets[1:], strict=False):
        union = previous | current
        jaccards.append(len(previous & current) / len(union) if union else 1.0)
    reasons = (
        candidates.get("exclusion_reason", pd.Series(dtype=object))
        .fillna("unknown")
        .astype(str)
        .value_counts()
        .to_dict()
    )
    ranks = pd.to_numeric(candidates.get("ranking_position"), errors="coerce")
    rank_counts = (
        candidates.assign(_rank=ranks)
        .dropna(subset=["_rank"])
        .groupby("_rank")["eligible"]
        .agg(candidate_rows="size", eligible_rows="sum")
        .reset_index()
    )
    observed = pd.to_datetime(candidates.get("observed_at"), errors="coerce", utc=True)
    span_hours = (
        float((observed.max() - observed.min()).total_seconds() / 3600)
        if observed.notna().sum() >= 2
        else 0.0
    )
    summary = {
        "telemetry_status": telemetry_status,
        "candidate_rows": int(len(candidates)),
        "eligible_rows": int(len(eligible)),
        "eligibility_rate": float(eligible_mask.mean()),
        "run_count": int(candidates["run_id"].nunique()),
        "span_hours": span_hours,
        "unique_candidate_models": int(candidates["model_id"].nunique()),
        "unique_eligible_models": int(eligible["model_id"].nunique()),
        "eligible_support_dominance": dominance,
        "eligible_effective_model_count": effective_models,
        "eligible_normalized_model_entropy": normalized_entropy,
        "mean_adjacent_support_jaccard": (float(np.mean(jaccards)) if jaccards else None),
        "mean_adjacent_support_turnover": (float(1.0 - np.mean(jaccards)) if jaccards else None),
        "exclusion_reason_counts": {str(key): int(value) for key, value in reasons.items()},
        "ranking_position_funnel": [
            {
                "ranking_position": int(row["_rank"]),
                "candidate_rows": int(row["candidate_rows"]),
                "eligible_rows": int(row["eligible_rows"]),
            }
            for _, row in rank_counts.iterrows()
        ],
        "claim_boundary": (
            "The funnel covers only resolved public ranking positions assigned to H81. "
            "It measures displayed positive-price provider eligibility and repeated model "
            "support, not the router's private eligible set or all model demand."
        ),
    }
    return candidates, model_panel, run_panel, summary


def verify_first_assignment(block: pd.DataFrame) -> bool:
    try:
        seed = int(block["block_seed"].iloc[0])
        count = int(block["block_policy_count"].dropna().iloc[0])
    except (IndexError, TypeError, ValueError):
        return False
    first = block[block["policy_order"].eq(0)]
    if count != len(POLICIES) or len(first) != 1:
        return False
    expected = list(POLICIES)
    random.Random(seed).shuffle(expected)
    return str(first["policy"].iloc[0]) == expected[0]


def verify_treatment_metadata(row: pd.Series) -> bool:
    """Check that provider-set controls implement the recorded policy label."""
    try:
        order_count = int(row["requested_order_length"])
        only_count = int(row["provider_only_count"])
        public_count = int(row["public_provider_count"])
    except (KeyError, TypeError, ValueError):
        return False
    fallback = bool(row["allow_fallbacks"])
    policy = str(row["policy"])
    if policy == "delegated_default":
        return order_count == 0 and only_count == 0 and fallback
    if policy == "price_only_no_fallback":
        return order_count == 1 and only_count == 1 and not fallback
    if policy == "price_order_fallback":
        return public_count >= 2 and order_count == public_count == only_count and fallback
    return False


def first_position_sample(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    attempts = prepare_attempts(frame)
    first_rows = []
    candidate_blocks = 0
    assignment_replay_passes = 0
    verified_blocks = 0
    treatment_metadata_passes = 0
    complete_blocks = 0
    for block_id, block in attempts.groupby("block_id", sort=False, dropna=True):
        if not block_id:
            continue
        candidate_blocks += 1
        complete_blocks += int(
            len(block) == len(POLICIES)
            and set(block["policy"]) == set(POLICIES)
            and not block["policy"].duplicated().any()
            and not block["policy_order"].duplicated().any()
        )
        if not verify_first_assignment(block):
            continue
        assignment_replay_passes += 1
        first = block[block["policy_order"].eq(0)].iloc[0].copy()
        if not verify_treatment_metadata(first):
            continue
        treatment_metadata_passes += 1
        first["assignment_verified"] = True
        first_rows.append(first)
        verified_blocks += 1
    first = pd.DataFrame(first_rows)
    audit = {
        "candidate_blocks": candidate_blocks,
        "assignment_replay_passes": assignment_replay_passes,
        "verified_first_position_blocks": verified_blocks,
        "treatment_metadata_passes": treatment_metadata_passes,
        "complete_blocks": complete_blocks,
        "assignment_replay_rate": (
            assignment_replay_passes / candidate_blocks if candidate_blocks else None
        ),
        "treatment_metadata_pass_rate": (
            treatment_metadata_passes / assignment_replay_passes
            if assignment_replay_passes
            else None
        ),
    }
    return first, audit


def _order_entropy(attempts: pd.DataFrame) -> float | None:
    if attempts.empty:
        return None
    values = []
    for policy in POLICIES:
        distribution = (
            attempts[attempts["policy"].eq(policy)]["policy_order"]
            .value_counts(normalize=True)
            .to_numpy(dtype=float)
        )
        if len(distribution):
            values.append(float(-(distribution * np.log(distribution)).sum() / math.log(3)))
    return float(np.mean(values)) if values else None


def arm_missingness_bounds(arm: pd.DataFrame, *, total_blocks: int) -> dict[str, Any]:
    """Bound H81 secondary means under protocol-level support restrictions."""
    n = len(arm)
    policy = str(arm["policy"].iloc[0]) if n else ""
    spend = pd.to_numeric(
        arm.get("observed_spend_usd", pd.Series(index=arm.index, dtype=float)),
        errors="coerce",
    )
    quote_cap = pd.to_numeric(
        arm.get("public_quote_cost_cap_usd", pd.Series(index=arm.index, dtype=float)),
        errors="coerce",
    )
    if policy == "delegated_default":
        # Default delegation can leave the displayed provider set, so a cap
        # derived from that public set is not a valid support restriction.
        quote_cap[:] = np.nan
    spend_bounds = bounded_mean(spend, lower=0.0, upper=quote_cap)
    ht_spend_bounds = ht_bounded_mean(
        spend,
        pd.to_numeric(
            arm.get(
                "assignment_probability_first",
                pd.Series(index=arm.index, dtype=float),
            ),
            errors="coerce",
        ),
        total_blocks=total_blocks,
        lower=0.0,
        upper=quote_cap,
    )

    successful = arm[arm["success"].astype(bool)] if n else arm
    latency = pd.to_numeric(
        successful.get("latency_ms", pd.Series(index=successful.index, dtype=float)),
        errors="coerce",
    )
    timeout = pd.to_numeric(
        successful.get(
            "request_timeout_ms",
            pd.Series(60_000.0, index=successful.index, dtype=float),
        ),
        errors="coerce",
    ).fillna(60_000.0)
    latency_bounds = bounded_mean(latency, lower=0.0, upper=timeout)
    selected = successful.get(
        "selected_provider", pd.Series(index=successful.index, dtype="string")
    ).astype("string")
    selected_missing = selected.fillna("").eq("")
    selected_observation_rate = float((~selected_missing).mean()) if len(successful) else None
    return {
        "spend_observed": spend_bounds["observed"],
        "spend_missing": spend_bounds["missing"],
        "spend_mean_lower_bound_usd": spend_bounds["mean_lower_bound"],
        "spend_mean_upper_bound_usd": spend_bounds["mean_upper_bound"],
        "ht_spend_mean_lower_bound_usd": ht_spend_bounds["mean_lower_bound"],
        "ht_spend_mean_upper_bound_usd": ht_spend_bounds["mean_upper_bound"],
        "spend_upper_support_complete_for_missing": spend_bounds[
            "upper_support_complete_for_missing"
        ],
        "spend_observed_upper_support_violations": spend_bounds[
            "observed_upper_support_violations"
        ],
        "successful_latency_observed": latency_bounds["observed"],
        "successful_latency_missing": latency_bounds["missing"],
        "successful_latency_mean_lower_bound_ms": latency_bounds["mean_lower_bound"],
        "successful_latency_mean_upper_bound_ms": latency_bounds["mean_upper_bound"],
        "selected_provider_observed_successes": int((~selected_missing).sum()),
        "selected_provider_missing_successes": int(selected_missing.sum()),
        "selected_provider_observation_rate_success": selected_observation_rate,
    }


def analyze(
    frame: pd.DataFrame,
    *,
    eligibility: pd.DataFrame | None = None,
    simulations: int = RANDOMIZATION_DRAWS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    attempts = prepare_attempts(frame)
    _, _, _, eligibility_summary = eligibility_diagnostics(eligibility, attempts)
    first, audit = first_position_sample(attempts)
    collection_first = first.copy()
    first, release_ready, confirmatory_cutoff = first_balanced_prefix(
        collection_first, POLICIES, MIN_FIRST_POSITION_PER_POLICY
    )
    n_blocks = len(first)
    panel_rows = []
    for policy in POLICIES:
        arm = first[first["policy"].eq(policy)] if n_blocks else first
        n = len(arm)
        successes = int(arm["success"].sum()) if n else 0
        low, high = proportion_confint(successes, n, method="wilson") if n else (np.nan, np.nan)
        probability = pd.to_numeric(arm.get("assignment_probability_first"), errors="coerce")
        missingness = arm_missingness_bounds(arm, total_blocks=n_blocks)
        panel_rows.append(
            {
                "policy": policy,
                "first_position_attempts": n,
                "successes": successes,
                "success_rate": successes / n if n else np.nan,
                "success_ci_low": float(low),
                "success_ci_high": float(high),
                "ht_success_mean": (
                    float((arm["success"].astype(float) / probability).sum() / n_blocks)
                    if n_blocks and n and probability.notna().all()
                    else np.nan
                ),
                "rate_429": float(arm["rejected_429"].mean()) if n else np.nan,
                "fallback_observed_rate": (
                    float(arm["fallback_triggered"].mean()) if n else np.nan
                ),
                **missingness,
                "mean_observed_spend_usd": (
                    float(arm["observed_spend_usd"].mean())
                    if n and not missingness["spend_missing"]
                    else np.nan
                ),
            }
        )
    panel = pd.DataFrame(panel_rows)

    model_rows = []
    if n_blocks:
        for (model_id, policy), arm in first.groupby(["model_id", "policy"], sort=True):
            model_blocks = int(first["model_id"].eq(model_id).sum())
            probability = pd.to_numeric(arm["assignment_probability_first"], errors="coerce")
            model_rows.append(
                {
                    "model_id": model_id,
                    "policy": policy,
                    "model_blocks": model_blocks,
                    "attempts": len(arm),
                    "success_rate": float(arm["success"].mean()),
                    "ht_success_mean_within_model": float(
                        (arm["success"].astype(float) / probability).sum() / model_blocks
                    ),
                }
            )
    model_panel = pd.DataFrame(model_rows)

    outcomes = first["success"].astype(float).to_numpy() if n_blocks else np.array([], dtype=float)
    if n_blocks and simulations:
        labels = np.random.default_rng(20260715).integers(
            0, len(POLICIES), size=(simulations, n_blocks), dtype=np.int8
        )
    else:
        labels = np.empty((0, 0), dtype=np.int8)
    policy_index = {policy: index for index, policy in enumerate(POLICIES)}
    probability = 1.0 / len(POLICIES)
    contrast_rows = []
    for name, positive, negative, primary in COMPARISONS:
        pos = first[first["policy"].eq(positive)] if n_blocks else first
        neg = first[first["policy"].eq(negative)] if n_blocks else first
        raw = (
            float(pos["success"].mean() - neg["success"].mean())
            if len(pos) and len(neg)
            else np.nan
        )
        if len(pos) and len(neg):
            ci_low, ci_high = confint_proportions_2indep(
                int(pos["success"].sum()),
                len(pos),
                int(neg["success"].sum()),
                len(neg),
                method="newcomb",
                compare="diff",
            )
        else:
            ci_low = ci_high = np.nan
        ht = (
            float(
                (
                    first["policy"].eq(positive).to_numpy() * outcomes / probability
                    - first["policy"].eq(negative).to_numpy() * outcomes / probability
                ).sum()
                / n_blocks
            )
            if n_blocks
            else np.nan
        )
        if n_blocks and simulations:
            simulated = (
                (labels == policy_index[positive]) * outcomes[None, :] / probability
                - (labels == policy_index[negative]) * outcomes[None, :] / probability
            ).sum(axis=1) / n_blocks
            p_greater = float((1 + (simulated >= ht - 1e-15).sum()) / (simulations + 1))
            p_two_sided = float(
                (1 + (np.abs(simulated) >= abs(ht) - 1e-15).sum()) / (simulations + 1)
            )
        else:
            p_greater = p_two_sided = np.nan
        spend_complete = bool(
            len(pos)
            and len(neg)
            and pos["observed_spend_usd"].notna().all()
            and neg["observed_spend_usd"].notna().all()
        )
        spend_difference = (
            float(pos["observed_spend_usd"].mean() - neg["observed_spend_usd"].mean())
            if spend_complete
            else np.nan
        )
        pos_missingness = arm_missingness_bounds(pos, total_blocks=n_blocks)
        neg_missingness = arm_missingness_bounds(neg, total_blocks=n_blocks)
        spend_bound_low, spend_bound_high = difference_bounds(
            {
                "mean_lower_bound": pos_missingness["spend_mean_lower_bound_usd"],
                "mean_upper_bound": pos_missingness["spend_mean_upper_bound_usd"],
            },
            {
                "mean_lower_bound": neg_missingness["spend_mean_lower_bound_usd"],
                "mean_upper_bound": neg_missingness["spend_mean_upper_bound_usd"],
            },
        )
        ht_spend_bound_low, ht_spend_bound_high = difference_bounds(
            {
                "mean_lower_bound": pos_missingness["ht_spend_mean_lower_bound_usd"],
                "mean_upper_bound": pos_missingness["ht_spend_mean_upper_bound_usd"],
            },
            {
                "mean_lower_bound": neg_missingness["ht_spend_mean_lower_bound_usd"],
                "mean_upper_bound": neg_missingness["ht_spend_mean_upper_bound_usd"],
            },
        )
        latency_bound_low, latency_bound_high = difference_bounds(
            {
                "mean_lower_bound": pos_missingness["successful_latency_mean_lower_bound_ms"],
                "mean_upper_bound": pos_missingness["successful_latency_mean_upper_bound_ms"],
            },
            {
                "mean_lower_bound": neg_missingness["successful_latency_mean_lower_bound_ms"],
                "mean_upper_bound": neg_missingness["successful_latency_mean_upper_bound_ms"],
            },
        )
        pos_provider_rate = pos_missingness["selected_provider_observation_rate_success"]
        neg_provider_rate = neg_missingness["selected_provider_observation_rate_success"]
        contrast_rows.append(
            {
                "estimand": name,
                "positive_policy": positive,
                "negative_policy": negative,
                "primary": primary,
                "n_blocks": n_blocks,
                "positive_n": len(pos),
                "negative_n": len(neg),
                "success_difference_hajek": raw,
                "success_difference_ci_low": float(ci_low),
                "success_difference_ci_high": float(ci_high),
                "success_difference_ht": ht,
                "randomization_p_greater": p_greater,
                "randomization_p_two_sided": p_two_sided,
                "spend_complete_both_arms": spend_complete,
                "observed_spend_difference_usd": spend_difference,
                "spend_difference_lower_bound_usd": spend_bound_low,
                "spend_difference_upper_bound_usd": spend_bound_high,
                "ht_spend_difference_lower_bound_usd": ht_spend_bound_low,
                "ht_spend_difference_upper_bound_usd": ht_spend_bound_high,
                "successful_latency_difference_lower_bound_ms": latency_bound_low,
                "successful_latency_difference_upper_bound_ms": latency_bound_high,
                "selected_provider_observation_rate_difference": (
                    float(pos_provider_rate - neg_provider_rate)
                    if pos_provider_rate is not None and neg_provider_rate is not None
                    else np.nan
                ),
            }
        )
    contrasts = pd.DataFrame(contrast_rows)
    contrasts["holm_p_greater"] = np.nan
    primary_mask = contrasts["primary"].astype(bool)
    contrasts.loc[primary_mask, "holm_p_greater"] = holm_adjust(
        contrasts.loc[primary_mask, "randomization_p_greater"].tolist()
    )

    analysis_counts = panel.set_index("policy")["first_position_attempts"].reindex(
        POLICIES, fill_value=0
    )
    collection_counts = (
        collection_first["policy"].value_counts().reindex(POLICIES, fill_value=0)
        if len(collection_first)
        else pd.Series(0, index=POLICIES, dtype=int)
    )
    audit.update(
        {
            "study_id": STUDY_ID,
            "first_position_counts": {key: int(value) for key, value in collection_counts.items()},
            "confirmatory_prefix_counts": {
                key: int(value) for key, value in analysis_counts.items()
            },
            "confirmatory_prefix_blocks": n_blocks if release_ready else 0,
            "confirmatory_cutoff": confirmatory_cutoff,
            "outcomes_released": release_ready,
            "models_represented": (
                int(collection_first["model_id"].nunique()) if len(collection_first) else 0
            ),
            "model_ids": (
                sorted(collection_first["model_id"].astype(str).unique().tolist())
                if len(collection_first)
                else []
            ),
            "normalized_order_entropy": _order_entropy(attempts),
            "target_per_policy": MIN_FIRST_POSITION_PER_POLICY,
            "randomization_draws": simulations,
            "eligibility_funnel": eligibility_summary,
            "evidence_status": (
                "randomized_decomposition_ready"
                if release_ready
                else "randomized_decomposition_power_gated"
            ),
            "claim_boundary": (
                "The fallback contrast holds the cheapest first provider fixed and changes "
                "fallback permission. The hidden-selection contrast compares delegated default "
                "with an explicit public-price order, both permitting fallback. It measures one "
                "owned account and does not reveal provider intent or private router scores."
            ),
        }
    )
    if not release_ready:
        for column in panel.columns:
            if column not in {"policy", "first_position_attempts"}:
                panel[column] = np.nan
        for column in model_panel.columns:
            if column not in {"model_id", "policy", "model_blocks", "attempts"}:
                model_panel[column] = np.nan
        for column in contrasts.columns:
            if column not in {
                "estimand",
                "positive_policy",
                "negative_policy",
                "primary",
                "n_blocks",
                "positive_n",
                "negative_n",
            }:
                contrasts[column] = np.nan
    return panel, model_panel, contrasts, audit


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    frame = data.q(
        f"""
        select *
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        """
    ).df()
    try:
        eligibility = data.q(
            f"""
            select *
            from read_parquet(
              '{data.table_glob("router_probe_eligibility")}',
              union_by_name=true
            )
            """
        ).df()
    except Exception:
        # The table is prospective and optional for historical/local datasets.
        eligibility = pd.DataFrame()
    panel, model_panel, contrasts, summary = analyze(frame, eligibility=eligibility)
    eligibility_rows, eligibility_models, eligibility_runs, _ = eligibility_diagnostics(
        eligibility, prepare_attempts(frame)
    )
    save(panel, out_dir, "h81_policy_panel")
    save(model_panel, out_dir, "h81_model_policy_panel")
    save(contrasts, out_dir, "h81_contrasts")
    save(eligibility_rows, out_dir, "h81_eligibility_rows")
    save(eligibility_models, out_dir, "h81_eligibility_models")
    save(eligibility_runs, out_dir, "h81_eligibility_runs")
    save_json(summary, out_dir, "h81_summary")
    return summary
