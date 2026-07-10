"""Schema guards for the direct-provider list-price collectors."""

import json

import pandas as pd

from orcap.analysis import h13_venue_basis
from orcap.capture_direct import (
    CEREBRAS_MODELS_URL,
    CHUTES_MODELS_URL,
    DEEPINFRA_URL,
    FIREWORKS_MODEL_PAGES,
    GROQ_MODELS_URL,
    NOVITA_PRICING_URL,
    SAMBANOVA_MODELS_URL,
    TOGETHER_SERVERLESS_MODELS_URL,
    cerebras_rows,
    chutes_rows,
    deepinfra_rows,
    direct_price_table,
    fireworks_rows,
    groq_rows,
    novita_rows,
    sambanova_rows,
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

FIREWORKS_MODEL_PAGE = """
<html><body>
  <p>model path:accounts/fireworks/models/gpt-oss-20bWelcome to the model page.</p>
  <section>Available ServerlessRun queries immediately, pay only for usage
  $0.07 / $0.04 / $0.30Per 1M Tokens (input/cached input/output)</section>
</body></html>
"""

GROQ_MODELS_TABLE = """
<table><thead><tr><th>Model ID</th><th>Price Per 1M Tokens</th></tr></thead>
<tbody><tr><td>meta-llama/llama-4-scout-17b-16e-instruct</td>
<td>$0.11 input $0.34 output</td></tr></tbody></table>
"""


def _novita_pricing_page(models):
    payload = '0:{"initialFullLLMModels":' + json.dumps(models, separators=(",", ":")) + "}"
    return "<script>self.__next_f.push(" + json.dumps([1, payload]) + ")</script>"


def test_cerebras_rows_keep_provider_api_and_first_party_canonical_ids():
    rows = cerebras_rows(
        {
            "object": "list",
            "data": [
                {
                    "id": "gpt-oss-120b",
                    "hugging_face_id": "openai/gpt-oss-120b",
                    "pricing": {"prompt": "0.00000035", "completion": "0.00000075"},
                    "deprecated": False,
                }
            ],
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["model_name"] == "openai/gpt-oss-120b"
    assert row["direct_provider_model_id"] == "gpt-oss-120b"
    assert row["model_identifier_type"] == "first_party_hugging_face_id"
    assert row["price_input_usd"] == 0.00000035
    assert row["price_output_usd"] == 0.00000075
    assert row["source_url"] == CEREBRAS_MODELS_URL


def test_cerebras_rows_reject_missing_or_non_positive_prices():
    assert cerebras_rows(
        {"data": [{"id": "m", "pricing": {"prompt": "0", "completion": "1"}}]},
        "20260710T000000Z",
        "2026-07-10",
    ) == []


def test_sambanova_rows_keep_versioned_verified_canonical_map():
    rows = sambanova_rows(
        {
            "data": [
                {
                    "id": "gpt-oss-120b",
                    "pricing": {"prompt": "0.00000022", "completion": "0.00000059"},
                }
            ]
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["model_name"] == "gpt-oss-120b"
    assert row["direct_provider_model_id"] == "gpt-oss-120b"
    assert row["canonical_model_id"] == "openai/gpt-oss-120b"
    assert row["model_identifier_type"] == "verified_router_canonical_pair_v1"
    assert row["price_input_usd"] == 0.00000022
    assert row["price_output_usd"] == 0.00000059
    assert row["source_url"] == SAMBANOVA_MODELS_URL


def test_sambanova_rows_keep_unmapped_id_without_fuzzy_crosswalk():
    rows = sambanova_rows(
        {
            "data": [
                {
                    "id": "DeepSeek-V3.1",
                    "pricing": {"prompt": "0.000003", "completion": "0.0000045"},
                }
            ]
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["canonical_model_id"] is None
    assert rows[0]["model_identifier_type"] == "provider_api_id"


def test_chutes_rows_require_provider_root_and_quantization_for_canonical_map():
    rows = chutes_rows(
        {
            "data": [
                {
                    "id": "Qwen/Qwen3.6-27B-TEE",
                    "root": "Qwen/Qwen3.6-27B-FP8",
                    "quantization": "fp8",
                    "pricing": {"prompt": 0.3, "completion": 2.0, "input_cache_read": 0.15},
                },
                {
                    "id": "Qwen/Qwen3.6-27B-TEE",
                    "root": "wrong-root",
                    "quantization": "fp8",
                    "pricing": {"prompt": 0.3, "completion": 2.0},
                },
            ]
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert len(rows) == 2
    assert rows[0]["canonical_model_id"] == "qwen/qwen3.6-27b"
    assert rows[0]["model_identifier_type"] == "verified_provider_configuration_pair_v1"
    assert rows[0]["price_input_usd"] == 0.3 / 1_000_000
    assert rows[0]["price_cached_input_usd"] == 0.15 / 1_000_000
    assert rows[0]["source_url"] == CHUTES_MODELS_URL
    assert rows[1]["canonical_model_id"] is None
    assert rows[1]["model_identifier_type"] == "provider_api_id"


def test_chutes_glm_map_requires_the_literal_fp8_root():
    rows = chutes_rows(
        {
            "data": [
                {
                    "id": "zai-org/GLM-5.1-TEE",
                    "root": "zai-org/GLM-5.1-FP8",
                    "quantization": "fp8",
                    "pricing": {"prompt": 0.98, "completion": 3.08},
                }
            ]
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["canonical_model_id"] == "z-ai/glm-5.1"


def test_direct_price_table_keeps_later_provider_provenance_columns():
    deepinfra = deepinfra_rows(
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
    cerebras = cerebras_rows(
        {
            "data": [
                {
                    "id": "gpt-oss-120b",
                    "hugging_face_id": "openai/gpt-oss-120b",
                    "pricing": {"prompt": "0.00000035", "completion": "0.00000075"},
                }
            ]
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    table = direct_price_table(deepinfra + cerebras)
    row = table.to_pylist()[1]
    assert row["direct_provider_model_id"] == "gpt-oss-120b"
    assert row["model_identifier_type"] == "first_party_hugging_face_id"


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


def test_groq_rows_require_exact_id_and_labeled_two_sided_token_price():
    rows = groq_rows(GROQ_MODELS_TABLE, "20260710T000000Z", "2026-07-10")
    assert len(rows) == 1
    assert rows[0]["model_name"] == "meta-llama/llama-4-scout-17b-16e-instruct"
    assert rows[0]["price_input_usd"] == 0.11 / 1_000_000
    assert rows[0]["price_output_usd"] == 0.34 / 1_000_000
    assert rows[0]["source_url"] == GROQ_MODELS_URL


def test_groq_rows_reject_malformed_price_cell():
    changed = GROQ_MODELS_TABLE.replace("$0.11 input $0.34 output", "starting at $0.11")
    assert groq_rows(changed, "20260710T000000Z", "2026-07-10") == []


def test_novita_rows_require_literal_active_chat_ids_and_displayed_token_prices():
    rows = novita_rows(
        _novita_pricing_page(
            [
                {
                    "type": "Chat",
                    "id": "openai/gpt-oss-20b",
                    "status": 1,
                    "endpoints": ["chat/completions"],
                    "input_token_price_per_m_toString": "0.04",
                    "output_token_price_per_m_toString": "0.15",
                },
                {
                    "type": "Chat",
                    "id": "not-active",
                    "status": 0,
                    "endpoints": ["chat/completions"],
                    "input_token_price_per_m_toString": "0.01",
                    "output_token_price_per_m_toString": "0.02",
                },
            ]
        ),
        "20260710T000000Z",
        "2026-07-10",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["model_name"] == "openai/gpt-oss-20b"
    assert row["direct_provider_model_id"] == "openai/gpt-oss-20b"
    assert row["price_input_usd"] == 0.04 / 1_000_000
    assert row["price_output_usd"] == 0.15 / 1_000_000
    assert row["source_type"] == "published_ssr_pricing_catalog"
    assert row["source_url"] == NOVITA_PRICING_URL


def test_novita_rows_reject_missing_flight_catalog_or_unlabeled_prices():
    assert novita_rows("<html></html>", "20260710T000000Z", "2026-07-10") == []
    page = _novita_pricing_page(
        [
            {
                "type": "Chat",
                "id": "openai/gpt-oss-20b",
                "status": 1,
                "endpoints": ["chat/completions"],
                "input_token_price_per_m_toString": "starting at 0.04",
                "output_token_price_per_m_toString": "0.15",
            }
        ]
    )
    assert novita_rows(page, "20260710T000000Z", "2026-07-10") == []


def test_fireworks_rows_require_literal_provider_id_and_labeled_price_block():
    model_id = "accounts/fireworks/models/gpt-oss-20b"
    rows = fireworks_rows({model_id: FIREWORKS_MODEL_PAGE}, "20260710T000000Z", "2026-07-10")
    assert len(rows) == 1
    row = rows[0]
    assert row["model_name"] == model_id
    assert row["price_input_usd"] == 0.07 / 1_000_000
    assert row["price_cached_input_usd"] == 0.04 / 1_000_000
    assert row["price_output_usd"] == 0.30 / 1_000_000
    assert row["source_type"] == "published_model_page"
    assert row["source_url"] == FIREWORKS_MODEL_PAGES[model_id]


def test_fireworks_rows_reject_pages_without_exact_provider_identity():
    model_id = "accounts/fireworks/models/gpt-oss-20b"
    changed = FIREWORKS_MODEL_PAGE.replace(model_id, "accounts/fireworks/models/not-gpt-oss")
    assert fireworks_rows({model_id: changed}, "20260710T000000Z", "2026-07-10") == []


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


def test_h13_maps_cerebras_to_first_party_canonical_model_key(monkeypatch):
    class Relation:
        def df(self):
            return pd.DataFrame(
                [
                    {
                        "dt": "2026-07-10",
                        "provider_display_name": "Cerebras",
                        "record_json": json.dumps(
                            {
                                "model_id": "openai/gpt-oss-120b",
                                "pricing": {"prompt": "0.00000035", "completion": "0.00000075"},
                            }
                        ),
                    }
                ]
            )

    monkeypatch.setattr(h13_venue_basis.data, "q", lambda _sql: Relation())
    routed = h13_venue_basis.load_routed()
    assert routed.loc[0, "provider"] == "cerebras"
    assert routed.loc[0, "model_name"] == "openai/gpt-oss-120b"


def test_h13_maps_sambanova_to_versioned_canonical_pair_key(monkeypatch):
    class Relation:
        def df(self):
            return pd.DataFrame(
                [
                    {
                        "dt": "2026-07-10",
                        "provider_display_name": "SambaNova",
                        "record_json": json.dumps(
                            {
                                "model_id": "openai/gpt-oss-120b",
                                "pricing": {"prompt": "0.00000014", "completion": "0.00000095"},
                            }
                        ),
                    }
                ]
            )

    monkeypatch.setattr(h13_venue_basis.data, "q", lambda _sql: Relation())
    routed = h13_venue_basis.load_routed()
    assert routed.loc[0, "provider"] == "sambanova"
    assert routed.loc[0, "model_name"] == "openai/gpt-oss-120b"


def test_h13_maps_fireworks_only_by_exact_provider_model_id(monkeypatch):
    class Relation:
        def df(self):
            return pd.DataFrame(
                [
                    {
                        "dt": "2026-07-10",
                        "provider_display_name": "Fireworks",
                        "record_json": json.dumps(
                            {
                                "provider_model_id": "accounts/fireworks/models/gpt-oss-20b",
                                "pricing": {"prompt": "0.00000007", "completion": "0.0000003"},
                            }
                        ),
                    }
                ]
            )

    monkeypatch.setattr(h13_venue_basis.data, "q", lambda _sql: Relation())
    routed = h13_venue_basis.load_routed()
    assert routed.loc[0, "provider"] == "fireworks"
    assert routed.loc[0, "model_name"] == "accounts/fireworks/models/gpt-oss-20b"


def test_h13_maps_novita_by_the_literal_direct_provider_model_id(monkeypatch):
    class Relation:
        def df(self):
            return pd.DataFrame(
                [
                    {
                        "dt": "2026-07-10",
                        "provider_display_name": "Novita",
                        "record_json": json.dumps(
                            {
                                "model_id": "openai/gpt-oss-20b",
                                "pricing": {"prompt": "0.00000004", "completion": "0.00000015"},
                            }
                        ),
                    }
                ]
            )

    monkeypatch.setattr(h13_venue_basis.data, "q", lambda _sql: Relation())
    routed = h13_venue_basis.load_routed()
    assert routed.loc[0, "provider"] == "novita"
    assert routed.loc[0, "model_name"] == "openai/gpt-oss-20b"


def test_h13_api_snapshot_preserves_exact_novita_provider_and_model_id(monkeypatch):
    class Relation:
        def df(self):
            return pd.DataFrame(
                [
                    {
                        "dt": "2026-07-10",
                        "run_ts": "20260710T065500Z",
                        "provider_name": "Novita",
                        "model_id": "openai/gpt-oss-20b",
                        "price_prompt": 0.00000004,
                        "price_completion": 0.00000015,
                    }
                ]
            )

    monkeypatch.setattr(h13_venue_basis.data, "q", lambda _sql: Relation())
    routed = h13_venue_basis._load_api_routed()
    assert routed.to_dict("records") == [
        {
            "dt": "2026-07-10",
            "run_ts": "20260710T065500Z",
            "provider": "novita",
            "model_name": "openai/gpt-oss-20b",
            "routed_in": 0.00000004,
            "routed_out": 0.00000015,
            "routed_source": "api_endpoint_snapshot",
        }
    ]


def test_h13_selects_nearest_quote_and_rejects_stale_same_day_quote():
    direct = pd.DataFrame(
        [
            {
                "dt": "2026-07-10",
                "run_ts": "20260710T120000Z",
                "provider": "novita",
                "model_name": "openai/gpt-oss-20b",
                "direct_in": 0.00000004,
                "direct_out": 0.00000015,
                "source_type": "published_ssr_pricing_catalog",
                "source_url": NOVITA_PRICING_URL,
            }
        ]
    )
    routed = pd.DataFrame(
        [
            {
                "dt": "2026-07-10",
                "run_ts": "20260710T115500Z",
                "provider": "novita",
                "model_name": "openai/gpt-oss-20b",
                "routed_in": 0.00000004,
                "routed_out": 0.00000015,
                "routed_source": "api_endpoint_snapshot",
            },
            {
                "dt": "2026-07-10",
                "run_ts": "20260710T121000Z",
                "provider": "novita",
                "model_name": "openai/gpt-oss-20b",
                "routed_in": 0.00000005,
                "routed_out": 0.00000020,
                "routed_source": "frontend_endpoint_stats",
            },
            {
                "dt": "2026-07-10",
                "run_ts": "20260710T060000Z",
                "provider": "novita",
                "model_name": "openai/gpt-oss-20b",
                "routed_in": 0.00000007,
                "routed_out": 0.00000030,
                "routed_source": "api_endpoint_snapshot",
            },
        ]
    )
    matched = h13_venue_basis.nearest_same_day_quotes(direct, routed)
    assert len(matched) == 1
    assert matched.loc[0, "routed_run_ts"] == "20260710T115500Z"
    assert matched.loc[0, "quote_time_gap_minutes"] == 5.0


def test_h13_deduplicates_mapping_changes_by_stable_direct_provider_id():
    direct = pd.DataFrame(
        [
            {
                "dt": "2026-07-10",
                "run_ts": "20260710T070000Z",
                "provider": "chutes",
                "direct_provider_model_id": "zai-org/GLM-5-TEE",
                "model_name": "zai-org/GLM-5-TEE",
            },
            {
                "dt": "2026-07-10",
                "run_ts": "20260710T071000Z",
                "provider": "chutes",
                "direct_provider_model_id": "zai-org/GLM-5-TEE",
                "model_name": "z-ai/glm-5",
            },
        ]
    )
    latest = h13_venue_basis.latest_direct_by_provider_id(direct)
    assert latest.to_dict("records") == [
        {
            "dt": "2026-07-10",
            "run_ts": "20260710T071000Z",
            "provider": "chutes",
            "direct_provider_model_id": "zai-org/GLM-5-TEE",
            "model_name": "z-ai/glm-5",
        }
    ]


def test_h13_market_wide_claim_is_power_gated_without_breadth():
    m = pd.DataFrame(
        {
            "dt": ["2026-07-10"] * 10,
            "provider": ["deepinfra"] * 10,
            "source_type": ["structured_public_api"] * 10,
            "basis_out_pct": [0.0] * 10,
        }
    )
    summary = h13_venue_basis.summarize(m)
    assert summary["evidence_status"] == "power_gated"
    assert "only 1/7 daily observations" in summary["gate_reasons"]
    assert "only 1/3 providers" in summary["gate_reasons"]


def test_h13_descriptive_gate_accepts_repeated_multivenue_panel():
    rows = []
    for day in range(7):
        for provider in ("deepinfra", "together", "fireworks"):
            for _pair in range(10):
                rows.append(
                    {
                        "dt": f"2026-07-{day + 1:02d}",
                        "provider": provider,
                        "source_type": "structured_public_api",
                        "basis_out_pct": 0.0,
                    }
                )
    summary = h13_venue_basis.summarize(pd.DataFrame(rows))
    assert summary["evidence_status"] == "provisional_descriptive"
    assert summary["n_pairs"] == 210
