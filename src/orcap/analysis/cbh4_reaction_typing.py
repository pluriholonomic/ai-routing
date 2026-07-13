"""CBH-4 (was H73) — Typed rival reactions to price cuts: competitive vs collusive dynamics.

Three mutually exclusive dynamic signatures from the algorithmic-pricing
literature: match-and-stick (competitive Bertrand adjustment), punish-and-
revert (Calvano et al. 2020 Q-learning collusion: rivals cut, then all drift
back up), and no-response (segmented/loyal markets). Edgeworth sawtooth
(Musolff 2022) needs longer windows and gates separately.

Event = completion-price cut in derived/pricing_changes. Rival responses read
from subsequent change events on the same model within the response window.

  h73_events.parquet   per-event typing
  h73_summary.json     type shares
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

RESPONSE_H = 72  # hours
REVERT_H = 96


def change_events() -> pd.DataFrame:
    df = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name,
               try_cast(old_value as double) as old_value,
               try_cast(new_value as double) as new_value
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and model_id not like '%:%'
          and try_cast(old_value as double) > 0 and try_cast(new_value as double) > 0
        """
    ).df()
    df["ts"] = pd.to_datetime(df["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    df["is_cut"] = df["new_value"] < df["old_value"]
    return df.sort_values("ts")


def type_event(cut: pd.Series, changes: pd.DataFrame, panel_end: pd.Timestamp) -> str | None:
    """Classify one cut event by rivals' subsequent moves on the same model."""
    if cut["ts"] + pd.Timedelta(hours=RESPONSE_H) > panel_end:
        return None  # window not observed yet
    rivals = changes[
        (changes["model_id"] == cut["model_id"])
        & (changes["provider_name"] != cut["provider_name"])
    ]
    window = rivals[
        (rivals["ts"] > cut["ts"]) & (rivals["ts"] <= cut["ts"] + pd.Timedelta(hours=RESPONSE_H))
    ]
    rival_cuts = window[window["is_cut"]]
    if rival_cuts.empty:
        return "no_response"
    # did any responding rival then re-raise above its post-cut level?
    for _, rc in rival_cuts.iterrows():
        later = rivals[
            (rivals["provider_name"] == rc["provider_name"])
            & (rivals["ts"] > rc["ts"])
            & (rivals["ts"] <= rc["ts"] + pd.Timedelta(hours=REVERT_H))
            & (~rivals["is_cut"])
        ]
        if not later.empty and later["new_value"].max() > rc["new_value"] * 1.01:
            return "punish_and_revert"
    return "match_and_stick"


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    changes = change_events()
    cuts = changes[changes["is_cut"]]
    if len(cuts) < 20:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(cuts)}/20 cut events"}
        save_json(summary, out_dir, "cbh4_summary")
        return summary
    panel_end = changes["ts"].max()
    rows = []
    for _, cut in cuts.iterrows():
        t = type_event(cut, changes, panel_end)
        if t is not None:
            rows.append(
                {
                    "model_id": cut["model_id"],
                    "provider_name": cut["provider_name"],
                    "ts": str(cut["ts"]),
                    "dlog": float(np.log(cut["new_value"] / cut["old_value"])),
                    "reaction_type": t,
                }
            )
    ev = pd.DataFrame(rows)
    if ev.empty:
        summary = {"evidence_status": "power_gated", "gate": "no cut events with full windows"}
        save_json(summary, out_dir, "cbh4_summary")
        return summary
    save(ev, out_dir, "cbh4_events")
    shares = ev["reaction_type"].value_counts(normalize=True).to_dict()
    responded = ev[ev["reaction_type"] != "no_response"]
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_typed_events": int(len(ev)),
        "type_shares": {k: round(float(v), 3) for k, v in shares.items()},
        "conditional_on_response": {
            k: round(float(v), 3)
            for k, v in responded["reaction_type"].value_counts(normalize=True).to_dict().items()
        }
        if len(responded)
        else {},
        "signatures": {
            "match_and_stick": "competitive adjustment",
            "punish_and_revert": "Calvano Q-learning collusion signature",
            "no_response": "segmented/loyal or thin market",
        },
        "claim_boundary": (
            "Typing uses change events only (not full quote paths); revert detection "
            "requires an explicit later raise, so slow drift-back beyond 96h escapes it. "
            "Edgeworth-cycle detection gates on a multi-week panel."
        ),
    }
    save_json(summary, out_dir, "cbh4_summary")
    return summary
