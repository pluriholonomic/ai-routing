"""Synthetic recovery tests for the public quote-pulse screen."""

import pandas as pd

from orcap.analysis.h67_quote_pulse import (
    QuotePulseConfig,
    annotate_surface,
    attach_reversion_paths,
    build_episode_events,
    build_paths,
    derive_five_minute_surface,
    provider_scorecard,
    summarize,
)


def _surface_rows(*, tie_after_cut: bool = False) -> pd.DataFrame:
    rows = []
    timestamps = [
        "20260710T000000Z",
        "20260710T000500Z",
        "20260710T001000Z",
        "20260710T001500Z",
        "20260710T002000Z",
        "20260710T002500Z",
        "20260710T003000Z",
        "20260710T003500Z",
    ]
    for index, ts in enumerate(timestamps):
        cut = index == 1
        a_quote = 1.0 if cut else 2.0
        a_share = 0.5 if cut and tie_after_cut else (0.55 if cut else 0.2)
        b_share = 0.5 if cut and tie_after_cut else (0.45 if cut else 0.8)
        rows.extend(
            [
                {
                    "run_ts": ts,
                    "dt": "2026-07-10",
                    "panel_id": "p",
                    "model_id": "m",
                    "scenario": "short_chat",
                    "provider_name": "a",
                    "expected_quote_usd": a_quote,
                    "simulated_route_share": a_share,
                    "surface_source": "synthetic",
                },
                {
                    "run_ts": ts,
                    "dt": "2026-07-10",
                    "panel_id": "p",
                    "model_id": "m",
                    "scenario": "short_chat",
                    "provider_name": "b",
                    "expected_quote_usd": 1.0,
                    "simulated_route_share": b_share,
                    "surface_source": "synthetic",
                },
            ]
        )
    return pd.DataFrame(rows)


def _config() -> QuotePulseConfig:
    return QuotePulseConfig(
        fade_horizons_minutes=(30,),
        max_contiguous_gap_minutes=10.0,
        min_span_days=7,
        min_independent_cut_episodes=80,
    )


def test_h67_finds_a_top_tier_cut_and_observed_quote_reversion():
    config = _config()
    surface = annotate_surface(_surface_rows())
    paths = attach_reversion_paths(build_paths(surface, config), config)
    events = build_episode_events(paths, config)

    assert len(events) == 1
    event = events.iloc[0]
    assert event["quote_pulse_candidate"]
    assert event["entered_unique_leader"]
    assert event["followup_complete_30m"]
    assert event["quote_reverted_30m"]
    assert event["pulse_and_fade_30m"]
    assert event["n_scenario_cuts"] == 1
    scorecard = provider_scorecard(events, config)
    assert scorecard.loc[0, "n_followup_complete_30m"] == 1


def test_h67_preserves_top_tier_ties_without_calling_them_unique_leaders():
    config = _config()
    surface = annotate_surface(_surface_rows(tie_after_cut=True))
    paths = attach_reversion_paths(build_paths(surface, config), config)
    events = build_episode_events(paths, config)

    event = events.iloc[0]
    assert event["top_tier_after"] == "a|b"
    assert not event["entered_unique_leader"]
    assert event["quote_pulse_candidate"]


def test_h67_summary_is_temporally_gated_and_never_claims_realized_routing():
    config = _config()
    surface = annotate_surface(_surface_rows())
    paths = attach_reversion_paths(build_paths(surface, config), config)
    events = build_episode_events(paths, config)
    result = summarize(surface, events, config)

    assert result["evidence_status"] == "insufficient_temporal_coverage"
    assert "do not identify selected provider" in result["claim_boundary"]


def test_h67_replay_treats_a_missing_per_request_price_as_zero_surcharge():
    rows = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "endpoint_fingerprint": provider,
                "model_id": "z-ai/glm-5.2",
                "model_name": "GLM",
                "provider_name": provider,
                "tag": "standard",
                "context_length": 100_000,
                "max_completion_tokens": 10_000,
                "max_prompt_tokens": 90_000,
                "status": 1,
                "uptime_last_5m": 1.0,
                "uptime_last_30m": 1.0,
                "latency_last_30m": None,
                "throughput_last_30m": None,
                "supported_parameters": [],
                "price_prompt": prompt,
                "price_completion": completion,
                "price_request": float("nan"),
            }
            for provider, prompt, completion in [("a", 1e-6, 1e-6), ("b", 2e-6, 2e-6)]
        ]
    )

    surface = derive_five_minute_surface(rows)

    assert not surface.empty
    assert {"a", "b"} == set(
        surface.loc[surface["scenario"] == "short_chat", "provider_name"]
    )
