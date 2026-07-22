"""Tests for the contestable-entry theory analysis bundle."""

from __future__ import annotations

from orcap.analysis.contestable_entry_mechanism import (
    adaptive_panel,
    elasticity_panel,
    entry_panel,
    learning_panel,
    summarize,
)


def test_contestable_entry_panels_preserve_theory_boundaries() -> None:
    entry = entry_panel()
    elasticity = elasticity_panel()
    learning = learning_panel()
    adaptive = adaptive_panel()
    result = summarize(entry, elasticity, learning, adaptive)

    assert result["free_entry_at_high_bilateral_profit"] > result[
        "free_entry_at_zero_bilateral_profit"
    ]
    assert result["adaptive_zero_region_present"] is True
    assert 0.48 < result["inverse_square_revenue_threshold_group_share"] < 0.52
    assert learning["required_horizon"].max() > learning["required_horizon"].min()
    assert "not live provider estimates" in result["claim_boundary"]
