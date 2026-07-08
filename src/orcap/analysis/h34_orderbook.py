"""H34 — The inference order book: an ask-only LOB per model.

Construction (model m, day t; 5-min for hot-40 via congestion_intraday later):
  - Each provider endpoint = a limit SELL at price p (completion $/tok) with
    size = remaining capacity (capacity_ceiling_rpm − recent_peak_rpm, floored
    at 10% of ceiling) converted to tokens/min via the model's mean
    completion tokens per request that day.
  - Demand = the model's tokens/min from activity (market-order flow rate).
  - Quotes with 1-day reject rate > 20% are flagged non-executable and
    excluded from the executable book (last-look adjustment).

Metrics per model-day:
  best_ask, top_gap (p2/p1 − 1), executable_best (reject-adjusted),
  depth_at_best, cumulative depth within 10% / 25% of best (tokens/min),
  book_pressure = demand / depth_within_25pct,
  impact_2x = marginal price to absorb 2× current demand ÷ best ask
  effective_spread = volume-weighted paid price ÷ best ask − 1

Uses: book pressure is the demand-state covariate for the repricing hazard
(H20); top-gap dynamics are the spread series (wars = spread compression);
λ(D) is the AMM-slippage comparator.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_asks() -> pd.DataFrame:
    rows = data.q(
        f"""
        select cast(dt as varchar) as day, model_permaslug, variant,
               provider_display_name as provider, record_json
        from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        where variant = 'standard'
        """
    ).df()
    recs = []
    for r in rows.itertuples(index=False):
        d = json.loads(r.record_json)
        pricing = d.get("pricing") or {}
        f = d.get("fortuna") or {}
        sh = d.get("status_heuristics_1d") or {}
        tot = sum(v or 0 for v in sh.values())
        try:
            p = float(pricing.get("completion"))
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        ceil = f.get("capacity_ceiling_rpm")
        peak = f.get("recent_peak_rpm") or 0
        if not ceil or ceil <= 0:
            continue
        recs.append(
            {
                "day": r.day,
                "model_permaslug": r.model_permaslug,
                "provider": r.provider,
                "price": p,
                "ceiling_rpm": float(ceil),
                "free_rpm": float(max(0.1 * ceil, ceil - peak)),
                "reject_1d": ((sh.get("rateLimited") or 0) + (sh.get("derankableError") or 0)) / tot
                if tot >= 100
                else 0.0,
            }
        )
    return pd.DataFrame(recs)


def load_demand() -> pd.DataFrame:
    d = data.q(
        f"""
        select substr(cast(date as varchar), 1, 10) as day, model_permaslug,
               sum(total_completion_tokens) comp_toks, sum(request_count) reqs
        from read_parquet('{data.table_glob("model_activity_daily")}')
        where variant = 'standard' group by 1, 2
        """
    ).df()
    d["toks_per_req"] = d["comp_toks"] / d["reqs"].clip(lower=1)
    d["demand_tokmin"] = d["comp_toks"] / 1440
    return d


def book_metrics(asks: pd.DataFrame, dem: pd.DataFrame) -> pd.DataFrame:
    m = asks.merge(dem, on=["day", "model_permaslug"])
    out = []
    for (day, model), g in m.groupby(["day", "model_permaslug"]):
        g = g.sort_values("price")
        if len(g) < 2 or g["demand_tokmin"].iat[0] <= 0:
            continue
        tpr = g["toks_per_req"].iat[0]
        g = g.assign(depth_tokmin=g["free_rpm"] * tpr)
        exe = g[g["reject_1d"] <= 0.20]
        best, second = g["price"].iat[0], g["price"].iat[1]
        demand = g["demand_tokmin"].iat[0]

        def within(frac: float, g=g, best=best) -> float:
            return float(g.loc[g["price"] <= best * (1 + frac), "depth_tokmin"].sum())

        # walk the book to absorb k x demand
        def impact(k: float, g=g, demand=demand, best=best) -> float | None:
            need = demand * k
            cum = 0.0
            for r in g.itertuples(index=False):
                cum += r.depth_tokmin
                if cum >= need:
                    return r.price / best
            return None  # book exhausted

        out.append(
            {
                "day": day,
                "model_permaslug": model,
                "n_asks": int(len(g)),
                "best_ask": best,
                "top_gap": second / best - 1,
                "executable_best": float(exe["price"].min()) if len(exe) else np.nan,
                "depth_at_best_tokmin": float(g["depth_tokmin"].iat[0]),
                "depth_10pct": within(0.10),
                "depth_25pct": within(0.25),
                "demand_tokmin": demand,
                "book_pressure": demand / max(1e-9, within(0.25)),
                "impact_2x": impact(2.0),
                "book_exhaust_multiple": next(
                    (k for k in (1, 2, 5, 10, 25) if impact(float(k)) is None), np.inf
                ),
            }
        )
    return pd.DataFrame(out)


def effective_spread(bm: pd.DataFrame) -> pd.DataFrame:
    eff = data.q(
        f"""
        select cast(dt as varchar) as day, model_permaslug,
               sum(effective_output_price * total_tokens) / sum(total_tokens) as paid_per_mtok
        from read_parquet('{data.table_glob("effective_pricing_daily")}')
        where variant = 'standard' and total_tokens > 0 and effective_output_price > 0
        group by 1, 2
        """
    ).df()
    bm = bm.merge(eff, on=["day", "model_permaslug"], how="left")
    bm["effective_spread"] = bm["paid_per_mtok"] / (bm["best_ask"] * 1e6) - 1
    return bm


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    asks = load_asks()
    bm = book_metrics(asks, load_demand())
    bm = effective_spread(bm)
    save(bm, out_dir, "h34_book_metrics")
    if bm.empty:
        return {"note": "no book days yet"}
    latest = bm[bm["day"] == bm["day"].max()]
    hot = latest.nlargest(1, "demand_tokmin")
    results = {
        "n_model_days": int(len(bm)),
        "n_models_latest": int(len(latest)),
        "median_top_gap_pct": float(latest["top_gap"].median() * 100),
        "median_book_pressure": float(latest["book_pressure"].median()),
        "share_books_pressure_gt_1": float((latest["book_pressure"] > 1).mean()),
        "median_impact_2x": float(latest["impact_2x"].dropna().median())
        if latest["impact_2x"].notna().any()
        else None,
        "median_effective_spread_pct": float(latest["effective_spread"].dropna().median() * 100)
        if latest["effective_spread"].notna().any()
        else None,
        "largest_book": {
            "model": hot["model_permaslug"].iat[0],
            "best_ask_per_mtok": round(float(hot["best_ask"].iat[0]) * 1e6, 3),
            "top_gap_pct": round(float(hot["top_gap"].iat[0]) * 100, 2),
            "book_pressure": round(float(hot["book_pressure"].iat[0]), 3),
            "impact_2x": round(float(hot["impact_2x"].iat[0]), 3)
            if pd.notna(hot["impact_2x"].iat[0])
            else None,
        }
        if len(hot)
        else None,
    }
    save_json(results, out_dir, "h34_summary")
    log.info("H34: %s", results)
    return results
