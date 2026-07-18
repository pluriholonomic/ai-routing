"""Router mechanisms for the fast strategic market kernel."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from math import isfinite
from random import Random

from .types import Availability, ProviderAction, ProviderSpec


class RouterMechanism(ABC):
    """Allocation interface shared by in-repo and executable adapters."""

    @abstractmethod
    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        """Return first-route probabilities over eligible providers."""

    def ordered_attempts(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
        rng: Random,
    ) -> tuple[str, ...]:
        """Sample a weighted order without replacement."""
        weights = self.probabilities(specs, actions)
        remaining = dict(weights)
        order: list[str] = []
        while remaining:
            total = sum(remaining.values())
            if total <= 0:
                break
            draw = rng.random() * total
            cumulative = 0.0
            chosen: str | None = None
            for provider in sorted(remaining):
                cumulative += remaining[provider]
                if draw <= cumulative:
                    chosen = provider
                    break
            if chosen is None:
                chosen = sorted(remaining)[-1]
            order.append(chosen)
            del remaining[chosen]
        return tuple(order)

    @staticmethod
    def eligible(
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> tuple[str, ...]:
        if set(specs) != set(actions):
            raise ValueError("actions must contain exactly the configured providers")
        return tuple(
            provider
            for provider in sorted(specs)
            if actions[provider].availability != Availability.WITHDRAWN
            and actions[provider].admitted_capacity_fraction > 0
            and specs[provider].physical_capacity > 0
        )


class InversePriceRouter(RouterMechanism):
    """First-route weight proportional to quote raised to minus exponent."""

    def __init__(self, exponent: float = 2.0) -> None:
        if not isfinite(float(exponent)) or float(exponent) < 0:
            raise ValueError("exponent must be finite and non-negative")
        self.exponent = float(exponent)

    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        candidates = self.eligible(specs, actions)
        if not candidates:
            return {}
        weights = {provider: actions[provider].quote ** (-self.exponent) for provider in candidates}
        total = sum(weights.values())
        if not isfinite(total) or total <= 0:
            return {}
        return {provider: weight / total for provider, weight in weights.items()}


class LowestCostRouter(RouterMechanism):
    """Deterministic lowest-quote allocation with stable tie breaking."""

    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        candidates = self.eligible(specs, actions)
        if not candidates:
            return {}
        winner = min(candidates, key=lambda provider: (actions[provider].quote, provider))
        return {provider: float(provider == winner) for provider in candidates}

    def ordered_attempts(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
        rng: Random,
    ) -> tuple[str, ...]:
        del rng
        return tuple(
            sorted(
                self.eligible(specs, actions),
                key=lambda provider: (actions[provider].quote, provider),
            )
        )


class RandomRouter(InversePriceRouter):
    """Uniform random allocation over eligible providers."""

    def __init__(self) -> None:
        super().__init__(exponent=0.0)


class ReliabilityWeightedRouter(InversePriceRouter):
    """Inverse-price score multiplied by public reliability to a power."""

    def __init__(
        self,
        exponent: float = 2.0,
        reliability_exponent: float = 1.0,
    ) -> None:
        super().__init__(exponent=exponent)
        if not isfinite(float(reliability_exponent)) or reliability_exponent < 0:
            raise ValueError("reliability_exponent must be finite and non-negative")
        self.reliability_exponent = float(reliability_exponent)

    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        candidates = self.eligible(specs, actions)
        if not candidates:
            return {}
        weights: dict[str, float] = {}
        for provider in candidates:
            reliability = specs[provider].reliability
            if actions[provider].availability == Availability.DEGRADED:
                reliability *= specs[provider].degraded_reliability_multiplier
            weights[provider] = (
                actions[provider].quote ** (-self.exponent)
                * reliability**self.reliability_exponent
            )
        total = sum(weights.values())
        if not isfinite(total) or total <= 0:
            return {}
        return {provider: weight / total for provider, weight in weights.items()}
