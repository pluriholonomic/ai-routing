"""CBH-15 — JIT-capacity share: how much flow does on-spike supply serve?

Uniswap v3 benchmark (Wan-Adams 2022): just-in-time liquidity is ~0.3% of
volume against a 40%+ folklore perception. Inference analog: serverless /
on-spike providers vs standing-capacity providers.

Labels: keyword (provider marketing page matches /serverless/i, from
external/provider_pages.parquet) UNION behavioral (capacity ceiling reported
in <50% of the provider's hot-panel ticks — capacity appears intermittently).
Outcomes: steady-state token share of the JIT class; spike differential
(share during top-decile demand ticks vs median ticks, hot panel).

  cbh15_summary.json
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json
from .h68_competition import demand_shares

log = logging.getLogger(__name__)


def keyword_labels() -> dict[str, bool]:
    glob = data.table_glob("provider_pages", layer="external").replace("/*/*.parquet", ".parquet")
    try:
        pages = data.q(f"select * from read_parquet('{glob}')").df()
    except Exception:
        return {}
    text_col = next((c for c in ("text", "page_text", "content", "body") if c in pages), None)
    name_col = next((c for c in ("provider_name", "provider", "name") if c in pages), None)
    if text_col is None or name_col is None:
        return {}
    out = {}
    for _, r in pages.iterrows():
        out[str(r[name_col])] = bool(re.search(r"serverless", str(r[text_col]), re.I))
    return out


def behavioral_labels() -> dict[str, bool]:
    df = data.q(
        f"""
        select provider_name,
               avg(case when capacity_ceiling_rpm is not null then 1.0 else 0.0 end) as ceil_share
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        group by 1
        """
    ).df()
    return {r["provider_name"]: bool(r["ceil_share"] < 0.5) for _, r in df.iterrows()}


def spike_differential(jit: set[str]) -> dict:
    df = data.q(
        f"""
        select run_ts, model_permaslug, provider_name,
               try_cast(request_count_30m as double) as requests
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where request_count_30m is not null
        """
    ).df()
    tot = df.groupby(["model_permaslug", "run_ts"])["requests"].transform("sum")
    df = df[tot > 0].assign(total=tot[tot > 0])
    df["is_jit"] = df["provider_name"].isin(jit)
    tick = (
        df.groupby(["model_permaslug", "run_ts"])
        .apply(
            lambda g: pd.Series(
                {
                    "total": g["total"].iloc[0],
                    "jit_share": g.loc[g["is_jit"], "requests"].sum() / g["total"].iloc[0],
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    out = {}
    for model, g in tick.groupby("model_permaslug"):
        if len(g) < 100 or g["jit_share"].max() == 0:
            continue
        hi = g[g["total"] >= g["total"].quantile(0.9)]["jit_share"].mean()
        mid = g[g["total"] <= g["total"].quantile(0.6)]["jit_share"].mean()
        out[model] = {"spike": float(hi), "calm": float(mid)}
    if not out:
        return {"n_models_with_jit_flow": 0}
    spikes = np.array([v["spike"] for v in out.values()])
    calms = np.array([v["calm"] for v in out.values()])
    return {
        "n_models_with_jit_flow": len(out),
        "median_jit_share_spike_ticks": float(np.median(spikes)),
        "median_jit_share_calm_ticks": float(np.median(calms)),
        "median_spike_minus_calm_pp": float(np.median(spikes - calms) * 100),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    # keyword-only is the maintained label: the behavioral 'ceiling rarely
    # reported' criterion turns out to select hyperscalers (Bedrock/Azure)
    # that simply don't expose ceilings — a reporting artifact, not an
    # on-spike capacity strategy. Kept as a diagnostic below.
    kw = keyword_labels()
    bh = behavioral_labels()
    jit = {p for p, flag in kw.items() if flag}
    shares = demand_shares()
    shares["is_jit"] = shares["provider_name"].isin(jit)
    steady = float(shares.loc[shares["is_jit"], "tokens"].sum() / shares["tokens"].sum())
    bh_only = {p for p, flag in bh.items() if flag}
    shares["is_bh"] = shares["provider_name"].isin(bh_only)
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_providers_keyword_labeled": len(kw),
        "n_jit_class_keyword": len(jit),
        "jit_examples": sorted(jit)[:12],
        "steady_state_jit_token_share": round(steady, 4),
        "benchmark_uniswap_jit": 0.003,
        "spike_differential": spike_differential(jit),
        "diagnostic_behavioral_label": {
            "n_flagged": len(bh_only),
            "token_share": round(
                float(shares.loc[shares["is_bh"], "tokens"].sum() / shares["tokens"].sum()), 4
            ),
            "note": "confounded by ceiling-reporting availability; not used",
        },
        "claim_boundary": (
            "Keyword label = 'serverless' in provider marketing copy, which both "
            "over-includes (standing-capacity providers marketing serverless) and "
            "under-includes; a serving-architecture-verified label needs provider "
            "docs review. Spike differential is hot-panel only."
        ),
    }
    save_json(summary, out_dir, "cbh15_summary")
    return summary
