"""SM1b — elastic-demand welfare under inverse-power provider routing."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from ..market_env.theory import (
    isoelastic_quantity,
    isoelastic_welfare,
    symmetric_elastic_price,
    unilateral_elastic_profit,
)
from .common import DEFAULT_OUT, save, save_json


def numerical_elastic_best_response(
    *,
    rival_price: float,
    rivals: int,
    exponent: float,
    demand_elasticity: float,
    marginal_cost: float,
    price_cap: float,
) -> float:
    """Global grid search followed by local refinement.

    Elastic-demand profit can be non-quasiconcave, so a single bounded scalar
    optimization is not a valid global best-response audit.
    """

    def profit(price: float) -> float:
        return unilateral_elastic_profit(
            own_price=float(price),
            rival_prices=(rival_price,) * rivals,
            exponent=exponent,
            marginal_cost=marginal_cost,
            demand_elasticity=demand_elasticity,
        )

    grid = np.geomspace(marginal_cost, price_cap, 2_049)
    values = np.array([profit(float(price)) for price in grid])
    candidate_indices = np.argpartition(values, -min(12, len(values)))[-12:]
    candidates = [
        (float(values[0]), float(grid[0])),
        (float(values[-1]), float(grid[-1])),
    ]
    for index in candidate_indices:
        low = float(grid[max(0, index - 1)])
        high = float(grid[min(len(grid) - 1, index + 1)])
        result = minimize_scalar(
            lambda price: -profit(float(price)),
            bounds=(low, high),
            method="bounded",
            options={"xatol": 1e-12},
        )
        if result.success:
            candidates.append((-float(result.fun), float(result.x)))
    _, best_price = max(candidates, key=lambda item: (item[0], -item[1]))
    return best_price


def elastic_panel(
    *,
    provider_counts: tuple[int, ...] = tuple(range(2, 21)),
    exponents: tuple[float, ...] = (1.5, 2.0, 3.0, 4.0),
    demand_elasticities: tuple[float, ...] = (1.25, 2.0, 4.0, 8.0),
    marginal_cost: float = 1.0,
    demand_scale: float = 1.0,
    price_cap: float = 100.0,
) -> pd.DataFrame:
    competitive_welfare = {
        epsilon: isoelastic_welfare(
            marginal_cost,
            marginal_cost=marginal_cost,
            demand_elasticity=epsilon,
            demand_scale=demand_scale,
        )
        for epsilon in demand_elasticities
    }
    rows: list[dict] = []
    for exponent in exponents:
        for epsilon in demand_elasticities:
            for providers in provider_counts:
                equilibrium = symmetric_elastic_price(
                    providers=providers,
                    exponent=exponent,
                    demand_elasticity=epsilon,
                    marginal_cost=marginal_cost,
                    price_cap=price_cap,
                )
                assert equilibrium is not None
                best_response = numerical_elastic_best_response(
                    rival_price=equilibrium,
                    rivals=providers - 1,
                    exponent=exponent,
                    demand_elasticity=epsilon,
                    marginal_cost=marginal_cost,
                    price_cap=price_cap,
                )
                quantity = isoelastic_quantity(
                    equilibrium,
                    demand_elasticity=epsilon,
                    demand_scale=demand_scale,
                )
                welfare = isoelastic_welfare(
                    equilibrium,
                    marginal_cost=marginal_cost,
                    demand_elasticity=epsilon,
                    demand_scale=demand_scale,
                )
                effective_elasticity = exponent * (providers - 1) + epsilon
                unconstrained = effective_elasticity > providers
                candidate_profit = unilateral_elastic_profit(
                    own_price=equilibrium,
                    rival_prices=(equilibrium,) * (providers - 1),
                    exponent=exponent,
                    marginal_cost=marginal_cost,
                    demand_elasticity=epsilon,
                    demand_scale=demand_scale,
                )
                best_response_profit = unilateral_elastic_profit(
                    own_price=best_response,
                    rival_prices=(equilibrium,) * (providers - 1),
                    exponent=exponent,
                    marginal_cost=marginal_cost,
                    demand_elasticity=epsilon,
                    demand_scale=demand_scale,
                )
                deviation_gain = best_response_profit - candidate_profit
                rows.append(
                    {
                        "providers": providers,
                        "exponent": exponent,
                        "demand_elasticity": epsilon,
                        "marginal_cost": marginal_cost,
                        "price_cap": price_cap,
                        "effective_provider_elasticity": effective_elasticity / providers,
                        "unconstrained_interior_exists": unconstrained,
                        "cap_binds": bool(
                            not unconstrained or np.isclose(equilibrium, price_cap)
                        ),
                        "equilibrium_price": equilibrium,
                        "markup_ratio": equilibrium / marginal_cost,
                        "quantity": quantity,
                        "welfare": welfare,
                        "competitive_welfare": competitive_welfare[epsilon],
                        "welfare_ratio": welfare / competitive_welfare[epsilon],
                        "deadweight_loss_share": 1 - welfare / competitive_welfare[epsilon],
                        "numerical_best_response": best_response,
                        "best_response_absolute_error": abs(best_response - equilibrium),
                        "candidate_provider_profit": candidate_profit,
                        "best_response_profit": best_response_profit,
                        "deviation_gain": deviation_gain,
                        "normalized_deviation_gain": deviation_gain
                        / max(abs(candidate_profit), 1e-12),
                        "global_best_response_pass": bool(
                            abs(best_response - equilibrium) < 1e-4
                            and deviation_gain < 1e-8
                        ),
                    }
                )
    return pd.DataFrame(rows)


def summary(panel: pd.DataFrame) -> dict:
    inverse_square = panel[np.isclose(panel["exponent"], 2.0)]
    exact_case = inverse_square[np.isclose(inverse_square["demand_elasticity"], 2.0)]
    selected = inverse_square[
        (inverse_square["providers"] == 20)
        & np.isclose(inverse_square["demand_elasticity"], 2.0)
    ].iloc[0]
    failures = panel[~panel["global_best_response_pass"]]
    return {
        "experiment_id": "sm1b-elastic-power-router-v1",
        "evidence_status": "proved_eta2_epsilon2_equilibrium_plus_numerical_general_audit",
        "rows": int(len(panel)),
        "global_best_response_passes": int(panel["global_best_response_pass"].sum()),
        "global_best_response_failures": int(len(failures)),
        "failure_cells": failures[
            [
                "providers",
                "exponent",
                "demand_elasticity",
                "equilibrium_price",
                "numerical_best_response",
                "normalized_deviation_gain",
            ]
        ].to_dict("records"),
        "max_best_response_absolute_error": float(
            panel["best_response_absolute_error"].max()
        ),
        "inverse_square_n20_epsilon2_markup": float(selected["markup_ratio"]),
        "inverse_square_n20_epsilon2_welfare_ratio": float(selected["welfare_ratio"]),
        "inverse_square_asymptotic_markup": 2.0,
        "inverse_square_epsilon2_asymptotic_welfare_ratio": 0.75,
        "inverse_square_epsilon2_all_n_markup_exact": bool(
            np.allclose(exact_case["markup_ratio"], 2.0)
        ),
        "inverse_square_epsilon2_all_n_welfare_ratio_exact": bool(
            np.allclose(exact_case["welfare_ratio"], 0.75)
        ),
        "entry_comparative_static": {
            "epsilon_below_eta": "entry lowers stationary markup and deadweight loss",
            "epsilon_equal_eta": "entry leaves stationary markup and welfare unchanged",
            "epsilon_above_eta": "entry raises stationary markup and deadweight loss",
        },
        "primary_result": (
            "When both the router exponent and aggregate-demand elasticity equal "
            "two, p=2c is a global symmetric equilibrium for every n>=2. Entry "
            "does not change price and welfare is exactly 75% of the competitive "
            "benchmark. The remaining frozen grid passes a numerical global audit."
        ),
        "mechanism_implication": (
            "Provider entry is not unambiguously pro-competitive. Its stationary "
            "price effect has the sign of aggregate-demand elasticity minus the "
            "router exponent. Capacity, reliability, and latency are required to "
            "design a finite welfare-optimal exponent."
        ),
        "claim_boundary": (
            "The eta=epsilon=2 special case has a global best-response proof. "
            "Other parameter cells have a local formula plus dense numerical audit. "
            "Neither is a calibrated effect or established novelty claim relative "
            "to differentiated-products and contest models."
        ),
    }


def plot_panel(panel: pd.DataFrame, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    view = panel[np.isclose(panel["exponent"], 2.0)].copy()
    elasticities = [1.25, 2.0, 4.0, 8.0]
    colors = plt.cm.cividis(np.linspace(0.1, 0.9, len(elasticities)))
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2), constrained_layout=True)

    for epsilon, color in zip(elasticities, colors, strict=True):
        rows = view[np.isclose(view["demand_elasticity"], epsilon)].sort_values(
            "providers"
        )
        label = rf"$\epsilon={epsilon:g}$"
        axes[0].plot(
            rows["providers"],
            rows["markup_ratio"],
            color=color,
            linewidth=2,
            marker="o",
            markersize=3.5,
            label=label,
        )
        valid = rows[rows["global_best_response_pass"]]
        axes[1].plot(
            valid["providers"],
            100 * valid["deadweight_loss_share"],
            color=color,
            linewidth=2,
            marker="o",
            markersize=3.5,
            label=label,
        )

    axes[0].axhline(2, color="#777777", linestyle=":", linewidth=1.2)
    axes[0].text(20, 2.05, r"entry-neutral at $\epsilon=\eta$", ha="right", va="bottom", fontsize=8)
    axes[0].set_ylabel("Symmetric stationary price / marginal cost")
    axes[0].set_title(r"Entry effect reverses at $\epsilon=\eta$")
    axes[1].set_ylabel("Deadweight loss (% of competitive welfare)")
    axes[1].set_title("Entry can increase deadweight loss")
    axes[1].legend(frameon=False, title="Demand elasticity")
    for axis in axes:
        axis.set_xlabel("Number of eligible providers")
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#dddddd", linewidth=0.7)
        axis.set_xticks([2, 5, 10, 15, 20])
    failures = view[~view["global_best_response_pass"]]
    if len(failures):
        axes[0].scatter(
            failures["providers"],
            failures["markup_ratio"],
            marker="x",
            s=65,
            linewidth=2,
            color="#B22222",
            zorder=5,
            label="profitable global deviation",
        )
        axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Inverse-square routing with isoelastic aggregate demand", fontsize=12)
    png = out_dir / "sm1b_elastic_power_router.png"
    pdf = out_dir / "sm1b_elastic_power_router.pdf"
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = elastic_panel()
    save(panel, out_dir, "sm1b_elastic_power_router")
    result = summary(panel)
    save_json(result, out_dir, "sm1b_elastic_power_router_summary")
    plot_panel(panel, out_dir)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
