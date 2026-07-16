from __future__ import annotations

import pandas as pd
import pytest

from orcap.analysis.pm5_menu_simulation import (
    event_level_size_power,
    exact_cluster_sign_flip,
    known_clock_size_power,
    sim2_empirical_calibration,
    simulate_known_clock_panel,
)


def test_known_clock_panel_is_deterministic_and_nonreactive_null_reads_no_rival() -> None:
    first, metadata = simulate_known_clock_panel(
        rho=0,
        seed=17,
        n_models=4,
        n_providers=3,
        n_ticks=72,
    )
    second, repeated = simulate_known_clock_panel(
        rho=0,
        seed=17,
        n_models=4,
        n_providers=3,
        n_ticks=72,
    )
    pd.testing.assert_frame_equal(first, second)
    assert metadata == repeated
    assert len(first) == 4 * 3 * 72
    assert first["price"].gt(0).all()
    assert metadata["scheduled_refreshes"] > 0
    assert metadata["reactive_replacements"] == 0


def test_event_level_simulation_has_fixed_target_and_increasing_power() -> None:
    panel = pd.DataFrame(
        {
            "model_id": [f"m{index % 4}" for index in range(40)],
            "global_menu_match_probability": [0.2 + 0.1 * (index % 3) for index in range(40)],
        }
    )
    rows, summary = event_level_size_power(
        panel,
        rhos=(0.0, 0.5),
        replications=100,
        bootstrap_draws=100,
        seed=31,
    )
    assert len(rows) == 200
    null = summary[summary["rho"].eq(0)].iloc[0]
    alternative = summary[summary["rho"].eq(0.5)].iloc[0]
    assert null["target_excess"] == pytest.approx(0)
    assert alternative["target_excess"] > 0.25
    assert alternative["mean_estimate"] > null["mean_estimate"]
    assert alternative["joint_promotion_rate"] > null["joint_promotion_rate"]


def test_known_clock_experiment_runs_unchanged_event_extractor() -> None:
    rows, summary = known_clock_size_power(
        rhos=(0.0, 0.5),
        replications=2,
        bootstrap_draws=100,
        seed=41,
        n_models=4,
        n_providers=3,
        n_ticks=96,
        workers=1,
    )
    assert len(rows) == 4
    assert rows["n_events"].gt(0).all()
    assert set(summary["rho"]) == {0.0, 0.5}
    assert summary["null_size_criterion_passes"].nunique() == 1


def test_exact_cluster_sign_flip_enumerates_every_assignment() -> None:
    panel = pd.DataFrame(
        {
            "model_id": ["a", "a", "b"],
            "exact_lagged_rival_match": [1.0, 1.0, 0.0],
            "global_menu_match_probability": [0.5, 0.5, 0.5],
        }
    )
    result = exact_cluster_sign_flip(panel)
    assert result["n_clusters"] == 2
    assert result["n_assignments"] == 4
    assert result["estimate"] == pytest.approx(1 / 6)
    assert result["one_sided_p"] == pytest.approx(0.5)
    assert result["two_sided_p"] == pytest.approx(1.0)


def test_sim2_empirical_calibration_fails_when_probabilities_are_outside() -> None:
    empirical = pd.DataFrame(
        {
            "exact_lagged_rival_match": [0.0, 1.0],
            "global_menu_match_probability": [0.1, 0.1],
        }
    )
    simulated = pd.DataFrame(
        {
            "rho": [0.0, 0.0, 0.0],
            "n_events": [10, 11, 12],
            "exact_landing_share": [0.8, 0.85, 0.9],
            "menu_probability": [0.9, 0.91, 0.92],
            "estimate": [-0.1, -0.06, -0.02],
        }
    )
    table, summary = sim2_empirical_calibration(empirical, simulated)
    assert len(table) == 4
    assert not table["inside_sim2_null_p05_p95"].any()
    assert summary["empirically_calibrated_on_registered_probabilities"] is False
    assert summary["required_description"].startswith("stress-test")
