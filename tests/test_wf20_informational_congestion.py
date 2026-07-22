from __future__ import annotations

import numpy as np

from orcap.analysis.wf20_informational_congestion import rank_and_factor_transport


def test_independent_signals_have_near_full_effective_rank():
    rng = np.random.default_rng(3)
    train = rng.normal(size=(2_000, 6))
    holdout = rng.normal(size=(2_000, 6))
    result = rank_and_factor_transport(train, holdout)
    assert result["effective_rank"] > 5.7
    assert abs(result["factor_optimism_gap"]) < 0.03


def test_stable_common_factor_has_low_rank_and_transports():
    rng = np.random.default_rng(4)
    loadings = np.linspace(0.8, 1.2, 6)
    train = rng.normal(size=(2_000, 1)) * loadings + 0.15 * rng.normal(size=(2_000, 6))
    holdout = rng.normal(size=(2_000, 1)) * loadings + 0.15 * rng.normal(size=(2_000, 6))
    result = rank_and_factor_transport(train, holdout)
    assert result["effective_rank"] < 1.2
    assert result["leading_factor_share_holdout"] > 0.9
    assert abs(result["factor_optimism_gap"]) < 0.03


def test_spurious_train_factor_is_exposed_by_holdout_optimism():
    rng = np.random.default_rng(5)
    loadings = np.ones(6)
    train = rng.normal(size=(1_000, 1)) * loadings + 0.20 * rng.normal(size=(1_000, 6))
    holdout = rng.normal(size=(1_000, 6))
    result = rank_and_factor_transport(train, holdout)
    assert result["leading_factor_share_train"] > 0.9
    assert result["leading_factor_share_holdout"] < 0.25
    assert result["factor_optimism_gap"] > 0.65
