import math
from itertools import combinations_with_replacement

import pandas as pd
import pytest

from orcap.mechanism import (
    CapacityProcurementOffer,
    CertifiedCostCurveOffer,
    CollateralizedCapacityCurveOffer,
    DeliveryCollateralOffer,
    DeliveryParticipationOffer,
    OutageScenario,
    ProviderOffer,
    allocation_counterfactual,
    allocation_shares,
    audited_reliability_minimum_score_scale,
    audited_reliability_report_diagnostic,
    audited_reliability_report_payoff,
    bounded_log_score,
    capacity_bond_floor,
    capacity_constrained_allocation,
    capacity_procurement_allocation,
    capacity_procurement_report_diagnostic,
    capacity_procurement_utility,
    certified_audited_vcg_minimum_score_scale,
    certified_audited_vcg_product_report_diagnostic,
    certified_cost_curve_allocation,
    certified_cost_curve_vcg_payment,
    certified_cost_curve_vcg_report_diagnostic,
    certified_cost_curve_vcg_utility,
    certified_reliability_cost_allocation,
    collateralized_capacity_reliability_allocation,
    collateralized_capacity_reliability_minimum_score_scale,
    collateralized_capacity_reliability_product_report_diagnostic,
    collateralized_capacity_vcg_allocation,
    collateralized_capacity_vcg_payment,
    collateralized_capacity_vcg_report_diagnostic,
    collateralized_capacity_vcg_utility,
    collateralized_delivery_allocation,
    collateralized_reported_capacity,
    declared_capacity_payoff,
    declared_reliability_payoff,
    delivery_collateral_capacities,
    expected_delivered_under_outage_scenarios,
    expected_net_welfare,
    expected_reliability_report_payoff,
    limited_liability_delivery_gain,
    minimum_collectible_delivery_bond,
    minimum_reservation_transfer,
    own_price_share_elasticity,
    procurement_payment,
    procurement_report_diagnostic,
    procurement_utility,
    realized_provider_payoff,
    reported_cost_allocation,
    reservation_delivery_diagnostic,
    reservation_delivery_participation_diagnostic,
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


def test_delivery_collateral_capacity_turns_finite_bond_collateral_into_a_hard_cap():
    offer = DeliveryCollateralOffer(
        provider="underwater",
        delivery_price=0.4,
        known_marginal_cost=1.0,
        reliability=1.0,
        physical_capacity=10.0,
        posted_collateral=1.5,
    )
    capacities = delivery_collateral_capacities([offer], minimum_delivery_gain=0.1).set_index(
        "provider"
    )

    assert minimum_collectible_delivery_bond(-0.6, minimum_delivery_gain=0.1) == pytest.approx(0.7)
    assert capacities.loc["underwater", "collateral_capacity"] == pytest.approx(1.5 / 0.7)
    assert capacities.loc["underwater", "collateral_certified_capacity"] == pytest.approx(1.5 / 0.7)


def test_collateralized_delivery_allocation_reallocates_beyond_the_bond_limited_cap():
    offers = [
        DeliveryCollateralOffer(
            provider="cheap-underwater",
            delivery_price=1.0,
            known_marginal_cost=2.0,
            reliability=1.0,
            physical_capacity=10.0,
            posted_collateral=2.0,
        ),
        DeliveryCollateralOffer(
            provider="expensive-profitable",
            delivery_price=2.0,
            known_marginal_cost=1.0,
            reliability=1.0,
            physical_capacity=10.0,
            posted_collateral=0.0,
        ),
    ]

    allocation = collateralized_delivery_allocation(offers, demand=5.0)

    assert allocation["cheap-underwater"] == 2.0
    assert allocation["expensive-profitable"] == 3.0
    assert allocation.sum() == 5.0


def test_reservation_transfer_cancels_from_delivery_incentive_and_collateral_certificate():
    base = dict(
        provider="provider",
        delivery_price=0.5,
        known_marginal_cost=1.0,
        reliability=1.0,
        physical_capacity=10.0,
        posted_collateral=2.2,
    )
    no_reservation = reservation_delivery_diagnostic(
        [DeliveryCollateralOffer(**base, reservation_transfer=0.0)],
        demand=4.0,
        minimum_delivery_gain=0.05,
    ).iloc[0]
    paid_reservation = reservation_delivery_diagnostic(
        [DeliveryCollateralOffer(**base, reservation_transfer=7.0)],
        demand=4.0,
        minimum_delivery_gain=0.05,
    ).iloc[0]

    assert no_reservation["delivery_gain_per_feasible_request"] == pytest.approx(0.05)
    assert paid_reservation["delivery_gain_per_feasible_request"] == pytest.approx(0.05)
    assert paid_reservation["all_served_payoff"] - no_reservation["all_served_payoff"] == 7.0
    assert paid_reservation["all_rationed_payoff"] - no_reservation["all_rationed_payoff"] == 7.0
    assert bool(paid_reservation["allocation_is_collateral_feasible"])
    assert bool(paid_reservation["delivery_gain_target_met"])


def test_minimum_reservation_transfer_recovers_served_state_participation_after_collateral_cost():
    minimum = minimum_reservation_transfer(
        allocated_requests=2.0,
        marginal_margin_per_request=-0.5,
        bond_per_missed_request=0.6,
        collateral_capital_cost_rate=0.1,
        outside_option=0.2,
    )

    assert minimum == pytest.approx(1.32)
    assert (
        minimum_reservation_transfer(
            allocated_requests=0.0,
            marginal_margin_per_request=-10.0,
            bond_per_missed_request=5.0,
            collateral_capital_cost_rate=1.0,
            outside_option=100.0,
        )
        == 0.0
    )


def test_participation_certificate_prices_collateral_capital_without_weakening_delivery():
    base = dict(
        provider="underwater",
        delivery_price=0.5,
        known_marginal_cost=1.0,
        reliability=1.0,
        physical_capacity=10.0,
        posted_collateral=4.0,
        outside_option=0.2,
        collateral_capital_cost_rate=0.1,
    )
    binding = reservation_delivery_participation_diagnostic(
        [DeliveryParticipationOffer(**base, reservation_transfer=1.32)],
        demand=2.0,
        minimum_delivery_gain=0.1,
    ).iloc[0]
    higher_transfer = reservation_delivery_participation_diagnostic(
        [DeliveryParticipationOffer(**base, reservation_transfer=4.0)],
        demand=2.0,
        minimum_delivery_gain=0.1,
    ).iloc[0]

    assert binding["minimum_reservation_transfer"] == pytest.approx(1.32)
    assert binding["all_served_payoff_net_collateral_cost"] == pytest.approx(0.2)
    assert binding["all_rationed_payoff_net_collateral_cost"] == pytest.approx(0.0)
    assert binding["delivery_gain_per_feasible_request"] == pytest.approx(0.1)
    assert bool(binding["all_served_participation_met"])
    assert bool(binding["allocation_is_collateral_feasible"])
    assert higher_transfer["delivery_gain_per_feasible_request"] == pytest.approx(0.1)


def test_participation_primitives_reject_negative_collateral_capital_cost_or_outside_option():
    with pytest.raises(ValueError, match="non-negative"):
        minimum_reservation_transfer(
            allocated_requests=1.0,
            marginal_margin_per_request=0.0,
            bond_per_missed_request=0.0,
            collateral_capital_cost_rate=-0.1,
            outside_option=0.0,
        )
    with pytest.raises(ValueError, match="non-negative"):
        reservation_delivery_participation_diagnostic(
            [
                DeliveryParticipationOffer(
                    provider="invalid",
                    delivery_price=1.0,
                    known_marginal_cost=0.5,
                    reliability=1.0,
                    physical_capacity=1.0,
                    posted_collateral=0.0,
                    outside_option=-1.0,
                )
            ],
            demand=1.0,
        )


def test_delivery_collateral_primitives_reject_nonpositive_price_and_handle_an_empty_market():
    with pytest.raises(ValueError, match="delivery price"):
        delivery_collateral_capacities(
            [
                DeliveryCollateralOffer(
                    provider="free",
                    delivery_price=0.0,
                    known_marginal_cost=0.0,
                    reliability=1.0,
                    physical_capacity=1.0,
                    posted_collateral=0.0,
                )
            ]
        )
    assert collateralized_delivery_allocation([], demand=10.0).empty


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


def test_bounded_audit_score_recovers_truthfulness_on_an_explicit_finite_grid():
    grid = (0.5, 0.9, 0.99)
    allocation = {0.5: 1.0, 0.9: 5.0, 0.99: 10.0}
    scale = audited_reliability_minimum_score_scale(
        reliability_grid=grid,
        allocation_by_report=allocation,
        marginal_margin_per_success=0.6,
        nominal_bond_per_missed_request=1.0,
        collectible_liability_cap=1.0,
        audit_probability=0.1,
        strict_advantage=1e-5,
    )
    truthful = audited_reliability_report_payoff(
        actual_reliability=0.9,
        reported_reliability=0.9,
        allocated_requests=allocation[0.9],
        marginal_margin_per_success=0.6,
        nominal_bond_per_missed_request=1.0,
        collectible_liability_cap=1.0,
        audit_probability=0.1,
        audit_score_scale=scale,
        report_floor=0.01,
    )
    overreported = audited_reliability_report_payoff(
        actual_reliability=0.9,
        reported_reliability=0.99,
        allocated_requests=allocation[0.99],
        marginal_margin_per_success=0.6,
        nominal_bond_per_missed_request=1.0,
        collectible_liability_cap=1.0,
        audit_probability=0.1,
        audit_score_scale=scale,
        report_floor=0.01,
    )
    assert truthful > overreported
    diagnostic = audited_reliability_report_diagnostic(
        reliability_grid=grid,
        allocation_by_report=allocation,
        marginal_margin_per_success=0.6,
        nominal_bond_per_missed_request=1.0,
        collectible_liability_cap=1.0,
        audit_probability=0.1,
        audit_score_scale=scale,
    )
    off_diagonal = diagnostic[diagnostic["true_reliability"] != diagnostic["reported_reliability"]]
    assert (off_diagonal["truthful_payoff_advantage"] > 0).all()


def test_bounded_log_score_requires_clipping_but_has_finite_nonnegative_transfers():
    assert bounded_log_score(reported_reliability=0.01, audit_success=True, report_floor=0.01) == 0
    assert bounded_log_score(reported_reliability=0.99, audit_success=True, report_floor=0.01) > 0
    with pytest.raises(ValueError, match="clipped"):
        bounded_log_score(reported_reliability=1.0, audit_success=True, report_floor=0.01)
    with pytest.raises(ValueError, match="audit_probability"):
        audited_reliability_minimum_score_scale(
            reliability_grid=(0.5, 0.9),
            allocation_by_report={0.5: 1.0, 0.9: 2.0},
            marginal_margin_per_success=0.6,
            nominal_bond_per_missed_request=1.0,
            collectible_liability_cap=1.0,
            audit_probability=0.0,
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


def test_collateralized_vcg_elicits_joint_private_capacity_and_cost_on_a_finite_grid():
    outside, sentinel = 10.0, 100.0
    offers = [
        CollateralizedCapacityCurveOffer("a", 4, (1.0, 4.0, sentinel, sentinel)),
        CollateralizedCapacityCurveOffer("b", 4, (2.0, 5.0, 6.0, sentinel)),
    ]
    allocation = collateralized_capacity_vcg_allocation(
        offers,
        demand=4,
        outside_option_cost=outside,
        shortfall_sentinel_cost=sentinel,
    )
    assert allocation.to_dict() == {"a": 2, "b": 2}
    assert collateralized_reported_capacity(
        offers[0], outside_option_cost=outside, shortfall_sentinel_cost=sentinel
    ) == 2
    payment = collateralized_capacity_vcg_payment(
        offers,
        provider="a",
        demand=4,
        outside_option_cost=outside,
        shortfall_sentinel_cost=sentinel,
    )
    assert payment == pytest.approx(16.0)
    assert collateralized_capacity_vcg_utility(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 4.0, sentinel, sentinel),
        demand=4,
        outside_option_cost=outside,
        shortfall_sentinel_cost=sentinel,
    ) == pytest.approx(11.0)

    report_grid = [
        tuple(costs) + (sentinel,) * (4 - capacity)
        for capacity in range(5)
        for costs in combinations_with_replacement((0.0, 1.0, 4.0, 7.0), capacity)
    ]
    diagnostic = collateralized_capacity_vcg_report_diagnostic(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 4.0, sentinel, sentinel),
        report_schedules=report_grid,
        demand=4,
        outside_option_cost=outside,
        shortfall_sentinel_cost=sentinel,
    )
    truthful = diagnostic.loc[
        diagnostic["reported_marginal_costs"] == (1.0, 4.0, sentinel, sentinel),
        "utility_at_true_capacity_and_cost",
    ].iat[0]
    assert truthful >= diagnostic["utility_at_true_capacity_and_cost"].max() - 1e-9
    assert truthful >= 0.0
    over = diagnostic.loc[
        diagnostic["reported_marginal_costs"] == (1.0, 4.0, 4.0, sentinel)
    ].iloc[0]
    assert over["defaulted_reserved_units_at_true_capacity"] == 1
    assert over["utility_at_true_capacity_and_cost"] < truthful


def test_collateralized_vcg_rejects_a_nonmonotone_or_costlier_delivery_than_fallback():
    with pytest.raises(ValueError, match="non-decreasing"):
        collateralized_capacity_vcg_allocation(
            [CollateralizedCapacityCurveOffer("a", 3, (1.0, 100.0, 2.0))],
            demand=1,
            outside_option_cost=10.0,
            shortfall_sentinel_cost=100.0,
        )
    with pytest.raises(ValueError, match="below outside"):
        collateralized_capacity_vcg_allocation(
            [CollateralizedCapacityCurveOffer("a", 2, (11.0, 100.0))],
            demand=1,
            outside_option_cost=10.0,
            shortfall_sentinel_cost=100.0,
        )


def test_audited_collateralized_vcg_controls_joint_capacity_cost_and_reliability_reports():
    sentinel = 100.0
    offers = [
        CollateralizedCapacityCurveOffer("a", 4, (1.0, 6.0, sentinel, sentinel)),
        CollateralizedCapacityCurveOffer("b", 4, (3.0, 5.0, 9.0, sentinel)),
    ]
    low = collateralized_capacity_reliability_allocation(
        offers,
        reported_reliability={"a": 0.3, "b": 0.5},
        demand=3,
        value_per_success=10.0,
        shortfall_sentinel_cost=sentinel,
    )
    high = collateralized_capacity_reliability_allocation(
        offers,
        reported_reliability={"a": 0.8, "b": 0.5},
        demand=3,
        value_per_success=10.0,
        shortfall_sentinel_cost=sentinel,
    )
    assert low.to_dict() == {"a": 1, "b": 1}
    assert high.to_dict() == {"a": 2, "b": 1}

    scale = collateralized_capacity_reliability_minimum_score_scale(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 6.0, sentinel, sentinel),
        reliability_grid=(0.3, 0.8),
        other_reported_reliability={"b": 0.5},
        demand=3,
        value_per_success=10.0,
        shortfall_sentinel_cost=sentinel,
        audit_probability=0.2,
        strict_advantage=1e-5,
    )
    report_grid = [
        tuple(costs) + (sentinel,) * (4 - capacity)
        for capacity in range(5)
        for costs in combinations_with_replacement((0.0, 1.0, 3.0, 6.0, 9.0), capacity)
    ]
    diagnostic = collateralized_capacity_reliability_product_report_diagnostic(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 6.0, sentinel, sentinel),
        capacity_cost_report_schedules=report_grid,
        reliability_grid=(0.3, 0.8),
        other_reported_reliability={"b": 0.5},
        demand=3,
        value_per_success=10.0,
        shortfall_sentinel_cost=sentinel,
        audit_probability=0.2,
        audit_score_scale=scale,
    )
    assert (diagnostic["truthful_joint_payoff_advantage"] >= -1e-9).all()
    off_grid = diagnostic.loc[
        (diagnostic["reported_marginal_costs"] == (1.0, 6.0, sentinel, sentinel))
        & (diagnostic["true_reliability"] != diagnostic["reported_reliability"])
    ]
    assert (off_grid["truthful_joint_payoff_advantage"] > 0).all()
    over = diagnostic.loc[
        (diagnostic["true_reliability"] == 0.8)
        & (diagnostic["reported_reliability"] == 0.8)
        & (diagnostic["reported_marginal_costs"] == (1.0, 6.0, 6.0, sentinel))
    ].iloc[0]
    assert over["defaulted_reserved_units_at_true_capacity"] == 1
    assert over["truthful_joint_payoff_advantage"] > 0


def test_audited_vcg_synthesis_controls_joint_finite_grid_cost_and_reliability_reports():
    offers = [
        CertifiedCostCurveOffer("a", certified_capacity=2, reported_marginal_costs=(1.0, 6.0)),
        CertifiedCostCurveOffer("b", certified_capacity=2, reported_marginal_costs=(3.0, 5.0)),
    ]
    low = certified_reliability_cost_allocation(
        offers,
        reported_reliability={"a": 0.3, "b": 0.5},
        demand=2,
        value_per_success=10.0,
    )
    high = certified_reliability_cost_allocation(
        offers,
        reported_reliability={"a": 0.8, "b": 0.5},
        demand=2,
        value_per_success=10.0,
    )
    assert low.to_dict() == {"a": 1, "b": 1}
    assert high.to_dict() == {"a": 2, "b": 0}

    scale = certified_audited_vcg_minimum_score_scale(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 6.0),
        reliability_grid=(0.3, 0.8),
        other_reported_reliability={"b": 0.5},
        demand=2,
        value_per_success=10.0,
        audit_probability=0.2,
        strict_advantage=1e-5,
    )
    diagnostic = certified_audited_vcg_product_report_diagnostic(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 6.0),
        cost_report_schedules=[(0.0, 0.0), (1.0, 6.0), (9.0, 10.0)],
        reliability_grid=(0.3, 0.8),
        other_reported_reliability={"b": 0.5},
        demand=2,
        value_per_success=10.0,
        audit_probability=0.2,
        audit_score_scale=scale,
    )
    assert (diagnostic["truthful_joint_payoff_advantage"] >= -1e-9).all()
    off_grid = diagnostic.loc[
        (diagnostic["reported_marginal_costs"] == (1.0, 6.0))
        & (diagnostic["true_reliability"] != diagnostic["reported_reliability"])
    ]
    assert (off_grid["truthful_joint_payoff_advantage"] > 0).all()


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
