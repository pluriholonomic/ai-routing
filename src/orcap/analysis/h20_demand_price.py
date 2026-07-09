"""H20 (preliminary) — Demand features vs token pricing, and provider
elasticity to demand.

Part 1 — cross-source correlation panel (model level, latest day):
  demand features: routed tokens (activity), HF downloads/trending,
  HN stories (7d), model age; pricing objects: min price, cross-provider
  dispersion, provider count, repriced-recently flag.
  Spearman matrix — the "does demand line up with pricing" map.

Part 2 — provider elasticity to demand (the hazard, v0):
  model-day panel (~34 days × ~370 models): P(any endpoint reprices on day t)
  ~ lagged demand growth (Δlog tokens), demand level, model age, prior
  events. Logit, model-clustered. ~35 positive days — preliminary; HF/HN/
  devrel features enter as their daily panels lengthen (they started
  2026-07-08/09). This is E3's extensive margin with real demand data.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def demand_panel() -> pd.DataFrame:
    act = data.q(
        f"""
        select substr(cast(date as varchar), 1, 10) as day, model_permaslug,
               sum(total_prompt_tokens + total_completion_tokens) as toks,
               sum(request_count) as reqs
        from read_parquet('{data.table_glob("model_activity_daily")}')
        group by 1, 2
        """
    ).df()
    act = act.sort_values(["model_permaslug", "day"])
    act["dlog_toks"] = act.groupby("model_permaslug")["toks"].transform(
        lambda s: np.log(s.clip(lower=1)).diff()
    )
    return act


def event_days() -> pd.DataFrame:
    ev = data.q(
        f"""
        with panel as (
          select run_ts, model_id, provider_name, tag, endpoint_fingerprint, price_completion,
                 lag(price_completion) over (
                   partition by model_id, provider_name, tag, endpoint_fingerprint
                   order by run_ts) prev
          from read_parquet('{data.table_glob("endpoints_snapshots")}'))
        select distinct substr(run_ts, 1, 4) || '-' || substr(run_ts, 5, 2) || '-'
               || substr(run_ts, 7, 2) as day, model_id
        from panel where prev is not null and prev != price_completion
          and model_id not like '%:%'
        """
    ).df()
    slug = data.q(
        f"""select distinct canonical_slug, id from {data.models_snapshots()}
        where id not like '%:%'"""
    ).df()
    return ev.merge(slug, left_on="model_id", right_on="id")[["day", "canonical_slug"]].rename(
        columns={"canonical_slug": "model_permaslug"}
    )


def latest_features() -> pd.DataFrame:
    act = demand_panel()
    latest_day = sorted(act["day"].unique())[-2]  # last complete day
    a = act[act["day"] == latest_day][["model_permaslug", "toks"]]
    hf = data.q(
        f"""
        select model_permaslug, max(downloads_30d) as hf_downloads,
               max(trending_score) as hf_trending
        from read_parquet('{data.table_glob("hf_model_stats_daily")}')
        group by 1
        """
    ).df()
    try:
        hn = data.q(
            f"""
            select name, max(value) as hn_stories
            from read_parquet('{data.table_glob("devrel_daily")}')
            where source = 'hn' group by 1
            """
        ).df()
    except Exception:
        hn = pd.DataFrame(columns=["name", "hn_stories"])
    px = data.q(
        f"""
        select model_id, min(price_completion) as min_price,
               count(distinct provider_name) as n_providers,
               stddev(price_completion) / nullif(avg(price_completion), 0) as cv
        from {data.latest_endpoints()}
        where price_completion > 0 and model_id not like '%:free'
        group by 1
        """
    ).df()
    slug = data.q(
        f"""select distinct canonical_slug, id, created from {data.models_snapshots()}
        where run_ts = (select max(run_ts) from {data.models_snapshots()})
          and id not like '%:%'"""
    ).df()
    m = a.merge(slug, left_on="model_permaslug", right_on="canonical_slug")
    m = m.merge(px, left_on="id", right_on="model_id", how="left")
    m = m.merge(hf, on="model_permaslug", how="left")
    m["short"] = (
        m["model_permaslug"].str.split("/").str[-1].str.replace(r"-202[56].*", "", regex=True)
    )
    m = m.merge(hn, left_on="short", right_on="name", how="left")
    m["age_days"] = (pd.Timestamp.now().timestamp() - m["created"]) / 86400
    return m


def correlation_map(m: pd.DataFrame) -> dict:
    cols = {
        "log_tokens": np.log(m["toks"].clip(lower=1)),
        "log_hf_downloads": np.log(m["hf_downloads"].clip(lower=1)),
        "hf_trending": m["hf_trending"],
        "hn_stories": m["hn_stories"],
        "log_min_price": np.log(m["min_price"].clip(lower=1e-9)),
        "price_cv": m["cv"],
        "n_providers": m["n_providers"],
        "log_age_days": np.log(m["age_days"].clip(lower=0.1)),
    }
    df = pd.DataFrame(cols)
    corr = df.corr(method="spearman", min_periods=20).round(2)
    demand_cols = ["log_tokens", "log_hf_downloads", "hf_trending", "hn_stories"]
    price_cols = ["log_min_price", "price_cv", "n_providers", "log_age_days"]
    return {
        d: {p: (None if pd.isna(corr.loc[d, p]) else float(corr.loc[d, p])) for p in price_cols}
        for d in demand_cols
    }


def hazard(act: pd.DataFrame, ev: pd.DataFrame) -> dict:
    panel = act.dropna(subset=["dlog_toks"]).copy()
    panel = panel[panel["reqs"] >= 100]
    ev["repriced"] = 1
    panel = panel.merge(ev, on=["day", "model_permaslug"], how="left")
    panel["repriced"] = panel["repriced"].fillna(0)
    panel["dlog_toks_lag"] = panel.groupby("model_permaslug")["dlog_toks"].shift(1)
    panel["log_toks"] = np.log(panel["toks"].clip(lower=1))
    panel = panel.dropna(subset=["dlog_toks_lag"])
    n_pos = int(panel["repriced"].sum())
    if n_pos < 10:
        return {"gated": f"needs >=10 repricing model-days (have {n_pos})"}
    m = smf.logit("repriced ~ dlog_toks_lag + log_toks", data=panel).fit(disp=0)
    return {
        "n_model_days": int(len(panel)),
        "n_repricing_days": n_pos,
        "odds_ratio_demand_growth_lag1": round(float(np.exp(m.params["dlog_toks_lag"])), 2),
        "p_demand_growth": round(float(m.pvalues["dlog_toks_lag"]), 3),
        "odds_ratio_demand_level": round(float(np.exp(m.params["log_toks"])), 2),
        "p_demand_level": round(float(m.pvalues["log_toks"]), 4),
        "read": (
            "OR>1 on growth = providers reprice after demand surges (elastic to demand); "
            "level OR>1 = hot models reprice more (H17/H18 consistent). Preliminary n; "
            "HF/HN/devrel lags + utilization enter as their panels lengthen"
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    m = latest_features()
    save(m, out_dir, "h20_feature_panel")
    act = demand_panel()
    ev = event_days()
    results = {
        "demand_x_pricing_spearman": correlation_map(m),
        "reprice_hazard_v0": hazard(act, ev),
        "coverage": {
            "n_models": int(len(m)),
            "with_hf": int(m["hf_downloads"].notna().sum()),
            "with_hn": int(m["hn_stories"].notna().sum()),
        },
    }
    save_json(results, out_dir, "h20_summary")
    log.info("H20: %s", results)
    return results
