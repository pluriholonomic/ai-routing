from __future__ import annotations

from pathlib import Path

import pandas as pd

from orcap.analysis import wf16_provider_type_validation as wf16


def _quotes() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2026-01-01", periods=10, tz="UTC")
    providers = {
        "Author": [1.0] * 10,
        "Premium": [1.2] * 10,
        "Anchor": [1.0] * 10,
        "Static": [0.8] * 10,
        "Active": [0.7] * 10,
    }
    for date in dates:
        for provider, prices in providers.items():
            rows.append(
                {
                    "dt": date,
                    "model_id": "author/model",
                    "provider_name": provider,
                    "price_completion": prices[(date - dates[0]).days],
                }
            )
    return pd.DataFrame(rows)


def _anchored() -> pd.DataFrame:
    quotes = _quotes()
    author = quotes[quotes.provider_name == "Author"][
        ["model_id", "dt", "price_completion"]
    ].rename(columns={"price_completion": "author_price"})
    joined = quotes[quotes.provider_name != "Author"].merge(author, on=["model_id", "dt"])
    joined["at_anchor"] = joined.price_completion == joined.author_price
    joined["log_wedge"] = __import__("numpy").log(
        joined.price_completion / joined.author_price
    )
    return joined


def _changes() -> pd.DataFrame:
    rows = []
    for day in range(1, 10):
        for provider in ("Active",):
            ts = pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(day, unit="D")
            rows.append(
                {
                    "changed_at_run_ts": ts.strftime("%Y%m%dT%H%M%SZ"),
                    "dt": ts.normalize(),
                    "ts": ts,
                    "model_id": "author/model",
                    "provider_name": provider,
                    "old_price": 0.72,
                    "new_price": 0.70,
                }
            )
    return pd.DataFrame(rows)


def test_frozen_four_type_classification_and_holdout_persistence():
    quotes = _anchored()
    changes = _changes()
    split = pd.Timestamp("2026-01-07", tz="UTC")
    labels = wf16.classify_pairs(
        quotes[quotes.dt < split],
        changes[changes.dt < split],
        min_days=5,
        adoption_share=0.8,
        active_changes_per_day=0.05,
    )
    types = labels.set_index("provider_name").provider_type.to_dict()
    assert types == {
        "Active": "active_undercutter",
        "Anchor": "anchor_adopter",
        "Premium": "premium_differentiated",
        "Static": "static_discounter",
    }

    protocol, _ = wf16.load_protocol()
    transitions = wf16.build_holdout_transitions(
        labels,
        quotes[quotes.dt >= split],
        changes[changes.dt >= split],
        protocol,
    )
    assert transitions.type_persisted.all()


def test_response_panel_uses_frozen_shifted_placebo():
    labels = pd.DataFrame(
        [
            {
                "model_id": "author/model",
                "provider_name": "Active",
                "provider_type": "active_undercutter",
            }
        ]
    )
    changes = pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-01-02T00:00:00Z"),
                "model_id": "author/model",
                "provider_name": "Rival",
                "old_price": 1.0,
                "new_price": 0.9,
            },
            {
                "ts": pd.Timestamp("2026-01-02T02:00:00Z"),
                "model_id": "author/model",
                "provider_name": "Active",
                "old_price": 0.8,
                "new_price": 0.7,
            },
            {
                "ts": pd.Timestamp("2026-01-06T00:00:00Z"),
                "model_id": "author/model",
                "provider_name": "Rival",
                "old_price": 0.9,
                "new_price": 1.0,
            },
        ]
    )
    panel = wf16.build_response_panel(
        changes,
        labels,
        pd.Timestamp("2026-01-01", tz="UTC"),
        window_hours=12,
        placebo_shift_hours=48,
    )
    observed = panel[panel.arm == "observed"]
    placebo = panel[panel.arm == "shifted_placebo"]
    assert observed.responded.any()
    assert not placebo.responded.any()


def test_dumping_screen_never_promotes_to_supported():
    labels = pd.DataFrame(
        [
            {
                "model_id": "author/model",
                "provider_name": "Active",
                "provider_type": "active_undercutter",
                "median_log_wedge": -0.5,
            }
        ]
    )
    capacity = pd.DataFrame(
        [
            {
                "model_id": "author/model",
                "provider_name": "Active",
                "below_cost_bound_share": 1.0,
                "utilization": 0.9,
            }
        ]
    )
    fades = pd.DataFrame(
        [
            {
                "cut_event_id": 1,
                "model_id": "author/model",
                "provider_name": "Active",
                "faded_within_window": True,
            }
        ]
    )
    fills = pd.DataFrame(
        [
            {
                "model_id": "author/model",
                "provider_name": "Active",
                "probe_mode": "delegated_routing_selection",
                "attempts": 2,
                "selected_count": 1,
            }
        ]
    )
    score = wf16.build_dumping_scorecard(labels, capacity, fades, fills).iloc[0]
    assert bool(score.dumping_candidate)
    assert not bool(score.dumping_supported)
    assert "not observed" in score.missing_identification_leg


def test_run_writes_complete_bundle(monkeypatch, tmp_path: Path):
    quotes = _quotes()
    changes = _changes()
    slug = pd.DataFrame([{"canonical_slug": "author/model", "model_id": "author/model"}])
    congestion = pd.DataFrame(
        [
            {
                "run_ts": "20260109T000000Z",
                "dt": pd.Timestamp("2026-01-09", tz="UTC"),
                "ts": pd.Timestamp("2026-01-09", tz="UTC"),
                "model_permaslug": "author/model",
                "provider_name": provider,
                "price_completion": price,
                "throughput": 20.0,
                "latency": 0.5,
                "requests": 10.0,
                "peak_rpm": 8.0,
                "capacity_rpm": 10.0,
                "rate_limited": 0.0,
                "derankable_errors": 0.0,
                "is_deranked": False,
            }
            for provider, price in (
                ("Premium", 1.2),
                ("Anchor", 1.0),
                ("Static", 0.8),
                ("Active", 0.7),
            )
        ]
    )
    monkeypatch.setenv("ORCAP_ANALYSIS_SOURCE", "local")
    monkeypatch.setattr(wf16, "load_daily_quotes", lambda: quotes)
    monkeypatch.setattr(wf16, "load_price_changes", lambda: changes)
    monkeypatch.setattr(wf16, "load_slug_map", lambda: slug)
    monkeypatch.setattr(wf16, "load_congestion", lambda: congestion)
    monkeypatch.setattr(wf16, "load_paid_attempts", pd.DataFrame)
    monkeypatch.setattr(
        wf16,
        "add_author_anchor",
        lambda _quotes, _rtol: _anchored(),
    )

    summary = wf16.run(tmp_path)

    assert summary["n_training_pairs"] == 4
    assert summary["dumping_supported"] is False
    assert (tmp_path / "wf16_summary.json").is_file()
    assert (tmp_path / "wf16_provider_type_validation.png").is_file()
    assert (tmp_path / "wf16_provider_type_validation.pdf").is_file()
    assert len(list(tmp_path.glob("wf16_*.parquet"))) == 9
