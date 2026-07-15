"""WF-6 — The retry externality (condition C7): do rejections amplify demand?

Free retries convert rationing into demand amplification precisely in
shortage states — the positive-feedback wedge the classical queueing canon
does not cover (balking is replaced by retrying). Reduced-form measurement:
within endpoint, does a rate-limit spike RAISE subsequent request counts
(retry storm) rather than lower them (balking)?

  Δlog requests_{t+1} = a + φ·rl_share_t + controls, within endpoint, 5-min.

φ > 0: retry amplification (C7 violated, magnitude = φ);
φ < 0: balking/deterrence (Naor-like, self-limiting).

  wf6_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = data.q(
        f"""
        select endpoint_uuid, run_ts,
               try_cast(request_count_30m as double) as req,
               try_cast(rate_limited_30m as double) as rl
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where request_count_30m is not null
        """
    ).df()
    df["ts"] = pd.to_datetime(df["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    df = df.sort_values(["endpoint_uuid", "ts"])
    df["rl_share"] = (df["rl"] / df["req"].clip(lower=1)).clip(0, 1)
    df["dlog_req_fwd"] = (
        np.log(df.groupby("endpoint_uuid")["req"].shift(-6).clip(lower=1))
        - np.log(df["req"].clip(lower=1))
    )  # +30 min ahead (6 ticks), matching the rolling window
    # within-endpoint demeaning
    sub = df.dropna(subset=["dlog_req_fwd"])
    sub = sub[sub["req"] >= 10]
    for col in ("dlog_req_fwd", "rl_share"):
        sub[f"{col}_dm"] = sub[col] - sub.groupby("endpoint_uuid")[col].transform("mean")
    # per-endpoint sufficient statistics -> cheap endpoint-block bootstrap
    agg = sub.assign(
        sxy=sub["rl_share_dm"] * sub["dlog_req_fwd_dm"], sxx=sub["rl_share_dm"] ** 2
    ).groupby("endpoint_uuid")[["sxy", "sxx"]].sum()
    phi = float(agg["sxy"].sum() / agg["sxx"].sum()) if agg["sxx"].sum() > 0 else np.nan
    rng = np.random.default_rng(6)
    sxy, sxx = agg["sxy"].to_numpy(), agg["sxx"].to_numpy()
    draws = []
    for _ in range(500):
        idx = rng.integers(0, len(agg), len(agg))
        d = sxx[idx].sum()
        if d > 0:
            draws.append(float(sxy[idx].sum() / d))
    lo, hi = (np.percentile(draws, [2.5, 97.5]) if draws else (np.nan, np.nan))
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_obs": int(len(sub)),
        "n_endpoints": int(sub["endpoint_uuid"].nunique()),
        "phi_dlogreq30m_on_rlshare": round(phi, 3),
        "phi_ci95": [round(float(lo), 3), round(float(hi), 3)],
        "read": "phi > 0 = retry amplification (C7 wedge live); phi < 0 = balking",
        "claim_boundary": (
            "Rolling-window smoothing attenuates; rl_share is endogenous to demand "
            "level (mean reversion biases phi down within endpoint) — a positive phi "
            "is therefore conservative evidence of amplification; instrument version "
            "gates on provider-outage events."
        ),
    }
    save_json(summary, out_dir, "wf6_summary")
    return summary
