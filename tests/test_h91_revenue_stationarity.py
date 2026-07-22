from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orcap.analysis.bm_common import load_gates
from orcap.analysis.h91_revenue_stationarity import (
    cluster_sign_flip_score_test,
    fit_two_way_fe,
    leave_one_residual_support_cluster_out,
    revenue_foc_test,
    within_between_decomposition,
)


def test_registered_revenue_analysis_gates_are_packaged() -> None:
    gates = load_gates()
    assert gates["revenue_stationarity"]["min_panel_days"] == 30
    assert gates["revenue_identity"]["permutation_draws"] == 999
    assert gates["revenue_gap"]["grid_points"] == 161


def test_revenue_foc_equivalence_test_accepts_precise_unit_elasticity() -> None:
    result = revenue_foc_test(-1.0, 0.05, equivalence_margin=0.25)
    assert result["p_equal_revenue_foc"] == pytest.approx(1.0)
    assert result["equivalent_to_revenue_foc"] is True
    assert result["p_equal_zero"] < 1e-10
    assert result["p_equal_inverse_square"] < 1e-10


def test_revenue_foc_equivalence_refuses_imprecise_estimate() -> None:
    result = revenue_foc_test(-1.0, 0.30, equivalence_margin=0.25)
    assert result["p_equal_revenue_foc"] == pytest.approx(1.0)
    assert result["equivalent_to_revenue_foc"] is False


def test_within_between_decomposition_recovers_distinct_slopes() -> None:
    rng = np.random.default_rng(7)
    rows = []
    entity_price = rng.normal(size=80)
    day_effect = rng.normal(scale=0.3, size=12)
    for day in range(12):
        within_shock = rng.normal(scale=0.25, size=len(entity_price))
        for entity, mean_price in enumerate(entity_price):
            price = mean_price + within_shock[entity]
            outcome = (
                -1.0 * mean_price
                + 0.2 * within_shock[entity]
                + day_effect[day]
                + rng.normal(scale=0.03)
            )
            rows.append(
                {
                    "outcome": outcome,
                    "price": price,
                    "group": f"day-{day}",
                    "entity": f"entity-{entity}",
                }
            )
    result = within_between_decomposition(
        pd.DataFrame(rows),
        outcome="outcome",
        price="price",
        group="group",
        entity="entity",
    )
    assert result["between_elasticity"] == pytest.approx(-1.0, abs=0.03)
    assert result["within_elasticity"] == pytest.approx(0.2, abs=0.03)
    assert result["difference_p_value"] < 1e-10


def test_two_way_fixed_effects_recover_within_entity_price_slope() -> None:
    rng = np.random.default_rng(19)
    rows = []
    entity_effect = rng.normal(scale=1.5, size=60)
    for day in range(18):
        market_effect = rng.normal(scale=0.8)
        for entity in range(60):
            if rng.uniform() < 0.08:
                continue
            price = 0.7 * entity_effect[entity] + rng.normal(scale=0.4)
            outcome = entity_effect[entity] + market_effect - 0.65 * price + rng.normal(scale=0.08)
            rows.append(
                {
                    "outcome": outcome,
                    "price": price,
                    "market_time": f"day-{day}",
                    "entity": f"entity-{entity}",
                    "provider": f"provider-{entity % 12}",
                }
            )
    result = fit_two_way_fe(
        pd.DataFrame(rows),
        outcome="outcome",
        price="price",
        market_time="market_time",
        entity="entity",
        cluster="provider",
    )
    assert result["elasticity"] == pytest.approx(-0.65, abs=0.03)
    assert result["absorption_final_change"] <= 1e-10


def test_two_way_cluster_robustness_rejects_distant_null() -> None:
    rng = np.random.default_rng(23)
    rows = []
    for day in range(16):
        for entity in range(48):
            price = rng.normal(scale=0.5)
            rows.append(
                {
                    "outcome": -0.25 * price + rng.normal(scale=0.08),
                    "price": price,
                    "market_time": f"day-{day}",
                    "entity": f"entity-{entity}",
                    "provider": f"provider-{entity % 12}",
                }
            )
    panel = pd.DataFrame(rows)
    sign_flip = cluster_sign_flip_score_test(
        panel,
        outcome="outcome",
        price="price",
        market_time="market_time",
        entity="entity",
        cluster="provider",
        null_coefficient=-1.0,
    )
    assert sign_flip["method"] == "exact"
    assert sign_flip["two_sided_p_value"] < 0.01
    lopo = leave_one_residual_support_cluster_out(
        panel,
        outcome="outcome",
        price="price",
        market_time="market_time",
        entity="entity",
        cluster="provider",
    )
    assert len(lopo) == 12
    assert (lopo["elasticity"] > -0.4).all()
