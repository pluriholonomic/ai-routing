"""CBH-11 — Insulation test (Weyl): does the router shield demand from
supply-side shocks?

Weyl (AER 2010): platforms use 'insulating tariffs' — conditioning one side's
experience on the other side's participation — to neutralize participation
shocks. Managed-platform prediction: when a provider is deranked/degraded,
model-level delivered congestion barely moves (flow reroutes within minutes)
while the affected provider's own metrics collapse. Bulletin-board
alternative: the shock passes through to the model level.

Events: is_deranked False→True transitions in the 5-min congestion panel.
Outcome: model-level request-weighted p90 latency and rate-limit share,
±3h around the event, for the model vs the deranked endpoint.

  cbh11_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

WINDOW_H = 3


def panel() -> pd.DataFrame:
    df = data.q(
        f"""
        select run_ts, model_permaslug, endpoint_uuid,
               cast(is_deranked as boolean) as is_deranked,
               try_cast(request_count_30m as double) as requests,
               try_cast(rate_limited_30m as double) as rate_limited,
               try_cast(p90_latency_ms as double) as p90
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        """
    ).df()
    df["ts"] = pd.to_datetime(df["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    return df


def derank_events(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["endpoint_uuid", "ts"])
    prev = df.groupby("endpoint_uuid")["is_deranked"].shift()
    return df[(df["is_deranked"]) & (prev == False)]  # noqa: E712


def _model_metrics(g: pd.DataFrame) -> pd.Series:
    w = g["requests"].fillna(0.0)
    tot = w.sum()
    if tot <= 0:
        return pd.Series({"p90": np.nan, "rl_share": np.nan})
    return pd.Series(
        {
            "p90": float((g["p90"] * w).sum() / tot),
            "rl_share": float(g["rate_limited"].fillna(0).sum() / tot),
        }
    )


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = panel()
    events = derank_events(df)
    rows = []
    for _, e in events.iterrows():
        lo, hi = e["ts"] - pd.Timedelta(hours=WINDOW_H), e["ts"] + pd.Timedelta(hours=WINDOW_H)
        m = df[(df["model_permaslug"] == e["model_permaslug"]) & (df["ts"] >= lo) & (df["ts"] <= hi)]
        if m["ts"].nunique() < 20:
            continue
        pre_m = _model_metrics(m[m["ts"] < e["ts"]])
        post_m = _model_metrics(m[m["ts"] >= e["ts"]])
        own = m[m["endpoint_uuid"] == e["endpoint_uuid"]]
        pre_o = own[own["ts"] < e["ts"]]["p90"].median()
        post_o = own[own["ts"] >= e["ts"]]["p90"].median()
        if any(pd.isna(v) for v in (pre_m["p90"], post_m["p90"], pre_o, post_o)) or pre_m["p90"] <= 0:
            continue
        rows.append(
            {
                "model": e["model_permaslug"],
                "model_dp90_pct": 100.0 * (post_m["p90"] - pre_m["p90"]) / pre_m["p90"],
                "own_dp90_pct": 100.0 * (post_o - pre_o) / pre_o if pre_o > 0 else np.nan,
                "model_drl": post_m["rl_share"] - pre_m["rl_share"],
            }
        )
    ev = pd.DataFrame(rows)
    if len(ev) < 10:
        summary = {
            "evidence_status": "power_gated",
            "gate": f"only {len(ev)}/10 derank events with adequate windows",
            "n_derank_transitions_total": int(len(events)),
        }
        save_json(summary, out_dir, "cbh11_summary")
        return summary
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_events": int(len(ev)),
        "model_level_abs_dp90_median_pct": float(ev["model_dp90_pct"].abs().median()),
        "own_endpoint_abs_dp90_median_pct": float(ev["own_dp90_pct"].abs().median()),
        "insulation_ratio_median": float(
            (ev["own_dp90_pct"].abs() / ev["model_dp90_pct"].abs().clip(lower=0.1)).median()
        ),
        "read": (
            "insulation = model-level delivered latency ~flat while the deranked "
            "endpoint's own latency moves; ratio >> 1 supports managed-platform"
        ),
        "claim_boundary": (
            "Deranks are router actions, not exogenous outages — the router removes "
            "an endpoint precisely because it degraded, so 'insulation' measures the "
            "combined detect+reroute loop, not counterfactual pass-through."
        ),
    }
    save_json(summary, out_dir, "cbh11_summary")
    return summary
