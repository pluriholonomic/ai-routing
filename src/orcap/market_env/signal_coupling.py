"""Auditable multi-provider pricing environment for HMP signal coupling.

Providers observe only their own realized reward.  A router allocates a unit of
demand using inverse-price weights.  Signal columns can be independently
permuted to break contemporaneous and temporal coupling while preserving every
provider's marginal signal distribution exactly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

Algorithm = Literal["ucb", "epsilon", "static_low", "static_high"]


@dataclass(frozen=True)
class SignalCouplingConfig:
    horizon: int = 3000
    burn_in: int = 750
    n_providers: int = 2
    low_price: float = 0.65
    high_price: float = 1.0
    marginal_cost: float = 0.20
    router_eta: float = 5.0
    signal_to_noise: float = 2.0
    common_correlation: float = 0.5
    reward_memory: float = 0.8
    epsilon: float = 0.05
    ucb_bonus: float = 0.5
    algorithms: tuple[Algorithm, ...] = ("ucb", "ucb")
    seed: int = 0

    def __post_init__(self) -> None:
        if self.horizon < 20 or not 0 <= self.burn_in < self.horizon:
            raise ValueError("invalid simulation horizon or burn-in")
        if self.n_providers < 2 or len(self.algorithms) != self.n_providers:
            raise ValueError("algorithms must contain one entry per provider")
        if not 0 < self.marginal_cost < self.low_price < self.high_price:
            raise ValueError("prices must satisfy cost < low < high")
        if self.router_eta < 0 or self.signal_to_noise <= 0:
            raise ValueError("router eta must be nonnegative and SNR positive")
        if not 0 <= self.common_correlation <= 1:
            raise ValueError("common correlation must lie in [0, 1]")
        if not 0 <= self.reward_memory < 1:
            raise ValueError("reward memory must lie in [0, 1)")
        if not 0 <= self.epsilon <= 1 or self.ucb_bonus < 0:
            raise ValueError("invalid exploration parameter")


@dataclass
class SignalCouplingResult:
    config: SignalCouplingConfig
    actions: np.ndarray
    prices: np.ndarray
    rewards: np.ndarray
    shares: np.ndarray
    signals: np.ndarray
    summary: dict[str, float | int | str]


class _Learner:
    def __init__(self, algorithm: Algorithm, config: SignalCouplingConfig, seed: int) -> None:
        self.algorithm = algorithm
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.values = np.array([0.0, 0.0], dtype=float)
        self.counts = np.zeros(2, dtype=int)
        self.total = 0

    def act(self) -> int:
        if self.algorithm == "static_low":
            return 0
        if self.algorithm == "static_high":
            return 1
        missing = np.flatnonzero(self.counts == 0)
        if len(missing):
            return int(missing[0])
        if self.algorithm == "epsilon" and self.rng.random() < self.config.epsilon:
            return int(self.rng.integers(2))
        index = self.values.copy()
        if self.algorithm == "ucb":
            index += self.config.ucb_bonus * np.sqrt(
                np.log(max(self.total, 2)) / np.maximum(self.counts, 1)
            )
        best = np.flatnonzero(np.isclose(index, index.max()))
        return int(1 if 1 in best else best[0])

    def update(self, action: int, reward: float) -> None:
        if self.algorithm.startswith("static"):
            return
        self.total += 1
        self.counts[action] += 1
        memory = self.config.reward_memory
        if memory == 0:
            self.values[action] = reward
        else:
            self.values[action] = memory * self.values[action] + (1 - memory) * reward


def correlated_signals(config: SignalCouplingConfig) -> np.ndarray:
    rng = np.random.default_rng(config.seed * 10_007 + 17)
    common = rng.normal(size=(config.horizon, 1))
    independent = rng.normal(size=(config.horizon, config.n_providers))
    rho = config.common_correlation
    return np.sqrt(rho) * common + np.sqrt(1 - rho) * independent


def shuffle_signal_order(signals: np.ndarray, *, seed: int) -> np.ndarray:
    """Break cross-provider ordering and preserve each column's multiset exactly."""
    signals = np.asarray(signals, dtype=float)
    if signals.ndim != 2:
        raise ValueError("signals must be a two-dimensional array")
    rng = np.random.default_rng(seed)
    shuffled = signals.copy()
    for provider in range(signals.shape[1]):
        shuffled[:, provider] = rng.permutation(signals[:, provider])
    return shuffled


def router_shares(prices: np.ndarray, eta: float) -> np.ndarray:
    prices = np.asarray(prices, dtype=float)
    if np.any(prices <= 0):
        raise ValueError("router prices must be positive")
    weights = np.power(prices, -float(eta))
    return weights / weights.sum()


def stage_payoffs(config: SignalCouplingConfig) -> dict[str, float | bool]:
    low, high, cost = config.low_price, config.high_price, config.marginal_cost
    both_low = float((low - cost) * 0.5)
    both_high = float((high - cost) * 0.5)
    low_vs_high = float((low - cost) * router_shares(np.array([low, high]), config.router_eta)[0])
    high_vs_low = float((high - cost) * router_shares(np.array([high, low]), config.router_eta)[0])
    return {
        "low_vs_high": low_vs_high,
        "both_high": both_high,
        "both_low": both_low,
        "high_vs_low": high_vs_low,
        "prisoners_dilemma_ordering": bool(low_vs_high > both_high > both_low > high_vs_low),
    }


def _safe_correlation(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or np.std(a) <= 1e-12 or np.std(b) <= 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def simulate_signal_coupling(
    config: SignalCouplingConfig,
    *,
    signals: np.ndarray | None = None,
    arm: str = "coupled",
) -> SignalCouplingResult:
    signal = correlated_signals(config) if signals is None else np.asarray(signals, dtype=float)
    if signal.shape != (config.horizon, config.n_providers):
        raise ValueError("signal matrix does not match horizon and provider count")
    learners = [
        _Learner(algorithm, config, config.seed * 7919 + provider * 101 + 3)
        for provider, algorithm in enumerate(config.algorithms)
    ]
    actions = np.zeros((config.horizon, config.n_providers), dtype=np.int8)
    prices = np.zeros_like(actions, dtype=float)
    shares = np.zeros_like(actions, dtype=float)
    rewards = np.zeros_like(actions, dtype=float)
    price_values = np.array([config.low_price, config.high_price], dtype=float)
    noise_scale = 0.10 / config.signal_to_noise
    for time in range(config.horizon):
        actions[time] = [learner.act() for learner in learners]
        prices[time] = price_values[actions[time]]
        shares[time] = router_shares(prices[time], config.router_eta)
        structural = (prices[time] - config.marginal_cost) * shares[time]
        rewards[time] = structural + noise_scale * signal[time]
        for provider, learner in enumerate(learners):
            learner.update(int(actions[time, provider]), float(rewards[time, provider]))
    tail = slice(config.burn_in, None)
    innovations = np.diff(actions[tail].astype(float), axis=0)
    exploration_innovations = np.diff(actions[: max(config.burn_in, 2)].astype(float), axis=0)
    pair_correlations = [
        _safe_correlation(innovations[:, i], innovations[:, j])
        for i in range(config.n_providers)
        for j in range(i + 1, config.n_providers)
    ]
    exploration_pair_correlations = [
        _safe_correlation(exploration_innovations[:, i], exploration_innovations[:, j])
        for i in range(config.n_providers)
        for j in range(i + 1, config.n_providers)
    ]
    price_correlations = [
        _safe_correlation(prices[tail, i], prices[tail, j])
        for i in range(config.n_providers)
        for j in range(i + 1, config.n_providers)
    ]
    summary: dict[str, float | int | str] = {
        **asdict(config),
        "algorithms": "_".join(config.algorithms),
        "arm": arm,
        "innovation_correlation": float(np.mean(pair_correlations)),
        "exploration_innovation_correlation": float(np.mean(exploration_pair_correlations)),
        "price_correlation": float(np.mean(price_correlations)),
        "all_high_share": float(np.mean(np.all(actions[tail] == 1, axis=1))),
        "all_low_share": float(np.mean(np.all(actions[tail] == 0, axis=1))),
        "mean_price": float(np.sum(prices[tail] * shares[tail], axis=1).mean()),
        "mean_hhi": float(np.square(shares[tail]).sum(axis=1).mean()),
        "mean_provider_reward": float(rewards[tail].mean()),
        "signal_realized_correlation": float(
            np.mean(
                [
                    _safe_correlation(signal[:, i], signal[:, j])
                    for i in range(config.n_providers)
                    for j in range(i + 1, config.n_providers)
                ]
            )
        ),
    }
    return SignalCouplingResult(config, actions, prices, rewards, shares, signal, summary)


def paired_signal_intervention(
    config: SignalCouplingConfig,
) -> tuple[SignalCouplingResult, SignalCouplingResult]:
    signals = correlated_signals(config)
    coupled = simulate_signal_coupling(config, signals=signals, arm="coupled")
    shuffled = simulate_signal_coupling(
        config,
        signals=shuffle_signal_order(signals, seed=config.seed * 10_007 + 29),
        arm="marginal_preserving_shuffle",
    )
    return coupled, shuffled


def algorithm_mix(name: str, n_providers: int = 2) -> tuple[Algorithm, ...]:
    mapping: dict[str, tuple[Algorithm, ...]] = {
        "ucb_ucb": ("ucb", "ucb"),
        "ucb_epsilon": ("ucb", "epsilon"),
        "epsilon_epsilon": ("epsilon", "epsilon"),
        "ucb_static": ("ucb", "static_low"),
    }
    value = mapping.get(name)
    if value is None or len(value) != n_providers:
        raise ValueError(f"unsupported algorithm mix: {name}")
    return value


def run_factorial(protocol: dict, *, seeds: int | None = None) -> pd.DataFrame:
    sim = protocol["simulation"]
    rows = []
    seed_count = int(seeds if seeds is not None else sim["seeds"])
    for snr, correlation, memory, eta, mix, seed in itertools_product(
        sim["signal_to_noise"],
        sim["common_correlations"],
        sim["reward_memory"],
        sim["router_etas"],
        sim["algorithm_mixes"],
        range(seed_count),
    ):
        config = SignalCouplingConfig(
            horizon=int(sim["horizon"]),
            burn_in=int(sim["burn_in"]),
            signal_to_noise=float(snr),
            common_correlation=float(correlation),
            reward_memory=float(memory),
            router_eta=float(eta),
            algorithms=algorithm_mix(str(mix)),
            seed=int(seed),
        )
        coupled, shuffled = paired_signal_intervention(config)
        rows.extend([coupled.summary, shuffled.summary])
    return pd.DataFrame(rows)


def itertools_product(*values):
    """Local import boundary keeps the environment module dependency-light."""
    import itertools

    return itertools.product(*values)
