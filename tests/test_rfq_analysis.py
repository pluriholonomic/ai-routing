"""Synthetic-parameter recovery for the RFQ-comparison estimators (H10/H11)."""

import numpy as np
import pandas as pd

from orcap.analysis.h10_lastlook import executable_dispersion, fit_price_vs_reject

rng = np.random.default_rng(11)


def _ll_frame(slope: float, n_models: int = 120) -> pd.DataFrame:
    rows = []
    for m in range(n_models):
        n = rng.integers(2, 5)
        base = rng.uniform(0.2, 2.0)
        for i in range(n):
            price = base * rng.uniform(0.6, 1.6)
            # reject rate declines in log price with the planted slope
            rr = np.clip(0.15 + slope * np.log(price / base), 0, 1)
            rows.append(
                {
                    "model_permaslug": f"m{m}",
                    "provider_name": f"p{i}",
                    "price_completion": price,
                    "reject_rate": rr,
                    "is_free": False,
                }
            )
    return pd.DataFrame(rows)


def test_h10_price_reject_slope_recovered():
    df = _ll_frame(slope=-0.08)
    fit = fit_price_vs_reject(df)
    assert abs(fit["reject_on_logprice"] - (-0.08)) < 0.005
    assert fit["pvalue"] < 0.01


def test_h10_executable_dispersion_collapses_when_cheap_quotes_fake():
    # two quotes per model: cheap one rejects 95%, expensive one fills
    rows = []
    for m in range(50):
        p = rng.uniform(0.5, 2.0)
        rows.append(
            {"model_permaslug": f"m{m}", "provider_name": "cheapfake",
             "price_completion": 0.5 * p, "reject_rate": 0.95, "is_free": False}
        )
        rows.append(
            {"model_permaslug": f"m{m}", "provider_name": "real",
             "price_completion": p, "reject_rate": 0.01, "is_free": False}
        )
    res = executable_dispersion(pd.DataFrame(rows))
    assert res["mean_cv_executable"] < res["mean_cv_posted"] * 0.5
    assert res["dispersion_reduction_pct"] > 50
