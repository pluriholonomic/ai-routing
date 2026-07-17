from pathlib import Path

import pytest

from orcap.capture_router_catalogs import (
    PUBLIC_ROUTER_QUOTE_SCHEMA,
    glama_quote_rows,
    nemo_quote_rows,
    requesty_quote_rows,
)
from orcap.observability import registry, source_spec

RUN_TS = "20260716T120000Z"
DT = "2026-07-16"


def test_requesty_prices_are_normalized_from_per_token_to_per_million():
    body = {
        "data": [
            {
                "id": "deepinfra/deepseek-chat-v3",
                "api": "chat",
                "input_price": 2.8e-7,
                "cached_price": 3e-8,
                "output_price": 1.1e-6,
                "context_window": 196_608,
                "max_output_tokens": 16_384,
                "supports_caching": True,
                "supports_vision": False,
                "supports_reasoning": True,
                "supports_tool_calling": True,
                "supports_output_json_schema": True,
            }
        ]
    }
    row = requesty_quote_rows(body, RUN_TS, DT)[0]
    assert row["router"] == "requesty"
    assert row["provider_name"] == "deepinfra"
    assert row["source_model_key"] == "deepseek-chat-v3"
    assert row["price_input_usd_per_mtok"] == 0.28
    assert row["price_output_usd_per_mtok"] == 1.1
    assert row["price_cache_read_usd_per_mtok"] == 0.03
    assert row["supports_tools"] is True


def test_nemo_uses_public_model_id_as_join_key_and_keeps_upstream_deployment_id():
    body = {
        "data": [
            {
                "model_id": "codestral-2501",
                "params": {"model": "azure_ai/codestral-2501"},
                "provider": "azure_ai",
                "mode": "chat",
                "model_info": {
                    "input_cost_per_token": 2e-7,
                    "output_cost_per_token": 6e-7,
                    "max_input_tokens": 128_000,
                    "max_tokens": 16_384,
                    "supports_vision": False,
                    "supports_function_calling": True,
                },
            }
        ]
    }
    row = nemo_quote_rows(body, RUN_TS, DT)[0]
    assert row["source_model_id"] == "azure_ai/codestral-2501"
    assert row["source_model_key"] == "codestral-2501"
    assert row["provider_name"] == "azure_ai"
    assert row["price_input_usd_per_mtok"] == pytest.approx(0.2)
    assert row["price_output_usd_per_mtok"] == pytest.approx(0.6)
    assert row["supports_tools"] is True


def test_glama_public_page_exposes_provider_menu_prices_and_health():
    page = """
    <html><body><table><tbody>
      <tr><th>Model ID</th><td><code>deepseek-chat-v3</code></td></tr>
      <tr><th>Creator</th><td>deepseek</td></tr>
      <tr><th>Token limits</th><td>
        <section><h4>Input token limit</h4><p>64,000</p></section>
        <section><h4>Output token limit</h4><p>8,000</p></section>
      </td></tr>
      <tr><th>Capabilities</th><td><p>Caching</p><p>Function calling</p></td></tr>
      <tr><th>Providers</th><td><table><tbody>
        <tr><th>Name</th><th colspan="4">USD / M Tokens</th></tr>
        <tr><th>Input</th><th>Output</th><th>Cache Read</th><th>Cache Write</th></tr>
        <tr><td><a href="/ai/gateway/providers/deepseek">deepseek</a>
          <span data-status="healthy"></span><button><span>Chat</span></button></td>
          <td>$ 0. 14</td><td>$ 0. 28</td><td>$ 0.0 14</td><td>$ 0. 14</td></tr>
        <tr><td><a href="/ai/gateway/providers/fireworks">fireworks</a>
          <span data-status="unknown"></span><button><span>Chat</span></button></td>
          <td>$ 0. 9</td><td>$ 0. 9</td><td>$ –</td><td>$ –</td></tr>
      </tbody></table></td></tr>
    </tbody></table></body></html>
    """
    rows = glama_quote_rows(
        page,
        "deepseek-chat-v3",
        RUN_TS,
        DT,
        "https://glama.ai/gateway/models/deepseek-chat-v3",
    )
    assert len(rows) == 2
    assert rows[0]["model_creator"] == "deepseek"
    assert rows[0]["status"] == "healthy"
    assert rows[0]["price_input_usd_per_mtok"] == 0.14
    assert rows[0]["price_cache_read_usd_per_mtok"] == 0.014
    assert rows[0]["context_length"] == 64_000
    assert rows[0]["supports_tools"] is True
    assert rows[1]["price_cache_read_usd_per_mtok"] is None


def test_public_quote_schema_is_stable_and_explicit():
    assert PUBLIC_ROUTER_QUOTE_SCHEMA.field("price_input_usd_per_mtok").type.bit_width == 64
    assert PUBLIC_ROUTER_QUOTE_SCHEMA.field("context_length").type.bit_width == 64


def test_router_catalog_sources_and_remote_workflow_are_registered():
    _, profiles = registry()
    assert profiles["router_catalogs"] == [
        "glama_public_catalog",
        "requesty_public_catalog",
        "nemo_public_catalog",
    ]
    assert source_spec("requesty_public_catalog").required
    assert source_spec("nemo_public_catalog").min_rows == 50
    workflow = (Path(__file__).parents[1] / ".github/workflows/router-catalogs.yml").read_text()
    assert "python -m orcap.capture_router_catalogs" in workflow
    assert "orcap quality --profile router_catalogs" in workflow
    assembler = (Path(__file__).parents[1] / "scripts/assemble_artifacts.sh").read_text()
    assert "router-catalogs.yml" in assembler
