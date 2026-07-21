from __future__ import annotations

from dataclasses import replace

import numpy as np

from orcap.market_env.signal_coupling import (
    SignalCouplingConfig,
    correlated_signals,
    paired_signal_intervention,
    router_shares,
    shuffle_signal_order,
    simulate_signal_coupling,
    stage_payoffs,
)


def test_focal_stage_game_has_registered_prisoners_dilemma_ordering():
    payoffs = stage_payoffs(SignalCouplingConfig(horizon=100, burn_in=20))
    assert payoffs["prisoners_dilemma_ordering"] is True
    assert payoffs["low_vs_high"] > payoffs["both_high"]
    assert payoffs["both_high"] > payoffs["both_low"]
    assert payoffs["both_low"] > payoffs["high_vs_low"]


def test_router_shares_are_probabilities_and_price_monotone():
    shares = router_shares(np.array([0.5, 1.0, 2.0]), eta=2)
    assert np.isclose(shares.sum(), 1)
    assert shares[0] > shares[1] > shares[2]


def test_marginal_preserving_shuffle_is_exact_and_breaks_order():
    config = SignalCouplingConfig(horizon=500, burn_in=100, common_correlation=0.95, seed=4)
    signals = correlated_signals(config)
    shuffled = shuffle_signal_order(signals, seed=5)
    for provider in range(config.n_providers):
        assert np.array_equal(np.sort(signals[:, provider]), np.sort(shuffled[:, provider]))
    assert np.corrcoef(signals[:, 0], signals[:, 1])[0, 1] > 0.8
    assert abs(np.corrcoef(shuffled[:, 0], shuffled[:, 1])[0, 1]) < 0.2


def test_simulation_is_seed_replayable():
    config = SignalCouplingConfig(horizon=300, burn_in=50, seed=11)
    first = simulate_signal_coupling(config)
    second = simulate_signal_coupling(config)
    assert np.array_equal(first.actions, second.actions)
    assert np.array_equal(first.rewards, second.rewards)
    assert first.summary == second.summary


def test_paired_intervention_uses_same_signal_marginals():
    config = SignalCouplingConfig(
        horizon=800,
        burn_in=200,
        common_correlation=0.9,
        signal_to_noise=4,
        seed=12,
    )
    coupled, shuffled = paired_signal_intervention(config)
    for provider in range(config.n_providers):
        assert np.array_equal(
            np.sort(coupled.signals[:, provider]),
            np.sort(shuffled.signals[:, provider]),
        )
    assert coupled.summary["arm"] == "coupled"
    assert shuffled.summary["arm"] == "marginal_preserving_shuffle"


def test_heterogeneous_algorithm_arm_runs_without_private_information():
    config = SignalCouplingConfig(
        horizon=400,
        burn_in=100,
        algorithms=("ucb", "epsilon"),
        seed=3,
    )
    result = simulate_signal_coupling(config)
    assert result.summary["algorithms"] == "ucb_epsilon"
    assert 0 <= result.summary["mean_hhi"] <= 1
    static = simulate_signal_coupling(replace(config, algorithms=("ucb", "static_low")))
    assert static.actions.shape == result.actions.shape
