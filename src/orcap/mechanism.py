"""Minimal capacity-certified routing mechanism used by H48.

The model is deliberately small enough for empirical calibration. Providers
post a unit quote and a capacity commitment; the router allocates first-route
probability using reliability-weighted inverse-price scores. A capacity bond
is a deferred payment/forfeit for committed but unserved allocation.  It is a
mechanism-design proposal, not a claim about any existing router's policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite, log

import pandas as pd
from scipy.optimize import linprog


@dataclass(frozen=True)
class ProviderOffer:
    provider: str
    price: float
    reliability: float
    committed_capacity: float
    marginal_cost: float


@dataclass(frozen=True)
class CapacityProcurementOffer:
    """A certified capacity ceiling with a reported linear reservation cost.

    The provider's capacity-acquisition cost is ``a_i k + b_i k^2 / 2`` up to
    ``certified_capacity``. ``a_i`` is the single private report; the ceiling
    and known positive curvature ``b_i`` are certified before procurement.
    """

    provider: str
    reported_linear_cost: float
    certified_capacity: float
    capacity_cost_curvature: float


@dataclass(frozen=True)
class CertifiedCostCurveOffer:
    """A certified integer capacity ceiling and a reported convex cost curve.

    ``reported_marginal_costs[u]`` is the reported cost of reserving unit
    ``u + 1``. The whole non-decreasing vector is the private report, so it
    contains both a linear term and arbitrary discrete convex curvature. The
    physical ceiling and reliability eligibility are certified outside this
    mechanism; this is not a solution to private capacity or reliability.
    """

    provider: str
    certified_capacity: int
    reported_marginal_costs: tuple[float, ...]


@dataclass(frozen=True)
class OutageScenario:
    """One joint provider-availability state for a fixed allocation epoch.

    The state is intentionally joint: a shared GPU, cloud, or routing outage
    can remove several providers together. Independence must not be inferred
    from marginal uptime scores.
    """

    probability: float
    unavailable_providers: frozenset[str]


def _validate_certified_cost_curve_offers(offers: list[CertifiedCostCurveOffer]) -> None:
    if len({offer.provider for offer in offers}) != len(offers):
        raise ValueError("provider names must be unique")
    for offer in offers:
        if not isinstance(offer.certified_capacity, int) or isinstance(
            offer.certified_capacity, bool
        ):
            raise ValueError("certified capacity must be an integer")
        if offer.certified_capacity < 0:
            raise ValueError("certified capacity must be non-negative")
        costs = tuple(offer.reported_marginal_costs)
        if len(costs) != offer.certified_capacity:
            raise ValueError("marginal-cost schedule length must equal certified capacity")
        if any(not isfinite(float(cost)) or float(cost) < 0 for cost in costs):
            raise ValueError("marginal costs must be finite and non-negative")
        if any(float(left) > float(right) for left, right in zip(costs, costs[1:], strict=False)):
            raise ValueError("marginal-cost schedule must be non-decreasing")


def _validate_integer_demand(demand: int) -> int:
    if not isinstance(demand, int) or isinstance(demand, bool) or demand < 0:
        raise ValueError("demand must be a non-negative integer")
    return demand


def _cost_curve_total_cost(offer: CertifiedCostCurveOffer, units: int) -> float:
    if not isinstance(units, int) or units < 0 or units > offer.certified_capacity:
        raise ValueError("procured units must lie within certified capacity")
    return float(sum(offer.reported_marginal_costs[:units]))


def certified_cost_curve_allocation(
    offers: list[CertifiedCostCurveOffer], demand: int
) -> pd.Series:
    """Minimize reported convex reservation cost under certified integer caps.

    The mechanism procures ``min(D, sum_i K_i)`` units. Selecting the globally
    cheapest reported marginal units is optimal because every accepted schedule
    is non-decreasing, so no later unit of a provider can be selected before
    its earlier units. Any residual is explicit unfilled demand, not a
    fictitious reservation beyond certified caps.
    """
    demand = _validate_integer_demand(demand)
    _validate_certified_cost_curve_offers(offers)
    allocation = {offer.provider: 0 for offer in offers}
    target = min(demand, sum(offer.certified_capacity for offer in offers))
    marginal_units = [
        (float(cost), offer.provider, unit)
        for offer in offers
        for unit, cost in enumerate(offer.reported_marginal_costs, start=1)
    ]
    for _, provider, _ in sorted(marginal_units)[:target]:
        allocation[provider] += 1
    return pd.Series(allocation, dtype="int64")


def certified_cost_curve_system_cost(
    offers: list[CertifiedCostCurveOffer],
    demand: int,
    *,
    unfilled_penalty: float,
) -> float:
    """Reported procurement cost plus an explicit forced-shortfall penalty."""
    demand = _validate_integer_demand(demand)
    _validate_certified_cost_curve_offers(offers)
    if not isfinite(unfilled_penalty) or unfilled_penalty < 0:
        raise ValueError("unfilled_penalty must be finite and non-negative")
    allocation = certified_cost_curve_allocation(offers, demand)
    reported_cost = sum(
        _cost_curve_total_cost(offer, int(allocation[offer.provider])) for offer in offers
    )
    return reported_cost + float(unfilled_penalty) * (demand - int(allocation.sum()))


def certified_cost_curve_vcg_payment(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    demand: int,
    unfilled_penalty: float,
) -> float:
    """Clarke-pivot procurement payment for a reported convex cost curve.

    The payment equals the cost imposed on every *other* participant and on
    the router's declared unfilled-demand outside option. It intentionally
    excludes the reporting provider's own reported cost. With a truthful
    curve, this is DSIC and individually rational over the entire convex
    schedule, but it need not be budget balanced.
    """
    demand = _validate_integer_demand(demand)
    _validate_certified_cost_curve_offers(offers)
    if provider not in {offer.provider for offer in offers}:
        raise ValueError(f"unknown provider: {provider}")
    if not isfinite(unfilled_penalty) or unfilled_penalty < 0:
        raise ValueError("unfilled_penalty must be finite and non-negative")
    allocation = certified_cost_curve_allocation(offers, demand)
    without = [offer for offer in offers if offer.provider != provider]
    cost_without_provider = certified_cost_curve_system_cost(
        without, demand, unfilled_penalty=unfilled_penalty
    )
    others_cost = sum(
        _cost_curve_total_cost(offer, int(allocation[offer.provider]))
        for offer in without
    )
    others_cost += float(unfilled_penalty) * (demand - int(allocation.sum()))
    return cost_without_provider - others_cost


def certified_cost_curve_vcg_utility(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    true_marginal_costs: tuple[float, ...],
    demand: int,
    unfilled_penalty: float,
) -> float:
    """Counterfactual utility when true convex costs are supplied for an audit."""
    _validate_certified_cost_curve_offers(offers)
    by_provider = {offer.provider: offer for offer in offers}
    if provider not in by_provider:
        raise ValueError(f"unknown provider: {provider}")
    offer = by_provider[provider]
    true_offer = CertifiedCostCurveOffer(
        provider=provider,
        certified_capacity=offer.certified_capacity,
        reported_marginal_costs=true_marginal_costs,
    )
    _validate_certified_cost_curve_offers([true_offer])
    allocation = certified_cost_curve_allocation(offers, demand)
    payment = certified_cost_curve_vcg_payment(
        offers,
        provider=provider,
        demand=demand,
        unfilled_penalty=unfilled_penalty,
    )
    true_cost = _cost_curve_total_cost(true_offer, int(allocation[provider]))
    return payment - true_cost


def certified_cost_curve_vcg_report_diagnostic(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    true_marginal_costs: tuple[float, ...],
    report_schedules: list[tuple[float, ...]],
    demand: int,
    unfilled_penalty: float,
) -> pd.DataFrame:
    """Audit multi-dimensional VCG incentives over a declared report grid."""
    _validate_certified_cost_curve_offers(offers)
    if provider not in {offer.provider for offer in offers}:
        raise ValueError(f"unknown provider: {provider}")
    rows = []
    for schedule in report_schedules:
        reported_offers = [
            (
                CertifiedCostCurveOffer(
                    provider=offer.provider,
                    certified_capacity=offer.certified_capacity,
                    reported_marginal_costs=schedule,
                )
                if offer.provider == provider
                else offer
            )
            for offer in offers
        ]
        allocation = certified_cost_curve_allocation(reported_offers, demand)
        payment = certified_cost_curve_vcg_payment(
            reported_offers,
            provider=provider,
            demand=demand,
            unfilled_penalty=unfilled_penalty,
        )
        utility = certified_cost_curve_vcg_utility(
            reported_offers,
            provider=provider,
            true_marginal_costs=true_marginal_costs,
            demand=demand,
            unfilled_penalty=unfilled_penalty,
        )
        rows.append(
            {
                "reported_marginal_costs": tuple(float(cost) for cost in schedule),
                "procured_capacity": int(allocation[provider]),
                "payment": payment,
                "utility_at_true_cost_curve": utility,
            }
        )
    return pd.DataFrame(rows)


def _validate_reliability_reports(
    offers: list[CertifiedCostCurveOffer], reported_reliability: dict[str, float]
) -> dict[str, float]:
    """Validate a complete report vector without inferring a health process."""
    providers = {offer.provider for offer in offers}
    if set(reported_reliability) != providers:
        raise ValueError("reported reliability keys must equal the provider set")
    reports = {provider: float(value) for provider, value in reported_reliability.items()}
    if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in reports.values()):
        raise ValueError("reported reliability values must lie in [0, 1]")
    return reports


def certified_reliability_cost_allocation(
    offers: list[CertifiedCostCurveOffer],
    *,
    reported_reliability: dict[str, float],
    demand: int,
    value_per_success: float,
) -> pd.Series:
    """Maximize reported expected net value with certified capacity and costs.

    Every marginal capacity unit for provider ``i`` has reported buyer benefit
    ``r_i * v`` and reported reservation cost ``c_iu``.  The mechanism takes
    only strictly positive-surplus units, subject to demand and certified
    integer caps. It is a finite-capacity VCG allocation primitive, not an
    estimate of actual reliability, welfare, or delivered work.
    """
    demand = _validate_integer_demand(demand)
    _validate_certified_cost_curve_offers(offers)
    reports = _validate_reliability_reports(offers, reported_reliability)
    if not isfinite(value_per_success) or value_per_success < 0:
        raise ValueError("value_per_success must be finite and non-negative")
    allocation = {offer.provider: 0 for offer in offers}
    marginal_units = []
    for offer in offers:
        benefit = reports[offer.provider] * float(value_per_success)
        for unit, cost in enumerate(offer.reported_marginal_costs, start=1):
            surplus = benefit - float(cost)
            marginal_units.append((-surplus, offer.provider, unit, surplus))
    for _, provider, _, surplus in sorted(marginal_units):
        if sum(allocation.values()) >= demand or surplus <= 0:
            break
        allocation[provider] += 1
    return pd.Series(allocation, dtype="int64")


def certified_reliability_cost_reported_welfare(
    offers: list[CertifiedCostCurveOffer],
    *,
    reported_reliability: dict[str, float],
    demand: int,
    value_per_success: float,
    allocation: pd.Series | None = None,
) -> float:
    """Reported buyer-value-minus-reservation-cost welfare for one allocation."""
    demand = _validate_integer_demand(demand)
    _validate_certified_cost_curve_offers(offers)
    reports = _validate_reliability_reports(offers, reported_reliability)
    if not isfinite(value_per_success) or value_per_success < 0:
        raise ValueError("value_per_success must be finite and non-negative")
    chosen = (
        certified_reliability_cost_allocation(
            offers,
            reported_reliability=reports,
            demand=demand,
            value_per_success=value_per_success,
        )
        if allocation is None
        else _validated_allocation(allocation).reindex(
            [offer.provider for offer in offers], fill_value=0.0
        )
    )
    if any(chosen[offer.provider] > offer.certified_capacity for offer in offers):
        raise ValueError("allocation exceeds certified capacity")
    if float(chosen.sum()) > demand:
        raise ValueError("allocation exceeds demand")
    return sum(
        reports[offer.provider] * float(value_per_success) * float(chosen[offer.provider])
        - _cost_curve_total_cost(offer, int(chosen[offer.provider]))
        for offer in offers
    )


def certified_reliability_cost_vcg_payment(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    reported_reliability: dict[str, float],
    demand: int,
    value_per_success: float,
) -> float:
    """Clarke-pivot payment with reported expected buyer value.

    Conditional on the reliability reports, the reported expected buyer values
    are fixed terms in the allocation objective. Thus this is the usual VCG
    payment to a provider for its complete convex cost-curve report; it is not
    itself incentive compatible for a private reliability report.
    """
    _validate_certified_cost_curve_offers(offers)
    reports = _validate_reliability_reports(offers, reported_reliability)
    if provider not in reports:
        raise ValueError(f"unknown provider: {provider}")
    allocation = certified_reliability_cost_allocation(
        offers,
        reported_reliability=reports,
        demand=demand,
        value_per_success=value_per_success,
    )
    without = [offer for offer in offers if offer.provider != provider]
    without_reports = {name: value for name, value in reports.items() if name != provider}
    welfare_without = certified_reliability_cost_reported_welfare(
        without,
        reported_reliability=without_reports,
        demand=demand,
        value_per_success=value_per_success,
    )
    others_welfare = sum(
        reports[offer.provider] * float(value_per_success) * float(allocation[offer.provider])
        - _cost_curve_total_cost(offer, int(allocation[offer.provider]))
        for offer in without
    )
    own_reported_buyer_value = (
        reports[provider] * float(value_per_success) * float(allocation[provider])
    )
    return own_reported_buyer_value + others_welfare - welfare_without


def certified_reliability_cost_vcg_utility(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    true_marginal_costs: tuple[float, ...],
    reported_reliability: dict[str, float],
    demand: int,
    value_per_success: float,
) -> float:
    """Provider utility at an audited true convex cost curve, before audit score."""
    _validate_certified_cost_curve_offers(offers)
    by_provider = {offer.provider: offer for offer in offers}
    if provider not in by_provider:
        raise ValueError(f"unknown provider: {provider}")
    true_offer = CertifiedCostCurveOffer(
        provider=provider,
        certified_capacity=by_provider[provider].certified_capacity,
        reported_marginal_costs=tuple(true_marginal_costs),
    )
    _validate_certified_cost_curve_offers([true_offer])
    allocation = certified_reliability_cost_allocation(
        offers,
        reported_reliability=reported_reliability,
        demand=demand,
        value_per_success=value_per_success,
    )
    payment = certified_reliability_cost_vcg_payment(
        offers,
        provider=provider,
        reported_reliability=reported_reliability,
        demand=demand,
        value_per_success=value_per_success,
    )
    return payment - _cost_curve_total_cost(true_offer, int(allocation[provider]))


def _validated_audit_grid(reliability_grid: tuple[float, ...]) -> tuple[tuple[float, ...], float]:
    grid = tuple(float(value) for value in reliability_grid)
    if len(grid) < 2 or len(set(grid)) != len(grid) or tuple(sorted(grid)) != grid:
        raise ValueError("reliability_grid must contain at least two sorted unique reports")
    if any(not isfinite(value) or not 0.0 < value < 1.0 for value in grid):
        raise ValueError("reliability_grid must lie strictly inside (0, 1)")
    return grid, min(grid[0], 1.0 - grid[-1])


def _reliability_vector_for_provider_report(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    other_reported_reliability: dict[str, float],
    provider_report: float,
) -> dict[str, float]:
    providers = {offer.provider for offer in offers}
    if provider not in providers:
        raise ValueError(f"unknown provider: {provider}")
    if set(other_reported_reliability) != providers - {provider}:
        raise ValueError("other reported reliability keys must equal the other provider set")
    reports = dict(other_reported_reliability) | {provider: float(provider_report)}
    return _validate_reliability_reports(offers, reports)


def _replace_cost_curve_report(
    offers: list[CertifiedCostCurveOffer], provider: str, schedule: tuple[float, ...]
) -> list[CertifiedCostCurveOffer]:
    return [
        (
            CertifiedCostCurveOffer(
                provider=offer.provider,
                certified_capacity=offer.certified_capacity,
                reported_marginal_costs=tuple(schedule),
            )
            if offer.provider == provider
            else offer
        )
        for offer in offers
    ]


def certified_audited_vcg_minimum_score_scale(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    true_marginal_costs: tuple[float, ...],
    reliability_grid: tuple[float, ...],
    other_reported_reliability: dict[str, float],
    demand: int,
    value_per_success: float,
    audit_probability: float,
    strict_advantage: float = 0.0,
) -> float:
    """Audit-score scale that offsets every finite-grid VCG reliability gain.

    Capacity is certified and the provider's complete convex cost curve is held
    truthful in this calculation. The score scale makes the independently
    audited reliability report strictly optimal on the stated finite grid; the
    separate VCG argument controls any cost-curve misreport conditional on a
    reliability report.
    """
    _validate_certified_cost_curve_offers(offers)
    grid, _ = _validated_audit_grid(reliability_grid)
    _reliability_vector_for_provider_report(
        offers,
        provider=provider,
        other_reported_reliability=other_reported_reliability,
        provider_report=grid[0],
    )
    if not isfinite(audit_probability) or not 0.0 < audit_probability <= 1.0:
        raise ValueError("audit_probability must lie in (0, 1]")
    if not isfinite(strict_advantage) or strict_advantage < 0.0:
        raise ValueError("strict_advantage must be finite and non-negative")
    truthful_offers = _replace_cost_curve_report(offers, provider, true_marginal_costs)
    base_utility = {}
    for report in grid:
        reports = _reliability_vector_for_provider_report(
            truthful_offers,
            provider=provider,
            other_reported_reliability=other_reported_reliability,
            provider_report=report,
        )
        base_utility[report] = certified_reliability_cost_vcg_utility(
            truthful_offers,
            provider=provider,
            true_marginal_costs=true_marginal_costs,
            reported_reliability=reports,
            demand=demand,
            value_per_success=value_per_success,
        )
    required_scale = 0.0
    for true_q in grid:
        for report in grid:
            if report == true_q:
                continue
            base_gain = max(0.0, base_utility[report] - base_utility[true_q])
            kl_divergence = true_q * log(true_q / report) + (1.0 - true_q) * log(
                (1.0 - true_q) / (1.0 - report)
            )
            required_scale = max(
                required_scale,
                (base_gain + strict_advantage) / (audit_probability * kl_divergence),
            )
    return required_scale


def certified_audited_vcg_product_report_diagnostic(
    offers: list[CertifiedCostCurveOffer],
    *,
    provider: str,
    true_marginal_costs: tuple[float, ...],
    cost_report_schedules: list[tuple[float, ...]],
    reliability_grid: tuple[float, ...],
    other_reported_reliability: dict[str, float],
    demand: int,
    value_per_success: float,
    audit_probability: float,
    audit_score_scale: float,
) -> pd.DataFrame:
    """Audit finite reliability and declared convex-cost report deviations.

    The diagnostic is not the theorem's domain restriction: VCG cost truth is
    over every feasible convex cost report. It makes the product-report logic
    inspectable on a supplied report grid and displays the funded audit score.
    """
    _validate_certified_cost_curve_offers(offers)
    grid, report_floor = _validated_audit_grid(reliability_grid)
    if not isfinite(audit_probability) or not 0.0 < audit_probability <= 1.0:
        raise ValueError("audit_probability must lie in (0, 1]")
    if not isfinite(audit_score_scale) or audit_score_scale < 0.0:
        raise ValueError("audit_score_scale must be finite and non-negative")
    truthful_offers = _replace_cost_curve_report(offers, provider, true_marginal_costs)
    _validate_certified_cost_curve_offers(truthful_offers)
    rows = []
    for true_q in grid:
        truth_reports = _reliability_vector_for_provider_report(
            truthful_offers,
            provider=provider,
            other_reported_reliability=other_reported_reliability,
            provider_report=true_q,
        )
        truthful_base = certified_reliability_cost_vcg_utility(
            truthful_offers,
            provider=provider,
            true_marginal_costs=true_marginal_costs,
            reported_reliability=truth_reports,
            demand=demand,
            value_per_success=value_per_success,
        )
        truthful_score = audit_probability * audit_score_scale * expected_bounded_log_score(
            actual_reliability=true_q,
            reported_reliability=true_q,
            report_floor=report_floor,
        )
        truthful_total = truthful_base + truthful_score
        for reliability_report in grid:
            reports = _reliability_vector_for_provider_report(
                truthful_offers,
                provider=provider,
                other_reported_reliability=other_reported_reliability,
                provider_report=reliability_report,
            )
            for cost_report in cost_report_schedules:
                reported_offers = _replace_cost_curve_report(
                    truthful_offers, provider, cost_report
                )
                _validate_certified_cost_curve_offers(reported_offers)
                base_utility = certified_reliability_cost_vcg_utility(
                    reported_offers,
                    provider=provider,
                    true_marginal_costs=true_marginal_costs,
                    reported_reliability=reports,
                    demand=demand,
                    value_per_success=value_per_success,
                )
                score = audit_probability * audit_score_scale * expected_bounded_log_score(
                    actual_reliability=true_q,
                    reported_reliability=reliability_report,
                    report_floor=report_floor,
                )
                rows.append(
                    {
                        "true_reliability": true_q,
                        "reported_reliability": reliability_report,
                        "reported_marginal_costs": tuple(float(cost) for cost in cost_report),
                        "base_vcg_utility_at_true_cost": base_utility,
                        "expected_audit_score": score,
                        "combined_expected_payoff": base_utility + score,
                        "truthful_joint_payoff_advantage": truthful_total - (base_utility + score),
                    }
                )
    return pd.DataFrame(rows)


def _validated_allocation(allocation: pd.Series) -> pd.Series:
    """Return a finite, uniquely indexed non-negative allocation series."""
    numeric_allocation = pd.to_numeric(allocation, errors="coerce")
    if (
        numeric_allocation.index.has_duplicates
        or numeric_allocation.isna().any()
        or any(not isfinite(float(value)) or float(value) < 0 for value in numeric_allocation)
    ):
        raise ValueError("allocation must be finite, non-negative, and uniquely indexed")
    return numeric_allocation.astype("float64")


def _validated_outage_scenarios(
    scenarios: list[OutageScenario], known_providers: set[str]
) -> list[OutageScenario]:
    """Validate and normalize a probability distribution over joint outages."""
    if not scenarios:
        raise ValueError("at least one outage scenario is required")
    normalized: list[OutageScenario] = []
    for scenario in scenarios:
        try:
            probability = float(scenario.probability)
            unavailable = frozenset(scenario.unavailable_providers)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "outage scenarios must contain numeric probabilities and providers"
            ) from exc
        if not isfinite(probability) or probability < 0:
            raise ValueError("outage scenario probabilities must be finite and non-negative")
        unknown = unavailable - known_providers
        if unknown:
            raise ValueError(f"outage scenario names unknown providers: {sorted(unknown)}")
        normalized.append(OutageScenario(probability, unavailable))
    total_probability = sum(scenario.probability for scenario in normalized)
    if not isclose(total_probability, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("outage scenario probabilities must sum to one")
    return normalized


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


def limited_liability_delivery_gain(
    marginal_margin_per_request: float,
    nominal_bond_per_missed_request: float,
    collectible_liability_cap: float,
) -> float:
    """Payoff gain from serving rather than rationing under limited liability.

    A promised bond above the provider's collectible collateral does not make
    delivery more attractive. For a feasible request, the exact gain is
    ``p - c + min(b, L)`` where ``L`` is the liability cap. Strict delivery
    preference requires this value to be positive. This does not apply to a
    physical outage, where delivery is infeasible rather than strategically
    withheld.
    """
    values = {
        "marginal_margin_per_request": marginal_margin_per_request,
        "nominal_bond_per_missed_request": nominal_bond_per_missed_request,
        "collectible_liability_cap": collectible_liability_cap,
    }
    if any(not isfinite(value) for value in values.values()):
        raise ValueError("limited-liability inputs must be finite")
    if nominal_bond_per_missed_request < 0 or collectible_liability_cap < 0:
        raise ValueError("bond and liability cap must be non-negative")
    return marginal_margin_per_request + min(
        nominal_bond_per_missed_request, collectible_liability_cap
    )


def expected_reliability_report_payoff(
    *,
    actual_reliability: float,
    allocated_requests: float,
    marginal_margin_per_success: float,
    nominal_bond_per_missed_request: float,
    collectible_liability_cap: float,
) -> float:
    """Expected payoff under a reliability report and a capped shortfall bond.

    A completed assigned request succeeds with the provider's *actual*
    probability ``q``.  Conditional on success it earns the stated serving
    margin; conditional on a failed delivery it loses at most the collectible
    portion of the nominal bond.  Thus, for ``x`` assignments, expected payoff
    is ``x [q m - (1-q) min(b, L)]``.

    This is the private-reliability boundary of the current payment rule. If a
    report raises allocation while this per-assignment expectation is positive,
    the report is profitable even though failure is penalized. It is not an
    outcome-effort model, a reliability estimator, or an assertion that
    observed failures are independent.
    """
    values = {
        "actual_reliability": actual_reliability,
        "allocated_requests": allocated_requests,
        "marginal_margin_per_success": marginal_margin_per_success,
        "nominal_bond_per_missed_request": nominal_bond_per_missed_request,
        "collectible_liability_cap": collectible_liability_cap,
    }
    if any(not isfinite(value) for value in values.values()):
        raise ValueError("reliability-report inputs must be finite")
    if not 0 <= actual_reliability <= 1:
        raise ValueError("actual_reliability must lie in [0, 1]")
    if allocated_requests < 0:
        raise ValueError("allocated_requests must be non-negative")
    if nominal_bond_per_missed_request < 0 or collectible_liability_cap < 0:
        raise ValueError("bond and liability cap must be non-negative")
    collectible_bond = min(nominal_bond_per_missed_request, collectible_liability_cap)
    return allocated_requests * (
        actual_reliability * marginal_margin_per_success
        - (1.0 - actual_reliability) * collectible_bond
    )


def bounded_log_score(
    *, reported_reliability: float, audit_success: bool, report_floor: float
) -> float:
    """A non-negative, bounded log score for a clipped reliability report.

    The additive ``-log(report_floor)`` shift makes the transfer non-negative;
    it does not change report incentives.  Restricting reports to
    ``[report_floor, 1-report_floor]`` makes the score and every conditional
    audit transfer finite.  This is an audit *payment*, not a shortfall bond.
    """
    if not isfinite(report_floor) or not 0 < report_floor < 0.5:
        raise ValueError("report_floor must lie in (0, 0.5)")
    if not isfinite(reported_reliability) or not (
        report_floor <= reported_reliability <= 1.0 - report_floor
    ):
        raise ValueError("reported_reliability must lie in the clipped report domain")
    probability = reported_reliability if audit_success else 1.0 - reported_reliability
    return log(probability) - log(report_floor)


def expected_bounded_log_score(
    *, actual_reliability: float, reported_reliability: float, report_floor: float
) -> float:
    """Expected bounded log score under an independent Bernoulli audit outcome."""
    if not isfinite(actual_reliability) or not 0.0 <= actual_reliability <= 1.0:
        raise ValueError("actual_reliability must lie in [0, 1]")
    return actual_reliability * bounded_log_score(
        reported_reliability=reported_reliability,
        audit_success=True,
        report_floor=report_floor,
    ) + (1.0 - actual_reliability) * bounded_log_score(
        reported_reliability=reported_reliability,
        audit_success=False,
        report_floor=report_floor,
    )


def audited_reliability_report_payoff(
    *,
    actual_reliability: float,
    reported_reliability: float,
    allocated_requests: float,
    marginal_margin_per_success: float,
    nominal_bond_per_missed_request: float,
    collectible_liability_cap: float,
    audit_probability: float,
    audit_score_scale: float,
    report_floor: float,
) -> float:
    """Expected allocation payoff plus an independently-audited proper score.

    An audit occurs independently with probability ``audit_probability`` and
    pays ``audit_score_scale * bounded_log_score(report, outcome)``. This
    transfer is finite and non-negative on the clipped report domain. It can
    counter an allocation benefit from over-reporting, but requires an audit
    population independent of allocation and an explicitly funded transfer.
    """
    if not isfinite(audit_probability) or not 0.0 <= audit_probability <= 1.0:
        raise ValueError("audit_probability must lie in [0, 1]")
    if not isfinite(audit_score_scale) or audit_score_scale < 0.0:
        raise ValueError("audit_score_scale must be finite and non-negative")
    allocation_payoff = expected_reliability_report_payoff(
        actual_reliability=actual_reliability,
        allocated_requests=allocated_requests,
        marginal_margin_per_success=marginal_margin_per_success,
        nominal_bond_per_missed_request=nominal_bond_per_missed_request,
        collectible_liability_cap=collectible_liability_cap,
    )
    return allocation_payoff + audit_probability * audit_score_scale * expected_bounded_log_score(
        actual_reliability=actual_reliability,
        reported_reliability=reported_reliability,
        report_floor=report_floor,
    )


def audited_reliability_minimum_score_scale(
    *,
    reliability_grid: tuple[float, ...],
    allocation_by_report: dict[float, float],
    marginal_margin_per_success: float,
    nominal_bond_per_missed_request: float,
    collectible_liability_cap: float,
    audit_probability: float,
    strict_advantage: float = 0.0,
) -> float:
    """Scale needed for truthful reports on a finite clipped type/report grid.

    For every true grid point ``q`` and alternative report ``r``, the proper
    score supplies ``rho*A*KL(Bern(q)||Bern(r))`` in expected truthful-report
    advantage. The allocation side can gain at most its exact report-induced
    payoff difference. The returned scale makes truthful reporting weakly
    optimal; any positive ``strict_advantage`` makes it strictly optimal on
    each distinct report pair. This is deliberately a finite-grid theorem, not
    a continuous-type or budget-balance result.
    """
    grid = tuple(float(value) for value in reliability_grid)
    if len(grid) < 2 or len(set(grid)) != len(grid) or tuple(sorted(grid)) != grid:
        raise ValueError("reliability_grid must contain at least two sorted unique reports")
    if any(not isfinite(value) or not 0.0 < value < 1.0 for value in grid):
        raise ValueError("reliability_grid must lie strictly inside (0, 1)")
    if set(allocation_by_report) != set(grid):
        raise ValueError("allocation_by_report keys must equal reliability_grid")
    if any(
        not isfinite(value) or value < 0.0 for value in allocation_by_report.values()
    ):
        raise ValueError("allocations must be finite and non-negative")
    if not isfinite(audit_probability) or not 0.0 < audit_probability <= 1.0:
        raise ValueError("audit_probability must lie in (0, 1]")
    if not isfinite(strict_advantage) or strict_advantage < 0.0:
        raise ValueError("strict_advantage must be finite and non-negative")
    if not all(
        isfinite(value)
        for value in (
            marginal_margin_per_success,
            nominal_bond_per_missed_request,
            collectible_liability_cap,
        )
    ):
        raise ValueError("allocation-payoff inputs must be finite")
    if nominal_bond_per_missed_request < 0 or collectible_liability_cap < 0:
        raise ValueError("bond and liability cap must be non-negative")
    collectible_bond = min(nominal_bond_per_missed_request, collectible_liability_cap)
    required_scale = 0.0
    for true_q in grid:
        payoff_per_assignment = (
            true_q * marginal_margin_per_success - (1.0 - true_q) * collectible_bond
        )
        truthful_allocation = allocation_by_report[true_q]
        for report in grid:
            if report == true_q:
                continue
            allocation_gain = max(
                0.0, (allocation_by_report[report] - truthful_allocation) * payoff_per_assignment
            )
            kl_divergence = true_q * log(true_q / report) + (1.0 - true_q) * log(
                (1.0 - true_q) / (1.0 - report)
            )
            required_scale = max(
                required_scale,
                (allocation_gain + strict_advantage) / (audit_probability * kl_divergence),
            )
    return required_scale


def audited_reliability_report_diagnostic(
    *,
    reliability_grid: tuple[float, ...],
    allocation_by_report: dict[float, float],
    marginal_margin_per_success: float,
    nominal_bond_per_missed_request: float,
    collectible_liability_cap: float,
    audit_probability: float,
    audit_score_scale: float,
) -> pd.DataFrame:
    """Evaluate every finite-grid report pair under the audited score design."""
    # Reuse the full validation and guarantee a valid clipped scoring domain.
    audited_reliability_minimum_score_scale(
        reliability_grid=reliability_grid,
        allocation_by_report=allocation_by_report,
        marginal_margin_per_success=marginal_margin_per_success,
        nominal_bond_per_missed_request=nominal_bond_per_missed_request,
        collectible_liability_cap=collectible_liability_cap,
        audit_probability=audit_probability,
    )
    grid = tuple(float(value) for value in reliability_grid)
    report_floor = min(grid[0], 1.0 - grid[-1])
    rows = []
    for true_q in grid:
        truthful = audited_reliability_report_payoff(
            actual_reliability=true_q,
            reported_reliability=true_q,
            allocated_requests=allocation_by_report[true_q],
            marginal_margin_per_success=marginal_margin_per_success,
            nominal_bond_per_missed_request=nominal_bond_per_missed_request,
            collectible_liability_cap=collectible_liability_cap,
            audit_probability=audit_probability,
            audit_score_scale=audit_score_scale,
            report_floor=report_floor,
        )
        for report in grid:
            payoff = audited_reliability_report_payoff(
                actual_reliability=true_q,
                reported_reliability=report,
                allocated_requests=allocation_by_report[report],
                marginal_margin_per_success=marginal_margin_per_success,
                nominal_bond_per_missed_request=nominal_bond_per_missed_request,
                collectible_liability_cap=collectible_liability_cap,
                audit_probability=audit_probability,
                audit_score_scale=audit_score_scale,
                report_floor=report_floor,
            )
            rows.append(
                {
                    "true_reliability": true_q,
                    "reported_reliability": report,
                    "allocated_requests": allocation_by_report[report],
                    "expected_payoff": payoff,
                    "truthful_payoff_advantage": truthful - payoff,
                }
            )
    return pd.DataFrame(rows)


def declared_reliability_payoff(
    offers: list[ProviderOffer],
    *,
    provider: str,
    actual_reliability: float,
    reported_reliability: float,
    demand: float,
    nominal_bond_per_missed_request: float,
    collectible_liability_cap: float,
    eta: float = 2.0,
) -> float:
    """Expected payoff when only one provider's reliability report changes.

    It mechanically applies the existing capped score rule to the report, then
    values its allocation at the provider's actual success probability. This
    is a counterfactual diagnostic for the limited-liability impossibility
    boundary: it does not make a self-report incentive compatible.
    """
    if not isfinite(actual_reliability) or not 0 <= actual_reliability <= 1:
        raise ValueError("actual_reliability must lie in [0, 1]")
    if not isfinite(reported_reliability) or not 0 <= reported_reliability <= 1:
        raise ValueError("reported_reliability must lie in [0, 1]")
    by_provider = {offer.provider: offer for offer in offers}
    if provider not in by_provider:
        raise ValueError(f"unknown provider: {provider}")
    reported_offers = [
        (
            ProviderOffer(
                provider=offer.provider,
                price=offer.price,
                reliability=reported_reliability,
                committed_capacity=offer.committed_capacity,
                marginal_cost=offer.marginal_cost,
            )
            if offer.provider == provider
            else offer
        )
        for offer in offers
    ]
    allocation = capacity_constrained_allocation(reported_offers, demand, eta)
    allocated = float(allocation.get(provider, 0))
    offer = by_provider[provider]
    return expected_reliability_report_payoff(
        actual_reliability=actual_reliability,
        allocated_requests=allocated,
        marginal_margin_per_success=offer.price - offer.marginal_cost,
        nominal_bond_per_missed_request=nominal_bond_per_missed_request,
        collectible_liability_cap=collectible_liability_cap,
    )


def expected_delivered_under_outage_scenarios(
    allocation: pd.Series, scenarios: list[OutageScenario]
) -> float:
    """Expected delivered requests under an explicitly joint outage law.

    This is a measurement primitive, not an optimal robust-routing solver.
    The capacity-certified allocation maximizes deterministic delivered count
    under hard commitments; correlated physical failures require this separate
    joint availability input before any reliability or welfare statement.
    """
    numeric_allocation = _validated_allocation(allocation)
    scenarios = _validated_outage_scenarios(scenarios, set(numeric_allocation.index))
    delivered = 0.0
    for scenario in scenarios:
        available = numeric_allocation.drop(
            labels=list(scenario.unavailable_providers), errors="ignore"
        )
        delivered += scenario.probability * float(available.sum())
    return delivered


def robust_outage_allocation(
    offers: list[ProviderOffer],
    demand: float,
    scenarios: list[OutageScenario],
    eta: float = 2.0,
) -> pd.Series:
    """Maximize the delivered-request floor over an explicit joint outage law.

    This is a *non-replicated* robust allocation. It solves

    ``max_{x,z} z`` subject to ``sum_i x_i <= D``, ``0 <= x_i <= k_i``, and
    ``sum_{i available in omega} x_i >= z`` for every positive-probability
    joint scenario. A second linear program applies score weights only to break
    ties among max-min-optimal allocations. Thus it cannot convert marginal
    uptime into independent availability, or a nominal shortfall bond into
    insurance against a physical correlated outage.
    """
    if demand < 0:
        raise ValueError("demand must be non-negative")
    if eta <= 0:
        raise ValueError("eta must be positive")
    if len({offer.provider for offer in offers}) != len(offers):
        raise ValueError("provider names must be unique")
    all_providers = {offer.provider for offer in offers}
    scenarios = _validated_outage_scenarios(scenarios, all_providers)
    eligible = [
        offer
        for offer in offers
        if offer.price > 0 and offer.reliability > 0 and offer.committed_capacity > 0
    ]
    if demand == 0 or not eligible:
        return pd.Series({offer.provider: 0.0 for offer in offers}, dtype="float64")
    providers = [offer.provider for offer in eligible]
    capacities = [max(0.0, offer.committed_capacity) for offer in eligible]
    positive_scenarios = [scenario for scenario in scenarios if scenario.probability > 0]
    # ``z - availability dot x <= 0`` enforces the delivery floor in each
    # scenario. A capacity-certified score allocation is feasible in this LP,
    # so its minimum delivery cannot exceed this optimum.
    constraints = [[1.0] * len(providers) + [0.0]]
    rhs = [float(demand)]
    for scenario in positive_scenarios:
        constraints.append(
            [
                -1.0 if provider not in scenario.unavailable_providers else 0.0
                for provider in providers
            ]
            + [1.0]
        )
        rhs.append(0.0)
    bounds = [(0.0, capacity) for capacity in capacities] + [(0.0, float(demand))]
    first = linprog(
        [0.0] * len(providers) + [-1.0],
        A_ub=constraints,
        b_ub=rhs,
        bounds=bounds,
        method="highs",
    )
    if not first.success:
        raise RuntimeError(f"robust outage allocation failed: {first.message}")
    floor = max(0.0, float(first.x[-1]))
    weights = [offer.reliability * offer.price ** (-eta) for offer in eligible]
    total_weight = sum(weights)
    if total_weight > 0:
        weights = [weight / total_weight for weight in weights]
    second = linprog(
        [-weight for weight in weights] + [0.0],
        A_ub=constraints,
        b_ub=rhs,
        bounds=[(0.0, capacity) for capacity in capacities] + [(floor, floor)],
        method="highs",
    )
    allocation = second.x[:-1] if second.success else first.x[:-1]
    result = {offer.provider: 0.0 for offer in offers}
    result.update(dict(zip(providers, allocation, strict=True)))
    return pd.Series(result, dtype="float64")


def outage_delivery_profile(
    allocation: pd.Series, scenarios: list[OutageScenario]
) -> pd.DataFrame:
    """Return the exact delivered count in each declared joint outage state."""
    numeric_allocation = _validated_allocation(allocation)
    scenarios = _validated_outage_scenarios(scenarios, set(numeric_allocation.index))
    rows = []
    for index, scenario in enumerate(scenarios):
        delivered = float(
            numeric_allocation.drop(
                labels=list(scenario.unavailable_providers), errors="ignore"
            ).sum()
        )
        rows.append(
            {
                "scenario_index": index,
                "probability": scenario.probability,
                "unavailable_provider_count": len(scenario.unavailable_providers),
                "delivered_requests": delivered,
            }
        )
    return pd.DataFrame(rows)


def robust_outage_counterfactual(
    offers: list[ProviderOffer],
    demand: float,
    scenarios: list[OutageScenario],
    eta: float = 2.0,
) -> pd.DataFrame:
    """Compare score water-fill with the max-min joint-outage allocation.

    The reported worst-case improvement is a theorem conditional on the supplied
    scenario support and hard capacities; it is not an empirical reliability or
    welfare estimate. Expected delivery is included only under the same
    explicitly supplied joint law.
    """
    score = capacity_constrained_allocation(offers, demand, eta)
    robust = robust_outage_allocation(offers, demand, scenarios, eta)
    score_profile = outage_delivery_profile(score, scenarios)
    robust_profile = outage_delivery_profile(robust, scenarios)
    result = pd.DataFrame(
        {
            "provider": robust.index,
            "score_waterfill_allocation": score.reindex(robust.index, fill_value=0.0).to_numpy(),
            "robust_outage_allocation": robust.to_numpy(),
        }
    )
    result["score_worst_case_delivered"] = score_profile["delivered_requests"].min()
    result["robust_worst_case_delivered"] = robust_profile["delivered_requests"].min()
    result["robust_worst_case_delivery_gain"] = (
        result["robust_worst_case_delivered"] - result["score_worst_case_delivered"]
    )
    result["score_expected_delivered"] = (
        score_profile["probability"] * score_profile["delivered_requests"]
    ).sum()
    result["robust_expected_delivered"] = (
        robust_profile["probability"] * robust_profile["delivered_requests"]
    ).sum()
    return result


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


def capacity_procurement_allocation(
    offers: list[CapacityProcurementOffer], demand: float
) -> pd.Series:
    """Minimize certified convex capacity-acquisition cost for a fixed demand.

    The allocation solves ``min sum_i a_i k_i + b_i k_i^2 / 2`` subject to
    ``sum_i k_i = min(demand, sum_i K_i)`` and ``0 <= k_i <= K_i``. It buys
    every feasible unit when demand exceeds aggregate certified capacity. The
    KKT solution is ``k_i = clip((lambda-a_i)/b_i, 0, K_i)``; this makes a
    provider's capacity allocation weakly decreasing in its reported linear
    cost.
    """
    if not isfinite(demand) or demand < 0:
        raise ValueError("demand must be finite and non-negative")
    _validate_capacity_procurement_offers(offers)
    result = {offer.provider: 0.0 for offer in offers}
    target = min(float(demand), sum(offer.certified_capacity for offer in offers))
    if target == 0:
        return pd.Series(result, dtype="float64")
    if target == sum(offer.certified_capacity for offer in offers):
        return pd.Series(
            {offer.provider: offer.certified_capacity for offer in offers}, dtype="float64"
        )
    lower = min(offer.reported_linear_cost for offer in offers)
    upper = max(
        offer.reported_linear_cost + offer.capacity_cost_curvature * offer.certified_capacity
        for offer in offers
    )
    for _ in range(100):
        multiplier = (lower + upper) / 2
        supplied = sum(_capacity_supply_at_multiplier(offer, multiplier) for offer in offers)
        if supplied < target:
            lower = multiplier
        else:
            upper = multiplier
    return pd.Series(
        {
            offer.provider: _capacity_supply_at_multiplier(offer, upper)
            for offer in offers
        },
        dtype="float64",
    )


def reported_capacity_procurement_allocation(
    offers: list[CapacityProcurementOffer],
    *,
    provider: str,
    reported_linear_cost: float,
    demand: float,
) -> float:
    """Capacity assigned after one provider's single-parameter cost report."""
    if not isfinite(reported_linear_cost) or reported_linear_cost < 0:
        raise ValueError("reported_linear_cost must be finite and non-negative")
    if provider not in {offer.provider for offer in offers}:
        raise ValueError(f"unknown provider: {provider}")
    reported_offers = [
        (
            CapacityProcurementOffer(
                provider=offer.provider,
                reported_linear_cost=reported_linear_cost,
                certified_capacity=offer.certified_capacity,
                capacity_cost_curvature=offer.capacity_cost_curvature,
            )
            if offer.provider == provider
            else offer
        )
        for offer in offers
    ]
    return float(capacity_procurement_allocation(reported_offers, demand).get(provider, 0.0))


def capacity_procurement_payment(
    offers: list[CapacityProcurementOffer],
    *,
    provider: str,
    reported_linear_cost: float,
    demand: float,
    cost_upper_bound: float,
    quadrature_steps: int = 512,
) -> float:
    """Envelope payment for certified capacity procurement with convex cost.

    For known curvature ``b_i`` and monotone capacity allocation ``k_i(r)``,
    the transfer is ``r k_i(r) + b_i k_i(r)^2/2 + integral_r^abar k_i(z)dz``.
    This is a numerical evaluation of the exact envelope formula, not a
    budget-balance result or a solution to a privately chosen capacity ceiling.
    """
    _validate_capacity_procurement_payment_inputs(
        offers, provider, reported_linear_cost, cost_upper_bound, quadrature_steps
    )
    offer = _capacity_procurement_offer(offers, provider)
    allocation = reported_capacity_procurement_allocation(
        offers,
        provider=provider,
        reported_linear_cost=reported_linear_cost,
        demand=demand,
    )
    base_cost = (
        reported_linear_cost * allocation
        + offer.capacity_cost_curvature * allocation**2 / 2
    )
    if reported_linear_cost == cost_upper_bound:
        return base_cost
    step = (cost_upper_bound - reported_linear_cost) / quadrature_steps
    previous = allocation
    integral = 0.0
    for index in range(1, quadrature_steps + 1):
        report = reported_linear_cost + index * step
        current = reported_capacity_procurement_allocation(
            offers,
            provider=provider,
            reported_linear_cost=report,
            demand=demand,
        )
        integral += (previous + current) * step / 2
        previous = current
    return base_cost + integral


def capacity_procurement_utility(
    offers: list[CapacityProcurementOffer],
    *,
    provider: str,
    true_linear_cost: float,
    reported_linear_cost: float,
    demand: float,
    cost_upper_bound: float,
    quadrature_steps: int = 512,
) -> float:
    """Utility from a capacity-cost report under certified convex costs."""
    if (
        not isfinite(true_linear_cost)
        or true_linear_cost < 0
        or true_linear_cost > cost_upper_bound
    ):
        raise ValueError("true_linear_cost must lie in [0, cost_upper_bound]")
    offer = _capacity_procurement_offer(offers, provider)
    allocation = reported_capacity_procurement_allocation(
        offers,
        provider=provider,
        reported_linear_cost=reported_linear_cost,
        demand=demand,
    )
    payment = capacity_procurement_payment(
        offers,
        provider=provider,
        reported_linear_cost=reported_linear_cost,
        demand=demand,
        cost_upper_bound=cost_upper_bound,
        quadrature_steps=quadrature_steps,
    )
    true_cost = true_linear_cost * allocation + offer.capacity_cost_curvature * allocation**2 / 2
    return payment - true_cost


def capacity_procurement_report_diagnostic(
    offers: list[CapacityProcurementOffer],
    *,
    provider: str,
    true_linear_cost: float,
    report_grid: list[float],
    demand: float,
    cost_upper_bound: float,
    quadrature_steps: int = 512,
) -> pd.DataFrame:
    """Numerically audit monotonicity, DSIC, and IR for the capacity menu."""
    rows = []
    for report in report_grid:
        allocation = reported_capacity_procurement_allocation(
            offers, provider=provider, reported_linear_cost=report, demand=demand
        )
        payment = capacity_procurement_payment(
            offers,
            provider=provider,
            reported_linear_cost=report,
            demand=demand,
            cost_upper_bound=cost_upper_bound,
            quadrature_steps=quadrature_steps,
        )
        utility = capacity_procurement_utility(
            offers,
            provider=provider,
            true_linear_cost=true_linear_cost,
            reported_linear_cost=report,
            demand=demand,
            cost_upper_bound=cost_upper_bound,
            quadrature_steps=quadrature_steps,
        )
        rows.append(
            {
                "reported_linear_cost": report,
                "procured_capacity": allocation,
                "payment": payment,
                "utility_at_true_cost": utility,
            }
        )
    return pd.DataFrame(rows)


def _capacity_supply_at_multiplier(offer: CapacityProcurementOffer, multiplier: float) -> float:
    return min(
        offer.certified_capacity,
        max(0.0, (multiplier - offer.reported_linear_cost) / offer.capacity_cost_curvature),
    )


def _capacity_procurement_offer(
    offers: list[CapacityProcurementOffer], provider: str
) -> CapacityProcurementOffer:
    _validate_capacity_procurement_offers(offers)
    for offer in offers:
        if offer.provider == provider:
            return offer
    raise ValueError(f"unknown provider: {provider}")


def _validate_capacity_procurement_offers(offers: list[CapacityProcurementOffer]) -> None:
    if not offers:
        raise ValueError("at least one capacity procurement offer is required")
    if len({offer.provider for offer in offers}) != len(offers):
        raise ValueError("provider names must be unique")
    for offer in offers:
        values = {
            "reported_linear_cost": offer.reported_linear_cost,
            "certified_capacity": offer.certified_capacity,
            "capacity_cost_curvature": offer.capacity_cost_curvature,
        }
        if any(not isfinite(value) for value in values.values()):
            raise ValueError("capacity procurement inputs must be finite")
        if offer.reported_linear_cost < 0 or offer.certified_capacity < 0:
            raise ValueError("capacity procurement cost and capacity must be non-negative")
        if offer.capacity_cost_curvature <= 0:
            raise ValueError("capacity_cost_curvature must be positive")


def _validate_capacity_procurement_payment_inputs(
    offers: list[CapacityProcurementOffer],
    provider: str,
    reported_linear_cost: float,
    cost_upper_bound: float,
    quadrature_steps: int,
) -> None:
    _capacity_procurement_offer(offers, provider)
    if not isfinite(cost_upper_bound) or cost_upper_bound < 0:
        raise ValueError("cost_upper_bound must be finite and non-negative")
    if not isfinite(reported_linear_cost) or not 0 <= reported_linear_cost <= cost_upper_bound:
        raise ValueError("reported_linear_cost must lie in [0, cost_upper_bound]")
    if not isinstance(quadrature_steps, int) or quadrature_steps < 1:
        raise ValueError("quadrature_steps must be a positive integer")


def expected_net_welfare(
    offers: list[ProviderOffer], allocation: pd.Series, request_value: float
) -> float:
    """Expected equal-request net surplus under known reliability and cost.

    Assigned request ``x_i`` yields value ``request_value`` with probability
    ``q_i`` and incurs the provider's marginal serving cost whenever assigned.
    Payments are transfers and do not enter this social-surplus benchmark.
    """
    _validate_welfare_inputs(offers, request_value)
    numeric_allocation = _validated_allocation(allocation)
    unknown = set(numeric_allocation.index) - {offer.provider for offer in offers}
    if unknown:
        raise ValueError(f"allocation names unknown providers: {sorted(unknown)}")
    return float(
        sum(
            float(numeric_allocation.get(offer.provider, 0.0))
            * (request_value * offer.reliability - offer.marginal_cost)
            for offer in offers
        )
    )


def welfare_capacity_allocation(
    offers: list[ProviderOffer], demand: float, request_value: float
) -> pd.Series:
    """Maximize expected net welfare with hard capacity and equal-value requests.

    The rule assigns only to positive expected-surplus providers in descending
    order of ``request_value * reliability - marginal_cost``. It can leave
    demand unfilled when every remaining feasible assignment has negative
    expected welfare; it is a known-primitive benchmark, not an implementable
    policy when costs or reliability are private.
    """
    _validate_welfare_inputs(offers, request_value, demand)
    allocation = {offer.provider: 0.0 for offer in offers}
    remaining = float(demand)
    ranked = sorted(
        offers,
        key=lambda offer: (
            request_value * offer.reliability - offer.marginal_cost,
            offer.reliability,
            -offer.marginal_cost,
        ),
        reverse=True,
    )
    for offer in ranked:
        surplus = request_value * offer.reliability - offer.marginal_cost
        if remaining <= 0 or surplus <= 0:
            break
        assigned = min(remaining, offer.committed_capacity)
        allocation[offer.provider] = assigned
        remaining -= assigned
    return pd.Series(allocation, dtype="float64")


def benchmark_capacity_allocation(
    offers: list[ProviderOffer], demand: float, *, policy: str
) -> pd.Series:
    """Allocate feasible demand by a transparent price-only or reliability-only rule."""
    if not isfinite(demand) or demand < 0:
        raise ValueError("demand must be finite and non-negative")
    _validate_welfare_inputs(offers, request_value=0.0)
    allocation = {offer.provider: 0.0 for offer in offers}
    if policy == "lowest_cost":
        ranked = sorted(offers, key=lambda offer: (offer.marginal_cost, offer.provider))
    elif policy == "reliability_only":
        ranked = sorted(
            offers, key=lambda offer: (-offer.reliability, offer.marginal_cost, offer.provider)
        )
    else:
        raise ValueError("policy must be 'lowest_cost' or 'reliability_only'")
    remaining = float(demand)
    for offer in ranked:
        if remaining <= 0:
            break
        assigned = min(remaining, offer.committed_capacity)
        allocation[offer.provider] = assigned
        remaining -= assigned
    return pd.Series(allocation, dtype="float64")


def welfare_policy_counterfactual(
    offers: list[ProviderOffer], demand: float, request_value: float
) -> pd.DataFrame:
    """Compare known-primitive welfare optimum with price and reliability baselines."""
    _validate_welfare_inputs(offers, request_value, demand)
    allocations = {
        "expected_welfare": welfare_capacity_allocation(offers, demand, request_value),
        "lowest_cost": benchmark_capacity_allocation(offers, demand, policy="lowest_cost"),
        "reliability_only": benchmark_capacity_allocation(
            offers, demand, policy="reliability_only"
        ),
    }
    rows = []
    for policy, allocation in allocations.items():
        allocated = float(allocation.sum())
        expected_delivered = float(
            sum(allocation[offer.provider] * offer.reliability for offer in offers)
        )
        rows.append(
            {
                "policy": policy,
                "allocated_requests": allocated,
                "unfilled_requests": max(0.0, demand - allocated),
                "expected_delivered_requests": expected_delivered,
                "expected_net_welfare": expected_net_welfare(offers, allocation, request_value),
            }
        )
    result = pd.DataFrame(rows)
    welfare_value = float(
        result.loc[result["policy"] == "expected_welfare", "expected_net_welfare"].iat[0]
    )
    result["welfare_gain_over_policy"] = welfare_value - result["expected_net_welfare"]
    return result


def _validate_welfare_inputs(
    offers: list[ProviderOffer], request_value: float, demand: float | None = None
) -> None:
    if not isfinite(request_value) or request_value < 0:
        raise ValueError("request_value must be finite and non-negative")
    if demand is not None and (not isfinite(demand) or demand < 0):
        raise ValueError("demand must be finite and non-negative")
    if len({offer.provider for offer in offers}) != len(offers):
        raise ValueError("provider names must be unique")
    for offer in offers:
        values = {
            "reliability": offer.reliability,
            "committed_capacity": offer.committed_capacity,
            "marginal_cost": offer.marginal_cost,
        }
        if any(not isfinite(value) for value in values.values()):
            raise ValueError("welfare inputs must be finite")
        if not 0 <= offer.reliability <= 1:
            raise ValueError("reliability must lie in [0, 1] for welfare accounting")
        if offer.committed_capacity < 0 or offer.marginal_cost < 0:
            raise ValueError("capacity and marginal cost must be non-negative")


def capacity_feasible(offer: ProviderOffer, allocated_requests: float) -> bool:
    """Whether the commitment covers the router's allocated request quantity."""
    return allocated_requests <= offer.committed_capacity
