"""Costly entry and contestable-demand benchmarks for inference routing.

The helpers in this module deliberately separate four objects:

``n_free_entry``
    Providers whose public and bilateral operating profit covers market-entry
    and capacity cost.
``k_adaptive``
    Entered providers for whom adaptive pricing covers its own fixed cost.
``k_learnable``
    Provider-specific price effects that can be resolved at a declared signal,
    horizon, and accuracy.
``n_welfare``
    Providers whose incremental reliability value covers real entry and retry
    costs.

None of these functions estimates those objects from public OpenRouter data.
They are analytical benchmarks used by the venue papers and simulations.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .theory import symmetric_interior_price


def _positive(name: str, value: float, *, allow_zero: bool = False) -> float:
    result = float(value)
    valid = result >= 0 if allow_zero else result > 0
    if not math.isfinite(result) or not valid:
        qualifier = "nonnegative" if allow_zero else "strictly positive"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def symmetric_price_with_cap(
    *,
    providers: int,
    exponent: float,
    marginal_cost: float,
    price_cap: float,
) -> float:
    """Return the symmetric price benchmark with a finite menu cap.

    A monopoly and profiles without a finite interior stationary price bind the
    cap.  This is a bounded benchmark, not a uniqueness claim for every
    boundary equilibrium.
    """

    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 1:
        raise ValueError("providers must be a positive integer")
    eta = _positive("exponent", exponent)
    cost = _positive("marginal_cost", marginal_cost)
    cap = _positive("price_cap", price_cap)
    if cap < cost:
        raise ValueError("price_cap must be at least marginal_cost")
    if providers == 1:
        return cap
    interior = symmetric_interior_price(
        providers=providers,
        exponent=eta,
        marginal_cost=cost,
    )
    return cap if interior is None else min(float(interior), cap)


def symmetric_public_operating_profit(
    *,
    providers: int,
    exponent: float,
    marginal_cost: float,
    public_demand: float,
    price_cap: float,
    availability: float = 1.0,
) -> float:
    """Per-provider public operating profit before fixed entry cost.

    With availability below one, serial fallback delivers probability
    ``1-(1-rho)^n`` and symmetry assigns an equal fraction of delivered jobs to
    every provider.
    """

    demand = _positive("public_demand", public_demand)
    rho = _positive("availability", availability)
    if rho > 1:
        raise ValueError("availability must not exceed one")
    price = symmetric_price_with_cap(
        providers=providers,
        exponent=exponent,
        marginal_cost=marginal_cost,
        price_cap=price_cap,
    )
    delivered = delivered_probability(providers, rho)
    return demand * delivered * (price - float(marginal_cost)) / providers


def interior_public_profit_closed_form(
    *, providers: int, exponent: float, marginal_cost: float, public_demand: float
) -> float:
    """Closed-form public profit at a finite interior symmetric equilibrium."""

    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 2:
        raise ValueError("providers must be an integer of at least two")
    eta = _positive("exponent", exponent)
    cost = _positive("marginal_cost", marginal_cost)
    demand = _positive("public_demand", public_demand)
    denominator = eta * (providers - 1) - providers
    if denominator <= 0:
        raise ValueError("finite interior symmetric price does not exist")
    return demand * cost / denominator


def delivered_probability(providers: int, availability: float) -> float:
    """Probability that at least one of ``providers`` independent attempts works."""

    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 0:
        raise ValueError("providers must be a nonnegative integer")
    rho = _positive("availability", availability)
    if rho > 1:
        raise ValueError("availability must not exceed one")
    return float(1.0 - (1.0 - rho) ** providers)


def expected_serial_attempts(providers: int, availability: float) -> float:
    """Expected attempts under independent serial fallback with a finite menu."""

    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 0:
        raise ValueError("providers must be a nonnegative integer")
    rho = _positive("availability", availability)
    if rho > 1:
        raise ValueError("availability must not exceed one")
    if providers == 0:
        return 0.0
    return delivered_probability(providers, rho) / rho


def entry_welfare(
    providers: int,
    *,
    demand: float,
    delivered_value_minus_cost: float,
    availability: float,
    fixed_entry_cost: float,
    failed_attempt_cost: float = 0.0,
) -> float:
    """Real surplus from redundancy net of entry and failed-attempt costs."""

    volume = _positive("demand", demand)
    surplus = _positive("delivered_value_minus_cost", delivered_value_minus_cost)
    fixed = _positive("fixed_entry_cost", fixed_entry_cost, allow_zero=True)
    retry = _positive("failed_attempt_cost", failed_attempt_cost, allow_zero=True)
    success = delivered_probability(providers, availability)
    attempts = expected_serial_attempts(providers, availability)
    failed_attempts = attempts - success
    return volume * (surplus * success - retry * failed_attempts) - providers * fixed


def welfare_entry_count(
    *,
    max_providers: int,
    demand: float,
    delivered_value_minus_cost: float,
    availability: float,
    fixed_entry_cost: float,
    failed_attempt_cost: float = 0.0,
) -> int:
    """Return the largest welfare-maximizing integer provider count."""

    if not isinstance(max_providers, int) or isinstance(max_providers, bool) or max_providers < 0:
        raise ValueError("max_providers must be a nonnegative integer")
    values = [
        entry_welfare(
            providers,
            demand=demand,
            delivered_value_minus_cost=delivered_value_minus_cost,
            availability=availability,
            fixed_entry_cost=fixed_entry_cost,
            failed_attempt_cost=failed_attempt_cost,
        )
        for providers in range(max_providers + 1)
    ]
    maximum = max(values)
    return max(index for index, value in enumerate(values) if math.isclose(value, maximum))


def free_entry_count(
    *,
    max_providers: int,
    exponent: float,
    marginal_cost: float,
    public_demand: float,
    price_cap: float,
    fixed_entry_cost: float,
    bilateral_profit: float = 0.0,
    adaptive_cost: float = 0.0,
    availability: float = 1.0,
) -> int:
    """Largest count whose symmetric per-provider payoff covers fixed costs."""

    if not isinstance(max_providers, int) or isinstance(max_providers, bool) or max_providers < 1:
        raise ValueError("max_providers must be a positive integer")
    fixed = _positive("fixed_entry_cost", fixed_entry_cost, allow_zero=True)
    bilateral = _positive("bilateral_profit", bilateral_profit, allow_zero=True)
    adaptation = _positive("adaptive_cost", adaptive_cost, allow_zero=True)
    profitable: list[int] = []
    for providers in range(1, max_providers + 1):
        public = symmetric_public_operating_profit(
            providers=providers,
            exponent=exponent,
            marginal_cost=marginal_cost,
            public_demand=public_demand,
            price_cap=price_cap,
            availability=availability,
        )
        if public + bilateral - fixed - adaptation >= -1e-12:
            profitable.append(providers)
    return max(profitable, default=0)


def pigouvian_entry_charge(
    providers_before_entry: int,
    *,
    entrant_private_operating_profit: float,
    demand: float,
    delivered_value_minus_cost: float,
    availability: float,
    fixed_entry_cost: float,
    failed_attempt_cost: float = 0.0,
) -> float:
    """Charge that aligns entrant net payoff with marginal social surplus.

    Positive output is a fee; negative output is a subsidy or capacity credit.
    The entrant's fixed cost is included in both the private and social entry
    decisions and therefore in the marginal-surplus calculation.
    """

    if providers_before_entry < 0:
        raise ValueError("providers_before_entry must be nonnegative")
    private = float(entrant_private_operating_profit) - float(fixed_entry_cost)
    before = entry_welfare(
        providers_before_entry,
        demand=demand,
        delivered_value_minus_cost=delivered_value_minus_cost,
        availability=availability,
        fixed_entry_cost=fixed_entry_cost,
        failed_attempt_cost=failed_attempt_cost,
    )
    after = entry_welfare(
        providers_before_entry + 1,
        demand=demand,
        delivered_value_minus_cost=delivered_value_minus_cost,
        availability=availability,
        fixed_entry_cost=fixed_entry_cost,
        failed_attempt_cost=failed_attempt_cost,
    )
    marginal_social = after - before
    return float(private - marginal_social)


def group_elasticity(
    group_share: float, *, exponent: float, score_log_price_slope: float = 0.0
) -> float:
    """Positive magnitude of common group log-price elasticity."""

    share = float(group_share)
    if not math.isfinite(share) or not 0 <= share <= 1:
        raise ValueError("group_share must lie in [0, 1]")
    eta = _positive("exponent", exponent)
    slope = float(score_log_price_slope)
    if not math.isfinite(slope) or eta - slope < 0:
        raise ValueError("effective exponent must be finite and nonnegative")
    return (eta - slope) * (1.0 - share)


def group_cut_gradients(
    group_share: float,
    *,
    exponent: float,
    price: float,
    marginal_cost: float,
    capacity_shadow_cost: float = 0.0,
    score_log_price_slope: float = 0.0,
) -> dict[str, float]:
    """Local revenue and profit gradients for a common proportional cut."""

    quote = _positive("price", price)
    cost = _positive("marginal_cost", marginal_cost, allow_zero=True)
    scarcity = _positive("capacity_shadow_cost", capacity_shadow_cost, allow_zero=True)
    margin = quote - cost - scarcity
    if margin <= 0:
        raise ValueError("price must exceed marginal plus capacity shadow cost")
    elasticity = group_elasticity(
        group_share,
        exponent=exponent,
        score_log_price_slope=score_log_price_slope,
    )
    return {
        "group_elasticity": elasticity,
        "log_revenue_cut_gradient": elasticity - 1.0,
        "log_profit_cut_gradient": elasticity - quote / margin,
    }


def omitted_rival_price_coefficient(
    shares: Sequence[float],
    price_experiment_covariance: Sequence[Sequence[float]],
    *,
    focal: int,
    exponent: float,
) -> dict[str, float]:
    """Population own-price slope when rival price experiments are omitted."""

    share = np.asarray(shares, dtype=float)
    covariance = np.asarray(price_experiment_covariance, dtype=float)
    if share.ndim != 1 or len(share) < 2 or np.any(share < 0) or not np.isclose(share.sum(), 1):
        raise ValueError("shares must be a probability vector with at least two entries")
    if covariance.shape != (len(share), len(share)) or not np.allclose(
        covariance, covariance.T
    ):
        raise ValueError("covariance must be symmetric and match shares")
    if np.linalg.eigvalsh(covariance).min() < -1e-10:
        raise ValueError("covariance must be positive semidefinite")
    if not 0 <= focal < len(share):
        raise ValueError("focal index is invalid")
    own_variance = float(covariance[focal, focal])
    if own_variance <= 0:
        raise ValueError("focal experiment variance must be positive")
    eta = _positive("exponent", exponent)
    omitted = eta * sum(
        float(share[j] * covariance[focal, j] / own_variance)
        for j in range(len(share))
        if j != focal
    )
    structural_slope = -eta * (1.0 - float(share[focal]))
    observed_slope = structural_slope + omitted
    return {
        "structural_log_share_slope": structural_slope,
        "omitted_rival_term": omitted,
        "own_only_log_share_slope": observed_slope,
        "own_only_elasticity_magnitude": -observed_slope,
    }


def required_learning_horizon(
    *,
    reward_noise_variance: float,
    conditional_experiment_variance: float,
    target_error: float,
    actions: int,
    error_probability: float,
    constant: float = 2.0,
) -> int:
    """A declared concentration-style horizon for a provider-specific slope."""

    noise = _positive("reward_noise_variance", reward_noise_variance)
    variation = _positive("conditional_experiment_variance", conditional_experiment_variance)
    error = _positive("target_error", target_error)
    factor = _positive("constant", constant)
    if not isinstance(actions, int) or isinstance(actions, bool) or actions < 2:
        raise ValueError("actions must be an integer of at least two")
    delta = float(error_probability)
    if not math.isfinite(delta) or not 0 < delta < 1:
        raise ValueError("error_probability must lie in (0, 1)")
    raw = factor * noise / (error**2 * variation) * math.log(actions / delta)
    return int(math.ceil(raw))


def adaptive_count_reduced_form(
    *,
    providers: int,
    signal_rank: float,
    gross_benefit: float,
    contestable_share: float,
    fixed_adaptation_cost: float,
    congestion_cost: float,
    congestion_exponent: float,
) -> float:
    """Conditional continuous adaptive count from the amended reduced form.

    This helper validates a corollary only.  It does not provide the primitive
    derivation required before the power law can enter the EC paper.
    """

    if not isinstance(providers, int) or isinstance(providers, bool) or providers < 1:
        raise ValueError("providers must be a positive integer")
    rank = _positive("signal_rank", signal_rank)
    if rank > providers:
        raise ValueError("signal_rank cannot exceed providers")
    benefit = _positive("gross_benefit", gross_benefit)
    contestable = float(contestable_share)
    if not math.isfinite(contestable) or not 0 <= contestable <= 1:
        raise ValueError("contestable_share must lie in [0, 1]")
    fixed = _positive("fixed_adaptation_cost", fixed_adaptation_cost, allow_zero=True)
    cost = _positive("congestion_cost", congestion_cost)
    gamma = _positive("congestion_exponent", congestion_exponent)
    net = benefit * contestable - fixed
    if net <= 0:
        return 0.0
    raw = (
        net * providers * rank**gamma / (cost * (2.0 + gamma))
    ) ** (1.0 / (1.0 + gamma))
    return float(min(providers, raw))


@dataclass(frozen=True)
class EntryComparison:
    """A transparent free-entry versus welfare-entry comparison."""

    free_entry: int
    welfare_entry: int
    wedge: int
    direction: str


def compare_entry_counts(free_entry: int, welfare_entry: int) -> EntryComparison:
    if min(free_entry, welfare_entry) < 0:
        raise ValueError("entry counts must be nonnegative")
    wedge = int(free_entry - welfare_entry)
    direction = "excess_entry" if wedge > 0 else "insufficient_entry" if wedge < 0 else "aligned"
    return EntryComparison(
        free_entry=int(free_entry),
        welfare_entry=int(welfare_entry),
        wedge=wedge,
        direction=direction,
    )
