import pytest
from pyarrow.parquet import ParquetFile

from orcap.router_policy import normalize_policy_document, write_policy_snapshot
from orcap.router_registry import registry


def _document():
    return {
        "router": "cloudflare_ai_gateway",
        "config_id": "study-router-v1",
        "observed_at": "2026-07-10T00:00:00Z",
        "policies": [
            {
                "model_id": "model-a",
                "policy_type": "ordered_failover",
                "providers": [
                    {"name": "provider-a", "order": 1},
                    {"name": "provider-b", "order": 2},
                ],
            }
        ],
    }


def test_registry_covers_public_and_configured_routers():
    version, routers = registry()
    assert version.startswith("v1-")
    assert set(routers) == {
        "openrouter",
        "huggingface_inference_providers",
        "cloudflare_ai_gateway",
        "portkey",
        "litellm",
    }


def test_policy_snapshot_is_redacted_and_writable(tmp_path):
    rows = normalize_policy_document(_document())
    assert [row["provider_name"] for row in rows] == ["provider-a", "provider-b"]
    path = write_policy_snapshot(
        _document(), run_ts="20260710T000000Z", dt="2026-07-10", curated_dir=tmp_path
    )
    stored = ParquetFile(path).read().to_pylist()
    assert stored[0]["payload_retained"] is False
    assert stored[0]["router"] == "cloudflare_ai_gateway"


def test_policy_snapshot_rejects_credentials_or_payloads():
    document = _document()
    document["policies"][0]["metadata"] = {"api_key": "do-not-store"}
    with pytest.raises(ValueError, match="sensitive"):
        normalize_policy_document(document)
