"""Steering router variants (counterfactual mechanisms; this session's file).

CutPenaltyRouter implements the empirically observed JRW-inverse steering:
the probe panel shows the default router selects a cheapest provider with a
recent price CUT far less often than one without (3.9% vs 23.3%). Modeled as
a multiplicative weight penalty theta on any provider whose current quote is
below its quote `memory` epochs ago. Stateful across epochs: call
`advance(quotes)` once per epoch after collecting actions.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping

from .routers import InversePriceRouter
from .types import ProviderAction, ProviderSpec


class CutPenaltyRouter(InversePriceRouter):
    """``cheapest_only=True`` penalizes a flagged provider only while it
    holds the cheapest quote — the exact conditional our probe panel
    measured (3.9% vs 23.3% is cheapest-with-recent-cut). The default
    (False) penalizes any recent cutter. The two coincide at symmetric
    profiles (any strict cut makes the deviant cheapest) and bracket the
    unobserved treatment of non-cheapest cutters."""

    def __init__(self, exponent: float = 2.0, theta: float = 0.17, memory: int = 7,
                 cheapest_only: bool = False) -> None:
        super().__init__(exponent=exponent)
        if not 0 <= theta <= 1:
            raise ValueError("theta must lie in [0, 1]")
        self.theta = float(theta)
        self.memory = int(memory)
        self.cheapest_only = bool(cheapest_only)
        self._history: deque[dict[str, float]] = deque(maxlen=self.memory)

    def advance(self, quotes: Mapping[str, float]) -> None:
        self._history.append(dict(quotes))

    def _recently_cut(self, provider: str, quote: float) -> bool:
        return any(
            provider in past and quote < past[provider] - 1e-12
            for past in self._history
        )

    def probabilities(
        self,
        specs: Mapping[str, ProviderSpec],
        actions: Mapping[str, ProviderAction],
    ) -> dict[str, float]:
        base = super().probabilities(specs, actions)
        if not base:
            return base
        cheapest = min(base, key=lambda p: (actions[p].quote, p))
        def penalized(p: str) -> bool:
            if not self._recently_cut(p, actions[p].quote):
                return False
            return (p == cheapest) if self.cheapest_only else True
        weights = {
            p: w * (self.theta if penalized(p) else 1.0)
            for p, w in base.items()
        }
        total = sum(weights.values())
        if total <= 0:
            return base
        return {p: w / total for p, w in weights.items()}
