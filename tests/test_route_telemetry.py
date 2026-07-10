import pytest
from pyarrow.parquet import ParquetFile

from orcap.route_telemetry import validate_attempt, write_attempts


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
    row = validate_attempt(_attempt())
    assert row["selected_provider"] == "deepinfra"
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
