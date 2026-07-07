"""H10 — Last look / phantom liquidity: do aggressive quotes reject more flow?

RFQ market makers post attractive quotes and reject fills under stress ("last
look"); the inference analog is rate-limiting and derankable errors. OpenRouter
even keeps an MM scorecard: the `fortuna` Beta posterior over endpoint success.

From endpoint_stats_daily.record_json (latest day):
  h10_endpoint_ll     endpoint-day reject rates + fortuna + capacity + price
  h10_summary         (a) within-model price→reject regression
                      (b) H2 dispersion recomputed on executable quotes
                      (c) reject-rate distribution vs FX last-look norms
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_lastlook() -> pd.DataFrame:
    rows = data.q(
        f"""
        select model_permaslug, variant, provider_display_name as provider_name,
               endpoint_uuid, record_json
        from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        where dt = (select max(dt) from
                    read_parquet('{data.table_glob("endpoint_stats_daily")}'))
        """
    ).df()
    out = []
    for r in rows.itertuples(index=False):
        d = json.loads(r.record_json)
        sh = d.get("status_heuristics_1d") or {}
        succ = sh.get("success", 0) or 0
        rl = sh.get("rateLimited", 0) or 0
        de = sh.get("derankableError", 0) or 0
        total = succ + rl + de
        pricing = d.get("pricing") or {}
        fortuna = d.get("fortuna") or {}
        price = _f(pricing.get("completion"))
        if total < 100 or not price or price <= 0:
            continue  # too little flow to measure a reject rate
        out.append(
            {
                "model_permaslug": r.model_permaslug,
                "variant": r.variant,
                "provider_name": r.provider_name,
                "endpoint_uuid": r.endpoint_uuid,
                "price_completion": price,
                "requests_1d": total,
                "reject_rate": (rl + de) / total,
                "rate_limited_share": rl / total,
                "error_share": de / total,
                "fortuna_mean": _beta_mean(fortuna),
                "capacity_ceiling_rpm": fortuna.get("capacity_ceiling_rpm"),
                "is_deranked": bool(d.get("is_deranked")),
                "is_free": bool(d.get("is_free")),
            }
        )
    return pd.DataFrame(out)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _beta_mean(fortuna: dict) -> float | None:
    a, b = fortuna.get("beta_alpha"), fortuna.get("beta_beta")
    if a and b:
        return a / (a + b)
    return None


def fit_price_vs_reject(df: pd.DataFrame) -> dict:
    d = df[(~df["is_free"])].copy()
    d = d[d.groupby("model_permaslug")["model_permaslug"].transform("count") >= 2]
    if len(d) < 30:
        return {"n_obs": len(d), "note": "insufficient multi-quoter models"}
    d["log_p"] = np.log(d["price_completion"])
    d["log_p_dm"] = d["log_p"] - d.groupby("model_permaslug")["log_p"].transform("mean")
    d["rr_dm"] = d["reject_rate"] - d.groupby("model_permaslug")["reject_rate"].transform("mean")
    m = smf.ols("rr_dm ~ log_p_dm - 1", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": d["model_permaslug"]}
    )
    return {
        "n_obs": int(m.nobs),
        "n_models": int(d["model_permaslug"].nunique()),
        "reject_on_logprice": float(m.params["log_p_dm"]),
        "se": float(m.bse["log_p_dm"]),
        "pvalue": float(m.pvalues["log_p_dm"]),
        "interpretation": "negative slope = cheaper quotes reject more (last-look equilibrium)",
    }


def executable_dispersion(df: pd.DataFrame) -> dict:
    """H2's CV recomputed weighting quotes by executability (1 - reject rate)."""
    d = df[~df["is_free"]].copy()
    res = []
    for _slug, g in d.groupby("model_permaslug"):
        if len(g) < 2:
            continue
        p = g["price_completion"].to_numpy()
        w = (1 - g["reject_rate"]).clip(lower=0.01).to_numpy()
        cv_posted = p.std() / p.mean()
        mu = np.average(p, weights=w)
        cv_exec = np.sqrt(np.average((p - mu) ** 2, weights=w)) / mu
        res.append({"cv_posted": cv_posted, "cv_executable": cv_exec})
    r = pd.DataFrame(res)
    if r.empty:
        return {"n_models": 0}
    return {
        "n_models": int(len(r)),
        "mean_cv_posted": float(r["cv_posted"].mean()),
        "mean_cv_executable": float(r["cv_executable"].mean()),
        "dispersion_reduction_pct": float(
            100 * (1 - r["cv_executable"].mean() / r["cv_posted"].mean())
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_lastlook()
    save(df, out_dir, "h10_endpoint_ll")
    rr = df.loc[~df["is_free"], "reject_rate"]
    results = {
        "n_endpoints": int(len(df)),
        "reject_rate_median": float(rr.median()) if len(rr) else None,
        "reject_rate_p90": float(rr.quantile(0.9)) if len(rr) else None,
        "share_endpoints_reject_gt_5pct": float((rr > 0.05).mean()) if len(rr) else None,
        "share_deranked": float(df["is_deranked"].mean()),
        "fx_last_look_norm": "2-10% reject rates (FX/RFQ literature)",
        "price_vs_reject": fit_price_vs_reject(df),
        "executable_dispersion": executable_dispersion(df),
    }
    save_json(results, out_dir, "h10_summary")
    log.info("H10: %s", results)
    return results
