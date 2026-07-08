"""H21 — Quoter reaction functions: who follows whom, and how fast?

From the live pricing_changes event log: for every ordered pair of events on
the same model by different providers within 14 days, record the follow lag.
Per-provider (and market) reaction-lag distributions accumulate nightly.
Verdict is gated at >=100 follow pairs; preliminary numbers reported from
day one so progress is visible.

Also gates H22 (Ss bands, >=200 events) and H25 (post-cut flow composition,
>=30 cuts with 7-day post windows) — this module reports their counters so
the whole phase-3 queue's readiness is visible in one place.
"""

import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

GATE_H21, GATE_H22, GATE_H25 = 100, 200, 30


def load_events() -> pd.DataFrame:
    ev = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name,
               cast(old_value as double) old_v, cast(new_value as double) new_v
        from read_parquet('{data.table_glob("pricing_changes", "derived")}')
        where field = 'price_completion' and old_value is not null
        """
    ).df()
    ev["ts"] = pd.to_datetime(ev["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    ev["is_cut"] = ev["new_v"] < ev["old_v"]
    return ev.sort_values("ts")


def follow_pairs(ev: pd.DataFrame) -> pd.DataFrame:
    pairs = []
    for _model, g in ev.groupby("model_id"):
        recs = g.to_dict("records")
        for i, lead in enumerate(recs):
            for follow in recs[i + 1 :]:
                lag_h = (follow["ts"] - lead["ts"]).total_seconds() / 3600
                if follow["provider_name"] == lead["provider_name"] or lag_h > 14 * 24:
                    continue
                pairs.append(
                    {
                        "model_id": lead["model_id"],
                        "leader": lead["provider_name"],
                        "follower": follow["provider_name"],
                        "lag_hours": lag_h,
                        "leader_cut": lead["is_cut"],
                        "follower_cut": follow["is_cut"],
                        "same_direction": lead["is_cut"] == follow["is_cut"],
                    }
                )
    return pd.DataFrame(pairs)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ev = load_events()
    pairs = follow_pairs(ev) if len(ev) else pd.DataFrame()
    if len(pairs):
        save(pairs, out_dir, "h21_follow_pairs")
    n_ev, n_pairs = int(len(ev)), int(len(pairs))
    n_cuts = int(ev["is_cut"].sum()) if len(ev) else 0
    results: dict = {
        "phase3_readiness": {
            "h21_follow_pairs": f"{n_pairs}/{GATE_H21}",
            "h22_events": f"{n_ev}/{GATE_H22}",
            "h25_cut_events": f"{n_cuts}/{GATE_H25}",
        },
        "n_events": n_ev,
    }
    if n_pairs:
        results["preliminary" if n_pairs < GATE_H21 else "reactions"] = {
            "n_follow_pairs": n_pairs,
            "median_lag_hours": float(pairs["lag_hours"].median()),
            "share_within_24h": float((pairs["lag_hours"] <= 24).mean()),
            "share_same_direction": float(pairs["same_direction"].mean()),
            "fastest_followers": pairs.groupby("follower")["lag_hours"]
            .median()
            .sort_values()
            .head(6)
            .round(1)
            .to_dict(),
        }
    save_json(results, out_dir, "h21_summary")
    log.info("H21: %s", results)
    return results
