"""Numerical and constructive validation for the paper's companion theorems."""

from __future__ import annotations

from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .common import DEFAULT_OUT, save, save_json


def validate_detection_threshold(
    *,
    events_per_cell: int = 200_000,
    seed: int = 20260719,
) -> pd.DataFrame:
    """Check E[Y-q] = p-q+rho(1-p) around the analytic threshold."""
    rng = np.random.default_rng(seed)
    rows = []
    for p, q in ((0.10, 0.25), (0.25, 0.50), (0.55, 0.70), (0.70, 0.90)):
        threshold = (q - p) / (1.0 - p)
        levels = sorted(
            {
                0.0,
                max(0.0, threshold - 0.08),
                threshold,
                min(1.0, threshold + 0.08),
                1.0,
            }
        )
        for rho in levels:
            reactive = rng.random(events_per_cell) < rho
            outcome = reactive | (rng.random(events_per_cell) < p)
            simulated = float(outcome.mean() - q)
            analytic = float(p - q + rho * (1.0 - p))
            standard_error = float(
                np.sqrt(outcome.mean() * (1.0 - outcome.mean()) / events_per_cell)
            )
            rows.append(
                {
                    "p_nonreactive": p,
                    "q_benchmark": q,
                    "rho": rho,
                    "rho_threshold": threshold,
                    "analytic_residual": analytic,
                    "simulated_residual": simulated,
                    "monte_carlo_se": standard_error,
                    "absolute_z_error": (
                        abs(simulated - analytic) / standard_error if standard_error else 0.0
                    ),
                    "sign_matches_away_from_threshold": (
                        True
                        if abs(analytic) <= 4 * standard_error
                        else np.sign(simulated) == np.sign(analytic)
                    ),
                }
            )
    return pd.DataFrame(rows)


def validate_revenue_share_identity(
    *,
    markets: int = 80,
    providers_per_market: int = 5,
    seed: int = 20260720,
) -> dict[str, float]:
    """Verify coefficient, residual, and HC1-SE identities under arbitrary WLS."""
    rng = np.random.default_rng(seed)
    n = markets * providers_per_market
    market = np.repeat(np.arange(markets), providers_per_market)
    log_price = rng.normal(0.0, 0.7, n)
    control = rng.normal(size=n)
    log_quantity = 0.4 * control - 0.35 * log_price + rng.normal(0.0, 0.5, n)
    price = np.exp(log_price)
    quantity = np.exp(log_quantity)
    frame = pd.DataFrame(
        {
            "market": market,
            "log_price": log_price,
            "control": control,
            "price": price,
            "quantity": quantity,
            "weight": np.exp(rng.normal(0.0, 0.3, n)),
        }
    )
    frame["quantity_share"] = frame["quantity"] / frame.groupby("market")[
        "quantity"
    ].transform("sum")
    frame["revenue"] = frame["price"] * frame["quantity"]
    frame["revenue_share"] = frame["revenue"] / frame.groupby("market")["revenue"].transform("sum")
    dummies = pd.get_dummies(frame["market"], prefix="market", drop_first=True, dtype=float)
    design = pd.concat(
        [
            pd.Series(1.0, index=frame.index, name="constant"),
            frame[["log_price", "control"]],
            dummies,
        ],
        axis=1,
    )
    quantity_fit = sm.WLS(
        np.log(frame["quantity_share"]), design, weights=frame["weight"]
    ).fit(cov_type="HC1")
    revenue_fit = sm.WLS(
        np.log(frame["revenue_share"]), design, weights=frame["weight"]
    ).fit(cov_type="HC1")
    return {
        "quantity_share_price_coefficient": float(quantity_fit.params["log_price"]),
        "revenue_share_price_coefficient": float(revenue_fit.params["log_price"]),
        "coefficient_identity_error": float(
            quantity_fit.params["log_price"] - revenue_fit.params["log_price"] + 1.0
        ),
        "maximum_residual_difference": float(
            np.max(np.abs(quantity_fit.resid - revenue_fit.resid))
        ),
        "hc1_standard_error_difference": float(
            quantity_fit.bse["log_price"] - revenue_fit.bse["log_price"]
        ),
    }


def validate_entry_grid(max_n: int = 200) -> pd.DataFrame:
    """Exhaustively compare integer welfare and free-entry counts."""
    rows = []
    for demand, value, cost, setup, availability in product(
        (20.0, 100.0),
        (2.0, 5.0),
        (0.5, 1.0),
        (0.2, 1.0, 5.0),
        (0.1, 0.4, 0.8),
    ):
        if value <= cost:
            continue
        for price in (cost + 0.25 * (value - cost), value):
            ceiling = int(np.floor((price - cost) * demand / setup)) if price > cost else 0
            grid_max = max(max_n, ceiling + 5)
            n = np.arange(grid_max + 1)
            success = 1.0 - np.power(1.0 - availability, n)
            welfare = demand * (value - cost) * success - n * setup
            welfare_n = int(np.flatnonzero(welfare == welfare.max())[-1])
            candidates = np.arange(1, grid_max + 1)
            profit = (price - cost) * demand * success[1:] / candidates - setup
            profitable = candidates[profit >= -1e-12]
            entry_n = int(profitable.max()) if len(profitable) else 0
            rows.append(
                {
                    "demand": demand,
                    "value": value,
                    "price": price,
                    "cost": cost,
                    "setup": setup,
                    "availability": availability,
                    "welfare_entry": welfare_n,
                    "free_entry": entry_n,
                    "entry_ceiling": ceiling,
                    "ceiling_holds": entry_n <= ceiling,
                    "equal_margin_overentry_holds": (
                        entry_n >= welfare_n if abs(price - value) <= 1e-12 else True
                    ),
                    "grid_boundary_hit": welfare_n == grid_max or entry_n == grid_max,
                }
            )
    return pd.DataFrame(rows)


def validate_coarsening_construction(
    *,
    draws: int = 20_000,
    seed: int = 20260721,
) -> dict[str, Any]:
    """Construct every changed provider as latent leader with identical endpoints."""
    rng = np.random.default_rng(seed)
    attempts = 0
    failures = 0
    for _ in range(draws):
        providers = int(rng.integers(2, 7))
        before = rng.integers(0, 5, size=providers)
        after = before.copy()
        changed_count = int(rng.integers(2, providers + 1))
        changed = rng.choice(providers, size=changed_count, replace=False)
        after[changed] = (after[changed] + rng.integers(1, 5, size=changed_count)) % 5
        for leader in changed:
            attempts += 1
            others = [int(item) for item in changed if item != leader]
            latent_order = [int(leader), *others]
            state = before.copy()
            for provider in latent_order:
                state[provider] = after[provider]
            if not np.array_equal(state, after):
                failures += 1
    return {
        "sampled_transitions": draws,
        "leader_witnesses_attempted": attempts,
        "construction_failures": failures,
        "all_changed_providers_attainable": failures == 0,
        "claim_boundary": (
            "Endpoint reconstruction validates the constructive equivalence under unrestricted "
            "within-bin update order; it does not validate the model against market data."
        ),
    }


def summarize(
    threshold: pd.DataFrame,
    revenue: dict[str, float],
    entry: pd.DataFrame,
    coarsening: dict[str, Any],
) -> dict[str, Any]:
    return {
        "hypothesis": "companion theorem validation suite",
        "detection_threshold": {
            "cells": int(len(threshold)),
            "maximum_absolute_z_error": float(threshold["absolute_z_error"].max()),
            "all_signs_match_away_from_threshold": bool(
                threshold["sign_matches_away_from_threshold"].all()
            ),
        },
        "revenue_share_identity": revenue,
        "entry_grid": {
            "cells": int(len(entry)),
            "all_ceilings_hold": bool(entry["ceiling_holds"].all()),
            "all_equal_margin_overentry_checks_hold": bool(
                entry["equal_margin_overentry_holds"].all()
            ),
            "any_grid_boundary_hit": bool(entry["grid_boundary_hit"].any()),
        },
        "coarsening_construction": coarsening,
        "evidence_status": "logical_and_numerical_validation_only",
    }


def plot_validation(threshold: pd.DataFrame, entry: pd.DataFrame, out_dir: Path) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.8))
    axes[0].scatter(
        threshold["analytic_residual"],
        threshold["simulated_residual"],
        color="#2369a1",
        s=24,
    )
    limits = [
        float(min(threshold["analytic_residual"].min(), threshold["simulated_residual"].min())),
        float(max(threshold["analytic_residual"].max(), threshold["simulated_residual"].max())),
    ]
    axes[0].plot(limits, limits, linestyle="--", color="black", linewidth=0.8)
    axes[0].set_xlabel("Analytic residual")
    axes[0].set_ylabel("Simulated residual")
    axes[0].set_title("A. Detection-threshold identity", fontsize=11)

    scatter = axes[1].scatter(
        entry["welfare_entry"],
        entry["free_entry"],
        c=entry["availability"],
        cmap="viridis",
        s=20,
        alpha=0.75,
    )
    maximum = int(max(entry["welfare_entry"].max(), entry["free_entry"].max()))
    axes[1].plot([0, maximum], [0, maximum], linestyle="--", color="black", linewidth=0.8)
    axes[1].set_xscale("symlog", linthresh=1)
    axes[1].set_yscale("symlog", linthresh=1)
    axes[1].set_xlabel("Welfare-maximizing provider count")
    axes[1].set_ylabel("Free-entry provider count")
    axes[1].set_title("B. Entry wedge across primitives", fontsize=11)
    colorbar = fig.colorbar(scatter, ax=axes[1], pad=0.02)
    colorbar.set_label("Availability $a$")
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "theory_validation_suite.png", dpi=200)
    fig.savefig(out_dir / "theory_validation_suite.pdf")
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    threshold = validate_detection_threshold()
    revenue = validate_revenue_share_identity()
    entry = validate_entry_grid()
    coarsening = validate_coarsening_construction()
    summary = summarize(threshold, revenue, entry, coarsening)
    save(threshold, out_dir, "theory_detection_threshold_validation")
    save(entry, out_dir, "theory_entry_grid_validation")
    save_json(summary, out_dir, "theory_validation_summary")
    plot_validation(threshold, entry, out_dir)
    return summary
