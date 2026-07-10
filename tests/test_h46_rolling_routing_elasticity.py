import numpy as np
import pandas as pd
import pytest

from orcap.analysis.h46_rolling_routing_elasticity import rolling_elasticity, summarize


def _shares(elasticity: float = -1.3, days: int = 5) -> pd.DataFrame:
    rows = []
    for day in range(days):
        for model in range(4):
            prices = [1.0 + 0.02 * day, 2.0 + 0.01 * model]
            weights = np.array(prices) ** elasticity
            shares = weights / weights.sum()
            for provider, (price, share) in enumerate(zip(prices, shares, strict=True)):
                rows.append(
                    {
                        "dt": f"2026-07-{day + 1:02d}",
                        "group": f"2026-07-{day + 1:02d}|model-{model}|standard",
                        "share": share,
                        "effective_output_price": price,
                        "cache_hit_rate": 0.1 * provider,
                    }
                )
    return pd.DataFrame(rows)


def test_h46_recovers_rolling_within_market_elasticity():
    panel = rolling_elasticity(_shares(), window_days=3, min_observations=12, min_groups=6)
    assert len(panel) == 3
    assert panel["share_price_elasticity"].iloc[-1] == pytest.approx(-1.3, abs=1e-9)


def test_h46_short_trajectory_is_power_gated_and_keeps_causal_boundary():
    panel = rolling_elasticity(_shares(days=3), window_days=3, min_observations=12, min_groups=6)
    result = summarize(panel)
    assert result["evidence_status"] == "power_gated"
    assert result["n_windows"] == 1
    assert "not an individual-request routing rule" in result["claim_boundary"]


def test_h46_reports_partial_input_coverage_when_no_complete_window_exists():
    result = summarize(pd.DataFrame(), _shares(days=1))
    assert result["evidence_status"] == "power_gated"
    assert result["input_coverage"]["n_input_days"] == 1
    assert "1/14" in result["gate_reasons"][0]
