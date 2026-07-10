import math

import pandas as pd

from orcap.shadow_routing import allocate, flip_conditions, stress_states, summarize_states


def _candidates(**extra):
    base = {
        "router": "test-router",
        "policy_type": "inverse_square_price",
        "model_id": "model-a",
        "scenario": "short",
        "provider_name": ["a", "b"],
        "expected_quote_usd": [1.0, 2.0],
        "throughput_tps": [10.0, 5.0],
        "provider_order": [1, 2],
        "provider_weight": [3.0, 1.0],
    }
    base.update(extra)
    return pd.DataFrame(base)


def test_inverse_square_allocation_and_quote_flip():
    allocated = allocate(_candidates(), "inverse_square_price")
    assert allocated.set_index("provider_name").loc["a", "simulated_route_share"] == 0.8
    assert allocated.set_index("provider_name").loc["b", "simulated_route_share"] == 0.2

    flips = flip_conditions(_candidates())
    assert flips.set_index("provider_name").loc["a", "required_quote_cut_pct_to_tie_best"] == 0
    assert math.isclose(
        flips.set_index("provider_name").loc["b", "required_quote_cut_pct_to_tie_best"], 50.0
    )


def test_stress_state_removes_provider_and_reports_winner_fragility():
    states = stress_states(_candidates())
    down_a = states[states["health_state"] == "provider_down:a"]
    assert down_a["provider_name"].tolist() == ["b"]
    summary = summarize_states(states).iloc[0]
    assert summary["base_winner"] == "a"
    assert summary["base_winner_state_robustness"] < 1.0
    assert summary["n_distinct_state_winners"] == 2


def test_lowest_cost_ordered_and_weighted_policies():
    candidates = _candidates(expected_quote_usd=[0.0, 1.0])
    cheapest = allocate(candidates, "lowest_cost").set_index("provider_name")
    assert cheapest.loc["a", "simulated_route_share"] == 1.0

    ordered = allocate(candidates, "ordered_failover").set_index("provider_name")
    assert ordered.loc["a", "simulated_route_share"] == 1.0
    assert ordered.loc["b", "simulated_route_share"] == 0.0

    weighted = allocate(candidates, "weighted").set_index("provider_name")
    assert weighted.loc["a", "simulated_route_share"] == 0.75
    assert weighted.loc["b", "simulated_route_share"] == 0.25
