"""Tests for the elastic-demand power-router theorem."""

from __future__ import annotations

from orcap.analysis.sm1b_elastic_power_router import elastic_panel, summary


def test_sm1b_frozen_grid_passes_numerical_best_response_validation() -> None:
    panel = elastic_panel()
    assert len(panel) == 19 * 4 * 4
    failures = panel[~panel["global_best_response_pass"]]
    assert failures.empty
    assert panel["best_response_absolute_error"].max() < 1e-4
    assert (panel["welfare_ratio"] <= 1 + 1e-12).all()
    assert (panel["welfare_ratio"] > 0).all()


def test_sm1b_summary_preserves_theory_and_novelty_boundaries() -> None:
    result = summary(elastic_panel())
    assert (
        result["evidence_status"]
        == "proved_eta2_epsilon2_equilibrium_plus_numerical_general_audit"
    )
    assert result["global_best_response_failures"] == 0
    assert result["inverse_square_epsilon2_all_n_markup_exact"]
    assert result["inverse_square_epsilon2_all_n_welfare_ratio_exact"]
    assert "calibrated effect" in result["claim_boundary"]
    assert "established novelty claim" in result["claim_boundary"]
