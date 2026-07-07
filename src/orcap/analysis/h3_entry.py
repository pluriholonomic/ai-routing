"""H3 — Free entry / zero-profit: does the Nth entrant push prices to
competitive levels (Bresnahan–Reiss), and how do prices sit relative to a
naive GPU cost bound?

  h3_entry_price      per model: min/median completion price vs N providers
  h3_br_fit           log(min price | model controls) on entrant-count dummies
  h3_markup           naive cost bound per endpoint: GPU $/hr (H100 SXM
                      on-demand median from gpu_offers_snapshots) divided by
                      single-stream throughput. Batched serving makes true
                      cost much lower, so LEVELS overstate margins wildly —
                      interpret only the SLOPE vs N and the cross-provider
                      ordering, never the level.

Comparator: mining/staking free entry (hashprice ≈ marginal cost); phase-2
adds entry/exit hazards from pricing_changes endpoint add/remove events.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h2_dispersion import load_endpoints

log = logging.getLogger(__name__)


def gpu_hourly_usd(gpu_class: str = "H100 SXM") -> float | None:
    try:
        df = data.q(
            f"""
            with latest as (select max(run_ts) m from {data.gpu_offers()})
            select median(dph_total) med from {data.gpu_offers()}, latest
            where run_ts = latest.m and gpu_class = '{gpu_class}'
              and offer_type = 'on-demand' and num_gpus = 1
            """
        ).df()
        return float(df["med"].iat[0])
    except Exception as exc:  # table may not exist yet in a fresh store
        log.warning("gpu offers unavailable: %s", exc)
        return None


def entry_price_table(df: pd.DataFrame) -> pd.DataFrame:
    agg = (
        df.groupby("model_id")
        .agg(
            n_providers=("provider_name", "nunique"),
            n_endpoints=("provider_name", "size"),
            min_price=("price_completion", "min"),
            median_price=("price_completion", "median"),
            context_length=("context_length", "max"),
            median_throughput=("throughput_last_30m", "median"),
        )
        .reset_index()
    )
    agg["author"] = agg["model_id"].str.split("/").str[0]
    return agg


def br_fit(agg: pd.DataFrame) -> dict:
    d = agg[(agg["min_price"] > 0)].copy()
    d["log_min_p"] = np.log(d["min_price"])
    d["log_ctx"] = np.log(d["context_length"].clip(lower=1))
    d["n_cat"] = pd.cut(
        d["n_providers"], bins=[0, 1, 2, 3, 4, np.inf], labels=["1", "2", "3", "4", "5+"]
    )
    m = smf.ols("log_min_p ~ C(n_cat) + log_ctx + C(author)", data=d).fit(cov_type="HC1")
    coefs = {
        k.replace("C(n_cat)[T.", "n=").rstrip("]"): float(v)
        for k, v in m.params.items()
        if k.startswith("C(n_cat)")
    }
    ses = {
        k.replace("C(n_cat)[T.", "n=").rstrip("]"): float(v)
        for k, v in m.bse.items()
        if k.startswith("C(n_cat)")
    }
    return {"n_obs": int(m.nobs), "r2": float(m.rsquared), "price_vs_n1": coefs, "se": ses}


def load_scrape_throughput() -> pd.DataFrame:
    """Median tok/s per (model, provider) from the frontend perf comparisons —
    much denser than the v1 snapshot's throughput_last_30m."""
    try:
        return data.q(
            f"""
            with es as (
              select distinct endpoint_uuid, model_permaslug, provider_slug,
                     provider_display_name
              from read_parquet('{data.table_glob("endpoint_stats_daily")}')
            ),
            tp as (
              select endpoint_uuid, median(value) tok_s
              from read_parquet('{data.table_glob("perf_comparisons_daily")}')
              where metric = 'throughput-comparison' and value > 0
              group by 1
            )
            select es.model_permaslug, es.provider_display_name as provider_name,
                   median(tp.tok_s) as tok_s
            from es join tp using (endpoint_uuid)
            group by 1, 2
            """
        ).df()
    except Exception as exc:
        log.warning("scrape throughput unavailable: %s", exc)
        return pd.DataFrame(columns=["model_permaslug", "provider_name", "tok_s"])


def markup_table(df: pd.DataFrame, gpu_usd_hr: float | None) -> pd.DataFrame:
    tp = load_scrape_throughput()
    slug_map = data.q(
        f"""
        select distinct canonical_slug, id from {data.models_snapshots()}
        where run_ts = (select max(run_ts) from {data.models_snapshots()})
          and id not like '%:%'
        """
    ).df()
    tp = tp.merge(slug_map, left_on="model_permaslug", right_on="canonical_slug")
    d = df.merge(
        tp[["id", "provider_name", "tok_s"]],
        left_on=["model_id", "provider_name"],
        right_on=["id", "provider_name"],
        how="left",
    )
    d["tok_s"] = d["tok_s"].fillna(d["throughput_last_30m"])
    d = d[d["tok_s"] > 0].copy()
    if gpu_usd_hr is None:
        d["naive_cost_per_token"] = np.nan
    else:
        d["naive_cost_per_token"] = gpu_usd_hr / (d["tok_s"] * 3600)
    d["naive_markup"] = d["price_completion"] / d["naive_cost_per_token"]
    return d[
        [
            "model_id",
            "provider_name",
            "tag",
            "quantization",
            "price_completion",
            "tok_s",
            "naive_cost_per_token",
            "naive_markup",
        ]
    ]


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_endpoints()
    agg = entry_price_table(df)
    save(agg, out_dir, "h3_entry_price")
    gpu = gpu_hourly_usd()
    mk = markup_table(df, gpu)
    save(mk, out_dir, "h3_markup")
    results = {
        "br": br_fit(agg),
        "gpu_h100_usd_hr": gpu,
        "median_naive_markup": float(mk["naive_markup"].median())
        if mk["naive_markup"].notna().any()
        else None,
        "markup_slope_note": "levels overstated (single-stream cost bound); use slope/ordering",
    }
    save_json(results, out_dir, "h3_summary")
    log.info("H3: %s", results)
    return results
