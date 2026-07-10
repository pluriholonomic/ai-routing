from pathlib import Path

from orcap.capture_hf_router import policy_simulation_rows, provider_endpoint_rows
from orcap.observability import registry, source_spec


def _body():
    return {
        "object": "list",
        "data": [
            {
                "id": "org/model",
                "created": 1,
                "owned_by": "org",
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "providers": [
                    {
                        "provider": "slow-expensive",
                        "status": "live",
                        "context_length": 100_000,
                        "pricing": {"input": 2.0, "output": 4.0},
                        "supports_tools": True,
                        "supports_structured_output": True,
                        "first_token_latency_ms": 900,
                        "throughput": 10,
                    },
                    {
                        "provider": "fast-cheap",
                        "status": "live",
                        "context_length": 100_000,
                        "pricing": {"input": 1.0, "output": 2.0},
                        "supports_tools": True,
                        "supports_structured_output": True,
                        "first_token_latency_ms": 300,
                        "throughput": 100,
                    },
                ],
            }
        ],
    }


def test_hf_provider_rows_keep_listing_metadata_not_usage():
    rows = provider_endpoint_rows(_body(), "20260710T000000Z", "2026-07-10")
    assert len(rows) == 2
    assert rows[0]["price_input_usd_per_mtok"] == 2.0
    assert rows[1]["throughput_tps"] == 100.0
    assert "not requests" in rows[0]["metric_definition"]


def test_hf_policy_surface_uses_public_cheapest_and_reported_fastest():
    endpoints = provider_endpoint_rows(_body(), "20260710T000000Z", "2026-07-10")
    rows = policy_simulation_rows(endpoints, "20260710T000000Z", "2026-07-10")
    short = [row for row in rows if row["scenario"] == "short_chat"]
    cheapest = {
        row["provider_name"]: row
        for row in short
        if row["policy"] == "hf_cheapest_public_quote"
    }
    fastest = {
        row["provider_name"]: row
        for row in short
        if row["policy"] == "hf_fastest_reported_throughput"
    }
    assert cheapest["fast-cheap"]["simulated_route_share"] == 1.0
    assert cheapest["slow-expensive"]["simulated_route_share"] == 0.0
    assert fastest["fast-cheap"]["simulated_route_share"] == 1.0
    assert fastest["slow-expensive"]["simulated_route_share"] == 0.0


def test_hf_router_is_required_in_its_own_source_profile():
    spec = source_spec("huggingface_inference_providers")
    assert spec.required
    assert spec.min_rows == 100

    _, profiles = registry()
    assert profiles["hf_router"] == ["huggingface_inference_providers"]
    assert "openrouter_api" in profiles["router_comparator"]


def test_hf_router_workflow_validates_its_independent_profile():
    workflow = (Path(__file__).parents[1] / ".github/workflows/hf-router.yml").read_text()
    assert "orcap quality --profile hf_router" in workflow
    assert "orcap quality --profile router_comparator" not in workflow
