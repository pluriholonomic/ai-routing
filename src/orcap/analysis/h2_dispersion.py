"""H2 — Law of one price: cross-provider dispersion for the same model, and how
much of it is quality (hedonic) vs friction.

From the latest endpoints snapshot:
  h2_model_dispersion   per (model): N endpoints, price CV, max/min ratio,
                        same stats within identical quantization
  h2_dispersion_fit     regression log(CV) ~ log(N)  (free entry should
                        compress dispersion if routing works like aggregation)
  h2_hedonic            log(price) ~ quantization + log(context) + perf + model FE
                        -> R², residual dispersion after quality adjustment

Comparators: cross-venue same-asset spreads in AMMs (arb'd to bps) vs
Baye–Morgan online-retail dispersion (CV ~ 10-30% persists). Deep analogy ⇒
quality-adjusted residual dispersion near arb-bound levels, shrinking in N.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_endpoints() -> pd.DataFrame:
    df = data.q(
        f"""
        select model_id, provider_name, tag, endpoint_fingerprint, quantization,
               context_length, max_completion_tokens,
               price_prompt, price_completion,
               uptime_last_1d, latency_last_30m, throughput_last_30m
        from {data.latest_endpoints()}
        where price_completion is not null and price_completion > 0
          and model_id not like '%:free'
        """
    ).df()
    return df


def dispersion_table(df: pd.DataFrame) -> pd.DataFrame:
    def _stats(g: pd.DataFrame) -> pd.Series:
        p = g["price_completion"]
        return pd.Series(
            {
                "n_endpoints": len(g),
                "n_providers": g["provider_name"].nunique(),
                "cv": p.std(ddof=0) / p.mean() if len(g) > 1 else 0.0,
                "max_min_ratio": p.max() / p.min(),
                "iqr_over_median": (p.quantile(0.75) - p.quantile(0.25)) / p.median(),
                "modal_quant": g["quantization"].mode().iat[0]
                if g["quantization"].notna().any()
                else None,
            }
        )

    out = df.groupby("model_id").apply(_stats, include_groups=False).reset_index()
    # dispersion within identical quantization (quality-controlled)
    within = (
        df.groupby(["model_id", "quantization"])["price_completion"]
        .agg(["count", "mean", lambda s: s.std(ddof=0)])
        .reset_index()
    )
    within.columns = ["model_id", "quantization", "n", "mean", "std"]
    within = within[within["n"] >= 2]
    within["cv_within_quant"] = within["std"] / within["mean"]
    wq = within.groupby("model_id")["cv_within_quant"].mean().reset_index()
    return out.merge(wq, on="model_id", how="left")


def fit_dispersion_vs_n(disp: pd.DataFrame) -> dict:
    d = disp[(disp["n_providers"] >= 2) & (disp["cv"] > 0)].copy()
    if len(d) < 10:
        return {"n_obs": len(d), "note": "insufficient multi-provider models"}
    d["log_cv"] = np.log(d["cv"])
    d["log_n"] = np.log(d["n_providers"])
    m = smf.ols("log_cv ~ log_n", data=d).fit(cov_type="HC1")
    return {
        "n_obs": int(m.nobs),
        "elasticity_cv_wrt_n": float(m.params["log_n"]),
        "se": float(m.bse["log_n"]),
        "pvalue": float(m.pvalues["log_n"]),
        "r2": float(m.rsquared),
        "mean_cv_multiprovider": float(d["cv"].mean()),
        "median_max_min_ratio": float(d["max_min_ratio"].median()),
    }


def fit_hedonic(df: pd.DataFrame) -> dict:
    # perf fields (latency/throughput 30m) are sparse in v1 snapshots, so the
    # primary hedonic uses only densely-populated quality attributes; a perf-
    # augmented spec runs on the subsample where they exist
    d = df[(df["price_completion"] > 0)].copy()
    d = d[d.groupby("model_id")["model_id"].transform("count") >= 2]
    d["log_p"] = np.log(d["price_completion"])
    d["log_ctx"] = np.log(d["context_length"].clip(lower=1))
    d["quant"] = d["quantization"].fillna("unknown")
    d["uptime"] = d["uptime_last_1d"].fillna(d["uptime_last_1d"].median())
    base = smf.ols("log_p ~ C(model_id)", data=d).fit()
    full = smf.ols("log_p ~ C(model_id) + C(quant) + log_ctx + uptime", data=d).fit()
    out = {
        "n_obs": int(full.nobs),
        "r2_model_fe_only": float(base.rsquared),
        "r2_full_hedonic": float(full.rsquared),
        "within_model_price_var_explained_by_quality": float(
            (full.rsquared - base.rsquared) / max(1e-9, 1 - base.rsquared)
        ),
        "residual_dispersion_approx_cv": float(np.exp(full.resid.std()) - 1),
    }
    perf = d[(d["throughput_last_30m"] > 0) & (d["latency_last_30m"] > 0)].copy()
    if len(perf) >= 50:
        perf["log_tp"] = np.log(perf["throughput_last_30m"])
        perf["log_lat"] = np.log(perf["latency_last_30m"])
        m = smf.ols(
            "log_p ~ C(model_id) + C(quant) + log_ctx + uptime + log_tp + log_lat", data=perf
        ).fit()
        out["perf_subsample"] = {"n_obs": int(m.nobs), "r2": float(m.rsquared)}
    return out


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_endpoints()
    disp = dispersion_table(df)
    save(disp, out_dir, "h2_model_dispersion")
    results = {
        "dispersion_fit": fit_dispersion_vs_n(disp),
        "hedonic": fit_hedonic(df),
        "share_models_multiprovider": float((disp["n_providers"] >= 2).mean()),
    }
    save_json(results, out_dir, "h2_summary")
    log.info("H2: %s", results)
    return results
