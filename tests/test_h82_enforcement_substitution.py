"""Synthetic identification and accounting checks for H82."""

from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from orcap.analysis.h82_enforcement_substitution import (
    analyze,
    build_event_time_panel,
    canonical_panel,
    discovery_panel,
    event_effects,
    event_registry,
    match_negative_controls,
)


def _row(
    timestamp: pd.Timestamp,
    *,
    endpoint: str,
    provider: str,
    success: float,
    rate_limited: float = 0,
    model: str = "model-v1",
    price: float = 1e-6,
) -> dict:
    return {
        "run_ts": timestamp.strftime("%Y%m%dT%H%M%SZ"),
        "dt": timestamp.strftime("%Y-%m-%d"),
        "model_permaslug": model,
        "endpoint_uuid": endpoint,
        "provider_name": provider,
        "source": "congestion_intraday",
        "price_completion": price,
        "success_5m": success,
        "rate_limited_5m": rate_limited,
        "derankable_error_30m": 0,
        "request_count_30m": success + rate_limited,
        "capacity_ceiling_rpm": 100,
        "recent_peak_rpm": 50,
        "is_deranked": False,
    }


def _event_rows() -> pd.DataFrame:
    origin = pd.Timestamp("2026-07-15T01:00:00Z")
    rows = []
    # High event: focal share falls from 0.8 to 0.4 while the rival absorbs the
    # difference and total model success remains exactly 100.
    for minute in range(-35, 65, 5):
        timestamp = origin + pd.to_timedelta(minute, unit="min")
        after = minute >= 5
        focal_success = 40 if after else 80
        rival_success = 60 if after else 20
        focal_rl = 20 if minute == 0 else 0
        rows.append(
            _row(
                timestamp,
                endpoint="endpoint-high",
                provider="provider-high",
                success=focal_success,
                rate_limited=focal_rl,
            )
        )
        rows.append(
            _row(
                timestamp,
                endpoint="endpoint-rival",
                provider="provider-rival",
                success=rival_success,
            )
        )

    # Low-intensity negative control on the same model, more than 60 minutes
    # away. Its flow path is flat and it is eligible for pre-treatment matching.
    low_origin = origin + pd.to_timedelta(3, unit="h")
    for minute in range(-35, 65, 5):
        timestamp = low_origin + pd.to_timedelta(minute, unit="min")
        low_rl = 2 if minute == 0 else 0
        rows.append(
            _row(
                timestamp,
                endpoint="endpoint-low",
                provider="provider-low",
                success=70,
                rate_limited=low_rl,
            )
        )
        rows.append(
            _row(
                timestamp,
                endpoint="endpoint-low-rival",
                provider="provider-rival",
                success=30,
            )
        )
    return pd.DataFrame(rows)


def test_h82_builds_isolated_event_paths_and_exact_flow_accounting(tmp_path: Path):
    panel = canonical_panel(_event_rows())
    assert panel["accounting_residual"].abs().max() < 1e-12

    registry = event_registry(panel)
    eligible = registry[registry["analysis_eligible"]]
    assert eligible["event_class"].value_counts().to_dict() == {"high": 1, "low": 1}

    event_time = build_event_time_panel(panel, registry)
    effects = event_effects(event_time)
    complete = effects[effects["complete_event"]]
    high = complete[complete["event_class"].eq("high")].iloc[0]
    assert np.isclose(high["endpoint_success_share_delta"], -0.4)
    assert np.isclose(high["provider_success_share_delta"], -0.4)
    assert high["log1p_other_provider_success_delta"] > 0
    assert np.isclose(high["model_success_5m_delta"], 0)
    assert bool(high["price_sticky"])

    matches = match_negative_controls(effects)
    assert len(matches) == 1
    assert np.isclose(matches.iloc[0]["endpoint_success_share_high_minus_low"], -0.4)

    summary = analyze(_event_rows(), tmp_path)
    assert summary["n_complete_high_events"] == 1
    assert summary["n_matched_high_low_pairs"] == 1
    assert summary["flow_accounting"]["maximum_snapshot_identity_residual"] < 1e-12
    assert abs(summary["flow_accounting"]["mean_identity_residual"]) < 1e-12
    assert not summary["release_gate"]["all_pass"]
    assert (tmp_path / "h82_enforcement_substitution.png").exists()


def test_h82_excludes_simultaneous_high_onsets():
    origin = pd.Timestamp("2026-07-15T01:00:00Z")
    rows = []
    for minute in (-5, 0, 5):
        timestamp = origin + pd.to_timedelta(minute, unit="min")
        rate_limited = 10 if minute == 0 else 0
        for endpoint, provider in (("endpoint-a", "provider-a"), ("endpoint-b", "provider-b")):
            rows.append(
                _row(
                    timestamp,
                    endpoint=endpoint,
                    provider=provider,
                    success=20,
                    rate_limited=rate_limited,
                )
            )
    registry = event_registry(canonical_panel(pd.DataFrame(rows)))
    high = registry[registry["event_class"].eq("high")]
    assert len(high) == 2
    assert not high["analysis_eligible"].any()
    assert set(high["exclusion_reason"]) == {"simultaneous_high"}


def test_h82_coerces_decimal_backed_authoritative_counts():
    rows = _event_rows()
    for column in ("success_5m", "rate_limited_5m", "capacity_ceiling_rpm"):
        rows[column] = rows[column].map(lambda value: Decimal(str(value)))
    panel = canonical_panel(rows)
    assert np.issubdtype(panel["model_success_5m"].dtype, np.floating)
    assert np.isfinite(panel["log1p_other_provider_success"]).all()


def test_h82_discovery_cut_excludes_later_holdout_rows():
    rows = _event_rows()
    later = _row(
        pd.Timestamp("2026-07-15T12:30:00Z"),
        endpoint="future-endpoint",
        provider="future-provider",
        success=10,
    )
    full = canonical_panel(pd.concat([rows, pd.DataFrame([later])], ignore_index=True))
    frozen = discovery_panel(full)
    assert len(frozen) == len(full) - 1
    assert frozen["ts"].max() <= pd.Timestamp("2026-07-15T11:33:02Z")
    assert "future-endpoint" not in set(frozen["endpoint_uuid"])


def test_h82_handles_panel_without_an_eligible_event(tmp_path: Path):
    row = _row(
        pd.Timestamp("2026-07-15T10:00:00Z"),
        endpoint="quiet-endpoint",
        provider="quiet-provider",
        success=10,
    )
    summary = analyze(pd.DataFrame([row]), tmp_path)
    assert summary["n_candidate_high_onsets"] == 0
    assert summary["n_complete_high_events"] == 0
    assert summary["n_matched_high_low_pairs"] == 0
    assert not summary["release_gate"]["all_pass"]
