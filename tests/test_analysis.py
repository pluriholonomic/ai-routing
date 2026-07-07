"""Synthetic-data tests: each estimator must recover a planted parameter."""

import numpy as np
import pandas as pd

from orcap.analysis.h1_spells import change_events, summarize
from orcap.analysis.h2_dispersion import fit_dispersion_vs_n
from orcap.analysis.h4_routing import fit_elasticity
from orcap.analysis.h5_frontends import hhi, zipf_slope

rng = np.random.default_rng(7)


def test_h1_change_rate_recovered():
    # one model, monthly snapshots for 2 years, price changes every 4th snapshot
    ts = pd.date_range("2024-01-01", periods=24, freq="30D", tz="UTC")
    price, prices = 1.0, []
    for i in range(24):
        if i > 0 and i % 4 == 0:
            price *= 1.2
        prices.append(price)
    panel = pd.DataFrame(
        {
            "model_id": "a/m",
            "ts": ts,
            "price_completion": prices,
            "run_ts": ts.strftime("%Y%m%dT%H%M%SZ"),
        }
    )
    ev = change_events(panel)
    s = summarize(ev)
    assert s["n_changes"] == 5
    assert abs(s["share_pairs_changed"] - 5 / 23) < 1e-9
    # every change is +20% -> all > 10%
    assert s["share_changes_gt_10pct"] == 1.0


def test_h2_dispersion_elasticity_recovered():
    # plant CV = N^(-0.5): log CV = -0.5 log N
    rows = []
    for i in range(200):
        n = rng.integers(2, 12)
        rows.append(
            {"model_id": f"m{i}", "n_providers": n, "cv": float(n**-0.5), "max_min_ratio": 2.0}
        )
    fit = fit_dispersion_vs_n(pd.DataFrame(rows))
    assert abs(fit["elasticity_cv_wrt_n"] - (-0.5)) < 0.01


def test_h4_elasticity_recovered():
    # plant conditional-logit shares with elasticity -2 (inverse-square routing)
    rows = []
    for g in range(300):
        n = rng.integers(2, 6)
        prices = rng.uniform(0.5, 3.0, n)
        w = prices**-2.0
        shares = w / w.sum()
        for i in range(n):
            rows.append(
                {
                    "dt": "2026-07-07",
                    "model_permaslug": f"m{g}",
                    "variant": "standard",
                    "provider_slug": f"p{i}",
                    "provider_name": f"p{i}",
                    "effective_input_price": prices[i],
                    "effective_output_price": prices[i],
                    "cache_hit_rate": 0.0,
                    "total_tokens": shares[i] * 1e9,
                    "group": f"g{g}",
                    "share": shares[i],
                    "n_in_group": n,
                }
            )
    fit = fit_elasticity(pd.DataFrame(rows))
    assert abs(fit["share_price_elasticity"] - (-2.0)) < 0.05


def test_h5_hhi_and_zipf():
    assert abs(hhi(np.array([1.0, 1.0])) - 5000) < 1e-9
    # perfect Zipf: size ∝ 1/rank -> slope -1
    sizes = 1.0 / np.arange(1, 101)
    z = zipf_slope(sizes * 1e9)
    assert abs(z["slope"] - (-1.0)) < 0.01
