import pytest
from pyarrow.parquet import ParquetFile

from orcap.capacity_telemetry import (
    validate_commitment,
    validate_outcome,
    write_commitments,
    write_outcomes,
)


def _commitment():
    return {
        "commitment_id": "capacity-2026-07-10-deepinfra-a",
        "observed_at": "2026-07-10T00:00:00Z",
        "study_id": "routing-calibration-v1",
        "provider": "deepinfra",
        "model_id": "meta-llama/llama-3.3-70b-instruct",
        "epoch_start": "2026-07-10T00:00:00Z",
        "epoch_end": "2026-07-10T01:00:00Z",
        "committed_requests": 120,
        "verification_method": "provider_signed_export",
        "marginal_cost_usd_per_request": 0.001,
        "capacity_linear_cost_usd_per_request": 0.0002,
        "capacity_cost_curvature_usd_per_request_sq": 0.00001,
        "failure_domains": ["cloud:example", "region:us-east"],
        "metadata": {"capacity_class": "reserved"},
    }


def _outcome():
    return {
        "outcome_id": "outcome-2026-07-10-deepinfra-a",
        "observed_at": "2026-07-10T01:00:00Z",
        "study_id": "routing-calibration-v1",
        "provider": "deepinfra",
        "model_id": "meta-llama/llama-3.3-70b-instruct",
        "epoch_start": "2026-07-10T00:00:00Z",
        "epoch_end": "2026-07-10T01:00:00Z",
        "allocated_requests": 120,
        "served_requests": 114,
        "verification_method": "router_epoch_ledger",
        "realized_cost_usd": 0.12,
        "realized_revenue_usd": 0.18,
        "declared_value_usd_per_served_request": 0.03,
        "availability_status": "available",
        "metadata": {"workload_class": "short_chat"},
    }


def test_capacity_commitment_contract_preserves_only_capacity_metadata():
    row = validate_commitment(_commitment())
    assert row["committed_requests"] == 120.0
    assert row["payload_retained"] is False
    assert row["metadata_json"] == '{"capacity_class":"reserved"}'
    assert row["failure_domains_json"] == '["cloud:example","region:us-east"]'
    assert row["capacity_linear_cost_usd_per_request"] == 0.0002
    assert row["capacity_cost_curvature_usd_per_request_sq"] == 0.00001


def test_capacity_commitment_allows_explicit_zero_but_rejects_payloads():
    zero = validate_commitment(_commitment() | {"committed_requests": 0})
    assert zero["committed_requests"] == 0.0

    nested_payload = _commitment() | {"metadata": {"prompt": "do not retain"}}
    with pytest.raises(ValueError, match="forbidden"):
        validate_commitment(nested_payload)


def test_capacity_commitment_rejects_missing_and_negative_capacity():
    with pytest.raises(ValueError, match="model_id"):
        validate_commitment(_commitment() | {"model_id": ""})
    with pytest.raises(ValueError, match="non-negative"):
        validate_commitment(_commitment() | {"committed_requests": -1})
    with pytest.raises(ValueError, match="curvature"):
        validate_commitment(_commitment() | {"capacity_cost_curvature_usd_per_request_sq": 0})


def test_capacity_commitment_write_uses_immutable_commitment_id(tmp_path):
    path = write_commitments([_commitment()], curated_dir=tmp_path)
    assert path is not None
    row = ParquetFile(path).read().to_pylist()[0]
    assert row["commitment_id"] == "capacity-2026-07-10-deepinfra-a"
    assert row["payload_retained"] is False

    with pytest.raises(ValueError, match="duplicate"):
        write_commitments([_commitment(), _commitment()], curated_dir=tmp_path)


def test_capacity_outcome_contract_records_aggregate_delivery_without_payload():
    row = validate_outcome(_outcome())
    assert row["allocated_requests"] == 120.0
    assert row["served_requests"] == 114.0
    assert row["shortfall_requests"] == 6.0
    assert row["payload_retained"] is False
    assert row["declared_value_usd_per_served_request"] == 0.03


def test_capacity_outcome_rejects_impossible_counts_and_payloads():
    with pytest.raises(ValueError, match="cannot exceed"):
        validate_outcome(_outcome() | {"served_requests": 121})
    with pytest.raises(ValueError, match="forbidden"):
        validate_outcome(_outcome() | {"metadata": {"messages": ["do not persist"]}})
    with pytest.raises(ValueError, match="outage_event_id"):
        validate_outcome(_outcome() | {"availability_status": "unavailable"})
    with pytest.raises(ValueError, match="declared_value"):
        validate_outcome(_outcome() | {"declared_value_usd_per_served_request": -0.01})


def test_capacity_outcome_records_aggregate_joint_outage_identifier_without_payload():
    row = validate_outcome(
        _outcome()
        | {
            "availability_status": "unavailable",
            "outage_event_id": "outage-2026-07-10-us-east-a",
        }
    )
    assert row["availability_status"] == "unavailable"
    assert row["outage_event_id"] == "outage-2026-07-10-us-east-a"


def test_capacity_outcome_write_uses_immutable_outcome_id(tmp_path):
    path = write_outcomes([_outcome()], curated_dir=tmp_path)
    assert path is not None
    row = ParquetFile(path).read().to_pylist()[0]
    assert row["outcome_id"] == "outcome-2026-07-10-deepinfra-a"
    assert row["shortfall_requests"] == 6.0
    with pytest.raises(ValueError, match="duplicate"):
        write_outcomes([_outcome(), _outcome()], curated_dir=tmp_path)
