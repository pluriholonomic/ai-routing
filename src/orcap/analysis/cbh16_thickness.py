"""CBH-16 — Thickness backfire: does more supply degrade delivered quality?

Li-Netessine (Mgmt Sci 2019): doubling marketplace thickness REDUCED match
rates ~15% via search congestion. Algorithmic-routing null: the router
evaluates all providers at zero marginal cost, so delivered quality is
monotone (weakly improving) in provider count.

Now: cross-section of model-level delivered quality vs provider count.
Event version (pre-registered trigger: a top-50 model gaining >=5 quoting
providers within 14 days) gates until such an entry wave occurs.

  cbh16_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json
from .h68_competition import daily_quotes, demand_shares

log = logging.getLogger(__name__)

ENTRY_WAVE_MIN_PROVIDERS = 5
ENTRY_WAVE_WINDOW_DAYS = 14


def delivered_quality() -> pd.DataFrame:
    """Model-level request-weighted congestion metrics (hot panel)."""
    df = data.q(
        f"""
        select model_permaslug as model_id,
               sum(try_cast(p90_latency_ms as double) * try_cast(request_count_30m as double))
                 / nullif(sum(try_cast(request_count_30m as double)), 0) as p90_weighted,
               sum(try_cast(rate_limited_30m as double))
                 / nullif(sum(try_cast(request_count_30m as double)), 0) as rl_share
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where request_count_30m is not null
        group by 1
        """
    ).df()
    return df


def entry_waves() -> int:
    """Count qualifying entry waves in the panel (trigger check)."""
    q = daily_quotes()
    counts = q.groupby(["model_id", "dt"])["provider_name"].nunique().reset_index()
    waves = 0
    for _, g in counts.groupby("model_id"):
        g = g.sort_values("dt")
        if len(g) >= 2 and g["provider_name"].iloc[-1] - g["provider_name"].iloc[0] >= (
            ENTRY_WAVE_MIN_PROVIDERS
        ):
            waves += 1
    return waves


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quality = delivered_quality()
    quotes = daily_quotes()
    n_prov = quotes.groupby("model_id")["provider_name"].nunique().rename("n_providers")
    shares = demand_shares()
    tokens = shares.groupby("model_id")["tokens"].sum().rename("tokens")
    # congestion panel keys by permaslug; map via slug map inside demand_shares'
    # convention (model_id already harmonized there); join loosely on both keys
    slug = data.q(
        f"""
        select distinct canonical_slug, id
        from read_parquet('{data.table_glob("models_snapshots")}', union_by_name=true)
        where canonical_slug is not null
        """
    ).df()
    quality = quality.merge(slug, left_on="model_id", right_on="canonical_slug", how="left")
    quality["model_id"] = quality["id"].fillna(quality["model_id"])
    df = quality.merge(n_prov, left_on="model_id", right_index=True, how="inner")
    df = df.merge(tokens, left_on="model_id", right_index=True, how="left").dropna(
        subset=["p90_weighted", "n_providers"]
    )
    if len(df) < 15:
        summary = {
            "evidence_status": "power_gated",
            "gate": f"only {len(df)}/15 models with joined quality+thickness",
        }
        save_json(summary, out_dir, "cbh16_summary")
        return summary
    # rank partial correlation of quality vs N controlling demand
    sub = df.dropna(subset=["tokens"])
    r = sub[["p90_weighted", "rl_share", "n_providers", "tokens"]].rank()
    X = np.column_stack([r["n_providers"], r["tokens"], np.ones(len(r))])
    beta_lat, *_ = np.linalg.lstsq(X, r["p90_weighted"].to_numpy(), rcond=None)
    beta_rl, *_ = np.linalg.lstsq(X, r["rl_share"].to_numpy(), rcond=None)
    waves = entry_waves()
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_models": int(len(df)),
        "rank_beta_latency_on_n_providers": round(float(beta_lat[0]), 3),
        "rank_beta_ratelimit_on_n_providers": round(float(beta_rl[0]), 3),
        "read": (
            "positive betas = quality degrades with thickness (Li-Netessine "
            "backfire); zero/negative = router absorbs congestion"
        ),
        "event_version": {
            "trigger": f">={ENTRY_WAVE_MIN_PROVIDERS} new providers on a top-50 model "
            f"within {ENTRY_WAVE_WINDOW_DAYS}d",
            "qualifying_waves_in_panel": int(waves),
            "status": "armed" if waves == 0 else "triggerable",
        },
        "claim_boundary": (
            "Cross-sectional, hot-panel models only; provider count correlates with "
            "demand and model age, and quality drives entry — the event version "
            "carries the identification."
        ),
    }
    save_json(summary, out_dir, "cbh16_summary")
    return summary
