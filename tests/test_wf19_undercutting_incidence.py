from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from orcap.analysis import wf19_undercutting_incidence as wf19


def test_frozen_artifact_ignores_stale_local_copy(tmp_path, monkeypatch):
    name = "wf16_summary.json"
    (tmp_path / name).write_bytes(b"stale")
    pinned = tmp_path / "pinned.json"
    pinned.write_bytes(b"pinned")
    expected = hashlib.sha256(b"pinned").hexdigest()
    monkeypatch.setenv("ORCAP_ANALYSIS_SOURCE", "hf")
    monkeypatch.setattr(wf19, "hf_hub_download", lambda *args, **kwargs: str(pinned))

    observed = wf19._artifact_path(tmp_path, name, revision="immutable", expected_sha256=expected)

    assert observed == pinned


def _panel() -> pd.DataFrame:
    rows = []
    for run_ts, prices in (
        ("20260102T000000Z", {"Active": 1.0, "Anchor": 2.0, "Static": 1.5}),
        ("20260102T001500Z", {"Active": 0.8, "Anchor": 2.0, "Static": 1.5}),
    ):
        weights = {provider: price**-2 for provider, price in prices.items()}
        total = sum(weights.values())
        for provider, price in prices.items():
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": "2026-01-02",
                    "panel_id": "p",
                    "model_id": "author/model",
                    "scenario": "short_chat",
                    "provider_name": provider,
                    "expected_quote_usd": price,
                    "simulated_route_share": weights[provider] / total,
                    "public_status": 1,
                    "uptime_last_5m": 1.0,
                    "uptime_last_30m": 1.0,
                }
            )
    frame = pd.DataFrame(rows)
    frame["ts"] = pd.to_datetime(frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    return frame


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model_id": "author/model",
                "provider_name": "Active",
                "provider_type": "active_undercutter",
            },
            {
                "model_id": "author/model",
                "provider_name": "Anchor",
                "provider_type": "anchor_adopter",
            },
            {
                "model_id": "author/model",
                "provider_name": "Static",
                "provider_type": "static_discounter",
            },
        ]
    )


def test_unilateral_cut_has_equal_relative_nonmover_loss_and_distinct_incidence():
    provider, counters = wf19.build_provider_incidence(
        _panel(),
        _labels(),
        start=pd.Timestamp("2026-01-02", tz="UTC"),
        max_gap_minutes=30,
        price_rtol=1e-10,
    )
    assert counters["qualifying_direction"] == 1
    nonmovers = provider[~provider.is_mover]
    assert nonmovers.relative_share_loss.max() == pytest.approx(nonmovers.relative_share_loss.min())
    assert nonmovers.share_loss_burden.sum() == pytest.approx(1.0)
    assert nonmovers.quote_revenue_loss_burden.sum() == pytest.approx(1.0)

    scenarios, shocks = wf19.aggregate_incidence(provider)
    assert len(scenarios) == len(wf19.REPORT_TYPES)
    anchor = shocks[shocks.provider_type == "anchor_adopter"].iloc[0]
    static = shocks[shocks.provider_type == "static_discounter"].iloc[0]
    assert anchor.share_loss_burden < static.share_loss_burden
    assert anchor.quote_revenue_loss_burden > anchor.share_loss_burden

    jit = wf19.build_jit_capture_panel(provider)
    assert len(jit) == 1
    row = jit.iloc[0]
    assert row.dynamic_capture_share == pytest.approx(
        row.post_cut_shadow_share - row.frozen_quote_counterfactual_share
    )
    assert row.passive_share_displaced == pytest.approx(row.dynamic_capture_share)
    assert row.share_conservation_error == pytest.approx(0.0, abs=1e-12)
    assert row.net_quote_revenue_change == pytest.approx(
        row.volume_gain_at_old_quote - row.price_concession_cost_at_post_share
    )
    summary = wf19.summarize_jit_capture(jit)
    assert summary["n_shocks"] == 1
    assert summary["net_quote_revenue_increase_rate"] == float(row.net_quote_revenue_change > 0)
    assert "not realized market share" in summary["boundary"]
    elasticity = wf19.summarize_shadow_curve_numerical_check(provider)
    assert elasticity["scenario_events"] == 1
    assert elasticity["exact_finite_curve_maximum_absolute_share_error"] == pytest.approx(
        0.0, abs=1e-12
    )
    assert elasticity["mean_absolute_arc_minus_local_deviation"] > 0


def test_simultaneous_moves_and_pre_holdout_events_are_excluded():
    frame = _panel()
    after = frame[frame.run_ts == "20260102T001500Z"].copy()
    mask = after.provider_name == "Static"
    after.loc[mask, "expected_quote_usd"] = 1.4
    weights = after.expected_quote_usd.pow(-2)
    after["simulated_route_share"] = weights / weights.sum()
    both = pd.concat([frame[frame.run_ts == "20260102T000000Z"], after])
    panel, counters = wf19.build_provider_incidence(
        both,
        _labels(),
        start=pd.Timestamp("2026-01-02", tz="UTC"),
        max_gap_minutes=30,
        price_rtol=1e-10,
    )
    assert panel.empty
    assert counters["unilateral_quote_move"] == 0

    panel, counters = wf19.build_provider_incidence(
        _panel(),
        _labels(),
        start=pd.Timestamp("2026-01-03", tz="UTC"),
        max_gap_minutes=30,
        price_rtol=1e-10,
    )
    assert panel.empty
    assert counters["after_primary_start"] == 0


def test_public_health_transition_is_excluded_from_primary_panel():
    frame = _panel()
    frame.loc[
        (frame.run_ts == "20260102T001500Z") & (frame.provider_name == "Anchor"),
        "uptime_last_5m",
    ] = 0.5
    panel, counters = wf19.build_provider_incidence(
        frame,
        _labels(),
        start=None,
        max_gap_minutes=30,
        price_rtol=1e-10,
        exclude_public_health_transitions=True,
    )
    assert panel.empty
    assert counters["unchanged_provider_set"] == 1
    assert counters["unchanged_public_health"] == 0


def test_paid_validation_treats_negative_rank_crossing_as_a_cut(monkeypatch):
    events = pd.DataFrame(
        [
            {
                "event_id": "cut-event",
                "detected_at": "2026-01-03T00:00:00Z",
                "model_id": "author/model",
                "provider_name": "Active",
                "event_type": "rank_crossing",
                "relative_change": -0.01,
            }
        ]
    )
    attempts = pd.DataFrame(
        [
            {
                "event_id": "owned-request",
                "study_id": "openrouter-price-event-v1",
                "policy": "default_fresh",
                "model_id": "author/model",
                "selected_provider": "Active",
                "outcome": "succeeded",
                "observed_at": "20260103T001000Z",
                "metadata_json": ('{"event_id":"cut-event","wave_id":"w1","block_id":"block-1"}'),
            }
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "block_id": "block-1",
                "model_id": "author/model",
                "provider_name": "Active",
                "expected_quote_usd": 1.0,
                "compatible": True,
            },
            {
                "block_id": "block-1",
                "model_id": "author/model",
                "provider_name": "Anchor",
                "expected_quote_usd": 2.0,
                "compatible": True,
            },
        ]
    )

    def optional(name):
        if name == "price_event_registry":
            return events
        if name == "price_event_candidates":
            return candidates
        return attempts

    monkeypatch.setattr(wf19, "_load_optional_table", optional)
    protocol, _ = wf19.load_protocol()
    panel, baseline, summary = wf19.paid_event_validation(_labels(), protocol)
    assert summary["default_attempts"] == 1
    assert summary["moving_provider_selection_rate"] == 1.0
    assert summary["event_waves_with_contemporaneous_menu"] == 1
    assert panel.iloc[0].selected_provider_type == "active_undercutter"
    assert panel.iloc[0].predicted_shadow_share == pytest.approx(0.8)
    assert panel.iloc[0].calibration_residual == pytest.approx(0.2)
    assert baseline.empty


def test_continuous_default_panel_builds_same_model_pre_post_window():
    event = pd.DataFrame(
        [
            {
                "registered_event_id": "cut-event",
                "detected_at": "2026-01-03T00:00:00Z",
                "model_id": "author/model",
                "moving_provider": "Active",
            }
        ]
    )
    attempts = pd.DataFrame(
        [
            {
                "study_id": "openrouter-routing-crossover-v2",
                "policy": "openrouter_default",
                "outcome": "succeeded",
                "model_id": "author/model",
                "selected_provider": provider,
                "observed_at": when,
            }
            for provider, when in (
                ("Anchor", "20260102T231000Z"),
                ("Anchor", "20260102T232000Z"),
                ("Static", "20260102T233000Z"),
                ("Static", "20260102T234000Z"),
                ("Active", "20260103T001000Z"),
                ("Active", "20260103T002000Z"),
                ("Active", "20260103T003000Z"),
                ("Anchor", "20260103T004000Z"),
            )
        ]
    )
    protocol, _ = wf19.load_protocol()
    panel = wf19.build_continuous_paid_event_panel(event, attempts, _labels(), protocol)
    active = panel[panel.selected_provider_type == "active_undercutter"].iloc[0]
    assert active.support_eligible
    assert active.pre_selection_share == 0
    assert active.post_selection_share == pytest.approx(0.75)
    assert active.post_minus_pre == pytest.approx(0.75)
