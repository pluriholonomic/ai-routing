"""Synthetic recovery tests for the H42 routing-volume-capture event contract."""

import pandas as pd
from pyarrow.parquet import ParquetFile

from orcap.analysis.h42_routing_mev import (
    _mean_observed,
    _sum_observed,
    attach_intraday,
    build_event_panel,
    event_effects,
    event_quality,
    threshold_summary,
)
from orcap.capture_api import write_event_burst_manifest

TS = "20260709T120000Z"


def _event(old: float, new: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": f"{TS}|m|a|standard|a1",
                "changed_at_run_ts": TS,
                "event_ts": pd.Timestamp("2026-07-09T12:00:00Z"),
                "model_id": "m",
                "provider_name": "a",
                "tag": "standard",
                "endpoint_fingerprint": "a1",
                "old_price": old,
                "new_price": new,
                "provider_wave": False,
                "competitor_event_prior_48h": False,
                "simultaneous_price_events": 1,
            }
        ]
    )


def _snapshots(a_price: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_ts": TS,
                "model_id": "m",
                "provider_name": "a",
                "tag": "standard",
                "endpoint_fingerprint": "a1",
                "price_completion": a_price,
            },
            {
                "run_ts": TS,
                "model_id": "m",
                "provider_name": "b",
                "tag": "standard",
                "endpoint_fingerprint": "b1",
                "price_completion": 1.0,
            },
            {
                "run_ts": TS,
                "model_id": "m",
                "provider_name": "c",
                "tag": "standard",
                "endpoint_fingerprint": "c1",
                "price_completion": 1.5,
            },
        ]
    )


def test_h42_reconstructs_rank_improving_undercut():
    panel = build_event_panel(_event(2.0, 0.9), _snapshots(0.9))
    focal = panel[panel["is_focal"]].iloc[0]
    assert focal["rank_before"] == 3
    assert focal["rank_after"] == 1
    assert focal["newly_best"]
    assert focal["is_cut"]
    assert focal["eligible_quote"]
    assert threshold_summary(panel)["n_rank_crossing_cuts"] == 1


def test_h42_keeps_all_missing_flow_as_missing():
    assert pd.isna(_sum_observed(pd.Series([pd.NA], dtype="Int64")))
    assert pd.isna(_mean_observed(pd.Series([pd.NA], dtype="Int64")))


def test_h42_finds_stale_quote_beneficiary_after_competitor_raise():
    panel = build_event_panel(_event(0.8, 1.2), _snapshots(1.2))
    beneficiary = panel[panel["provider_name"] == "b"].iloc[0]
    assert beneficiary["rank_before"] == 2
    assert beneficiary["rank_after"] == 1
    assert beneficiary["is_stale_beneficiary"]


def test_h42_attaches_rolling_flow_and_computes_event_effect():
    panel = build_event_panel(_event(2.0, 0.9), _snapshots(0.9))
    congestion = pd.DataFrame(
        [
            {
                "run_ts": "20260709T113000Z",
                "model_permaslug": "m",
                "provider_name": "a",
                "request_count_30m": 10,
                "success_30m": 10,
                "rate_limited_30m": 0,
                "derankable_error_30m": 0,
                "capacity_ceiling_rpm": 100,
                "recent_peak_rpm": 20,
                "p90_latency_ms": 100,
            },
            {
                "run_ts": "20260709T113000Z",
                "model_permaslug": "m",
                "provider_name": "b",
                "request_count_30m": 20,
                "success_30m": 20,
                "rate_limited_30m": 0,
                "derankable_error_30m": 0,
                "capacity_ceiling_rpm": 100,
                "recent_peak_rpm": 20,
                "p90_latency_ms": 100,
            },
            {
                "run_ts": "20260709T123000Z",
                "model_permaslug": "m",
                "provider_name": "a",
                "request_count_30m": 80,
                "success_30m": 80,
                "rate_limited_30m": 0,
                "derankable_error_30m": 0,
                "capacity_ceiling_rpm": 100,
                "recent_peak_rpm": 60,
                "p90_latency_ms": 100,
            },
            {
                "run_ts": "20260709T123000Z",
                "model_permaslug": "m",
                "provider_name": "b",
                "request_count_30m": 20,
                "success_30m": 20,
                "rate_limited_30m": 0,
                "derankable_error_30m": 0,
                "capacity_ceiling_rpm": 100,
                "recent_peak_rpm": 20,
                "p90_latency_ms": 100,
            },
        ]
    )
    intraday = attach_intraday(panel, congestion)
    quality = event_quality(panel, intraday)
    effects = event_effects(panel, intraday, "undercut")

    assert quality.iloc[0]["eligible_intraday"]
    assert len(effects) == 1
    assert effects.iloc[0]["delta_request_share_30m"] > 0.45


def test_h42_event_linked_congestion_avoids_cross_event_cartesian():
    first = build_event_panel(_event(2.0, 0.9), _snapshots(0.9))
    second = first.copy()
    second["event_id"] = "second-event"
    second["event_ts"] = pd.Timestamp("2026-07-09T13:00:00Z")
    panel = pd.concat([first, second], ignore_index=True)
    congestion = pd.DataFrame(
        [
            {
                "event_id": event_id,
                "run_ts": run_ts,
                "model_permaslug": "m",
                "provider_name": provider,
                "request_count_30m": count,
            }
            for event_id, run_ts, count in (
                (first.iloc[0]["event_id"], "20260709T120500Z", 10),
                ("second-event", "20260709T130500Z", 20),
            )
            for provider in ("a", "b")
        ]
    )
    intraday = attach_intraday(panel, congestion)
    assert len(intraday) == 4
    assert set(
        intraday.loc[
            intraday["event_id"] == first.iloc[0]["event_id"],
            "request_count_30m",
        ]
    ) == {10.0}
    assert set(
        intraday.loc[
            intraday["event_id"] == "second-event", "request_count_30m"
        ]
    ) == {20.0}


def test_event_burst_manifest_marks_post_only_high_frequency_window(tmp_path):
    path = write_event_burst_manifest({"m"}, TS, "2026-07-09", 235, tmp_path)
    assert path is not None
    row = ParquetFile(path).read().to_pylist()[0]
    assert row["pre_event_resolution_seconds"] == 300
    assert row["post_event_resolution_seconds"] == 60
    assert row["post_burst_attempted"]
