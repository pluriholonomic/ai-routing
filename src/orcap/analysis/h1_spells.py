"""H1 — Price-formation regime: posted prices with lumpy adjustment, or
continuous repricing?

Data: Wayback model-level snapshots (2023-07 → now, irregular sampling) plus
current models_snapshots. For each model we observe listed completion price at
snapshot times; between consecutive observations we record whether the price
changed and the exposure time. Outputs:

  h1_change_events   one row per consecutive observation pair (gap days,
                     changed flag, log price ratio)
  h1_summary         repricing rate (changes per model-month), change-size
                     distribution stats (median |Δlog p|, share of changes
                     >10%, tail behavior)

Comparators (computed in defi_benchmarks / cited): EIP-1559 base fee changes
~every block (continuous), AMM returns diffusive, menu-cost retail lumpy.
A low repricing hazard + fat lumpy change sizes = posted-price/menu-cost
regime — structurally unlike AMMs regardless of the surface analogy.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_price_panel() -> pd.DataFrame:
    """Model-level listed completion price at each wayback snapshot + latest live."""
    wb = data.q(
        f"""
        select id as model_id, run_ts, price_completion
        from {data.wayback_models()}
        where price_completion is not null and price_completion > 0
        """
    ).df()
    live = data.q(
        f"""
        with latest as (select max(run_ts) m from {data.models_snapshots()})
        select id as model_id, run_ts, price_completion
        from {data.models_snapshots()}, latest
        where run_ts = latest.m and price_completion is not null and price_completion > 0
        """
    ).df()
    panel = pd.concat([wb, live], ignore_index=True)
    panel["ts"] = pd.to_datetime(panel["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    return panel.sort_values(["model_id", "ts"])


def change_events(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model_id, g in panel.groupby("model_id"):
        g = g.drop_duplicates(subset="ts").sort_values("ts")
        if len(g) < 2:
            continue
        p = g["price_completion"].to_numpy()
        t = g["ts"].to_numpy()
        for i in range(1, len(g)):
            gap_days = (t[i] - t[i - 1]) / np.timedelta64(1, "D")
            rows.append(
                {
                    "model_id": model_id,
                    "ts_from": t[i - 1],
                    "ts_to": t[i],
                    "gap_days": float(gap_days),
                    "changed": bool(p[i] != p[i - 1]),
                    "dlog_price": float(np.log(p[i] / p[i - 1])),
                }
            )
    return pd.DataFrame(rows)


def summarize(events: pd.DataFrame) -> dict:
    if events.empty:
        return {"n_pairs": 0}
    changes = events[events["changed"]]
    exposure_months = events["gap_days"].sum() / 30.44
    abs_dlog = changes["dlog_price"].abs()
    return {
        "n_models": int(events["model_id"].nunique()),
        "n_pairs": int(len(events)),
        "n_changes": int(len(changes)),
        "share_pairs_changed": float(events["changed"].mean()),
        "median_gap_days": float(events["gap_days"].median()),
        "repricing_rate_per_model_month": float(len(changes) / exposure_months)
        if exposure_months
        else None,
        "median_abs_dlog": float(abs_dlog.median()) if len(changes) else None,
        "share_changes_gt_10pct": float((abs_dlog > np.log(1.10)).mean()) if len(changes) else None,
        "share_changes_gt_25pct": float((abs_dlog > np.log(1.25)).mean()) if len(changes) else None,
        "share_price_cuts": float((changes["dlog_price"] < 0).mean()) if len(changes) else None,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = load_price_panel()
    events = change_events(panel)
    summary = summarize(events)
    save(events, out_dir, "h1_change_events")
    save_json(summary, out_dir, "h1_summary")
    log.info("H1: %s", summary)
    return summary
