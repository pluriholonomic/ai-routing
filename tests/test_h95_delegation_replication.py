from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta

import pandas as pd

import orcap.analysis.h95_delegation_replication as h95
from orcap.capture_decomposition_probes import POLICIES
from orcap.capture_decomposition_replication import STUDY_ID, tasks_with_assigned_first


def _frames(triplets: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligibility: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    provider_order = ["cheap", "backup"]
    endpoints = [
        {"provider": "cheap", "price": 1.0, "input_price": 0.0},
        {"provider": "backup", "price": 2.0, "input_price": 0.0},
    ]
    for triplet_index in range(triplets):
        triplet_id = f"{STUDY_ID}|triplet-{triplet_index:03d}"
        observed_at = datetime(2026, 7, 17, 5, tzinfo=UTC) + timedelta(
            hours=triplet_index
        )
        for position, policy in enumerate(POLICIES):
            model_id = f"org/model-{(triplet_index + position) % 9}"
            block_id = f"{triplet_id}|{model_id}"
            block_seed = 10_000 + triplet_index * 3 + position
            eligibility.append(
                {
                    "run_id": f"triplet-{triplet_index:03d}",
                    "run_ts": observed_at.strftime("%Y%m%dT%H%M%SZ"),
                    "observed_at": observed_at.isoformat(),
                    "study_id": STUDY_ID,
                    "triplet_id": triplet_id,
                    "ranking_position": 7 + (triplet_index + position) % 24,
                    "model_id": model_id,
                    "hugging_face_id": model_id,
                    "eligible": True,
                    "selected_for_triplet": True,
                    "assigned_first_policy": policy,
                    "block_id": block_id,
                }
            )
            tasks = tasks_with_assigned_first(
                endpoints, policy, random.Random(block_seed)
            )
            for policy_order, task in enumerate(tasks):
                metadata = {
                    "triplet_id": triplet_id,
                    "block_id": block_id,
                    "assigned_first_policy": policy,
                    "policy_order": policy_order,
                    "block_seed": block_seed,
                    "ranking_position": 7 + (triplet_index + position) % 24,
                    "hugging_face_id": model_id,
                    "public_provider_order": provider_order,
                    "assignment_probability_first": 1 / 3,
                }
                attempts.append(
                    {
                        "source": "openrouter_generation",
                        "event_id": f"{block_id}|{policy_order}",
                        "run_ts": observed_at.strftime("%Y%m%dT%H%M%SZ"),
                        "observed_at": (
                            observed_at + timedelta(seconds=policy_order)
                        ).isoformat(),
                        "study_id": STUDY_ID,
                        "model_id": model_id,
                        "policy": task["policy"],
                        "metadata_json": json.dumps(metadata),
                        "outcome": (
                            "succeeded"
                            if policy in {"delegated_default", "price_order_fallback"}
                            else "failed"
                        ),
                    }
                )
    return pd.DataFrame(eligibility), pd.DataFrame(attempts)


def test_gate_is_assignment_only_before_fixed_horizon() -> None:
    eligibility, attempts = _frames(4)
    prepared = h95.prepare_assignment_attempts(
        attempts.drop(columns=["outcome"])
    )
    summary, audit, _, plans = h95.gate_summary(
        prepared, eligibility, simulations=200
    )

    assert summary["release_ready"] is False
    assert summary["outcome_access"] == "not_queried_by_fixed_horizon_gate"
    assert summary["planned_triplets"] == 4
    assert summary["planned_first_position_blocks"] == 12
    assert audit["complete_assignment"].all()
    assert audit["plan_compliance"].all()
    assert audit["replay_passes"].sum() == 12
    assert len(plans) == 12


def test_fixed_horizon_releases_exact_balance_and_blocked_contrasts() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, audit, _, plans = h95.gate_summary(
        prepared, eligibility, simulations=500
    )
    assert summary["release_ready"] is True
    assert len(plans) == 360
    assert audit["complete_assignment"].all()

    panel, models, contrasts, released = h95.analyze_released(
        attempts, plans, summary, simulations=500
    )

    assert panel.set_index("policy")["assigned_blocks"].to_dict() == {
        policy: 120 for policy in POLICIES
    }
    estimates = contrasts.set_index("estimand")["success_difference"].to_dict()
    assert estimates["fallback_option_value"] == 1.0
    assert estimates["hidden_selection_value"] == 0.0
    assert estimates["total_delegation_value"] == 1.0
    assert released["primary_missing_attempts"] == 0
    assert released["primary_assignment_compliance_rate"] == 1.0
    assert models["model_id"].nunique() == 9


def test_run_never_queries_outcomes_while_gate_is_closed(monkeypatch, tmp_path) -> None:
    eligibility, attempts = _frames(2)
    assignment = attempts.drop(columns=["outcome"])
    queries: list[str] = []

    class Relation:
        def __init__(self, frame):
            self.frame = frame

        def df(self):
            return self.frame.copy()

    def fake_q(sql: str):
        queries.append(sql)
        if "router_replication_eligibility" in sql:
            return Relation(eligibility)
        assert "outcome" not in sql.lower()
        assert "cost_usd" not in sql.lower()
        assert "selected_provider" not in sql.lower()
        return Relation(assignment)

    monkeypatch.setattr(h95.data, "q", fake_q)
    summary = h95.run(tmp_path, simulations=100)

    assert summary["outcomes_released"] is False
    assert len(queries) == 2
    assert all("outcome" not in query.lower() for query in queries)
