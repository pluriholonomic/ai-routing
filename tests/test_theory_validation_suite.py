from __future__ import annotations

from orcap.analysis.theory_validation_suite import (
    summarize,
    validate_coarsening_construction,
    validate_detection_threshold,
    validate_entry_grid,
    validate_revenue_share_identity,
)


def test_companion_theorem_validations_hold_on_small_suite():
    threshold = validate_detection_threshold(events_per_cell=20_000, seed=1)
    revenue = validate_revenue_share_identity(markets=20, providers_per_market=4, seed=2)
    entry = validate_entry_grid(max_n=200)
    coarsening = validate_coarsening_construction(draws=1_000, seed=3)
    result = summarize(threshold, revenue, entry, coarsening)

    assert result["detection_threshold"]["all_signs_match_away_from_threshold"] is True
    assert abs(revenue["coefficient_identity_error"]) < 1e-10
    assert revenue["maximum_residual_difference"] < 1e-10
    assert abs(revenue["hc1_standard_error_difference"]) < 1e-10
    assert result["entry_grid"]["all_ceilings_hold"] is True
    assert result["entry_grid"]["all_equal_margin_overentry_checks_hold"] is True
    assert result["entry_grid"]["any_grid_boundary_hit"] is False
    assert result["coarsening_construction"]["all_changed_providers_attainable"] is True

