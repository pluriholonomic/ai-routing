"""CBH-1 (was H70) — Algorithmic-repricer census and the both-adopt margin test (Assad).

Assad et al. (JPE 2024, German retail gasoline): algorithmic-pricing adoption
detected via markers (repricing frequency, response speed); margins rose +28%
in duopolies where BOTH stations adopted, ~0 where only one did. The
interaction sign separates algorithmic collusion (margins rise with
saturation) from commoditization (margins fall with adoption everywhere).

Adoption markers here (v0, short panel — census is preliminary):
  fast repricer = >=2 completion-price changes in the live window OR >=1
  change responding to a rival on the same model within 48h.

Margin proxy (levels overstated, ordering informative — same caveat as H3):
  markup = price_completion / (H100 $/hr / (throughput tok/s * 3600))

  h70_census.parquet   per-provider markers + class
  h70_summary.json     census + saturation-margin regression
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def h100_usd_hr() -> float:
    df = data.q(
        f"""
        select median(try_cast(dph_base as double) / greatest(num_gpus, 1)) as p
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}', union_by_name=true)
        where gpu_name like '%H100%' and offer_type = 'on-demand' and rentable
        """
    ).df()
    v = float(df["p"].iloc[0]) if not df.empty and pd.notna(df["p"].iloc[0]) else 2.0
    return v


def census() -> pd.DataFrame:
    ch = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and model_id not like '%:%'
        """
    ).df()
    ch["ts"] = pd.to_datetime(ch["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    universe = data.q(
        f"""
        select distinct provider_name
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where price_completion > 0 and model_id not like '%:%'
        """
    ).df()["provider_name"]
    rows = [
        {
            "provider_name": p,
            "n_changes": 0,
            "n_models_changed": 0,
            "n_reactive_48h": 0,
            "algorithmic": False,
        }
        for p in universe
        if p not in set(ch["provider_name"])
    ]
    for prov, g in ch.groupby("provider_name"):
        reactive = 0
        for _, e in g.iterrows():
            rivals = ch[
                (ch["model_id"] == e["model_id"])
                & (ch["provider_name"] != prov)
                & (ch["ts"] < e["ts"])
                & (ch["ts"] >= e["ts"] - pd.Timedelta(hours=48))
            ]
            reactive += int(len(rivals) > 0)
        rows.append(
            {
                "provider_name": prov,
                "n_changes": int(len(g)),
                "n_models_changed": int(g["model_id"].nunique()),
                "n_reactive_48h": reactive,
                "algorithmic": bool(len(g) >= 2 or reactive >= 1),
            }
        )
    return pd.DataFrame(rows)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    cen = census()
    if cen.empty:
        summary = {"evidence_status": "power_gated", "gate": "no repricing events"}
        save_json(summary, out_dir, "cbh1_summary")
        return summary
    save(cen, out_dir, "cbh1_census")
    algo = set(cen[cen["algorithmic"]]["provider_name"])

    gpu = h100_usd_hr()
    # throughput lives only in the hot-model congestion panel; markup test is
    # therefore restricted to the top-volume markets
    ep = data.q(
        f"""
        select model_permaslug as model_id, provider_name,
               median(try_cast(price_completion as double)) as price,
               median(try_cast(p50_throughput as double)) as tps
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where try_cast(price_completion as double) > 0 and p50_throughput is not null
        group by 1, 2
        """
    ).df()
    ep = ep[ep["tps"] > 1]
    ep["cost_per_token"] = gpu / (ep["tps"] * 3600.0)
    ep["log_markup"] = np.log(ep["price"] / ep["cost_per_token"])
    ep["algo"] = ep["provider_name"].isin(algo)

    market = (
        ep.groupby("model_id")
        .agg(
            n_providers=("provider_name", "nunique"),
            n_algo=("algo", "sum"),
            median_log_markup=("log_markup", "median"),
        )
        .reset_index()
    )
    market = market[market["n_providers"] >= 2]
    market["saturation"] = np.where(
        market["n_algo"] == 0, "none",
        np.where(market["n_algo"] < market["n_providers"], "mixed", "all"),
    )
    by_sat = market.groupby("saturation")["median_log_markup"].agg(["median", "count"])
    # rank regression: markup on algo share, controlling provider count
    market["algo_share"] = market["n_algo"] / market["n_providers"]
    x = market[["algo_share", "n_providers"]].rank()
    y = market["median_log_markup"].rank()
    X = np.column_stack([x["algo_share"], x["n_providers"], np.ones(len(x))])
    beta, *_ = np.linalg.lstsq(X, y.to_numpy(), rcond=None)

    summary = {
        "evidence_status": "power_gated",
        "gate": (
            "census window ~6 days: 'algorithmic' means recently-active repricer, not "
            "verified automation; Assad-style structural-break detection needs months"
        ),
        "n_providers_scored": int(len(cen)),
        "n_algorithmic_v0": int(len(algo)),
        "most_active": cen.sort_values("n_changes", ascending=False)
        .head(8)[["provider_name", "n_changes", "n_models_changed", "n_reactive_48h"]]
        .to_dict("records"),
        "h100_usd_hr_used": gpu,
        "markup_by_saturation": {
            k: {"median_log_markup": round(float(v["median"]), 3), "n_markets": int(v["count"])}
            for k, v in by_sat.iterrows()
        },
        "rank_beta_algo_share_on_markup": round(float(beta[0]), 4),
        "prediction_q2": (
            "Assad: markup HIGHER where all major quoters are algorithmic; "
            "commoditization: markup falls with adoption everywhere"
        ),
        "claim_boundary": (
            "Markup levels are overstated (single-stream GPU cost bound; batching "
            "economies ignored) — only the ordering across saturation classes is "
            "informative. Preliminary census; re-run as the panel lengthens."
        ),
    }
    save_json(summary, out_dir, "cbh1_summary")
    return summary
