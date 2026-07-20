from __future__ import annotations

import json

from orcap.analysis.adaptive_adversarial_report import build_scorecard


def test_scorecard_is_explicitly_screening_and_handles_missing_components(tmp_path):
    result = build_scorecard(
        replay_path=tmp_path / "missing-replay.json",
        simulation_path=tmp_path / "missing-simulation.json",
        out_dir=tmp_path / "out",
    )
    assert result["status"] == "awaiting_components"
    assert result["verdict"] == "screening_mixed_or_incomplete"
    assert (tmp_path / "out" / "adaptive-adversarial-scorecard.html").exists()


def test_scorecard_computes_hardened_to_baseline_ratios(tmp_path):
    replay = {
        "menus": 2,
        "models": 1,
        "dates": 2,
        "policies": [
            {
                "policy": "baseline_eta2",
                "mean_max_share_gain": 0.2,
                "p95_max_share_gain": 0.3,
                "mean_quote_fade_share": 0.4,
                "mean_sybil_gain": 0.2,
            },
            {
                "policy": "menu_adaptive_hardened",
                "mean_max_share_gain": 0.1,
                "p95_max_share_gain": 0.15,
                "mean_quote_fade_share": 0.2,
                "mean_sybil_gain": 0.0,
            },
        ],
    }
    simulation = {
        "menus": 2,
        "static_cells": 8,
        "learning_runs": 4,
        "q_learning_runs": 4,
        "policies": [
            {
                "policy": "baseline_eta2",
                "mean_unilateral_exploitability": 2.0,
                "p95_unilateral_exploitability": 3.0,
                "mean_coalition_exploitability": 4.0,
            },
            {
                "policy": "menu_adaptive_hardened",
                "mean_unilateral_exploitability": 1.0,
                "p95_unilateral_exploitability": 1.5,
                "mean_coalition_exploitability": 2.0,
            },
        ],
        "learning": [
            {"policy": "baseline_eta2", "mean_post_learning_exploitability": 2.0},
            {
                "policy": "menu_adaptive_hardened",
                "mean_post_learning_exploitability": 1.0,
            },
        ],
        "q_learning": [],
    }
    replay_path = tmp_path / "replay.json"
    simulation_path = tmp_path / "simulation.json"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    simulation_path.write_text(json.dumps(simulation), encoding="utf-8")
    result = build_scorecard(
        replay_path=replay_path,
        simulation_path=simulation_path,
        out_dir=tmp_path / "out",
    )
    assert result["status"] == "screening_complete"
    assert result["descriptive_all_ratio_metrics_nonworsening"] is True
    assert result["comparisons_hardened_over_baseline"][
        "simulation_p95_unilateral_exploitability_ratio"
    ] == 0.5

