import pandas as pd

from orcap.analysis.h44_cross_router import compare_policy_surfaces, match_quotes

ALIASES = {"z-ai/glm-5.2": "zai-org/GLM-5.2"}


def test_h44_matches_explicit_model_alias_and_provider_alias():
    openrouter = pd.DataFrame(
        [
            {
                "model_id": "z-ai/glm-5.2",
                "provider_name": "Fireworks",
                "price_prompt": 1e-6,
                "price_completion": 2e-6,
            }
        ]
    )
    huggingface = pd.DataFrame(
        [
            {
                "model_id": "zai-org/GLM-5.2",
                "provider_name": "fireworks-ai",
                "price_input_usd_per_mtok": 1.0,
                "price_output_usd_per_mtok": 2.0,
            }
        ]
    )
    matched = match_quotes(openrouter, huggingface, ALIASES)
    assert len(matched) == 1
    assert matched.iloc[0]["provider_id"] == "fireworks"
    assert matched.iloc[0]["output_basis_pct"] == 0.0


def test_h44_aligns_policy_share_proxies_without_claiming_fills():
    openrouter = pd.DataFrame(
        [
            {
                "model_id": "z-ai/glm-5.2",
                "scenario": "short_chat",
                "provider_name": "DeepInfra",
                "simulated_route_share": 0.7,
            }
        ]
    )
    huggingface = pd.DataFrame(
        [
            {
                "model_id": "zai-org/GLM-5.2",
                "scenario": "short_chat",
                "provider_name": "deepinfra",
                "policy": "hf_cheapest_public_quote",
                "simulated_route_share": 1.0,
            },
            {
                "model_id": "zai-org/GLM-5.2",
                "scenario": "short_chat",
                "provider_name": "deepinfra",
                "policy": "hf_fastest_reported_throughput",
                "simulated_route_share": 0.0,
            },
        ]
    )
    panel = compare_policy_surfaces(openrouter, huggingface, ALIASES)
    assert len(panel) == 1
    assert panel.iloc[0]["openrouter_simulated_share"] == 0.7
    assert panel.iloc[0]["hf_cheapest_public_share"] == 1.0
    assert panel.iloc[0]["hf_fastest_reported_share"] == 0.0
