"""H31 — GPU marketplace supply response and utilization-price co-movement.

The model links the observed GPU rental market to the inference economics
stack.  It is deliberately a *supply-state* screen, not an instrumented causal
estimate: rented offer share and price can both respond to demand shocks.  The
screen becomes a causal pass-through input only after a pre-specified supply or
demand instrument is added to the panel.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

MIN_SPAN_HOURS = 7 * 24
MIN_DIFFERENCED_OBSERVATIONS = 100
MIN_GPU_CLASSES = 3
MAX_CONTIGUOUS_GAP_HOURS = 2.5
PANEL_COLUMNS = [
    "run_ts",
    "gpu_class",
    "offer_type",
    "n_offers",
    "rented_share",
    "median_usd_hr",
    "p25_usd_hr",
    "p75_usd_hr",
]
FIT_COLUMNS = [
    "term",
    "coefficient",
    "std_error",
    "p_value",
    "n_observations",
    "n_gpu_classes",
    "span_hours",
]


def _boolean(value: object) -> bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        if value.lower() in {"true", "1", "yes"}:
            return True
        if value.lower() in {"false", "0", "no"}:
            return False
        return None
    return bool(value)


def market_panel(offers: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a snapshot offer book to the GPU-class market state."""
    if offers.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    rows = offers.copy()
    rows["dph_total"] = pd.to_numeric(rows.get("dph_total"), errors="coerce")
    rows = rows[rows["dph_total"] > 0].copy()
    if rows.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    rows["rented_bool"] = rows.get("rented").map(_boolean)
    rows = rows.dropna(subset=["run_ts", "gpu_class", "offer_type", "rented_bool"])
    if rows.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    grouped = rows.groupby(["run_ts", "gpu_class", "offer_type"], as_index=False)
    panel = grouped.agg(
        n_offers=("dph_total", "size"),
        rented_share=("rented_bool", "mean"),
        median_usd_hr=("dph_total", "median"),
        p25_usd_hr=("dph_total", lambda x: x.quantile(0.25)),
        p75_usd_hr=("dph_total", lambda x: x.quantile(0.75)),
    )
    return panel.loc[:, PANEL_COLUMNS].sort_values(PANEL_COLUMNS[:3]).reset_index(drop=True)


def _differenced_panel(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel.assign(dlog_price=pd.Series(dtype="float64"))
    rows = panel.copy()
    rows["ts"] = pd.to_datetime(rows["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    rows = rows[(rows["offer_type"] == "on-demand") & (rows["median_usd_hr"] > 0)].copy()
    rows["rented_share_clipped"] = rows["rented_share"].clip(0.01, 0.99)
    rows = rows.sort_values(["gpu_class", "ts"])
    rows["elapsed_hours"] = rows.groupby("gpu_class")["ts"].diff().dt.total_seconds() / 3600
    rows["dlog_price"] = rows.groupby("gpu_class")["median_usd_hr"].transform(
        lambda x: np.log(x).diff()
    )
    rows["dlog_rented_share"] = rows.groupby("gpu_class")["rented_share_clipped"].transform(
        lambda x: np.log(x).diff()
    )
    return rows[
        (rows["elapsed_hours"] > 0) & (rows["elapsed_hours"] <= MAX_CONTIGUOUS_GAP_HOURS)
    ].dropna(subset=["dlog_price", "dlog_rented_share"]).copy()


def supply_response(panel: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Fit the registered first-difference supply-state regression when powered."""
    diff = _differenced_panel(panel)
    span_hours = 0.0
    if not panel.empty:
        ts = pd.to_datetime(panel["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
        span_hours = (ts.max() - ts.min()).total_seconds() / 3600 if len(ts) > 1 else 0.0
    n_classes = int(diff["gpu_class"].nunique()) if not diff.empty else 0
    gate = {
        "min_span_hours": MIN_SPAN_HOURS,
        "min_differenced_observations": MIN_DIFFERENCED_OBSERVATIONS,
        "min_gpu_classes": MIN_GPU_CLASSES,
        "max_contiguous_gap_hours": MAX_CONTIGUOUS_GAP_HOURS,
        "span_hours": round(span_hours, 2),
        "differenced_observations": int(len(diff)),
        "gpu_classes": n_classes,
    }
    gate["passed"] = bool(
        span_hours >= MIN_SPAN_HOURS
        and len(diff) >= MIN_DIFFERENCED_OBSERVATIONS
        and n_classes >= MIN_GPU_CLASSES
    )
    if not gate["passed"]:
        return {"gated": gate}, pd.DataFrame(columns=FIT_COLUMNS)
    fit = smf.ols("dlog_price ~ dlog_rented_share + C(gpu_class)", data=diff).fit(cov_type="HC1")
    results = pd.DataFrame(
        {
            "term": fit.params.index,
            "coefficient": fit.params.values,
            "std_error": fit.bse.values,
            "p_value": fit.pvalues.values,
            "n_observations": int(fit.nobs),
            "n_gpu_classes": n_classes,
            "span_hours": span_hours,
        }
    )
    coefficient = float(fit.params["dlog_rented_share"])
    return {
        "gate": gate,
        "rented_share_price_elasticity": coefficient,
        "standard_error": float(fit.bse["dlog_rented_share"]),
        "n_observations": int(fit.nobs),
        "n_gpu_classes": n_classes,
        "r_squared": float(fit.rsquared),
        "identification_boundary": (
            "First-difference association between rental price and rented-share state. "
            "It is not a causal supply elasticity without a declared exogenous instrument."
        ),
    }, results.loc[:, FIT_COLUMNS]


def load_offers() -> pd.DataFrame:
    try:
        return data.q(
            f"""
            select run_ts, gpu_class, offer_type, dph_total, rented
            from read_parquet('{data.table_glob("gpu_offers_snapshots")}')
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = market_panel(load_offers())
    summary, fit = supply_response(panel)
    save(panel, out_dir, "h31_gpu_market_panel")
    save(fit, out_dir, "h31_gpu_supply_response")
    result = {
        "market_panel_rows": int(len(panel)),
        "supply_response": summary,
        "claim_boundary": (
            "Vast.ai on-demand offer-book snapshots only. The rented flag is a marketplace "
            "state, not realized GPU-hours, and the uninstrumented response is descriptive."
        ),
    }
    save_json(result, out_dir, "h31_summary")
    return result
