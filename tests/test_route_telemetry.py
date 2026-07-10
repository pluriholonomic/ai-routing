import pytest
from pyarrow.parquet import ParquetFile

from orcap.route_telemetry import normalize_export, validate_attempt, write_attempts


def _attempt():
    return {
        "event_id": "generation-123:0",
        "observed_at": "2026-07-10T00:00:00Z",
        "router": "openrouter",
        "source": "openrouter_generation",
        "study_id": "routing-calibration-v1",
        "request_ref": "salted-hash",
        "model_id": "z-ai/glm-5.2",
        "selected_provider": "deepinfra",
        "attempt_index": 0,
        "outcome": "succeeded",
        "input_tokens": 12,
        "output_tokens": 4,
        "cost_usd": 0.00001,
        "latency_ms": 123.0,
        "metadata": {"scenario": "short_chat"},
    }


def test_route_telemetry_contract_preserves_route_metadata_not_payload():
    row = validate_attempt(_attempt() | {"reliability_audit_assignment_id": "audit-a001"})
    assert row["selected_provider"] == "deepinfra"
    assert row["reliability_audit_assignment_id"] == "audit-a001"
    assert row["payload_retained"] is False
    assert row["metadata_json"] == '{"scenario":"short_chat"}'


def test_route_telemetry_contract_rejects_prompt_payloads():
    event = _attempt() | {"messages": [{"role": "user", "content": "sensitive"}]}
    with pytest.raises(ValueError, match="payload"):
        validate_attempt(event)

    nested = _attempt() | {"metadata": {"prompt": "also sensitive"}}
    with pytest.raises(ValueError, match="payload"):
        validate_attempt(nested)


def test_route_telemetry_write_uses_immutable_source_event_key(tmp_path):
    path = write_attempts(
        [_attempt()], run_ts="20260710T000000Z", dt="2026-07-10", curated_dir=tmp_path
    )
    assert path is not None
    row = ParquetFile(path).read().to_pylist()[0]
    assert row["event_id"] == "generation-123:0"
    assert row["payload_retained"] is False


def test_native_openrouter_export_maps_only_redacted_route_fields():
    records = [
        {
            "id": "gen-abc",
            "created_at": "2026-07-10T00:00:00Z",
            "model": "z-ai/glm-5.2",
            "provider_name": "deepinfra",
            "total_cost": 0.0001,
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            "status_code": 200,
            "metadata": {"scenario": "short_chat"},
        }
    ]
    normalized = normalize_export(
        records, export_format="openrouter-generation", study_id="routing-v1"
    )
    row = validate_attempt(normalized[0])
    assert row["source"] == "openrouter_generation"
    assert row["selected_provider"] == "deepinfra"
    assert row["metadata_json"] == '{"scenario":"short_chat","status_code":200}'


def test_native_export_rejects_payload_before_persistence():
    with pytest.raises(ValueError, match="redacted"):
        normalize_export(
            [{"id": "gen", "messages": [{"content": "do not ingest"}]}],
            export_format="openrouter-generation",
            study_id="routing-v1",
        )
