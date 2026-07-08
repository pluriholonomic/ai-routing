"""H33 — Provider elasticity-quality scorecard.

Assesses each provider's *pricing responsiveness quality* from the live event
log and share panel. Components (each only where data exists):

  reaction_lag_h     median hours to follow a rival's move on a shared model
                     (lower = more elastic)
  reaction_slope     |Δln p_follower| / |Δln p_leader| within follow pairs
                     (≈1 = peg-to-best automation; ≈0 = ignores rivals)
  recapture          Δshare gained per 1% price cut (event-based router
                     response the provider actually harvests)
  activity           price events per model served (mover intensity)

Composite: mean of available component percentile ranks (activity, inverse
lag, slope-closeness-to-1, recapture). Joined to the H19 type. Small-n
preliminary until the H21 gates open; recomputed nightly.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h21_reactions import load_events

log = logging.getLogger(__name__)


def follow_pairs_mag(ev: pd.DataFrame) -> pd.DataFrame:
    pairs = []
    for _model, g in ev.groupby("model_id"):
        recs = g.to_dict("records")
        for i, lead in enumerate(recs):
            for fol in recs[i + 1 :]:
                lag_h = (fol["ts"] - lead["ts"]).total_seconds() / 3600
                if fol["provider_name"] == lead["provider_name"] or lag_h > 14 * 24:
                    continue
                pairs.append(
                    {
                        "follower": fol["provider_name"],
                        "lag_h": lag_h,
                        "slope": abs(np.log(fol["new_v"] / fol["old_v"]))
                        / max(1e-9, abs(np.log(lead["new_v"] / lead["old_v"]))),
                    }
                )
    return pd.DataFrame(pairs)


def shares_daily() -> pd.DataFrame:
    sh = data.q(
        f"""
        select cast(dt as varchar) as dt, model_permaslug, provider_name, total_tokens,
               total_tokens / sum(total_tokens) over (partition by dt, model_permaslug, variant)
                 as share
        from read_parquet('{data.table_glob("effective_pricing_daily")}')
        where variant = 'standard'
        """
    ).df()
    slug = data.q(
        f"""select distinct canonical_slug, id from {data.models_snapshots()}
        where id not like '%:%'"""
    ).df()
    return sh.merge(slug, left_on="model_permaslug", right_on="canonical_slug")


def recapture(ev: pd.DataFrame, sh: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cuts = ev[ev["new_v"] < ev["old_v"]]
    for r in cuts.itertuples(index=False):
        day = r.ts.strftime("%Y-%m-%d")
        s = sh[(sh["id"] == r.model_id) & (sh["provider_name"] == r.provider_name)]
        pre = s[s["dt"] <= day]["share"]
        post = s[s["dt"] > day]["share"]
        if len(pre) and len(post):
            cut_pct = -np.log(r.new_v / r.old_v)
            rows.append(
                {
                    "provider": r.provider_name,
                    "dshare_per_pct_cut": float((post.mean() - pre.iloc[-1]) / max(0.01, cut_pct)),
                }
            )
    return pd.DataFrame(rows)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ev = load_events()
    ev = ev.rename(columns={"provider_name": "provider_name"})
    n_models = data.q(
        f"""
        select provider_name, count(distinct model_id) n_models
        from {data.latest_endpoints()} group by 1
        """
    ).df()

    activity = (
        ev.groupby("provider_name").size().rename("n_events").reset_index()
        if len(ev)
        else pd.DataFrame(columns=["provider_name", "n_events"])
    )
    card = n_models.merge(activity, on="provider_name", how="left")
    card["n_events"] = card["n_events"].fillna(0)
    card["events_per_model"] = card["n_events"] / card["n_models"].clip(lower=1)

    pairs = follow_pairs_mag(ev) if len(ev) else pd.DataFrame()
    if len(pairs):
        f = pairs.groupby("follower").agg(
            reaction_lag_h=("lag_h", "median"), reaction_slope=("slope", "median")
        )
        card = card.merge(f, left_on="provider_name", right_index=True, how="left")
    rec = recapture(ev, shares_daily()) if len(ev) else pd.DataFrame()
    if len(rec):
        card = card.merge(
            rec.groupby("provider").agg(recapture=("dshare_per_pct_cut", "mean")),
            left_on="provider_name",
            right_index=True,
            how="left",
        )

    # composite: percentile ranks of available components
    comp = pd.DataFrame(index=card.index)
    comp["act"] = card["events_per_model"].rank(pct=True)
    if "reaction_lag_h" in card:
        comp["lag"] = (-card["reaction_lag_h"]).rank(pct=True)
        comp["slope"] = (-(card["reaction_slope"] - 1).abs()).rank(pct=True)
    if "recapture" in card:
        comp["rec"] = card["recapture"].rank(pct=True)
    card["elasticity_score"] = comp.mean(axis=1, skipna=True).round(3)
    card = card.sort_values("elasticity_score", ascending=False)
    save(card, out_dir, "h33_scorecard")

    active = card[card["n_events"] > 0]
    results = {
        "n_providers_scored": int(len(card)),
        "n_with_events": int(len(active)),
        "top_elastic": active.head(8)[
            [
                c
                for c in [
                    "provider_name",
                    "elasticity_score",
                    "n_events",
                    "reaction_lag_h",
                    "reaction_slope",
                    "recapture",
                ]
                if c in card
            ]
        ]
        .round(3)
        .to_dict("records"),
        "note": "small-n preliminary; recomputed nightly, hardens with the event log",
    }
    save_json(results, out_dir, "h33_summary")
    log.info("H33: scored %d providers, %d with events", len(card), len(active))
    return results
