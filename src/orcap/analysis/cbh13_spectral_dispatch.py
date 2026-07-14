"""CBH-13 — Spectral dispatch test: does routing leave a clock signature?

A dispatch system that re-ranks providers on a fixed cycle leaves periodicity
in provider request-share series at the re-rank interval; a continuous
quote-driven market or per-request randomization leaves none beyond the
diurnal cycle. Detect via periodogram of within-model share series,
excluding diurnal harmonics (>= 12h periods).

  cbh13_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

TICK_MIN = 5.0
MIN_TICKS = 500


def share_series() -> pd.DataFrame:
    df = data.q(
        f"""
        select run_ts, model_permaslug, endpoint_uuid,
               try_cast(request_count_30m as double) as requests
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where request_count_30m is not null
        """
    ).df()
    df["ts"] = pd.to_datetime(df["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    tot = df.groupby(["model_permaslug", "ts"])["requests"].transform("sum")
    df["share"] = np.where(tot > 0, df["requests"] / tot, np.nan)
    return df


def dominant_period(share: np.ndarray) -> tuple[float, float] | None:
    """(period_hours, prominence) of the largest non-diurnal spectral peak."""
    x = share[~np.isnan(share)]
    if len(x) < MIN_TICKS or np.std(x) < 1e-6:
        return None
    # prewhiten: share series are strongly red (rolling-window smoothing +
    # slow drifts); first-differencing flattens the background so a peak is a
    # genuine cycle rather than low-frequency leakage
    x = np.diff(x)
    if np.std(x) < 1e-9:
        return None
    x = x - x.mean()
    f = np.fft.rfftfreq(len(x), d=TICK_MIN / 60.0)  # cycles per hour
    p = np.abs(np.fft.rfft(x)) ** 2
    mask = (f > 0) & (1.0 / np.maximum(f, 1e-9) < 12.0)  # periods < 12h only
    if mask.sum() < 20:
        return None
    peak = int(np.argmax(p * mask))
    background = np.median(p[mask])
    if background <= 0:
        return None
    return float(1.0 / f[peak]), float(p[peak] / background)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = share_series()
    results = []
    for (_, uuid), g in df.groupby(["model_permaslug", "endpoint_uuid"]):
        g = g.sort_values("ts").drop_duplicates("ts")
        r = dominant_period(g["share"].to_numpy())
        if r:
            results.append({"endpoint_uuid": uuid, "period_h": r[0], "prominence": r[1]})
    res = pd.DataFrame(results)
    if len(res) < 30:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(res)}/30 endpoints"}
        save_json(summary, out_dir, "cbh13_summary")
        return summary
    # a genuine dispatch clock shows as a COMMON period across endpoints with
    # high prominence; idiosyncratic peaks are noise
    strong = res[res["prominence"] >= 20]
    common = (
        strong["period_h"].round(1).value_counts(normalize=True).head(3).to_dict()
        if len(strong)
        else {}
    )
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_endpoints": int(len(res)),
        "median_peak_prominence": float(res["prominence"].median()),
        "share_endpoints_prominence_ge_20": float((res["prominence"] >= 20).mean()),
        "common_periods_among_strong_h": {str(k): round(float(v), 2) for k, v in common.items()},
        "read": (
            "a shared sub-12h period across many endpoints = dispatch re-rank clock; "
            "scattered idiosyncratic peaks = no clock (per-request or continuous)"
        ),
        "claim_boundary": (
            "request_count_30m is a rolling window: it low-passes the series and can "
            "alias sub-30-minute clocks; absence of a peak below ~1h is not evidence "
            "of absence at that scale."
        ),
    }
    save_json(summary, out_dir, "cbh13_summary")
    return summary
