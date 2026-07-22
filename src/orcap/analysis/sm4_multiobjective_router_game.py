"""SM4 — heterogeneous-provider pricing game under alternative router objectives.

The exercise is a declared structural simulation.  Providers differ in cost,
capacity, reliability, quality, fixed investment, and whether they update a
posted price.  For each router rule, strategic providers play cyclic bounded
best responses.  The router-rule grid is then ranked separately by social
welfare, router fee revenue, delivered quality, and provider viability.

Payments are transfers in welfare.  Router revenue, provider profit, and user
utility remain separate private objectives.  Pairwise joint deviations are a
coalition-susceptibility diagnostic; they are not evidence of live collusion.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save, save_json


@dataclass(frozen=True)
class ProviderTechnology:
    provider: str
    provider_type: str
    marginal_cost: float
    quality: float
    reliability: float
    capacity: float
    latency_cost: float
    fixed_cost: float
    strategic: bool
    correlated_pricer: bool
    benchmark_price: float = 1.0


@dataclass(frozen=True)
class RouterRule:
    eta: float
    quality_weight: float
    reliability_weight: float
    uniform_mix: float
    correlated_group_cap: float
    take_rate: float = 0.05

    @property
    def rule_id(self) -> str:
        return (
            f"eta={self.eta:g}|q={self.quality_weight:g}|r={self.reliability_weight:g}"
            f"|mix={self.uniform_mix:g}|cap={self.correlated_group_cap:g}"
        )


def heterogeneous_providers() -> tuple[ProviderTechnology, ...]:
    """Frozen provider types motivated by the observed market taxonomy."""
    return (
        ProviderTechnology(
            "author", "author_anchor", 0.62, 0.98, 0.995, 35, 0.012, 0, False, False
        ),
        ProviderTechnology(
            "anchor_a", "anchor_reseller", 0.65, 0.96, 0.990, 28, 0.014, 0, False, False
        ),
        ProviderTechnology(
            "anchor_b", "anchor_reseller", 0.66, 0.95, 0.985, 25, 0.015, 0, False, False
        ),
        ProviderTechnology(
            "reserved_a", "reserved_capacity", 0.31, 0.94, 0.985, 75, 0.013, 7.0, True, True
        ),
        ProviderTechnology(
            "reserved_b", "reserved_capacity", 0.35, 0.93, 0.980, 65, 0.014, 6.0, True, True
        ),
        ProviderTechnology("spot_a", "spot_startup", 0.54, 0.90, 0.955, 18, 0.020, 0.5, True, True),
        ProviderTechnology("spot_b", "spot_startup", 0.57, 0.89, 0.945, 16, 0.022, 0.4, True, True),
        ProviderTechnology("spot_c", "spot_startup", 0.59, 0.88, 0.935, 14, 0.024, 0.3, True, True),
        ProviderTechnology(
            "custom_a", "custom_quality", 0.72, 1.08, 0.997, 30, 0.008, 3.0, True, False
        ),
        ProviderTechnology(
            "custom_b", "custom_quality", 0.76, 1.06, 0.995, 26, 0.009, 2.5, True, False
        ),
    )


def technology_stress_menus() -> dict[str, tuple[ProviderTechnology, ...]]:
    """Return bounded technology perturbations for selected-policy transport."""
    base = heterogeneous_providers()
    return {
        "base": base,
        "reserved_capacity_shortfall": tuple(
            replace(provider, capacity=0.35 * provider.capacity)
            if provider.provider_type == "reserved_capacity"
            else provider
            for provider in base
        ),
        "reserved_reliability_shock": tuple(
            replace(provider, reliability=0.88 * provider.reliability)
            if provider.provider_type == "reserved_capacity"
            else provider
            for provider in base
        ),
        "spot_cost_spike": tuple(
            replace(provider, marginal_cost=1.40 * provider.marginal_cost)
            if provider.provider_type == "spot_startup"
            else provider
            for provider in base
        ),
        "quality_compression": tuple(
            replace(provider, quality=min(provider.quality, 1.0))
            if provider.provider_type == "custom_quality"
            else provider
            for provider in base
        ),
    }


def _validate_prices(prices: np.ndarray, providers: tuple[ProviderTechnology, ...]) -> None:
    if prices.shape != (len(providers),):
        raise ValueError("price vector does not match provider menu")
    if np.any(~np.isfinite(prices)) or np.any(prices <= 0):
        raise ValueError("prices must be finite and positive")


def routing_weights(
    prices: np.ndarray,
    providers: tuple[ProviderTechnology, ...],
    rule: RouterRule,
) -> np.ndarray:
    """Return declared score shares before capacity truncation."""
    _validate_prices(prices, providers)
    if rule.eta < 0 or not 0 <= rule.uniform_mix < 1:
        raise ValueError("invalid router rule")
    if not 0 < rule.correlated_group_cap <= 1:
        raise ValueError("correlated_group_cap must lie in (0, 1]")
    quality = np.asarray([provider.quality for provider in providers], dtype=float)
    reliability = np.asarray([provider.reliability for provider in providers], dtype=float)
    log_score = (
        -rule.eta * np.log(prices)
        + rule.quality_weight * np.log(quality)
        + rule.reliability_weight * np.log(reliability)
    )
    log_score -= float(log_score.max())
    raw = np.exp(log_score)
    shares = raw / raw.sum()
    shares = (1.0 - rule.uniform_mix) * shares + rule.uniform_mix / len(providers)

    correlated = np.asarray([provider.correlated_pricer for provider in providers], dtype=bool)
    group_share = float(shares[correlated].sum())
    if correlated.any() and (~correlated).any() and group_share > rule.correlated_group_cap:
        shares[correlated] *= rule.correlated_group_cap / group_share
        remainder = float(shares[~correlated].sum())
        shares[~correlated] *= (1.0 - rule.correlated_group_cap) / remainder
    return shares / shares.sum()


def capacity_allocation(weights: np.ndarray, demand: float, capacities: np.ndarray) -> np.ndarray:
    """Proportionally route and exactly redistribute capacity overflow."""
    if demand < 0 or np.any(capacities < 0):
        raise ValueError("demand and capacities must be nonnegative")
    if weights.shape != capacities.shape or np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("invalid allocation weights")
    allocation = np.zeros_like(weights, dtype=float)
    remaining = float(demand)
    available = np.ones(len(weights), dtype=bool)
    for _ in range(len(weights) + 1):
        if remaining <= 1e-10 or not available.any():
            break
        local = weights * available
        local /= local.sum()
        proposal = remaining * local
        slack = capacities - allocation
        constrained = available & (proposal > slack + 1e-10)
        if not constrained.any():
            allocation += proposal
            remaining = 0.0
            break
        allocation[constrained] += slack[constrained]
        remaining -= float(slack[constrained].sum())
        available[constrained] = False
    return allocation


def market_outcome(
    prices: np.ndarray,
    providers: tuple[ProviderTechnology, ...],
    rule: RouterRule,
    *,
    demand_scale: float = 120.0,
    demand_elasticity: float = 0.6,
    delivered_value: float = 2.0,
    failure_loss: float = 0.8,
) -> dict[str, Any]:
    """Solve expected demand and capacity allocation for a fixed quote profile."""
    _validate_prices(prices, providers)
    weights = routing_weights(prices, providers, rule)
    capacities = np.asarray([provider.capacity for provider in providers], dtype=float)
    demand = float(demand_scale)
    allocation = capacity_allocation(weights, demand, capacities)
    for _ in range(200):
        served = float(allocation.sum())
        price_index = float(np.dot(allocation, prices) / served) if served > 0 else 4.0
        updated = demand_scale * price_index ** (-demand_elasticity)
        updated = float(np.clip(updated, 0.2 * demand_scale, 2.5 * demand_scale))
        new_demand = 0.65 * demand + 0.35 * updated
        new_allocation = capacity_allocation(weights, new_demand, capacities)
        if abs(new_demand - demand) <= 1e-9 and np.max(np.abs(new_allocation - allocation)) <= 1e-9:
            demand = new_demand
            allocation = new_allocation
            break
        demand = new_demand
        allocation = new_allocation

    cost = np.asarray([provider.marginal_cost for provider in providers], dtype=float)
    quality = np.asarray([provider.quality for provider in providers], dtype=float)
    reliability = np.asarray([provider.reliability for provider in providers], dtype=float)
    latency = np.asarray([provider.latency_cost for provider in providers], dtype=float)
    fixed = np.asarray([provider.fixed_cost for provider in providers], dtype=float)
    payment = allocation * prices
    successful = allocation * reliability
    failed = allocation * (1.0 - reliability)
    unserved = max(demand - float(allocation.sum()), 0.0)
    delivered_quality = successful * quality
    provider_profit = allocation * (prices - cost) - fixed
    router_revenue = rule.take_rate * float(payment.sum())
    failure_cost = failure_loss * (float(failed.sum()) + unserved)
    latency_cost = float(np.dot(allocation, latency))
    social_value = delivered_value * float(delivered_quality.sum())
    resource_cost = float(np.dot(allocation, cost)) + float(fixed.sum())
    welfare = social_value - resource_cost - failure_cost - latency_cost
    user_utility = (
        social_value - (1.0 + rule.take_rate) * float(payment.sum()) - failure_cost - latency_cost
    )
    total_provider_profit = float(provider_profit.sum())
    accounting_gap = welfare - (user_utility + total_provider_profit + router_revenue)
    served = float(allocation.sum())
    served_shares = allocation / served if served > 0 else np.zeros_like(allocation)
    return {
        "demand": demand,
        "served": served,
        "unserved": unserved,
        "success_rate": float(successful.sum() / demand) if demand > 0 else 0.0,
        "mean_delivered_quality": float(delivered_quality.sum() / successful.sum())
        if successful.sum() > 0
        else 0.0,
        "quality_adjusted_successes": float(delivered_quality.sum()),
        "consumer_payment": (1.0 + rule.take_rate) * float(payment.sum()),
        "provider_revenue": float(payment.sum()),
        "router_revenue": router_revenue,
        "provider_profit": total_provider_profit,
        "user_utility": user_utility,
        "welfare": welfare,
        "accounting_gap": accounting_gap,
        "served_hhi": float(np.square(served_shares).sum()),
        "viable_providers": int(np.sum(provider_profit >= 0)),
        "minimum_provider_profit": float(provider_profit.min()),
        "allocation": allocation,
        "provider_profits": provider_profit,
        "routing_weights": weights,
    }


def _price_grid(provider: ProviderTechnology, points: int) -> np.ndarray:
    lower = max(1.01 * provider.marginal_cost, 0.10)
    upper = max(2.5 * provider.benchmark_price, 1.1 * lower)
    return np.unique(
        np.concatenate(
            [
                np.geomspace(lower, upper, points),
                [provider.benchmark_price],
            ]
        )
    )


def unilateral_best_response(
    focal: int,
    prices: np.ndarray,
    providers: tuple[ProviderTechnology, ...],
    rule: RouterRule,
    *,
    grid_points: int = 41,
) -> tuple[float, float]:
    provider = providers[focal]
    current = market_outcome(prices, providers, rule)["provider_profits"][focal]
    candidates: list[tuple[float, float]] = []
    for price in _price_grid(provider, grid_points):
        trial = prices.copy()
        trial[focal] = price
        profit = float(market_outcome(trial, providers, rule)["provider_profits"][focal])
        candidates.append((profit, float(price)))
    best_profit, best_price = max(candidates, key=lambda item: (item[0], -item[1]))
    return best_price, float(best_profit - current)


def approximate_equilibrium(
    providers: tuple[ProviderTechnology, ...],
    rule: RouterRule,
    *,
    initialization: str = "benchmark",
    grid_points: int = 41,
    max_sweeps: int = 60,
) -> dict[str, Any]:
    """Compute a bounded cyclic-grid best-response fixed point."""
    if initialization == "benchmark":
        prices = np.asarray([provider.benchmark_price for provider in providers], dtype=float)
    elif initialization == "cost_plus":
        prices = np.asarray(
            [max(1.05 * provider.marginal_cost, 0.10) for provider in providers], dtype=float
        )
    elif initialization == "premium":
        prices = np.asarray([1.8 * provider.benchmark_price for provider in providers], dtype=float)
    else:
        raise ValueError("unknown initialization")
    for index, provider in enumerate(providers):
        if not provider.strategic:
            prices[index] = provider.benchmark_price

    strategic = [index for index, provider in enumerate(providers) if provider.strategic]
    converged = False
    sweep = 0
    for _sweep in range(1, max_sweeps + 1):
        sweep = _sweep
        previous = prices.copy()
        for focal in strategic:
            best_price, _ = unilateral_best_response(
                focal,
                prices,
                providers,
                rule,
                grid_points=grid_points,
            )
            prices[focal] = best_price
        if np.max(np.abs(np.log(prices / previous))) <= 1e-10:
            converged = True
            break

    regrets = []
    for focal in strategic:
        _, gain = unilateral_best_response(
            focal,
            prices,
            providers,
            rule,
            grid_points=grid_points,
        )
        regrets.append(max(gain, 0.0))
    outcome = market_outcome(prices, providers, rule)
    return {
        "prices": prices,
        "outcome": outcome,
        "iterations": sweep,
        "converged": converged,
        "maximum_unilateral_regret": float(max(regrets, default=0.0)),
        "aggregate_unilateral_regret": float(sum(regrets)),
        "initialization": initialization,
    }


def candidate_rules() -> tuple[RouterRule, ...]:
    rules = [
        RouterRule(eta, quality, reliability, mix, cap)
        for eta in (0.5, 2.0, 4.0)
        for quality in (0.0, 2.0, 4.0)
        for reliability in (0.0, 3.0)
        for mix in (0.0, 0.15)
        for cap in (0.50, 0.75, 1.0)
    ]
    baseline = RouterRule(2.0, 0.0, 0.0, 0.0, 1.0)
    return tuple(dict.fromkeys([baseline, *rules]))


def policy_panel(
    *,
    providers: tuple[ProviderTechnology, ...] | None = None,
    rules: tuple[RouterRule, ...] | None = None,
    grid_points: int = 31,
    max_sweeps: int = 40,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    menu = providers or heterogeneous_providers()
    policies = rules or candidate_rules()
    rows: list[dict[str, Any]] = []
    equilibria: dict[str, dict[str, Any]] = {}
    for rule in policies:
        equilibrium = approximate_equilibrium(
            menu,
            rule,
            grid_points=grid_points,
            max_sweeps=max_sweeps,
        )
        equilibria[rule.rule_id] = equilibrium
        outcome = equilibrium["outcome"]
        rows.append(
            {
                **asdict(rule),
                "rule_id": rule.rule_id,
                "iterations": equilibrium["iterations"],
                "converged": equilibrium["converged"],
                "maximum_unilateral_regret": equilibrium["maximum_unilateral_regret"],
                "aggregate_unilateral_regret": equilibrium["aggregate_unilateral_regret"],
                **{
                    key: value
                    for key, value in outcome.items()
                    if isinstance(value, (int, float, np.integer, np.floating))
                },
            }
        )
    return pd.DataFrame(rows), equilibria


def select_objectives(panel: pd.DataFrame) -> pd.DataFrame:
    """Select one rule for each private or social router objective."""
    frame = panel.copy()
    frame["viability_score"] = (
        frame["viable_providers"] - frame["served_hhi"] - frame["unserved"] / 120.0
    )
    objectives = {
        "global_welfare": "welfare",
        "router_revenue": "router_revenue",
        "delivered_quality": "quality_adjusted_successes",
        "provider_viability": "viability_score",
        "user_utility": "user_utility",
        "aggregate_provider_profit": "provider_profit",
    }
    rows = []
    for objective, column in objectives.items():
        ordered = frame.sort_values(
            [column, "maximum_unilateral_regret", "rule_id"],
            ascending=[False, True, True],
        )
        record = ordered.iloc[0].to_dict()
        record["objective"] = objective
        record["objective_column"] = column
        rows.append(record)
    return pd.DataFrame(rows)


def provider_type_panel(
    selected: pd.DataFrame,
    equilibria: dict[str, dict[str, Any]],
    providers: tuple[ProviderTechnology, ...],
) -> pd.DataFrame:
    rows = []
    for selection in selected.itertuples(index=False):
        equilibrium = equilibria[selection.rule_id]
        prices = equilibrium["prices"]
        outcome = equilibrium["outcome"]
        for provider_type in sorted({provider.provider_type for provider in providers}):
            indices = [
                index
                for index, provider in enumerate(providers)
                if provider.provider_type == provider_type
            ]
            allocation = outcome["allocation"][indices]
            rows.append(
                {
                    "objective": selection.objective,
                    "rule_id": selection.rule_id,
                    "provider_type": provider_type,
                    "providers": len(indices),
                    "mean_price": float(np.mean(prices[indices])),
                    "total_allocation": float(np.sum(allocation)),
                    "total_profit": float(np.sum(outcome["provider_profits"][indices])),
                    "mean_routing_weight": float(np.mean(outcome["routing_weights"][indices])),
                }
            )
    return pd.DataFrame(rows)


def selected_rule_stress_panel(
    selected: pd.DataFrame,
    *,
    menus: dict[str, tuple[ProviderTechnology, ...]] | None = None,
    grid_points: int = 31,
    max_sweeps: int = 40,
) -> pd.DataFrame:
    """Re-equilibrate each distinct selected rule under technology shocks."""
    objectives_by_rule = (
        selected.groupby("rule_id")["objective"].agg(lambda values: sorted(values)).to_dict()
    )
    rows: list[dict[str, Any]] = []
    for scenario, providers in (menus or technology_stress_menus()).items():
        for rule_id, objectives in objectives_by_rule.items():
            source = selected[selected["rule_id"].eq(rule_id)].iloc[0]
            rule = RouterRule(
                float(source["eta"]),
                float(source["quality_weight"]),
                float(source["reliability_weight"]),
                float(source["uniform_mix"]),
                float(source["correlated_group_cap"]),
                float(source["take_rate"]),
            )
            equilibrium = approximate_equilibrium(
                providers,
                rule,
                grid_points=grid_points,
                max_sweeps=max_sweeps,
            )
            outcome = equilibrium["outcome"]
            rows.append(
                {
                    "scenario": scenario,
                    "rule_id": rule_id,
                    "objectives": objectives,
                    "converged": equilibrium["converged"],
                    "maximum_unilateral_regret": equilibrium["maximum_unilateral_regret"],
                    **{
                        key: value
                        for key, value in outcome.items()
                        if isinstance(value, (int, float, np.integer, np.floating))
                    },
                }
            )
    return pd.DataFrame(rows)


def pairwise_coalition_regret(
    prices: np.ndarray,
    providers: tuple[ProviderTechnology, ...],
    rule: RouterRule,
    *,
    multipliers: tuple[float, ...] = (0.70, 0.85, 1.0, 1.15, 1.30),
) -> dict[str, Any]:
    """Bound the best same-type two-provider joint price deviation."""
    base = market_outcome(prices, providers, rule)["provider_profits"]
    best = {"gain": 0.0, "pair": None, "multipliers": None}
    for left in range(len(providers)):
        for right in range(left + 1, len(providers)):
            if (
                not providers[left].strategic
                or not providers[right].strategic
                or providers[left].provider_type != providers[right].provider_type
            ):
                continue
            baseline = float(base[left] + base[right])
            for left_multiplier in multipliers:
                for right_multiplier in multipliers:
                    trial = prices.copy()
                    trial[left] *= left_multiplier
                    trial[right] *= right_multiplier
                    profits = market_outcome(trial, providers, rule)["provider_profits"]
                    gain = float(profits[left] + profits[right] - baseline)
                    if gain > best["gain"]:
                        best = {
                            "gain": gain,
                            "pair": [providers[left].provider, providers[right].provider],
                            "multipliers": [left_multiplier, right_multiplier],
                        }
    return {
        "maximum_pairwise_joint_deviation_gain": float(best["gain"]),
        "maximizing_pair": best["pair"],
        "maximizing_multipliers": best["multipliers"],
        "grid": list(multipliers),
        "boundary": (
            "A positive bounded joint-deviation gain is mechanism susceptibility, "
            "not evidence of communication, agreement, or live collusion."
        ),
    }


def summarize(
    panel: pd.DataFrame,
    selected: pd.DataFrame,
    equilibria: dict[str, dict[str, Any]],
    providers: tuple[ProviderTechnology, ...],
    stress: pd.DataFrame,
) -> dict[str, Any]:
    baseline_id = RouterRule(2.0, 0.0, 0.0, 0.0, 1.0).rule_id
    baseline = panel[panel["rule_id"].eq(baseline_id)].iloc[0]
    coalition = {}
    for row in selected.itertuples(index=False):
        rule = RouterRule(
            row.eta,
            row.quality_weight,
            row.reliability_weight,
            row.uniform_mix,
            row.correlated_group_cap,
            row.take_rate,
        )
        coalition[row.objective] = pairwise_coalition_regret(
            equilibria[row.rule_id]["prices"], providers, rule
        )

    def native(value: Any) -> Any:
        return value.item() if isinstance(value, np.generic) else value

    return {
        "experiment_id": "sm4-multiobjective-router-game-v1",
        "evidence_status": "heterogeneous_structural_game_screen",
        "provider_types": {
            provider_type: sum(provider.provider_type == provider_type for provider in providers)
            for provider_type in sorted({provider.provider_type for provider in providers})
        },
        "candidate_rules": int(len(panel)),
        "converged_rules": int(panel["converged"].sum()),
        "maximum_accounting_gap": float(panel["accounting_gap"].abs().max()),
        "baseline_inverse_square": {
            key: native(baseline[key])
            for key in (
                "rule_id",
                "welfare",
                "router_revenue",
                "quality_adjusted_successes",
                "user_utility",
                "provider_profit",
                "viable_providers",
                "served_hhi",
                "maximum_unilateral_regret",
            )
        },
        "selected_rule_by_objective": selected[
            [
                "objective",
                "rule_id",
                "welfare",
                "router_revenue",
                "quality_adjusted_successes",
                "user_utility",
                "provider_profit",
                "viable_providers",
                "served_hhi",
                "maximum_unilateral_regret",
            ]
        ].to_dict("records"),
        "selected_rule_technology_stress": (
            stress.groupby("rule_id", as_index=False)
            .agg(
                scenarios=("scenario", "nunique"),
                worst_case_welfare=("welfare", "min"),
                best_case_welfare=("welfare", "max"),
                worst_case_router_revenue=("router_revenue", "min"),
                worst_case_quality_adjusted_successes=(
                    "quality_adjusted_successes",
                    "min",
                ),
                worst_case_viable_providers=("viable_providers", "min"),
                maximum_stress_unilateral_regret=(
                    "maximum_unilateral_regret",
                    "max",
                ),
            )
            .to_dict("records")
        ),
        "pairwise_coalition_susceptibility": coalition,
        "game_result": (
            "The rule maximizing one agent's objective generally differs from the "
            "welfare rule once quality, reliability, capacity, fixed investment, "
            "and demand elasticity are present. Approximate unilateral regret and "
            "bounded pairwise coalition regret are reported for every selected rule."
        ),
        "claim_boundary": (
            "Technologies and demand are declared scenarios, not cost or quality "
            "estimates for named live providers. Grid best responses establish only "
            "an approximate bounded equilibrium. Coalition gains show susceptibility, "
            "not conduct. Policy ranking is not a deployment recommendation without "
            "calibration and a randomized live trial."
        ),
    }


def _render(
    panel: pd.DataFrame, selected: pd.DataFrame, types: pd.DataFrame, out_dir: Path
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.0), constrained_layout=True)
    scatter = axes[0, 0].scatter(
        panel["welfare"],
        panel["router_revenue"],
        c=panel["quality_adjusted_successes"],
        cmap="viridis",
        s=20,
        alpha=0.65,
    )
    objective_codes = {
        "global_welfare": "W",
        "router_revenue": "R",
        "delivered_quality": "Q",
        "provider_viability": "V",
        "user_utility": "U",
        "aggregate_provider_profit": "P",
    }
    selected_points = (
        selected.groupby(["welfare", "router_revenue"], as_index=False)["objective"]
        .agg(lambda values: "/".join(objective_codes[value] for value in values))
        .sort_values(["welfare", "router_revenue"])
    )
    for row in selected_points.itertuples(index=False):
        axes[0, 0].scatter(
            row.welfare, row.router_revenue, marker="x", s=75, color="black"
        )
        axes[0, 0].annotate(
            row.objective,
            (row.welfare, row.router_revenue),
            xytext=(4, 5),
            textcoords="offset points",
            fontsize=7,
            fontweight="bold",
        )
    axes[0, 0].set(xlabel="social welfare", ylabel="router fee revenue", title="A. Policy frontier")
    axes[0, 0].text(
        0.02,
        0.03,
        "W welfare  R revenue  Q quality\nU user  P provider profit  V viability",
        transform=axes[0, 0].transAxes,
        fontsize=6,
        va="bottom",
    )
    fig.colorbar(scatter, ax=axes[0, 0], label="quality-adjusted successes")

    order = selected.sort_values("welfare")["objective"]
    axes[0, 1].barh(order, selected.set_index("objective").loc[order, "welfare"], color="#2A6F97")
    axes[0, 1].set(title="B. Welfare under objective-selected rules", xlabel="social welfare")

    pivot = types.pivot(index="provider_type", columns="objective", values="total_profit")
    pivot.plot(kind="bar", ax=axes[1, 0], width=0.8)
    axes[1, 0].set(title="C. Provider profit by technology", ylabel="profit", xlabel="")
    axes[1, 0].legend(frameon=False, fontsize=6, ncol=2)
    axes[1, 0].tick_params(axis="x", rotation=25)

    axes[1, 1].scatter(
        panel["served_hhi"], panel["viable_providers"], c=panel["welfare"], cmap="plasma", s=22
    )
    axes[1, 1].set(
        xlabel="served-share HHI", ylabel="viable providers", title="D. Concentration and viability"
    )
    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#e5e5e5", linewidth=0.6)
    fig.suptitle("Heterogeneous inference providers under alternative router objectives")
    fig.savefig(out_dir / "sm4_multiobjective_router_game.png", dpi=190)
    fig.savefig(out_dir / "sm4_multiobjective_router_game.pdf")
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    providers = heterogeneous_providers()
    panel, equilibria = policy_panel(providers=providers)
    selected = select_objectives(panel)
    types = provider_type_panel(selected, equilibria, providers)
    stress = selected_rule_stress_panel(selected)
    result = summarize(panel, selected, equilibria, providers, stress)
    save(panel, out_dir, "sm4_multiobjective_router_policies")
    save(selected, out_dir, "sm4_multiobjective_router_selected")
    save(types, out_dir, "sm4_multiobjective_router_provider_types")
    save(stress, out_dir, "sm4_multiobjective_router_stress")
    save_json(result, out_dir, "sm4_multiobjective_router_game_summary")
    _render(panel, selected, types, out_dir)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
