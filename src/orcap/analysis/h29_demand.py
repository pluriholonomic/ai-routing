"""H29 — Demand elasticity of token consumption (historical panel arm).

Model×week panel: tokens from rankings_weekly (2025-07→now) × listed prices
from the wayback panel (forward-filled to weeks). First-difference regression
of Δln tokens on Δln price with week fixed effects (absorbs aggregate growth)
— the substitution-inclusive own-price demand elasticity.

Identification caveat (stated, not hidden): OLS on posted prices. Phase-1/2
evidence says repricing responds to competition and launch experimentation,
not demand level, which limits (but does not eliminate) simultaneity; the
IV arm (entry-instrumented) and the GLM-5.2 war synthetic control join as
the prospective panel matures.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def build_panel() -> pd.DataFrame:
    dem = data.q(
        f"""
        select cast(week as varchar) as week, model_id, max(total_tokens) as tokens
        from read_parquet('{data.table_glob("rankings_weekly")}')
        where model_id not like '%:%' group by 1, 2
        """
    ).df()
    px = data.q(
        f"""
        select id as model_id, run_ts, price_completion
        from {data.wayback_models()}
        where price_completion > 0 and id not like '%:%'
        """
    ).df()
    px["date"] = pd.to_datetime(px["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    px["week"] = px["date"].dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    pw = px.groupby(["model_id", "week"])["price_completion"].median().reset_index()

    dem["week"] = pd.to_datetime(dem["week"]).dt.strftime("%Y-%m-%d")
    weeks = sorted(dem["week"].unique())
    # forward-fill prices onto the demand weeks per model
    frames = []
    for model_id, g in pw.groupby("model_id"):
        s = g.set_index("week")["price_completion"].reindex(weeks).ffill()
        frames.append(pd.DataFrame({"model_id": model_id, "week": weeks, "price": s.values}))
    prices = pd.concat(frames, ignore_index=True).dropna()
    m = dem.merge(prices, on=["model_id", "week"])
    m = m[m["tokens"] > 0].sort_values(["model_id", "week"])
    m["dlog_d"] = m.groupby("model_id")["tokens"].transform(lambda s: np.log(s).diff())
    m["dlog_p"] = m.groupby("model_id")["price"].transform(lambda s: np.log(s).diff())
    return m.dropna(subset=["dlog_d", "dlog_p"])


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    m = build_panel()
    save(m, out_dir, "h29_panel")
    moved = m[m["dlog_p"] != 0]
    results: dict = {
        "n_obs": int(len(m)),
        "n_models": int(m["model_id"].nunique()),
        "n_price_change_weeks": int(len(moved)),
    }
    if len(moved) >= 50:
        reg = smf.ols("dlog_d ~ dlog_p + C(week)", data=m).fit(
            cov_type="cluster", cov_kwds={"groups": m["model_id"]}
        )
        # dynamic response: demand change over the following 4 weeks
        m4 = m.copy()
        m4["dlog_d_fwd4"] = m4.groupby("model_id")["dlog_d"].transform(
            lambda s: s.shift(-1).rolling(4, min_periods=2).sum().shift(-3)
        )
        m4 = m4.dropna(subset=["dlog_d_fwd4"])
        reg4 = smf.ols("dlog_d_fwd4 ~ dlog_p + C(week)", data=m4).fit(
            cov_type="cluster", cov_kwds={"groups": m4["model_id"]}
        )
        results["contemporaneous_elasticity"] = {
            "epsilon": float(reg.params["dlog_p"]),
            "se": float(reg.bse["dlog_p"]),
            "pvalue": float(reg.pvalues["dlog_p"]),
        }
        results["four_week_elasticity"] = {
            "epsilon": float(reg4.params["dlog_p"]),
            "se": float(reg4.bse["dlog_p"]),
            "n": int(reg4.nobs),
        }
        results["identification_note"] = (
            "OLS on posted prices, week FE, model-clustered; IV + war synthetic control gate later"
        )
    else:
        results["gated"] = f"needs >=50 price-change weeks (have {len(moved)})"
    save_json(results, out_dir, "h29_summary")
    log.info("H29: %s", results)
    return results
