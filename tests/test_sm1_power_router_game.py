"""Tests for the inverse-power router equilibrium experiment."""

from __future__ import annotations

import pytest

from orcap.analysis.sm1_power_router_game import (
    equilibrium_panel,
    equilibrium_price_with_cap,
    summary,
)


def test_cap_constrained_equilibrium_matches_inverse_square_corollary() -> None:
    assert equilibrium_price_with_cap(
        providers=2,
        exponent=2,
        marginal_cost=1,
        price_cap=10,
    ) == (10.0, True)
    assert equilibrium_price_with_cap(
        providers=3,
        exponent=2,
        marginal_cost=1,
        price_cap=10,
    ) == (4.0, False)
    assert equilibrium_price_with_cap(
        providers=4,
        exponent=2,
        marginal_cost=1,
        price_cap=10,
    ) == (3.0, False)


def test_numerical_best_responses_validate_the_whole_frozen_grid() -> None:
    panel = equilibrium_panel()
    assert len(panel) == 9 * 7 * 4
    assert panel["best_response_absolute_error"].max() < 1e-4


def test_summary_keeps_welfare_and_conduct_claims_bounded() -> None:
    result = summary(equilibrium_panel())
    assert result["inverse_square_duopoly_cap_binds"]
    assert result["inverse_square_triopoly_price_at_high_cap"] == pytest.approx(4)
    assert "not evidence of collusion" in result["conduct_boundary"]
    assert "inelastic demand" in result["welfare_boundary"]
