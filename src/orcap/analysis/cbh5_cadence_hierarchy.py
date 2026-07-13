"""CBH-5 (was H74) — Brown-MacKay cadence hierarchy: do slow repricers price higher?

Brown & MacKay (2023): among retailers selling identical products, pricing
*frequency* acts as commitment — the fastest-updating firm undercuts, slower
firms sit persistently above it (+10% for daily-vs-hourly, ~+30% for weekly),
supracompetitive without collusion.

Cadence classes here: 'fast' = provider repriced within the live 5-min panel
window; 'slow' = no live change but present with history in the LiteLLM
backfill or the live panel. Price-level test: within (model, day), OLS of
log(price) on the fast dummy with model-day demeaning.

  h74_summary.json   slow-over-fast premium + follower-rule diagnostics
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json
from .h68_competition import daily_quotes

log = logging.getLogger(__name__)


def fast_providers() -> set[str]:
    df = data.q(
        f"""
        select distinct provider_name
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field like 'price_%' and model_id not like '%:%'
        """
    ).df()
    return set(df["provider_name"])


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quotes = daily_quotes()
    fast = fast_providers()
    quotes["fast"] = quotes["provider_name"].isin(fast).astype(float)
    # within (model, day) demeaning — identical-product comparison
    grp = quotes.groupby(["model_id", "dt"])
    n_per = grp["provider_name"].transform("size")
    mixed = quotes[(n_per >= 2)].copy()
    mixed = mixed[mixed.groupby(["model_id", "dt"])["fast"].transform("nunique") > 1]
    if mixed["model_id"].nunique() < 10:
        summary = {
            "evidence_status": "power_gated",
            "gate": f"only {mixed['model_id'].nunique()}/10 models with mixed cadence classes",
        }
        save_json(summary, out_dir, "cbh5_summary")
        return summary
    mixed["logp"] = np.log(mixed["price"])
    mixed["logp_dm"] = mixed["logp"] - mixed.groupby(["model_id", "dt"])["logp"].transform("mean")
    mixed["fast_dm"] = mixed["fast"] - mixed.groupby(["model_id", "dt"])["fast"].transform("mean")
    beta = float(
        (mixed["fast_dm"] * mixed["logp_dm"]).sum() / (mixed["fast_dm"] ** 2).sum()
    )
    # cluster-robust-ish se via model-level block bootstrap
    rng = np.random.default_rng(0)
    models = mixed["model_id"].unique()
    draws = []
    for _ in range(300):
        pick = rng.choice(models, size=len(models), replace=True)
        b = pd.concat([mixed[mixed["model_id"] == m] for m in pick], ignore_index=True)
        denom = (b["fast_dm"] ** 2).sum()
        if denom > 0:
            draws.append(float((b["fast_dm"] * b["logp_dm"]).sum() / denom))
    lo, hi = (np.percentile(draws, [2.5, 97.5]) if draws else (np.nan, np.nan))
    slow_premium_pct = 100.0 * (np.exp(-beta) - 1.0)
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_obs": int(len(mixed)),
        "n_models": int(mixed["model_id"].nunique()),
        "n_fast_providers": int(len(fast)),
        "beta_fast_on_logprice_within_model_day": round(beta, 4),
        "beta_ci95": [round(float(lo), 4), round(float(hi), 4)],
        "slow_over_fast_premium_pct": round(float(slow_premium_pct), 2),
        "benchmark_brown_mackay_pct": [10, 30],
        "claim_boundary": (
            "Cadence classified from a ~6-day live window: 'fast' means repriced at "
            "least once recently, a coarse proxy for update technology. Not quality-"
            "adjusted; slow providers may differ in latency/quantization. Follower-rule "
            "estimation gates on a multi-week panel."
        ),
    }
    save_json(summary, out_dir, "cbh5_summary")
    return summary
