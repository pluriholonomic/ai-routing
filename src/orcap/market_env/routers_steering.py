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
    def __init__(self, exponent: float = 2.0, theta: float = 0.17, memory: int = 7) -> None:
        super().__init__(exponent=exponent)
        if not 0 <= theta <= 1:
            raise ValueError("theta must lie in [0, 1]")
        self.theta = float(theta)
        self.memory = int(memory)
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
        weights = {
            p: w * (self.theta if self._recently_cut(p, actions[p].quote) else 1.0)
            for p, w in base.items()
        }
        total = sum(weights.values())
        if total <= 0:
            return base
        return {p: w / total for p, w in weights.items()}
