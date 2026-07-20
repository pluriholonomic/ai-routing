from __future__ import annotations

import json

import pandas as pd

from orcap.analysis.adaptive_adversarial_replay import run_replay
from orcap.analysis.adaptive_adversarial_simulation import (
    _market_from_menu,
    router_for,
    run_simulation,
    sequential_best_response,
    train_q_screen,
    train_ucb_market,
)


def _menu() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "provider_name": ["A", "B", "C"],
            "expected_quote_usd": [1.0, 1.2, 1.5],
            "quality": [0.99, 0.98, 0.97],
        }
    )


def test_market_calibration_preserves_cost_and_capacity_bands():
    specs, actions = _market_from_menu(
        _menu(), cost_fraction=0.5, capacity_multiplier=1.0, demand=120
    )
    assert len(specs) == 3
    assert sum(spec.physical_capacity for spec in specs.values()) == 120
    for provider in specs:
        assert specs[provider].marginal_cost == 0.5 * actions[provider].quote


def test_sequential_best_response_is_deterministic_and_audited():
    specs, actions = _market_from_menu(
        _menu(), cost_fraction=0.5, capacity_multiplier=2.0, demand=30
    )
    first = sequential_best_response(
        router_for("fixed_eta125_eps10"), specs, actions, demand=30, rounds=4
    )
    second = sequential_best_response(
        router_for("fixed_eta125_eps10"), specs, actions, demand=30, rounds=4
    )
    assert first == second
    assert set(first["final_quotes"]) == set(specs)
    assert first["max_deviation_gain"] >= -1e-12


def test_ucb_market_is_seeded_and_retains_exploitability_audit():
    specs, actions = _market_from_menu(
        _menu(), cost_fraction=0.5, capacity_multiplier=2.0, demand=30
    )
    first = train_ucb_market(
        router_for("baseline_eta2"),
        specs,
        actions,
        demand=30,
        steps=30,
        seed=4,
    )
    second = train_ucb_market(
        router_for("baseline_eta2"),
        specs,
        actions,
        demand=30,
        steps=30,
        seed=4,
    )
    assert first == second
    assert first["max_deviation_gain"] >= -1e-12
    different = train_ucb_market(
        router_for("baseline_eta2"),
        specs,
        actions,
        demand=30,
        steps=100,
        seed=5,
    )
    reference = train_ucb_market(
        router_for("baseline_eta2"),
        specs,
        actions,
        demand=30,
        steps=100,
        seed=4,
    )
    assert different["mean_tail_profit"] != reference["mean_tail_profit"]
    assert "realized multinomial" in different["training_reward"]


def test_q_screen_is_bounded_and_serializable():
    rows = train_q_screen("baseline_eta2", seeds=1, max_epochs=200)
    assert len(rows) == 1
    assert rows[0]["epochs_run"] <= 200
    assert rows[0]["policy"] == "baseline_eta2"
    assert isinstance(rows[0]["final_prices_json"], str)


def test_replay_and_simulation_execute_end_to_end_on_parquet_fixture(tmp_path):
    source = tmp_path / "data" / "curated" / "endpoints_snapshots" / "dt=2026-07-20"
    source.mkdir(parents=True)
    pd.DataFrame(
        {
            "run_ts": ["20260720T000000Z"] * 3,
            "dt": ["2026-07-20"] * 3,
            "model_id": ["example/model"] * 3,
            "provider_name": ["A", "B", "C"],
            "tag": ["a", "b", "c"],
            "price_prompt": [0.01, 0.012, 0.015],
            "price_completion": [0.01, 0.012, 0.015],
            "uptime_last_30m": [99.0, 98.0, 97.0],
            "status": [0, 0, 0],
        }
    ).to_parquet(source / "fixture.parquet", index=False)
    replay = run_replay(
        data_root=tmp_path / "data",
        out_dir=tmp_path / "replay",
        max_menus=1,
        max_attack_providers=2,
        bootstrap_draws=10,
    )
    simulation = run_simulation(
        data_root=tmp_path / "data",
        out_dir=tmp_path / "simulation",
        max_menus=1,
        learning_menus=1,
        learning_steps=10,
        learning_seeds=1,
        q_learning_epochs=20,
        demand=12,
    )
    assert replay["menus"] == 1
    assert simulation["menus"] == 1
    assert simulation["learning_runs"] == 4
    assert (tmp_path / "replay" / "adaptive-adversarial-summary.json").exists()
    assert (
        tmp_path
        / "simulation"
        / "adaptive-adversarial-simulation-summary.json"
    ).exists()
    serialized = (
        tmp_path
        / "simulation"
        / "adaptive-adversarial-simulation-summary.json"
    ).read_text(encoding="utf-8")
    assert "NaN" not in serialized
    assert json.loads(serialized)["status"] == "complete"


def test_future_only_date_window_rejects_pre_freeze_menus(tmp_path):
    root = tmp_path / "data"
    for date in ("2026-07-20", "2026-07-21"):
        source = root / "curated" / "endpoints_snapshots" / f"dt={date}"
        source.mkdir(parents=True)
        compact = date.replace("-", "")
        pd.DataFrame(
            {
                "run_ts": [f"{compact}T000000Z"] * 3,
                "dt": [date] * 3,
                "model_id": ["example/model"] * 3,
                "provider_name": ["A", "B", "C"],
                "tag": ["a", "b", "c"],
                "price_prompt": [0.01, 0.012, 0.015],
                "price_completion": [0.01, 0.012, 0.015],
                "uptime_last_30m": [99.0, 98.0, 97.0],
                "status": [0, 0, 0],
            }
        ).to_parquet(source / "fixture.parquet", index=False)
    replay = run_replay(
        data_root=root,
        out_dir=tmp_path / "replay-future",
        max_menus=10,
        max_attack_providers=1,
        bootstrap_draws=5,
        start_date="2026-07-21",
        end_date="2026-07-21",
    )
    simulation = run_simulation(
        data_root=root,
        out_dir=tmp_path / "simulation-future",
        max_menus=10,
        learning_menus=1,
        learning_steps=2,
        learning_seeds=1,
        q_learning_epochs=2,
        demand=12,
        start_date="2026-07-21",
        end_date="2026-07-21",
    )
    assert replay["date_window"]["observed_min"] == "2026-07-21"
    assert replay["date_window"]["observed_max"] == "2026-07-21"
    assert simulation["date_window"]["observed_min"] == "2026-07-21"
    assert simulation["date_window"]["observed_max"] == "2026-07-21"
