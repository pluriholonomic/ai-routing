from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / "papers/icml/credit-propagation-diagnostic.json"
FROZEN = ROOT / "output/market_env/esim6/93265b9b03/results.json"


def test_credit_diagnostic_reconciles_to_frozen_esim6():
    diagnostic = json.loads(DIAGNOSTIC.read_text(encoding="utf-8"))
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    calibrated = next(arm for arm in frozen["sweep"] if arm["memory"] == 7)
    frozen_action = {
        int(row["seed"]): int(row["primitive_q"]["first_action"])
        for row in calibrated["rows"]
    }
    rows = diagnostic["rows"]
    assert len(rows) == diagnostic["seeds"] == 20
    assert {int(row["seed"]) for row in rows} == set(range(20))
    assert diagnostic["frozen_q_tables_reproduced"]
    assert max(float(row["max_frozen_q_table_error"]) for row in rows) <= 1e-12
    assert {
        int(row["seed"]): int(row["final_initial_action"]) for row in rows
    } == frozen_action


def test_credit_diagnostic_separates_early_discovery_from_late_support():
    diagnostic = json.loads(DIAGNOSTIC.read_text(encoding="utf-8"))
    rows = diagnostic["rows"]
    failed = [row for row in rows if row["final_initial_action_label"] == "high"]
    first_hits = [int(row["first_all_low_transition"]) for row in rows]
    assert diagnostic["first_all_low_transition_range"] == [min(first_hits), max(first_hits)]
    assert diagnostic["first_all_low_transition_range"] == [7, 901]
    assert len(failed) == diagnostic["failed_initial_policies"] == 19
    assert diagnostic["failed_with_any_depth_5_visit_after_100k"] == 0
    assert diagnostic["failed_with_any_all_low_transition_after_100k"] == 0
    assert all(int(row["deepest_depth_after_100k"]) < 5 for row in failed)


def test_complete_early_model_supports_ordered_offline_backups():
    diagnostic = json.loads(DIAGNOSTIC.read_text(encoding="utf-8"))
    rows = diagnostic["rows"]
    assert diagnostic["seeds_with_full_state_action_coverage"] == 20
    assert diagnostic["batch_model_correct_initial_action"] == 20
    assert all(int(row["minimum_state_action_visits"]) > 0 for row in rows)
    assert max(float(row["batch_model_max_value_error"]) for row in rows) <= 1e-10
