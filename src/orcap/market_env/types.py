"""Validated economic primitives for the strategic market kernel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


def _finite_nonnegative(name: str, value: float) -> None:
    if not isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{name} must be finite and non-negative")


class Availability(StrEnum):
    """Provider admission state for one quote epoch."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class Workload:
    """Request value and real external costs for one workload shape."""

    name: str
    input_tokens: int
    output_tokens: int
    delivered_value: float
    latency_cost_per_ms: float = 0.0
    failure_loss: float = 0.0
    fallback_latency_ms: float = 0.0
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("workload name must be non-empty")
        for name, value in [
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ]:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name, value in [
            ("delivered_value", self.delivered_value),
            ("latency_cost_per_ms", self.latency_cost_per_ms),
            ("failure_loss", self.failure_loss),
            ("fallback_latency_ms", self.fallback_latency_ms),
        ]:
            _finite_nonnegative(name, value)
        if self.max_attempts is not None and (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or self.max_attempts < 1
        ):
            raise ValueError("max_attempts must be a positive integer or None")


@dataclass(frozen=True)
class ProviderSpec:
    """Private technology and capacity for one simulated provider.

    Marginal cost is charged for every admitted attempt, including a failed
    attempt, because an inference failure can consume compute.  Capital cost is
    an epoch cost for installed capacity and is paid even when capacity is
    withdrawn.
    """

    provider: str
    marginal_cost: float
    physical_capacity: int
    capital_cost_per_slot: float = 0.0
    base_latency_ms: float = 0.0
    reliability: float = 1.0
    degraded_capacity_multiplier: float = 0.5
    degraded_reliability_multiplier: float = 0.8

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("provider name must be non-empty")
        _finite_nonnegative("marginal_cost", self.marginal_cost)
        _finite_nonnegative("capital_cost_per_slot", self.capital_cost_per_slot)
        _finite_nonnegative("base_latency_ms", self.base_latency_ms)
        if (
            not isinstance(self.physical_capacity, int)
            or isinstance(self.physical_capacity, bool)
            or self.physical_capacity < 0
        ):
            raise ValueError("physical_capacity must be a non-negative integer")
        for name, value in [
            ("reliability", self.reliability),
            ("degraded_capacity_multiplier", self.degraded_capacity_multiplier),
            ("degraded_reliability_multiplier", self.degraded_reliability_multiplier),
        ]:
            if not isfinite(float(value)) or not 0 <= float(value) <= 1:
                raise ValueError(f"{name} must lie in [0, 1]")


@dataclass(frozen=True)
class ProviderAction:
    """Public quote and admitted-capacity decision for one epoch."""

    quote: float
    admitted_capacity_fraction: float = 1.0
    availability: Availability = Availability.ACTIVE

    def __post_init__(self) -> None:
        if not isfinite(float(self.quote)) or float(self.quote) <= 0:
            raise ValueError("quote must be finite and strictly positive")
        if (
            not isfinite(float(self.admitted_capacity_fraction))
            or not 0 <= float(self.admitted_capacity_fraction) <= 1
        ):
            raise ValueError("admitted_capacity_fraction must lie in [0, 1]")
        if not isinstance(self.availability, Availability):
            object.__setattr__(self, "availability", Availability(self.availability))


@dataclass(frozen=True)
class RequestOutcome:
    """Settlement of one request after fallback."""

    request_index: int
    ordered_providers: tuple[str, ...]
    attempted_providers: tuple[str, ...]
    served_provider: str | None
    payment: float
    resource_cost: float
    latency_ms: float
    user_utility: float
    welfare_before_capital_cost: float

    @property
    def served(self) -> bool:
        return self.served_provider is not None


@dataclass(frozen=True)
class ProviderEpochResult:
    """Provider accounting for one epoch."""

    provider: str
    quote: float
    admitted_capacity: int
    attempted_requests: int
    served_requests: int
    technical_failures: int
    capacity_rejections: int
    revenue: float
    variable_cost: float
    capital_cost: float
    profit: float


@dataclass(frozen=True)
class EpochResult:
    """Complete accounting result for one market epoch."""

    demand: int
    requests: tuple[RequestOutcome, ...]
    providers: tuple[ProviderEpochResult, ...]
    total_user_utility: float
    total_provider_profit: float
    total_payment: float
    total_resource_cost: float
    total_capital_cost: float
    total_welfare: float

    @property
    def served_requests(self) -> int:
        return sum(outcome.served for outcome in self.requests)

    @property
    def failed_requests(self) -> int:
        return self.demand - self.served_requests
