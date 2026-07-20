"""Adaptive monotone router implementations for strategic stress tests.

The paid OpenRouter experiment emulates allocations from frozen public menus.
These adapters expose the same rules through :class:`RouterMechanism` so that
providers can respond inside the strategic market kernel.

`MenuProjectedRouter` is intentionally the vulnerable, contemporaneous rule:
every call re-solves the menu-level constraint problem.  `HardenedAdaptiveRouter`
uses lagged inputs, committed provider-specific leave-one-out parameters,
provider-independent exploration, operator-level share caps, and a log-share
trust region.  Calling ``probabilities`` never changes state; callers advance
the public state exactly once per quote epoch with ``advance``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

import numpy as np

from ..adaptive_router import allocation_probabilities, projected_policy
from .routers import RouterMechanism
from .types import Availability, ProviderAction, ProviderSpec


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    total = float(sum(weights.values()))
    if not isfinite(total) or total <= 0:
        return {}
    return {name: float(value / total) for name, value in weights.items()}


def _operator_cap(
    probabilities: Mapping[str, float],
    groups: Mapping[str, str],
    cap: float,
) -> dict[str, float]:
    """Project shares onto operator caps while preserving within-group ratios."""
    if not probabilities:
        return {}
    operators = {provider: groups.get(provider, provider) for provider in probabilities}
    group_members: dict[str, list[str]] = {}
    for provider, operator in operators.items():
        group_members.setdefault(operator, []).append(provider)
    if cap * len(group_members) < 1 - 1e-12:
        raise ValueError("operator share cap is infeasible for the eligible groups")

    group_mass = {
        operator: sum(probabilities[p] for p in members)
        for operator, members in group_members.items()
    }
    projected = dict(group_mass)
    free = set(projected)
    remaining = 1.0
    while free:
        free_total = sum(group_mass[group] for group in free)
        if free_total <= 0:
            equal = remaining / len(free)
            for group in free:
                projected[group] = equal
            break
        newly_bound = {
            group
            for group in free
            if remaining * group_mass[group] / free_total > cap + 1e-15
        }
        if not newly_bound:
            for group in free:
                projected[group] = remaining * group_mass[group] / free_total
            break
        for group in newly_bound:
            projected[group] = cap
            remaining -= cap
        free -= newly_bound

    output: dict[str, float] = {}
    for operator, members in group_members.items():
        original = group_mass[operator]
        if original <= 0:
            for provider in members:
                output[provider] = projected[operator] / len(members)
        else:
            for provider in members:
                output[provider] = (
                    projected[operator] * probabilities[provider] / original
                )
    return _normalize(output)


def _operator_neutral_probabilities(
    scores: Mapping[str, float],
    groups: Mapping[str, str],
    *,
    exploration: float,
    cap: float,
    capacities: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Allocate to economic operators first, then split within each operator.

    The operator score is the maximum member score, so cloning an identical
    endpoint does not create score mass or extra exploration probability.
    Within-operator shares follow installed capacity when available.
    """
    members: dict[str, list[str]] = {}
    for provider in scores:
        members.setdefault(groups.get(provider, provider), []).append(provider)
    operator_scores = {
        operator: max(scores[provider] for provider in providers)
        for operator, providers in members.items()
    }
    active_operators = {
        operator for operator, score in operator_scores.items() if score > 0
    }
    base = _normalize(
        {operator: operator_scores[operator] for operator in active_operators}
    )
    if not base:
        return {}
    operator_probabilities = {
        operator: (1 - exploration) * base[operator]
        + exploration / len(active_operators)
        for operator in active_operators
    }
    if cap * len(active_operators) >= 1 - 1e-12:
        operator_probabilities = _operator_cap(
            operator_probabilities,
            {operator: operator for operator in active_operators},
            cap,
        )
    output: dict[str, float] = {}
    for operator, providers in members.items():
        if operator not in active_operators:
            output.update(dict.fromkeys(providers, 0.0))
            continue
        weights = {
            provider: max(float((capacities or {}).get(provider, 1.0)), 0.0)
            for provider in providers
        }
        if sum(weights.values()) <= 0:
            weights = dict.fromkeys(providers, 1.0)
        total = sum(weights.values())
        for provider in providers:
            output[provider] = operator_probabilities[operator] * weights[provider] / total
    return _normalize(output)


def _trust_region(
    target: Mapping[str, float],
    previous: Mapping[str, float],
    max_log_change: float,
) -> dict[str, float]:
    """Cap allocation increases while allowing immediate allocation losses.

    A symmetric trust region is manipulable: a provider can raise price while
    the router protects it from losing traffic.  This upper-capped simplex
    projection limits sudden gains from undercutting without insuring a provider
    against its own higher price or worse quality.
    """
    if not target or not previous or not math.isfinite(max_log_change):
        return dict(target)
    upper = {
        provider: min(
            1.0,
            previous.get(provider, 1.0) * math.exp(max_log_change),
        )
        for provider in target
    }
    if sum(upper.values()) < 1 - 1e-12:
        raise ValueError("allocation trust-region upper bounds are infeasible")
    projected: dict[str, float] = {}
    free = set(target)
    remaining = 1.0
    while free:
        free_total = sum(target[provider] for provider in free)
        if free_total <= 0:
            equal = remaining / len(free)
            for provider in free:
                projected[provider] = equal
            break
        newly_bound = {
            provider
            for provider in free
            if remaining * target[provider] / free_total > upper[provider] + 1e-15
        }
        if not newly_bound:
            for provider in free:
                projected[provider] = remaining * target[provider] / free_total
            break
        for provider in newly_bound:
            projected[provider] = upper[provider]
            remaining -= upper[provider]
        free -= newly_bound
    return _normalize(projected)


@dataclass(frozen=True)
class AdaptivePolicyState:
    """Inspectable committed state of a hardened router."""

    epoch: int
    committed_at: int
    eta_by_provider: dict[str, float]
    exploration: float
    smoothed_quotes: dict[str, float]
    smoothed_qualities: dict[str, float]
    reference_quotes: dict[str, float]
    reference_qualities: dict[str, float]
    prior_probabilities: dict[str, float]


class AdaptiveMonotoneRouter(RouterMechanism):
    """Fixed quality-adjusted inverse-price rule with independent exploration."""

    def __init__(
        self,
        *,
        eta: float = 1.25,
        exploration: float = 0.10,
        reliability_power: float = 1.0,
        quality_overrides: Mapping[str, float] | None = None,
    ) -> None:
        if not isfinite(float(eta)) or eta < 0:
            raise ValueError("eta must be finite and non-negative")
        if not 0 <= exploration < 1:
            raise ValueError("exploration must lie in [0, 1)")
        if not isfinite(float(reliability_power)) or reliability_power < 0:
            raise ValueError("reliability_power must be finite and non-negative")
        self.eta = float(eta)
        self.exploration = float(exploration)
        self.reliability_power = float(reliability_power)
        self.quality_overrides = dict(quality_overrides or {})

    def _quality(self, provider: str, spec: ProviderSpec, action: ProviderAction) -> float:
        quality = float(self.quality_overrides.get(provider, spec.reliability))
        if action.availability == Availability.DEGRADED:
            quality *= spec.degraded_reliability_multiplier
        return min(max(quality, 1e-6), 1.0)

    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        candidates = self.eligible(specs, actions)
        if not candidates:
            return {}
        costs = [float(actions[p].quote) for p in candidates]
        qualities = [self._quality(p, specs[p], actions[p]) for p in candidates]
        shares = allocation_probabilities(
            costs,
            qualities,
            eta=self.eta,
            exploration=self.exploration,
            reliability_power=self.reliability_power,
        )
        return {provider: float(shares[index]) for index, provider in enumerate(candidates)}


class MenuProjectedRouter(AdaptiveMonotoneRouter):
    """Contemporaneous per-menu projection used as a manipulation benchmark."""

    def __init__(
        self,
        *,
        max_cost_premium: float = 0.02,
        max_reliability_loss: float = 0.002,
    ) -> None:
        super().__init__(eta=2.0, exploration=0.0)
        self.max_cost_premium = float(max_cost_premium)
        self.max_reliability_loss = float(max_reliability_loss)

    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        candidates = self.eligible(specs, actions)
        if not candidates:
            return {}
        costs = [float(actions[p].quote) for p in candidates]
        qualities = [self._quality(p, specs[p], actions[p]) for p in candidates]
        choice = projected_policy(
            costs,
            qualities,
            max_cost_premium=self.max_cost_premium,
            max_reliability_loss=self.max_reliability_loss,
        )
        shares = allocation_probabilities(
            costs,
            qualities,
            eta=float(choice["eta"]),
            exploration=float(choice["exploration"]),
        )
        return {provider: float(shares[index]) for index, provider in enumerate(candidates)}


class HardenedAdaptiveRouter(AdaptiveMonotoneRouter):
    """Lagged, committed, impact-limited menu-adaptive allocation rule."""

    def __init__(
        self,
        *,
        exploration_floor: float = 0.10,
        smoothing_alpha: float = 0.25,
        commitment_epochs: int = 12,
        max_log_share_change: float = math.log(1.5),
        operator_share_cap: float = 0.60,
        reliability_power: float = 1.0,
        operator_groups: Mapping[str, str] | None = None,
        firmness: Mapping[str, float] | None = None,
        raise_exponent_floor: float = 2.0,
        upward_quote_tolerance: float = 0.0,
    ) -> None:
        super().__init__(
            eta=1.25,
            exploration=exploration_floor,
            reliability_power=reliability_power,
        )
        if not 0 < smoothing_alpha <= 1:
            raise ValueError("smoothing_alpha must lie in (0, 1]")
        if commitment_epochs < 1:
            raise ValueError("commitment_epochs must be positive")
        if max_log_share_change <= 0:
            raise ValueError("max_log_share_change must be positive")
        if not 0 < operator_share_cap <= 1:
            raise ValueError("operator_share_cap must lie in (0, 1]")
        if raise_exponent_floor < 0:
            raise ValueError("raise_exponent_floor must be non-negative")
        if upward_quote_tolerance < 0:
            raise ValueError("upward_quote_tolerance must be non-negative")
        self.smoothing_alpha = float(smoothing_alpha)
        self.commitment_epochs = int(commitment_epochs)
        self.max_log_share_change = float(max_log_share_change)
        self.operator_share_cap = float(operator_share_cap)
        self.operator_groups = dict(operator_groups or {})
        self.firmness = {key: float(value) for key, value in (firmness or {}).items()}
        self.raise_exponent_floor = float(raise_exponent_floor)
        self.upward_quote_tolerance = float(upward_quote_tolerance)
        self._epoch = 0
        self._committed_at = -1
        self._eta_by_provider: dict[str, float] = {}
        self._committed_exploration = float(exploration_floor)
        self._smoothed_quotes: dict[str, float] = {}
        self._smoothed_qualities: dict[str, float] = {}
        self._reference_quotes: dict[str, float] = {}
        self._reference_qualities: dict[str, float] = {}
        self._prior_probabilities: dict[str, float] = {}

    @property
    def state(self) -> AdaptivePolicyState:
        return AdaptivePolicyState(
            epoch=self._epoch,
            committed_at=self._committed_at,
            eta_by_provider=dict(self._eta_by_provider),
            exploration=self._committed_exploration,
            smoothed_quotes=dict(self._smoothed_quotes),
            smoothed_qualities=dict(self._smoothed_qualities),
            reference_quotes=dict(self._reference_quotes),
            reference_qualities=dict(self._reference_qualities),
            prior_probabilities=dict(self._prior_probabilities),
        )

    def _observed_quality(
        self, provider: str, spec: ProviderSpec, action: ProviderAction
    ) -> float:
        quality = self._quality(provider, spec, action)
        quality *= min(max(self.firmness.get(provider, 1.0), 0.01), 1.0)
        return min(max(quality, 1e-6), 1.0)

    def _commit(self, candidates: tuple[str, ...]) -> None:
        eta_by_provider: dict[str, float] = {}
        explorations: list[float] = []
        for provider in candidates:
            comparison = [other for other in candidates if other != provider]
            if len(comparison) < 2:
                eta_by_provider[provider] = 1.25
                explorations.append(self.exploration)
                continue
            choice = projected_policy(
                [self._smoothed_quotes[p] for p in comparison],
                [self._smoothed_qualities[p] for p in comparison],
            )
            eta_by_provider[provider] = float(choice["eta"])
            explorations.append(float(choice["exploration"]))
        self._eta_by_provider = eta_by_provider
        self._committed_exploration = max(
            self.exploration,
            float(np.mean(explorations)) if explorations else self.exploration,
        )
        self._reference_quotes = {
            provider: self._smoothed_quotes[provider] for provider in candidates
        }
        self._reference_qualities = {
            provider: self._smoothed_qualities[provider] for provider in candidates
        }
        self._committed_at = self._epoch

    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        candidates = self.eligible(specs, actions)
        if not candidates:
            return {}
        quotes: dict[str, float] = {}
        qualities: dict[str, float] = {}
        current_quotes: dict[str, float] = {}
        raised: dict[str, bool] = {}
        for provider in candidates:
            current_quote = float(actions[provider].quote)
            current_quotes[provider] = current_quote
            lagged_quote = self._smoothed_quotes.get(provider, current_quote)
            # Cuts are admitted gradually; increases are scored immediately.
            quotes[provider] = (
                current_quote
                if current_quote >= lagged_quote
                else self.smoothing_alpha * current_quote
                + (1 - self.smoothing_alpha) * lagged_quote
            )
            raised[provider] = current_quote > lagged_quote + 1e-15
            current_quality = self._observed_quality(
                provider, specs[provider], actions[provider]
            )
            lagged_quality = self._smoothed_qualities.get(provider, current_quality)
            # Degradation enters immediately while an improvement earns trust gradually.
            qualities[provider] = (
                current_quality
                if current_quality <= lagged_quality
                else self.smoothing_alpha * current_quality
                + (1 - self.smoothing_alpha) * lagged_quality
            )
        if not self._eta_by_provider or any(p not in self._eta_by_provider for p in candidates):
            # Initial commitment uses current values but does not mutate smoothing
            # clocks or prior allocations.
            old_quotes, old_qualities = self._smoothed_quotes, self._smoothed_qualities
            self._smoothed_quotes, self._smoothed_qualities = dict(quotes), dict(qualities)
            self._commit(candidates)
            self._smoothed_quotes, self._smoothed_qualities = old_quotes, old_qualities

        scores = {}
        quote_lock_breaches: set[str] = set()
        for provider in candidates:
            base_eta = self._eta_by_provider.get(provider, 1.25)
            response_eta = base_eta
            if raised[provider]:
                response_eta = max(base_eta, self.raise_exponent_floor)
            reference_quote = self._reference_quotes.get(
                provider, self._smoothed_quotes.get(provider, quotes[provider])
            )
            relative_quote = quotes[provider] / reference_quote
            reference_quality = self._reference_qualities.get(
                provider, qualities[provider]
            )
            quality_response = (qualities[provider] / reference_quality) ** (
                self.reliability_power
            )
            quote_lock_breached = (
                current_quotes[provider]
                > reference_quote * (1.0 + self.upward_quote_tolerance) + 1e-15
            )
            if quote_lock_breached:
                scores[provider] = 0.0
                quote_lock_breaches.add(provider)
            elif provider in self._prior_probabilities:
                scores[provider] = (
                    self._prior_probabilities[provider]
                    * quality_response
                    * relative_quote ** (-response_eta)
                )
            else:
                scores[provider] = (
                    qualities[provider] ** self.reliability_power
                    * reference_quote ** (-base_eta)
                    * relative_quote ** (-response_eta)
                )
        epsilon = 0.0 if self._prior_probabilities else self._committed_exploration
        groups = {p: self.operator_groups.get(p, p) for p in candidates}
        mixed = _operator_neutral_probabilities(
            scores,
            groups,
            exploration=epsilon,
            cap=self.operator_share_cap,
            capacities={p: float(specs[p].physical_capacity) for p in candidates},
        )
        bounded = (
            mixed
            if quote_lock_breaches
            else _trust_region(
                mixed,
                {
                    p: value
                    for p, value in self._prior_probabilities.items()
                    if p in mixed
                },
                self.max_log_share_change,
            )
        )
        return bounded

    def advance(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> None:
        """Advance lagged public state exactly once after an epoch."""
        candidates = self.eligible(specs, actions)
        current = self.probabilities(specs, actions)
        alpha = self.smoothing_alpha
        for provider in candidates:
            quote = float(actions[provider].quote)
            quality = self._observed_quality(provider, specs[provider], actions[provider])
            self._smoothed_quotes[provider] = (
                alpha * quote + (1 - alpha) * self._smoothed_quotes.get(provider, quote)
            )
            self._smoothed_qualities[provider] = (
                alpha * quality
                + (1 - alpha) * self._smoothed_qualities.get(provider, quality)
            )
        self._prior_probabilities = current
        self._epoch += 1
        if self._epoch - self._committed_at >= self.commitment_epochs:
            self._commit(candidates)
