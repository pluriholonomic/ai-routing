import hashlib

import pytest
from pyarrow.parquet import ParquetFile

from orcap.study_registry import (
    validate_assignment,
    validate_manifest,
    write_assignments,
    write_manifest,
)

SEED_COMMITMENT = hashlib.sha256(b"not-a-live-seed").hexdigest()


def _manifest():
    return {
        "manifest_id": "routing-rct-2026-07-11-v1",
        "study_id": "routing-rct-2026-07-11",
        "registered_at": "2026-07-10T00:00:00Z",
        "planned_start_at": "2026-07-11T00:00:00Z",
        "planned_end_at": "2026-07-12T00:00:00Z",
        "randomization_unit": "model_epoch",
        "randomization_seed_commitment": SEED_COMMITMENT,
        "baseline_arm": "inverse_square_price",
        "arms": [
            {
                "name": "inverse_square_price",
                "policy": "inverse_square_price",
                "assignment_probability": 0.5,
            },
            {
                "name": "capacity_certified",
                "policy": "capacity_certified",
                "assignment_probability": 0.5,
            },
        ],
        "primary_outcomes": ["attempt_success_rate", "mean_cost_usd"],
        "negative_control_outcome": "mean_latency_ms",
        "min_clusters_per_arm": 20,
        "min_attempts_per_arm": 100,
        "stopping_rule": "Stop after both arms have their pre-registered minimum coverage.",
        "metadata": {"workload_class": "short_chat"},
    }


def _assignment():
    return {
        "assignment_id": "routing-rct-2026-07-11-a000",
        "manifest_id": "routing-rct-2026-07-11-v1",
        "study_id": "routing-rct-2026-07-11",
        "model_id": "meta-llama/llama-3.3-70b-instruct",
        "epoch_start": "2026-07-11T00:00:00Z",
        "epoch_end": "2026-07-11T00:15:00Z",
        "assigned_at": "2026-07-10T23:59:00Z",
        "treatment_arm": "capacity_certified",
        "randomization_stratum": "short-chat-us",
        "assignment_probability": 0.5,
        "metadata": {"randomization_block": "b1"},
    }


def test_study_manifest_and_assignment_are_payload_free_and_immutable(tmp_path):
    manifest = validate_manifest(_manifest())
    assignment = validate_assignment(_assignment())
    assert manifest["payload_retained"] is False
    assert assignment["payload_retained"] is False
    assert assignment["model_id"] == "meta-llama/llama-3.3-70b-instruct"

    manifest_path = write_manifest(_manifest(), curated_dir=tmp_path)
    assignment_path = write_assignments([_assignment()], curated_dir=tmp_path)
    manifest_row = ParquetFile(manifest_path).read().to_pylist()[0]
    assignment_row = ParquetFile(assignment_path).read().to_pylist()[0]
    assert manifest_row["baseline_arm"] == "inverse_square_price"
    assert assignment_row["treatment_arm"] == "capacity_certified"
    with pytest.raises(ValueError, match="immutable"):
        write_manifest(_manifest(), curated_dir=tmp_path)
    with pytest.raises(ValueError, match="immutable"):
        write_assignments([_assignment()], curated_dir=tmp_path)


def test_study_registry_rejects_post_outcome_design_and_payloads():
    with pytest.raises(ValueError, match="registered_at"):
        validate_manifest(_manifest() | {"registered_at": "2026-07-11T00:01:00Z"})
    with pytest.raises(ValueError, match="assigned_at"):
        validate_assignment(_assignment() | {"assigned_at": "2026-07-11T00:01:00Z"})
    with pytest.raises(ValueError, match="forbidden"):
        validate_manifest(_manifest() | {"metadata": {"prompt": "do not retain"}})
    with pytest.raises(ValueError, match="forbidden"):
        validate_assignment(_assignment() | {"metadata": {"response": "do not retain"}})
