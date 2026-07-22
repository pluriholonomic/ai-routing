from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orcap.analysis.h92_revenue_share_identity import (
    _fit_market_fe,
    build_identity_panel,
    price_label_permutation,
)


def _synthetic_panel(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for day in range(8):
        for market in range(10):
            group = f"{day}|{market}|standard"
            log_price = rng.normal(scale=0.8, size=6)
            revenue_weight = np.exp(rng.normal(scale=0.12, size=6))
            tokens = revenue_weight / np.exp(log_price)
            shares = tokens / tokens.sum()
            for provider in range(6):
                rows.append(
                    {
                        "group": group,
                        "dt": f"2026-07-{day + 1:02d}",
                        "provider_slug": f"provider-{provider}",
                        "share": shares[provider],
                        "total_tokens": tokens[provider] * 1_000_000,
                        "effective_output_price": np.exp(log_price[provider]),
                        "cache_hit_rate": rng.uniform(0, 0.5),
                    }
                )
    return pd.DataFrame(rows)


def test_accounting_identity_is_exact() -> None:
    panel = build_identity_panel(_synthetic_panel())
    assert panel["identity_residual"].abs().max() < 1e-12
    assert np.allclose(panel.groupby("group")["share"].sum(), 1.0)
    assert np.allclose(panel.groupby("group")["revenue_proxy_share"].sum(), 1.0)


def test_market_fe_coefficients_translate_by_exactly_one() -> None:
    panel = build_identity_panel(_synthetic_panel())
    quantity = _fit_market_fe(panel, "log_share")
    revenue = _fit_market_fe(panel, "log_revenue_proxy_share")
    assert revenue["coefficient"] - quantity["coefficient"] == pytest.approx(1.0, abs=1e-12)
    assert revenue["standard_error"] == pytest.approx(quantity["standard_error"], abs=1e-12)
    assert quantity["coefficient"] == pytest.approx(-1.0, abs=0.03)
    assert revenue["coefficient"] == pytest.approx(0.0, abs=0.03)


def test_within_market_price_permutation_rejects_planted_inverse_matching() -> None:
    panel = build_identity_panel(_synthetic_panel())
    null, summary = price_label_permutation(panel, draws=99, seed=7)
    assert len(null) == 99
    assert summary["observed_quantity_share_price_coefficient"] < -0.95
    assert summary["one_sided_p_quantity_slope_at_most_observed"] <= 0.02
    low, high = summary["quantity_slope_null_ci95"]
    assert low < 0 < high
