"""Schema guards for the direct-provider list-price collectors."""

import json

import pandas as pd

from orcap.analysis import h13_venue_basis
from orcap.capture_direct import (
    DEEPINFRA_URL,
    TOGETHER_SERVERLESS_MODELS_URL,
    deepinfra_rows,
    together_rows,
)

TOGETHER_CHAT_TABLE = """
<table>
  <thead><tr>
    <th>Organization</th><th>Model name</th><th>API model string</th>
    <th>Context length</th><th>Input pricing (per 1M tokens)</th>
    <th>Cached input pricing (per 1M tokens)</th>
    <th>Output pricing (per 1M tokens)</th>
  </tr></thead>
  <tbody><tr>
    <td>MiniMax</td><td>MiniMax M2.7</td><td>MiniMaxAI/MiniMax-M2.7</td>
    <td>202752</td><td>$0.30</td><td>$0.06</td><td>$1.20</td>
  </tr></tbody>
</table>
"""


def test_deepinfra_rows_label_structured_api_provenance():
    rows = deepinfra_rows(
        [
            {
                "model_name": "meta-llama/Llama-3",
                "type": "chat",
                "pricing": {
                    "type": "tokens",
                    "cents_per_input_token": 0.0001,
                    "cents_per_output_token": 0.0002,
                },
            }
        ],
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["source_type"] == "structured_public_api"
    assert rows[0]["source_url"] == DEEPINFRA_URL
    assert rows[0]["quote_unit"] == "usd_per_token"


def test_together_rows_require_explicit_api_id_and_token_price_headers():
    rows = together_rows(TOGETHER_CHAT_TABLE, "20260710T000000Z", "2026-07-10")
    assert len(rows) == 1
    row = rows[0]
    assert row["model_name"] == "MiniMaxAI/MiniMax-M2.7"
    assert row["price_input_usd"] == 0.30 / 1_000_000
    assert row["price_cached_input_usd"] == 0.06 / 1_000_000
    assert row["price_output_usd"] == 1.20 / 1_000_000
    assert row["source_type"] == "published_docs_table"
    assert row["source_url"] == TOGETHER_SERVERLESS_MODELS_URL


def test_together_rows_rejects_changed_header_schema_instead_of_guessing():
    changed = TOGETHER_CHAT_TABLE.replace("API model string", "Model identifier")
    assert together_rows(changed, "20260710T000000Z", "2026-07-10") == []


def test_h13_accepts_rest_model_id_but_keeps_exact_model_identifier(monkeypatch):
    class Relation:
        def df(self):
            return pd.DataFrame(
                [
                    {
                        "dt": "2026-07-10",
                        "provider_display_name": "Together",
                        "record_json": json.dumps(
                            {
                                "model_id": "openai/gpt-oss-20b",
                                "pricing": {"prompt": "0.00000005", "completion": "0.0000002"},
                            }
                        ),
                    }
                ]
            )

    monkeypatch.setattr(h13_venue_basis.data, "q", lambda _sql: Relation())
    routed = h13_venue_basis.load_routed()
    assert routed.to_dict("records") == [
        {
            "dt": "2026-07-10",
            "provider": "together",
            "model_name": "openai/gpt-oss-20b",
            "routed_in": 0.00000005,
            "routed_out": 0.0000002,
        }
    ]
