"""Identification, spell construction, and masking checks for H84/H85."""

from pathlib import Path

import pandas as pd

from orcap.analysis.h82_enforcement_substitution import canonical_panel
from orcap.analysis.h84_stale_quote_hazard import (
    analyze_discovery,
    analyze_future,
    choice_contrasts,
    choice_rows,
    quote_state_panel,
    risk_rows,
)


def _row(
    timestamp: pd.Timestamp,
    *,
    endpoint: str,
    provider: str,
    price: float,
    success: float = 20,
    rate_limited: float = 0,
    model: str = "model-v1",
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


def _hazard_rows(origin: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for minute in range(0, 30, 5):
        timestamp = origin + pd.to_timedelta(minute, unit="min")
        for endpoint, provider, base_price in (
            ("stale-cheap", "provider-a", 1.0),
            ("recent-middle", "provider-b", 2.0),
            ("expensive", "provider-c", 3.0),
        ):
            price = base_price
            if endpoint == "recent-middle" and minute >= 10:
                price = 2.2
            rate_limited = 5 if endpoint == "stale-cheap" and minute == 15 else 0
            rows.append(
                _row(
                    timestamp,
                    endpoint=endpoint,
                    provider=provider,
                    price=price,
                    rate_limited=rate_limited,
                )
            )
    return pd.DataFrame(rows)


def _cadence() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"provider_name": "provider-a", "cadence_class": "weekly", "is_fast": False},
            {"provider_name": "provider-b", "cadence_class": "intraday", "is_fast": True},
            {"provider_name": "provider-c", "cadence_class": "daily", "is_fast": True},
        ]
    )


def test_quote_age_resets_only_on_observed_price_change():
    panel = quote_state_panel(canonical_panel(_hazard_rows(pd.Timestamp("2026-07-15T00:00Z"))))
    middle = panel[panel["endpoint_uuid"].eq("recent-middle")].set_index("ts")
    assert middle.loc[pd.Timestamp("2026-07-15T00:05Z"), "quote_age_hours"] > 0
    assert middle.loc[pd.Timestamp("2026-07-15T00:10Z"), "quote_age_hours"] == 0
    assert not bool(
        middle.loc[pd.Timestamp("2026-07-15T00:10Z"), "spell_left_censored"]
    )


def test_forward_choice_set_identifies_stale_cheap_case_and_backward_placebo():
    panel = canonical_panel(_hazard_rows(pd.Timestamp("2026-07-15T00:00Z")))
    risk = risk_rows(panel, _cadence())
    forward = choice_rows(risk, "case_forward")
    backward = choice_rows(risk, "case_backward")

    assert forward["choice_set_id"].nunique() == 1
    assert backward["choice_set_id"].nunique() == 1
    assert forward.loc[forward["case"], "endpoint_uuid"].tolist() == ["stale-cheap"]
    contrast = choice_contrasts(forward).iloc[0]
    assert contrast["stale_cheap_case_minus_rival"] > 0
    assert bool(contrast["case_price_sticky"])


def test_nullable_adjacent_state_is_coerced_to_not_an_event():
    rows = _hazard_rows(pd.Timestamp("2026-07-15T00:00Z"))
    rows.loc[
        rows["endpoint_uuid"].eq("expensive") & rows["run_ts"].eq("20260715T000000Z"),
        "success_5m",
    ] = pd.NA
    risk = risk_rows(canonical_panel(rows), _cadence())
    assert risk["case_forward"].dtype == bool
    assert risk["case_backward"].dtype == bool
    assert not risk[["case_forward", "case_backward"]].isna().any().any()


def test_h84_discovery_reports_predictive_not_causal_result(tmp_path: Path):
    summary = analyze_discovery(
        _hazard_rows(pd.Timestamp("2026-07-15T00:00Z")),
        tmp_path,
        cadence=_cadence(),
    )
    assert summary["evidence_status"] == "retrospectively_preregistered_discovery"
    assert summary["support"]["forward_choice_sets"] == 1
    assert summary["primary_forward_contrast"]["mean"] > 0
    assert "does not identify" in summary["claim_boundary"]
    assert (tmp_path / "h84_stale_quote_hazard.png").exists()


def test_h85_masks_all_outcomes_before_sample_gates(tmp_path: Path):
    summary = analyze_future(
        _hazard_rows(pd.Timestamp("2026-07-15T12:00Z")),
        tmp_path,
        cadence=_cadence(),
    )
    assert summary["evidence_status"] == "future_holdout_power_gated"
    assert summary["outcomes_released"] is False
    assert summary["support"]["valid_forward_choice_sets"] == 1
    assert "released_results" not in summary
    assert not (tmp_path / "h85_forward_choice_rows.parquet").exists()
    assert not (tmp_path / "h85_stale_quote_hazard.png").exists()
