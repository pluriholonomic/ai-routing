"""Finite-population validation of the stopped H81 randomization design."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save, save_json
from .h81_delegation_decomposition import _exact_pairwise_binary_randomization_pvalues

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


def summarize(
    bias: pd.DataFrame,
    size: pd.DataFrame,
    nuisance_size: pd.DataFrame | None = None,
    power: pd.DataFrame | None = None,
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
        "evidence_status": "simulation_validation_not_empirical_evidence",
        "claim_boundary": (
            "This validates the stopped-design estimator under a synthetic fixed potential-"
            "outcome schedule and reports model-based Bernoulli power scenarios. It does not "
            "validate H81 transport, reveal H81 outcomes, or identify market welfare."
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
    axes[0].legend(frameon=False, fontsize=8)

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
    axes[1].legend(frameon=False, fontsize=8)

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


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    bias = simulate_bias()
    size = simulate_randomization_size()
    nuisance_size = simulate_nuisance_arm_size()
    power = exact_power_grid()
    summary = summarize(bias, size, nuisance_size, power)
    save(bias, out_dir, "h81_theorem_validation_draws")
    save(size, out_dir, "h81_theorem_randomization_size")
    save(nuisance_size, out_dir, "h81_theorem_nuisance_arm_size")
    save(power, out_dir, "h81_theorem_power")
    save_json(summary, out_dir, "h81_theorem_validation_summary")
    plot_validation(bias, size, nuisance_size, power, out_dir)
    return summary
