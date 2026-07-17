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
RANDOMIZATION_MC_AUDIT_TOLERANCE = 0.01
PRIMARY_FWER_ALPHA = 0.05
BINARY_OUTCOME_VALUES = {
    "succeeded": 1.0,
    "failed": 0.0,
    "cancelled": 0.0,
}


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


def prepare_assignment_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate H81 rows and expose assignment metadata without outcomes."""
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
    return out


def prepare_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    """Add response, rejection, and spend fields to an assignment frame."""
    out = prepare_assignment_attempts(frame)
    if out.empty:
        return out
    outcome = (
        out.get("outcome", pd.Series(pd.NA, index=out.index, dtype="string"))
        .astype("string")
        .str.strip()
        .str.lower()
    )
    out["outcome_observed"] = outcome.isin(BINARY_OUTCOME_VALUES)
    out["success"] = outcome.map(BINARY_OUTCOME_VALUES).astype("Float64")
    retry_reason = out.get("retry_reason", pd.Series("", index=out.index, dtype="string")).astype(
        "string"
    )
    out["rejected_429"] = pd.Series(pd.NA, index=out.index, dtype="Float64")
    observed = out["outcome_observed"].fillna(False).astype(bool)
    out.loc[observed, "rejected_429"] = (
        out.loc[observed, "success"].eq(0)
        & retry_reason.loc[observed].fillna("").str.contains("429")
    ).astype(float)
    cost = pd.to_numeric(out.get("cost_usd"), errors="coerce")
    out["observed_spend_usd"] = cost.where(out["success"].eq(1), 0.0).where(observed)
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
    expected = _expected_first_policy(block)
    first = block[block["policy_order"].eq(0)]
    return expected is not None and len(first) == 1 and str(first["policy"].iloc[0]) == expected


def _expected_first_policy(block: pd.DataFrame) -> str | None:
    """Reconstruct a block's randomized first policy without reading outcomes."""
    try:
        seed = int(block["block_seed"].iloc[0])
        count = int(block["block_policy_count"].dropna().iloc[0])
    except (IndexError, TypeError, ValueError):
        return None
    if count != len(POLICIES):
        return None
    expected = list(POLICIES)
    random.Random(seed).shuffle(expected)
    return expected[0]


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
    attempts = prepare_assignment_attempts(frame)
    if attempts.empty:
        return attempts.copy(), {
            "candidate_blocks": 0,
            "assignment_replay_passes": 0,
            "verified_first_position_blocks": 0,
            "treatment_metadata_passes": 0,
            "complete_blocks": 0,
            "assignment_replay_rate": None,
            "treatment_metadata_pass_rate": None,
        }
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
    success = pd.to_numeric(
        arm.get("success", pd.Series(index=arm.index, dtype=float)),
        errors="coerce",
    )
    success_bounds = bounded_mean(success, lower=0.0, upper=1.0)
    probability_column = (
        "analysis_assignment_probability"
        if "analysis_assignment_probability" in arm
        else "assignment_probability_first"
    )
    probability = pd.to_numeric(
        arm.get(probability_column, pd.Series(index=arm.index, dtype=float)),
        errors="coerce",
    )
    ht_success_bounds = ht_bounded_mean(
        success,
        probability,
        total_blocks=total_blocks,
        lower=0.0,
        upper=1.0,
    )
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
        probability,
        total_blocks=total_blocks,
        lower=0.0,
        upper=quote_cap,
    )

    successful = arm[success.eq(1)] if n else arm
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
        "success_outcomes_observed": success_bounds["observed"],
        "success_outcomes_missing": success_bounds["missing"],
        "success_mean_lower_bound": success_bounds["mean_lower_bound"],
        "success_mean_upper_bound": success_bounds["mean_upper_bound"],
        "ht_success_mean_lower_bound": ht_success_bounds["mean_lower_bound"],
        "ht_success_mean_upper_bound": ht_success_bounds["mean_upper_bound"],
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


def _finalize_gate_audit(
    audit: dict[str, Any],
    *,
    attempts: pd.DataFrame,
    collection_first: pd.DataFrame,
    release_gate_first: pd.DataFrame,
    analysis_first: pd.DataFrame,
    release_ready: bool,
    confirmatory_cutoff: str | None,
    eligibility_summary: dict[str, Any],
    simulations: int,
) -> dict[str, Any]:
    """Attach only assignment/support facts to the public gate audit."""
    collection_counts = (
        collection_first["policy"].value_counts().reindex(POLICIES, fill_value=0)
        if len(collection_first)
        else pd.Series(0, index=POLICIES, dtype=int)
    )
    release_gate_counts = (
        release_gate_first["policy"].value_counts().reindex(POLICIES, fill_value=0)
        if len(release_gate_first)
        else pd.Series(0, index=POLICIES, dtype=int)
    )
    analysis_counts = (
        analysis_first["policy"].value_counts().reindex(POLICIES, fill_value=0)
        if len(analysis_first)
        else pd.Series(0, index=POLICIES, dtype=int)
    )
    audit.update(
        {
            "study_id": STUDY_ID,
            "first_position_counts": {key: int(value) for key, value in collection_counts.items()},
            "confirmatory_prefix_counts": {
                key: int(value) for key, value in analysis_counts.items()
            },
            "release_gate_prefix_counts": {
                key: int(value) for key, value in release_gate_counts.items()
            },
            "release_gate_prefix_blocks": (int(len(release_gate_first)) if release_ready else 0),
            "confirmatory_prefix_blocks": (int(len(analysis_first)) if release_ready else 0),
            "confirmatory_cutoff": confirmatory_cutoff,
            "outcomes_released": release_ready,
            "outcome_access": (
                "released_confirmatory_prefix"
                if release_ready
                else "not_queried_by_40_per_arm_gate"
            ),
            "terminal_gate_block_excluded": bool(release_ready),
            "analysis_randomization": (
                "fixed-count randomization conditional on preterminal arm counts"
                if release_ready
                else "not released"
            ),
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
            "accrual_projection": _accrual_projection(
                collection_first,
                collection_counts,
                target_per_policy=MIN_FIRST_POSITION_PER_POLICY,
            ),
            "randomization_draws": simulations,
            "eligibility_funnel": eligibility_summary,
            "evidence_status": (
                "randomized_decomposition_ready"
                if release_ready
                else "randomized_decomposition_power_gated"
            ),
            "identification": (
                "After the release gate opens, the gate-hitting terminal block is excluded. "
                "Conditional on the preterminal arm counts, treatment labels are uniformly "
                "distributed over fixed-count assignments, so arm means and equivalent "
                "conditional HT contrasts are design-unbiased for that finite prefix."
            ),
            "claim_boundary": (
                "The fallback contrast holds the cheapest first provider fixed and changes "
                "fallback permission. The hidden-selection contrast compares delegated default "
                "with an explicit public-price order, both permitting fallback. It measures one "
                "owned account and does not reveal provider intent or private router scores."
            ),
        }
    )
    return audit


def _pairwise_fixed_count_randomizations(
    n_positive: int,
    n_negative: int,
    *,
    simulations: int,
    seed: int = 20260715,
) -> np.ndarray:
    """Permute only a contrasted pair while holding the nuisance arm fixed."""
    n_pair = int(n_positive + n_negative)
    if n_positive <= 0 or n_negative <= 0 or not n_pair or not simulations:
        return np.empty((0, 0), dtype=np.int8)
    template = np.concatenate(
        [np.ones(n_positive, dtype=np.int8), np.zeros(n_negative, dtype=np.int8)]
    )
    rng = np.random.default_rng(seed)
    labels = np.empty((simulations, n_pair), dtype=np.int8)
    for draw in range(simulations):
        labels[draw] = rng.permutation(template)
    return labels


def _exact_pairwise_binary_randomization_pvalues(
    positive_outcomes: np.ndarray,
    negative_outcomes: np.ndarray,
    *,
    observed_statistic: float | None = None,
) -> tuple[float, float]:
    """Return exact conditional Fisher tails for one binary policy pair.

    For a null comparing policies ``positive`` and ``negative``, the third
    policy is a nuisance arm whose potential outcomes need not satisfy the
    pairwise null.  We therefore condition on the nuisance-arm assignment and
    permute only the two contrasted labels.  Conditional on their combined
    binary outcomes, the positive-arm success count is hypergeometric.  This
    yields a valid pairwise sharp-null p-value even when the nuisance policy has
    an arbitrary effect.
    """
    positive_values = np.asarray(positive_outcomes, dtype=float)
    negative_values = np.asarray(negative_outcomes, dtype=float)
    n_positive = int(len(positive_values))
    n_negative = int(len(negative_values))
    values = np.concatenate([positive_values, negative_values])
    n_pair = int(len(values))
    if observed_statistic is None and n_positive and n_negative:
        observed_statistic = float(positive_values.mean() - negative_values.mean())
    if (
        n_positive <= 0
        or n_negative <= 0
        or not np.isfinite(values).all()
        or observed_statistic is None
        or not np.isfinite(observed_statistic)
        or not np.isin(values, (0.0, 1.0)).all()
    ):
        return np.nan, np.nan

    successes = int(values.sum())
    denominator = math.comb(n_pair, successes)
    greater_probabilities: list[float] = []
    two_sided_probabilities: list[float] = []
    support_probabilities: list[float] = []
    tolerance = 1e-15
    positive_min = max(0, successes - n_negative)
    positive_max = min(n_positive, successes)
    for positive_successes in range(positive_min, positive_max + 1):
        negative_successes = successes - positive_successes
        ways = math.comb(n_positive, positive_successes) * math.comb(n_negative, negative_successes)
        probability = ways / denominator
        support_probabilities.append(probability)
        statistic = positive_successes / n_positive - negative_successes / n_negative
        if statistic >= observed_statistic - tolerance:
            greater_probabilities.append(probability)
        if abs(statistic) >= abs(observed_statistic) - tolerance:
            two_sided_probabilities.append(probability)
    support_mass = math.fsum(support_probabilities)
    if not math.isclose(support_mass, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(f"exact randomization support has mass {support_mass}")
    return (
        float(math.fsum(greater_probabilities)),
        float(math.fsum(two_sided_probabilities)),
    )


def _simultaneous_serfling_mean_radii(
    counts: pd.Series,
    *,
    alpha: float = PRIMARY_FWER_ALPHA,
) -> dict[str, float]:
    """Return design-valid simultaneous radii for all randomized policy means.

    Conditional on the preterminal count vector, each policy arm is a simple
    random sample without replacement from the fixed preterminal population.
    Serfling's finite-population refinement of Hoeffding's bound for outcomes
    in ``[0, 1]`` and a union bound across all three policy means give coverage
    of at least ``1 - alpha``.  This needs neither independent arms nor a
    binomial model.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    aligned = counts.reindex(POLICIES, fill_value=0).astype(int)
    if (aligned <= 0).any():
        return {policy: np.nan for policy in POLICIES}
    population_size = int(aligned.sum())
    log_term = math.log(2.0 * len(POLICIES) / alpha)
    return {
        policy: min(
            1.0,
            math.sqrt(
                (1.0 - (int(aligned[policy]) - 1.0) / population_size)
                * log_term
                / (2.0 * int(aligned[policy]))
            ),
        )
        for policy in POLICIES
    }


def _row_time(frame: pd.DataFrame) -> pd.Series:
    """Return the first available UTC timestamp under the production sort order."""
    result = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    for column in ("observed_ts", "observed_at", "run_ts"):
        if column not in frame:
            continue
        candidate = pd.to_datetime(frame[column], errors="coerce", utc=True)
        result = result.where(result.notna(), candidate)
    return result


def preterminal_missingness_sensitivity(
    attempts: pd.DataFrame,
    *,
    analysis_first: pd.DataFrame,
    terminal_gate_block: pd.Series,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Recover intended preterminal arms and expose treatment/outcome attrition.

    The confirmatory point estimator continues to use only replayed, compliant
    first-position blocks.  This companion panel adds every reconstructable
    intended first-position block no later than the gate-hitting block and codes
    a missing/mismatched treatment or a non-binary outcome as unknown in [0, 1].
    It is constructed only after the outcome gate opens.
    """
    if attempts.empty:
        return pd.DataFrame(), {
            "candidate_blocks_preterminal": 0,
            "assigned_policy_reconstructed": 0,
            "treatment_verified": 0,
            "treatment_missing_or_noncompliant": 0,
            "binary_outcome_missing_among_verified": 0,
            "unorderable_candidate_blocks": 0,
            "unassigned_candidate_blocks": 0,
        }

    terminal_id = str(terminal_gate_block.get("block_id", ""))
    terminal_frame = terminal_gate_block.to_frame().T
    terminal_times = _row_time(terminal_frame)
    terminal_time = terminal_times.iloc[0] if len(terminal_times) else pd.NaT
    confirmed_ids = set(analysis_first.get("block_id", pd.Series(dtype=object)).astype(str))
    rows: list[dict[str, Any]] = []
    unorderable = 0

    for block_id, block in attempts.groupby("block_id", sort=False, dropna=True):
        block_id = str(block_id)
        if not block_id or block_id == terminal_id:
            continue
        times = _row_time(block)
        block_time = times.min() if times.notna().any() else pd.NaT
        if block_id not in confirmed_ids:
            if pd.isna(block_time) or pd.isna(terminal_time):
                # An unorderable block cannot safely be declared post-cutoff.
                unorderable += 1
            elif block_time > terminal_time:
                continue

        expected_policy = _expected_first_policy(block)
        first_rows = block[block["policy_order"].eq(0)]
        first = first_rows.iloc[0] if len(first_rows) == 1 else None
        replay = bool(
            expected_policy is not None
            and first is not None
            and str(first["policy"]) == expected_policy
        )
        treatment_verified = bool(replay and verify_treatment_metadata(first))
        outcome_flag = first.get("outcome_observed") if first is not None else None
        outcome_observed = bool(
            treatment_verified
            and first is not None
            and pd.notna(outcome_flag)
            and bool(outcome_flag)
        )
        success = (
            float(first["success"])
            if outcome_observed and first is not None and pd.notna(first.get("success"))
            else np.nan
        )
        rows.append(
            {
                "block_id": block_id,
                "block_time": block_time,
                "expected_policy": expected_policy,
                "first_row_observed": first is not None,
                "assignment_replay_pass": replay,
                "treatment_metadata_pass": treatment_verified,
                "binary_outcome_observed": outcome_observed,
                "success_for_worst_case_bounds": success,
                "in_confirmatory_point_sample": block_id in confirmed_ids,
            }
        )

    panel = pd.DataFrame(rows)
    if panel.empty:
        assigned = treatment_verified = treatment_missing = outcome_missing = 0
        unassigned = 0
    else:
        assigned_mask = panel["expected_policy"].isin(POLICIES)
        assigned = int(assigned_mask.sum())
        treatment_verified = int(panel["treatment_metadata_pass"].sum())
        treatment_missing = int(
            (assigned_mask & ~panel["treatment_metadata_pass"].astype(bool)).sum()
        )
        outcome_missing = int(
            (
                panel["treatment_metadata_pass"].astype(bool)
                & ~panel["binary_outcome_observed"].astype(bool)
            ).sum()
        )
        unassigned = int((~assigned_mask).sum())
    summary = {
        "candidate_blocks_preterminal": int(len(panel)),
        "assigned_policy_reconstructed": assigned,
        "treatment_verified": treatment_verified,
        "treatment_missing_or_noncompliant": treatment_missing,
        "binary_outcome_missing_among_verified": outcome_missing,
        "unorderable_candidate_blocks": int(unorderable),
        "unassigned_candidate_blocks": unassigned,
        "bound_rule": (
            "Reconstructed intended arms are retained. Missing or noncompliant treatment "
            "metadata and unknown/corrupt outcomes are assigned success 0 and 1 at the two "
            "worst-case endpoints. Any unreconstructable arm widens every contrast to [-1,1]."
        ),
        "estimand_boundary": (
            "These are attrition/treatment-record sensitivity bounds for intended policy "
            "assignment, not a per-protocol treatment effect."
        ),
    }
    return panel, summary


def _accrual_projection(
    collection_first: pd.DataFrame,
    counts: pd.Series,
    *,
    target_per_policy: int,
    draws: int = 50_000,
) -> dict[str, Any]:
    """Forecast the assignment-only balance gate under continued uniform draws."""
    if collection_first.empty:
        return {
            "remaining_by_policy": {policy: int(target_per_policy) for policy in POLICIES},
            "completion_fraction_min_arm": 0.0,
            "forecast_boundary": "No assignments have accrued; no time forecast is available.",
        }
    timestamps = pd.to_datetime(
        collection_first.get(
            "observed_at",
            collection_first.get("run_ts", pd.Series(pd.NaT, index=collection_first.index)),
        ),
        errors="coerce",
        utc=True,
    )
    span_hours = (
        float((timestamps.max() - timestamps.min()).total_seconds() / 3600)
        if timestamps.notna().sum() >= 2
        else 0.0
    )
    blocks_per_hour = len(collection_first) / span_hours if span_hours > 0 else None
    initial = np.asarray([int(counts.get(policy, 0)) for policy in POLICIES], dtype=np.int16)
    simulated = np.repeat(initial[None, :], draws, axis=0)
    extra = np.zeros(draws, dtype=np.int16)
    active = simulated.min(axis=1) < target_per_policy
    rng = np.random.default_rng(20260717)
    while active.any():
        active_index = np.flatnonzero(active)
        labels = rng.integers(0, len(POLICIES), size=len(active_index))
        simulated[active_index, labels] += 1
        extra[active_index] += 1
        active[active_index] = simulated[active_index].min(axis=1) < target_per_policy
    remaining = {
        policy: max(0, int(target_per_policy - counts.get(policy, 0))) for policy in POLICIES
    }
    return {
        "remaining_by_policy": remaining,
        "completion_fraction_min_arm": float(counts.min() / target_per_policy),
        "observed_first_position_blocks_per_hour": blocks_per_hour,
        "simulated_additional_blocks_mean": float(extra.mean()),
        "simulated_additional_blocks_p50": float(np.quantile(extra, 0.50)),
        "simulated_additional_blocks_p90": float(np.quantile(extra, 0.90)),
        "simulated_hours_to_gate_mean": (
            float(extra.mean() / blocks_per_hour) if blocks_per_hour else None
        ),
        "simulated_hours_to_gate_p90": (
            float(np.quantile(extra, 0.90) / blocks_per_hour) if blocks_per_hour else None
        ),
        "first_assignment_at": (timestamps.min().isoformat() if timestamps.notna().any() else None),
        "latest_assignment_at": (
            timestamps.max().isoformat() if timestamps.notna().any() else None
        ),
        "forecast_boundary": (
            "Uniform-assignment and observed-cadence extrapolation only. Scheduling gaps, "
            "model eligibility, and collection failures can delay the gate. No outcome enters."
        ),
    }


def _blinded_outputs(
    collection_first: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return schema-stable accrual outputs without reading outcome columns."""
    counts = collection_first["policy"].value_counts().reindex(POLICIES, fill_value=0)
    panel = pd.DataFrame(
        [
            {
                "policy": policy,
                "first_position_attempts": int(counts[policy]),
                "successes": np.nan,
                "success_rate": np.nan,
                "success_rate_observed_cases": np.nan,
                "success_ci_low": np.nan,
                "success_ci_high": np.nan,
                "ht_success_mean": np.nan,
                "success_outcomes_observed": np.nan,
                "success_outcomes_missing": np.nan,
                "success_mean_lower_bound": np.nan,
                "success_mean_upper_bound": np.nan,
                "ht_success_mean_lower_bound": np.nan,
                "ht_success_mean_upper_bound": np.nan,
                "rate_429": np.nan,
                "fallback_observed_rate": np.nan,
                "spend_observed": np.nan,
                "spend_missing": np.nan,
                "spend_mean_lower_bound_usd": np.nan,
                "spend_mean_upper_bound_usd": np.nan,
                "ht_spend_mean_lower_bound_usd": np.nan,
                "ht_spend_mean_upper_bound_usd": np.nan,
                "spend_upper_support_complete_for_missing": np.nan,
                "spend_observed_upper_support_violations": np.nan,
                "successful_latency_observed": np.nan,
                "successful_latency_missing": np.nan,
                "successful_latency_mean_lower_bound_ms": np.nan,
                "successful_latency_mean_upper_bound_ms": np.nan,
                "selected_provider_observed_successes": np.nan,
                "selected_provider_missing_successes": np.nan,
                "selected_provider_observation_rate_success": np.nan,
                "mean_observed_spend_usd": np.nan,
            }
            for policy in POLICIES
        ]
    )
    model_rows = []
    for (model_id, policy), arm in collection_first.groupby(["model_id", "policy"], sort=True):
        model_rows.append(
            {
                "model_id": model_id,
                "policy": policy,
                "model_blocks": int(collection_first["model_id"].eq(model_id).sum()),
                "attempts": int(len(arm)),
                "success_rate": np.nan,
                "success_outcomes_missing": np.nan,
                "success_mean_lower_bound": np.nan,
                "success_mean_upper_bound": np.nan,
                "ht_success_mean_within_model": np.nan,
            }
        )
    model_panel = pd.DataFrame(
        model_rows,
        columns=[
            "model_id",
            "policy",
            "model_blocks",
            "attempts",
            "success_rate",
            "success_outcomes_missing",
            "success_mean_lower_bound",
            "success_mean_upper_bound",
            "ht_success_mean_within_model",
        ],
    )
    contrasts = pd.DataFrame(
        [
            {
                "estimand": name,
                "positive_policy": positive,
                "negative_policy": negative,
                "primary": primary,
                "n_blocks": int(len(collection_first)),
                "positive_n": int(counts[positive]),
                "negative_n": int(counts[negative]),
                "success_difference_hajek": np.nan,
                "success_difference_conditional": np.nan,
                "success_difference_ci_low": np.nan,
                "success_difference_ci_high": np.nan,
                "success_difference_simultaneous_ci_low": np.nan,
                "success_difference_simultaneous_ci_high": np.nan,
                "success_difference_ht": np.nan,
                "positive_success_outcomes_missing": np.nan,
                "negative_success_outcomes_missing": np.nan,
                "success_difference_lower_bound": np.nan,
                "success_difference_upper_bound": np.nan,
                "ht_success_difference_lower_bound": np.nan,
                "ht_success_difference_upper_bound": np.nan,
                "planned_positive_n": np.nan,
                "planned_negative_n": np.nan,
                "planned_positive_treatment_or_outcome_missing": np.nan,
                "planned_negative_treatment_or_outcome_missing": np.nan,
                "success_difference_treatment_outcome_lower_bound": np.nan,
                "success_difference_treatment_outcome_upper_bound": np.nan,
                "randomization_p_greater": np.nan,
                "randomization_p_two_sided": np.nan,
                "randomization_p_greater_mc_check": np.nan,
                "randomization_p_two_sided_mc_check": np.nan,
                "randomization_mc_max_abs_error": np.nan,
                "randomization_mc_audit_pass": np.nan,
                "spend_complete_both_arms": np.nan,
                "observed_spend_difference_usd": np.nan,
                "spend_difference_lower_bound_usd": np.nan,
                "spend_difference_upper_bound_usd": np.nan,
                "ht_spend_difference_lower_bound_usd": np.nan,
                "ht_spend_difference_upper_bound_usd": np.nan,
                "successful_latency_difference_lower_bound_ms": np.nan,
                "successful_latency_difference_upper_bound_ms": np.nan,
                "selected_provider_observation_rate_difference": np.nan,
                "holm_p_greater": np.nan,
            }
            for name, positive, negative, primary in COMPARISONS
        ]
    )
    return panel, model_panel, contrasts


def analyze(
    frame: pd.DataFrame,
    *,
    eligibility: pd.DataFrame | None = None,
    simulations: int = RANDOMIZATION_DRAWS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    assignment_attempts = prepare_assignment_attempts(frame)
    _, _, _, eligibility_summary = eligibility_diagnostics(eligibility, assignment_attempts)
    collection_first, audit = first_position_sample(assignment_attempts)
    assignment_prefix, release_ready, confirmatory_cutoff = first_balanced_prefix(
        collection_first, POLICIES, MIN_FIRST_POSITION_PER_POLICY
    )
    if not release_ready:
        panel, model_panel, contrasts = _blinded_outputs(collection_first)
        summary = _finalize_gate_audit(
            audit,
            attempts=assignment_attempts,
            collection_first=collection_first,
            release_gate_first=assignment_prefix,
            analysis_first=assignment_prefix,
            release_ready=False,
            confirmatory_cutoff=confirmatory_cutoff,
            eligibility_summary=eligibility_summary,
            simulations=simulations,
        )
        return panel, model_panel, contrasts, summary

    # Outcome columns are touched only after the assignment-only gate opens.
    attempts = prepare_attempts(frame)
    outcome_first, _ = first_position_sample(attempts)
    outcome_gate_prefix, outcome_release_ready, outcome_cutoff = first_balanced_prefix(
        outcome_first, POLICIES, MIN_FIRST_POSITION_PER_POLICY
    )
    if not outcome_release_ready or outcome_cutoff != confirmatory_cutoff:
        raise RuntimeError("assignment and outcome confirmatory prefixes do not match")
    if len(outcome_gate_prefix) < 2:
        raise RuntimeError("release-gate prefix is too short for preterminal analysis")
    terminal_gate_block = outcome_gate_prefix.iloc[-1]
    first = outcome_gate_prefix.iloc[:-1].copy()
    n_blocks = len(first)
    analysis_counts = first["policy"].value_counts().reindex(POLICIES, fill_value=0)
    analysis_probabilities = analysis_counts / n_blocks
    design_mean_radii = _simultaneous_serfling_mean_radii(analysis_counts)
    first["analysis_assignment_probability"] = first["policy"].map(analysis_probabilities)
    missingness_plan, treatment_outcome_sensitivity = preterminal_missingness_sensitivity(
        attempts,
        analysis_first=first,
        terminal_gate_block=terminal_gate_block,
    )
    panel_rows = []
    for policy in POLICIES:
        arm = first[first["policy"].eq(policy)] if n_blocks else first
        n = len(arm)
        success = pd.to_numeric(arm.get("success"), errors="coerce")
        success_observed = int(success.notna().sum())
        success_missing = int(success.isna().sum())
        successes = int(success.fillna(0).sum()) if n else 0
        low, high = (
            proportion_confint(successes, n, method="wilson")
            if n and not success_missing
            else (np.nan, np.nan)
        )
        probability = pd.to_numeric(arm.get("analysis_assignment_probability"), errors="coerce")
        missingness = arm_missingness_bounds(arm, total_blocks=n_blocks)
        panel_rows.append(
            {
                "policy": policy,
                "first_position_attempts": n,
                "successes": successes,
                "success_rate": successes / n if n and not success_missing else np.nan,
                "success_rate_observed_cases": (
                    successes / success_observed if success_observed else np.nan
                ),
                "success_ci_low": float(low),
                "success_ci_high": float(high),
                "success_design_simultaneous_ci_low": (
                    max(0.0, successes / n - design_mean_radii[policy])
                    if n and not success_missing
                    else np.nan
                ),
                "success_design_simultaneous_ci_high": (
                    min(1.0, successes / n + design_mean_radii[policy])
                    if n and not success_missing
                    else np.nan
                ),
                "success_design_simultaneous_radius": design_mean_radii[policy],
                "ht_success_mean": (
                    float((success / probability).sum() / n_blocks)
                    if n_blocks and n and not success_missing and probability.notna().all()
                    else np.nan
                ),
                "rate_429": (
                    float(pd.to_numeric(arm["rejected_429"], errors="coerce").mean())
                    if success_observed
                    else np.nan
                ),
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
            probability = pd.to_numeric(arm["analysis_assignment_probability"], errors="coerce")
            model_success = pd.to_numeric(arm["success"], errors="coerce")
            model_missing = int(model_success.isna().sum())
            model_bounds = bounded_mean(model_success, lower=0.0, upper=1.0)
            model_rows.append(
                {
                    "model_id": model_id,
                    "policy": policy,
                    "model_blocks": model_blocks,
                    "attempts": len(arm),
                    "success_rate": (float(model_success.mean()) if not model_missing else np.nan),
                    "success_outcomes_missing": model_missing,
                    "success_mean_lower_bound": model_bounds["mean_lower_bound"],
                    "success_mean_upper_bound": model_bounds["mean_upper_bound"],
                    "ht_success_mean_within_model": (
                        float((model_success / probability).sum() / model_blocks)
                        if not model_missing
                        else np.nan
                    ),
                }
            )
    model_panel = pd.DataFrame(model_rows)

    outcomes = (
        pd.to_numeric(first["success"], errors="coerce").to_numpy(dtype=float)
        if n_blocks
        else np.array([], dtype=float)
    )
    complete_binary_outcomes = bool(n_blocks and np.isfinite(outcomes).all())
    primary_comparisons = sum(int(primary) for _, _, _, primary in COMPARISONS)
    contrast_rows = []
    for contrast_index, (name, positive, negative, primary) in enumerate(COMPARISONS):
        pos = first[first["policy"].eq(positive)] if n_blocks else first
        neg = first[first["policy"].eq(negative)] if n_blocks else first
        pos_success = pd.to_numeric(pos.get("success"), errors="coerce")
        neg_success = pd.to_numeric(neg.get("success"), errors="coerce")
        pos_success_missing = int(pos_success.isna().sum())
        neg_success_missing = int(neg_success.isna().sum())
        raw = (
            float(pos_success.mean() - neg_success.mean())
            if len(pos) and len(neg) and not pos_success_missing and not neg_success_missing
            else np.nan
        )
        if len(pos) and len(neg) and not pos_success_missing and not neg_success_missing:
            ci_low, ci_high = confint_proportions_2indep(
                int(pos_success.sum()),
                len(pos),
                int(neg_success.sum()),
                len(neg),
                method="newcomb",
                compare="diff",
            )
            if primary:
                simultaneous_low, simultaneous_high = confint_proportions_2indep(
                    int(pos_success.sum()),
                    len(pos),
                    int(neg_success.sum()),
                    len(neg),
                    method="newcomb",
                    compare="diff",
                    alpha=PRIMARY_FWER_ALPHA / primary_comparisons,
                )
            else:
                simultaneous_low = simultaneous_high = np.nan
        else:
            ci_low = ci_high = np.nan
            simultaneous_low = simultaneous_high = np.nan
        ht = (
            float(
                (
                    first["policy"].eq(positive).to_numpy()
                    * outcomes
                    / analysis_probabilities[positive]
                    - first["policy"].eq(negative).to_numpy()
                    * outcomes
                    / analysis_probabilities[negative]
                ).sum()
                / n_blocks
            )
            if n_blocks and complete_binary_outcomes
            else np.nan
        )
        design_radius = design_mean_radii[positive] + design_mean_radii[negative]
        design_simultaneous_low = max(-1.0, raw - design_radius) if np.isfinite(raw) else np.nan
        design_simultaneous_high = min(1.0, raw + design_radius) if np.isfinite(raw) else np.nan
        if n_blocks and complete_binary_outcomes:
            p_greater, p_two_sided = _exact_pairwise_binary_randomization_pvalues(
                pos_success.to_numpy(dtype=float),
                neg_success.to_numpy(dtype=float),
                observed_statistic=ht,
            )
        else:
            p_greater = p_two_sided = np.nan
        if n_blocks and simulations and complete_binary_outcomes:
            pair_outcomes = np.concatenate(
                [pos_success.to_numpy(dtype=float), neg_success.to_numpy(dtype=float)]
            )
            pair_labels = _pairwise_fixed_count_randomizations(
                len(pos),
                len(neg),
                simulations=simulations,
                seed=20260715 + contrast_index,
            )
            simulated = ((pair_labels == 1) * pair_outcomes[None, :]).sum(axis=1) / len(pos) - (
                (pair_labels == 0) * pair_outcomes[None, :]
            ).sum(axis=1) / len(neg)
            p_greater_mc = float((1 + (simulated >= ht - 1e-15).sum()) / (simulations + 1))
            p_two_sided_mc = float(
                (1 + (np.abs(simulated) >= abs(ht) - 1e-15).sum()) / (simulations + 1)
            )
            mc_max_abs_error = float(
                max(abs(p_greater_mc - p_greater), abs(p_two_sided_mc - p_two_sided))
            )
            mc_audit_pass = bool(mc_max_abs_error <= RANDOMIZATION_MC_AUDIT_TOLERANCE)
        else:
            p_greater_mc = p_two_sided_mc = mc_max_abs_error = np.nan
            mc_audit_pass = np.nan
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
        success_bound_low, success_bound_high = difference_bounds(
            {
                "mean_lower_bound": pos_missingness["success_mean_lower_bound"],
                "mean_upper_bound": pos_missingness["success_mean_upper_bound"],
            },
            {
                "mean_lower_bound": neg_missingness["success_mean_lower_bound"],
                "mean_upper_bound": neg_missingness["success_mean_upper_bound"],
            },
        )
        ht_success_bound_low, ht_success_bound_high = difference_bounds(
            {
                "mean_lower_bound": pos_missingness["ht_success_mean_lower_bound"],
                "mean_upper_bound": pos_missingness["ht_success_mean_upper_bound"],
            },
            {
                "mean_lower_bound": neg_missingness["ht_success_mean_lower_bound"],
                "mean_upper_bound": neg_missingness["ht_success_mean_upper_bound"],
            },
        )
        planned_pos = missingness_plan[
            missingness_plan.get("expected_policy", pd.Series(dtype=object)).eq(positive)
        ]
        planned_neg = missingness_plan[
            missingness_plan.get("expected_policy", pd.Series(dtype=object)).eq(negative)
        ]
        planned_pos_values = pd.to_numeric(
            planned_pos.get(
                "success_for_worst_case_bounds",
                pd.Series(index=planned_pos.index, dtype=float),
            ),
            errors="coerce",
        )
        planned_neg_values = pd.to_numeric(
            planned_neg.get(
                "success_for_worst_case_bounds",
                pd.Series(index=planned_neg.index, dtype=float),
            ),
            errors="coerce",
        )
        planned_pos_bounds = bounded_mean(planned_pos_values, lower=0.0, upper=1.0)
        planned_neg_bounds = bounded_mean(planned_neg_values, lower=0.0, upper=1.0)
        treatment_outcome_low, treatment_outcome_high = difference_bounds(
            planned_pos_bounds,
            planned_neg_bounds,
        )
        if treatment_outcome_sensitivity["unassigned_candidate_blocks"]:
            treatment_outcome_low, treatment_outcome_high = -1.0, 1.0
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
                "success_difference_conditional": raw,
                "success_difference_ci_low": float(ci_low),
                "success_difference_ci_high": float(ci_high),
                "success_difference_simultaneous_ci_low": float(simultaneous_low),
                "success_difference_simultaneous_ci_high": float(simultaneous_high),
                "success_difference_design_simultaneous_ci_low": design_simultaneous_low,
                "success_difference_design_simultaneous_ci_high": design_simultaneous_high,
                "success_difference_design_simultaneous_radius": design_radius,
                "success_difference_ht": ht,
                "positive_success_outcomes_missing": pos_success_missing,
                "negative_success_outcomes_missing": neg_success_missing,
                "success_difference_lower_bound": success_bound_low,
                "success_difference_upper_bound": success_bound_high,
                "ht_success_difference_lower_bound": ht_success_bound_low,
                "ht_success_difference_upper_bound": ht_success_bound_high,
                "planned_positive_n": int(len(planned_pos)),
                "planned_negative_n": int(len(planned_neg)),
                "planned_positive_treatment_or_outcome_missing": int(
                    planned_pos_values.isna().sum()
                ),
                "planned_negative_treatment_or_outcome_missing": int(
                    planned_neg_values.isna().sum()
                ),
                "success_difference_treatment_outcome_lower_bound": treatment_outcome_low,
                "success_difference_treatment_outcome_upper_bound": treatment_outcome_high,
                "randomization_p_greater": p_greater,
                "randomization_p_two_sided": p_two_sided,
                "randomization_p_greater_mc_check": p_greater_mc,
                "randomization_p_two_sided_mc_check": p_two_sided_mc,
                "randomization_mc_max_abs_error": mc_max_abs_error,
                "randomization_mc_audit_pass": mc_audit_pass,
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
    if simulations >= RANDOMIZATION_DRAWS and complete_binary_outcomes:
        audit_pass = contrasts["randomization_mc_audit_pass"].fillna(False).astype(bool)
        if not audit_pass.all():
            worst = float(contrasts["randomization_mc_max_abs_error"].max())
            raise RuntimeError(
                "exact-versus-Monte-Carlo randomization audit failed: "
                f"max absolute error {worst:.6f} exceeds "
                f"{RANDOMIZATION_MC_AUDIT_TOLERANCE:.6f}"
            )
    contrasts["holm_p_greater"] = np.nan
    primary_mask = contrasts["primary"].astype(bool)
    contrasts.loc[primary_mask, "holm_p_greater"] = holm_adjust(
        contrasts.loc[primary_mask, "randomization_p_greater"].tolist()
    )

    summary = _finalize_gate_audit(
        audit,
        attempts=attempts,
        collection_first=collection_first,
        release_gate_first=outcome_gate_prefix,
        analysis_first=first,
        release_ready=True,
        confirmatory_cutoff=confirmatory_cutoff,
        eligibility_summary=eligibility_summary,
        simulations=simulations,
    )
    summary["terminal_gate_block_policy"] = str(terminal_gate_block["policy"])
    summary["terminal_gate_block_id"] = str(terminal_gate_block["block_id"])
    summary["primary_estimator"] = (
        "preterminal fixed-count arm-mean difference; identical to conditional HT"
    )
    summary["randomization_inference"] = (
        "exact pairwise-hypergeometric Fisher sharp-null tails conditional on the "
        "nuisance-arm assignment and the two contrasted preterminal arm counts; configured "
        "Monte Carlo draws permute only the contrasted pair and are an audit check only"
    )
    summary["randomization_mc_audit_tolerance"] = RANDOMIZATION_MC_AUDIT_TOLERANCE
    summary["randomization_mc_audit_enforced"] = bool(
        simulations >= RANDOMIZATION_DRAWS and complete_binary_outcomes
    )
    summary["simultaneous_uncertainty"] = (
        "Bonferroni-Newcombe 95% familywise intervals over the two registered primary "
        "contrasts under a binomial interpretation; conditional finite-population "
        "Hoeffding-Serfling intervals simultaneous over all three policy means; Holm-adjusted "
        "one-sided fixed-count randomization p-values"
    )
    summary["treatment_outcome_missingness_sensitivity"] = treatment_outcome_sensitivity
    return panel, model_panel, contrasts, summary


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    assignment_frame = data.q(
        f"""
        select source, event_id, run_ts, observed_at, study_id, model_id,
               policy, metadata_json
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        where study_id = '{STUDY_ID}'
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
    collection_first, _ = first_position_sample(assignment_frame)
    _, release_ready, _ = first_balanced_prefix(
        collection_first, POLICIES, MIN_FIRST_POSITION_PER_POLICY
    )
    if release_ready:
        frame = data.q(
            f"""
            select *
            from read_parquet(
              '{data.table_glob("router_route_attempts")}',
              union_by_name=true
            )
            where study_id = '{STUDY_ID}'
            """
        ).df()
    else:
        frame = assignment_frame
    panel, model_panel, contrasts, summary = analyze(frame, eligibility=eligibility)
    eligibility_rows, eligibility_models, eligibility_runs, _ = eligibility_diagnostics(
        eligibility, prepare_assignment_attempts(assignment_frame)
    )
    save(panel, out_dir, "h81_policy_panel")
    save(model_panel, out_dir, "h81_model_policy_panel")
    save(contrasts, out_dir, "h81_contrasts")
    save(eligibility_rows, out_dir, "h81_eligibility_rows")
    save(eligibility_models, out_dir, "h81_eligibility_models")
    save(eligibility_runs, out_dir, "h81_eligibility_runs")
    save_json(summary, out_dir, "h81_summary")
    return summary
