"""Future-only masking and shape tests for H83."""

from pathlib import Path

import numpy as np
import pandas as pd

from orcap.analysis.h83_capacity_overshoot import (
    analyze,
    matched_shape_contrasts,
    shape_effects,
)


def _share(minute: int, *, high: bool) -> float:
    if not high:
        return 0.10
    if minute <= -20:
        return 0.10
    if minute <= -5:
        return 0.15
    if minute == 0:
        return 0.08
    if minute <= 10:
        return 0.05
    if minute <= 20:
        return 0.06
    if minute <= 30:
        return 0.07
    if minute <= 40:
        return 0.08
    return 0.10


def _event_time() -> tuple[pd.DataFrame, pd.DataFrame]:
    origin = pd.Timestamp("2026-07-16T13:00:00Z")
    rows = []
    for event_id, event_class, shift in (("high-1", "high", 0), ("low-1", "low", 180)):
        event_ts = origin + pd.to_timedelta(shift, unit="min")
        for minute in range(-30, 65, 5):
            share = _share(minute, high=event_class == "high")
            rows.append(
                {
                    "event_id": event_id,
                    "event_class": event_class,
                    "event_ts": event_ts,
                    "model_permaslug": "model-v1",
                    "endpoint_uuid": f"endpoint-{event_class}",
                    "provider_name": f"provider-{event_class}",
                    "relative_minutes": minute,
                    "endpoint_success_share": share,
                    "provider_success_share": share,
                    "price_completion": 1e-6,
                    "accounting_residual": 0.0,
                }
            )
    base = pd.DataFrame(
        {
            "event_id": ["high-1", "low-1"],
            "complete_event": [True, True],
        }
    )
    return pd.DataFrame(rows), base


def test_h83_shape_components_recover_the_frozen_cycle():
    event_time, base = _event_time()
    shapes = shape_effects(event_time, base)
    high = shapes[shapes["event_class"].eq("high")].iloc[0]
    for metric in ("endpoint_success_share", "provider_success_share"):
        assert high[f"{metric}_loading"] > 0
        assert high[f"{metric}_break"] < 0
        assert high[f"{metric}_recovery"] > 0
        assert high[f"{metric}_level_loss"] < 0
    assert bool(high["price_sticky"])
    assert bool(high["complete_shape_event"])

    base_matches = pd.DataFrame(
        {
            "high_event_id": ["high-1"],
            "low_event_id": ["low-1"],
            "match_score": [0.0],
        }
    )
    matched = matched_shape_contrasts(shapes, base_matches)
    assert len(matched) == 1
    assert matched.iloc[0]["provider_success_share_break_high_minus_low"] < 0


def _raw_row(
    timestamp: pd.Timestamp,
    *,
    endpoint: str,
    provider: str,
    success: float,
    rate_limited: float = 0,
) -> dict:
    return {
        "run_ts": timestamp.strftime("%Y%m%dT%H%M%SZ"),
        "dt": timestamp.strftime("%Y-%m-%d"),
        "model_permaslug": "model-v1",
        "endpoint_uuid": endpoint,
        "provider_name": provider,
        "source": "congestion_intraday",
        "price_completion": 1e-6,
        "success_5m": success,
        "rate_limited_5m": rate_limited,
        "derankable_error_30m": 0,
        "request_count_30m": success + rate_limited,
        "capacity_ceiling_rpm": 100,
        "recent_peak_rpm": 50,
        "is_deranked": False,
    }


def test_h83_masks_future_outcomes_before_sample_release(tmp_path: Path):
    origin = pd.Timestamp("2026-07-16T13:00:00Z")
    rows = []
    for minute in range(-35, 65, 5):
        timestamp = origin + pd.to_timedelta(minute, unit="min")
        share = _share(minute, high=True)
        focal = 100 * share
        rows.append(
            _raw_row(
                timestamp,
                endpoint="endpoint-high",
                provider="provider-high",
                success=focal,
                rate_limited=20 if minute == 0 else 0,
            )
        )
        rows.append(
            _raw_row(
                timestamp,
                endpoint="endpoint-rival",
                provider="provider-rival",
                success=100 - focal,
            )
        )
    summary = analyze(pd.DataFrame(rows), tmp_path)
    assert summary["evidence_status"] == "future_holdout_power_gated"
    assert not summary["outcomes_released"]
    assert "shape_results" not in summary
    assert summary["support"]["complete_shape_high_events"] == 1
    assert not (tmp_path / "h83_capacity_overshoot_effects.parquet").exists()
    ledger = pd.read_parquet(tmp_path / "h83_capacity_overshoot_protocol_ledger.parquet")
    assert "success_5m" not in ledger
    assert np.isfinite(ledger["rate_limit_share_5m"]).all()


def test_h83_handles_nonempty_discovery_panel_with_no_future_events(tmp_path: Path):
    timestamp = pd.Timestamp("2026-07-15T11:30:00Z")
    rows = pd.DataFrame(
        [
            _raw_row(
                timestamp,
                endpoint="endpoint-a",
                provider="provider-a",
                success=10,
            ),
            _raw_row(
                timestamp,
                endpoint="endpoint-b",
                provider="provider-b",
                success=10,
            ),
        ]
    )
    summary = analyze(rows, tmp_path)
    assert summary["evidence_status"] == "future_holdout_power_gated"
    assert not summary["outcomes_released"]
    assert summary["support"]["candidate_high_onsets"] == 0
