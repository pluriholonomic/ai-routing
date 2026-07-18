"""Transparent provider strategies used before learned policies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .types import ProviderAction, ProviderSpec


class ProviderStrategy(Protocol):
    def act(
        self,
        spec: ProviderSpec,
        public_quotes: Mapping[str, float],
    ) -> ProviderAction: ...


@dataclass(frozen=True)
class StaticStrategy:
    quote: float
    admitted_capacity_fraction: float = 1.0

    def act(
        self,
        spec: ProviderSpec,
        public_quotes: Mapping[str, float],
    ) -> ProviderAction:
        del spec, public_quotes
        return ProviderAction(self.quote, self.admitted_capacity_fraction)


@dataclass(frozen=True)
class CostPlusStrategy:
    markup: float
    admitted_capacity_fraction: float = 1.0

    def act(
        self,
        spec: ProviderSpec,
        public_quotes: Mapping[str, float],
    ) -> ProviderAction:
        del public_quotes
        if self.markup < 1:
            raise ValueError("markup must be at least one")
        return ProviderAction(
            spec.marginal_cost * self.markup,
            self.admitted_capacity_fraction,
        )


@dataclass(frozen=True)
class AuthorAnchorStrategy:
    reference_quote: float
    multiplier: float = 1.0
    admitted_capacity_fraction: float = 1.0

    def act(
        self,
        spec: ProviderSpec,
        public_quotes: Mapping[str, float],
    ) -> ProviderAction:
        del spec, public_quotes
        return ProviderAction(
            self.reference_quote * self.multiplier,
            self.admitted_capacity_fraction,
        )


@dataclass(frozen=True)
class UndercutStrategy:
    tick: float
    margin_floor: float = 0.0
    admitted_capacity_fraction: float = 1.0

    def act(
        self,
        spec: ProviderSpec,
        public_quotes: Mapping[str, float],
    ) -> ProviderAction:
        if self.tick < 0:
            raise ValueError("tick must be non-negative")
        if self.margin_floor < 0:
            raise ValueError("margin_floor must be non-negative")
        rivals = [
            quote for provider, quote in public_quotes.items() if provider != spec.provider
        ]
        if not rivals:
            target = spec.marginal_cost * (1 + self.margin_floor)
        else:
            target = min(rivals) - self.tick
        floor = spec.marginal_cost * (1 + self.margin_floor)
        return ProviderAction(max(floor, target), self.admitted_capacity_fraction)
