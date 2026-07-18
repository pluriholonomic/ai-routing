"""Analytical benchmarks for inverse-power provider routing.

Consider n providers with identical marginal cost c, fixed unit demand, and
first-route share

    s_i(p) = p_i^(-eta) / sum_j p_j^(-eta).

Provider i maximizes (p_i - c) s_i.  These helpers encode the finite symmetric
interior first-order condition.  They do not claim uniqueness of every
asymmetric or boundary equilibrium in richer games.
"""

from __future__ import annotations

from math import isfinite


def symmetric_interior_price(
    *,
    providers: int,
    exponent: float,
    marginal_cost: float,
) -> float | None:
    """Return the finite symmetric interior stationary price, if it exists.

    The first-order condition gives

        p* = eta (n - 1) c / (eta (n - 1) - n).

    A positive finite solution requires eta > n / (n - 1).  At or below the
    boundary there is no finite symmetric interior stationary point.
    """
    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 2:
        raise ValueError("providers must be an integer of at least two")
    if not isfinite(float(exponent)) or float(exponent) <= 0:
        raise ValueError("exponent must be finite and strictly positive")
    if not isfinite(float(marginal_cost)) or float(marginal_cost) <= 0:
        raise ValueError("marginal_cost must be finite and strictly positive")
    denominator = exponent * (providers - 1) - providers
    if denominator <= 0:
        return None
    return exponent * (providers - 1) * marginal_cost / denominator


def symmetric_profit_gradient(
    *,
    providers: int,
    exponent: float,
    marginal_cost: float,
    common_price: float,
    demand: float = 1.0,
) -> float:
    """Derivative of one provider's profit at a symmetric price profile."""
    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 2:
        raise ValueError("providers must be an integer of at least two")
    for name, value in [
        ("exponent", exponent),
        ("marginal_cost", marginal_cost),
        ("common_price", common_price),
        ("demand", demand),
    ]:
        if not isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{name} must be finite and strictly positive")
    share = 1.0 / providers
    share_gradient = -exponent * share * (1.0 - share) / common_price
    return demand * (share + (common_price - marginal_cost) * share_gradient)


def unilateral_profit(
    *,
    own_price: float,
    rival_prices: tuple[float, ...],
    exponent: float,
    marginal_cost: float,
    demand: float = 1.0,
) -> float:
    """Profit for a unilateral price against fixed rival prices."""
    values = [own_price, *rival_prices, exponent, marginal_cost, demand]
    if any(not isfinite(float(value)) or float(value) <= 0 for value in values):
        raise ValueError("prices, exponent, cost, and demand must be positive and finite")
    own_weight = own_price ** (-exponent)
    total_weight = own_weight + sum(price ** (-exponent) for price in rival_prices)
    return demand * (own_price - marginal_cost) * own_weight / total_weight


def symmetric_elastic_price(
    *,
    providers: int,
    exponent: float,
    demand_elasticity: float,
    marginal_cost: float,
    price_cap: float | None = None,
) -> float | None:
    """Symmetric price with isoelastic demand for expected routed price.

    The symmetric markup fraction is

        (p-c)/p = n / [eta(n-1) + epsilon].

    A finite unconstrained price requires eta(n-1)+epsilon > n.
    """
    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 2:
        raise ValueError("providers must be an integer of at least two")
    for name, value in [
        ("exponent", exponent),
        ("demand_elasticity", demand_elasticity),
        ("marginal_cost", marginal_cost),
    ]:
        if not isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{name} must be finite and strictly positive")
    if price_cap is not None and (
        not isfinite(float(price_cap)) or float(price_cap) < marginal_cost
    ):
        raise ValueError("price_cap must be finite and at least marginal_cost")
    effective_elasticity = exponent * (providers - 1) + demand_elasticity
    denominator = effective_elasticity - providers
    if denominator <= 0:
        return float(price_cap) if price_cap is not None else None
    price = marginal_cost * effective_elasticity / denominator
    return min(price, float(price_cap)) if price_cap is not None else price


def isoelastic_quantity(
    price: float,
    *,
    demand_elasticity: float,
    demand_scale: float = 1.0,
) -> float:
    """Quantity A p^-epsilon."""
    for name, value in [
        ("price", price),
        ("demand_elasticity", demand_elasticity),
        ("demand_scale", demand_scale),
    ]:
        if not isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{name} must be finite and strictly positive")
    return demand_scale * price ** (-demand_elasticity)


def isoelastic_welfare(
    price: float,
    *,
    marginal_cost: float,
    demand_elasticity: float,
    demand_scale: float = 1.0,
) -> float:
    """Gross surplus less real cost under isoelastic inverse demand.

    Finite gross surplus requires epsilon > 1.
    """
    if demand_elasticity <= 1:
        raise ValueError("demand_elasticity must exceed one for finite welfare")
    quantity = isoelastic_quantity(
        price,
        demand_elasticity=demand_elasticity,
        demand_scale=demand_scale,
    )
    return (
        demand_elasticity / (demand_elasticity - 1) * price - marginal_cost
    ) * quantity


def unilateral_elastic_profit(
    *,
    own_price: float,
    rival_prices: tuple[float, ...],
    exponent: float,
    marginal_cost: float,
    demand_elasticity: float,
    demand_scale: float = 1.0,
) -> float:
    """Provider profit when demand depends on expected routed price."""
    values = [
        own_price,
        *rival_prices,
        exponent,
        marginal_cost,
        demand_elasticity,
        demand_scale,
    ]
    if any(not isfinite(float(value)) or float(value) <= 0 for value in values):
        raise ValueError("all inputs must be positive and finite")
    prices = (own_price, *rival_prices)
    weights = tuple(price ** (-exponent) for price in prices)
    total_weight = sum(weights)
    shares = tuple(weight / total_weight for weight in weights)
    expected_price = sum(price * share for price, share in zip(prices, shares, strict=True))
    quantity = isoelastic_quantity(
        expected_price,
        demand_elasticity=demand_elasticity,
        demand_scale=demand_scale,
    )
    return (own_price - marginal_cost) * shares[0] * quantity
