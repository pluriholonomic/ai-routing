import pytest
from pyarrow.parquet import ParquetFile

from orcap.capacity_telemetry import validate_commitment, write_commitments


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
        "metadata": {"capacity_class": "reserved"},
    }


def test_capacity_commitment_contract_preserves_only_capacity_metadata():
    row = validate_commitment(_commitment())
    assert row["committed_requests"] == 120.0
    assert row["payload_retained"] is False
    assert row["metadata_json"] == '{"capacity_class":"reserved"}'


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


def test_capacity_commitment_write_uses_immutable_commitment_id(tmp_path):
    path = write_commitments([_commitment()], curated_dir=tmp_path)
    assert path is not None
    row = ParquetFile(path).read().to_pylist()[0]
    assert row["commitment_id"] == "capacity-2026-07-10-deepinfra-a"
    assert row["payload_retained"] is False

    with pytest.raises(ValueError, match="duplicate"):
        write_commitments([_commitment(), _commitment()], curated_dir=tmp_path)
