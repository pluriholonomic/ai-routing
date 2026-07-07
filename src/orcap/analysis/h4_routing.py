"""H4 — Is the router an aggregator? Estimate the volume-share/price elasticity.

Sharp null: OpenRouter's documented default load balancing weights providers
proportional to 1/price^2 among healthy endpoints — i.e. a conditional-logit
share in log price with elasticity ≈ -2 at equal shares. AMM aggregator flow
splitting (marginal-price equalization) implies effectively enormous local
elasticity; sticky front-end order flow implies |elasticity| << 1.

Estimation: within (dt × model × variant), regress log(token share) on
log(effective output price), demeaned within group (group FE), weighting each
group equally. Controls: cache hit rate (proxies workload mix).

  h4_shares      per (dt, model, variant, provider) share + prices
  h4_summary     elasticity estimates
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_shares() -> pd.DataFrame:
    df = data.q(
        f"""
        select cast(dt as varchar) as dt, model_permaslug, variant, provider_slug, provider_name,
               effective_input_price, effective_output_price, cache_hit_rate,
               total_tokens
        from {data.effective_pricing()}
        where total_tokens > 0 and effective_output_price > 0
        """
    ).df()
    df["group"] = df["dt"] + "|" + df["model_permaslug"] + "|" + df["variant"]
    gsum = df.groupby("group")["total_tokens"].transform("sum")
    df["share"] = df["total_tokens"] / gsum
    df["n_in_group"] = df.groupby("group")["provider_slug"].transform("count")
    return df[df["n_in_group"] >= 2].copy()


def within_demean(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c + "_dm"] = out[c] - out.groupby("group")[c].transform("mean")
    return out


def fit_elasticity(df: pd.DataFrame) -> dict:
    d = df.copy()
    d["log_share"] = np.log(d["share"])
    d["log_p"] = np.log(d["effective_output_price"])
    d["chr"] = d["cache_hit_rate"].fillna(0)
    d = within_demean(d, ["log_share", "log_p", "chr"])
    m = smf.ols("log_share_dm ~ log_p_dm + chr_dm - 1", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": d["group"]}
    )
    # robustness: drop tiny shares (<1%), which are dominated by pinned/BYOK traffic
    d2 = d[d["share"] >= 0.01]
    m2 = smf.ols("log_share_dm ~ log_p_dm + chr_dm - 1", data=d2).fit(
        cov_type="cluster", cov_kwds={"groups": d2["group"]}
    )
    return {
        "n_obs": int(m.nobs),
        "n_groups": int(d["group"].nunique()),
        "share_price_elasticity": float(m.params["log_p_dm"]),
        "se": float(m.bse["log_p_dm"]),
        "elasticity_dropping_sub1pct_shares": float(m2.params["log_p_dm"]),
        "se_sub1pct": float(m2.bse["log_p_dm"]),
        "null_inverse_square_routing": -2.0,
        "interpretation": (
            "≈ -2 ⇒ algorithmic router dominates (aggregator-like); "
            "|e| << 1 ⇒ pinned order flow (front-end stickiness); "
            "e << -2 ⇒ near-marginal-price-equalization (AMM-splitter-like)"
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_shares()
    save(df, out_dir, "h4_shares")
    results = fit_elasticity(df) if len(df) else {"n_obs": 0}
    save_json(results, out_dir, "h4_summary")
    log.info("H4: %s", results)
    return results
