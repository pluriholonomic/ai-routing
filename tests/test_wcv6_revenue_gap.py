from __future__ import annotations

import numpy as np
import pytest

from orcap.analysis.wcv6_revenue_gap import (
    counterfactual_revenue_ratio,
    optimize_provider_revenue,
)


def test_counterfactual_revenue_ratio_is_one_at_observed_price() -> None:
    ratio = counterfactual_revenue_ratio(
        price=2.0,
        share=0.2,
        competitor_price=1.5,
        price_multiple=1.0,
        routing_elasticity=-1.2,
        demand_elasticity=-0.05,
    )
    assert float(ratio) == pytest.approx(1.0)


def test_local_revenue_elasticity_matches_one_plus_share_elasticity() -> None:
    result = optimize_provider_revenue(
        price=1.0,
        share=0.4,
        competitor_price=1.0,
        routing_elasticity=-1.1,
        demand_elasticity=0.0,
        price_multiples=np.geomspace(0.25, 4.0, 401),
    )
    assert result["revenue_maximizing_price_multiple_within_grid"] < 1.0
    assert result["best_revenue_ratio_within_grid"] > 1.0
    assert result["local_revenue_elasticity"] == pytest.approx(-0.1, abs=1e-7)


def test_more_elastic_low_share_provider_prefers_a_price_cut() -> None:
    result = optimize_provider_revenue(
        price=1.0,
        share=0.05,
        competitor_price=1.0,
        routing_elasticity=-2.0,
        demand_elasticity=0.0,
        price_multiples=np.geomspace(0.25, 4.0, 401),
    )
    assert result["revenue_maximizing_price_multiple_within_grid"] < 1.0
    assert result["best_revenue_ratio_within_grid"] > 1.0
    assert result["local_revenue_elasticity"] < 0.0


def test_boundary_optimum_is_disclosed() -> None:
    result = optimize_provider_revenue(
        price=1.0,
        share=0.2,
        competitor_price=1.0,
        routing_elasticity=-0.5,
        demand_elasticity=0.0,
        price_multiples=np.geomspace(0.25, 4.0, 101),
    )
    assert result["revenue_maximizing_price_multiple_within_grid"] == pytest.approx(4.0)
    assert result["optimum_at_grid_boundary"] is True
    assert result["deviation_direction"] == "upper_boundary"
