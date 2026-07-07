"""H5 — Harnesses as front-ends/order flow: concentration and multihoming.

  h5_concentration   HHI + Zipf (rank-size) slope of app token shares, global
                     and per-model
  h5_multihoming     apps appearing in top-N of many models (bipartite overlap)

Comparators: CoW solver win-share HHI + DEX front-end shares (BigQuery,
defi_benchmarks); winner-take-all front-end dynamics predict HHI in the
1500-4000 range with Zipf slope near -1.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_apps() -> pd.DataFrame:
    return data.q(
        f"""
        with latest as (select max(dt) m from {data.apps()})
        select * from {data.apps()}, latest where dt = latest.m
        """
    ).df()


def hhi(shares: np.ndarray) -> float:
    s = shares / shares.sum()
    return float((s**2).sum() * 10_000)


def zipf_slope(tokens: np.ndarray) -> dict:
    t = np.sort(tokens[tokens > 0])[::-1]
    if len(t) < 5:
        return {"n": int(len(t)), "slope": None}
    d = pd.DataFrame({"log_rank": np.log(np.arange(1, len(t) + 1)), "log_size": np.log(t)})
    m = smf.ols("log_size ~ log_rank", data=d).fit()
    return {"n": int(len(t)), "slope": float(m.params["log_rank"]), "r2": float(m.rsquared)}


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_apps()
    glob = df[(df["scope"] == "global") & (df["section"] == "popular")].copy()
    per_model = df[df["scope"] == "model"].copy()

    results: dict = {}
    if len(glob):
        tokens = glob["total_tokens"].astype(float).to_numpy()
        results["global"] = {
            "n_apps": int(len(glob)),
            "hhi": hhi(tokens),
            "top1_share": float(tokens.max() / tokens.sum()),
            "top3_share": float(np.sort(tokens)[::-1][:3].sum() / tokens.sum()),
            "zipf": zipf_slope(tokens),
        }

    if len(per_model):
        pm = (
            per_model.groupby("model_permaslug")
            .apply(
                lambda g: hhi(g["total_tokens"].astype(float).to_numpy()),
                include_groups=False,
            )
            .rename("hhi")
            .reset_index()
        )
        save(pm, out_dir, "h5_per_model_hhi")
        results["per_model"] = {
            "n_models": int(len(pm)),
            "median_hhi": float(pm["hhi"].median()),
            "p90_hhi": float(pm["hhi"].quantile(0.9)),
        }
        # multihoming: how many models' top lists does each app appear in?
        mh = per_model.groupby("app_slug")["model_permaslug"].nunique().rename("n_models")
        results["multihoming"] = {
            "n_apps_in_any_top_list": int(len(mh)),
            "median_models_per_app": float(mh.median()),
            "max_models_per_app": int(mh.max()),
        }
        save(mh.reset_index(), out_dir, "h5_multihoming")

    save(df, out_dir, "h5_apps_snapshot")
    save_json(results, out_dir, "h5_summary")
    log.info("H5: %s", results)
    return results
