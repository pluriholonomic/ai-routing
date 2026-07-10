"""Unit tests for the zero-spend public-quote routing simulation."""

import pandas as pd

from orcap.analysis.h43_routing_simulation import transition_panel
from orcap.routing_simulation import simulate_snapshot


def _endpoint(provider: str, *, prompt: float, completion: float, parameters=None) -> dict:
    return {
        "model_id": "m",
        "model_name": "Model M",
        "provider_name": provider,
        "tag": "standard",
        "endpoint_fingerprint": provider,
        "context_length": 100_000,
        "max_prompt_tokens": 90_000,
        "max_completion_tokens": 10_000,
        "supported_parameters": parameters or [],
        "price_prompt": prompt,
        "price_completion": completion,
        "price_request": 0.0,
        "status": 1,
        "uptime_last_5m": 1.0,
    }


def test_simulation_uses_inverse_square_cost_weights():
    rows, summary = simulate_snapshot(
        [
            _endpoint("a", prompt=2e-6, completion=2e-6),
            _endpoint("b", prompt=1e-6, completion=1e-6),
        ],
        run_ts="20260709T120000Z",
        dt="2026-07-09",
        models=("m",),
    )
    short = {row["provider_name"]: row for row in rows if row["scenario"] == "short_chat"}
    assert summary["groups_emitted"] == 2  # baseline + long context; feature profiles lack support
    assert short["b"]["is_lowest_public_quote"]
    assert abs(short["b"]["simulated_route_share"] - 0.8) < 1e-12
    assert abs(sum(row["simulated_route_share"] for row in short.values()) - 1.0) < 1e-12


def test_simulation_requires_explicit_feature_support_and_skips_free_quotes():
    rows, summary = simulate_snapshot(
        [
            _endpoint("tools", prompt=1e-6, completion=1e-6, parameters=["tools"]),
            _endpoint("base", prompt=2e-6, completion=2e-6),
            _endpoint("free", prompt=0.0, completion=0.0),
        ],
        run_ts="20260709T120000Z",
        dt="2026-07-09",
        models=("m",),
    )
    assert rows == []
    assert summary["groups_zero_cost"] == 2

    rows, summary = simulate_snapshot(
        [
            _endpoint("tools-a", prompt=1e-6, completion=1e-6, parameters=["tools"]),
            _endpoint("tools-b", prompt=2e-6, completion=2e-6, parameters=["tools"]),
        ],
        run_ts="20260709T120000Z",
        dt="2026-07-09",
        models=("m",),
    )
    assert summary["groups_emitted"] == 3
    assert {row["provider_name"] for row in rows if row["scenario"] == "tool_chat"} == {
        "tools-a",
        "tools-b",
    }
    assert not [row for row in rows if row["scenario"] == "structured_chat"]


def test_transition_panel_detects_quote_induced_share_and_top_route_change():
    rows = pd.DataFrame(
        [
            {
                "run_ts": "20260709T120000Z",
                "panel_id": "p",
                "model_id": "m",
                "scenario": "short_chat",
                "provider_name": "a",
                "expected_quote_usd": 1.0,
                "simulated_route_share": 0.8,
            },
            {
                "run_ts": "20260709T120000Z",
                "panel_id": "p",
                "model_id": "m",
                "scenario": "short_chat",
                "provider_name": "b",
                "expected_quote_usd": 2.0,
                "simulated_route_share": 0.2,
            },
            {
                "run_ts": "20260709T121500Z",
                "panel_id": "p",
                "model_id": "m",
                "scenario": "short_chat",
                "provider_name": "a",
                "expected_quote_usd": 2.0,
                "simulated_route_share": 0.2,
            },
            {
                "run_ts": "20260709T121500Z",
                "panel_id": "p",
                "model_id": "m",
                "scenario": "short_chat",
                "provider_name": "b",
                "expected_quote_usd": 1.0,
                "simulated_route_share": 0.8,
            },
        ]
    )
    rows["ts"] = pd.to_datetime(rows["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    changes = transition_panel(rows)
    change = changes.iloc[0]
    assert change["simulated_share_changed"]
    assert change["top_provider_changed"]
    assert abs(change["total_variation_distance"] - 0.6) < 1e-12
