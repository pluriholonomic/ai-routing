"""Multi-agent market-share HMP environment with an exact signal-order intervention."""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

from ..market_share_hmp import elasticity_identity, finite_path_elasticity, routing_shares

Algorithm = Literal["ucb", "thompson", "epsilon", "q_learning"]


@dataclass(frozen=True)
class MarketShareHMPConfig:
    horizon: int = 2500
    burn_in: int = 500
    demand_per_period: int = 120
    n_active: int = 3
    n_anchors: int = 3
    low_price: float = 0.65
    high_price: float = 1.0
    anchor_price: float = 1.0
    marginal_cost: float = 0.20
    router_eta: float = 1.6482780609377246
    signal_to_noise: float = 2.0
    common_correlation: float = 0.8
    reward_memory: float = 0.8
    algorithm: Algorithm = "ucb"
    epsilon: float = 0.05
    ucb_bonus: float = 1.0
    discount: float = 0.95
    learning_relative_error: float = 0.10
    seed: int = 0

    def __post_init__(self) -> None:
        if self.horizon < 50 or not 0 <= self.burn_in < self.horizon:
            raise ValueError("invalid horizon or burn-in")
        if self.n_active < 1 or self.n_anchors < 1 or self.demand_per_period < 1:
            raise ValueError("provider counts and demand must be positive")
        if not 0 < self.marginal_cost < self.low_price < self.high_price:
            raise ValueError("prices must satisfy cost < low < high")
        if self.anchor_price <= 0 or self.router_eta < 0 or self.signal_to_noise <= 0:
            raise ValueError("invalid router, anchor price, or signal-to-noise")
        if not 0 <= self.common_correlation <= 1 or not 0 <= self.reward_memory < 1:
            raise ValueError("correlation and reward memory are outside their domains")
        if self.algorithm not in {"ucb", "thompson", "epsilon", "q_learning"}:
            raise ValueError(f"unsupported learner: {self.algorithm}")


class _Learner:
    def __init__(self, config: MarketShareHMPConfig, seed: int) -> None:
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.counts = np.zeros(2, dtype=int)
        self.values = np.zeros(2, dtype=float)
        self.q = np.zeros((config.n_active + 1, 2), dtype=float)

    def act(self, state: int, step: int) -> int:
        unseen = np.flatnonzero(self.counts == 0)
        if len(unseen):
            return int(unseen[0])
        if self.config.algorithm in {"epsilon", "q_learning"} and (
            self.rng.random() < self.config.epsilon
        ):
            return int(self.rng.integers(2))
        if self.config.algorithm == "ucb":
            bonus = self.config.ucb_bonus * np.sqrt(
                np.log(max(step, 2)) / np.maximum(self.counts, 1)
            )
            return int(np.argmax(self.values + bonus))
        if self.config.algorithm == "thompson":
            draw = self.rng.normal(self.values, 1.0 / np.sqrt(self.counts + 1.0))
            return int(np.argmax(draw))
        if self.config.algorithm == "q_learning":
            return int(np.argmax(self.q[state]))
        return int(np.argmax(self.values))

    def update(self, state: int, action: int, reward: float, next_state: int) -> None:
        self.counts[action] += 1
        memory = self.config.reward_memory
        if memory == 0:
            self.values[action] = reward
        else:
            self.values[action] = memory * self.values[action] + (1.0 - memory) * reward
        if self.config.algorithm == "q_learning":
            target = reward + self.config.discount * float(self.q[next_state].max())
            self.q[state, action] += (1.0 - memory) * (target - self.q[state, action])


def correlated_signals(config: MarketShareHMPConfig) -> np.ndarray:
    rng = np.random.default_rng(config.seed * 10_007 + 41)
    common = rng.normal(size=(config.horizon, 1))
    independent = rng.normal(size=(config.horizon, config.n_active))
    rho = config.common_correlation
    return np.sqrt(rho) * common + np.sqrt(1.0 - rho) * independent


def shuffle_signal_order(signals: np.ndarray, *, seed: int) -> np.ndarray:
    values = np.asarray(signals, dtype=float)
    if values.ndim != 2:
        raise ValueError("signals must be two dimensional")
    rng = np.random.default_rng(seed)
    output = values.copy()
    for column in range(values.shape[1]):
        output[:, column] = rng.permutation(values[:, column])
    return output


def _safe_correlation(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2 or np.std(left) <= 1e-12 or np.std(right) <= 1e-12:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _target_path_elasticity(config: MarketShareHMPConfig) -> float:
    low = [config.low_price] * config.n_active + [config.anchor_price] * config.n_anchors
    high = [config.high_price] * config.n_active + [config.anchor_price] * config.n_anchors
    low_share = routing_shares(low, eta=config.router_eta)[0]
    high_share = routing_shares(high, eta=config.router_eta)[0]
    return float(
        -(np.log(low_share) - np.log(high_share))
        / (np.log(config.low_price) - np.log(config.high_price))
    )


def simulate(
    config: MarketShareHMPConfig,
    *,
    signals: np.ndarray | None = None,
    arm: str = "coupled",
) -> dict:
    signal = correlated_signals(config) if signals is None else np.asarray(signals, dtype=float)
    if signal.shape != (config.horizon, config.n_active):
        raise ValueError("signal matrix does not match the configured environment")
    learners = [
        _Learner(config, config.seed * 7919 + provider * 101 + 7)
        for provider in range(config.n_active)
    ]
    rng = np.random.default_rng(config.seed * 65_537 + 19)
    actions = np.zeros((config.horizon, config.n_active), dtype=np.int8)
    shares = np.zeros((config.horizon, config.n_active + config.n_anchors), dtype=float)
    routes = np.zeros_like(shares, dtype=int)
    weighted_price = np.zeros(config.horizon, dtype=float)
    state = 0
    low_visits = high_visits = 0
    low_routes = high_routes = 0
    target = _target_path_elasticity(config)
    learning_time: int | None = None
    for step in range(config.horizon):
        selected = np.array([learner.act(state, step + 1) for learner in learners], dtype=np.int8)
        actions[step] = selected
        active_prices = np.where(selected == 0, config.low_price, config.high_price)
        prices = np.concatenate([active_prices, np.full(config.n_anchors, config.anchor_price)])
        shares[step] = routing_shares(prices, eta=config.router_eta)
        routes[step] = rng.multinomial(config.demand_per_period, shares[step])
        weighted_price[step] = float(np.dot(prices, shares[step]))
        next_state = int(np.sum(selected == 0))
        structural = (active_prices - config.marginal_cost) * (
            routes[step, : config.n_active] / config.demand_per_period
        )
        scale = max(float(np.mean(np.abs(structural))), 0.01) / config.signal_to_noise
        rewards = structural + scale * signal[step]
        for provider, learner in enumerate(learners):
            learner.update(state, int(selected[provider]), float(rewards[provider]), next_state)
        state = next_state
        if np.all(selected == 0):
            low_visits += 1
            low_routes += int(routes[step, 0])
        elif np.all(selected == 1):
            high_visits += 1
            high_routes += int(routes[step, 0])
        if learning_time is None and min(low_visits, high_visits) >= 10:
            low_estimate = (low_routes + 0.5) / (low_visits * config.demand_per_period + 1.0)
            high_estimate = (high_routes + 0.5) / (high_visits * config.demand_per_period + 1.0)
            estimate = -(np.log(low_estimate) - np.log(high_estimate)) / (
                np.log(config.low_price) - np.log(config.high_price)
            )
            if abs(estimate - target) / max(abs(target), 1e-12) <= config.learning_relative_error:
                learning_time = step + 1
    tail = slice(config.burn_in, None)
    pair_correlations = [
        _safe_correlation(actions[tail, left], actions[tail, right])
        for left in range(config.n_active)
        for right in range(left + 1, config.n_active)
    ]
    signal_correlations = [
        _safe_correlation(signal[:, left], signal[:, right])
        for left in range(config.n_active)
        for right in range(left + 1, config.n_active)
    ]
    low_prices = [config.low_price] * config.n_active + [config.anchor_price] * config.n_anchors
    low_shares = routing_shares(low_prices, eta=config.router_eta)
    identity = elasticity_identity(
        low_shares,
        focal=0,
        cutters=range(config.n_active),
        eta=config.router_eta,
    )
    return {
        **asdict(config),
        "arm": arm,
        "target_path_elasticity": target,
        "elasticity_learning_time": learning_time,
        "elasticity_learned": learning_time is not None,
        "mean_action_correlation": float(np.mean(pair_correlations)) if pair_correlations else 0.0,
        "signal_realized_correlation": (
            float(np.mean(signal_correlations)) if signal_correlations else 0.0
        ),
        "all_low_share": float(np.mean(np.all(actions[tail] == 0, axis=1))),
        "all_high_share": float(np.mean(np.all(actions[tail] == 1, axis=1))),
        "mean_active_group_share": float(shares[tail, : config.n_active].sum(axis=1).mean()),
        "mean_anchor_group_share": float(shares[tail, config.n_active :].sum(axis=1).mean()),
        "mean_buyer_price": float(weighted_price[tail].mean()),
        "path_wedge": identity["path_wedge"],
        "unilateral_elasticity": identity["unilateral_elasticity"],
        "path_elasticity": identity["path_elasticity"],
    }


def paired_intervention(config: MarketShareHMPConfig) -> tuple[dict, dict]:
    signals = correlated_signals(config)
    coupled = simulate(config, signals=signals, arm="coupled")
    decoupled = simulate(
        config,
        signals=shuffle_signal_order(signals, seed=config.seed * 10_007 + 53),
        arm="marginal_preserving_shuffle",
    )
    return coupled, decoupled


def run_factorial(
    protocol: dict,
    *,
    seeds: int | None = None,
    horizon: int | None = None,
    calibration: dict | None = None,
) -> pd.DataFrame:
    settings = protocol["simulation"]
    calibrated = calibration or {}
    low_price = float(calibrated.get("low_price", 0.65))
    high_price = float(calibrated.get("high_price", 1.0))
    anchor_price = float(calibrated.get("anchor_price", 1.0))
    marginal_cost = float(calibrated.get("marginal_cost", 0.20))
    rows = []
    seed_count = int(seeds if seeds is not None else settings["seeds"])
    for active, snr, memory, eta, algorithm, seed in itertools.product(
        settings["active_counts"],
        settings["signal_to_noise"],
        settings["reward_memory"],
        settings["router_etas"],
        settings["algorithms"],
        range(seed_count),
    ):
        config = MarketShareHMPConfig(
            horizon=int(horizon or settings["horizon"]),
            burn_in=min(int(settings["burn_in"]), int(horizon or settings["horizon"]) // 2),
            demand_per_period=int(settings["demand_per_period"]),
            n_active=int(active),
            low_price=low_price,
            high_price=high_price,
            anchor_price=anchor_price,
            marginal_cost=marginal_cost,
            router_eta=float(eta),
            signal_to_noise=float(snr),
            reward_memory=float(memory),
            algorithm=str(algorithm),
            learning_relative_error=float(settings["learning_relative_error"]),
            seed=int(seed),
        )
        rows.extend(paired_intervention(config))
    return pd.DataFrame(rows)


def controlled_router_factorial(protocol: dict, *, calibration: dict | None = None) -> pd.DataFrame:
    calibrated = calibration or {}
    low_price = float(calibrated.get("low_price", 0.65))
    anchor_price = float(calibrated.get("anchor_price", 1.0))
    rows = []
    for active, eta, cut in itertools.product(
        protocol["simulation"]["active_counts"],
        protocol["study"]["eta_sensitivity"],
        (0.02, 0.05, 0.10, 0.20, 0.30),
    ):
        prices = [low_price] * int(active) + [anchor_price] * 3
        # For K=1 the unilateral and all-active paths are the same estimand.
        # Emit that negative-control cell once so it cannot be double weighted
        # in plots or downstream summaries.
        cutter_counts = (1,) if int(active) == 1 else (1, int(active))
        for cutters in cutter_counts:
            result = finite_path_elasticity(
                prices,
                focal=0,
                cutters=range(cutters),
                cut_fraction=float(cut),
                eta=float(eta),
            )
            rows.append(
                {
                    "n_active": int(active),
                    "n_cutters": cutters,
                    "router_eta": float(eta),
                    "cut_fraction": float(cut),
                    **result,
                }
            )
    return pd.DataFrame(rows)
