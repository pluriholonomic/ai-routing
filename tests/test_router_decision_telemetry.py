import pytest
from pyarrow.parquet import ParquetFile

from orcap.router_decision_telemetry import (
    validate_decision_event,
    validate_flow_aggregate,
    write_decision_events,
    write_flow_aggregates,
)


def _decision(**overrides):
    row = {
        "event_id": "decision-001",
        "study_id": "preselection-v1",
        "router": "openrouter",
        "arrival_at": "2026-07-12T00:00:00Z",
        "route_committed_at": "2026-07-12T00:00:00.200000Z",
        "candidate_set_version": "candidates-abc",
        "selected_endpoint": "deepinfra:model-a",
        "retry_outcome": "succeeded",
        "provider_signal_at": "2026-07-12T00:00:00.050000Z",
        "quote_or_capacity_action_at": "2026-07-12T00:00:00.100000Z",
        "experiment_arm": "provider_visible",
        "assignment_id": "assignment-001",
    }
    return row | overrides


def _aggregate(**overrides):
    row = {
        "aggregate_id": "aggregate-001",
        "study_id": "aggregate-v1",
        "router": "openrouter",
        "model_id": "model-a",
        "endpoint": "deepinfra:model-a",
        "candidate_set_version": "candidates-abc",
        "interval_start": "2026-07-12T00:00:00Z",
        "interval_end": "2026-07-12T00:05:00Z",
        "attempted_routes": 20,
        "selected_routes": 10,
        "succeeded_routes": 9,
        "fallback_routes": 2,
    }
    return row | overrides


def test_decision_contract_preserves_ordering_fields_without_payload(tmp_path):
    row = validate_decision_event(_decision())
    assert row["payload_retained"] is False
    assert row["provider_signal_at"].endswith("Z")

    path = write_decision_events([_decision()], curated_dir=tmp_path)
    assert path is not None
    persisted = ParquetFile(path).read().to_pylist()[0]
    assert persisted["candidate_set_version"] == "candidates-abc"


def test_decision_contract_rejects_payload_and_invalid_commit_order():
    with pytest.raises(ValueError, match="forbidden"):
        validate_decision_event(_decision(messages=[{"content": "private"}]))
    with pytest.raises(ValueError, match="must not precede"):
        validate_decision_event(_decision(route_committed_at="2026-07-11T23:59:59Z"))
    with pytest.raises(ValueError, match="requires assignment_id"):
        validate_decision_event(_decision(assignment_id=None))


def test_flow_aggregate_contract_checks_counts_and_writes(tmp_path):
    row = validate_flow_aggregate(_aggregate())
    assert row["payload_retained"] is False
    path = write_flow_aggregates([_aggregate()], curated_dir=tmp_path)
    assert path is not None
    assert ParquetFile(path).read().to_pylist()[0]["selected_routes"] == 10
    with pytest.raises(ValueError, match="internally consistent"):
        validate_flow_aggregate(_aggregate(selected_routes=21))
