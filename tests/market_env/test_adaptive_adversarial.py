from __future__ import annotations

import math

import pytest

from orcap.market_env.exploitability import (
    coalition_grid_audit,
    expected_capacity_profits,
    unilateral_grid_audit,
)
from orcap.market_env.routers import InversePriceRouter
from orcap.market_env.routers_adaptive import (
    AdaptiveMonotoneRouter,
    HardenedAdaptiveRouter,
    MenuProjectedRouter,
)
from orcap.market_env.types import ProviderAction, ProviderSpec


def _market(n: int = 3):
    specs = {
        f"p{i}": ProviderSpec(
            provider=f"p{i}",
            marginal_cost=0.2 + 0.01 * i,
            physical_capacity=100,
            reliability=0.99 - 0.01 * i,
        )
        for i in range(n)
    }
    actions = {
        provider: ProviderAction(1.0 + 0.1 * index)
        for index, provider in enumerate(specs)
    }
    return specs, actions


@pytest.mark.parametrize(
    "router",
    [
        AdaptiveMonotoneRouter(),
        MenuProjectedRouter(),
        HardenedAdaptiveRouter(operator_share_cap=0.6),
    ],
)
def test_adaptive_router_probabilities_are_valid_and_price_monotone(router):
    specs, actions = _market()
    baseline = router.probabilities(specs, actions)
    assert sum(baseline.values()) == pytest.approx(1.0)
    assert all(value > 0 for value in baseline.values())
    expensive = dict(actions)
    expensive["p0"] = ProviderAction(actions["p0"].quote * 1.2)
    changed = router.probabilities(specs, expensive)
    assert changed["p0"] <= baseline["p0"] + 1e-12


def test_hardened_router_commits_lags_and_caps_operator_share():
    specs, actions = _market(4)
    router = HardenedAdaptiveRouter(
        commitment_epochs=3,
        smoothing_alpha=0.5,
        operator_share_cap=0.55,
        operator_groups={"p0": "same", "p1": "same"},
    )
    first = router.probabilities(specs, actions)
    assert first["p0"] + first["p1"] <= 0.55 + 1e-12
    state = router.state
    router.advance(specs, actions)
    assert router.state.epoch == state.epoch + 1
    assert router.state.committed_at == state.committed_at
    shock = dict(actions)
    shock["p0"] = ProviderAction(0.4)
    before = router.probabilities(specs, shock)
    router.advance(specs, shock)
    after = router.probabilities(specs, shock)
    assert sum(after.values()) == pytest.approx(1.0)
    assert before["p0"] + before["p1"] <= 0.55 + 1e-12
    assert after["p0"] + after["p1"] <= 0.55 + 1e-12
    assert router.state.smoothed_quotes["p0"] > 0.4
    router.advance(specs, shock)
    assert router.state.committed_at == router.state.epoch


def test_hardened_router_bounds_share_increases_but_not_losses():
    specs, actions = _market()
    limit = math.log(1.25)
    router = HardenedAdaptiveRouter(
        max_log_share_change=limit,
        commitment_epochs=100,
        operator_share_cap=1.0,
    )
    old = router.probabilities(specs, actions)
    router.advance(specs, actions)
    shock = dict(actions)
    shock["p0"] = ProviderAction(0.25)
    new = router.probabilities(specs, shock)
    for provider in specs:
        assert new[provider] <= old[provider] * math.exp(limit) + 1e-12
    assert new["p0"] > old["p0"]


def test_cap_bound_provider_still_loses_share_when_raising_price():
    specs, actions = _market(4)
    actions["p0"] = ProviderAction(0.05)
    router = HardenedAdaptiveRouter(operator_share_cap=0.60)
    incumbent = router.probabilities(specs, actions)
    router.advance(specs, actions)
    assert incumbent["p0"] == pytest.approx(0.60)
    raised = dict(actions)
    raised["p0"] = ProviderAction(0.075)
    changed = router.probabilities(specs, raised)
    assert changed["p0"] == pytest.approx(0.0)


def test_quote_locked_operators_do_not_receive_cap_redistribution():
    specs, actions = _market(3)
    router = HardenedAdaptiveRouter(operator_share_cap=0.60)
    router.advance(specs, actions)
    raised = dict(actions)
    raised["p0"] = ProviderAction(actions["p0"].quote * 1.5)
    raised["p1"] = ProviderAction(actions["p1"].quote * 1.5)
    changed = router.probabilities(specs, raised)
    assert changed["p0"] == pytest.approx(0.0)
    assert changed["p1"] == pytest.approx(0.0)
    assert changed["p2"] == pytest.approx(1.0)


def test_expected_profit_respects_capacity_and_global_deviation_search():
    specs, actions = _market()
    router = InversePriceRouter(2.0)
    profile = expected_capacity_profits(router, specs, actions, demand=1_000)
    assert all(profile.served[p] <= specs[p].physical_capacity for p in specs)
    audit = unilateral_grid_audit(
        router,
        specs,
        actions,
        demand=100,
        quote_multipliers=(0.7, 1.0, 1.3),
        capacity_fractions=(0.5, 1.0),
    )
    assert set(audit["best_by_provider"]) == set(specs)
    assert audit["max_gain"] >= -1e-12
    assert len(audit["searched_deviations"]) == len(specs) * 3 * 2


def test_coalition_audit_is_complete_and_never_below_incumbent():
    specs, actions = _market()
    result = coalition_grid_audit(
        AdaptiveMonotoneRouter(),
        specs,
        actions,
        demand=100,
        quote_multipliers=(0.8, 1.0, 1.2),
    )
    assert len(result["coalitions"]) == 3
    assert result["max_gain"] >= -1e-12
    assert all(row["gain"] >= -1e-12 for row in result["coalitions"])
