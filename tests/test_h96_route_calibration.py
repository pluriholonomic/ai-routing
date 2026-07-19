from __future__ import annotations

import json

import numpy as np
import pandas as pd

from orcap.analysis import h96_route_calibration as h96


def _candidate_rows(run_id: str, block_id: str) -> list[dict]:
    return [
        {
            "run_id": run_id,
            "block_id": block_id,
            "study_id": h96.STUDY_ID,
            "model_id": "org/model",
            "shape_id": "short_chat",
            "provider_name": "Cheap",
            "expected_quote_usd": 1.0,
            "price_index_per_token": 1.0,
            "compatible": True,
        },
        {
            "run_id": run_id,
            "block_id": block_id,
            "study_id": h96.STUDY_ID,
            "model_id": "org/model",
            "shape_id": "short_chat",
            "provider_name": "Backup",
            "expected_quote_usd": 2.0,
            "price_index_per_token": 2.0,
            "compatible": True,
        },
    ]


def _attempt(task_id: str, provider: str, policy: str) -> dict:
    return {
        "study_id": h96.STUDY_ID,
        "selected_provider": provider,
        "outcome": "succeeded",
        "cost_usd": 0.001,
        "latency_ms": 10.0,
        "input_tokens": 64,
        "output_tokens": 8,
        "metadata_json": json.dumps({"task_id": task_id}),
        "policy": policy,
    }


def test_fit_eta_recovers_strong_price_preference() -> None:
    observations = [
        {
            "costs": np.array([1.0, 2.0]),
            "selected_index": 0 if index < 35 else 1,
        }
        for index in range(40)
    ]
    result = h96.fit_eta(observations)

    assert result["fit_ready"] is True
    assert result["n_fit"] == 40
    assert result["eta_hat"] > 1.0
    assert result["eta_profile_ci_low"] <= result["eta_hat"]
    assert result["eta_profile_ci_high"] >= result["eta_hat"]


def test_full_analysis_uses_chronological_holdout_and_builds_policy_audits() -> None:
    candidates: list[dict] = []
    assignments: list[dict] = []
    attempts: list[dict] = []
    for run_index in range(10):
        run_id = f"20260719T{run_index:02d}0000Z"
        block_id = f"block-{run_index}"
        candidates += _candidate_rows(run_id, block_id)
        for replicate in range(3):
            task_id = f"default-{run_index}-{replicate}"
            assignments.append(
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "block_id": block_id,
                    "model_id": "org/model",
                    "shape_id": "short_chat",
                    "policy": "default_budgeted_iid",
                    "requested_provider": None,
                    "sticky_pair_id": None,
                }
            )
            selected = "Cheap" if replicate < 2 else "Backup"
            attempts.append(_attempt(task_id, selected, "default_budgeted_iid"))

    block_id = "block-9"
    extra = [
        ("sort", "sort_price", None, "Cheap", None),
        ("pin", "pinned_cheapest", "Cheap", "Cheap", None),
        ("sticky-seed", "default_sticky_seed", None, "Backup", "pair-1"),
        ("sticky-repeat", "default_sticky_repeat", None, "Backup", "pair-1"),
    ]
    for task_id, policy, requested, selected, pair in extra:
        assignments.append(
            {
                "run_id": "20260719T090000Z",
                "task_id": task_id,
                "block_id": block_id,
                "model_id": "org/model",
                "shape_id": "short_chat",
                "policy": policy,
                "requested_provider": requested,
                "sticky_pair_id": pair,
            }
        )
        attempts.append(_attempt(task_id, selected, policy))

    scores, audit, summary = h96.analyze_frames(
        pd.DataFrame(candidates), pd.DataFrame(assignments), pd.DataFrame(attempts)
    )

    assert summary["split_rule"] == "chronological_70_30_by_run"
    assert summary["fit"]["fit_ready"] is True
    assert summary["fit"]["n_fit"] == 21
    assert len(scores) == 9
    assert scores["selected_in_public_menu"].all()
    assert set(audit["audit"]) == {
        "pinned_provider_match",
        "sort_price_cheapest_match",
        "sticky_provider_repeat",
    }
    assert audit["success"].all()


def test_out_of_menu_selection_is_flagged_not_silently_dropped() -> None:
    candidates = pd.DataFrame(_candidate_rows("run-1", "block-1"))
    assignments = pd.DataFrame(
        [
            {
                "run_id": "run-1",
                "task_id": "task-1",
                "block_id": "block-1",
                "model_id": "org/model",
                "shape_id": "short_chat",
                "policy": "default_budgeted_iid",
                "requested_provider": None,
                "sticky_pair_id": None,
            }
        ]
    )
    attempts = pd.DataFrame([_attempt("task-1", "Private Health Winner", "default_budgeted_iid")])

    scores, _, summary = h96.analyze_frames(candidates, assignments, attempts)

    assert len(scores) == 1
    assert not bool(scores.iloc[0]["selected_in_public_menu"])
    assert summary["evaluation_at_eta_hat_or_two"]["candidate_coverage_rate"] == 0.0
    assert summary["evaluation_at_eta_hat_or_two"]["mean_log_loss"] is None


def test_empty_inputs_return_not_ready_summary() -> None:
    scores, audit, summary = h96.analyze_frames(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    )
    assert scores.empty and audit.empty
    assert summary["fit"]["fit_ready"] is False
    assert summary["independent_default_observations"] == 0
