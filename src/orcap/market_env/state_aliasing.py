"""Exact and learned responses to a history-dependent cut penalty.

This module is the controlled mechanism laboratory for E-SIM5.  A provider
chooses between a high quote and a lower permanent-cut quote while rivals are
fixed.  The router penalizes a quote whenever it is below any of the provider's
last ``memory`` quotes.  With two actions the Markov state is a binary history,
so the exact discounted optimum can be enumerated and compared with Q-learners
that do or do not observe that history.

The experiment deliberately does not model collusion or infer live-router
conduct.  It tests whether omitting a payoff-relevant router state can account
for a bounded learner's high-price path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Literal

import numpy as np

LOW = 0
HIGH = 1
Observation = Literal["history", "aliased"]
COMMIT_LOW = 2


@dataclass(frozen=True)
class BinaryCutPenaltyMDP:
    """Two-action discounted pricing MDP against fixed rival quotes."""

    low_price: float
    high_price: float
    marginal_cost: float
    rival_prices: tuple[float, ...]
    exponent: float = 2.0
    theta: float = 0.17
    memory: int = 7
    gamma: float = 0.95
    demand: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.low_price < self.high_price:
            raise ValueError("prices must satisfy 0 < low_price < high_price")
        if self.marginal_cost >= self.low_price:
            raise ValueError("low price must exceed marginal cost")
        if not self.rival_prices or any(price <= 0 for price in self.rival_prices):
            raise ValueError("rival prices must be nonempty and positive")
        if self.memory < 1:
            raise ValueError("memory must be positive")
        if not 0 <= self.theta <= 1:
            raise ValueError("theta must lie in [0, 1]")
        if not 0 <= self.gamma < 1:
            raise ValueError("gamma must lie in [0, 1)")

    @property
    def n_states(self) -> int:
        return 1 << self.memory

    @property
    def initial_state(self) -> int:
        """All-high prehistory, matching the E-SIM4 terminal profile."""
        return self.n_states - 1

    def price(self, action: int) -> float:
        if action == LOW:
            return self.low_price
        if action == HIGH:
            return self.high_price
        raise ValueError("action must be LOW=0 or HIGH=1")

    def history(self, state: int) -> tuple[int, ...]:
        if not 0 <= state < self.n_states:
            raise ValueError("state outside binary history space")
        return tuple((state >> shift) & 1 for shift in reversed(range(self.memory)))

    def state(self, history: tuple[int, ...]) -> int:
        if len(history) != self.memory or any(bit not in (LOW, HIGH) for bit in history):
            raise ValueError("history must contain exactly memory binary actions")
        value = 0
        for bit in history:
            value = (value << 1) | bit
        return value

    def transition(self, state: int, action: int) -> int:
        self.price(action)  # validate action
        mask = self.n_states - 1
        return ((state << 1) & mask) | action

    def is_penalized(self, state: int, action: int) -> bool:
        quote = self.price(action)
        return any(quote < self.price(past) - 1e-12 for past in self.history(state))

    def reward(self, state: int, action: int) -> float:
        quote = self.price(action)
        own_weight = quote ** (-self.exponent)
        if self.is_penalized(state, action):
            own_weight *= self.theta
        rival_weight = sum(price ** (-self.exponent) for price in self.rival_prices)
        share = own_weight / (own_weight + rival_weight)
        return self.demand * share * (quote - self.marginal_cost)

    def reward_table(self) -> np.ndarray:
        return np.asarray(
            [[self.reward(state, action) for action in (LOW, HIGH)]
             for state in range(self.n_states)],
            dtype=float,
        )

    def permanent_low_value(self) -> float:
        """Closed-form value of cutting now and staying low forever."""
        penalized = self.reward(self.initial_state, LOW)
        unpenalized = self.reward(0, LOW)
        return (
            (1 - self.gamma**self.memory) * penalized
            + self.gamma**self.memory * unpenalized
        ) / (1 - self.gamma)

    def permanent_high_value(self) -> float:
        return self.reward(self.initial_state, HIGH) / (1 - self.gamma)


@dataclass(frozen=True)
class ExactSolution:
    values: np.ndarray
    policy: np.ndarray
    bellman_residual: float
    iterations: int


def solve_exact(
    mdp: BinaryCutPenaltyMDP,
    *,
    tolerance: float = 1e-13,
    max_iterations: int = 100_000,
) -> ExactSolution:
    """Value iteration over every binary history."""
    rewards = mdp.reward_table()
    successors = np.asarray(
        [[mdp.transition(state, action) for action in (LOW, HIGH)]
         for state in range(mdp.n_states)],
        dtype=int,
    )
    values = np.zeros(mdp.n_states, dtype=float)
    for _iteration in range(1, max_iterations + 1):
        q_values = rewards + mdp.gamma * values[successors]
        updated = q_values.max(axis=1)
        if float(np.max(np.abs(updated - values))) <= tolerance:
            values = updated
            break
        values = updated
    else:
        raise RuntimeError("value iteration did not converge")
    q_values = rewards + mdp.gamma * values[successors]
    policy = np.argmax(q_values, axis=1).astype(np.int8)
    residual = float(np.max(np.abs(values - q_values.max(axis=1))))
    return ExactSolution(values, policy, residual, _iteration)


@dataclass
class BinaryQAgent:
    """Q-learner with either the Markov history or a one-action alias."""

    memory: int
    observation: Observation
    alpha: float = 0.15
    gamma: float = 0.95
    beta: float = 2e-5
    seed: int = 0
    _rng: np.random.Generator = field(init=False, repr=False)
    q: np.ndarray = field(init=False, repr=False)
    t: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.observation not in ("history", "aliased"):
            raise ValueError("observation must be 'history' or 'aliased'")
        self._rng = np.random.default_rng(self.seed)
        n_observations = (1 << self.memory) if self.observation == "history" else 2
        self.q = np.zeros((n_observations, 2), dtype=float)

    def observe(self, full_state: int) -> int:
        if self.observation == "history":
            return full_state
        return full_state & 1

    def act(self, observation: int) -> int:
        epsilon = float(np.exp(-self.beta * self.t))
        self.t += 1
        if self._rng.random() < epsilon:
            return int(self._rng.integers(2))
        row = self.q[observation]
        return int(self._rng.choice(np.flatnonzero(row == row.max())))

    def greedy(self, observation: int) -> int:
        return int(np.argmax(self.q[observation]))

    def update(
        self,
        observation: int,
        action: int,
        reward: float,
        next_observation: int,
    ) -> None:
        target = reward + self.gamma * self.q[next_observation].max()
        self.q[observation, action] += self.alpha * (
            target - self.q[observation, action]
        )


def evaluate_deterministic_policy(
    mdp: BinaryCutPenaltyMDP,
    full_policy: np.ndarray,
) -> np.ndarray:
    """Solve the exact value of a deterministic policy on all full states."""
    if full_policy.shape != (mdp.n_states,):
        raise ValueError("full_policy has wrong shape")
    matrix = np.eye(mdp.n_states)
    rewards = np.empty(mdp.n_states, dtype=float)
    for state in range(mdp.n_states):
        action = int(full_policy[state])
        successor = mdp.transition(state, action)
        matrix[state, successor] -= mdp.gamma
        rewards[state] = mdp.reward(state, action)
    return np.linalg.solve(matrix, rewards)


@dataclass(frozen=True)
class OptionOutcome:
    discounted_reward: float
    successor: int
    duration: int
    primitive_actions: tuple[int, ...]


def option_outcome(
    mdp: BinaryCutPenaltyMDP,
    state: int,
    action: int,
    *,
    max_duration: int | None = None,
) -> OptionOutcome:
    """Return the exact semi-Markov transition for a primitive or cut option."""
    if action in (LOW, HIGH):
        actions = (action,)
    elif action == COMMIT_LOW:
        actions = (LOW,) * (mdp.memory + 1)
    else:
        raise ValueError("option action must be LOW, HIGH, or COMMIT_LOW")
    if max_duration is not None:
        if max_duration < 1:
            raise ValueError("max_duration must be positive")
        actions = actions[:max_duration]
    discounted_reward = 0.0
    current = state
    for offset, primitive in enumerate(actions):
        discounted_reward += mdp.gamma**offset * mdp.reward(current, primitive)
        current = mdp.transition(current, primitive)
    return OptionOutcome(discounted_reward, current, len(actions), actions)


def solve_exact_with_option(
    mdp: BinaryCutPenaltyMDP,
    *,
    tolerance: float = 1e-13,
    max_iterations: int = 100_000,
) -> ExactSolution:
    """Exact semi-Markov optimum after adding the payoff-equivalent cut option."""
    outcomes = [
        [option_outcome(mdp, state, action) for action in range(3)]
        for state in range(mdp.n_states)
    ]
    values = np.zeros(mdp.n_states, dtype=float)
    for _iteration in range(1, max_iterations + 1):
        q_values = np.asarray([
            [
                outcome.discounted_reward
                + mdp.gamma**outcome.duration * values[outcome.successor]
                for outcome in state_outcomes
            ]
            for state_outcomes in outcomes
        ])
        updated = q_values.max(axis=1)
        if float(np.max(np.abs(updated - values))) <= tolerance:
            values = updated
            break
        values = updated
    else:
        raise RuntimeError("option value iteration did not converge")
    q_values = np.asarray([
        [
            outcome.discounted_reward
            + mdp.gamma**outcome.duration * values[outcome.successor]
            for outcome in state_outcomes
        ]
        for state_outcomes in outcomes
    ])
    policy = np.argmax(q_values, axis=1).astype(np.int8)
    residual = float(np.max(np.abs(values - q_values.max(axis=1))))
    return ExactSolution(values, policy, residual, _iteration)


def evaluate_deterministic_option_policy(
    mdp: BinaryCutPenaltyMDP,
    policy: np.ndarray,
) -> np.ndarray:
    """Exact value of a deterministic semi-Markov policy on full histories."""
    if policy.shape != (mdp.n_states,):
        raise ValueError("policy has wrong shape")
    matrix = np.eye(mdp.n_states)
    rewards = np.empty(mdp.n_states, dtype=float)
    for state in range(mdp.n_states):
        outcome = option_outcome(mdp, state, int(policy[state]))
        matrix[state, outcome.successor] -= mdp.gamma**outcome.duration
        rewards[state] = outcome.discounted_reward
    return np.linalg.solve(matrix, rewards)


@dataclass
class OptionQAgent:
    """History-aware SMDP Q-learner with a persistent-low option."""

    memory: int
    alpha: float = 0.15
    gamma: float = 0.95
    beta: float = 2e-5
    seed: int = 0
    _rng: np.random.Generator = field(init=False, repr=False)
    q: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        self.q = np.zeros((1 << self.memory, 3), dtype=float)

    def act(self, state: int, environment_step: int) -> int:
        epsilon = float(np.exp(-self.beta * environment_step))
        if self._rng.random() < epsilon:
            return int(self._rng.integers(3))
        row = self.q[state]
        return int(self._rng.choice(np.flatnonzero(row == row.max())))

    def greedy(self, state: int) -> int:
        return int(np.argmax(self.q[state]))

    def update(self, state: int, action: int, outcome: OptionOutcome) -> None:
        target = (
            outcome.discounted_reward
            + self.gamma**outcome.duration * self.q[outcome.successor].max()
        )
        self.q[state, action] += self.alpha * (target - self.q[state, action])


def train_option_q(
    mdp: BinaryCutPenaltyMDP,
    *,
    seed: int,
    alpha: float = 0.15,
    beta: float = 2e-5,
    train_transitions: int = 300_000,
    stable_window: int = 100_000,
    evaluation_transitions: int = 10_000,
) -> dict[str, object]:
    """Train with the frozen environment-transition rather than decision budget."""
    agent = OptionQAgent(
        mdp.memory,
        alpha=alpha,
        gamma=mdp.gamma,
        beta=beta,
        seed=seed,
    )
    state = mdp.initial_state
    environment_step = 0
    last_policy = agent.q.argmax(axis=1).copy()
    last_change_step = 0
    decisions = 0
    option_decisions = 0
    while environment_step < train_transitions:
        action = agent.act(state, environment_step)
        remaining = train_transitions - environment_step
        outcome = option_outcome(mdp, state, action, max_duration=remaining)
        agent.update(state, action, outcome)
        state = outcome.successor
        environment_step += outcome.duration
        decisions += 1
        option_decisions += action == COMMIT_LOW
        if environment_step // 1_000 > (environment_step - outcome.duration) // 1_000:
            policy = agent.q.argmax(axis=1)
            if not np.array_equal(policy, last_policy):
                last_change_step = environment_step
                last_policy = policy.copy()

    policy = agent.q.argmax(axis=1).astype(np.int8)
    policy_values = evaluate_deterministic_option_policy(mdp, policy)
    exact = solve_exact(mdp)
    exact_option = solve_exact_with_option(mdp)
    exact_value_gap = float(np.max(np.abs(exact.values - exact_option.values)))
    state = mdp.initial_state
    evaluation_step = 0
    primitive_actions: list[int] = []
    evaluation_decisions = 0
    evaluation_option_decisions = 0
    while evaluation_step < evaluation_transitions:
        action = int(policy[state])
        outcome = option_outcome(
            mdp,
            state,
            action,
            max_duration=evaluation_transitions - evaluation_step,
        )
        primitive_actions.extend(outcome.primitive_actions)
        state = outcome.successor
        evaluation_step += outcome.duration
        evaluation_decisions += 1
        evaluation_option_decisions += action == COMMIT_LOW
    primitive_array = np.asarray(primitive_actions, dtype=np.int8)
    prices = np.where(primitive_array == LOW, mdp.low_price, mdp.high_price)
    regret = float(exact.values[mdp.initial_state] - policy_values[mdp.initial_state])
    return {
        "observation": "history_with_commit_option",
        "seed": seed,
        "alpha": alpha,
        "beta": beta,
        "train_transitions": train_transitions,
        "train_decisions": decisions,
        "train_option_decision_share": option_decisions / decisions,
        "evaluation_transitions": evaluation_transitions,
        "evaluation_decisions": evaluation_decisions,
        "evaluation_option_decision_share": (
            evaluation_option_decisions / evaluation_decisions
        ),
        "policy_stable_last_window": (
            train_transitions - last_change_step >= stable_window
        ),
        "last_policy_change_step": last_change_step,
        "first_action": int(policy[mdp.initial_state]),
        "first_primitive_action": int(
            LOW if policy[mdp.initial_state] == COMMIT_LOW
            else policy[mdp.initial_state]
        ),
        "first_action_agrees_exact": bool(
            (LOW if policy[mdp.initial_state] == COMMIT_LOW
             else policy[mdp.initial_state])
            == exact.policy[mdp.initial_state]
        ),
        "median_price": float(np.median(prices)),
        "low_action_share": float(np.mean(primitive_array == LOW)),
        "discounted_value": float(policy_values[mdp.initial_state]),
        "discounted_regret": max(0.0, regret),
        "exact_option_value_gap": exact_value_gap,
        "policy": policy.tolist(),
        "q_table": agent.q.tolist(),
    }


def train_q(
    mdp: BinaryCutPenaltyMDP,
    observation: Observation,
    *,
    seed: int,
    alpha: float = 0.15,
    beta: float = 2e-5,
    train_steps: int = 300_000,
    stable_window: int = 100_000,
    evaluation_steps: int = 10_000,
) -> dict[str, object]:
    """Train exactly ``train_steps`` and evaluate the frozen greedy policy."""
    agent = BinaryQAgent(
        mdp.memory,
        observation,
        alpha=alpha,
        gamma=mdp.gamma,
        beta=beta,
        seed=seed,
    )
    rewards = mdp.reward_table()
    successors = np.asarray(
        [[mdp.transition(state, action) for action in (LOW, HIGH)]
         for state in range(mdp.n_states)],
        dtype=np.int16,
    )
    state = mdp.initial_state
    last_policy = agent.q.argmax(axis=1).copy()
    last_change_step = 0
    for step in range(train_steps):
        observed = agent.observe(state)
        action = agent.act(observed)
        reward = float(rewards[state, action])
        next_state = int(successors[state, action])
        next_observed = agent.observe(next_state)
        agent.update(observed, action, reward, next_observed)
        state = next_state
        if (step + 1) % 1_000 == 0:
            policy = agent.q.argmax(axis=1)
            if not np.array_equal(policy, last_policy):
                last_change_step = step + 1
                last_policy = policy.copy()

    full_policy = np.asarray(
        [agent.greedy(agent.observe(state)) for state in range(mdp.n_states)],
        dtype=np.int8,
    )
    policy_values = evaluate_deterministic_policy(mdp, full_policy)
    exact = solve_exact(mdp)
    state = mdp.initial_state
    actions: list[int] = []
    prices: list[float] = []
    for _ in range(evaluation_steps):
        action = int(full_policy[state])
        actions.append(action)
        prices.append(mdp.price(action))
        state = mdp.transition(state, action)
    regret = float(exact.values[mdp.initial_state] - policy_values[mdp.initial_state])
    return {
        "observation": observation,
        "seed": seed,
        "alpha": alpha,
        "beta": beta,
        "train_steps": train_steps,
        "evaluation_steps": evaluation_steps,
        "policy_stable_last_window": train_steps - last_change_step >= stable_window,
        "last_policy_change_step": last_change_step,
        "first_action": int(full_policy[mdp.initial_state]),
        "first_action_agrees_exact": bool(
            full_policy[mdp.initial_state] == exact.policy[mdp.initial_state]
        ),
        "median_price": float(np.median(prices)),
        "low_action_share": float(np.mean(np.asarray(actions) == LOW)),
        "discounted_value": float(policy_values[mdp.initial_state]),
        "discounted_regret": max(0.0, regret),
        "full_policy": full_policy.tolist(),
        "q_table": agent.q.tolist(),
    }


def enumerate_histories(memory: int) -> tuple[tuple[int, ...], ...]:
    """Public helper used by tests and artifact diagnostics."""
    return tuple(product((LOW, HIGH), repeat=memory))
