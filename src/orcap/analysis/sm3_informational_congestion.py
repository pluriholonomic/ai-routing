"""SM3 — fixed-market information congestion and minority scaling.

The module deliberately separates two objects.

1. ``scaling_panel`` evaluates the conditional objective used by the theorem,

       V_n(k) = a k/n - c (k/n)^2 (k/r_n)^alpha,

   where the effective rank of the provider signal system is ``r_n=n^beta``.
   This is a structural numerical check, not an empirical estimate.
2. ``bandit_panel`` holds the total provider menu fixed and perturbs only the
   number of adaptive providers and the cross-provider signal covariance in the
   existing multi-agent routing environment.  It is a falsification/stress
   test for the channel, not evidence that live providers use the simulated
   learners.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from ..market_env.market_share_hmp import MarketShareHMPConfig, paired_intervention
from .common import DEFAULT_OUT, save, save_json


def effective_rank_equicorrelation(size: int, correlation: float) -> float:
    """Effective rank of a unit-variance equicorrelation matrix."""
    if size < 1:
        raise ValueError("size must be positive")
    rho = float(correlation)
    if not 0 <= rho <= 1:
        raise ValueError("correlation must lie in [0, 1]")
    return float(size / (1.0 + (size - 1) * rho**2))


def correlation_for_effective_rank(size: int, rank: float) -> float:
    """Return the nonnegative equicorrelation attaining ``rank``."""
    if size < 1:
        raise ValueError("size must be positive")
    target = float(rank)
    if not 1 <= target <= size:
        raise ValueError("rank must lie between one and size")
    if size == 1:
        return 0.0
    squared = (size / target - 1.0) / (size - 1.0)
    return float(np.sqrt(max(squared, 0.0)))


def congestion_value(
    active: np.ndarray | float,
    *,
    providers: int,
    signal_rank: float,
    benefit: float = 1.0,
    congestion_cost: float = 1.0,
    alpha: float = 1.0,
) -> np.ndarray:
    """Evaluate the theorem's finite-market objective."""
    if providers < 2 or not 1 <= signal_rank <= providers:
        raise ValueError("invalid market size or signal rank")
    if benefit <= 0 or congestion_cost <= 0 or alpha <= 0:
        raise ValueError("objective parameters must be positive")
    values = np.asarray(active, dtype=float)
    if np.any(values < 0) or np.any(values > providers):
        raise ValueError("active count must lie in [0, providers]")
    benefit_term = benefit * values / providers
    loss = congestion_cost * np.square(values / providers) * np.power(values / signal_rank, alpha)
    return benefit_term - loss


def continuous_optimum(
    *,
    providers: int,
    signal_rank: float,
    benefit: float = 1.0,
    congestion_cost: float = 1.0,
    alpha: float = 1.0,
) -> float:
    """Interior first-order solution, clipped to the feasible interval."""
    raw = (benefit * providers * signal_rank**alpha / (congestion_cost * (2.0 + alpha))) ** (
        1.0 / (1.0 + alpha)
    )
    return float(np.clip(raw, 0.0, providers))


def scaling_panel(
    *,
    provider_counts: tuple[int, ...] = (32, 64, 128, 256, 512, 1024),
    rank_exponents: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0),
    alpha: float = 1.0,
    benefit: float = 1.0,
    congestion_cost: float = 1.0,
) -> pd.DataFrame:
    """Find the exact integer optimum on the frozen fixed-n grid."""
    rows: list[dict[str, Any]] = []
    for beta in rank_exponents:
        if not 0 <= beta <= 1:
            raise ValueError("rank exponents must lie in [0, 1]")
        for providers in provider_counts:
            rank = float(providers**beta)
            active = np.arange(0, providers + 1, dtype=float)
            values = congestion_value(
                active,
                providers=providers,
                signal_rank=rank,
                benefit=benefit,
                congestion_cost=congestion_cost,
                alpha=alpha,
            )
            integer_optimum = int(np.argmax(values))
            continuous = continuous_optimum(
                providers=providers,
                signal_rank=rank,
                benefit=benefit,
                congestion_cost=congestion_cost,
                alpha=alpha,
            )
            rows.append(
                {
                    "providers": providers,
                    "rank_exponent_beta": beta,
                    "signal_effective_rank": rank,
                    "integer_optimal_active": integer_optimum,
                    "continuous_optimal_active": continuous,
                    "optimal_active_density": integer_optimum / providers,
                    "optimal_value": float(values[integer_optimum]),
                    "predicted_kstar_exponent": (1.0 + alpha * beta) / (1.0 + alpha),
                    "alpha": alpha,
                }
            )
    panel = pd.DataFrame(rows)
    estimated = []
    for beta, group in panel.groupby("rank_exponent_beta"):
        slope, intercept = np.polyfit(
            np.log(group["providers"]),
            np.log(group["integer_optimal_active"]),
            1,
        )
        estimated.append(
            {
                "rank_exponent_beta": float(beta),
                "estimated_kstar_exponent": float(slope),
                "estimated_log_intercept": float(intercept),
            }
        )
    return panel.merge(pd.DataFrame(estimated), on="rank_exponent_beta", how="left")


def _active_grid(providers: int) -> tuple[int, ...]:
    values = {1, 2, max(2, providers // 8), providers // 4, providers // 2, providers - 1}
    return tuple(sorted(value for value in values if 1 <= value < providers))


def bandit_panel(
    *,
    provider_counts: tuple[int, ...] = (8, 16),
    rank_exponents: tuple[float, ...] = (0.0, 0.5, 1.0),
    memories: tuple[float, ...] = (0.0, 0.8, 0.99),
    algorithms: tuple[str, ...] = ("ucb", "q_learning"),
    seeds: int = 8,
    horizon: int = 1_000,
) -> pd.DataFrame:
    """Run a fixed-total-provider signal-order intervention.

    The full-menu equicorrelation is chosen to have effective rank ``n^beta``.
    Nested active subsets inherit the corresponding principal submatrix.
    """
    rows: list[dict[str, Any]] = []
    for providers in provider_counts:
        for beta in rank_exponents:
            full_rank = float(providers**beta)
            rho = correlation_for_effective_rank(providers, full_rank)
            for active in _active_grid(providers):
                subset_rank = effective_rank_equicorrelation(active, rho)
                for memory in memories:
                    for algorithm in algorithms:
                        for seed in range(seeds):
                            config = MarketShareHMPConfig(
                                horizon=horizon,
                                burn_in=horizon // 2,
                                demand_per_period=120,
                                n_active=active,
                                n_anchors=providers - active,
                                low_price=0.72,
                                high_price=1.0,
                                anchor_price=1.0,
                                marginal_cost=0.25,
                                router_eta=1.6482780609377246,
                                signal_to_noise=2.0,
                                common_correlation=rho,
                                reward_memory=memory,
                                algorithm=algorithm,  # type: ignore[arg-type]
                                learning_relative_error=0.10,
                                seed=seed,
                            )
                            coupled, shuffled = paired_intervention(config)
                            record: dict[str, Any] = {
                                "providers": providers,
                                "active": active,
                                "active_density": active / providers,
                                "rank_exponent_beta": beta,
                                "full_signal_effective_rank": full_rank,
                                "active_subset_effective_rank": subset_rank,
                                "equicorrelation": rho,
                                "reward_memory": memory,
                                "algorithm": algorithm,
                                "seed": seed,
                            }
                            for name in (
                                "mean_action_correlation",
                                "mean_active_group_share",
                                "mean_anchor_group_share",
                                "mean_buyer_price",
                                "elasticity_learning_time",
                                "elasticity_learned",
                            ):
                                left = coupled[name]
                                right = shuffled[name]
                                record[f"{name}_coupled"] = left
                                record[f"{name}_shuffled"] = right
                                if isinstance(left, (int, float, np.number)) and isinstance(
                                    right, (int, float, np.number)
                                ):
                                    record[f"{name}_difference"] = float(left) - float(right)
                            rows.append(record)
    return pd.DataFrame(rows)


def summarize(scaling: pd.DataFrame, bandit: pd.DataFrame) -> dict[str, Any]:
    exponents = (
        scaling.groupby("rank_exponent_beta", as_index=False)
        .first()[
            [
                "rank_exponent_beta",
                "predicted_kstar_exponent",
                "estimated_kstar_exponent",
            ]
        ]
        .to_dict("records")
    )
    max_error = float(
        (scaling["predicted_kstar_exponent"] - scaling["estimated_kstar_exponent"]).abs().max()
    )

    def seed_interval(rows: pd.DataFrame, column: str) -> dict[str, Any]:
        values = rows.groupby("seed")[column].mean().to_numpy(dtype=float)
        estimate = float(np.mean(values)) if len(values) else None
        if len(values) < 2:
            return {
                "estimate": estimate,
                "ci95": None,
                "seed_clusters": int(len(values)),
            }
        standard_error = float(stats.sem(values))
        radius = float(stats.t.ppf(0.975, len(values) - 1) * standard_error)
        return {
            "estimate": estimate,
            "ci95": [estimate - radius, estimate + radius],
            "seed_clusters": int(len(values)),
        }

    if bandit.empty:
        bandit_summary: list[dict[str, Any]] = []
        rank_summary: list[dict[str, Any]] = []
    else:
        bandit_summary = (
            bandit.groupby(["rank_exponent_beta", "active_density"], as_index=False)
            .agg(
                action_correlation_difference=("mean_action_correlation_difference", "mean"),
                active_share_difference=("mean_active_group_share_difference", "mean"),
                seeds=("seed", "nunique"),
            )
            .to_dict("records")
        )
        rank_summary = []
        for beta, rows in bandit.groupby("rank_exponent_beta"):
            rank_summary.append(
                {
                    "rank_exponent_beta": float(beta),
                    "action_correlation_difference": seed_interval(
                        rows, "mean_action_correlation_difference"
                    ),
                    "active_share_difference": seed_interval(
                        rows, "mean_active_group_share_difference"
                    ),
                    "buyer_price_difference": seed_interval(rows, "mean_buyer_price_difference"),
                }
            )
    return {
        "experiment_id": "sm3-fixed-n-informational-congestion-v1",
        "evidence_status": "conditional_theorem_numeric_check_plus_synthetic_falsification",
        "scaling_cells": int(len(scaling)),
        "bandit_cells": int(len(bandit)),
        "kstar_scaling": exponents,
        "maximum_predicted_vs_estimated_exponent_error": max_error,
        "bandit_signal_order_screen": bandit_summary,
        "bandit_rank_seed_clustered_intervals": rank_summary,
        "theorem_result": (
            "For r_n proportional to n^beta, the structural objective has "
            "k-star proportional to n^((1+alpha beta)/(1+alpha)); it is a "
            "vanishing fraction when beta<1 and a constant fraction when beta=1."
        ),
        "mechanism_implication": (
            "A router that exposes more flow to correlated adaptive providers can "
            "cross the minority optimum even while each provider's displayed-price "
            "elasticity remains locally attractive. Covariance-aware exposure caps "
            "target that externality; they are not justified when signal rank is linear."
        ),
        "bandit_result": (
            "The declared bandit stress test can move action correlation, but in "
            "this frozen design its active-share effects are close to zero. The "
            "synthetic learner therefore does not validate an allocation-level "
            "congestion effect; it is a useful negative control on the theorem."
        ),
        "claim_boundary": (
            "The scaling panel numerically evaluates an assumed congestion objective. "
            "The bandit panel uses declared synthetic learners and a marginal-preserving "
            "signal-order intervention. Neither estimates live provider algorithms, "
            "signal rank asymptotics, collusion, costs, realized welfare, or k-star."
        ),
    }


def _render(scaling: pd.DataFrame, bandit: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 8.0), constrained_layout=True)
    for beta, rows in scaling.groupby("rank_exponent_beta"):
        rows = rows.sort_values("providers")
        axes[0, 0].plot(
            rows["providers"], rows["integer_optimal_active"], marker="o", label=f"beta={beta:g}"
        )
        axes[0, 1].plot(
            rows["providers"], rows["optimal_active_density"], marker="o", label=f"beta={beta:g}"
        )
    axes[0, 0].set(
        xscale="log",
        yscale="log",
        xlabel="providers n",
        ylabel="optimal active k",
        title="A. Critical active count",
    )
    axes[0, 1].set(
        xscale="log",
        xlabel="providers n",
        ylabel="k-star / n",
        title="B. Minority versus linear regimes",
    )
    axes[0, 0].legend(frameon=False, fontsize=8, ncol=2)

    if not bandit.empty:
        view = bandit.groupby(["rank_exponent_beta", "active_density"], as_index=False).agg(
            action=("mean_action_correlation_difference", "mean"),
            share=("mean_active_group_share_difference", "mean"),
        )
        for beta, rows in view.groupby("rank_exponent_beta"):
            rows = rows.sort_values("active_density")
            axes[1, 0].plot(
                rows["active_density"],
                rows["action"],
                marker="o",
                label=f"beta={beta:g}",
            )
            axes[1, 1].plot(
                rows["active_density"],
                rows["share"],
                marker="o",
                label=f"beta={beta:g}",
            )
    for axis in axes[1]:
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_xlabel("adaptive-provider fraction k/n")
    axes[1, 0].set_ylabel("coupled - shuffled action correlation")
    axes[1, 0].set_title("C. Synthetic coordination channel")
    axes[1, 1].set_ylabel("coupled - shuffled active share")
    axes[1, 1].set_title("D. Synthetic allocation effect")
    fig.suptitle("Fixed-n informational congestion: theorem check and bandit falsification")
    fig.savefig(out_dir / "sm3_informational_congestion.png", dpi=190)
    fig.savefig(out_dir / "sm3_informational_congestion.pdf")
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    scaling = scaling_panel()
    bandit = bandit_panel()
    result = summarize(scaling, bandit)
    save(scaling, out_dir, "sm3_informational_congestion_scaling")
    save(bandit, out_dir, "sm3_informational_congestion_bandit")
    save_json(result, out_dir, "sm3_informational_congestion_summary")
    _render(scaling, bandit, out_dir)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
