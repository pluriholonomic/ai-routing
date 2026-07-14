"""CBH-12 — Cold start: does early routed volume build durable share?

Pallais (AER 2014): information about new sellers is an underprovided public
good — randomly 'hiring' new workers raised their later employment beyond
what price competition explains. Router analog: providers entering a market
during high demand accumulate uptime/latency history fast; if that history
(not just current price) drives routing, early-traffic entrants should hold
share later, conditional on price rank.

Entry = __endpoint_added__ events after the panel's first day. Outcome =
provider's demand-side token share within the model ~4-5 days later
(effective_pricing), controlling contemporaneous price rank.

  cbh12_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json
from .h68_competition import daily_quotes, demand_shares

log = logging.getLogger(__name__)

MIN_ENTRIES = 20
MIN_POST_DAYS = 3


def entries() -> pd.DataFrame:
    ev = data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = '__endpoint_added__' and model_id not like '%:%'
        """
    ).df()
    first = ev["dt"].min()  # panel start: everything is "added" on day one
    return ev[ev["dt"] > first].drop_duplicates(["model_id", "provider_name"])


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ent = entries()
    shares = demand_shares()
    quotes = daily_quotes()
    last_dt = quotes["dt"].max()
    rows = []
    for _, e in ent.iterrows():
        post_days = (
            pd.to_datetime(last_dt) - pd.to_datetime(e["dt"])
        ).days
        if post_days < MIN_POST_DAYS:
            continue
        # demand environment at entry: model tokens on entry day (percentile)
        day_tokens = shares[shares["dt"] == e["dt"]].groupby("model_id")["tokens"].sum()
        if e["model_id"] not in day_tokens.index or len(day_tokens) < 10:
            continue
        demand_pctile = float((day_tokens < day_tokens[e["model_id"]]).mean())
        # outcome: entrant's token share in the final panel day, expressed
        # relative to pro-rata (share x N) — raw share is mechanically diluted
        # by incumbent count, which correlates with demand
        final = shares[(shares["dt"] == last_dt) & (shares["model_id"] == e["model_id"])]
        tot = final["tokens"].sum()
        own = final[final["provider_name"] == e["provider_name"]]["tokens"].sum()
        n_final = final["provider_name"].nunique()
        # control: entrant's price rank on the final day
        q = quotes[(quotes["dt"] == last_dt) & (quotes["model_id"] == e["model_id"])]
        rank = np.nan
        if not q.empty and e["provider_name"] in set(q["provider_name"]):
            q = q.sort_values("price").reset_index(drop=True)
            rank = float(
                q.index[q["provider_name"] == e["provider_name"]][0] / max(len(q) - 1, 1)
            )
        rows.append(
            {
                "model_id": e["model_id"],
                "provider_name": e["provider_name"],
                "entry_dt": e["dt"],
                "entry_demand_pctile": demand_pctile,
                "final_share": float(own / tot) if tot > 0 else 0.0,
                "final_share_vs_prorata": float(own / tot * n_final) if tot > 0 else 0.0,
                "final_price_rank": rank,
            }
        )
    df = pd.DataFrame(rows)
    if len(df) < MIN_ENTRIES:
        summary = {
            "evidence_status": "power_gated",
            "gate": f"only {len(df)}/{MIN_ENTRIES} entries with {MIN_POST_DAYS}+ post days",
            "n_raw_entries": int(len(ent)),
        }
        save_json(summary, out_dir, "cbh12_summary")
        return summary
    hot = df[df["entry_demand_pctile"] >= 0.5]
    cold = df[df["entry_demand_pctile"] < 0.5]
    corr = float(df["entry_demand_pctile"].corr(df["final_share_vs_prorata"], method="spearman"))
    # partial: does entry demand matter beyond final price rank?
    sub = df.dropna(subset=["final_price_rank"])
    partial = None
    if len(sub) >= 15:
        r = sub[["entry_demand_pctile", "final_share_vs_prorata", "final_price_rank"]].rank()
        X = np.column_stack([r["entry_demand_pctile"], r["final_price_rank"], np.ones(len(r))])
        beta, *_ = np.linalg.lstsq(X, r["final_share_vs_prorata"].to_numpy(), rcond=None)
        partial = round(float(beta[0]), 3)
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_entries": int(len(df)),
        "median_prorata_share_hot_entry": float(hot["final_share_vs_prorata"].median())
        if len(hot)
        else None,
        "median_prorata_share_cold_entry": float(cold["final_share_vs_prorata"].median())
        if len(cold)
        else None,
        "spearman_entrydemand_x_prorata_share": round(corr, 3),
        "rank_beta_entrydemand_controlling_price": partial,
        "read": (
            "positive conditional effect = information/cold-start channel (early "
            "traffic builds durable share); zero = share tracks current price only"
        ),
        "claim_boundary": (
            "Days-scale 'durability' only; entry timing is not random (providers "
            "choose hot models), so this is an association pending the listing-DiD."
        ),
    }
    save_json(summary, out_dir, "cbh12_summary")
    return summary
