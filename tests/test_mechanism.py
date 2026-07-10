import math

from orcap.mechanism import (
    ProviderOffer,
    allocation_counterfactual,
    allocation_shares,
    capacity_bond_floor,
    capacity_constrained_allocation,
    declared_capacity_payoff,
    own_price_share_elasticity,
    realized_provider_payoff,
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
