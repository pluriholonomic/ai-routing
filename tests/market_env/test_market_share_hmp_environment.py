from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from orcap.market_env.experiments_market_share_hmp import (
    critical_memory_screen,
    public_price_calibration,
)
from orcap.market_env.market_share_hmp import (
    MarketShareHMPConfig,
    correlated_signals,
    paired_intervention,
    shuffle_signal_order,
)


def test_signal_order_intervention_preserves_each_marginal_exactly():
    config = MarketShareHMPConfig(horizon=200, burn_in=40, n_active=3, seed=11)
    signals = correlated_signals(config)
    shuffled = shuffle_signal_order(signals, seed=23)
    for provider in range(config.n_active):
        assert np.array_equal(np.sort(signals[:, provider]), np.sort(shuffled[:, provider]))
    assert not np.array_equal(signals, shuffled)


def test_k_one_is_zero_wedge_negative_control_for_every_learner():
    for algorithm in ("ucb", "thompson", "epsilon", "q_learning"):
        config = MarketShareHMPConfig(
            horizon=120,
            burn_in=30,
            n_active=1,
            algorithm=algorithm,
            seed=3,
        )
        coupled, shuffled = paired_intervention(config)
        assert coupled["path_wedge"] == 0
        assert shuffled["path_wedge"] == 0
        assert coupled["arm"] == "coupled"
        assert shuffled["arm"] == "marginal_preserving_shuffle"


def test_public_price_calibration_uses_relative_glm52_quotes(tmp_path):
    protocol = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "config/glm52_market_share_hmp_v1.toml").read_text()
    )
    rows = []
    for run in ("20260722T025500Z", "20260722T030500Z"):
        for provider, quote in (("Novita", 0.5e-6), ("Together", 1.0e-6)):
            rows.append(
                {
                    "run_ts": run,
                    "model_id": "z-ai/glm-5.2",
                    "provider_name": provider,
                    "price_prompt": quote,
                    "price_completion": quote,
                    "price_request": 0.0,
                }
            )
    path = tmp_path / "curated/endpoints_snapshots/dt=2026-07-22"
    path.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(path / "part.parquet", index=False)
    calibration = public_price_calibration(tmp_path, protocol)
    assert calibration["status"] == "public_glm52_relative_price_calibration"
    assert calibration["low_price"] == 0.5
    assert calibration["marginal_cost"] == 0.125
    assert calibration["snapshots"] == 1


def test_critical_memory_screen_selects_on_training_and_scores_holdout():
    rows = []
    for active in (1, 3):
        for seed in range(6):
            for memory in (0.0, 0.5, 0.8, 0.95, 0.99):
                effect = 0.0 if active == 1 else -10 - 100 * max(memory - 0.8, 0)
                rows.append(
                    {
                        "n_active": active,
                        "signal_to_noise": 2.0,
                        "router_eta": 1.648,
                        "algorithm": "ucb",
                        "seed": seed,
                        "reward_memory": memory,
                        "horizon": 1000,
                        "learning_time__coupled_minus_shuffled": effect + seed,
                    }
                )
    screen = critical_memory_screen(pd.DataFrame(rows))
    assert screen["multiple_active"]["status"] == "estimated"
    assert screen["multiple_active"]["selected_threshold"] in {0.5, 0.8, 0.95}
    assert screen["multiple_active"]["holdout_seeds"] == [3, 4, 5]
