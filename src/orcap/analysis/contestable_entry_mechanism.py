"""Validated theory panels for costly entry and adaptive routing exposure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..market_env.contestable_entry import (
    adaptive_count_reduced_form,
    compare_entry_counts,
    free_entry_count,
    group_cut_gradients,
    pigouvian_entry_charge,
    required_learning_horizon,
    symmetric_public_operating_profit,
    welfare_entry_count,
)
from .common import DEFAULT_OUT, save, save_json


def entry_panel() -> pd.DataFrame:
    """Compare free entry with welfare entry as bilateral profit changes."""

    rows: list[dict[str, Any]] = []
    settings = {
        "max_providers": 40,
        "exponent": 2.0,
        "marginal_cost": 1.0,
        "public_demand": 20.0,
        "price_cap": 8.0,
        "fixed_entry_cost": 1.0,
        "availability": 0.55,
    }
    welfare = welfare_entry_count(
        max_providers=settings["max_providers"],
        demand=settings["public_demand"],
        delivered_value_minus_cost=3.0,
        availability=settings["availability"],
        fixed_entry_cost=settings["fixed_entry_cost"],
        failed_attempt_cost=0.08,
    )
    for bilateral in np.linspace(0.0, 1.25, 26):
        free = free_entry_count(
            **settings,
            bilateral_profit=float(bilateral),
        )
        comparison = compare_entry_counts(free, welfare)
        marginal_private = (
            symmetric_public_operating_profit(
                providers=max(free, 1),
                exponent=settings["exponent"],
                marginal_cost=settings["marginal_cost"],
                public_demand=settings["public_demand"],
                price_cap=settings["price_cap"],
                availability=settings["availability"],
            )
            + bilateral
        )
        charge = pigouvian_entry_charge(
            max(free - 1, 0),
            entrant_private_operating_profit=float(marginal_private),
            demand=settings["public_demand"],
            delivered_value_minus_cost=3.0,
            availability=settings["availability"],
            fixed_entry_cost=settings["fixed_entry_cost"],
            failed_attempt_cost=0.08,
        )
        rows.append(
            {
                "bilateral_profit": float(bilateral),
                "free_entry": free,
                "welfare_entry": welfare,
                "entry_wedge": comparison.wedge,
                "entry_direction": comparison.direction,
                "implementing_entry_charge": charge,
            }
        )
    return pd.DataFrame(rows)


def elasticity_panel() -> pd.DataFrame:
    rows = []
    for exponent in (1.45, 2.0, 3.0):
        for group_share in np.linspace(0.02, 0.90, 45):
            gradients = group_cut_gradients(
                float(group_share),
                exponent=exponent,
                price=1.0,
                marginal_cost=0.30,
                capacity_shadow_cost=0.05,
            )
            rows.append(
                {
                    "exponent": exponent,
                    "group_share": float(group_share),
                    **gradients,
                }
            )
    return pd.DataFrame(rows)


def _equicorrelation_conditional_variance(size: int, correlation: float) -> float:
    covariance = np.full((size, size), correlation, dtype=float)
    np.fill_diagonal(covariance, 1.0)
    rivals = covariance[1:, 1:]
    cross = covariance[0, 1:]
    explained = float(cross @ np.linalg.solve(rivals, cross))
    return max(1.0 - explained, 1e-12)


def learning_panel() -> pd.DataFrame:
    rows = []
    for providers in (2, 4, 8, 16):
        for correlation in np.linspace(0.0, 0.98, 50):
            conditional = _equicorrelation_conditional_variance(
                providers,
                float(correlation),
            )
            horizon = required_learning_horizon(
                reward_noise_variance=1.0,
                conditional_experiment_variance=conditional,
                target_error=0.15,
                actions=4,
                error_probability=0.05,
            )
            rows.append(
                {
                    "providers": providers,
                    "correlation": float(correlation),
                    "conditional_experiment_variance": conditional,
                    "required_horizon": horizon,
                }
            )
    return pd.DataFrame(rows)


def adaptive_panel() -> pd.DataFrame:
    rows = []
    providers = 100
    for rank_fraction in (0.05, 0.20, 1.0):
        rank = providers * rank_fraction
        for contestable in np.linspace(0.0, 1.0, 51):
            active = adaptive_count_reduced_form(
                providers=providers,
                signal_rank=rank,
                gross_benefit=1.0,
                contestable_share=float(contestable),
                fixed_adaptation_cost=0.10,
                congestion_cost=1.0,
                congestion_exponent=1.0,
            )
            rows.append(
                {
                    "providers": providers,
                    "rank_fraction": rank_fraction,
                    "contestable_share": float(contestable),
                    "adaptive_count": active,
                    "adaptive_density": active / providers,
                }
            )
    return pd.DataFrame(rows)


def summarize(
    entry: pd.DataFrame,
    elasticity: pd.DataFrame,
    learning: pd.DataFrame,
    adaptive: pd.DataFrame,
) -> dict[str, Any]:
    zero_contract = entry.iloc[0]
    high_contract = entry.iloc[-1]
    eta_two = elasticity[np.isclose(elasticity["exponent"], 2.0)]
    revenue_crossing = eta_two.loc[
        eta_two["log_revenue_cut_gradient"].abs().idxmin()
    ]
    return {
        "experiment_id": "contestable-entry-mechanism-v1",
        "evidence_status": "analytical_benchmarks_and_deterministic_sensitivity",
        "free_entry_at_zero_bilateral_profit": int(zero_contract["free_entry"]),
        "free_entry_at_high_bilateral_profit": int(high_contract["free_entry"]),
        "welfare_entry": int(zero_contract["welfare_entry"]),
        "inverse_square_revenue_threshold_group_share": float(
            revenue_crossing["group_share"]
        ),
        "maximum_learning_horizon": int(learning["required_horizon"].max()),
        "adaptive_zero_region_present": bool(adaptive["adaptive_count"].eq(0).any()),
        "claim_boundary": (
            "The panels evaluate declared analytical primitives. Bilateral profit, entry cost, "
            "availability, covariance, contestability, and signal rank are scenarios, not live "
            "provider estimates."
        ),
    }


def plot_panels(
    entry: pd.DataFrame,
    elasticity: pd.DataFrame,
    learning: pd.DataFrame,
    adaptive: pd.DataFrame,
    out_dir: Path,
) -> tuple[Path, Path]:
    colors = {1.45: "#4C78A8", 2.0: "#C51B1D", 3.0: "#2A9D8F"}
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7.8), constrained_layout=True)

    axes[0, 0].step(
        entry["bilateral_profit"],
        entry["free_entry"],
        where="post",
        color="#C51B1D",
        linewidth=2,
        label=r"free entry $n^{FE}$",
    )
    axes[0, 0].plot(
        entry["bilateral_profit"],
        entry["welfare_entry"],
        color="#303030",
        linestyle="--",
        linewidth=1.6,
        label=r"welfare entry $n^W$",
    )
    axes[0, 0].set_title("A. Bilateral profit can finance public listing")
    axes[0, 0].set_xlabel("Per-provider bilateral operating profit")
    axes[0, 0].set_ylabel("Provider count")
    axes[0, 0].legend(frameon=False)

    for exponent, rows in elasticity.groupby("exponent"):
        axes[0, 1].plot(
            rows["group_share"],
            rows["group_elasticity"],
            linewidth=2,
            color=colors[float(exponent)],
            label=rf"$\eta={exponent:g}$",
        )
    axes[0, 1].axhline(1.0, color="#303030", linestyle="--", linewidth=1)
    axes[0, 1].set_title("B. Co-movers attenuate the share return")
    axes[0, 1].set_xlabel(r"Co-moving group share $S_G$")
    axes[0, 1].set_ylabel(r"Path elasticity $z_G$")
    axes[0, 1].legend(frameon=False)

    for providers, rows in learning.groupby("providers"):
        axes[1, 0].plot(
            rows["correlation"],
            rows["required_horizon"],
            linewidth=1.8,
            label=rf"$k={providers}$",
        )
    axes[1, 0].set_yscale("log")
    axes[1, 0].set_title("C. Collinearity raises identification time")
    axes[1, 0].set_xlabel("Pairwise experiment correlation")
    axes[1, 0].set_ylabel("Required observations")
    axes[1, 0].legend(frameon=False, ncol=2)

    for rank_fraction, rows in adaptive.groupby("rank_fraction"):
        axes[1, 1].plot(
            rows["contestable_share"],
            rows["adaptive_density"],
            linewidth=2,
            label=rf"$r/n={rank_fraction:g}$",
        )
    axes[1, 1].set_title("D. Contestability and rank bound adaptation")
    axes[1, 1].set_xlabel(r"Contestable volume share $\lambda$")
    axes[1, 1].set_ylabel(r"Conditional adaptive density $k^{AE}/n$")
    axes[1, 1].legend(frameon=False)

    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#dddddd", linewidth=0.7)

    fig.suptitle("Costly entry, price-path elasticity, and adaptive participation", fontsize=13)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "contestable_entry_mechanism.png"
    pdf = out_dir / "contestable_entry_mechanism.pdf"
    fig.savefig(png, dpi=200)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    entry = entry_panel()
    elasticity = elasticity_panel()
    learning = learning_panel()
    adaptive = adaptive_panel()
    save(entry, out_dir, "contestable_entry_panel")
    save(elasticity, out_dir, "contestable_elasticity_panel")
    save(learning, out_dir, "contestable_learning_panel")
    save(adaptive, out_dir, "contestable_adaptive_panel")
    result = summarize(entry, elasticity, learning, adaptive)
    save_json(result, out_dir, "contestable_entry_summary")
    plot_panels(entry, elasticity, learning, adaptive, out_dir)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
