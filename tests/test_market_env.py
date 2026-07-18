"""Invariant and theory tests for the strategic market vertical slice."""

from __future__ import annotations

import math

import pytest

from orcap.market_env import (
    Availability,
    InversePriceRouter,
    LowestCostRouter,
    MarketKernel,
    ProviderAction,
    ProviderSpec,
    ReliabilityWeightedRouter,
    Workload,
    load_scenario,
)
from orcap.market_env.strategies import (
    AuthorAnchorStrategy,
    CostPlusStrategy,
    UndercutStrategy,
)
from orcap.market_env.theory import (
    isoelastic_welfare,
    symmetric_elastic_price,
    symmetric_interior_price,
    symmetric_profit_gradient,
    unilateral_profit,
)


def _providers(
    *,
    capacity_a: int = 10,
    capacity_b: int = 10,
    reliability_a: float = 1.0,
    reliability_b: float = 1.0,
) -> tuple[ProviderSpec, ...]:
    return (
        ProviderSpec(
            "a",
            marginal_cost=1.0,
            physical_capacity=capacity_a,
            capital_cost_per_slot=0.02,
            base_latency_ms=10,
            reliability=reliability_a,
        ),
        ProviderSpec(
            "b",
            marginal_cost=1.2,
            physical_capacity=capacity_b,
            capital_cost_per_slot=0.02,
            base_latency_ms=20,
            reliability=reliability_b,
        ),
    )


def _workload() -> Workload:
    return Workload(
        "short_chat",
        input_tokens=1_000,
        output_tokens=256,
        delivered_value=8.0,
        latency_cost_per_ms=0.001,
        failure_loss=4.0,
        fallback_latency_ms=5.0,
    )


def _actions() -> dict[str, ProviderAction]:
    return {"a": ProviderAction(2.0), "b": ProviderAction(4.0)}


def test_inverse_square_router_matches_public_simulation_formula() -> None:
    specs = {provider.provider: provider for provider in _providers()}
    probabilities = InversePriceRouter(2).probabilities(specs, _actions())
    assert probabilities == pytest.approx({"a": 0.8, "b": 0.2})
    assert sum(probabilities.values()) == pytest.approx(1.0)


def test_seeded_kernel_is_exactly_reproducible() -> None:
    kernel = MarketKernel(
        _providers(reliability_a=0.75, reliability_b=0.8),
        _workload(),
        InversePriceRouter(2),
        seed=123,
    )
    first = kernel.step(_actions(), demand=20)
    kernel.reset(seed=123)
    second = kernel.step(_actions(), demand=20)
    assert first == second


def test_failure_shocks_are_provider_request_specific_across_router_rules() -> None:
    providers = _providers(reliability_a=0.5, reliability_b=0.5)
    actions = _actions()
    inverse = MarketKernel(
        providers,
        _workload(),
        InversePriceRouter(2),
        seed=847,
    ).step(actions, demand=20)
    lowest = MarketKernel(
        providers,
        _workload(),
        LowestCostRouter(),
        seed=847,
    ).step(actions, demand=20)
    inverse_a = {
        outcome.request_index
        for outcome in inverse.requests
        if "a" in outcome.attempted_providers and outcome.served_provider != "a"
    }
    lowest_a = {
        outcome.request_index
        for outcome in lowest.requests
        if "a" in outcome.attempted_providers and outcome.served_provider != "a"
    }
    common_attempts = {
        outcome.request_index
        for outcome in inverse.requests
        if "a" in outcome.attempted_providers
    } & {
        outcome.request_index
        for outcome in lowest.requests
        if "a" in outcome.attempted_providers
    }
    assert (inverse_a & common_attempts) == (lowest_a & common_attempts)


def test_capacity_fallback_never_overserves_and_settles_every_request() -> None:
    kernel = MarketKernel(
        _providers(capacity_a=2, capacity_b=3),
        _workload(),
        LowestCostRouter(),
        seed=7,
    )
    result = kernel.step(_actions(), demand=8)
    by_provider = {row.provider: row for row in result.providers}
    assert by_provider["a"].attempted_requests <= by_provider["a"].admitted_capacity
    assert by_provider["b"].attempted_requests <= by_provider["b"].admitted_capacity
    assert result.served_requests == 5
    assert result.failed_requests == 3
    assert len(result.requests) == result.demand
    assert all(len(outcome.ordered_providers) == 2 for outcome in result.requests)


def test_request_attempt_limit_creates_a_reliability_allocation_margin() -> None:
    workload = Workload(
        "single_attempt",
        input_tokens=1,
        output_tokens=1,
        delivered_value=5,
        failure_loss=5,
        max_attempts=1,
    )
    result = MarketKernel(
        _providers(reliability_a=0.0, reliability_b=1.0),
        workload,
        LowestCostRouter(),
        seed=2,
    ).step(_actions(), demand=10)
    assert result.served_requests == 0
    assert all(outcome.ordered_providers == ("a",) for outcome in result.requests)


def test_internal_transfers_cancel_exactly_from_welfare() -> None:
    kernel = MarketKernel(
        _providers(reliability_a=0.6, reliability_b=0.7),
        _workload(),
        InversePriceRouter(2),
        seed=991,
    )
    result = kernel.step(_actions(), demand=20)
    assert result.total_user_utility + result.total_provider_profit == pytest.approx(
        result.total_welfare
    )
    assert sum(provider.revenue for provider in result.providers) == pytest.approx(
        result.total_payment
    )
    assert sum(provider.variable_cost for provider in result.providers) == pytest.approx(
        result.total_resource_cost
    )


def test_withdrawn_provider_is_ineligible() -> None:
    specs = {provider.provider: provider for provider in _providers()}
    actions = {
        "a": ProviderAction(2.0, availability=Availability.WITHDRAWN),
        "b": ProviderAction(4.0),
    }
    assert InversePriceRouter(2).probabilities(specs, actions) == {"b": 1.0}


def test_reliability_weight_can_reverse_the_price_only_ranking() -> None:
    specs = {
        provider.provider: provider
        for provider in _providers(reliability_a=0.75, reliability_b=0.99)
    }
    probabilities = ReliabilityWeightedRouter(
        exponent=2,
        reliability_exponent=4,
    ).probabilities(
        specs,
        {"a": ProviderAction(0.0020), "b": ProviderAction(0.0024)},
    )
    assert probabilities["b"] > probabilities["a"]


def test_transparent_strategies_respect_cost_and_reference_floors() -> None:
    spec = _providers()[0]
    assert CostPlusStrategy(1.5).act(spec, {}).quote == pytest.approx(1.5)
    assert AuthorAnchorStrategy(2.0, 1.25).act(spec, {}).quote == pytest.approx(2.5)
    undercut = UndercutStrategy(tick=0.1, margin_floor=0.2)
    assert undercut.act(spec, {"a": 2.0, "b": 1.1}).quote == pytest.approx(1.2)


def test_inverse_power_symmetric_stationary_price_has_sharp_threshold() -> None:
    assert symmetric_interior_price(providers=2, exponent=2, marginal_cost=1) is None
    assert symmetric_interior_price(providers=3, exponent=2, marginal_cost=1) == pytest.approx(4)
    assert symmetric_interior_price(providers=4, exponent=2, marginal_cost=1) == pytest.approx(3)
    assert symmetric_interior_price(
        providers=2, exponent=2.01, marginal_cost=1
    ) == pytest.approx(201)


def test_stationary_price_zeroes_profit_gradient_and_is_a_local_best_response() -> None:
    price = symmetric_interior_price(providers=3, exponent=2, marginal_cost=1)
    assert price is not None
    assert symmetric_profit_gradient(
        providers=3,
        exponent=2,
        marginal_cost=1,
        common_price=price,
    ) == pytest.approx(0, abs=1e-12)
    center = unilateral_profit(
        own_price=price,
        rival_prices=(price, price),
        exponent=2,
        marginal_cost=1,
    )
    for deviation in [price - 0.01, price + 0.01]:
        assert center > unilateral_profit(
            own_price=deviation,
            rival_prices=(price, price),
            exponent=2,
            marginal_cost=1,
        )


def test_two_provider_inverse_square_profile_has_upward_profit_gradient() -> None:
    for price in [1.01, 2.0, 10.0, 1_000.0]:
        assert (
            symmetric_profit_gradient(
                providers=2,
                exponent=2,
                marginal_cost=1,
                common_price=price,
            )
            > 0
        )
    profit = unilateral_profit(
        own_price=10,
        rival_prices=(10,),
        exponent=2,
        marginal_cost=1,
    )
    assert math.isfinite(profit)


def test_elastic_demand_regularizes_duopoly_but_not_free_entry_limit() -> None:
    assert symmetric_elastic_price(
        providers=2,
        exponent=2,
        demand_elasticity=2,
        marginal_cost=1,
    ) == pytest.approx(2)
    price = symmetric_elastic_price(
        providers=10_000,
        exponent=2,
        demand_elasticity=2,
        marginal_cost=1,
    )
    assert price == pytest.approx(2, rel=2e-4)
    assert isoelastic_welfare(
        1,
        marginal_cost=1,
        demand_elasticity=2,
    ) == pytest.approx(1)
    assert isoelastic_welfare(
        2,
        marginal_cost=1,
        demand_elasticity=2,
    ) == pytest.approx(0.75)


def test_versioned_scenario_fixture_loads() -> None:
    scenario = load_scenario("config/strategic_routing_v1.toml")
    assert scenario.scenario_id == "strategic-routing-v1-vertical-slice"
    assert scenario.horizon_epochs == 2_016
    assert len(scenario.providers) == 2
