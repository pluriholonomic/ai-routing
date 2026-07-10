import math

from orcap.mechanism import (
    OutageScenario,
    ProviderOffer,
    allocation_counterfactual,
    allocation_shares,
    capacity_bond_floor,
    capacity_constrained_allocation,
    declared_capacity_payoff,
    expected_delivered_under_outage_scenarios,
    limited_liability_delivery_gain,
    own_price_share_elasticity,
    procurement_payment,
    procurement_report_diagnostic,
    procurement_utility,
    realized_provider_payoff,
    reported_cost_allocation,
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
