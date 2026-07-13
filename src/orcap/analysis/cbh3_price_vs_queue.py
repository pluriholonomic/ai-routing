"""CBH-3 (was H72) — Does price or the queue absorb demand shocks? (+ diurnal RM test)

Uber's NYE-2015 surge outage showed what happens when price cannot clear:
completion collapses and waiting rations. Electricity retail and post-2017
AWS spot show the steady-state version: administered posted prices, quantity
rationing clears. Compute Brokerage invariant (ii): demand shocks load onto
queues (rate-limits, latency) at all horizons under ~1 month; posted prices
load ~0. Revenue-management prediction P2 baseline: prices load ~0 on diurnal
harmonics while congestion loads fully (the pre-RM airline regime).

Data: congestion_intraday (5-min, hot-model panel): price_completion,
request_count_30m, rate_limited_30m, p90_latency_ms per endpoint.

  h72_summary.json   shock loadings by horizon + diurnal variance shares
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

HORIZONS = {"30min": 6, "3h": 36, "1d": 288}  # in 5-min ticks (panel cadence)


def panel() -> pd.DataFrame:
    df = data.q(
        f"""
        select run_ts, model_permaslug, endpoint_uuid,
               try_cast(price_completion as double) as price,
               try_cast(request_count_30m as double) as requests,
               try_cast(rate_limited_30m as double) as rate_limited,
               try_cast(p90_latency_ms as double) as p90_latency
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where request_count_30m is not null
        """
    ).df()
    df["ts"] = pd.to_datetime(df["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    return df


def _r2(y: np.ndarray, x: np.ndarray) -> float | None:
    m = ~(np.isnan(y) | np.isnan(x))
    # near-constant outcomes (a price that never moved) produce numerically
    # spurious correlations; require genuine variation in both series
    if m.sum() < 50 or len(np.unique(y[m])) < 6 or len(np.unique(x[m])) < 6:
        return None
    if np.var(y[m]) < 1e-12 * (np.nanmean(np.abs(y[m])) ** 2 + 1e-12):
        return None
    r = np.corrcoef(y[m], x[m])[0, 1]
    return float(r * r)


def shock_loadings(df: pd.DataFrame) -> dict:
    """Per endpoint: R^2 of Δoutcome on model-level demand innovation, by horizon."""
    # model-level demand: sum of requests across endpoints per tick
    demand = df.groupby(["model_permaslug", "ts"])["requests"].sum().rename("model_requests")
    df = df.join(demand, on=["model_permaslug", "ts"])
    out: dict[str, dict[str, list[float]]] = {
        h: {"price": [], "rate_limited": [], "p90_latency": []} for h in HORIZONS
    }
    for _, g in df.groupby("endpoint_uuid"):
        g = g.sort_values("ts").drop_duplicates("ts")
        if len(g) < 200:
            continue
        for label, k in HORIZONS.items():
            shock = g["model_requests"].diff(k).to_numpy()
            for col in ("price", "rate_limited", "p90_latency"):
                r2 = _r2(g[col].diff(k).to_numpy(), shock)
                if r2 is not None:
                    out[label][col].append(r2)
    return {
        h: {col: (float(np.median(v)) if v else None) for col, v in cols.items()}
        for h, cols in out.items()
    }


def diurnal_shares(df: pd.DataFrame) -> dict:
    """Share of within-endpoint variance explained by hour-of-day harmonics."""
    res: dict[str, list[float]] = {"price": [], "rate_limited": [], "p90_latency": []}
    for _, g in df.groupby("endpoint_uuid"):
        g = g.sort_values("ts").drop_duplicates("ts")
        if len(g) < 400:
            continue
        hod = g["ts"].dt.hour + g["ts"].dt.minute / 60.0
        X = np.column_stack(
            [np.sin(2 * np.pi * hod / 24), np.cos(2 * np.pi * hod / 24),
             np.sin(4 * np.pi * hod / 24), np.cos(4 * np.pi * hod / 24),
             np.ones(len(g))]
        )
        for col in res:
            y = g[col].to_numpy(dtype=float)
            m = ~np.isnan(y)
            if m.sum() < 300 or len(np.unique(y[m])) < 6:
                continue
            if np.var(y[m]) < 1e-12 * (np.nanmean(np.abs(y[m])) ** 2 + 1e-12):
                continue
            beta, *_ = np.linalg.lstsq(X[m], y[m], rcond=None)
            fit = X[m] @ beta
            res[col].append(float(1 - np.var(y[m] - fit) / np.var(y[m])))
    return {col: (float(np.median(v)) if v else None) for col, v in res.items()}


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = panel()
    n_days = df["ts"].dt.date.nunique() if not df.empty else 0
    if df.empty or n_days < 3:
        summary = {"evidence_status": "power_gated", "gate": f"only {n_days}/3 panel days"}
        save_json(summary, out_dir, "cbh3_summary")
        return summary
    # the bluntest version of the invariant: how many endpoints ever moved price
    # vs ever moved congestion state, over the same window
    moved = df.groupby("endpoint_uuid").agg(
        price_moved=("price", lambda s: s.dropna().nunique() > 1),
        rl_moved=("rate_limited", lambda s: s.dropna().nunique() > 1),
        lat_moved=("p90_latency", lambda s: s.dropna().nunique() > 1),
    )
    loadings = shock_loadings(df)
    diurnal = diurnal_shares(df)
    # headline ratio: queue loading / price loading at 1d
    d1 = loadings.get("1d", {})
    ratio = None
    if d1.get("rate_limited") and d1.get("price"):
        ratio = d1["rate_limited"] / max(d1["price"], 1e-6)
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_endpoints": int(df["endpoint_uuid"].nunique()),
        "n_days": int(n_days),
        "share_endpoints_price_ever_moved": float(moved["price_moved"].mean()),
        "share_endpoints_rate_limit_ever_moved": float(moved["rl_moved"].mean()),
        "share_endpoints_latency_ever_moved": float(moved["lat_moved"].mean()),
        "shock_r2_median_by_horizon": loadings,
        "diurnal_variance_share_median": diurnal,
        "queue_over_price_loading_1d": ratio,
        "prediction": (
            "invariant (ii): price R2 ~ 0 at <=1d while rate-limit/latency carry the "
            "shock; P2 baseline: diurnal share ~0 for price, positive for congestion"
        ),
        "claim_boundary": (
            "Hot-model panel only; request_count_30m is a rolling window (attenuates "
            "high-frequency loadings toward zero for ALL outcomes, so the ratio, not "
            "the level, is the statistic). Demand innovations are not exogenous shocks. "
            "Loadings/diurnal shares for price are conditional on the small subset of "
            "endpoints whose price moved at all — read them jointly with the "
            "ever-moved shares."
        ),
    }
    save_json(summary, out_dir, "cbh3_summary")
    return summary
