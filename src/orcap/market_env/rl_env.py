"""Minimal parallel multi-agent API for the strategic routing kernel.

The wrapper intentionally has no Gymnasium or PettingZoo dependency.  Its reset
and step signatures are small enough for native use and for downstream adapters.
Observations contain public quotes plus the observing provider's own settlement;
they never expose rival cost, physical capacity, or reliability primitives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .kernel import MarketKernel
from .types import EpochResult, ProviderAction


@dataclass(frozen=True)
class ProviderObservation:
    """Public market state and one provider's private realized feedback."""

    epoch: int
    demand: int
    public_quotes: tuple[tuple[str, float], ...]
    own_profit: float
    own_attempted_requests: int
    own_served_requests: int
    own_technical_failures: int
    own_capacity_rejections: int


@dataclass(frozen=True)
class ParallelStep:
    """One transition in the parallel provider game."""

    observations: dict[str, ProviderObservation]
    rewards: dict[str, float]
    terminations: dict[str, bool]
    truncations: dict[str, bool]
    infos: dict[str, dict[str, float | int]]
    market_result: EpochResult


class StrategicRoutingParallelEnv:
    """Parallel provider game backed by exact request-level settlement."""

    def __init__(self, kernel: MarketKernel, *, horizon_epochs: int) -> None:
        if not isinstance(horizon_epochs, int) or horizon_epochs < 1:
            raise ValueError("horizon_epochs must be a positive integer")
        self.kernel = kernel
        self.horizon_epochs = horizon_epochs
        self.possible_agents = tuple(sorted(kernel.specs))
        self.agents = self.possible_agents
        self._epoch = 0
        self._last_actions: dict[str, ProviderAction] = {}
        self._last_demand = 0
        self._last_result: EpochResult | None = None

    def _observations(self) -> dict[str, ProviderObservation]:
        public_quotes = tuple(
            sorted((provider, action.quote) for provider, action in self._last_actions.items())
        )
        result_by_provider = (
            {row.provider: row for row in self._last_result.providers}
            if self._last_result is not None
            else {}
        )
        output = {}
        for provider in self.possible_agents:
            row = result_by_provider.get(provider)
            output[provider] = ProviderObservation(
                epoch=self._epoch,
                demand=self._last_demand,
                public_quotes=public_quotes,
                own_profit=0.0 if row is None else row.profit,
                own_attempted_requests=0 if row is None else row.attempted_requests,
                own_served_requests=0 if row is None else row.served_requests,
                own_technical_failures=0 if row is None else row.technical_failures,
                own_capacity_rejections=0 if row is None else row.capacity_rejections,
            )
        return output

    def reset(self, *, seed: int) -> dict[str, ProviderObservation]:
        self.kernel.reset(seed=seed)
        self.agents = self.possible_agents
        self._epoch = 0
        self._last_actions = {}
        self._last_demand = 0
        self._last_result = None
        return self._observations()

    def step(
        self,
        actions: Mapping[str, ProviderAction],
        *,
        demand: int,
    ) -> ParallelStep:
        if not self.agents:
            raise RuntimeError("step called after the episode terminated; reset first")
        result = self.kernel.step(actions, demand=demand)
        self._epoch += 1
        self._last_actions = dict(actions)
        self._last_demand = demand
        self._last_result = result
        done = self._epoch >= self.horizon_epochs
        rewards = {row.provider: row.profit for row in result.providers}
        terminations = dict.fromkeys(self.possible_agents, done)
        truncations = dict.fromkeys(self.possible_agents, False)
        infos = {
            row.provider: {
                "attempted_requests": row.attempted_requests,
                "served_requests": row.served_requests,
                "technical_failures": row.technical_failures,
                "capacity_rejections": row.capacity_rejections,
            }
            for row in result.providers
        }
        observations = self._observations()
        if done:
            self.agents = ()
        return ParallelStep(
            observations=observations,
            rewards=rewards,
            terminations=terminations,
            truncations=truncations,
            infos=infos,
            market_result=result,
        )
