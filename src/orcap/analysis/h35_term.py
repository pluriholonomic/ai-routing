"""H35 — Spot vs forward: the compute term structure.

Legs assembled from heterogeneous sources (each labeled):
  spot            vast.ai H100 SXM on-demand median (ours, hourly)
  interruptible   vast.ai bid median (spot-with-interruption-risk)
  short tenors    vast.ai offers bucketed by max rental duration (ours)
  1y forward      cited anchors (data-static/gpu_forward_anchors.csv —
                  SemiAnalysis public 1-yr contract points); Compute Desk /
                  SemiAnalysis full curves (3m-5y) drop into the same CSV if
                  subscribed; Architect AIX futures quotes when the DCM goes
                  live.
  spot history    Silicon Data segment medians (gpu_index_periods.csv)

Outputs implied annualized carry ln(F/S)/tenor and the contango/backwardation
verdict, historically and now. Runs nightly; the curve sharpens as anchor
sources are added.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

ANCHORS = Path("data-static/gpu_forward_anchors.csv")
SPOT_HIST = Path("data-static/gpu_index_periods.csv")

TENOR_YEARS = {"1m": 1 / 12, "3m": 0.25, "6m": 0.5, "1y": 1.0, "2y": 2.0, "3y": 3.0}


def current_spot(gpu_class: str = "H100 SXM") -> dict:
    row = data.q(
        f"""
        with latest as (select max(run_ts) m from read_parquet('{data.table_glob("gpu_offers_snapshots")}'))
        select median(dph_total) filter (where offer_type = 'on-demand') as ondemand,
               median(dph_total) filter (where offer_type = 'bid') as bid
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}'), latest
        where run_ts = latest.m and gpu_class = '{gpu_class}' and num_gpus = 1
        """
    ).fetchone()
    return {
        "spot_ondemand": float(row[0]) if row[0] else None,
        "spot_interruptible": float(row[1]) if row[1] else None,
    }


def vast_duration_curve(gpu_class: str = "H100 SXM") -> list[dict]:
    rows = data.q(
        f"""
        with latest as (select max(run_ts) m from read_parquet('{data.table_glob("gpu_offers_snapshots")}'))
        select case when duration < 86400*7 then '<1w'
                    when duration < 86400*30 then '1w-1mo'
                    when duration < 86400*90 then '1-3mo'
                    else '3mo+' end as bucket,
               median(dph_total) as usd_hr, count(*) as n
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}'), latest
        where run_ts = latest.m and gpu_class = '{gpu_class}'
          and offer_type = 'on-demand' and num_gpus = 1 and duration is not null
        group by 1 order by min(duration)
        """
    ).df()
    return rows.round(3).to_dict("records")


def carry_history() -> list[dict]:
    """Historical contango/backwardation: forward anchors vs nearest spot."""
    if not ANCHORS.exists() or not SPOT_HIST.exists():
        return []
    fwd = pd.read_csv(ANCHORS, parse_dates=["obs_date"])
    spot = pd.read_csv(SPOT_HIST, parse_dates=["period_start", "period_end"])
    spot = spot[spot["segment"] == "marketplace"]
    out = []
    for r in fwd.itertuples(index=False):
        near = spot[(spot["period_start"] <= r.obs_date) & (spot["period_end"] >= r.obs_date)]
        if near.empty:
            deltas = (spot["period_start"] - r.obs_date).abs()
            near = spot.loc[[deltas.idxmin()]]
        s = float(near["usd_hr"].iloc[0])
        tenor_y = TENOR_YEARS.get(r.tenor, 1.0)
        out.append(
            {
                "obs_date": str(r.obs_date)[:10],
                "gpu_class": r.gpu_class,
                "tenor": r.tenor,
                "forward": float(r.usd_hr),
                "spot_marketplace": s,
                "carry_annualized_pct": round(100 * np.log(r.usd_hr / s) / tenor_y, 1),
                "regime": "contango" if r.usd_hr > s else "backwardation",
            }
        )
    return out


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    spot = current_spot()
    hist = carry_history()
    curve = vast_duration_curve()
    latest_fwd = hist[-1] if hist else None
    results: dict = {
        "current_spot": spot,
        "vast_duration_curve": curve,
        "carry_history": hist,
    }
    if latest_fwd and spot.get("spot_ondemand"):
        f = latest_fwd["forward"]
        s = spot["spot_ondemand"]
        results["current_vs_latest_anchor"] = {
            "forward_1y": f,
            "spot_now": s,
            "carry_annualized_pct": round(100 * np.log(f / s), 1),
            "regime": "contango" if f > s else "backwardation",
            "caveat": "forward anchor and spot are different venues/segments; "
            "directional only until a same-venue curve (Compute Desk / AIX) is added",
        }
    save(pd.DataFrame(hist), out_dir, "h35_carry_history")
    save_json(results, out_dir, "h35_summary")
    log.info("H35: %s", results.get("current_vs_latest_anchor"))
    return results
