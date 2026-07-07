"""Synthetic-parameter recovery for H11 (lemons) and H13 (venue basis)."""

import numpy as np
import pandas as pd

from orcap.analysis.h11_quality import lemons_test

rng = np.random.default_rng(13)


def _quality_frame(lemons: bool, n_models: int = 100) -> pd.DataFrame:
    rows = []
    for m in range(n_models):
        base_p = rng.uniform(0.2, 2.0)
        for i in range(4):
            price = base_p * rng.uniform(0.5, 1.5)
            if lemons:
                # cheaper than model median -> higher error rate, deterministically
                err = 0.08 if price < base_p else 0.01
                err += rng.uniform(0, 0.005)
            else:
                err = rng.uniform(0, 0.05)  # quality independent of price
            rows.append(
                {
                    "model_permaslug": f"m{m}",
                    "price_completion": price,
                    "tool_err": err,
                }
            )
    return pd.DataFrame(rows)


def test_lemons_detected_when_planted():
    res = lemons_test(_quality_frame(lemons=True))
    assert res["pvalue"] < 0.01
    assert res["share_bad_given_cheap"] > res["share_bad_given_expensive"]


def test_lemons_not_detected_when_absent():
    res = lemons_test(_quality_frame(lemons=False))
    assert res["pvalue"] > 0.05
