"""SM1 — equilibrium benchmark for inverse-power provider routing."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from ..market_env.theory import symmetric_interior_price, unilateral_profit
from .common import DEFAULT_OUT, save, save_json


def equilibrium_price_with_cap(
    *,
    providers: int,
    exponent: float,
    marginal_cost: float,
    price_cap: float,
) -> tuple[float, bool]:
    """Return the theorem-implied symmetric equilibrium and cap status."""
    if price_cap < marginal_cost:
        raise ValueError("price_cap must be at least marginal_cost")
    interior = symmetric_interior_price(
        providers=providers,
        exponent=exponent,
        marginal_cost=marginal_cost,
    )
    if interior is None or interior >= price_cap:
        return float(price_cap), True
    return float(interior), False


def numerical_best_response(
    *,
    rival_price: float,
    rivals: int,
    exponent: float,
    marginal_cost: float,
    price_cap: float,
) -> float:
    """Compute a bounded best response for theorem validation."""
    result = minimize_scalar(
        lambda price: -unilateral_profit(
            own_price=float(price),
            rival_prices=(rival_price,) * rivals,
            exponent=exponent,
            marginal_cost=marginal_cost,
        ),
        bounds=(marginal_cost, price_cap),
        method="bounded",
        options={"xatol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"best-response optimization failed: {result.message}")
    return float(result.x)


def equilibrium_panel(
    *,
    provider_counts: tuple[int, ...] = tuple(range(2, 11)),
    exponents: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 8.0),
    price_caps: tuple[float, ...] = (2.0, 4.0, 10.0, 100.0),
    marginal_cost: float = 1.0,
) -> pd.DataFrame:
    """Evaluate the frozen entry, exponent, and cap grid."""
    rows: list[dict] = []
    for price_cap in price_caps:
        for exponent in exponents:
            for providers in provider_counts:
                interior = symmetric_interior_price(
                    providers=providers,
                    exponent=exponent,
                    marginal_cost=marginal_cost,
                )
                equilibrium, cap_binds = equilibrium_price_with_cap(
                    providers=providers,
                    exponent=exponent,
                    marginal_cost=marginal_cost,
                    price_cap=price_cap,
                )
                best_response = numerical_best_response(
                    rival_price=equilibrium,
                    rivals=providers - 1,
                    exponent=exponent,
                    marginal_cost=marginal_cost,
                    price_cap=price_cap,
                )
                markup = equilibrium / marginal_cost
                lerner = (equilibrium - marginal_cost) / equilibrium
                rows.append(
                    {
                        "providers": providers,
                        "exponent": exponent,
                        "marginal_cost": marginal_cost,
                        "price_cap": price_cap,
                        "existence_threshold": providers / (providers - 1),
                        "unconstrained_interior_price": interior,
                        "equilibrium_price": equilibrium,
                        "markup_ratio": markup,
                        "lerner_index": lerner,
                        "cap_binds": cap_binds,
                        "provider_share": 1.0 / providers,
                        "provider_profit": (equilibrium - marginal_cost) / providers,
                        "aggregate_provider_profit": equilibrium - marginal_cost,
                        "consumer_payment": equilibrium,
                        "numerical_best_response": best_response,
                        "best_response_absolute_error": abs(best_response - equilibrium),
                    }
                )
    return pd.DataFrame(rows)


def summary(panel: pd.DataFrame) -> dict:
    """Write theorem-validation and claim-boundary facts."""
    inverse_square = panel[np.isclose(panel["exponent"], 2.0)]
    high_cap = inverse_square[np.isclose(inverse_square["price_cap"], 100.0)]
    n2 = high_cap[high_cap["providers"] == 2].iloc[0]
    n3 = high_cap[high_cap["providers"] == 3].iloc[0]
    return {
        "experiment_id": "sm1-power-router-equilibrium-v1",
        "evidence_status": "analytical_theorem_numerically_validated",
        "rows": int(len(panel)),
        "max_best_response_absolute_error": float(
            panel["best_response_absolute_error"].max()
        ),
        "inverse_square_duopoly_price_at_high_cap": float(n2["equilibrium_price"]),
        "inverse_square_duopoly_cap_binds": bool(n2["cap_binds"]),
        "inverse_square_triopoly_price_at_high_cap": float(n3["equilibrium_price"]),
        "inverse_square_triopoly_cap_binds": bool(n3["cap_binds"]),
        "inverse_square_free_entry_markup_limit": 2.0,
        "primary_result": (
            "Under inverse-square routing, the symmetric duopoly equilibrium is "
            "price-cap binding, while n >= 3 has the finite unconstrained price "
            "2(n-1)c/(n-2) when the cap is high enough. The markup converges to "
            "two, not one, under free entry."
        ),
        "welfare_boundary": (
            "With identical cost, quality, and inelastic demand, price is an "
            "internal transfer and allocation has no welfare content. Welfare "
            "comparisons require elasticity, heterogeneous technology, capacity, "
            "latency, or failure."
        ),
        "conduct_boundary": (
            "Cap-binding or elevated prices arise from unilateral incentives in "
            "the stated game and are not evidence of collusion."
        ),
    }


def plot_panel(panel: pd.DataFrame, out_dir: Path) -> tuple[Path, Path]:
    """Render a compact theorem figure for the high-cap treatment."""
    out_dir.mkdir(parents=True, exist_ok=True)
    view = panel[np.isclose(panel["price_cap"], 100.0)].copy()
    exponents = [1.5, 2.0, 3.0, 4.0, 8.0]
    colors = plt.cm.viridis(np.linspace(0.08, 0.9, len(exponents)))
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.1), constrained_layout=True)

    for exponent, color in zip(exponents, colors, strict=True):
        rows = view[np.isclose(view["exponent"], exponent)].sort_values("providers")
        axes[0].plot(
            rows["providers"],
            rows["markup_ratio"],
            marker="o",
            linewidth=1.8,
            markersize=4,
            color=color,
            label=rf"$\eta={exponent:g}$",
        )
        axes[1].plot(
            rows["providers"],
            rows["lerner_index"],
            marker="o",
            linewidth=1.8,
            markersize=4,
            color=color,
        )

    axes[0].set_yscale("log")
    axes[0].set_ylabel("Equilibrium price / marginal cost")
    axes[0].set_xlabel("Number of eligible providers")
    axes[0].set_title("Smooth routing leaves residual market power")
    axes[0].axhline(100, color="#777777", linestyle=":", linewidth=1, label="price cap")
    axes[0].legend(frameon=False, fontsize=8, ncol=2)

    axes[1].set_ylabel("Lerner index")
    axes[1].set_xlabel("Number of eligible providers")
    axes[1].set_title("Entry does not drive markup to zero")
    axes[1].set_ylim(-0.02, 1.02)

    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#dddddd", linewidth=0.7)
        axis.set_xticks(range(2, 11))

    fig.suptitle(
        r"Symmetric equilibrium under route share proportional to price$^{-\eta}$",
        fontsize=12,
    )
    png = out_dir / "sm1_power_router_equilibrium.png"
    pdf = out_dir / "sm1_power_router_equilibrium.pdf"
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = equilibrium_panel()
    save(panel, out_dir, "sm1_power_router_equilibrium")
    result = summary(panel)
    save_json(result, out_dir, "sm1_power_router_equilibrium_summary")
    plot_panel(panel, out_dir)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
