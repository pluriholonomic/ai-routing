"""WF-3 — Calibrated-regret screen (Hartline et al. 2024-25), v1.

A competitive (best-responding) pricing algorithm exhibits LOW regret against
the realized rival path; sustaining supra-competitive prices via reactive
threats requires sacrificing short-run best response = HIGH regret. v1
implementation: for each provider x hot model, compare realized margin under
the actual price path against the best CONSTANT price chosen from the
provider's own tried levels, with the router's documented inverse-square rule
as the share model and a GPU-throughput cost proxy.

  regret_pct = [max_p sum_t (p - c) s(p, rivals_t) - sum_t (p_t - c) s(p_t, rivals_t)]
               / |sum_t (p_t - c) s(p_t, rivals_t)|

  wf3_regret.parquet, wf3_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def hot_panel() -> pd.DataFrame:
    df = data.q(
        f"""
        select model_permaslug as model, provider_name, substr(run_ts,1,8) as day8,
               median(try_cast(price_completion as double)) as price,
               median(try_cast(p50_throughput as double)) as tps
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where try_cast(price_completion as double) > 0
        group by 1, 2, 3
        """
    ).df()
    return df


def h100_usd_hr() -> float:
    df = data.q(
        f"""
        select median(try_cast(dph_base as double)/greatest(num_gpus,1)) as p
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}', union_by_name=true)
        where gpu_name like '%H100%' and offer_type = 'on-demand' and rentable
        """
    ).df()
    return float(df["p"].iloc[0]) if pd.notna(df["p"].iloc[0]) else 2.0


def inv_sq_share(p_own: float, rival_prices: np.ndarray) -> float:
    w = p_own ** -2
    return float(w / (w + (rival_prices ** -2.0).sum()))


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = hot_panel()
    gpu = h100_usd_hr()
    tps = panel.groupby(["model", "provider_name"])["tps"].median()
    algo = set(
        data.q(
            f"""
            select distinct provider_name
            from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
            where field = 'price_completion'
            """
        ).df()["provider_name"]
    )
    rows = []
    for (model, prov), g in panel.groupby(["model", "provider_name"]):
        g = g.sort_values("day8")
        if len(g) < 6 or g["price"].nunique() < 1:
            continue
        t = tps.get((model, prov), np.nan)
        if not np.isfinite(t) or t <= 1:
            continue
        c = gpu / (t * 3600.0)
        days = g["day8"].tolist()
        rivals_by_day = {}
        for d in days:
            r = panel[(panel["model"] == model) & (panel["day8"] == d) & (panel["provider_name"] != prov)]
            if len(r) >= 1:
                rivals_by_day[d] = r["price"].to_numpy()
        days = [d for d in days if d in rivals_by_day]
        if len(days) < 6:
            continue
        actual = sum(
            (p - c) * inv_sq_share(p, rivals_by_day[d])
            for p, d in zip(g.set_index("day8").loc[days, "price"], days)
        )
        tried = sorted(set(g["price"]))
        best = max(
            sum((p - c) * inv_sq_share(p, rivals_by_day[d]) for d in days) for p in tried
        )
        if abs(actual) < 1e-15:
            continue
        rows.append(
            {
                "model": model,
                "provider": prov,
                "n_days": len(days),
                "n_tried_prices": len(tried),
                "margin_positive": bool(actual > 0),
                "regret_pct": float(100.0 * (best - actual) / abs(actual)),
                "algo": prov in algo,
            }
        )
    df = pd.DataFrame(rows)
    if len(df) < 30:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(df)}/30 provider-model cells"}
        save_json(summary, out_dir, "wf3_summary")
        return summary
    save(df, out_dir, "wf3_regret")
    movers = df[df["n_tried_prices"] >= 2]
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_cells": int(len(df)),
        "n_cells_with_price_moves": int(len(movers)),
        "median_regret_pct_movers": round(float(movers["regret_pct"].median()), 2)
        if len(movers)
        else None,
        "p90_regret_pct_movers": round(float(movers["regret_pct"].quantile(0.9)), 2)
        if len(movers)
        else None,
        "median_regret_algo_vs_not": {
            "algo": round(float(movers[movers["algo"]]["regret_pct"].median()), 2)
            if len(movers[movers["algo"]])
            else None,
            "non_algo": round(float(movers[~movers["algo"]]["regret_pct"].median()), 2)
            if len(movers[~movers["algo"]])
            else None,
        },
        "read": (
            "high regret among movers = price paths sacrifice short-run best response "
            "(consistent with reactive-threat conduct); low regret = near-best-response "
            "competitive algorithms. Static (non-moving) cells have zero regret by "
            "construction and are silent — the ABS rigidity story lives outside this test"
        ),
        "claim_boundary": (
            "v1: inverse-square share model (documented default, not audited weights), "
            "single-GPU cost proxy, best-in-own-menu comparator (not global). "
            "Caveat: threat-free algorithmic collusion evades regret screens entirely."
        ),
    }
    save_json(summary, out_dir, "wf3_summary")
    return summary
