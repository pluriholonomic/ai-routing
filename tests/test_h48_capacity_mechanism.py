import duckdb
import pandas as pd
import pytest

from orcap.analysis import h48_capacity_mechanism as h48
from orcap.analysis.h48_capacity_mechanism import allocation_calibration, enforcement_gate
from orcap.capacity_telemetry import write_commitments
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
    unmatched = {
        "matched_attempts": 0,
        "served_observed": 0,
        "realized_cost_observed": 0,
    }
    matched = {
        "matched_attempts": 2,
        "served_observed": 1,
        "realized_cost_observed": 2,
    }
    assert (
        enforcement_gate(attempts, commitments, unmatched)["status"]
        == "unmatched_owned_telemetry"
    )
    gate = enforcement_gate(attempts, commitments, matched)
    assert gate["status"] == "partial_owned_telemetry"
    assert gate["identified_in_matched_controlled_study"]["succeeded_attempts"] == 1


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
