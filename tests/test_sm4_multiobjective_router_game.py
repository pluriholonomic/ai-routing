from __future__ import annotations

import json

import numpy as np
import pytest

from orcap.analysis.sm4_multiobjective_router_game import (
    ProviderTechnology,
    RouterRule,
    approximate_equilibrium,
    capacity_allocation,
    market_outcome,
    policy_panel,
    routing_weights,
    select_objectives,
    selected_rule_stress_panel,
    summarize,
    technology_stress_menus,
)


def small_menu() -> tuple[ProviderTechnology, ...]:
    return (
        ProviderTechnology("anchor", "anchor", 0.6, 1.0, 0.99, 60, 0.01, 0, False, False),
        ProviderTechnology("reserved", "reserved", 0.3, 0.95, 0.98, 80, 0.01, 2, True, True),
        ProviderTechnology("quality", "quality", 0.7, 1.1, 0.995, 50, 0.005, 1, True, False),
    )


def test_capacity_allocation_conserves_and_respects_caps() -> None:
    allocation = capacity_allocation(
        np.array([0.8, 0.2]),
        demand=10,
        capacities=np.array([2.0, 20.0]),
    )
    assert allocation.sum() == pytest.approx(10)
    assert allocation[0] == pytest.approx(2)
    assert np.all(allocation <= np.array([2.0, 20.0]))


def test_group_cap_binds_declared_correlated_pricers() -> None:
    menu = small_menu()
    rule = RouterRule(4, 0, 0, 0, 0.25)
    shares = routing_weights(np.array([1.0, 0.35, 1.0]), menu, rule)
    assert shares[1] == pytest.approx(0.25)
    assert shares.sum() == pytest.approx(1)


def test_welfare_accounting_cancels_payments() -> None:
    menu = small_menu()
    outcome = market_outcome(np.array([1.0, 0.7, 1.2]), menu, RouterRule(2, 2, 2, 0, 1))
    assert outcome["accounting_gap"] == pytest.approx(0, abs=1e-9)


def test_approximate_equilibrium_reports_bounded_regret() -> None:
    menu = small_menu()
    result = approximate_equilibrium(
        menu,
        RouterRule(2, 0, 0, 0, 1),
        grid_points=13,
        max_sweeps=20,
    )
    assert result["maximum_unilateral_regret"] >= 0
    assert len(result["prices"]) == len(menu)


def test_objective_selection_returns_each_agent_objective() -> None:
    menu = small_menu()
    rules = (
        RouterRule(2, 0, 0, 0, 1),
        RouterRule(1, 4, 3, 0.1, 0.5),
    )
    panel, _ = policy_panel(
        providers=menu,
        rules=rules,
        grid_points=11,
        max_sweeps=15,
    )
    selected = select_objectives(panel)
    assert set(selected["objective"]) == {
        "global_welfare",
        "router_revenue",
        "delivered_quality",
        "provider_viability",
        "user_utility",
        "aggregate_provider_profit",
    }
    _, equilibria = policy_panel(
        providers=menu,
        rules=rules,
        grid_points=11,
        max_sweeps=15,
    )
    stress = selected_rule_stress_panel(
        selected,
        menus={"base": menu},
        grid_points=9,
        max_sweeps=10,
    )
    payload = summarize(panel, selected, equilibria, menu, stress)
    json.dumps(payload)


def test_technology_stresses_preserve_provider_identity() -> None:
    menus = technology_stress_menus()
    names = [[provider.provider for provider in menu] for menu in menus.values()]
    assert all(item == names[0] for item in names)
    base = menus["base"]
    shortfall = menus["reserved_capacity_shortfall"]
    assert sum(provider.capacity for provider in shortfall) < sum(
        provider.capacity for provider in base
    )
