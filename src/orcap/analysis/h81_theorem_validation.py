"""Finite-population validation of the stopped H81 randomization design."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save, save_json

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


def summarize(bias: pd.DataFrame, size: pd.DataFrame) -> dict[str, Any]:
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
                "terminal_inclusive_monte_carlo_se": float(
                    naive.std(ddof=1) / np.sqrt(len(naive))
                ),
                "terminal_inclusive_rmse": float(np.sqrt(np.square(naive).mean())),
            }
        )
    reject_rate = float(size["reject_5pct"].mean())
    reject_se = float(np.sqrt(reject_rate * (1.0 - reject_rate) / len(size)))
    return {
        "hypothesis": "H81 stopped-design estimator validation",
        "bias_draws": int(len(bias)),
        "size_experiments": int(len(size)),
        "mean_stopping_blocks": float(bias["stopping_blocks"].mean()),
        "p95_stopping_blocks": float(bias["stopping_blocks"].quantile(0.95)),
        "contrast_validation": contrast_rows,
        "randomization_test_rejection_rate_5pct": reject_rate,
        "randomization_test_rejection_rate_mc_se": reject_se,
        "evidence_status": "simulation_validation_not_empirical_evidence",
        "claim_boundary": (
            "This validates the stopped-design estimator under a synthetic fixed potential-"
            "outcome schedule. It does not validate H81 transport, outcomes, or market welfare."
        ),
    }


def plot_validation(bias: pd.DataFrame, size: pd.DataFrame, out_dir: Path) -> None:
    import matplotlib.pyplot as plt

    names = list(CONTRASTS)
    corrected = [float(bias[f"corrected_error_{name}"].mean()) for name in names]
    naive = [float(bias[f"terminal_inclusive_error_{name}"].mean()) for name in names]
    corrected_se = [
        float(bias[f"corrected_error_{name}"].std(ddof=1) / np.sqrt(len(bias)))
        for name in names
    ]
    naive_se = [
        float(bias[f"terminal_inclusive_error_{name}"].std(ddof=1) / np.sqrt(len(bias)))
        for name in names
    ]
    x = np.arange(len(names))
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.8))
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
    axes[1].set_title("B. Sharp-null size audit")
    axes[1].legend(frameon=False, fontsize=8)
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
    summary = summarize(bias, size)
    save(bias, out_dir, "h81_theorem_validation_draws")
    save(size, out_dir, "h81_theorem_randomization_size")
    save_json(summary, out_dir, "h81_theorem_validation_summary")
    plot_validation(bias, size, out_dir)
    return summary
