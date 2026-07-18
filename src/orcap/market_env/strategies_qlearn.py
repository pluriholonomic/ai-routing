"""Calvano-comparable tabular Q-learning provider agents.

Replicates the Calvano-Calzolari-Denicolo-Pastorello (2020 AER) design on
this market's demand system: the router IS the demand curve (inverse-square
weights = softmax in log price), so their repeated Bertrand-with-logit-demand
game nests directly.

Training uses the router's EXPECTED allocation (router.probabilities x
demand x margin), which is the exact expectation of the request-level kernel
under non-binding capacity and unit reliability — the kernel samples requests
from the same probabilities. That keeps 1e6-epoch runs to seconds; the
kernel is used for evaluation and known-answer checks, not the inner loop.

State: memory-1 (own grid index, min-rival grid index) — Calvano's baseline.
Action: choose a grid price (15 log-spaced anchor multiples; the anchor is an
exact grid point). Learning runs REQUIRE stationary synthetic demand;
experiments_sim enforces that replay demand never reaches a learner.

Convergence rule (Calvano): greedy policy unchanged for `stable_window`
consecutive epochs, hard cap `max_epochs`.

Collusion index: Delta = (pi - pi_N)/(pi_M - pi_N) with pi_N from iterated
best response on the grid and pi_M from the best joint symmetric price.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from .routers import RouterMechanism
from .types import ProviderAction, ProviderSpec

N_GRID = 15
GRID_LO, GRID_HI = 0.4, 1.6


def price_grid(anchor: float = 1.0, n: int = N_GRID) -> np.ndarray:
    """Log-spaced grid in anchor multiples containing the anchor exactly."""
    g = anchor * np.exp(np.linspace(np.log(GRID_LO), np.log(GRID_HI), n))
    g[np.argmin(np.abs(g - anchor))] = anchor
    return g


def expected_profits(
    prices: Mapping[str, float],
    costs: Mapping[str, float],
    router: RouterMechanism,
    demand: float,
) -> dict[str, float]:
    """Expected per-epoch profit under the router's first-choice allocation."""
    specs = {
        p: ProviderSpec(provider=p, marginal_cost=costs[p], physical_capacity=1)
        for p in prices
    }
    actions = {p: ProviderAction(prices[p]) for p in prices}
    probs = router.probabilities(specs, actions)
    return {
        p: demand * probs.get(p, 0.0) * (prices[p] - costs[p]) for p in prices
    }


def nash_profit(
    grid: np.ndarray, mc: float, router: RouterMechanism, demand: float,
    n_agents: int = 2, max_iter: int = 200,
) -> float:
    """Symmetric-game Nash profit by iterated best response on the grid."""
    idx = [0] * n_agents
    names = [f"a{i}" for i in range(n_agents)]
    for _ in range(max_iter):
        changed = False
        for i in range(n_agents):
            best, best_pi = idx[i], -np.inf
            for k in range(len(grid)):
                prices = {names[j]: float(grid[idx[j] if j != i else k])
                          for j in range(n_agents)}
                pi = expected_profits(prices, dict.fromkeys(names, mc), router, demand)[names[i]]
                if pi > best_pi + 1e-12:
                    best, best_pi = k, pi
            if best != idx[i]:
                idx[i], changed = best, True
        if not changed:
            break
    prices = {names[j]: float(grid[idx[j]]) for j in range(n_agents)}
    pis = expected_profits(prices, dict.fromkeys(names, mc), router, demand)
    return float(np.mean(list(pis.values())))


def monopoly_profit(
    grid: np.ndarray, mc: float, router: RouterMechanism, demand: float,
    n_agents: int = 2,
) -> float:
    """Best joint symmetric price (the cartel benchmark)."""
    names = [f"a{i}" for i in range(n_agents)]
    best = -np.inf
    for k in range(len(grid)):
        prices = dict.fromkeys(names, float(grid[k]))
        pis = expected_profits(prices, dict.fromkeys(names, mc), router, demand)
        best = max(best, float(np.mean(list(pis.values()))))
    return best


@dataclass
class TabularQAgent:
    """One learner. States are (own_idx, min_rival_idx); Q is dense."""

    grid: np.ndarray
    alpha: float = 0.15
    gamma: float = 0.95
    beta: float = 2e-5           # epsilon_t = exp(-beta * t)
    seed: int = 0
    q_init: float = 0.0
    _rng: np.random.Generator = field(init=False, repr=False)
    Q: np.ndarray = field(init=False, repr=False)
    t: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        n = len(self.grid)
        self._rng = np.random.default_rng(self.seed)
        self.Q = np.full((n * n, n), float(self.q_init))

    def state_index(self, own_idx: int, rival_idx: int) -> int:
        return own_idx * len(self.grid) + rival_idx

    def act_index(self, state: int) -> int:
        eps = float(np.exp(-self.beta * self.t))
        self.t += 1
        if self._rng.random() < eps:
            return int(self._rng.integers(len(self.grid)))
        row = self.Q[state]
        return int(self._rng.choice(np.flatnonzero(row == row.max())))

    def greedy(self, state: int) -> int:
        row = self.Q[state]
        return int(np.argmax(row))

    def update(self, state: int, action: int, reward: float, next_state: int) -> None:
        target = reward + self.gamma * self.Q[next_state].max()
        self.Q[state, action] += self.alpha * (target - self.Q[state, action])


@dataclass(frozen=True)
class FrozenQStrategy:
    """ProviderStrategy adapter for a trained agent (greedy, no learning) —
    used when a learner is dropped into a species-world slot for evaluation."""

    agent: TabularQAgent
    rival_of_interest: str | None = None

    def act(self, spec: ProviderSpec, public_quotes: Mapping[str, float]) -> ProviderAction:
        grid = self.agent.grid
        own = public_quotes.get(spec.provider, float(grid[len(grid) // 2]))
        rivals = [q for p, q in public_quotes.items() if p != spec.provider and q > 0]
        rival = min(rivals) if rivals else own
        s = self.agent.state_index(
            int(np.argmin(np.abs(grid - own))), int(np.argmin(np.abs(grid - rival)))
        )
        return ProviderAction(float(grid[self.agent.greedy(s)]))


def train_symmetric(
    router: RouterMechanism,
    n_agents: int = 2,
    mc: float = 0.2,
    demand: float = 1.0,
    anchor: float = 1.0,
    max_epochs: int = 2_000_000,
    stable_window: int = 100_000,
    seed: int = 0,
    check_every: int = 1000,
) -> dict:
    """Calvano loop: simultaneous Q-learners on the grid, expected-profit
    rewards, convergence when every agent's greedy policy is stable."""
    grid = price_grid(anchor)
    names = [f"a{i}" for i in range(n_agents)]
    costs = dict.fromkeys(names, mc)
    agents = [TabularQAgent(grid, seed=seed * 100 + i) for i in range(n_agents)]
    idx = [len(grid) // 2] * n_agents
    stable_since, last_policies = 0, None
    profits_trace = []
    for t in range(max_epochs):
        states = [
            agents[i].state_index(idx[i], min(idx[j] for j in range(n_agents) if j != i))
            for i in range(n_agents)
        ]
        acts = [agents[i].act_index(states[i]) for i in range(n_agents)]
        prices = {names[i]: float(grid[acts[i]]) for i in range(n_agents)}
        pis = expected_profits(prices, costs, router, demand)
        next_idx = acts
        next_states = [
            agents[i].state_index(next_idx[i], min(next_idx[j] for j in range(n_agents) if j != i))
            for i in range(n_agents)
        ]
        for i in range(n_agents):
            agents[i].update(states[i], acts[i], pis[names[i]], next_states[i])
        idx = next_idx
        if t % check_every == 0:
            pol = tuple(a.Q.argmax(axis=1).tobytes() for a in agents)
            if pol == last_policies:
                stable_since += check_every
            else:
                stable_since, last_policies = 0, pol
            profits_trace.append(float(np.mean(list(pis.values()))))
            if stable_since >= stable_window:
                break
    # converged play: run greedy from last state
    for _ in range(200):
        states = [
            agents[i].state_index(idx[i], min(idx[j] for j in range(n_agents) if j != i))
            for i in range(n_agents)
        ]
        idx = [agents[i].greedy(states[i]) for i in range(n_agents)]
    prices = {names[i]: float(grid[idx[i]]) for i in range(n_agents)}
    pis = expected_profits(prices, costs, router, demand)
    pi_bar = float(np.mean(list(pis.values())))
    pi_n = nash_profit(grid, mc, router, demand, n_agents)
    pi_m = monopoly_profit(grid, mc, router, demand, n_agents)
    delta = (pi_bar - pi_n) / (pi_m - pi_n) if pi_m > pi_n else None
    return {
        "epochs_run": t + 1,
        "converged": stable_since >= stable_window,
        "final_prices": {k: round(v, 4) for k, v in prices.items()},
        "mean_profit": round(pi_bar, 5),
        "pi_nash": round(pi_n, 5),
        "pi_monopoly": round(pi_m, 5),
        "calvano_delta": round(delta, 4) if delta is not None else None,
        "profit_trace_tail": [round(x, 4) for x in profits_trace[-5:]],
        "agents": agents,
        "grid": grid,
    }
