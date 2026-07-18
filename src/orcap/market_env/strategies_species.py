"""Behavioral provider strategies fitted to the observed pricing species.

Implements the `ProviderStrategy` protocol (strategies.py) for the four
split-sample-validated species from wf13 / the calibration bundle:

  adopter            quotes exactly the anchor (author) price; follows anchor
                     moves the same epoch; tiny idiosyncratic hazard
  below_static       targets anchor*exp(margin) with a rare repricing hazard
  below_active       best-responds every epoch: one tick below the cheapest
                     rival, floored at cost*(1+margin_floor)
  above              rigid premium anchor*exp(delta); repricing hazard only
                     restores the target after anchor moves

Instances hold a seeded numpy Generator and their current quote, so the same
seed reproduces the same trajectory (their kernel is deterministic given
actions). At the daily epoch grain, per-epoch hazards equal min(cadence, 1).

Constructed from the calibration bundle via `species_strategy(...)` — no
hand-set behavior parameters anywhere.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from .types import ProviderAction, ProviderSpec

EPS_TICK = 0.01  # one grid tick, as a fraction of the anchor price


def _anchor(public_quotes: Mapping[str, float], anchor_provider: str) -> float:
    if anchor_provider not in public_quotes:
        raise KeyError(f"anchor provider {anchor_provider!r} not in public quotes")
    return float(public_quotes[anchor_provider])


@dataclass
class AdopterStrategy:
    anchor_provider: str
    idio_hazard: float = 0.0
    seed: int = 0
    admitted_capacity_fraction: float = 1.0
    _rng: np.random.Generator = field(init=False, repr=False)
    _idio_mult: float = field(init=False, default=1.0)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def act(self, spec: ProviderSpec, public_quotes: Mapping[str, float]) -> ProviderAction:
        del spec
        anchor = _anchor(public_quotes, self.anchor_provider)
        if self.idio_hazard > 0 and self._rng.random() < self.idio_hazard:
            self._idio_mult = float(self._rng.choice([1.0 - EPS_TICK, 1.0, 1.0 + EPS_TICK]))
        return ProviderAction(anchor * self._idio_mult, self.admitted_capacity_fraction)


@dataclass
class TargetHazardStrategy:
    """Shared machinery: hold current quote; with per-epoch probability
    `hazard`, re-target `anchor * exp(margin_log)`. Also re-targets whenever
    the anchor itself moved (reference-price adjustment, observed for both
    static undercutters and premium providers)."""

    anchor_provider: str
    margin_log: float
    hazard: float
    follow_anchor: bool = True
    seed: int = 0
    admitted_capacity_fraction: float = 1.0
    _rng: np.random.Generator = field(init=False, repr=False)
    _current: float | None = field(init=False, default=None)
    _last_anchor: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def act(self, spec: ProviderSpec, public_quotes: Mapping[str, float]) -> ProviderAction:
        del spec
        anchor = _anchor(public_quotes, self.anchor_provider)
        target = anchor * float(np.exp(self.margin_log))
        anchor_moved = (
            self._last_anchor is not None
            and abs(anchor - self._last_anchor) > 1e-12
        )
        if (
            self._current is None
            or (self.follow_anchor and anchor_moved)
            or self._rng.random() < self.hazard
        ):
            self._current = target
        self._last_anchor = anchor
        return ProviderAction(self._current, self.admitted_capacity_fraction)


@dataclass
class ActiveUndercutterStrategy:
    """Every epoch: one tick below the cheapest rival, floored at
    cost*(1+margin_floor). The observed multi-change-per-day cadence is
    subsumed at the daily epoch grain (the agent is always at its best
    response by end of day)."""

    margin_floor: float = 0.10
    tick_frac: float = EPS_TICK
    admitted_capacity_fraction: float = 1.0

    def act(self, spec: ProviderSpec, public_quotes: Mapping[str, float]) -> ProviderAction:
        rivals = [q for p, q in public_quotes.items() if p != spec.provider and q > 0]
        floor = spec.marginal_cost * (1 + self.margin_floor)
        if not rivals:
            return ProviderAction(max(floor, 1e-9), self.admitted_capacity_fraction)
        target = min(rivals) * (1 - self.tick_frac)
        return ProviderAction(max(floor, target, 1e-9), self.admitted_capacity_fraction)


def species_strategy(
    anchor_class: str,
    species_params: Mapping[str, Mapping],
    anchor_provider: str,
    *,
    margin_log: float | None = None,
    seed: int = 0,
):
    """Build a strategy for one provider from the calibration bundle's
    ``species`` block. ``margin_log`` overrides the class median with the
    provider's own fitted margin when known (pairs.parquet)."""
    p = species_params[anchor_class]
    hazard = min(float(p["changes_per_day"]), 1.0)
    if anchor_class == "adopter":
        return AdopterStrategy(anchor_provider, idio_hazard=hazard, seed=seed)
    if anchor_class == "below_active":
        return ActiveUndercutterStrategy()
    if anchor_class in ("below_static", "above"):
        m = margin_log if margin_log is not None else float(p["margin_log_median"])
        return TargetHazardStrategy(anchor_provider, m, hazard, seed=seed)
    raise ValueError(f"unknown anchor_class {anchor_class!r}")
