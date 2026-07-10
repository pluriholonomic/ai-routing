import pandas as pd

from orcap.analysis.h45_shadow_execution import (
    configured_router_candidates,
    huggingface_candidates,
    openrouter_candidates,
    simulated_base_routes,
)


def test_h45_converts_public_and_configured_policies_to_one_surface():
    openrouter = openrouter_candidates(
        pd.DataFrame(
            {
                "run_ts": ["20260710T000000Z", "20260710T000000Z"],
                "model_id": ["model-a", "model-a"],
                "scenario": ["short", "short"],
                "provider_name": ["a", "b"],
                "expected_quote_usd": [1.0, 2.0],
                "uptime_last_5m": [1.0, 1.0],
                "throughput_last_30m": [10.0, 5.0],
            }
        )
    )
    configured = configured_router_candidates(
        pd.DataFrame(
            {
                "run_ts": ["20260710T000000Z", "20260710T000000Z"],
                "router": ["portkey", "portkey"],
                "config_id": ["router-v1", "router-v1"],
                "model_id": ["model-a", "model-a"],
                "policy_type": ["ordered_failover", "ordered_failover"],
                "provider_name": ["a", "b"],
                "provider_order": [1, 2],
                "provider_weight": [None, None],
            }
        )
    )
    base = simulated_base_routes(pd.concat([openrouter, configured], ignore_index=True))
    shares = base.set_index(["router", "provider_name"])["simulated_route_share"]
    assert shares.loc[("openrouter", "a")] == 0.8
    assert shares.loc[("portkey", "a")] == 1.0


def test_h45_huggingface_policy_type_matches_public_rule():
    candidates = huggingface_candidates(
        pd.DataFrame(
            {
                "run_ts": ["20260710T000000Z", "20260710T000000Z"],
                "policy": ["hf_cheapest_public_quote", "hf_fastest_reported_throughput"],
                "model_id": ["model-a", "model-a"],
                "scenario": ["short", "short"],
                "provider_name": ["a", "a"],
                "expected_quote_usd": [1.0, 1.0],
                "throughput_tps": [10.0, 10.0],
            }
        )
    )
    assert set(candidates["policy_type"]) == {"lowest_cost", "highest_throughput"}
