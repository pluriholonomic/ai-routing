"""Deterministic, seeded market transition and settlement kernel."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from random import Random

from .routers import RouterMechanism
from .types import (
    Availability,
    EpochResult,
    ProviderAction,
    ProviderEpochResult,
    ProviderSpec,
    RequestOutcome,
    Workload,
)


class MarketKernel:
    """Request-level fallback market with exact transfer reconciliation."""

    def __init__(
        self,
        providers: tuple[ProviderSpec, ...],
        workload: Workload,
        router: RouterMechanism,
        *,
        seed: int = 0,
    ) -> None:
        names = [provider.provider for provider in providers]
        if not providers:
            raise ValueError("market must contain at least one provider")
        if len(set(names)) != len(names):
            raise ValueError("provider names must be unique")
        self.specs = {provider.provider: provider for provider in providers}
        self.workload = workload
        self.router = router
        self._base_seed = int(seed)
        self._epoch_index = 0

    def reset(self, *, seed: int) -> None:
        self._base_seed = int(seed)
        self._epoch_index = 0

    def _subseed(self, *parts: object) -> int:
        """Return a stable substream seed for common-random-number designs."""
        payload = "|".join([str(self._base_seed), *(str(part) for part in parts)])
        digest = hashlib.blake2b(payload.encode(), digest_size=8).digest()
        return int.from_bytes(digest, "big")

    def _uniform(self, *parts: object) -> float:
        return Random(self._subseed(*parts)).random()

    def _capacity(
        self,
        spec: ProviderSpec,
        action: ProviderAction,
    ) -> int:
        if action.availability == Availability.WITHDRAWN:
            return 0
        multiplier = (
            spec.degraded_capacity_multiplier
            if action.availability == Availability.DEGRADED
            else 1.0
        )
        return math.floor(
            spec.physical_capacity * action.admitted_capacity_fraction * multiplier
        )

    def _reliability(
        self,
        spec: ProviderSpec,
        action: ProviderAction,
    ) -> float:
        multiplier = (
            spec.degraded_reliability_multiplier
            if action.availability == Availability.DEGRADED
            else 1.0
        )
        return spec.reliability * multiplier

    def step(
        self,
        actions: Mapping[str, ProviderAction],
        *,
        demand: int,
    ) -> EpochResult:
        """Clear and settle one quote epoch."""
        if not isinstance(demand, int) or isinstance(demand, bool) or demand < 0:
            raise ValueError("demand must be a non-negative integer")
        if set(actions) != set(self.specs):
            raise ValueError("actions must contain exactly the configured providers")

        capacities = {
            provider: self._capacity(spec, actions[provider])
            for provider, spec in self.specs.items()
        }
        attempted = defaultdict(int)
        served = defaultdict(int)
        technical_failures = defaultdict(int)
        capacity_rejections = defaultdict(int)
        revenue = defaultdict(float)
        variable_cost = defaultdict(float)
        outcomes: list[RequestOutcome] = []

        for request_index in range(demand):
            route_rng = Random(self._subseed("route", self._epoch_index, request_index))
            order = self.router.ordered_attempts(self.specs, actions, route_rng)
            if self.workload.max_attempts is not None:
                order = order[: self.workload.max_attempts]
            attempted_providers: list[str] = []
            resource_cost = 0.0
            latency_ms = 0.0
            payment = 0.0
            served_provider: str | None = None

            for position, provider in enumerate(order):
                spec = self.specs[provider]
                if attempted[provider] >= capacities[provider]:
                    capacity_rejections[provider] += 1
                    continue
                if position > 0:
                    latency_ms += self.workload.fallback_latency_ms
                attempted[provider] += 1
                attempted_providers.append(provider)
                variable_cost[provider] += spec.marginal_cost
                resource_cost += spec.marginal_cost
                latency_ms += spec.base_latency_ms
                reliability_draw = self._uniform(
                    "reliability",
                    self._epoch_index,
                    request_index,
                    provider,
                )
                if reliability_draw > self._reliability(spec, actions[provider]):
                    technical_failures[provider] += 1
                    continue
                served_provider = provider
                served[provider] += 1
                payment = actions[provider].quote
                revenue[provider] += payment
                break

            latency_loss = self.workload.latency_cost_per_ms * latency_ms
            if served_provider is None:
                user_utility = -self.workload.failure_loss - latency_loss
                welfare = -self.workload.failure_loss - latency_loss - resource_cost
            else:
                user_utility = self.workload.delivered_value - payment - latency_loss
                welfare = self.workload.delivered_value - latency_loss - resource_cost
            outcomes.append(
                RequestOutcome(
                    request_index=request_index,
                    ordered_providers=order,
                    attempted_providers=tuple(attempted_providers),
                    served_provider=served_provider,
                    payment=payment,
                    resource_cost=resource_cost,
                    latency_ms=latency_ms,
                    user_utility=user_utility,
                    welfare_before_capital_cost=welfare,
                )
            )

        provider_results: list[ProviderEpochResult] = []
        total_capital_cost = 0.0
        for provider in sorted(self.specs):
            spec = self.specs[provider]
            capital_cost = spec.capital_cost_per_slot * spec.physical_capacity
            total_capital_cost += capital_cost
            profit = revenue[provider] - variable_cost[provider] - capital_cost
            provider_results.append(
                ProviderEpochResult(
                    provider=provider,
                    quote=actions[provider].quote,
                    admitted_capacity=capacities[provider],
                    attempted_requests=attempted[provider],
                    served_requests=served[provider],
                    technical_failures=technical_failures[provider],
                    capacity_rejections=capacity_rejections[provider],
                    revenue=revenue[provider],
                    variable_cost=variable_cost[provider],
                    capital_cost=capital_cost,
                    profit=profit,
                )
            )

        total_user_utility = sum(outcome.user_utility for outcome in outcomes)
        total_provider_profit = sum(result.profit for result in provider_results)
        total_payment = sum(outcome.payment for outcome in outcomes)
        total_resource_cost = sum(outcome.resource_cost for outcome in outcomes)
        total_welfare = (
            sum(outcome.welfare_before_capital_cost for outcome in outcomes)
            - total_capital_cost
        )
        result = EpochResult(
            demand=demand,
            requests=tuple(outcomes),
            providers=tuple(provider_results),
            total_user_utility=total_user_utility,
            total_provider_profit=total_provider_profit,
            total_payment=total_payment,
            total_resource_cost=total_resource_cost,
            total_capital_cost=total_capital_cost,
            total_welfare=total_welfare,
        )
        self._epoch_index += 1
        return result
