"""H38 — How bursty is inference demand?

Three timescales, three instruments (each with its smoothing caveat):

  sub-30-min   peak-to-mean ratio (PMR): fortuna's recent_peak_rpm (an
               instantaneous peak the router observed) over the endpoint's
               average rpm (1-day request total / 1440). Captures bursts
               FASTER than any of our sampling.
  intraday     the 5-min congestion panel's request_count_30m per endpoint:
               within-endpoint CV, Fano factor (var/mean of 30-min counts —
               Poisson = 1; rolling windows smooth, so these are LOWER
               bounds), and the diurnal share (variance explained by
               hour-of-day, pooled with endpoint FE) — cycle vs true bursts.
  daily        per model, 33-day activity: CV of daily tokens, max/median.

Nightly; the intraday estimates sharpen as the congestion panel lengthens.
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


def peak_to_mean() -> tuple[pd.DataFrame, dict]:
    rows = data.q(
        f"""
        select provider_display_name as provider, model_permaslug, record_json
        from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        where dt = (select max(dt) from read_parquet('{data.table_glob("endpoint_stats_daily")}'))
          and variant = 'standard'
        """
    ).df()
    recs = []
    for r in rows.itertuples(index=False):
        d = json.loads(r.record_json)
        peak = (d.get("fortuna") or {}).get("recent_peak_rpm")
        sh = d.get("status_heuristics_1d") or {}
        tot = sum(v or 0 for v in sh.values())
        if not peak or tot < 1440:  # at least ~1 req/min average
            continue
        avg = tot / 1440
        recs.append(
            {
                "provider": r.provider,
                "model_permaslug": r.model_permaslug,
                "avg_rpm": avg,
                "peak_rpm": float(peak),
                "pmr": float(peak) / avg,
            }
        )
    df = pd.DataFrame(recs)
    if df.empty:
        return df, {"gated": "no endpoints"}
    stats = {
        "n_endpoints": int(len(df)),
        "pmr_median": round(float(df["pmr"].median()), 2),
        "pmr_p90": round(float(df["pmr"].quantile(0.9)), 2),
        "pmr_max": round(float(df["pmr"].max()), 1),
        "share_pmr_gt_5": round(float((df["pmr"] > 5).mean()), 3),
    }
    return df, stats


def intraday() -> dict:
    try:
        cg = data.q(
            f"""
            select endpoint_uuid, run_ts, request_count_30m
            from read_parquet('{data.table_glob("congestion_intraday")}')
            where request_count_30m > 0
            """
        ).df()
    except Exception:
        return {"gated": "no congestion panel"}
    n_per = cg.groupby("endpoint_uuid").size()
    d = cg[cg["endpoint_uuid"].isin(n_per[n_per >= 100].index)].copy()
    if d.empty:
        return {"gated": "panel too short"}
    g = d.groupby("endpoint_uuid")["request_count_30m"]
    per = pd.DataFrame({"mean": g.mean(), "var": g.var(), "cv": g.std() / g.mean()})
    per["fano"] = per["var"] / per["mean"]
    d["hour"] = d["run_ts"].str[9:11]
    d["log_c"] = np.log(d["request_count_30m"])
    d["log_c_dm"] = d["log_c"] - d.groupby("endpoint_uuid")["log_c"].transform("mean")
    m = smf.ols("log_c_dm ~ C(hour)", data=d).fit()
    return {
        "n_endpoints": int(len(per)),
        "cv_30min_median": round(float(per["cv"].median()), 3),
        "cv_30min_p90": round(float(per["cv"].quantile(0.9)), 3),
        "fano_median": round(float(per["fano"].median()), 1),
        "fano_note": "Poisson = 1; rolling-window smoothing makes these LOWER bounds",
        "diurnal_variance_share": round(float(m.rsquared), 3),
        "residual_burst_share": round(float(1 - m.rsquared), 3),
    }


def daily() -> dict:
    d = data.q(
        f"""
        select model_permaslug, cast(date as varchar) as day,
               sum(total_prompt_tokens + total_completion_tokens) as toks
        from read_parquet('{data.table_glob("model_activity_daily")}')
        where variant = 'standard' group by 1, 2 having sum(request_count) > 1000
        """
    ).df()
    g = d.groupby("model_permaslug")["toks"]
    per = pd.DataFrame(
        {"n_days": g.size(), "cv": g.std() / g.mean(), "maxmed": g.max() / g.median()}
    )
    per = per[per["n_days"] >= 14]
    return {
        "n_models": int(len(per)),
        "daily_cv_median": round(float(per["cv"].median()), 3),
        "daily_cv_p90": round(float(per["cv"].quantile(0.9)), 3),
        "max_over_median_day_median": round(float(per["maxmed"].median()), 2),
        "share_models_with_2x_day": round(float((per["maxmed"] > 2).mean()), 3),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    pmr_df, pmr_stats = peak_to_mean()
    if len(pmr_df):
        save(pmr_df, out_dir, "h38_pmr")
    results = {"sub30min_pmr": pmr_stats, "intraday": intraday(), "daily": daily()}
    save_json(results, out_dir, "h38_summary")
    log.info("H38: %s", results)
    return results
