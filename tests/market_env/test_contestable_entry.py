"""Tests for costly entry and contestable-demand theory benchmarks."""

from __future__ import annotations

import math

import numpy as np
import pytest

from orcap.market_env.contestable_entry import (
    adaptive_count_reduced_form,
    compare_entry_counts,
    delivered_probability,
    entry_welfare,
    expected_serial_attempts,
    free_entry_count,
    group_cut_gradients,
    group_elasticity,
    interior_public_profit_closed_form,
    omitted_rival_price_coefficient,
    pigouvian_entry_charge,
    required_learning_horizon,
    symmetric_public_operating_profit,
    welfare_entry_count,
)


def test_interior_public_profit_matches_price_share_accounting() -> None:
    closed = interior_public_profit_closed_form(
        providers=3,
        exponent=2,
        marginal_cost=1,
        public_demand=12,
    )
    accounted = symmetric_public_operating_profit(
        providers=3,
        exponent=2,
        marginal_cost=1,
        public_demand=12,
        price_cap=100,
    )
    assert closed == pytest.approx(12)
    assert accounted == pytest.approx(closed)


def test_group_elasticity_and_cut_gradients_recover_thresholds() -> None:
    assert group_elasticity(0.25, exponent=2) == pytest.approx(1.5)
    gradients = group_cut_gradients(
        0.25,
        exponent=2,
        price=1,
        marginal_cost=0,
    )
    assert gradients["log_revenue_cut_gradient"] == pytest.approx(0.5)
    assert gradients["log_profit_cut_gradient"] == pytest.approx(0.5)

    costly = group_cut_gradients(
        0.25,
        exponent=2,
        price=1,
        marginal_cost=0.4,
        capacity_shadow_cost=0.1,
    )
    assert costly["log_revenue_cut_gradient"] > 0
    assert costly["log_profit_cut_gradient"] < 0


def test_equal_share_common_experiments_recover_group_path_elasticity() -> None:
    shares = np.full(4, 0.25)
    covariance = np.eye(4)
    covariance[:2, :2] = 1.0
    result = omitted_rival_price_coefficient(
        shares,
        covariance,
        focal=0,
        exponent=2,
    )
    assert result["structural_log_share_slope"] == pytest.approx(-1.5)
    assert result["omitted_rival_term"] == pytest.approx(0.5)
    assert result["own_only_elasticity_magnitude"] == pytest.approx(1.0)
    assert result["own_only_elasticity_magnitude"] == pytest.approx(
        group_elasticity(0.5, exponent=2)
    )


def test_redundancy_and_attempt_identities() -> None:
    assert delivered_probability(0, 0.4) == 0
    assert delivered_probability(3, 0.4) == pytest.approx(1 - 0.6**3)
    assert expected_serial_attempts(3, 0.4) == pytest.approx(1 + 0.6 + 0.6**2)


def test_bilateral_profit_can_expand_entry_without_changing_public_price_formula() -> None:
    baseline = free_entry_count(
        max_providers=20,
        exponent=2,
        marginal_cost=1,
        public_demand=10,
        price_cap=10,
        fixed_entry_cost=1,
        bilateral_profit=0,
    )
    contracted = free_entry_count(
        max_providers=20,
        exponent=2,
        marginal_cost=1,
        public_demand=10,
        price_cap=10,
        fixed_entry_cost=1,
        bilateral_profit=0.75,
    )
    assert contracted > baseline


def test_free_entry_can_exceed_or_fall_below_welfare_entry() -> None:
    welfare = welfare_entry_count(
        max_providers=30,
        demand=10,
        delivered_value_minus_cost=2,
        availability=0.8,
        fixed_entry_cost=1,
    )
    free = free_entry_count(
        max_providers=30,
        exponent=2,
        marginal_cost=1,
        public_demand=20,
        price_cap=10,
        fixed_entry_cost=1,
        availability=0.8,
    )
    comparison = compare_entry_counts(free, welfare)
    assert comparison.direction == "excess_entry"

    high_resilience_value = welfare_entry_count(
        max_providers=30,
        demand=100,
        delivered_value_minus_cost=20,
        availability=0.1,
        fixed_entry_cost=1,
    )
    low_private = free_entry_count(
        max_providers=30,
        exponent=4,
        marginal_cost=1,
        public_demand=2,
        price_cap=4,
        fixed_entry_cost=1,
        availability=0.1,
    )
    assert compare_entry_counts(low_private, high_resilience_value).direction == (
        "insufficient_entry"
    )


def test_pigouvian_charge_exactly_aligns_private_and_social_entry_gain() -> None:
    before = 2
    fixed = 0.7
    private_operating = 1.8
    charge = pigouvian_entry_charge(
        before,
        entrant_private_operating_profit=private_operating,
        demand=10,
        delivered_value_minus_cost=3,
        availability=0.5,
        fixed_entry_cost=fixed,
        failed_attempt_cost=0.1,
    )
    social_gain = entry_welfare(
        before + 1,
        demand=10,
        delivered_value_minus_cost=3,
        availability=0.5,
        fixed_entry_cost=fixed,
        failed_attempt_cost=0.1,
    ) - entry_welfare(
        before,
        demand=10,
        delivered_value_minus_cost=3,
        availability=0.5,
        fixed_entry_cost=fixed,
        failed_attempt_cost=0.1,
    )
    assert private_operating - fixed - charge == pytest.approx(social_gain)


def test_learning_horizon_increases_as_conditional_variation_collapses() -> None:
    independent = required_learning_horizon(
        reward_noise_variance=1,
        conditional_experiment_variance=1,
        target_error=0.1,
        actions=4,
        error_probability=0.05,
    )
    correlated = required_learning_horizon(
        reward_noise_variance=1,
        conditional_experiment_variance=0.01,
        target_error=0.1,
        actions=4,
        error_probability=0.05,
    )
    assert correlated / independent > 99.8


def test_contestable_share_and_fixed_cost_create_zero_minority_and_linear_regimes() -> None:
    zero = adaptive_count_reduced_form(
        providers=100,
        signal_rank=100,
        gross_benefit=1,
        contestable_share=0.1,
        fixed_adaptation_cost=0.1,
        congestion_cost=1,
        congestion_exponent=1,
    )
    minority = adaptive_count_reduced_form(
        providers=100,
        signal_rank=10,
        gross_benefit=1,
        contestable_share=1,
        fixed_adaptation_cost=0,
        congestion_cost=1,
        congestion_exponent=1,
    )
    linear = adaptive_count_reduced_form(
        providers=100,
        signal_rank=100,
        gross_benefit=1,
        contestable_share=1,
        fixed_adaptation_cost=0,
        congestion_cost=1,
        congestion_exponent=1,
    )
    assert zero == 0
    assert 0 < minority < linear < 100
    assert minority == pytest.approx(math.sqrt(100 * 10 / 3))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"group_share": -0.1, "exponent": 2},
        {"group_share": 0.5, "exponent": 0},
    ],
)
def test_group_elasticity_rejects_invalid_inputs(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        group_elasticity(**kwargs)
