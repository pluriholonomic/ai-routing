"""Minimal capacity-certified routing mechanism used by H48.

The model is deliberately small enough for empirical calibration. Providers
post a unit quote and a capacity commitment; the router allocates first-route
probability using reliability-weighted inverse-price scores. A capacity bond
is a deferred payment/forfeit for committed but unserved allocation.  It is a
mechanism-design proposal, not a claim about any existing router's policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd


@dataclass(frozen=True)
class ProviderOffer:
    provider: str
    price: float
    reliability: float
    committed_capacity: float
    marginal_cost: float


def allocation_shares(offers: list[ProviderOffer], eta: float = 2.0) -> pd.Series:
    """Reliability-weighted inverse-price first-route shares.

    The result is conditional on a provider being eligible and therefore does
    not reproduce private health filtering or realized allocation.
    """
    if eta <= 0:
        raise ValueError("eta must be positive")
    weights = {
        offer.provider: max(0.0, offer.reliability) * offer.price ** (-eta)
        for offer in offers
        if offer.price > 0
    }
    total = sum(weights.values())
    if total <= 0:
        return pd.Series(dtype="float64")
    return pd.Series({provider: weight / total for provider, weight in weights.items()})


def capacity_constrained_allocation(
    offers: list[ProviderOffer], demand: float, eta: float = 2.0
) -> pd.Series:
    """Allocate demand by score while never exceeding certified capacity.

    Let ``w_i = q_i p_i^{-eta}``.  When total usable commitment covers demand,
    this is the unique capped water-fill ``x_i = min(k_i, tau w_i)`` whose
    allocations sum to demand. Equivalently, it is the entropy-regularized
    score allocation subject to ``x_i <= k_i``. If commitments are jointly
    insufficient, it allocates every feasible unit and leaves residual demand
    explicit rather than manufacturing a route assignment.
    """
    if demand < 0:
        raise ValueError("demand must be non-negative")
    if eta <= 0:
        raise ValueError("eta must be positive")
    if len({offer.provider for offer in offers}) != len(offers):
        raise ValueError("provider names must be unique")
    capacities = {
        offer.provider: max(0.0, offer.committed_capacity)
        for offer in offers
        if offer.price > 0 and offer.reliability > 0
    }
    weights = {
        offer.provider: offer.reliability * offer.price ** (-eta)
        for offer in offers
        if offer.provider in capacities and capacities[offer.provider] > 0
    }
    allocation = {provider: 0.0 for provider in capacities}
    remaining = min(float(demand), sum(capacities.values()))
    active = set(weights)
    while remaining > 0 and active:
        total_weight = sum(weights[provider] for provider in active)
        if total_weight <= 0:
            break
        proposal = {
            provider: remaining * weights[provider] / total_weight for provider in active
        }
        saturated = [
            provider
            for provider, quantity in proposal.items()
            if quantity >= capacities[provider] - allocation[provider]
        ]
        if not saturated:
            for provider, quantity in proposal.items():
                allocation[provider] += quantity
            remaining = 0.0
            break
        for provider in saturated:
            residual_capacity = capacities[provider] - allocation[provider]
            allocation[provider] += residual_capacity
            remaining -= residual_capacity
            active.remove(provider)
    return pd.Series(allocation, dtype="float64")


def allocation_counterfactual(
    offers: list[ProviderOffer], demand: float, eta: float = 2.0
) -> pd.DataFrame:
    """Compare uncapped score allocation with its capacity-certified form.

    ``uncapped_capacity_shortfall`` is a mechanical commitment mismatch, not a
    realized failure probability. It exposes the telemetry primitive needed to
    translate the theory into welfare or bond estimates.
    """
    if demand < 0:
        raise ValueError("demand must be non-negative")
    uncapped = allocation_shares(offers, eta) * demand
    capped = capacity_constrained_allocation(offers, demand, eta)
    commitment = pd.Series(
        {offer.provider: max(0.0, offer.committed_capacity) for offer in offers}, dtype="float64"
    )
    providers = uncapped.index.union(capped.index).union(commitment.index)
    result = pd.DataFrame(index=providers)
    result["uncapped_allocated"] = uncapped.reindex(providers, fill_value=0.0)
    result["committed_capacity"] = commitment.reindex(providers, fill_value=0.0)
    result["uncapped_capacity_shortfall"] = (
        result["uncapped_allocated"] - result["committed_capacity"]
    ).clip(lower=0.0)
    result["uncapped_delivered_under_commitment"] = result[
        ["uncapped_allocated", "committed_capacity"]
    ].min(axis=1)
    result["capacity_certified_allocated"] = capped.reindex(providers, fill_value=0.0)
    result["capacity_certified_delivery_gain"] = (
        result["capacity_certified_allocated"] - result["uncapped_delivered_under_commitment"]
    )
    result["uncapped_unserved_demand"] = max(
        0.0, demand - float(result["uncapped_delivered_under_commitment"].sum())
    )
    result["capacity_certified_unfilled_demand"] = max(
        0.0, demand - float(result["capacity_certified_allocated"].sum())
    )
    return result.reset_index(names="provider")


def own_price_share_elasticity(share: float, eta: float = 2.0) -> float:
    """d log(router share) / d log(own price) for the allocation rule."""
    if not 0 <= share <= 1:
        raise ValueError("share must lie in [0, 1]")
    return -eta * (1.0 - share)


def capacity_bond_floor(marginal_margin_per_request: float) -> float:
    """Non-negative threshold for a per-missed-request shortfall bond.

    Let the margin from serving a feasible assigned request be ``m = p - c``.
    Serving instead of deliberately rationing changes payoff by ``m + b``.
    The exact strict condition is ``b > -m``. Restricting bonds to be
    non-negative gives the convenient sufficient rule ``b > max(0, -m)``;
    when ``m > 0``, a zero bond already strictly deters rationing. The returned
    threshold uses a strict inequality and does not itself choose an epsilon.
    """
    if not isfinite(marginal_margin_per_request):
        raise ValueError("marginal margin must be finite")
    return max(0.0, -marginal_margin_per_request)


def realized_provider_payoff(
    offer: ProviderOffer,
    *,
    allocated_requests: float,
    served_requests: float,
    bond_per_missed_request: float,
) -> float:
    """Provider payoff under delivery payment plus an ex-post shortfall bond."""
    if allocated_requests < 0 or served_requests < 0:
        raise ValueError("request counts must be non-negative")
    if bond_per_missed_request < 0:
        raise ValueError("bond_per_missed_request must be non-negative")
    served = min(allocated_requests, served_requests)
    shortfall = max(0.0, allocated_requests - served)
    return (offer.price - offer.marginal_cost) * served - bond_per_missed_request * shortfall


def declared_capacity_payoff(
    offers: list[ProviderOffer],
    *,
    provider: str,
    actual_capacity: float,
    reported_capacity: float,
    demand: float,
    bond_per_missed_request: float,
    eta: float = 2.0,
) -> float:
    """Payoff from a capacity report when physical capacity is lower or equal.

    This is a counterfactual diagnostic for the hard-capacity reduced form:
    the report changes water-fill allocation, but delivery cannot exceed
    ``actual_capacity``. It does not model capacity acquisition, side payments,
    stochastic outages, or a provider's ability to manipulate reliability.
    """
    if actual_capacity < 0 or reported_capacity < 0:
        raise ValueError("actual and reported capacity must be non-negative")
    if bond_per_missed_request < 0:
        raise ValueError("bond_per_missed_request must be non-negative")
    by_provider = {offer.provider: offer for offer in offers}
    if provider not in by_provider:
        raise ValueError(f"unknown provider: {provider}")
    reported_offers = [
        (
            ProviderOffer(
                provider=offer.provider,
                price=offer.price,
                reliability=offer.reliability,
                committed_capacity=reported_capacity,
                marginal_cost=offer.marginal_cost,
            )
            if offer.provider == provider
            else offer
        )
        for offer in offers
    ]
    allocation = capacity_constrained_allocation(reported_offers, demand, eta)
    allocated = float(allocation.get(provider, 0))
    return realized_provider_payoff(
        by_provider[provider],
        allocated_requests=allocated,
        served_requests=min(allocated, actual_capacity),
        bond_per_missed_request=bond_per_missed_request,
    )


def reported_cost_allocation(
    offers: list[ProviderOffer],
    *,
    provider: str,
    reported_cost: float,
    demand: float,
    eta: float = 2.0,
) -> float:
    """Allocation to one provider after a direct marginal-cost report.

    This is an alternative procurement menu, not an interpretation of a
    router's public posted price. It holds hard committed capacity and the
    pre-allocation reliability score fixed, replacing only the reporting
    provider's score input by its positive marginal-cost report.
    """
    if not isfinite(reported_cost) or reported_cost <= 0:
        raise ValueError("reported_cost must be finite and positive")
    if provider not in {offer.provider for offer in offers}:
        raise ValueError(f"unknown provider: {provider}")
    reported_offers = [
        (
            ProviderOffer(
                provider=offer.provider,
                price=reported_cost,
                reliability=offer.reliability,
                committed_capacity=offer.committed_capacity,
                marginal_cost=offer.marginal_cost,
            )
            if offer.provider == provider
            else offer
        )
        for offer in offers
    ]
    return float(capacity_constrained_allocation(reported_offers, demand, eta).get(provider, 0.0))


def procurement_payment(
    offers: list[ProviderOffer],
    *,
    provider: str,
    reported_cost: float,
    demand: float,
    cost_upper_bound: float,
    eta: float = 2.0,
    quadrature_steps: int = 512,
) -> float:
    """Envelope payment for a cost-only, capacity-fixed direct menu.

    With allocation ``x_i(r)`` weakly decreasing in provider ``i``'s reported
    marginal cost ``r``, the procurement payment

    ``T_i(r) = r x_i(r) + integral_r^cbar x_i(z) dz``

    implements truthful cost reporting and gives zero utility to the upper
    cost type. The integral is a deterministic trapezoid approximation used
    for counterfactuals; the theorem is the exact envelope formula. This does
    not impose budget balance or solve private capacity reporting.
    """
    if not isfinite(cost_upper_bound) or cost_upper_bound <= 0:
        raise ValueError("cost_upper_bound must be finite and positive")
    if reported_cost > cost_upper_bound:
        raise ValueError("reported_cost cannot exceed cost_upper_bound")
    if not isinstance(quadrature_steps, int) or quadrature_steps < 1:
        raise ValueError("quadrature_steps must be a positive integer")
    allocation = reported_cost_allocation(
        offers,
        provider=provider,
        reported_cost=reported_cost,
        demand=demand,
        eta=eta,
    )
    if reported_cost == cost_upper_bound:
        return reported_cost * allocation
    step = (cost_upper_bound - reported_cost) / quadrature_steps
    previous = allocation
    integral = 0.0
    for index in range(1, quadrature_steps + 1):
        report = reported_cost + index * step
        current = reported_cost_allocation(
            offers,
            provider=provider,
            reported_cost=report,
            demand=demand,
            eta=eta,
        )
        integral += (previous + current) * step / 2
        previous = current
    return reported_cost * allocation + integral


def procurement_utility(
    offers: list[ProviderOffer],
    *,
    provider: str,
    true_cost: float,
    reported_cost: float,
    demand: float,
    cost_upper_bound: float,
    eta: float = 2.0,
    quadrature_steps: int = 512,
) -> float:
    """Expected utility from a cost report when assigned demand is delivered.

    Delivery is assumed feasible because capacity is fixed and hard in this
    result. The shortfall bond remains the separate ex-post delivery device.
    """
    if not isfinite(true_cost) or true_cost <= 0 or true_cost > cost_upper_bound:
        raise ValueError("true_cost must lie in (0, cost_upper_bound]")
    allocation = reported_cost_allocation(
        offers,
        provider=provider,
        reported_cost=reported_cost,
        demand=demand,
        eta=eta,
    )
    payment = procurement_payment(
        offers,
        provider=provider,
        reported_cost=reported_cost,
        demand=demand,
        cost_upper_bound=cost_upper_bound,
        eta=eta,
        quadrature_steps=quadrature_steps,
    )
    return payment - true_cost * allocation


def procurement_report_diagnostic(
    offers: list[ProviderOffer],
    *,
    provider: str,
    true_cost: float,
    report_grid: list[float],
    demand: float,
    cost_upper_bound: float,
    eta: float = 2.0,
    quadrature_steps: int = 512,
) -> pd.DataFrame:
    """Audit monotonic allocation and the direct-menu incentive numerically."""
    if not isfinite(true_cost) or true_cost <= 0 or true_cost > cost_upper_bound:
        raise ValueError("true_cost must lie in (0, cost_upper_bound]")
    rows = []
    for reported_cost in report_grid:
        allocation = reported_cost_allocation(
            offers,
            provider=provider,
            reported_cost=reported_cost,
            demand=demand,
            eta=eta,
        )
        payment = procurement_payment(
            offers,
            provider=provider,
            reported_cost=reported_cost,
            demand=demand,
            cost_upper_bound=cost_upper_bound,
            eta=eta,
            quadrature_steps=quadrature_steps,
        )
        rows.append(
            {
                "reported_cost": reported_cost,
                "allocated_requests": allocation,
                "payment": payment,
                "utility_at_true_cost": payment - true_cost * allocation,
            }
        )
    return pd.DataFrame(rows)


def capacity_feasible(offer: ProviderOffer, allocated_requests: float) -> bool:
    """Whether the commitment covers the router's allocated request quantity."""
    return allocated_requests <= offer.committed_capacity
