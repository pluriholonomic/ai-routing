"""Finite-population validation of the stopped H81 randomization design."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import confint_proportions_2indep

from .common import DEFAULT_OUT, save, save_json
from .h80_matched_quote_firmness import holm_adjust
from .h81_delegation_decomposition import (
    _exact_pairwise_binary_randomization_pvalues,
    _simultaneous_serfling_mean_radii,
)

POLICIES = ("delegated_default", "price_only_no_fallback", "price_order_fallback")
CONTRASTS = {
    "fallback_option": ("price_order_fallback", "price_only_no_fallback"),
    "hidden_selection": ("delegated_default", "price_order_fallback"),
    "total_delegation": ("delegated_default", "price_only_no_fallback"),
}


def potential_outcomes(n_blocks: int) -> pd.DataFrame:
    """A fixed, bounded, heterogeneous schedule with policy-specific time trends."""
    block = np.arange(1, n_blocks + 1, dtype=float)
    saturation = 1.0 - np.exp(-block / 55.0)
    return pd.DataFrame(
        {
            "delegated_default": np.clip(
                0.58 + 0.10 * np.sin(block / 8.0) + 0.05 * saturation,
                0.0,
                1.0,
            ),
            "price_only_no_fallback": np.clip(0.18 + 0.64 * saturation, 0.0, 1.0),
            "price_order_fallback": np.clip(0.86 - 0.42 * saturation, 0.0, 1.0),
        }
    )


def stopped_assignment(rng: np.random.Generator, target_per_arm: int) -> np.ndarray:
    """Draw independent production labels through the first balanced-count gate."""
    counts = np.zeros(len(POLICIES), dtype=int)
    labels: list[int] = []
    while int(counts.min()) < target_per_arm:
        label = int(rng.integers(0, len(POLICIES)))
        labels.append(label)
        counts[label] += 1
    return np.asarray(labels, dtype=np.int8)


def _means(
    outcomes: pd.DataFrame,
    labels: np.ndarray,
) -> tuple[dict[str, float], dict[str, float]]:
    observed: dict[str, float] = {}
    truth: dict[str, float] = {}
    for index, policy in enumerate(POLICIES):
        selected = labels == index
        observed[policy] = float(outcomes.loc[selected, policy].mean())
        truth[policy] = float(outcomes[policy].mean())
    return observed, truth


def _contrast(values: dict[str, float], name: str) -> float:
    positive, negative = CONTRASTS[name]
    return values[positive] - values[negative]


def simulate_bias(
    *,
    draws: int = 20_000,
    target_per_arm: int = 40,
    seed: int = 20260717,
) -> pd.DataFrame:
    """Compare the terminal-inclusive estimator with the conditional correction."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for draw in range(draws):
        labels = stopped_assignment(rng, target_per_arm)
        full = potential_outcomes(len(labels))
        preterminal = full.iloc[:-1].reset_index(drop=True)
        corrected_observed, corrected_truth = _means(preterminal, labels[:-1])
        naive_observed, naive_truth = _means(full, labels)
        row: dict[str, Any] = {
            "draw": draw,
            "stopping_blocks": int(len(labels)),
            "terminal_policy": POLICIES[int(labels[-1])],
            "preterminal_counts_json": json.dumps(
                {
                    policy: int((labels[:-1] == index).sum())
                    for index, policy in enumerate(POLICIES)
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        for name in CONTRASTS:
            corrected = _contrast(corrected_observed, name)
            corrected_target = _contrast(corrected_truth, name)
            naive = _contrast(naive_observed, name)
            naive_target = _contrast(naive_truth, name)
            row[f"corrected_{name}"] = corrected
            row[f"corrected_target_{name}"] = corrected_target
            row[f"corrected_error_{name}"] = corrected - corrected_target
            row[f"terminal_inclusive_{name}"] = naive
            row[f"terminal_inclusive_target_{name}"] = naive_target
            row[f"terminal_inclusive_error_{name}"] = naive - naive_target
        rows.append(row)
    return pd.DataFrame(rows)


def simulate_randomization_size(
    *,
    experiments: int = 2_000,
    permutations: int = 999,
    target_per_arm: int = 40,
    seed: int = 20260718,
) -> pd.DataFrame:
    """Evaluate a one-sided fixed-count test under a heterogeneous sharp null."""
    rng = np.random.default_rng(seed)
    rows = []
    for experiment in range(experiments):
        labels = stopped_assignment(rng, target_per_arm)[:-1]
        n_blocks = len(labels)
        block = np.arange(1, n_blocks + 1, dtype=float)
        sharp_null = np.clip(0.45 + 0.25 * np.sin(block / 9.0), 0.0, 1.0)
        positive = POLICIES.index("price_order_fallback")
        negative = POLICIES.index("price_only_no_fallback")

        def statistic(
            candidate: np.ndarray,
            outcomes: np.ndarray = sharp_null,
            positive_label: int = positive,
            negative_label: int = negative,
        ) -> float:
            return float(
                outcomes[candidate == positive_label].mean()
                - outcomes[candidate == negative_label].mean()
            )

        observed = statistic(labels)
        simulated = np.empty(permutations, dtype=float)
        for draw in range(permutations):
            simulated[draw] = statistic(rng.permutation(labels))
        p_greater = float((1 + (simulated >= observed - 1e-15).sum()) / (permutations + 1))
        rows.append(
            {
                "experiment": experiment,
                "n_blocks": n_blocks,
                "observed_statistic": observed,
                "p_greater": p_greater,
                "reject_5pct": p_greater <= 0.05,
            }
        )
    return pd.DataFrame(rows)


def _all_arm_tail_used_before_pairwise_correction(
    outcomes: np.ndarray,
    labels: np.ndarray,
    *,
    positive_label: int,
    negative_label: int,
) -> float:
    """Audit the superseded all-arm sharp-null reference law.

    This is deliberately not imported by the production analyzer.  It is kept
    here only to show why permuting a nuisance arm is invalid for a pairwise
    null when that nuisance policy has a nonzero effect.
    """
    values = np.asarray(outcomes, dtype=float)
    counts = np.bincount(labels, minlength=len(POLICIES)).astype(int)
    observed = float(
        values[labels == positive_label].mean() - values[labels == negative_label].mean()
    )
    successes = int(values.sum())
    denominator = math.comb(len(values), successes)
    n_positive = int(counts[positive_label])
    n_negative = int(counts[negative_label])
    n_other = int(len(values) - n_positive - n_negative)
    tail = []
    support = []
    for positive_successes in range(
        max(0, successes - n_negative - n_other), min(n_positive, successes) + 1
    ):
        for negative_successes in range(
            max(0, successes - positive_successes - n_other),
            min(n_negative, successes - positive_successes) + 1,
        ):
            other_successes = successes - positive_successes - negative_successes
            probability = (
                math.comb(n_positive, positive_successes)
                * math.comb(n_negative, negative_successes)
                * math.comb(n_other, other_successes)
                / denominator
            )
            support.append(probability)
            statistic = positive_successes / n_positive - negative_successes / n_negative
            if statistic >= observed - 1e-15:
                tail.append(probability)
    support_mass = math.fsum(support)
    if not math.isclose(support_mass, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(f"all-arm audit support has mass {support_mass}")
    return float(math.fsum(tail))


def simulate_nuisance_arm_size(
    *,
    experiments: int = 2_000,
    target_per_arm: int = 40,
    seed: int = 20260719,
) -> pd.DataFrame:
    """Stress pairwise size when the untested third policy has an effect."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    scenarios = (
        (
            "fallback_null_delegation_nuisance",
            POLICIES.index("price_order_fallback"),
            POLICIES.index("price_only_no_fallback"),
            POLICIES.index("delegated_default"),
        ),
        (
            "selection_null_no_fallback_nuisance",
            POLICIES.index("delegated_default"),
            POLICIES.index("price_order_fallback"),
            POLICIES.index("price_only_no_fallback"),
        ),
    )
    for experiment in range(experiments):
        labels = stopped_assignment(rng, target_per_arm)[:-1]
        block = np.arange(len(labels), dtype=int)
        # The contrasted policies share this fixed binary schedule exactly.
        common = ((37 * block + 17 * experiment) % 100 < 52).astype(float)
        # The untested policy has a large, time-varying effect.  It is not part
        # of the pairwise null and must not enter the reference permutation.
        nuisance = ((19 * block + 11 * experiment) % 100 < 88).astype(float)
        for scenario, positive, negative, other in scenarios:
            observed = np.where(labels == other, nuisance, common)
            positive_outcomes = observed[labels == positive]
            negative_outcomes = observed[labels == negative]
            pairwise_p, _ = _exact_pairwise_binary_randomization_pvalues(
                positive_outcomes,
                negative_outcomes,
            )
            all_arm_p = _all_arm_tail_used_before_pairwise_correction(
                observed,
                labels,
                positive_label=positive,
                negative_label=negative,
            )
            rows.append(
                {
                    "experiment": experiment,
                    "scenario": scenario,
                    "n_blocks": int(len(labels)),
                    "positive_n": int(len(positive_outcomes)),
                    "negative_n": int(len(negative_outcomes)),
                    "nuisance_n": int((labels == other).sum()),
                    "pairwise_p_greater": pairwise_p,
                    "all_arm_p_greater": all_arm_p,
                    "pairwise_reject_5pct": bool(pairwise_p <= 0.05),
                    "all_arm_reject_5pct": bool(all_arm_p <= 0.05),
                }
            )
    return pd.DataFrame(rows)


def exact_pairwise_bernoulli_power(
    *,
    n_positive: int,
    n_negative: int,
    p_positive: float,
    p_negative: float,
    alpha: float,
) -> float:
    """Exact scenario power for the conditional one-sided pairwise Fisher test."""
    if (
        n_positive <= 0
        or n_negative <= 0
        or not 0.0 <= p_positive <= 1.0
        or not 0.0 <= p_negative <= 1.0
        or not 0.0 < alpha < 1.0
    ):
        raise ValueError("invalid exact-power inputs")

    def binomial_probability(k: int, n: int, probability: float) -> float:
        return math.comb(n, k) * probability**k * (1.0 - probability) ** (n - k)

    rejection_probability = 0.0
    for positive_successes in range(n_positive + 1):
        positive_outcomes = np.concatenate(
            [
                np.ones(positive_successes, dtype=float),
                np.zeros(n_positive - positive_successes, dtype=float),
            ]
        )
        positive_probability = binomial_probability(positive_successes, n_positive, p_positive)
        for negative_successes in range(n_negative + 1):
            negative_outcomes = np.concatenate(
                [
                    np.ones(negative_successes, dtype=float),
                    np.zeros(n_negative - negative_successes, dtype=float),
                ]
            )
            p_value, _ = _exact_pairwise_binary_randomization_pvalues(
                positive_outcomes,
                negative_outcomes,
            )
            if p_value <= alpha:
                rejection_probability += positive_probability * binomial_probability(
                    negative_successes, n_negative, p_negative
                )
    return float(rejection_probability)


def exact_power_grid(
    *,
    n_positive: int = 39,
    n_negative: int = 40,
) -> pd.DataFrame:
    """Conservative pre-outcome power surface at the minimum preterminal counts."""
    rows: list[dict[str, Any]] = []
    for baseline in (0.25, 0.50, 0.75):
        for effect in np.arange(0.0, 0.5000001, 0.025):
            p_positive = baseline + float(effect)
            if p_positive > 1.0 + 1e-12:
                continue
            for alpha, label in ((0.05, "unadjusted_5pct"), (0.025, "bonferroni_2p5pct")):
                rows.append(
                    {
                        "negative_success_probability": baseline,
                        "effect": float(effect),
                        "positive_success_probability": min(1.0, p_positive),
                        "n_positive": n_positive,
                        "n_negative": n_negative,
                        "test_alpha": alpha,
                        "multiplicity_scenario": label,
                        "exact_power": exact_pairwise_bernoulli_power(
                            n_positive=n_positive,
                            n_negative=n_negative,
                            p_positive=min(1.0, p_positive),
                            p_negative=baseline,
                            alpha=alpha,
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _binary_potential_outcomes(n_blocks: int, scenario: str) -> pd.DataFrame:
    """Return fixed binary schedules used only for interval-coverage audits."""
    block = np.arange(n_blocks, dtype=int)
    latent = (37 * block + 11 * (block // 7) + 13) % 100
    if scenario == "sharp_null_heterogeneous":
        common = (latent < (35 + 30 * ((block // 11) % 2))).astype(float)
        values = {policy: common.copy() for policy in POLICIES}
    elif scenario == "monotone_midrange":
        values = {
            "price_only_no_fallback": (latent < 30).astype(float),
            "price_order_fallback": (latent < 50).astype(float),
            "delegated_default": (latent < 70).astype(float),
        }
    elif scenario == "heterogeneous_sign":
        no_fallback = (latent < 45).astype(float)
        fallback = np.where((block // 9) % 2 == 0, latent < 75, latent < 20).astype(float)
        delegated = np.where((block // 13) % 2 == 0, latent < 25, latent < 80).astype(float)
        values = {
            "price_only_no_fallback": no_fallback,
            "price_order_fallback": fallback,
            "delegated_default": delegated,
        }
    elif scenario == "rare_success":
        values = {
            "price_only_no_fallback": (latent < 5).astype(float),
            "price_order_fallback": (latent < 15).astype(float),
            "delegated_default": (latent < 25).astype(float),
        }
    elif scenario == "near_ceiling":
        values = {
            "price_only_no_fallback": (latent < 75).astype(float),
            "price_order_fallback": (latent < 85).astype(float),
            "delegated_default": (latent < 95).astype(float),
        }
    else:
        raise ValueError(f"unknown interval-coverage scenario: {scenario}")
    return pd.DataFrame(values).reindex(columns=POLICIES)


def simulate_interval_coverage(
    *,
    experiments_per_scenario: int = 3_000,
    target_per_arm: int = 40,
    seed: int = 20260720,
) -> pd.DataFrame:
    """Audit descriptive and design-valid intervals under stopped assignment."""
    rng = np.random.default_rng(seed)
    scenarios = (
        "sharp_null_heterogeneous",
        "monotone_midrange",
        "heterogeneous_sign",
        "rare_success",
        "near_ceiling",
    )
    primary = {
        "fallback_option": CONTRASTS["fallback_option"],
        "hidden_selection": CONTRASTS["hidden_selection"],
    }
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        for experiment in range(experiments_per_scenario):
            labels = stopped_assignment(rng, target_per_arm)[:-1]
            outcomes = _binary_potential_outcomes(len(labels), scenario)
            counts = pd.Series(
                {policy: int((labels == index).sum()) for index, policy in enumerate(POLICIES)}
            )
            radii = _simultaneous_serfling_mean_radii(counts)
            contrast_rows: list[dict[str, Any]] = []
            for name, (positive, negative) in primary.items():
                positive_index = POLICIES.index(positive)
                negative_index = POLICIES.index(negative)
                positive_observed = outcomes.loc[labels == positive_index, positive]
                negative_observed = outcomes.loc[labels == negative_index, negative]
                estimate = float(positive_observed.mean() - negative_observed.mean())
                truth = float(outcomes[positive].mean() - outcomes[negative].mean())
                marginal_low, marginal_high = confint_proportions_2indep(
                    int(positive_observed.sum()),
                    len(positive_observed),
                    int(negative_observed.sum()),
                    len(negative_observed),
                    method="newcomb",
                    compare="diff",
                )
                bonferroni_low, bonferroni_high = confint_proportions_2indep(
                    int(positive_observed.sum()),
                    len(positive_observed),
                    int(negative_observed.sum()),
                    len(negative_observed),
                    method="newcomb",
                    compare="diff",
                    alpha=0.025,
                )
                design_radius = radii[positive] + radii[negative]
                design_low = max(-1.0, estimate - design_radius)
                design_high = min(1.0, estimate + design_radius)
                contrast_rows.append(
                    {
                        "experiment": experiment,
                        "scenario": scenario,
                        "estimand": name,
                        "n_blocks": int(len(labels)),
                        "positive_n": int(len(positive_observed)),
                        "negative_n": int(len(negative_observed)),
                        "truth": truth,
                        "estimate": estimate,
                        "newcombe_marginal_low": float(marginal_low),
                        "newcombe_marginal_high": float(marginal_high),
                        "newcombe_marginal_covers": bool(marginal_low <= truth <= marginal_high),
                        "newcombe_bonferroni_low": float(bonferroni_low),
                        "newcombe_bonferroni_high": float(bonferroni_high),
                        "newcombe_bonferroni_covers": bool(
                            bonferroni_low <= truth <= bonferroni_high
                        ),
                        "design_serfling_low": design_low,
                        "design_serfling_high": design_high,
                        "design_serfling_covers": bool(design_low <= truth <= design_high),
                    }
                )
            joint_newcombe = all(row["newcombe_bonferroni_covers"] for row in contrast_rows)
            joint_design = all(row["design_serfling_covers"] for row in contrast_rows)
            for row in contrast_rows:
                row["newcombe_joint_family_covers"] = joint_newcombe
                row["design_serfling_joint_family_covers"] = joint_design
                row["newcombe_marginal_width"] = (
                    row["newcombe_marginal_high"] - row["newcombe_marginal_low"]
                )
                row["newcombe_bonferroni_width"] = (
                    row["newcombe_bonferroni_high"] - row["newcombe_bonferroni_low"]
                )
                row["design_serfling_width"] = (
                    row["design_serfling_high"] - row["design_serfling_low"]
                )
                rows.append(row)
    return pd.DataFrame(rows)


def _binomial_pmf(n: int, probability: float) -> np.ndarray:
    return np.asarray(
        [
            math.comb(n, successes)
            * probability**successes
            * (1.0 - probability) ** (n - successes)
            for successes in range(n + 1)
        ],
        dtype=float,
    )


def exact_joint_holm_power(
    *,
    counts: dict[str, int],
    probabilities: dict[str, float],
    alpha: float = 0.05,
) -> dict[str, float]:
    """Exact binomial-scenario rejection probabilities for the two-test Holm family."""
    if set(counts) != set(POLICIES) or set(probabilities) != set(POLICIES):
        raise ValueError("counts and probabilities must cover every H81 policy")
    if any(int(counts[policy]) <= 0 for policy in POLICIES):
        raise ValueError("all policy counts must be positive")
    if any(not 0.0 <= float(probabilities[policy]) <= 1.0 for policy in POLICIES):
        raise ValueError("all success probabilities must lie in [0, 1]")

    no_fallback = "price_only_no_fallback"
    fallback = "price_order_fallback"
    delegated = "delegated_default"
    pmf = {
        policy: _binomial_pmf(int(counts[policy]), float(probabilities[policy]))
        for policy in POLICIES
    }
    fallback_p = np.empty((counts[fallback] + 1, counts[no_fallback] + 1), dtype=float)
    selection_p = np.empty((counts[delegated] + 1, counts[fallback] + 1), dtype=float)
    for fallback_successes in range(counts[fallback] + 1):
        fallback_outcomes = np.concatenate(
            [
                np.ones(fallback_successes, dtype=float),
                np.zeros(counts[fallback] - fallback_successes, dtype=float),
            ]
        )
        for no_fallback_successes in range(counts[no_fallback] + 1):
            no_fallback_outcomes = np.concatenate(
                [
                    np.ones(no_fallback_successes, dtype=float),
                    np.zeros(counts[no_fallback] - no_fallback_successes, dtype=float),
                ]
            )
            fallback_p[fallback_successes, no_fallback_successes], _ = (
                _exact_pairwise_binary_randomization_pvalues(
                    fallback_outcomes,
                    no_fallback_outcomes,
                )
            )
        for delegated_successes in range(counts[delegated] + 1):
            delegated_outcomes = np.concatenate(
                [
                    np.ones(delegated_successes, dtype=float),
                    np.zeros(counts[delegated] - delegated_successes, dtype=float),
                ]
            )
            selection_p[delegated_successes, fallback_successes], _ = (
                _exact_pairwise_binary_randomization_pvalues(
                    delegated_outcomes,
                    fallback_outcomes,
                )
            )

    fallback_reject = 0.0
    selection_reject = 0.0
    any_reject = 0.0
    both_reject = 0.0
    for delegated_successes, delegated_probability in enumerate(pmf[delegated]):
        for fallback_successes, fallback_probability in enumerate(pmf[fallback]):
            for no_fallback_successes, no_fallback_probability in enumerate(pmf[no_fallback]):
                mass = delegated_probability * fallback_probability * no_fallback_probability
                adjusted = holm_adjust(
                    [
                        fallback_p[fallback_successes, no_fallback_successes],
                        selection_p[delegated_successes, fallback_successes],
                    ]
                )
                fallback_hit = bool(adjusted[0] <= alpha)
                selection_hit = bool(adjusted[1] <= alpha)
                fallback_reject += mass * fallback_hit
                selection_reject += mass * selection_hit
                any_reject += mass * (fallback_hit or selection_hit)
                both_reject += mass * (fallback_hit and selection_hit)
    return {
        "fallback_rejection_probability": float(fallback_reject),
        "selection_rejection_probability": float(selection_reject),
        "any_rejection_probability": float(any_reject),
        "both_rejection_probability": float(both_reject),
    }


def exact_joint_holm_power_grid() -> pd.DataFrame:
    """Power and mixed-null FWER across every minimum-count terminal policy."""
    rows: list[dict[str, Any]] = []
    for terminal_policy in POLICIES:
        counts = {policy: 40 for policy in POLICIES}
        counts[terminal_policy] = 39
        for effect in np.arange(0.0, 0.4000001, 0.05):
            scenarios = {
                "fallback_only": {
                    "price_only_no_fallback": 0.50,
                    "price_order_fallback": 0.50 + effect,
                    "delegated_default": 0.50 + effect,
                },
                "selection_only": {
                    "price_only_no_fallback": 0.50,
                    "price_order_fallback": 0.50,
                    "delegated_default": 0.50 + effect,
                },
                "equal_components": {
                    "price_only_no_fallback": 0.20,
                    "price_order_fallback": 0.20 + effect,
                    "delegated_default": 0.20 + 2.0 * effect,
                },
            }
            for scenario, probabilities in scenarios.items():
                if max(probabilities.values()) > 1.0 + 1e-12:
                    continue
                result = exact_joint_holm_power(
                    counts=counts,
                    probabilities={
                        policy: min(1.0, float(probabilities[policy])) for policy in POLICIES
                    },
                )
                rows.append(
                    {
                        "terminal_policy": terminal_policy,
                        "scenario": scenario,
                        "effect_per_nonnull_component": float(effect),
                        **{f"n_{policy}": count for policy, count in counts.items()},
                        **{f"p_{policy}": value for policy, value in probabilities.items()},
                        **result,
                    }
                )
    return pd.DataFrame(rows)


def summarize(
    bias: pd.DataFrame,
    size: pd.DataFrame,
    nuisance_size: pd.DataFrame | None = None,
    power: pd.DataFrame | None = None,
    interval_coverage: pd.DataFrame | None = None,
    joint_power: pd.DataFrame | None = None,
) -> dict[str, Any]:
    contrast_rows = []
    for name in CONTRASTS:
        corrected = bias[f"corrected_error_{name}"]
        naive = bias[f"terminal_inclusive_error_{name}"]
        contrast_rows.append(
            {
                "estimand": name,
                "corrected_bias": float(corrected.mean()),
                "corrected_monte_carlo_se": float(corrected.std(ddof=1) / np.sqrt(len(corrected))),
                "corrected_rmse": float(np.sqrt(np.square(corrected).mean())),
                "terminal_inclusive_bias": float(naive.mean()),
                "terminal_inclusive_monte_carlo_se": float(naive.std(ddof=1) / np.sqrt(len(naive))),
                "terminal_inclusive_rmse": float(np.sqrt(np.square(naive).mean())),
            }
        )
    reject_rate = float(size["reject_5pct"].mean())
    reject_se = float(np.sqrt(reject_rate * (1.0 - reject_rate) / len(size)))
    nuisance_rows: list[dict[str, Any]] = []
    if nuisance_size is not None and not nuisance_size.empty:
        for scenario, group in nuisance_size.groupby("scenario", sort=True):
            pairwise_rate = float(group["pairwise_reject_5pct"].mean())
            all_arm_rate = float(group["all_arm_reject_5pct"].mean())
            nuisance_rows.append(
                {
                    "scenario": str(scenario),
                    "experiments": int(len(group)),
                    "pairwise_rejection_rate_5pct": pairwise_rate,
                    "pairwise_rejection_rate_mc_se": float(
                        np.sqrt(pairwise_rate * (1.0 - pairwise_rate) / len(group))
                    ),
                    "superseded_all_arm_rejection_rate_5pct": all_arm_rate,
                    "superseded_all_arm_rejection_rate_mc_se": float(
                        np.sqrt(all_arm_rate * (1.0 - all_arm_rate) / len(group))
                    ),
                }
            )
    mde_rows: list[dict[str, Any]] = []
    if power is not None and not power.empty:
        for (baseline, scenario), group in power.groupby(
            ["negative_success_probability", "multiplicity_scenario"], sort=True
        ):
            ordered = group.sort_values("effect")
            powered = ordered[ordered["exact_power"].ge(0.80)]
            mde_rows.append(
                {
                    "negative_success_probability": float(baseline),
                    "multiplicity_scenario": str(scenario),
                    "minimum_grid_effect_for_80pct_power": (
                        float(powered["effect"].iloc[0]) if len(powered) else None
                    ),
                    "maximum_power_on_grid": float(ordered["exact_power"].max()),
                }
            )
    interval_rows: list[dict[str, Any]] = []
    if interval_coverage is not None and not interval_coverage.empty:
        for (scenario, estimand), group in interval_coverage.groupby(
            ["scenario", "estimand"], sort=True
        ):
            interval_rows.append(
                {
                    "scenario": str(scenario),
                    "estimand": str(estimand),
                    "experiments": int(len(group)),
                    "newcombe_marginal_coverage": float(group["newcombe_marginal_covers"].mean()),
                    "newcombe_bonferroni_coverage": float(
                        group["newcombe_bonferroni_covers"].mean()
                    ),
                    "design_serfling_coverage": float(group["design_serfling_covers"].mean()),
                    "mean_newcombe_marginal_width": float(group["newcombe_marginal_width"].mean()),
                    "mean_newcombe_bonferroni_width": float(
                        group["newcombe_bonferroni_width"].mean()
                    ),
                    "mean_design_serfling_width": float(group["design_serfling_width"].mean()),
                }
            )
        for scenario, group in interval_coverage.groupby("scenario", sort=True):
            unique = group.drop_duplicates(["scenario", "experiment"])
            interval_rows.append(
                {
                    "scenario": str(scenario),
                    "estimand": "joint_primary_family",
                    "experiments": int(len(unique)),
                    "newcombe_joint_family_coverage": float(
                        unique["newcombe_joint_family_covers"].mean()
                    ),
                    "design_serfling_joint_family_coverage": float(
                        unique["design_serfling_joint_family_covers"].mean()
                    ),
                }
            )
    joint_power_rows: list[dict[str, Any]] = []
    if joint_power is not None and not joint_power.empty:
        relevant_column = {
            "fallback_only": "fallback_rejection_probability",
            "selection_only": "selection_rejection_probability",
            "equal_components": "both_rejection_probability",
        }
        for scenario, group in joint_power.groupby("scenario", sort=True):
            worst = (
                group.groupby("effect_per_nonnull_component", sort=True)[
                    relevant_column[str(scenario)]
                ]
                .min()
                .reset_index(name="worst_terminal_policy_power")
            )
            powered = worst[worst["worst_terminal_policy_power"].ge(0.80)]
            row: dict[str, Any] = {
                "scenario": str(scenario),
                "power_definition": relevant_column[str(scenario)],
                "minimum_grid_effect_for_80pct_worst_terminal_power": (
                    float(powered["effect_per_nonnull_component"].iloc[0]) if len(powered) else None
                ),
                "maximum_worst_terminal_policy_power": float(
                    worst["worst_terminal_policy_power"].max()
                ),
            }
            if scenario == "fallback_only":
                row["maximum_mixed_null_false_rejection_probability"] = float(
                    group["selection_rejection_probability"].max()
                )
            elif scenario == "selection_only":
                row["maximum_mixed_null_false_rejection_probability"] = float(
                    group["fallback_rejection_probability"].max()
                )
            joint_power_rows.append(row)
    return {
        "hypothesis": "H81 stopped-design estimator validation",
        "bias_draws": int(len(bias)),
        "size_experiments": int(len(size)),
        "mean_stopping_blocks": float(bias["stopping_blocks"].mean()),
        "p95_stopping_blocks": float(bias["stopping_blocks"].quantile(0.95)),
        "contrast_validation": contrast_rows,
        "randomization_test_rejection_rate_5pct": reject_rate,
        "randomization_test_rejection_rate_mc_se": reject_se,
        "nuisance_arm_size_audit": nuisance_rows,
        "minimum_detectable_effect_grid": mde_rows,
        "interval_coverage_audit": interval_rows,
        "joint_holm_power_audit": joint_power_rows,
        "evidence_status": "simulation_validation_not_empirical_evidence",
        "claim_boundary": (
            "This validates the stopped-design estimator under a synthetic fixed potential-"
            "outcome schedule, audits descriptive interval coverage, validates a conservative "
            "finite-population confidence set, and reports model-based Bernoulli power "
            "scenarios. It does not validate H81 transport, reveal H81 outcomes, or identify "
            "market welfare."
        ),
    }


def plot_validation(
    bias: pd.DataFrame,
    size: pd.DataFrame,
    nuisance_size: pd.DataFrame,
    power: pd.DataFrame,
    out_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    names = list(CONTRASTS)
    corrected = [float(bias[f"corrected_error_{name}"].mean()) for name in names]
    naive = [float(bias[f"terminal_inclusive_error_{name}"].mean()) for name in names]
    corrected_se = [
        float(bias[f"corrected_error_{name}"].std(ddof=1) / np.sqrt(len(bias))) for name in names
    ]
    naive_se = [
        float(bias[f"terminal_inclusive_error_{name}"].std(ddof=1) / np.sqrt(len(bias)))
        for name in names
    ]
    x = np.arange(len(names))
    fig, axes_grid = plt.subplots(2, 2, figsize=(10.5, 7.0))
    axes = axes_grid.ravel()
    axes[0].errorbar(
        x - 0.08,
        corrected,
        yerr=np.asarray(corrected_se) * 1.96,
        fmt="o",
        label="Preterminal conditional",
        color="#2369a1",
    )
    axes[0].errorbar(
        x + 0.08,
        naive,
        yerr=np.asarray(naive_se) * 1.96,
        fmt="s",
        label="Terminal-inclusive",
        color="#c7553d",
    )
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set_xticks(x, ["Fallback", "Selection", "Total"])
    axes[0].set_ylabel("Monte Carlo bias")
    axes[0].set_title("A. Stopping-rule bias audit")
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")

    ordered = np.sort(size["p_greater"].to_numpy(dtype=float))
    empirical = np.arange(1, len(ordered) + 1) / len(ordered)
    axes[1].plot(ordered, empirical, color="#2369a1", label="Fixed-count test")
    axes[1].plot([0, 1], [0, 1], linestyle="--", color="black", linewidth=0.8)
    axes[1].axvline(0.05, linestyle=":", color="#c7553d", linewidth=1.0)
    axes[1].set_xlim(0, 1)
    axes[1].set_ylim(0, 1)
    axes[1].set_xlabel("Randomization p-value")
    axes[1].set_ylabel("Empirical CDF")
    axes[1].set_title("B. Global sharp-null size")
    axes[1].legend(frameon=False, fontsize=8, loc="lower right")

    nuisance_summary = (
        nuisance_size.groupby("scenario", sort=True)[
            ["pairwise_reject_5pct", "all_arm_reject_5pct"]
        ]
        .mean()
        .reset_index()
    )
    nx = np.arange(len(nuisance_summary))
    axes[2].bar(
        nx - 0.18,
        nuisance_summary["pairwise_reject_5pct"],
        width=0.36,
        color="#2369a1",
        label="Pairwise conditional",
    )
    axes[2].bar(
        nx + 0.18,
        nuisance_summary["all_arm_reject_5pct"],
        width=0.36,
        color="#c7553d",
        label="Superseded all-arm",
    )
    axes[2].axhline(0.05, linestyle="--", color="black", linewidth=0.8)
    axes[2].set_xticks(nx, ["Fallback null", "Selection null"])
    axes[2].set_ylabel("False rejection rate")
    axes[2].set_title("C. Nuisance-arm stress test")
    axes[2].legend(frameon=False, fontsize=8)

    power_mid = power[power["negative_success_probability"].eq(0.50)]
    for scenario, group in power_mid.groupby("multiplicity_scenario", sort=True):
        label = "Unadjusted 5%" if scenario == "unadjusted_5pct" else "Bonferroni 2.5%"
        axes[3].plot(
            group["effect"],
            group["exact_power"],
            marker="o",
            markersize=2.5,
            label=label,
        )
    axes[3].axhline(0.80, linestyle="--", color="black", linewidth=0.8)
    axes[3].set_xlim(0.0, 0.5)
    axes[3].set_ylim(0.0, 1.0)
    axes[3].set_xlabel("Success-probability effect")
    axes[3].set_ylabel("Exact scenario power")
    axes[3].set_title("D. Minimum-count power, baseline 50%")
    axes[3].legend(frameon=False, fontsize=8)
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h81_theorem_validation.png", dpi=200)
    fig.savefig(out_dir / "h81_theorem_validation.pdf")
    plt.close(fig)


def plot_interval_coverage(interval_coverage: pd.DataFrame, out_dir: Path) -> None:
    """Plot marginal coverage, family coverage, and precision tradeoffs."""
    import matplotlib.pyplot as plt

    scenario_order = [
        "sharp_null_heterogeneous",
        "monotone_midrange",
        "heterogeneous_sign",
        "rare_success",
        "near_ceiling",
    ]
    labels = ["Sharp null", "Monotone", "Sign-changing", "Rare", "Ceiling"]
    by_estimand = (
        interval_coverage.groupby(["scenario", "estimand"], sort=False)
        .agg(
            newcombe_marginal_coverage=("newcombe_marginal_covers", "mean"),
            design_coverage=("design_serfling_covers", "mean"),
            newcombe_width=("newcombe_marginal_width", "mean"),
            bonferroni_width=("newcombe_bonferroni_width", "mean"),
            design_width=("design_serfling_width", "mean"),
        )
        .reset_index()
    )
    worst = (
        by_estimand.groupby("scenario", sort=False)
        .agg(
            newcombe_marginal_coverage=("newcombe_marginal_coverage", "min"),
            design_coverage=("design_coverage", "min"),
            newcombe_width=("newcombe_width", "mean"),
            bonferroni_width=("bonferroni_width", "mean"),
            design_width=("design_width", "mean"),
        )
        .reindex(scenario_order)
    )
    joint = (
        interval_coverage.drop_duplicates(["scenario", "experiment"])
        .groupby("scenario", sort=False)
        .agg(
            newcombe_joint=("newcombe_joint_family_covers", "mean"),
            design_joint=("design_serfling_joint_family_covers", "mean"),
        )
        .reindex(scenario_order)
    )
    x = np.arange(len(scenario_order))
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8))
    axes[0].bar(
        x - 0.18,
        worst["newcombe_marginal_coverage"],
        width=0.36,
        label="Newcombe descriptive",
        color="#c7553d",
    )
    axes[0].bar(
        x + 0.18,
        worst["design_coverage"],
        width=0.36,
        label="Design Hoeffding-Serfling",
        color="#2369a1",
    )
    axes[0].axhline(0.95, color="black", linestyle="--", linewidth=0.8)
    axes[0].set_ylim(0.85, 1.005)
    axes[0].set_ylabel("Coverage probability")
    axes[0].set_title("A. Worst marginal coverage")

    axes[1].bar(
        x - 0.18,
        joint["newcombe_joint"],
        width=0.36,
        label="Bonferroni-Newcombe",
        color="#c7553d",
    )
    axes[1].bar(
        x + 0.18,
        joint["design_joint"],
        width=0.36,
        label="Design Hoeffding-Serfling",
        color="#2369a1",
    )
    axes[1].axhline(0.95, color="black", linestyle="--", linewidth=0.8)
    axes[1].set_ylim(0.85, 1.005)
    axes[1].set_ylabel("Joint family coverage")
    axes[1].set_title("B. Two-contrast family coverage")

    axes[2].plot(x, worst["newcombe_width"], marker="o", label="Newcombe 95%")
    axes[2].plot(x, worst["bonferroni_width"], marker="s", label="Bonferroni-Newcombe")
    axes[2].plot(x, worst["design_width"], marker="^", label="Design Hoeffding-Serfling")
    axes[2].set_ylabel("Mean interval width")
    axes[2].set_title("C. Precision cost")
    axes[2].legend(frameon=False, fontsize=8)
    handles, _ = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        ["Model-based interval", "Design Hoeffding-Serfling"],
        frameon=False,
        fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.43, 1.01),
        ncol=2,
    )
    for axis in axes:
        axis.set_xticks(x, labels, rotation=28, ha="right")
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h81_interval_coverage.png", dpi=200)
    fig.savefig(out_dir / "h81_interval_coverage.pdf")
    plt.close(fig)


def plot_joint_holm_power(joint_power: pd.DataFrame, out_dir: Path) -> None:
    """Plot conservative minimum-count power across terminal-arm identities."""
    import matplotlib.pyplot as plt

    definitions = {
        "fallback_only": ("fallback_rejection_probability", "Fallback power"),
        "selection_only": ("selection_rejection_probability", "Selection power"),
        "equal_components": ("both_rejection_probability", "Power to reject both"),
    }
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.2), sharey=True)
    for axis, (scenario, (column, title)) in zip(axes, definitions.items(), strict=True):
        group = joint_power[joint_power["scenario"].eq(scenario)]
        summarized = group.groupby("effect_per_nonnull_component", sort=True).agg(
            relevant_power=(column, "min"),
            any_power=("any_rejection_probability", "min"),
            both_power=("both_rejection_probability", "min"),
        )
        axis.plot(
            summarized.index,
            summarized["relevant_power"],
            marker="o",
            label=title,
            color="#2369a1",
        )
        axis.plot(
            summarized.index,
            summarized["any_power"],
            linestyle="--",
            label="Any rejection",
            color="#c7553d",
        )
        if scenario != "equal_components":
            null_column = (
                "selection_rejection_probability"
                if scenario == "fallback_only"
                else "fallback_rejection_probability"
            )
            false_null = group.groupby("effect_per_nonnull_component", sort=True)[null_column].max()
            axis.plot(
                false_null.index,
                false_null,
                linestyle=":",
                label="True-null false rejection",
                color="#6f6f6f",
            )
        axis.axhline(0.80, color="black", linestyle="--", linewidth=0.8)
        axis.set_title(title)
        axis.set_xlabel("Effect per nonnull component")
        axis.set_ylim(0.0, 1.0)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(frameon=False, fontsize=7)
    axes[0].set_ylabel("Exact Holm rejection probability")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h81_joint_holm_power.png", dpi=200)
    fig.savefig(out_dir / "h81_joint_holm_power.pdf")
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    bias = simulate_bias()
    size = simulate_randomization_size()
    nuisance_size = simulate_nuisance_arm_size()
    power = exact_power_grid()
    interval_coverage = simulate_interval_coverage()
    joint_power = exact_joint_holm_power_grid()
    summary = summarize(bias, size, nuisance_size, power, interval_coverage, joint_power)
    save(bias, out_dir, "h81_theorem_validation_draws")
    save(size, out_dir, "h81_theorem_randomization_size")
    save(nuisance_size, out_dir, "h81_theorem_nuisance_arm_size")
    save(power, out_dir, "h81_theorem_power")
    save(interval_coverage, out_dir, "h81_interval_coverage")
    save(joint_power, out_dir, "h81_joint_holm_power")
    save_json(summary, out_dir, "h81_theorem_validation_summary")
    plot_validation(bias, size, nuisance_size, power, out_dir)
    plot_interval_coverage(interval_coverage, out_dir)
    plot_joint_holm_power(joint_power, out_dir)
    return summary
