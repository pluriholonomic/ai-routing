"""H11 — Execution-quality-adjusted pricing: frontier, lemons, or noise?

Microstructure separates quoted, effective, and realized execution quality.
Here: does delivered quality (tool-call error rate, structured-output error
rate, throughput, latency) explain within-model price dispersion (a frontier),
or are cheap endpoints quality-equivalent (competition) or quality-degraded
without a visible discount signature (lemons)?

  h11_endpoint_quality  endpoint × quality metrics × price
  h11_summary           quality-extended hedonic, lemons chi-square,
                        quantization discount curve
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import chi2_contingency

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_quality() -> pd.DataFrame:
    return data.q(
        f"""
        with es as (
          select distinct endpoint_uuid, model_permaslug, variant,
                 provider_display_name as provider_name, quantization
          from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        ),
        perf as (
          select endpoint_uuid,
                 median(value) filter (where metric = 'throughput-comparison') as tok_s,
                 median(value) filter (where metric = 'latency-comparison') as latency,
                 avg(value) filter (where metric = 'tool-call-error-rate') as tool_err,
                 avg(value) filter (where metric = 'structured-output-error-rate') as struct_err
          from read_parquet('{data.table_glob("perf_comparisons_daily")}')
          group by 1
        ),
        prices as (
          select model_id, provider_name, tag, min(price_completion) as price_completion
          from {data.latest_endpoints()}
          where price_completion > 0 and model_id not like '%:free'
          group by 1, 2, 3
        ),
        slug_map as (
          select distinct canonical_slug, id from {data.models_snapshots()}
          where run_ts = (select max(run_ts) from {data.models_snapshots()})
            and id not like '%:%'
        )
        select es.model_permaslug, es.provider_name, es.quantization,
               perf.tok_s, perf.latency, perf.tool_err, perf.struct_err,
               p.price_completion
        from es
        join perf using (endpoint_uuid)
        join slug_map s on s.canonical_slug = es.model_permaslug
        join prices p on p.model_id = s.id and p.provider_name = es.provider_name
        where es.variant = 'standard'
        """
    ).df()


def quality_hedonic(df: pd.DataFrame) -> dict:
    d = df.copy()
    d = d[d.groupby("model_permaslug")["model_permaslug"].transform("count") >= 2]
    d["log_p"] = np.log(d["price_completion"])
    d["quant"] = d["quantization"].fillna("unknown")
    d["log_tp"] = np.log(d["tok_s"].where(d["tok_s"] > 0))
    d["log_lat"] = np.log(d["latency"].where(d["latency"] > 0))
    base = smf.ols("log_p ~ C(model_permaslug)", data=d).fit()
    full = smf.ols(
        "log_p ~ C(model_permaslug) + C(quant) + log_tp + log_lat + tool_err + struct_err",
        data=d,
        missing="drop",
    ).fit()
    return {
        "n_obs": int(full.nobs),
        "r2_model_fe": float(base.rsquared),
        "r2_quality": float(full.rsquared),
        "within_model_var_explained_by_delivered_quality": float(
            (full.rsquared - base.rsquared) / max(1e-9, 1 - base.rsquared)
        ),
        "coef_log_throughput": float(full.params.get("log_tp", np.nan)),
        "coef_tool_err": float(full.params.get("tool_err", np.nan)),
    }


def lemons_test(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["tool_err"]).copy()
    d = d[d.groupby("model_permaslug")["model_permaslug"].transform("count") >= 2]
    if len(d) < 40:
        return {"n_obs": len(d), "note": "insufficient"}
    d["cheap"] = d.groupby("model_permaslug")["price_completion"].transform(
        lambda s: s < s.median()
    )
    d["bad"] = d.groupby("model_permaslug")["tool_err"].transform(lambda s: s > s.median())
    tab = pd.crosstab(d["cheap"], d["bad"])
    chi2, p, _, _ = chi2_contingency(tab)
    cheap_bad_share = float(d.loc[d["cheap"], "bad"].mean())
    rich_bad_share = float(d.loc[~d["cheap"], "bad"].mean())
    return {
        "n_obs": int(len(d)),
        "chi2": float(chi2),
        "pvalue": float(p),
        "share_bad_given_cheap": cheap_bad_share,
        "share_bad_given_expensive": rich_bad_share,
        "interpretation": "cheap&bad overrepresented + p<0.05 = lemons discount",
    }


def quantization_curve(df: pd.DataFrame) -> dict:
    d = df.copy()
    d["log_p"] = np.log(d["price_completion"])
    d["quant"] = d["quantization"].fillna("unknown")
    keep = d["quant"].isin(["fp4", "fp8", "bf16", "fp16", "int8", "unknown"])
    d = d[keep]
    d = d[d.groupby("model_permaslug")["quant"].transform("nunique") >= 2]
    if d["model_permaslug"].nunique() < 5:
        return {
            "note": "few models with multiple quantizations",
            "n_models": int(d["model_permaslug"].nunique()),
        }
    m = smf.ols("log_p ~ C(model_permaslug) + C(quant, Treatment('bf16'))", data=d).fit()
    discounts = {
        k.split("T.")[1].rstrip("]"): round(float(np.exp(v) - 1), 4)
        for k, v in m.params.items()
        if "C(quant" in k
    }
    return {"n_obs": int(m.nobs), "discount_vs_bf16": discounts}


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_quality()
    save(df, out_dir, "h11_endpoint_quality")
    results = {
        "n_matched_endpoints": int(len(df)),
        "hedonic": quality_hedonic(df),
        "lemons": lemons_test(df),
        "quantization_curve": quantization_curve(df),
    }
    save_json(results, out_dir, "h11_summary")
    log.info("H11: %s", results)
    return results
