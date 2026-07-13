"""Synthetic checks for the simulated-provider pricing methodology."""

import pandas as pd

from orcap.analysis.h66_simulated_provider_pricing import (
    attach_public_performance,
    pricing_events,
    pricing_panel,
    provider_scorecard,
    summarize,
)


def _row(ts, provider, quote, share, uptime, latency, throughput):
    return {
        "run_ts": ts,
        "dt": "2026-07-10",
        "panel_id": "p",
        "model_id": "m",
        "scenario": "short_chat",
        "provider_name": provider,
        "expected_quote_usd": quote,
        "simulated_route_share": share,
        "provider_quote_rank": 1 if quote == 1.0 else 2,
        "n_eligible_providers": 2,
        "uptime_last_30m": uptime,
        "p90_latency_ms": latency,
        "p90_throughput": throughput,
    }


def _rows():
    return pd.DataFrame(
        [
            _row("20260710T000000Z", "a", 1.0, 0.8, 0.99, 100.0, 100.0),
            _row("20260710T000000Z", "b", 2.0, 0.2, 0.98, 120.0, 90.0),
            _row("20260710T001500Z", "a", 3.0, 4.0 / 13.0, 0.99, 100.0, 100.0),
            _row("20260710T001500Z", "b", 2.0, 9.0 / 13.0, 0.98, 120.0, 90.0),
        ]
    )


def test_h66_computes_mechanical_position_and_conservative_frontier():
    panel, duplicates = pricing_panel(_rows())
    first_a = panel[(panel.run_ts == "20260710T000000Z") & (panel.provider_name == "a")].iloc[0]
    first_b = panel[(panel.run_ts == "20260710T000000Z") & (panel.provider_name == "b")].iloc[0]
    assert duplicates == 0
    assert first_a["quote_markup_to_cheapest"] == 0.0
    assert abs(first_a["mechanical_own_price_elasticity"] + 0.4) < 1e-12
    assert first_a["public_operationally_dominated"] == False  # noqa: E712
    assert first_b["public_operationally_dominated"] == True  # noqa: E712


def test_h66_describes_quote_events_without_estimating_them():
    panel, duplicates = pricing_panel(_rows())
    events = pricing_events(panel)
    event = events.iloc[0]
    assert duplicates == 0
    assert len(events) == 1
    assert event["provider_name"] == "a"
    assert event["candidate_set_stable"]
    assert event["price_increase"]
    assert abs(event["quote_change_pct"] - 2.0) < 1e-12
    assert event["simulated_share_change"] < 0


def test_h66_marks_equal_top_quotes_as_a_top_tier_not_a_unique_leader():
    raw = _rows()
    raw.loc[
        (raw["run_ts"] == "20260710T001500Z") & (raw["provider_name"] == "a"), "expected_quote_usd"
    ] = 2.0
    raw.loc[
        (raw["run_ts"] == "20260710T001500Z") & (raw["provider_name"] == "a"),
        "simulated_route_share",
    ] = 0.5
    raw.loc[
        (raw["run_ts"] == "20260710T001500Z") & (raw["provider_name"] == "b"),
        "simulated_route_share",
    ] = 0.5

    panel, _ = pricing_panel(raw)
    event = pricing_events(panel).iloc[0]

    after = panel[panel["run_ts"] == "20260710T001500Z"]
    assert after["simulated_top_provider"].all()
    assert not after["simulated_unique_leader"].any()
    assert not event["became_simulated_unique_leader"]


def test_h66_is_temporally_gated_and_never_claims_realized_flow():
    raw = _rows()
    panel, duplicates = pricing_panel(raw)
    events = pricing_events(panel)
    scorecard = provider_scorecard(panel, events)
    result = summarize(raw, panel, events, scorecard, duplicates)
    assert result["evidence_status"] == "insufficient_temporal_coverage"
    assert result["n_quote_events"] == 1
    assert "not realized routing" in result["claim_boundary"]


def test_h66_excludes_ambiguous_duplicate_provider_observations():
    raw = pd.concat([_rows(), _rows().iloc[[0]]], ignore_index=True)
    panel, duplicates = pricing_panel(raw)
    assert duplicates == 2
    assert not ((panel.run_ts == "20260710T000000Z") & (panel.provider_name == "a")).any()


def test_h66_scorecard_handles_a_window_with_no_repricing_events():
    one_snapshot = _rows().iloc[:2].copy()
    panel, _ = pricing_panel(one_snapshot)
    scorecard = provider_scorecard(panel, pricing_events(panel))
    assert (scorecard["n_quote_events"] == 0).all()
    assert (scorecard["n_unique_pricing_shocks"] == 0).all()


def test_h66_uses_only_exact_unambiguous_historical_performance_matches():
    rows = _rows().iloc[:2].copy()
    rows["p90_latency_ms"] = None
    rows["p90_throughput"] = None
    model_map = pd.DataFrame(
        [{"run_ts": "20260710T000000Z", "model_id": "m", "canonical_slug": "m-v1"}]
    )
    stats = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "model_permaslug": "m-v1",
                "provider_name": "a",
                "p90_latency_ms": 100.0,
                "p90_throughput": 75.0,
            },
            {
                "run_ts": "20260710T000000Z",
                "model_permaslug": "m-v1",
                "provider_name": "b",
                "p90_latency_ms": 120.0,
                "p90_throughput": 50.0,
            },
            {
                "run_ts": "20260710T000000Z",
                "model_permaslug": "m-v1",
                "provider_name": "b",
                "p90_latency_ms": 121.0,
                "p90_throughput": 49.0,
            },
        ]
    )
    joined = attach_public_performance(rows, model_map, stats).set_index("provider_name")
    assert joined.loc["a", "p90_latency_ms"] == 100.0
    assert joined.loc["a", "performance_join_status"] == "analysis_exact_canonical_model_provider"
    assert pd.isna(joined.loc["b", "p90_latency_ms"])
    assert joined.loc["b", "performance_join_status"] == "no_exact_public_provider_stats"
