"""H18: the fit/eval pipeline must recover a planted lifecycle signal."""

import numpy as np
import pandas as pd

from orcap.analysis.h18_predict import FEATURES, fit_eval

rng = np.random.default_rng(18)


def _synthetic(n=6000):
    rows = []
    for _i in range(n):
        age = rng.uniform(1, 700)
        # planted: change hazard decays smoothly with age
        p = 0.35 * np.exp(-age / 60) + 0.01
        t1 = pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=int(rng.uniform(0, 500)))
        row = {f: 0.0 for f in FEATURES}
        row.update(
            {
                "t0": t1 - pd.Timedelta(days=7),
                "t1": t1,
                "changed": bool(rng.uniform() < p),
                "dlog": 0.1,
                "log_gap_days": np.log(7.0),
                "log_age_days": np.log(age),
                "is_young_30d": float(age < 30),
                "log_price": rng.normal(),
                "price_pctile_market": rng.uniform(),
                "month_index": float(t1.month),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def test_planted_lifecycle_signal_recovered():
    df = _synthetic()
    res = fit_eval(df, use_exposure=False)
    assert res["auc_logit"] > 0.8
    # young age must push probability up => negative coef on log_age_days
    assert res["logit_coefs_std"]["log_age_days"] < 0
