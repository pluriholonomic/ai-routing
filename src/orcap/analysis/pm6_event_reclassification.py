"""PM-6 — Signed reclassification of repricing reaction events.

Separates three stories the CBH-4 typing conflated, by initiator sign,
follower behavior, and PERSISTENCE of the initiator's move:

  failed_leadership   initiator RAISES, unfollowed within window, self-
                      reverts (Byrne-de Roos initiation phase)
  followed_leadership initiator raises, rivals follow up (coordination
                      building)
  punish_and_revert   initiator CUTS and HOLDS; rivals cut then re-raise
                      while the cut persists (Green-Porter signature)
  reoptimize          initiator cuts; rivals cut and stay (Brown-MacKay /
                      competitive adjustment)
  cut_withdrawn       initiator cuts but itself reverts before/with the
                      rivals' re-raise (experimentation, not punishment)
  no_response         no rival move in window

Overlay: initiator volume class (low-volume initiators = costless
ATPCO-style signaling) and algo/non-algo pair type (Assad).

  pm6_events.parquet, pm6_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import demand_shares

log = logging.getLogger(__name__)

RESPONSE_H = 72
REVERT_H = 96


def all_changes() -> pd.DataFrame:
    df = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name,
               try_cast(old_value as double) o, try_cast(new_value as double) n
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and model_id not like '%:%'
          and try_cast(old_value as double) > 0 and try_cast(new_value as double) > 0
        """
    ).df()
    df["ts"] = pd.to_datetime(df["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    df["is_cut"] = df["n"] < df["o"]
    return df.sort_values("ts")


def classify(e: pd.Series, ch: pd.DataFrame, panel_end: pd.Timestamp) -> str | None:
    if e["ts"] + pd.Timedelta(hours=RESPONSE_H) > panel_end:
        return None
    own_later = ch[
        (ch["model_id"] == e["model_id"])
        & (ch["provider_name"] == e["provider_name"])
        & (ch["ts"] > e["ts"])
        & (ch["ts"] <= e["ts"] + pd.Timedelta(hours=REVERT_H))
    ]
    own_reverted = bool(
        len(own_later) and (own_later["is_cut"] != e["is_cut"]).any()
    )
    rivals = ch[
        (ch["model_id"] == e["model_id"]) & (ch["provider_name"] != e["provider_name"])
    ]
    win = rivals[(rivals["ts"] > e["ts"]) & (rivals["ts"] <= e["ts"] + pd.Timedelta(hours=RESPONSE_H))]
    followers = win[win["is_cut"] == e["is_cut"]]

    if not e["is_cut"]:  # raise-initiated
        if followers.empty:
            return "failed_leadership" if own_reverted else "unfollowed_raise_held"
        return "followed_leadership"
    # cut-initiated
    if followers.empty:
        return "no_response"
    # did any follower later re-raise?
    reverting = False
    revert_ts = None
    for _, f in followers.iterrows():
        later = rivals[
            (rivals["provider_name"] == f["provider_name"])
            & (rivals["ts"] > f["ts"])
            & (rivals["ts"] <= f["ts"] + pd.Timedelta(hours=REVERT_H))
            & (~rivals["is_cut"])
        ]
        if len(later):
            reverting = True
            revert_ts = later["ts"].min() if revert_ts is None else min(revert_ts, later["ts"].min())
    if not reverting:
        return "reoptimize"
    # persistence: did the initiator hold its cut through the first revert?
    own_before_revert = ch[
        (ch["model_id"] == e["model_id"])
        & (ch["provider_name"] == e["provider_name"])
        & (ch["ts"] > e["ts"])
        & (ch["ts"] <= revert_ts)
        & (~ch["is_cut"])
    ]
    return "cut_withdrawn" if len(own_before_revert) else "punish_and_revert"


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ch = all_changes()
    if len(ch) < 50:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(ch)}/50 changes"}
        save_json(summary, out_dir, "pm6_summary")
        return summary
    panel_end = ch["ts"].max()
    shares = demand_shares()
    vol = shares.groupby(["model_id", "provider_name"])["tokens"].sum()
    model_vol = shares.groupby("model_id")["tokens"].sum()
    algo = set(ch["provider_name"].value_counts()[lambda s: s >= 2].index)

    rows = []
    for _, e in ch.iterrows():
        c = classify(e, ch, panel_end)
        if c is None:
            continue
        share = float(
            vol.get((e["model_id"], e["provider_name"]), 0.0)
            / max(model_vol.get(e["model_id"], np.nan), 1e-9)
        ) if e["model_id"] in model_vol.index else np.nan
        rows.append(
            {
                "model_id": e["model_id"],
                "provider_name": e["provider_name"],
                "ts": str(e["ts"]),
                "initiator_sign": "cut" if e["is_cut"] else "raise",
                "class": c,
                "initiator_token_share": share,
                "initiator_low_volume": bool(share < 0.01) if not np.isnan(share) else None,
                "initiator_algo": e["provider_name"] in algo,
            }
        )
    ev = pd.DataFrame(rows)
    save(ev, out_dir, "pm6_events")
    def shares_of(df):
        return {k: round(float(v), 3) for k, v in df["class"].value_counts(normalize=True).items()}
    lowvol = ev[ev["initiator_low_volume"] == True]  # noqa: E712
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_events": int(len(ev)),
        "by_initiator_sign": {
            s: shares_of(ev[ev["initiator_sign"] == s]) for s in ("cut", "raise")
        },
        "n_by_sign": ev["initiator_sign"].value_counts().to_dict(),
        "low_volume_initiator_share": round(float((ev["initiator_low_volume"] == True).mean()), 3),  # noqa: E712
        "low_volume_initiator_classes": shares_of(lowvol) if len(lowvol) >= 10 else None,
        "reading_keys": {
            "punish_and_revert": "Green-Porter candidate (cut held; rivals cut then re-raise)",
            "cut_withdrawn": "initiator experimentation, NOT punishment",
            "reoptimize": "Brown-MacKay/competitive",
            "failed_leadership": "Byrne-de Roos initiation attempt",
        },
        "claim_boundary": (
            "Windows 72h/96h; classes are event-level heuristics pending the pm8 "
            "regime model; volume shares from effective_pricing (missing for some "
            "providers); 'algo' = >=2 changes in panel."
        ),
    }
    save_json(summary, out_dir, "pm6_summary")
    return summary
