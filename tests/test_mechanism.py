import math

import pandas as pd
import pytest

from orcap.mechanism import (
    CapacityProcurementOffer,
    CertifiedCostCurveOffer,
    OutageScenario,
    ProviderOffer,
    allocation_counterfactual,
    allocation_shares,
    capacity_bond_floor,
    capacity_constrained_allocation,
    capacity_procurement_allocation,
    capacity_procurement_report_diagnostic,
    capacity_procurement_utility,
    certified_cost_curve_allocation,
    certified_cost_curve_vcg_payment,
    certified_cost_curve_vcg_report_diagnostic,
    certified_cost_curve_vcg_utility,
    declared_capacity_payoff,
    declared_reliability_payoff,
    expected_delivered_under_outage_scenarios,
    expected_net_welfare,
    expected_reliability_report_payoff,
    limited_liability_delivery_gain,
    own_price_share_elasticity,
    procurement_payment,
    procurement_report_diagnostic,
    procurement_utility,
    realized_provider_payoff,
    reported_cost_allocation,
    robust_outage_allocation,
    robust_outage_counterfactual,
    welfare_capacity_allocation,
    welfare_policy_counterfactual,
)


def test_capacity_certified_allocation_and_share_elasticity():
    offers = [
        ProviderOffer("a", price=1, reliability=1, committed_capacity=100, marginal_cost=0.4),
        ProviderOffer("b", price=2, reliability=1, committed_capacity=100, marginal_cost=0.4),
    ]
    shares = allocation_shares(offers)
    assert shares["a"] == 0.8
    assert shares["b"] == 0.2
    assert math.isclose(own_price_share_elasticity(shares["a"]), -0.4)


def test_positive_serving_margin_deters_deliberate_shortfall_without_a_bond():
    offer = ProviderOffer("a", price=1.0, reliability=1, committed_capacity=10, marginal_cost=0.4)
    floor = capacity_bond_floor(offer.price - offer.marginal_cost)
    served = realized_provider_payoff(
        offer, allocated_requests=10, served_requests=10, bond_per_missed_request=floor
    )
    rationed = realized_provider_payoff(
        offer, allocated_requests=10, served_requests=0, bond_per_missed_request=floor
    )
    assert served > rationed
    assert math.isclose(floor, 0.0)


def test_capacity_bond_covers_negative_serving_margin_to_deter_shortfall():
    offer = ProviderOffer("a", price=0.4, reliability=1, committed_capacity=10, marginal_cost=1.0)
    floor = capacity_bond_floor(offer.price - offer.marginal_cost)
    assert math.isclose(floor, 0.6)
    served = realized_provider_payoff(
        offer, allocated_requests=1, served_requests=1, bond_per_missed_request=floor + 0.01
    )
    rationed = realized_provider_payoff(
        offer, allocated_requests=1, served_requests=0, bond_per_missed_request=floor + 0.01
    )
    under_bonded = realized_provider_payoff(
        offer, allocated_requests=1, served_requests=0, bond_per_missed_request=floor - 0.01
    )
    assert served > rationed
    assert under_bonded > served


def test_limited_liability_caps_the_delivery_incentive_from_a_nominal_bond():
    assert limited_liability_delivery_gain(-1.0, 2.0, 0.4) == -0.6
    assert math.isclose(limited_liability_delivery_gain(-1.0, 2.0, 1.1), 0.1)


def test_finite_limited_liability_does_not_make_an_increasing_reliability_report_truthful():
    offers = [
        ProviderOffer("a", price=1.0, reliability=0.9, committed_capacity=100, marginal_cost=0.4),
        ProviderOffer("b", price=1.0, reliability=0.5, committed_capacity=100, marginal_cost=0.4),
    ]
    truthful = declared_reliability_payoff(
        offers,
        provider="a",
        actual_reliability=0.9,
        reported_reliability=0.9,
        demand=100,
        nominal_bond_per_missed_request=1.0,
        collectible_liability_cap=1.0,
    )
    overreported = declared_reliability_payoff(
        offers,
        provider="a",
        actual_reliability=0.9,
        reported_reliability=1.0,
        demand=100,
        nominal_bond_per_missed_request=1.0,
        collectible_liability_cap=1.0,
    )
    assert overreported > truthful
    assert expected_reliability_report_payoff(
        actual_reliability=0.9,
        allocated_requests=1,
        marginal_margin_per_success=0.6,
        nominal_bond_per_missed_request=5.0,
        collectible_liability_cap=1.0,
    ) == pytest.approx(0.44)


def test_reliability_report_payoff_requires_a_bounded_probability_and_nonnegative_liability():
    with pytest.raises(ValueError, match="actual_reliability"):
        expected_reliability_report_payoff(
            actual_reliability=1.01,
            allocated_requests=1,
            marginal_margin_per_success=1,
            nominal_bond_per_missed_request=1,
            collectible_liability_cap=1,
        )
    with pytest.raises(ValueError, match="bond"):
        expected_reliability_report_payoff(
            actual_reliability=0.5,
            allocated_requests=1,
            marginal_margin_per_success=1,
            nominal_bond_per_missed_request=-1,
            collectible_liability_cap=1,
        )


def test_joint_outage_scenarios_need_not_follow_marginal_uptime():
    allocation = allocation_shares(
        [
            ProviderOffer("a", price=1, reliability=1, committed_capacity=10, marginal_cost=0.5),
            ProviderOffer("b", price=1, reliability=1, committed_capacity=10, marginal_cost=0.5),
        ]
    ) * 10
    expected = expected_delivered_under_outage_scenarios(
        allocation,
        [
            OutageScenario(0.8, frozenset()),
            OutageScenario(0.2, frozenset({"a", "b"})),
        ],
    )
    assert expected == 8.0


def test_robust_outage_allocation_weakly_improves_the_joint_worst_case():
    offers = [
        ProviderOffer("cheap", price=1, reliability=1, committed_capacity=10, marginal_cost=0.5),
        ProviderOffer(
            "independent", price=2, reliability=1, committed_capacity=10, marginal_cost=0.5
        ),
    ]
    scenarios = [
        OutageScenario(0.8, frozenset()),
        OutageScenario(0.2, frozenset({"cheap"})),
    ]
    robust = robust_outage_allocation(offers, demand=10, scenarios=scenarios)
    assert robust["cheap"] == 0
    assert robust["independent"] == 10
    diagnostic = robust_outage_counterfactual(offers, demand=10, scenarios=scenarios)
    assert diagnostic["robust_worst_case_delivered"].iat[0] == 10
    assert diagnostic["score_worst_case_delivered"].iat[0] < 10
    assert diagnostic["robust_worst_case_delivery_gain"].iat[0] > 0


def test_robust_outage_allocation_rejects_unknown_joint_failure_domains():
    offers = [
        ProviderOffer("a", price=1, reliability=1, committed_capacity=10, marginal_cost=0.5)
    ]
    try:
        robust_outage_allocation(
            offers,
            demand=1,
            scenarios=[OutageScenario(1.0, frozenset({"not-a-provider"}))],
        )
    except ValueError as exc:
        assert "unknown providers" in str(exc)
    else:
        raise AssertionError("unknown outage provider should be rejected")


def test_zero_probability_outages_do_not_change_the_robust_support_problem():
    offers = [
        ProviderOffer("cheap", price=1, reliability=1, committed_capacity=10, marginal_cost=0.5),
        ProviderOffer(
            "expensive", price=2, reliability=1, committed_capacity=10, marginal_cost=0.5
        ),
    ]
    allocation = robust_outage_allocation(
        offers,
        demand=10,
        scenarios=[
            OutageScenario(1.0, frozenset()),
            OutageScenario(0.0, frozenset({"cheap"})),
        ],
    )
    assert allocation["cheap"] == 10
    assert allocation["expensive"] == 0


def test_outage_profiles_reject_unknown_or_non_finite_provider_allocations():
    with pytest.raises(ValueError, match="unknown providers"):
        expected_delivered_under_outage_scenarios(
            allocation_shares([ProviderOffer("a", 1, 1, 1, 0.5)]),
            [OutageScenario(1.0, frozenset({"missing"}))],
        )
    with pytest.raises(ValueError, match="finite"):
        expected_delivered_under_outage_scenarios(
            pd.Series({"a": float("inf")}),
            [OutageScenario(1.0, frozenset())],
        )


def test_zero_margin_requires_positive_bond_for_strict_delivery_preference():
    offer = ProviderOffer("a", price=1.0, reliability=1, committed_capacity=1, marginal_cost=1.0)
    assert capacity_bond_floor(0.0) == 0.0
    served = realized_provider_payoff(
        offer, allocated_requests=1, served_requests=1, bond_per_missed_request=0.0
    )
    rationed = realized_provider_payoff(
        offer, allocated_requests=1, served_requests=0, bond_per_missed_request=0.0
    )
    assert served == rationed
    assert realized_provider_payoff(
        offer, allocated_requests=1, served_requests=0, bond_per_missed_request=0.01
    ) < served


def test_capacity_constrained_allocation_waterfills_after_cheap_offer_is_capped():
    offers = [
        ProviderOffer("cheap", price=1, reliability=1, committed_capacity=10, marginal_cost=0.4),
        ProviderOffer(
            "expensive", price=2, reliability=1, committed_capacity=100, marginal_cost=0.4
        ),
    ]
    allocation = capacity_constrained_allocation(offers, demand=100)
    assert allocation["cheap"] == 10
    assert allocation["expensive"] == 90
    assert allocation.sum() == 100


def test_capacity_counterfactual_exposes_shortfall_and_unfilled_residual():
    offers = [
        ProviderOffer("cheap", price=1, reliability=1, committed_capacity=10, marginal_cost=0.4),
        ProviderOffer(
            "expensive", price=2, reliability=1, committed_capacity=20, marginal_cost=0.4
        ),
    ]
    counterfactual = allocation_counterfactual(offers, demand=100).set_index("provider")
    assert counterfactual.loc["cheap", "uncapped_capacity_shortfall"] == 70
    assert counterfactual["capacity_certified_allocated"].sum() == 30
    assert (counterfactual["capacity_certified_unfilled_demand"] == 70).all()


def test_capacity_certification_weakly_increases_deliverable_request_count():
    offers = [
        ProviderOffer("cheap", price=1, reliability=1, committed_capacity=10, marginal_cost=0.4),
        ProviderOffer(
            "expensive", price=2, reliability=1, committed_capacity=100, marginal_cost=0.4
        ),
    ]
    counterfactual = allocation_counterfactual(offers, demand=100).set_index("provider")
    assert counterfactual["uncapped_delivered_under_commitment"].sum() == 30
    assert counterfactual["capacity_certified_allocated"].sum() == 100
    assert counterfactual["capacity_certified_delivery_gain"].sum() == 70
    assert (counterfactual["uncapped_unserved_demand"] == 70).all()
    assert (counterfactual["capacity_certified_unfilled_demand"] == 0).all()


def test_hard_capacity_overreport_is_worse_when_it_creates_shortfall():
    offers = [
        ProviderOffer("a", price=1, reliability=1, committed_capacity=30, marginal_cost=0.4),
        ProviderOffer("b", price=1, reliability=1, committed_capacity=100, marginal_cost=0.4),
    ]
    truthful = declared_capacity_payoff(
        offers,
        provider="a",
        actual_capacity=30,
        reported_capacity=30,
        demand=100,
        bond_per_missed_request=0.1,
    )
    overreported = declared_capacity_payoff(
        offers,
        provider="a",
        actual_capacity=30,
        reported_capacity=100,
        demand=100,
        bond_per_missed_request=0.1,
    )
    assert truthful > overreported


def test_cost_only_procurement_menu_is_monotone_and_truthful_on_a_report_grid():
    offers = [
        ProviderOffer("a", price=1, reliability=1, committed_capacity=100, marginal_cost=1),
        ProviderOffer("b", price=1.5, reliability=1, committed_capacity=100, marginal_cost=1.5),
    ]
    reports = [0.5, 0.8, 1.0, 1.4, 2.0]
    diagnostic = procurement_report_diagnostic(
        offers,
        provider="a",
        true_cost=1.0,
        report_grid=reports,
        demand=100,
        cost_upper_bound=4.0,
        quadrature_steps=4_096,
    )
    assert diagnostic["allocated_requests"].is_monotonic_decreasing
    truthful_utility = diagnostic.loc[
        diagnostic["reported_cost"] == 1.0, "utility_at_true_cost"
    ].iat[0]
    assert truthful_utility >= diagnostic["utility_at_true_cost"].max() - 0.01
    assert truthful_utility >= -0.01


def test_procurement_payment_gives_upper_cost_type_zero_utility():
    offers = [
        ProviderOffer("a", price=1, reliability=1, committed_capacity=100, marginal_cost=1),
        ProviderOffer("b", price=2, reliability=1, committed_capacity=100, marginal_cost=2),
    ]
    upper = 4.0
    allocation = reported_cost_allocation(
        offers, provider="a", reported_cost=upper, demand=100
    )
    payment = procurement_payment(
        offers, provider="a", reported_cost=upper, demand=100, cost_upper_bound=upper
    )
    utility = procurement_utility(
        offers,
        provider="a",
        true_cost=upper,
        reported_cost=upper,
        demand=100,
        cost_upper_bound=upper,
    )
    assert math.isclose(payment, upper * allocation)
    assert math.isclose(utility, 0.0)


def test_convex_capacity_procurement_is_cost_minimizing_and_feasible():
    offers = [
        CapacityProcurementOffer("a", 1.0, 10.0, 1.0),
        CapacityProcurementOffer("b", 2.0, 10.0, 1.0),
    ]
    allocation = capacity_procurement_allocation(offers, demand=10)
    assert allocation.sum() == pytest.approx(10)
    assert allocation["a"] > allocation["b"]
    assert (allocation <= 10).all()


def test_convex_capacity_procurement_menu_is_monotone_truthful_and_individually_rational():
    offers = [
        CapacityProcurementOffer("a", 1.0, 10.0, 1.0),
        CapacityProcurementOffer("b", 2.0, 10.0, 1.0),
    ]
    diagnostic = capacity_procurement_report_diagnostic(
        offers,
        provider="a",
        true_linear_cost=1.0,
        report_grid=[0.0, 0.5, 1.0, 1.5, 2.0, 3.0],
        demand=10,
        cost_upper_bound=4.0,
        quadrature_steps=4_096,
    )
    assert diagnostic["procured_capacity"].is_monotonic_decreasing
    truthful = diagnostic.loc[
        diagnostic["reported_linear_cost"] == 1.0, "utility_at_true_cost"
    ].iat[0]
    assert truthful >= diagnostic["utility_at_true_cost"].max() - 0.01
    assert truthful >= -0.01
    upper_type_utility = capacity_procurement_utility(
        offers,
        provider="a",
        true_linear_cost=4.0,
        reported_linear_cost=4.0,
        demand=10,
        cost_upper_bound=4.0,
    )
    assert upper_type_utility == pytest.approx(0.0)


def test_cost_curve_vcg_procures_least_cost_certified_units_and_pays_pivot_externality():
    offers = [
        CertifiedCostCurveOffer("a", certified_capacity=2, reported_marginal_costs=(1.0, 3.0)),
        CertifiedCostCurveOffer("b", certified_capacity=2, reported_marginal_costs=(2.0, 4.0)),
    ]
    allocation = certified_cost_curve_allocation(offers, demand=2)
    assert allocation.to_dict() == {"a": 1, "b": 1}
    payment = certified_cost_curve_vcg_payment(
        offers, provider="a", demand=2, unfilled_penalty=20.0
    )
    assert payment == pytest.approx(4.0)
    utility = certified_cost_curve_vcg_utility(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 3.0),
        demand=2,
        unfilled_penalty=20.0,
    )
    assert utility == pytest.approx(3.0)


def test_cost_curve_vcg_has_truthful_best_response_on_a_convex_schedule_grid():
    offers = [
        CertifiedCostCurveOffer("a", certified_capacity=2, reported_marginal_costs=(1.0, 3.0)),
        CertifiedCostCurveOffer("b", certified_capacity=2, reported_marginal_costs=(2.0, 4.0)),
    ]
    diagnostic = certified_cost_curve_vcg_report_diagnostic(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 3.0),
        report_schedules=[(0.0, 0.0), (1.0, 3.0), (5.0, 6.0)],
        demand=2,
        unfilled_penalty=20.0,
    )
    truth = diagnostic.loc[
        diagnostic["reported_marginal_costs"] == (1.0, 3.0), "utility_at_true_cost_curve"
    ].iat[0]
    assert truth >= diagnostic["utility_at_true_cost_curve"].max() - 1e-9
    assert truth >= 0


def test_cost_curve_vcg_rejects_nonconvex_or_uncertified_schedule_reports():
    with pytest.raises(ValueError, match="length"):
        certified_cost_curve_allocation(
            [CertifiedCostCurveOffer("a", certified_capacity=2, reported_marginal_costs=(1.0,))],
            demand=1,
        )
    with pytest.raises(ValueError, match="non-decreasing"):
        certified_cost_curve_allocation(
            [
                CertifiedCostCurveOffer(
                    "a", certified_capacity=2, reported_marginal_costs=(2.0, 1.0)
                )
            ],
            demand=1,
        )


def test_known_primitive_welfare_rule_dominates_price_and_reliability_baselines():
    offers = [
        ProviderOffer("cheap", 1.0, 0.1, 10, 1.0),
        ProviderOffer("reliable", 1.0, 0.9, 10, 5.0),
        ProviderOffer("very-expensive", 1.0, 1.0, 10, 12.0),
    ]
    allocation = welfare_capacity_allocation(offers, demand=10, request_value=10)
    assert allocation["reliable"] == 10
    assert expected_net_welfare(offers, allocation, request_value=10) == pytest.approx(40)
    comparison = welfare_policy_counterfactual(offers, demand=10, request_value=10).set_index(
        "policy"
    )
    assert comparison.loc["expected_welfare", "welfare_gain_over_policy"] == pytest.approx(0)
    assert comparison.loc["lowest_cost", "welfare_gain_over_policy"] > 0
    assert comparison.loc["reliability_only", "welfare_gain_over_policy"] > 0
