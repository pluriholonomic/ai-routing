from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from orcap.analysis import pm5_heldout_matched_market as heldout


def _quotes() -> pd.DataFrame:
    rows = []
    snapshots = {
        "2026-01-01T00:00:00Z": {
            "focal": {"p1": 1.0, "p2": 3.0},
            "decoy-a": {"p3": 2.0, "p4": 4.0},
            "decoy-b": {"p5": 5.0, "p6": 6.0},
        },
        "2026-01-01T00:05:00Z": {
            "focal": {"p1": 2.0, "p2": 3.0},
            "decoy-a": {"p3": 2.0, "p4": 4.0},
            "decoy-b": {"p5": 5.0, "p6": 6.0},
        },
    }
    for timestamp, markets in snapshots.items():
        for model_id, providers in markets.items():
            for provider_name, price in providers.items():
                rows.append(
                    {
                        "run_ts": timestamp,
                        "model_id": model_id,
                        "provider_name": provider_name,
                        "price": price,
                    }
                )
    return pd.DataFrame(rows)


def test_registered_split_refuses_partial_holdout_and_freezes_15_15() -> None:
    partial = heldout.registered_split(
        pd.date_range("2026-01-01", periods=29, freq="D").tolist()
    )
    assert partial["ready"] is False
    assert partial["training_dates"] == []
    assert partial["holdout_dates"] == []
    complete = heldout.registered_split(
        pd.date_range("2026-01-01", periods=31, freq="D").tolist()
    )
    assert complete["ready"] is True
    assert len(complete["training_dates"]) == 15
    assert len(complete["holdout_dates"]) == 15
    assert complete["holdout_end"] == "2026-01-30"


def test_whole_market_probability_preserves_decoy_multiplicity() -> None:
    quotes = _quotes()
    states = heldout.market_state_panel(quotes)
    scaler = heldout.fit_feature_scaler(states, ["2026-01-01"])
    events = pd.DataFrame(
        {
            "model_id": ["focal"],
            "provider_name": ["p1"],
            "previous_run_ts": pd.to_datetime(["2026-01-01T00:00:00Z"], utc=True),
            "run_ts": pd.to_datetime(["2026-01-01T00:05:00Z"], utc=True),
            "new_price": [2.0],
            "n_rival_quotes": [1],
            "exact_lagged_rival_match": [0.0],
        }
    )
    panel = heldout.attach_matched_market_probability(
        events,
        quotes,
        scaler,
        match_count=2,
        minimum_decoys=2,
    )
    # Decoy A has one hit in two endpoints (1/2); decoy B has none.
    assert panel.loc[0, "matched_market_probability"] == pytest.approx(0.25)
    assert panel.loc[0, "matched_market_used_decoys"] == 2
    assert panel.loc[0, "exact_minus_matched_market"] == pytest.approx(-0.25)


def test_training_fitted_increment_and_holdout_scoring_are_frozen() -> None:
    training = pd.DataFrame(
        {
            "exact_lagged_rival_match": [1.0] * 8 + [0.0] * 2,
            "matched_market_probability": [0.2] * 10,
        }
    )
    fit = heldout.fit_response_increment(training)
    assert 0 < fit["rho"] < 1
    holdout_panel = training.assign(model_id=["a"] * 5 + ["b"] * 5)
    scored = heldout.score_response_models(holdout_panel, rho=float(fit["rho"]))
    assert scored["m1_probability"].gt(scored["m0_probability"]).all()
    assert scored["m1_minus_m0_log_score"].mean() > 0


def test_gate_path_never_loads_quotes_or_emits_outcome_table(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    @contextmanager
    def fake_source():
        yield {"source": "test", "revision": "frozen"}

    class Relation:
        def df(self) -> pd.DataFrame:
            return pd.DataFrame(
                {"dt": pd.date_range("2026-01-01", periods=29, freq="D")}
            )

    monkeypatch.setattr(heldout.data, "pinned_analysis_source", fake_source)
    monkeypatch.setattr(heldout.data, "q", lambda _query: Relation())
    monkeypatch.setattr(
        heldout,
        "quote_ticks",
        lambda: (_ for _ in ()).throw(AssertionError("quote outcomes were loaded")),
    )
    summary = heldout.run(tmp_path)
    assert summary["outcomes_loaded"] is False
    assert summary["split"]["remaining_days"] == 1
    assert not (tmp_path / "pm5_heldout_matched_market_panel.parquet").exists()
    assert (tmp_path / "pm5_heldout_matched_market_summary.json").exists()


def test_complete_split_runs_training_and_holdout_without_refitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = []
    dates = pd.date_range("2026-01-01", periods=30, freq="D", tz="UTC")
    for day in dates:
        for minute, moved in ((0, False), (5, True)):
            timestamp = day.to_pydatetime() + timedelta(minutes=minute)
            for model_index in range(6):
                base = float(10 * model_index + 1)
                rows.extend(
                    [
                        {
                            "run_ts": timestamp,
                            "model_id": f"model-{model_index}",
                            "provider_name": "p0",
                            "price": base + (1 if moved else 0),
                        },
                        {
                            "run_ts": timestamp,
                            "model_id": f"model-{model_index}",
                            "provider_name": "p1",
                            "price": base + 1,
                        },
                    ]
                )
    monkeypatch.setattr(heldout, "BOOTSTRAP_DRAWS", 100)
    split = heldout.registered_split(dates.tolist())
    panel, comparison, summary = heldout.heldout_experiment(pd.DataFrame(rows), split)
    assert summary["training_fit"]["n_training_events"] == 90
    assert len(panel) == 90
    assert len(comparison) == 3
    assert summary["holdout_support"]["models"] == 6
    assert summary["holdout_support"]["passes"] is False
    assert summary["predictive_promotion"] is False
