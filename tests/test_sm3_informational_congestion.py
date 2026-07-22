from __future__ import annotations

import numpy as np
import pytest

from orcap.analysis.sm3_informational_congestion import (
    bandit_panel,
    congestion_value,
    continuous_optimum,
    correlation_for_effective_rank,
    effective_rank_equicorrelation,
    scaling_panel,
)


@pytest.mark.parametrize("size,rank", [(4, 1.0), (8, 3.0), (16, 16.0)])
def test_equicorrelation_rank_inverse(size: int, rank: float) -> None:
    rho = correlation_for_effective_rank(size, rank)
    assert effective_rank_equicorrelation(size, rho) == pytest.approx(rank)


def test_continuous_optimum_matches_dense_grid() -> None:
    providers = 100
    rank = 10.0
    optimum = continuous_optimum(providers=providers, signal_rank=rank)
    grid = np.linspace(0, providers, 100_001)
    values = congestion_value(grid, providers=providers, signal_rank=rank)
    assert grid[int(np.argmax(values))] == pytest.approx(optimum, abs=0.002)


def test_scaling_recovers_minority_and_linear_exponents() -> None:
    panel = scaling_panel(
        provider_counts=(64, 128, 256, 512, 1024, 2048),
        rank_exponents=(0.0, 1.0),
    )
    estimates = panel.groupby("rank_exponent_beta")["estimated_kstar_exponent"].first()
    assert estimates.loc[0.0] == pytest.approx(0.5, abs=0.03)
    assert estimates.loc[1.0] == pytest.approx(1.0, abs=0.01)


def test_bandit_panel_holds_total_provider_count_fixed() -> None:
    panel = bandit_panel(
        provider_counts=(4,),
        rank_exponents=(0.0, 1.0),
        memories=(0.0,),
        algorithms=("ucb",),
        seeds=1,
        horizon=80,
    )
    assert set(panel["providers"]) == {4}
    assert panel["active"].between(1, 3).all()
    assert np.allclose(panel["active_density"], panel["active"] / 4)
    assert set(panel["rank_exponent_beta"]) == {0.0, 1.0}
