"""Minimal capacity-certified routing mechanism used by H48.

The model is deliberately small enough for empirical calibration. Providers
post a unit quote and a capacity commitment; the router allocates first-route
probability using reliability-weighted inverse-price scores. A capacity bond
is a deferred payment/forfeit for committed but unserved allocation.  It is a
mechanism-design proposal, not a claim about any existing router's policy.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def own_price_share_elasticity(share: float, eta: float = 2.0) -> float:
    """d log(router share) / d log(own price) for the allocation rule."""
    if not 0 <= share <= 1:
        raise ValueError("share must lie in [0, 1]")
    return -eta * (1.0 - share)


def capacity_bond_floor(marginal_margin_per_request: float) -> float:
    """Smallest per-missed-request forfeit that deters deliberate shortfall.

    With payment only for served requests, accepting a request and deliberately
    rationing can save at most the provider's positive marginal margin under
    this reduced form. A strictly larger bond makes that deviation dominated.
    """
    return max(0.0, marginal_margin_per_request)


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
    served = min(allocated_requests, served_requests)
    shortfall = max(0.0, allocated_requests - served)
    return (offer.price - offer.marginal_cost) * served - bond_per_missed_request * shortfall


def capacity_feasible(offer: ProviderOffer, allocated_requests: float) -> bool:
    """Whether the commitment covers the router's allocated request quantity."""
    return allocated_requests <= offer.committed_capacity
