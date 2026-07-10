import duckdb
import pandas as pd
import pytest

from orcap.analysis import h48_capacity_mechanism as h48
from orcap.analysis.h48_capacity_mechanism import (
    allocation_calibration,
    capacity_procurement_gate,
    enforcement_gate,
    welfare_gate,
)
from orcap.capacity_telemetry import write_commitments, write_outcomes
from orcap.route_telemetry import write_attempts


def test_h48_calibrates_theoretical_elasticity_from_public_allocation_share():
    panel = allocation_calibration(
        pd.DataFrame(
            [
                {
                    "run_ts": "20260710T000000Z",
                    "model_id": "model-a",
                    "scenario": "short",
                    "provider_name": "provider-a",
                    "simulated_route_share": 0.8,
                    "expected_quote_usd": 0.01,
                }
            ]
        )
    )
    assert panel.iloc[0]["mechanism_eta"] == 2.0
    assert panel.iloc[0]["predicted_own_price_share_elasticity"] == pytest.approx(-0.4)


def test_h48_capacity_gate_requires_matched_attempt_and_commitment_telemetry():
    attempts = {"attempts": 3}
    commitments = {"commitments": 1}
    outcomes = {"outcomes": 1}
    unmatched_outcomes = {
        "matched_outcomes": 0,
        "allocated_requests": 0.0,
        "served_requests": 0.0,
        "shortfall_requests": 0.0,
        "realized_cost_observed": 0,
        "realized_revenue_observed": 0,
    }
    unmatched_attempts = {
        "matched_attempts": 0,
        "served_observed": 0,
        "realized_cost_observed": 0,
    }
    matched_outcomes = {
        "matched_outcomes": 1,
        "allocated_requests": 2.0,
        "served_requests": 1.0,
        "shortfall_requests": 1.0,
        "realized_cost_observed": 2,
        "realized_revenue_observed": 1,
    }
    matched_attempts = {
        "matched_attempts": 2,
        "served_observed": 1,
        "realized_cost_observed": 2,
    }
    assert (
        enforcement_gate(
            attempts, commitments, outcomes, unmatched_outcomes, unmatched_attempts
        )["status"]
        == "unmatched_owned_telemetry"
    )
    gate = enforcement_gate(
        attempts, commitments, outcomes, matched_outcomes, matched_attempts
    )
    assert gate["status"] == "partial_owned_telemetry"
    assert gate["identified_in_matched_controlled_study"]["succeeded_attempts"] == 1
    assert gate["identified_in_matched_controlled_study"]["shortfall_requests"] == 1.0


def test_h48_capacity_procurement_gate_keeps_declared_costs_distinct_from_verification():
    unobserved = capacity_procurement_gate(
        {
            "commitments": 1,
            "capacity_linear_cost_observed": 0,
            "capacity_cost_curvature_observed": 0,
        }
    )
    assert unobserved["status"] == "cost_type_unobserved"
    partial = capacity_procurement_gate(
        {
            "commitments": 100,
            "capacity_linear_cost_observed": 100,
            "capacity_cost_curvature_observed": 100,
        }
    )
    assert partial["status"] == "declared_cost_type_coverage"
    assert "do not verify private cost" in partial["claim_boundary"]
    curve = capacity_procurement_gate(
        {
            "commitments": 100,
            "capacity_linear_cost_observed": 0,
            "capacity_cost_curvature_observed": 0,
            "capacity_cost_curve_observed": 100,
        }
    )
    assert curve["status"] == "declared_cost_curve_coverage"
    assert "VCG counterfactual" in curve["claim_boundary"]


def test_h48_welfare_gate_requires_registered_value_and_cost_primitives():
    commitments = {"commitments": 1}
    missing_value = welfare_gate(
        commitments,
        {"outcomes": 1, "declared_value_observed": 0, "realized_cost_observed": 1},
    )
    assert missing_value["status"] == "value_proxy_unobserved"
    partial = welfare_gate(
        commitments,
        {"outcomes": 1, "declared_value_observed": 1, "realized_cost_observed": 1},
    )
    assert partial["status"] == "partial_controlled_welfare_primitives"
    assert "not consumer surplus" in partial["claim_boundary"]


def test_h48_matches_owned_attempts_to_same_provider_model_study_and_epoch(tmp_path, monkeypatch):
    commitment = {
        "commitment_id": "capacity-a",
        "observed_at": "2026-07-10T00:00:00Z",
        "study_id": "study-a",
        "provider": "deepinfra",
        "model_id": "model-a",
        "epoch_start": "2026-07-10T00:00:00Z",
        "epoch_end": "2026-07-10T01:00:00Z",
        "committed_requests": 10,
        "verification_method": "signed_export",
    }
    attempts = [
        {
            "event_id": "a",
            "observed_at": "2026-07-10T00:15:00Z",
            "router": "openrouter",
            "source": "openrouter_generation",
            "study_id": "study-a",
            "model_id": "model-a",
            "selected_provider": "deepinfra",
            "outcome": "succeeded",
            "cost_usd": 0.01,
        },
        {
            "event_id": "b",
            "observed_at": "2026-07-10T00:15:00Z",
            "router": "openrouter",
            "source": "openrouter_generation",
            "study_id": "study-a",
            "model_id": "model-a",
            "selected_provider": "deepinfra",
            "outcome": "failed",
        },
        {
            "event_id": "c",
            "observed_at": "2026-07-10T01:00:00Z",
            "router": "openrouter",
            "source": "openrouter_generation",
            "study_id": "study-a",
            "model_id": "model-a",
            "selected_provider": "deepinfra",
            "outcome": "succeeded",
        },
    ]
    write_commitments([commitment], curated_dir=tmp_path)
    write_outcomes(
        [
            {
                "outcome_id": "outcome-a",
                "observed_at": "2026-07-10T01:00:00Z",
                "study_id": "study-a",
                "provider": "deepinfra",
                "model_id": "model-a",
                "epoch_start": "2026-07-10T00:00:00Z",
                "epoch_end": "2026-07-10T01:00:00Z",
                "allocated_requests": 2,
                "served_requests": 1,
                "realized_cost_usd": 0.01,
                "realized_revenue_usd": 0.03,
            }
        ],
        curated_dir=tmp_path,
    )
    write_attempts(attempts, curated_dir=tmp_path)

    def table_glob(name):
        return str(tmp_path / name / "*" / "*.parquet")

    connection = duckdb.connect()
    monkeypatch.setattr(h48.data, "table_glob", table_glob)
    monkeypatch.setattr(h48.data, "q", connection.sql)

    coverage = h48._matched_attempt_commitment_coverage()
    assert coverage["matched_attempts"] == 2
    assert coverage["served_observed"] == 1
    assert coverage["realized_cost_observed"] == 1

    outcome_coverage = h48._matched_commitment_outcome_coverage()
    assert outcome_coverage["matched_outcomes"] == 1
    assert outcome_coverage["allocated_requests"] == 2.0
    assert outcome_coverage["shortfall_requests"] == 1.0

    triple_coverage = h48._triple_matched_attempt_coverage()
    assert triple_coverage["matched_attempts"] == 2
    assert triple_coverage["served_observed"] == 1


def test_h48_does_not_cross_match_attempts_and_outcomes_across_epochs(tmp_path, monkeypatch):
    commitments = [
        {
            "commitment_id": "capacity-a",
            "observed_at": "2026-07-10T00:00:00Z",
            "study_id": "study-a",
            "provider": "deepinfra",
            "model_id": "model-a",
            "epoch_start": "2026-07-10T00:00:00Z",
            "epoch_end": "2026-07-10T01:00:00Z",
            "committed_requests": 10,
        },
        {
            "commitment_id": "capacity-b",
            "observed_at": "2026-07-10T01:00:00Z",
            "study_id": "study-a",
            "provider": "deepinfra",
            "model_id": "model-a",
            "epoch_start": "2026-07-10T01:00:00Z",
            "epoch_end": "2026-07-10T02:00:00Z",
            "committed_requests": 10,
        },
    ]
    write_commitments(commitments, curated_dir=tmp_path)
    write_outcomes(
        [
            {
                "outcome_id": "outcome-a",
                "observed_at": "2026-07-10T01:00:00Z",
                "study_id": "study-a",
                "provider": "deepinfra",
                "model_id": "model-a",
                "epoch_start": "2026-07-10T00:00:00Z",
                "epoch_end": "2026-07-10T01:00:00Z",
                "allocated_requests": 1,
                "served_requests": 1,
            }
        ],
        curated_dir=tmp_path,
    )
    write_attempts(
        [
            {
                "event_id": "attempt-b",
                "observed_at": "2026-07-10T01:15:00Z",
                "router": "openrouter",
                "source": "openrouter_generation",
                "study_id": "study-a",
                "model_id": "model-a",
                "selected_provider": "deepinfra",
                "outcome": "succeeded",
            }
        ],
        curated_dir=tmp_path,
    )

    def table_glob(name):
        return str(tmp_path / name / "*" / "*.parquet")

    connection = duckdb.connect()
    monkeypatch.setattr(h48.data, "table_glob", table_glob)
    monkeypatch.setattr(h48.data, "q", connection.sql)

    assert h48._matched_attempt_commitment_coverage()["matched_attempts"] == 1
    assert h48._matched_commitment_outcome_coverage()["matched_outcomes"] == 1
    assert h48._triple_matched_attempt_coverage()["matched_attempts"] == 0
