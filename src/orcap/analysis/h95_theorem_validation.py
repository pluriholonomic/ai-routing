"""Outcome-blind validation of the fixed-horizon H95 randomization design."""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binom
from scipy.stats import t as student_t

from ..capture_decomposition_probes import POLICIES
from ..capture_decomposition_replication import TARGET_TRIPLETS
from .common import DEFAULT_OUT, save, save_json
from .h95_delegation_replication import PRIMARY_FWER_ALPHA, _blocked_design_radius

PRIMARY_COMPARISONS = (
    ("fallback_option_value", "price_order_fallback", "price_only_no_fallback"),
    ("hidden_selection_value", "delegated_default", "price_order_fallback"),
)
POLICY_INDEX = {policy: index for index, policy in enumerate(POLICIES)}
PERMUTATIONS = np.asarray(list(itertools.permutations(range(3))), dtype=np.int8)


def _rotating_pattern(triplets: int, ones: int) -> np.ndarray:
    unit = np.arange(3)[None, :]
    shift = np.arange(triplets)[:, None]
    return (((unit + shift) % 3) < ones).astype(float)


def fixed_potential_outcome_schedules(
    triplets: int = TARGET_TRIPLETS,
) -> dict[str, np.ndarray]:
    """Return fixed binary schedules with sharp, nuisance, and heterogeneous cases."""
    schedules: dict[str, np.ndarray] = {}
    sharp = _rotating_pattern(triplets, ones=1)
    schedules["sharp_null_heterogeneous"] = np.repeat(sharp[:, :, None], 3, axis=2)

    fallback_base = _rotating_pattern(triplets, ones=1)
    fallback_nuisance = 1.0 - fallback_base
    fallback_null = np.empty((triplets, 3, 3), dtype=float)
    fallback_null[:, :, POLICY_INDEX["price_only_no_fallback"]] = fallback_base
    fallback_null[:, :, POLICY_INDEX["price_order_fallback"]] = fallback_base
    fallback_null[:, :, POLICY_INDEX["delegated_default"]] = fallback_nuisance
    schedules["fallback_null_delegation_nuisance"] = fallback_null

    selection_base = _rotating_pattern(triplets, ones=2)
    selection_nuisance = 1.0 - selection_base
    selection_null = np.empty((triplets, 3, 3), dtype=float)
    selection_null[:, :, POLICY_INDEX["price_order_fallback"]] = selection_base
    selection_null[:, :, POLICY_INDEX["delegated_default"]] = selection_base
    selection_null[:, :, POLICY_INDEX["price_only_no_fallback"]] = selection_nuisance
    schedules["selection_null_no_fallback_nuisance"] = selection_null

    index = np.arange(triplets * 3).reshape(triplets, 3)
    score = (17 * index + 11) % 100
    monotone = np.empty((triplets, 3, 3), dtype=float)
    monotone[:, :, POLICY_INDEX["price_only_no_fallback"]] = score < 25
    monotone[:, :, POLICY_INDEX["price_order_fallback"]] = score < 45
    monotone[:, :, POLICY_INDEX["delegated_default"]] = score < 60
    schedules["monotone_components"] = monotone

    heterogeneous = np.empty((triplets, 3, 3), dtype=float)
    base = ((13 * index + 7) % 19) < 9
    heterogeneous[:, :, POLICY_INDEX["price_only_no_fallback"]] = base
    heterogeneous[:, :, POLICY_INDEX["price_order_fallback"]] = np.where(
        index % 4 == 0, 1.0 - base, base
    )
    heterogeneous[:, :, POLICY_INDEX["delegated_default"]] = np.where(
        index % 5 == 0,
        1.0 - heterogeneous[:, :, POLICY_INDEX["price_order_fallback"]],
        heterogeneous[:, :, POLICY_INDEX["price_order_fallback"]],
    )
    schedules["sign_heterogeneous"] = heterogeneous
    return schedules


def _draw_observed_outcomes(
    schedule: np.ndarray,
    *,
    experiments: int,
    rng: np.random.Generator,
) -> np.ndarray:
    triplets = schedule.shape[0]
    assignment = PERMUTATIONS[rng.integers(0, len(PERMUTATIONS), size=(experiments, triplets))]
    observed = np.empty((experiments, triplets, len(POLICIES)), dtype=float)
    triplet_index = np.arange(triplets)[None, :]
    for policy_index in range(len(POLICIES)):
        observed[:, :, policy_index] = schedule[
            triplet_index,
            assignment[:, :, policy_index],
            policy_index,
        ]
    return observed


def _conditional_upper_pvalues(differences: np.ndarray) -> np.ndarray:
    informative = np.count_nonzero(differences, axis=1)
    observed_sum = differences.sum(axis=1).astype(int)
    threshold = np.ceil((observed_sum + informative) / 2.0).astype(int)
    pvalues = binom.sf(threshold - 1, informative, 0.5)
    return np.where(informative == 0, 1.0, pvalues).astype(float)


def _all_policy_upper_tail_table(triplets: int) -> list[np.ndarray]:
    tables: list[np.ndarray] = [np.asarray([1.0])]
    distribution = np.asarray([1.0])
    kernel = np.asarray([1.0 / 3.0] * 3)
    for informative in range(1, triplets + 1):
        distribution = np.convolve(distribution, kernel)
        support = np.arange(-informative, informative + 1)
        upper = np.asarray(
            [math.fsum(distribution[support >= value].tolist()) for value in support]
        )
        tables.append(upper)
    return tables


def _all_policy_upper_pvalues(
    observed: np.ndarray,
    differences: np.ndarray,
    tables: list[np.ndarray],
) -> np.ndarray:
    informative = np.count_nonzero(observed.max(axis=2) - observed.min(axis=2), axis=1)
    observed_sum = differences.sum(axis=1).astype(int)
    return np.asarray(
        [
            tables[int(count)][int(total + count)]
            for count, total in zip(informative, observed_sum, strict=True)
        ]
    )


def _holm_rejects_true_null(true_p: np.ndarray, other_p: np.ndarray, alpha: float) -> np.ndarray:
    return (true_p <= alpha / 2.0) | ((other_p <= alpha / 2.0) & (true_p <= alpha))


def simulate_pairwise_nuisance_size(
    *,
    experiments: int = 5_000,
    triplets: int = TARGET_TRIPLETS,
    seed: int = 20260717,
) -> pd.DataFrame:
    """Stress elementary pairwise tests while the nuisance policy has an effect."""
    schedules = fixed_potential_outcome_schedules(triplets)
    cases = (
        ("fallback_null_delegation_nuisance", "fallback_option_value", 0),
        ("selection_null_no_fallback_nuisance", "hidden_selection_value", 1),
    )
    tables = _all_policy_upper_tail_table(triplets)
    rows: list[dict[str, Any]] = []
    for case_index, (scenario, true_null, true_index) in enumerate(cases):
        rng = np.random.default_rng(seed + case_index)
        observed = _draw_observed_outcomes(schedules[scenario], experiments=experiments, rng=rng)
        corrected: list[np.ndarray] = []
        superseded: list[np.ndarray] = []
        for _, positive, negative in PRIMARY_COMPARISONS:
            differences = (
                observed[:, :, POLICY_INDEX[positive]] - observed[:, :, POLICY_INDEX[negative]]
            )
            corrected.append(_conditional_upper_pvalues(differences))
            superseded.append(_all_policy_upper_pvalues(observed, differences, tables))
        for method, pvalues in (
            ("pairwise_conditional", corrected),
            ("superseded_all_policy", superseded),
        ):
            true_p = pvalues[true_index]
            other_p = pvalues[1 - true_index]
            rows.append(
                {
                    "scenario": scenario,
                    "true_null": true_null,
                    "method": method,
                    "experiments": experiments,
                    "raw_rejection_rate": float(np.mean(true_p <= PRIMARY_FWER_ALPHA)),
                    "holm_true_null_rejection_rate": float(
                        np.mean(_holm_rejects_true_null(true_p, other_p, PRIMARY_FWER_ALPHA))
                    ),
                    "mean_true_null_pvalue": float(np.mean(true_p)),
                }
            )
    return pd.DataFrame(rows)


def simulate_interval_coverage(
    *,
    experiments_per_scenario: int = 5_000,
    triplets: int = TARGET_TRIPLETS,
    seed: int = 20260717,
) -> pd.DataFrame:
    """Audit bias, family coverage, and width over fixed potential schedules."""
    critical = float(student_t.ppf(1.0 - (PRIMARY_FWER_ALPHA / 2.0) / 2.0, df=triplets - 1))
    design_radius = _blocked_design_radius(
        triplets, alpha=PRIMARY_FWER_ALPHA, family_size=len(PRIMARY_COMPARISONS)
    )
    rows: list[dict[str, Any]] = []
    for scenario_index, (scenario, schedule) in enumerate(
        fixed_potential_outcome_schedules(triplets).items()
    ):
        rng = np.random.default_rng(seed + 100 + scenario_index)
        observed = _draw_observed_outcomes(schedule, experiments=experiments_per_scenario, rng=rng)
        paired_coverages: list[np.ndarray] = []
        design_coverages: list[np.ndarray] = []
        paired_widths: list[np.ndarray] = []
        design_widths: list[np.ndarray] = []
        for estimand, positive, negative in PRIMARY_COMPARISONS:
            positive_index = POLICY_INDEX[positive]
            negative_index = POLICY_INDEX[negative]
            differences = observed[:, :, positive_index] - observed[:, :, negative_index]
            estimate = differences.mean(axis=1)
            target = float(
                schedule[:, :, positive_index].mean() - schedule[:, :, negative_index].mean()
            )
            standard_error = differences.std(axis=1, ddof=1) / math.sqrt(triplets)
            paired_low = estimate - critical * standard_error
            paired_high = estimate + critical * standard_error
            design_low = np.maximum(-1.0, estimate - design_radius)
            design_high = np.minimum(1.0, estimate + design_radius)
            paired_coverage = (paired_low <= target) & (target <= paired_high)
            design_coverage = (design_low <= target) & (target <= design_high)
            paired_coverages.append(paired_coverage)
            design_coverages.append(design_coverage)
            paired_widths.append(paired_high - paired_low)
            design_widths.append(design_high - design_low)
            rows.append(
                {
                    "scenario": scenario,
                    "estimand": estimand,
                    "experiments": experiments_per_scenario,
                    "target": target,
                    "mean_estimate": float(np.mean(estimate)),
                    "monte_carlo_bias": float(np.mean(estimate) - target),
                    "paired_t_simultaneous_coverage": float(np.mean(paired_coverage)),
                    "design_hoeffding_coverage": float(np.mean(design_coverage)),
                    "paired_t_mean_width": float(np.mean(paired_high - paired_low)),
                    "design_hoeffding_mean_width": float(np.mean(design_high - design_low)),
                    "paired_t_family_coverage": np.nan,
                    "design_hoeffding_family_coverage": np.nan,
                }
            )
        family_row = {
            "scenario": scenario,
            "estimand": "two_primary_family",
            "experiments": experiments_per_scenario,
            "target": np.nan,
            "mean_estimate": np.nan,
            "monte_carlo_bias": np.nan,
            "paired_t_simultaneous_coverage": np.nan,
            "design_hoeffding_coverage": np.nan,
            "paired_t_mean_width": float(np.mean(np.column_stack(paired_widths))),
            "design_hoeffding_mean_width": float(np.mean(np.column_stack(design_widths))),
            "paired_t_family_coverage": float(np.mean(np.logical_and.reduce(paired_coverages))),
            "design_hoeffding_family_coverage": float(
                np.mean(np.logical_and.reduce(design_coverages))
            ),
        }
        rows.append(family_row)
    return pd.DataFrame(rows)


def summarize(size: pd.DataFrame, coverage: pd.DataFrame) -> dict[str, Any]:
    corrected = size.loc[size["method"].eq("pairwise_conditional")]
    superseded = size.loc[size["method"].eq("superseded_all_policy")]
    family = coverage.loc[coverage["estimand"].eq("two_primary_family")]
    component = coverage.loc[coverage["estimand"].ne("two_primary_family")]
    return {
        "hypothesis": "H95 fixed-horizon randomization validation",
        "outcome_status": "synthetic fixed-schedule audit; no H95 outcome queried",
        "triplets": TARGET_TRIPLETS,
        "pairwise_nuisance_size": {
            "worst_corrected_raw_rejection_rate": float(corrected["raw_rejection_rate"].max()),
            "worst_corrected_holm_true_null_rejection_rate": float(
                corrected["holm_true_null_rejection_rate"].max()
            ),
            "worst_superseded_raw_rejection_rate": float(superseded["raw_rejection_rate"].max()),
            "worst_superseded_holm_true_null_rejection_rate": float(
                superseded["holm_true_null_rejection_rate"].max()
            ),
        },
        "interval_coverage": {
            "worst_paired_t_family_coverage": float(family["paired_t_family_coverage"].min()),
            "worst_design_hoeffding_family_coverage": float(
                family["design_hoeffding_family_coverage"].min()
            ),
            "maximum_absolute_monte_carlo_bias": float(component["monte_carlo_bias"].abs().max()),
            "mean_paired_t_width": float(family["paired_t_mean_width"].mean()),
            "mean_design_hoeffding_width": float(family["design_hoeffding_mean_width"].mean()),
            "design_radius_at_120_triplets": _blocked_design_radius(
                TARGET_TRIPLETS,
                alpha=PRIMARY_FWER_ALPHA,
                family_size=len(PRIMARY_COMPARISONS),
            ),
        },
        "claim_boundary": (
            "The audit validates the registered assignment law and bounded-outcome reporting "
            "rule. It does not reveal an H95 outcome, prove no cross-model interference, or "
            "identify market-wide routing or welfare."
        ),
    }


def plot_validation(size: pd.DataFrame, coverage: pd.DataFrame, out_dir: Path) -> None:
    labels = {
        "fallback_null_delegation_nuisance": "Fallback null",
        "selection_null_no_fallback_nuisance": "Selection null",
        "sharp_null_heterogeneous": "Sharp null",
        "monotone_components": "Monotone",
        "sign_heterogeneous": "Sign-changing",
    }
    methods = ("pairwise_conditional", "superseded_all_policy")
    colors = {"pairwise_conditional": "#2b6ea6", "superseded_all_policy": "#c9583e"}
    method_labels = {
        "pairwise_conditional": "Pairwise conditional",
        "superseded_all_policy": "Superseded all-policy",
    }
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.2))
    scenarios = list(size["scenario"].drop_duplicates())
    x = np.arange(len(scenarios))
    width = 0.36
    for offset, method in enumerate(methods):
        panel = size.loc[size["method"].eq(method)].set_index("scenario").reindex(scenarios)
        axes[0, 0].bar(
            x + (offset - 0.5) * width,
            panel["raw_rejection_rate"],
            width=width,
            color=colors[method],
            label=method_labels[method],
        )
        axes[0, 1].bar(
            x + (offset - 0.5) * width,
            panel["holm_true_null_rejection_rate"],
            width=width,
            color=colors[method],
            label=method_labels[method],
        )
    for axis, title in zip(
        axes[0],
        ("A. Elementary true-null rejection", "B. Holm true-null rejection"),
        strict=True,
    ):
        axis.axhline(PRIMARY_FWER_ALPHA, color="black", linestyle="--", linewidth=0.8)
        axis.set_xticks(x, [labels[item] for item in scenarios])
        axis.set_ylabel("Rejection probability")
        axis.set_title(title)
        axis.set_ylim(0, max(0.12, float(size["raw_rejection_rate"].max()) * 1.15))

    family = coverage.loc[coverage["estimand"].eq("two_primary_family")].copy()
    scenario_order = list(family["scenario"])
    x_family = np.arange(len(family))
    axes[1, 0].plot(
        x_family,
        family["paired_t_family_coverage"],
        marker="o",
        label="Paired t, Bonferroni",
    )
    axes[1, 0].plot(
        x_family,
        family["design_hoeffding_family_coverage"],
        marker="^",
        label="Design Hoeffding",
    )
    axes[1, 0].axhline(0.95, color="black", linestyle="--", linewidth=0.8)
    axes[1, 0].set_xticks(
        x_family,
        [labels.get(item, item.replace("_", " ")) for item in scenario_order],
        rotation=20,
        ha="right",
    )
    axes[1, 0].set_ylabel("Two-contrast family coverage")
    axes[1, 0].set_title("C. Fixed-schedule family coverage")
    axes[1, 0].set_ylim(0.90, 1.005)

    axes[1, 1].plot(
        x_family,
        family["paired_t_mean_width"],
        marker="o",
        label="Paired t, Bonferroni",
    )
    axes[1, 1].plot(
        x_family,
        family["design_hoeffding_mean_width"],
        marker="^",
        label="Design Hoeffding",
    )
    axes[1, 1].set_xticks(
        x_family,
        [labels.get(item, item.replace("_", " ")) for item in scenario_order],
        rotation=20,
        ha="right",
    )
    axes[1, 1].set_ylabel("Mean contrast interval width")
    axes[1, 1].set_title("D. Precision cost")

    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    handles2, legend_labels2 = axes[1, 0].get_legend_handles_labels()
    fig.legend(
        handles + handles2,
        legend_labels + legend_labels2,
        loc="upper center",
        ncol=4,
        frameon=False,
        fontsize=8,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    fig.savefig(out_dir / "h95_theorem_validation.png", dpi=200)
    fig.savefig(out_dir / "h95_theorem_validation.pdf")
    plt.close(fig)


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    experiments: int = 5_000,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    size = simulate_pairwise_nuisance_size(experiments=experiments)
    coverage = simulate_interval_coverage(experiments_per_scenario=experiments)
    summary = summarize(size, coverage)
    save(size, out_dir, "h95_pairwise_nuisance_size")
    save(coverage, out_dir, "h95_interval_coverage")
    save_json(summary, out_dir, "h95_theorem_validation_summary")
    plot_validation(size, coverage, out_dir)
    return summary


def main() -> None:
    run()


if __name__ == "__main__":
    main()
