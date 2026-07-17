from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from orcap.analysis.pm1_temporal_validation import (
    _exact_sign_flip_p,
    assign_training_provider_rates,
    prepare_ex_ante_panel,
    registered_temporal_split,
    run,
)


def _panel(days: int = 30, models: int = 8, providers: int = 3) -> pd.DataFrame:
    rows: list[dict] = []
    starts: dict[tuple[str, str], pd.Timestamp | None] = {}
    for day in range(days):
        date = pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(day, unit="D")
        for model in range(models):
            for provider in range(providers):
                key = (f"m{model}", f"p{provider}")
                event = (day * 3 + model * 5 + provider * 7) % 11 < 2
                previous = starts.get(key)
                age = (date - previous).days if previous is not None else np.nan
                rows.append(
                    {
                        "dt": date.strftime("%Y-%m-%d"),
                        "d": date,
                        "model_id": key[0],
                        "provider_name": key[1],
                        "price": 0.4 + model * 0.03 + provider * 0.02 + day * 0.0005,
                        "event": event,
                        "any_raise": int(event and (day + provider) % 2 == 0),
                        "age": age,
                        "age_censored": previous is None,
                        "dow": date.dayofweek,
                        "gpu_dlog": 0.01 * np.sin(day / 3),
                        "util": 0.2 + 0.01 * ((day + provider) % 7),
                        "rl": 0.005 * ((day + model) % 5),
                    }
                )
                if event:
                    starts[key] = date
    return pd.DataFrame(rows)


def test_registered_split_uses_completed_dates_and_fixed_15_15_prefix() -> None:
    dates = pd.date_range("2026-01-01", periods=31, freq="D")
    split = registered_temporal_split(dates, as_of_date="2026-01-31")

    assert split["ready"] is True
    assert split["completed_dates"] == 30
    assert split["excluded_open_or_future_dates"] == ["2026-01-31"]
    assert split["train_dates"] == [f"2026-01-{day:02d}" for day in range(1, 16)]
    assert split["test_dates"] == [f"2026-01-{day:02d}" for day in range(16, 31)]


def test_prior_close_features_cannot_see_same_day_price_or_move() -> None:
    base = _panel(days=3, models=1, providers=2)
    changed = base.copy()
    target = (
        (changed["dt"] == "2026-01-02")
        & (changed["provider_name"] == "p0")
    )
    changed.loc[target, "price"] *= 10
    changed.loc[target, "event"] = ~changed.loc[target, "event"].astype(bool)

    prepared_base = prepare_ex_ante_panel(base)
    prepared_changed = prepare_ex_ante_panel(changed)
    key = ["dt", "model_id", "provider_name"]
    columns = ["gap_lag1", "rival_moves_lag1"]
    merged = prepared_base[key + columns].merge(
        prepared_changed[key + columns], on=key, suffixes=("_base", "_changed")
    )

    day_two = merged[merged["dt"] == "2026-01-02"]
    np.testing.assert_allclose(
        day_two["gap_lag1_base"], day_two["gap_lag1_changed"], equal_nan=True
    )
    np.testing.assert_allclose(
        day_two["rival_moves_lag1_base"],
        day_two["rival_moves_lag1_changed"],
        equal_nan=True,
    )
    day_three = merged[
        (merged["dt"] == "2026-01-03") & (merged["provider_name"] == "p1")
    ].iloc[0]
    assert day_three["gap_lag1_base"] != pytest.approx(day_three["gap_lag1_changed"])
    assert day_three["rival_moves_lag1_base"] != day_three["rival_moves_lag1_changed"]


def test_prior_close_panel_fails_closed_on_duplicate_risk_rows() -> None:
    panel = _panel(days=3, models=1, providers=2)
    duplicated = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="one row per provider-model-day"):
        prepare_ex_ante_panel(duplicated)


def test_provider_activity_encoding_does_not_use_test_outcomes() -> None:
    panel = _panel(days=4, models=2, providers=2)
    train = panel[panel["dt"] <= "2026-01-02"]
    test = panel[panel["dt"] > "2026-01-02"]
    _, encoded = assign_training_provider_rates(train, test)
    flipped = test.copy()
    flipped["event"] = ~flipped["event"].astype(bool)
    _, encoded_flipped = assign_training_provider_rates(train, flipped)

    np.testing.assert_allclose(
        encoded["provider_rate_train"], encoded_flipped["provider_rate_train"]
    )


def test_exact_sign_flip_is_enumerated_at_date_cluster_level() -> None:
    assert _exact_sign_flip_p(np.ones(15)) == pytest.approx(1 / 2**15)
    assert _exact_sign_flip_p(np.array([])) is None


def test_run_is_result_blind_before_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORCAP_ANALYSIS_SOURCE", "local")
    summary = run(
        tmp_path,
        endpoint_dates=pd.date_range("2026-01-01", periods=12, freq="D").tolist(),
        panel=None,
        as_of_date="2026-01-13",
    )

    assert summary["evidence_status"] == "not_run_before_30_completed_date_gate"
    assert summary["pricing_events_queried"] is False
    assert summary["split"]["remaining_completed_dates"] == 18
    assert (tmp_path / "pm1_temporal_validation_summary.json").exists()
    assert pd.read_parquet(tmp_path / "pm1_temporal_validation_predictions.parquet").empty


def test_ready_run_uses_one_fixed_holdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORCAP_ANALYSIS_SOURCE", "local")
    panel = _panel()
    summary = run(
        tmp_path,
        endpoint_dates=panel["dt"].drop_duplicates().tolist(),
        panel=panel,
        as_of_date="2026-02-01",
    )

    assert summary["evidence_status"] == "temporal_holdout_released"
    assert summary["pricing_events_queried"] is True
    assert summary["split"]["train_target_days"] == 15
    assert summary["split"]["test_target_days"] == 15
    assert set(summary["rung_metrics"]) == {"L1", "L2", "L3", "L4", "L5"}
    assert set(summary["contrasts"]) == {
        "L2_vs_L1",
        "L3_vs_L2",
        "L4_vs_L3",
        "L5_vs_L4",
    }
    predictions = pd.read_parquet(tmp_path / "pm1_temporal_validation_predictions.parquet")
    assert predictions["dt"].nunique() == 15
    assert predictions["dt"].min() == "2026-01-16"
    assert predictions["dt"].max() == "2026-01-30"
