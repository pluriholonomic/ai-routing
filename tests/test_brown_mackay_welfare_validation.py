from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orcap.analysis.bm2_fast_slow_reactions import build_reaction_panel
from orcap.analysis.bm3_quality_adjusted_premium import fit_within
from orcap.analysis.bm4_reaction_rules import link_reactions, paired_predictive_test
from orcap.analysis.bm_common import (
    classify_cadence,
    independent_waves,
    temporal_training_cutoff,
)
from orcap.analysis.wcv2_welfare_bounds import cadence_neutral_market
from orcap.analysis.wcv3_agent_regret import provider_best_response
from orcap.analysis.wcv5_verdict import conjecture_verdict


def _event(ts: str, provider: str, direction: int = -1) -> dict:
    old = 2.0 if direction < 0 else 1.0
    new = 1.0 if direction < 0 else 2.0
    return {
        "ts": pd.Timestamp(ts, tz="UTC"),
        "dt": ts[:10],
        "model_id": "m",
        "provider_name": provider,
        "old_price": old,
        "new_price": new,
        "dlog_price": np.log(new / old),
        "direction": direction,
    }


def test_cadence_classification_and_wave_thinning() -> None:
    assert classify_cadence(20, 3.0, 8.0) == "intraday"
    assert classify_cadence(5, 0.7, 30.0) == "daily"
    assert classify_cadence(2, 0.2, 120.0) == "weekly"
    assert classify_cadence(1, 0.01, None) == "episodic"
    events = pd.DataFrame(
        [
            _event("2026-01-01T00:00:00", "slow"),
            _event("2026-01-01T01:00:00", "fast"),
            _event("2026-01-01T08:00:00", "other"),
        ]
    )
    waves = independent_waves(events, 6)
    assert list(waves["provider_name"]) == ["slow", "other"]


def test_reaction_panel_has_post_and_placebo_windows() -> None:
    events = pd.DataFrame(
        [
            _event("2026-01-01T06:00:00", "fast"),
            _event("2026-01-01T12:00:00", "slow"),
            _event("2026-01-01T14:00:00", "fast"),
        ]
    )
    quotes = pd.DataFrame(
        [
            {"dt": "2026-01-01", "model_id": "m", "provider_name": "slow", "price": 2.0},
            {"dt": "2026-01-01", "model_id": "m", "provider_name": "fast", "price": 1.0},
        ]
    )
    cadence = pd.DataFrame(
        [
            {"provider_name": "slow", "cadence_class": "weekly", "is_fast": False},
            {"provider_name": "fast", "cadence_class": "intraday", "is_fast": True},
        ]
    )
    panel = build_reaction_panel(events, quotes, cadence, independence_hours=5)
    row = panel[(panel["initiator"] == "slow") & (panel["responder"] == "fast")].iloc[0]
    assert row["responded"] == 1
    assert row["placebo_move"] == 1
    assert row["response_lag_hours"] == 2


def test_temporal_cadence_cutoff_and_wave_window_prevent_lookahead() -> None:
    events = pd.DataFrame(
        [
            _event("2026-01-01T00:00:00", "slow"),
            _event("2026-01-01T06:00:00", "fast"),
            _event("2026-01-02T00:00:00", "slow"),
            _event("2026-01-02T03:00:00", "fast"),
        ]
    )
    cutoff = temporal_training_cutoff(events, 0.5)
    assert cutoff == pd.Timestamp("2026-01-01T06:00:00Z")
    quotes = pd.DataFrame(
        [
            {"dt": day, "model_id": "m", "provider_name": provider, "price": 1.0}
            for day in ["2026-01-01", "2026-01-02"]
            for provider in ["slow", "fast"]
        ]
    )
    cadence = pd.DataFrame(
        [
            {"provider_name": "slow", "cadence_class": "weekly", "is_fast": False},
            {"provider_name": "fast", "cadence_class": "intraday", "is_fast": True},
        ]
    )
    panel = build_reaction_panel(
        events,
        quotes,
        cadence,
        independence_hours=5,
        wave_start=cutoff,
        wave_end=pd.Timestamp("2026-01-02T00:00:00Z"),
    )
    assert set(panel["wave_ts"]) == {pd.Timestamp("2026-01-02T00:00:00Z")}


def test_simultaneous_updates_have_no_invented_initiator_or_reaction_order() -> None:
    events = pd.DataFrame(
        [
            _event("2026-01-01T00:00:00", "a"),
            _event("2026-01-01T00:00:00", "b"),
            _event("2026-01-01T08:00:00", "c"),
            _event("2026-01-01T16:00:00", "d"),
        ]
    )
    waves = independent_waves(events, 6)
    assert waves["provider_name"].tolist() == ["c", "d"]

    cadence = pd.DataFrame(
        {
            "provider_name": ["a", "b", "c", "d"],
            "is_fast": [False, False, True, True],
        }
    )
    linked = link_reactions(events, cadence)
    assert linked[["provider_name", "rival_provider"]].to_dict("records") == [
        {"provider_name": "d", "rival_provider": "c"}
    ]
    assert (linked["lag_hours"] > 0).all()


def test_paired_predictive_test_clusters_temporal_holdout_by_model() -> None:
    rows = []
    for index in range(60):
        rival = (index % 7 - 3) / 10
        rows.append(
            {
                "model_id": f"m{index % 6}",
                "own_dlog": 0.8 * rival,
                "gap": 0.0,
                "rival": rival,
            }
        )
    panel = pd.DataFrame(rows)
    result = paired_predictive_test(
        panel.iloc[:48],
        panel.iloc[48:],
        ["gap"],
        ["gap", "rival"],
        draws=200,
    )
    assert result["n_model_clusters"] == 6
    assert result["mse_improvement"] > 0
    assert result["exact_sign_flip_p_positive"] <= 0.05
    assert result["verdict"] == "brown_mackay_predictive_gain"


def test_within_estimator_recovers_fast_discount() -> None:
    rows = []
    for model in ["a", "b", "c", "d"]:
        for day in ["2026-01-01", "2026-01-02"]:
            for index, fast in enumerate([False, False, True, True]):
                rows.append(
                    {
                        "model_id": model,
                        "dt": day,
                        "provider_name": f"p{index}",
                        "price": np.exp(1.0 - 0.2 * fast),
                        "is_fast": float(fast),
                        "throughput": 10.0,
                        "latency": 100.0,
                        "uptime": 0.99,
                    }
                )
    result = fit_within(pd.DataFrame(rows), quality_adjusted=False)
    assert result["beta_fast"] == pytest.approx(-0.2, abs=1e-8)


def test_counterfactual_and_regret_are_directionally_sane() -> None:
    market = pd.DataFrame(
        {
            "tokens": [60.0, 40.0],
            "price": [1.0, 1.2],
            "is_fast": [True, False],
        }
    )
    result = cadence_neutral_market(market, -0.1, -1.2, -0.05, 0.5)
    assert result["price_change_pct"] < 0
    assert result["demand_change_pct"] > 0
    regret = provider_best_response(1.0, 0.5, 0.5, -2.0)
    assert regret["best_profit_index"] >= regret["actual_profit_index"]
    assert regret["normalized_regret"] >= 0


def test_verdict_fails_closed() -> None:
    conditions = [
        {"condition": "C1", "status": "supported_in_study_domain"},
        {"condition": "C2", "status": "not_identified"},
    ]
    assert conjecture_verdict(conditions, randomized_ready=True) == "not_identified"
    conditions[1]["status"] = "inconsistent_with_condition"
    assert (
        conjecture_verdict(conditions, randomized_ready=True)
        == "decentralization_conditions_not_satisfied"
    )
