"""Tests for the first synthetic router-welfare screening."""

from __future__ import annotations

from orcap.analysis.sm2_router_welfare import contrasts, screening_panel, summary


def test_sm2_uses_paired_common_seed_episodes_and_bounded_claims() -> None:
    panel = screening_panel(seeds=(0, 1, 2), horizon_epochs=24)
    assert len(panel) == 4 * 3 * 4
    assert not panel.isna().any().any()
    assert (panel["served_requests"] <= panel["requests"]).all()
    paired = contrasts(panel)
    assert set(paired["seeds"]) == {3}
    result = summary(panel, paired)
    assert result["evidence_status"] == "synthetic_screening_not_confirmatory"
    assert "not an equilibrium estimate" in result["evidence_boundary"]


def test_sm2_static_mechanisms_have_real_but_small_welfare_differences() -> None:
    panel = screening_panel(seeds=tuple(range(8)), horizon_epochs=96)
    paired = contrasts(panel)
    welfare = paired[paired["outcome"] == "welfare_per_request"]
    assert (welfare["mean_difference"].abs() > 0).any()
    assert (panel["welfare_per_request"] < 0.02).all()


def test_failure_loss_only_matters_when_attempts_are_constrained() -> None:
    panel = screening_panel(seeds=tuple(range(8)), horizon_epochs=96)
    paired = contrasts(panel)
    welfare = paired[
        (paired["outcome"] == "welfare_per_request")
        & (paired["router"] == "lowest_cost")
    ].set_index("scenario")
    low = abs(welfare.loc["cheap_provider_unreliable_low_loss", "mean_difference"])
    high = abs(welfare.loc["cheap_provider_unreliable_high_loss", "mean_difference"])
    assert high > low * 1.5
