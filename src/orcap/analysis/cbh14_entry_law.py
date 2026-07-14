"""CBH-14 — Entry law: does provider count scale as sqrt(demand)?

Intent-market theory (Chitra-Kulkarni-Pai 2024): with entry costs, the
equilibrium number of competing solvers scales as k* = O(sqrt(n)) in market
size (exponential value tails; n^(1/3) for uniform). Free-entry
zero-profit alternatives put no such structure on the exponent. Test: OLS of
log(active providers) on log(model token demand), cross-section.

  cbh14_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save_json
from .h68_competition import daily_quotes, demand_shares

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quotes = daily_quotes()
    shares = demand_shares()
    n_prov = quotes.groupby("model_id")["provider_name"].nunique().rename("n_providers")
    # 'active' = actually receiving tokens (the solver-analog margin, vs listing)
    n_active = shares.groupby("model_id")["provider_name"].nunique().rename("n_active")
    tokens = shares.groupby("model_id")["tokens"].sum().rename("tokens")
    df = pd.concat([n_prov, n_active, tokens], axis=1).dropna()
    df = df[(df["tokens"] > 0) & (df["n_providers"] >= 1)]
    if len(df) < 30:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(df)}/30 models"}
        save_json(summary, out_dir, "cbh14_summary")
        return summary
    x = np.log(df["tokens"].to_numpy())
    y = np.log(df["n_providers"].to_numpy())
    X = np.column_stack([x, np.ones(len(x))])
    beta, res, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    r2 = 1 - np.var(y - yhat) / np.var(y)
    # HC1-ish se via bootstrap
    rng = np.random.default_rng(3)
    draws = []
    for _ in range(500):
        idx = rng.integers(0, len(x), len(x))
        b, *_ = np.linalg.lstsq(X[idx], y[idx], rcond=None)
        draws.append(b[0])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    ya = np.log(df["n_active"].to_numpy())
    beta_a, *_ = np.linalg.lstsq(X, ya, rcond=None)
    r2_a = 1 - np.var(ya - X @ beta_a) / np.var(ya)
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_models": int(len(df)),
        "slope_log_providers_on_log_tokens": round(float(beta[0]), 4),
        "slope_ci95": [round(float(lo), 4), round(float(hi), 4)],
        "r2": round(float(r2), 3),
        "slope_active_providers": round(float(beta_a[0]), 4),
        "r2_active": round(float(r2_a), 3),
        "benchmarks": {"sqrt_law": 0.5, "cube_root_law": 0.333},
        "read": (
            "slope ~0.5 = entry-cost intent-market scaling; ~0.33 = uniform-tail "
            "variant; slope near 0 = listing is ~free and unrelated to demand"
        ),
        "claim_boundary": (
            "Cross-sectional; 'active provider' = quoting, not serving. Demand "
            "aggregated over a ~1-week window; simultaneity (entry raises capacity, "
            "hence tokens) inflates the slope — panel version gates on months."
        ),
    }
    save_json(summary, out_dir, "cbh14_summary")
    return summary
