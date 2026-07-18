"""WF-13 — Provider stratification: capital tier x anchor-adoption class.

Two orthogonal strata replace name-heuristics:
  capital tier      dc_hyperscaler / funded_neocloud / own_silicon /
                    small_startup (auditable registry with confidence flags:
                    data-static/provider_capital.csv)
  anchor class      per (provider, model): 'adopter' quotes exactly the model
                    author's first-party price on >=80% of common days;
                    'below'/'above' deviators by median sign; authors excluded

This converts the retired 'is the author price special' question into a
behavioral classification: WHO copies the anchor (the Together/BaseTen
default-pricing pattern) and how adopters behave differently (repricing,
relative price, rationing).

  wf13_strata.parquet   per provider-model: tier, anchor class, stats
  wf13_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .pm9_author_anchor import is_author_provider

log = logging.getLogger(__name__)

REGISTRY = Path(__file__).resolve().parents[3] / "data-static" / "provider_capital.csv"
ADOPT_SHARE = 0.8
MIN_DAYS = 5


def tiers() -> pd.DataFrame:
    return pd.read_csv(REGISTRY)


def tier_of(provider: str, reg: pd.DataFrame) -> str:
    pl = provider.lower()
    for _, r in reg.iterrows():
        if str(r["provider"]).lower() in pl:
            return r["tier"]
    return "unknown"


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    q = data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name,
               median(price_completion) as p
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where price_completion > 0 and model_id not like '%:%'
        group by 1, 2, 3
        """
    ).df()
    q["is_author"] = [
        is_author_provider(m, p) for m, p in zip(q["model_id"], q["provider_name"])
    ]
    anchor = (
        q[q["is_author"]]
        .groupby(["model_id", "dt"])["p"]
        .min()
        .rename("p_author")
        .reset_index()
    )
    j = q[~q["is_author"]].merge(anchor, on=["model_id", "dt"], how="inner")
    j["at_anchor"] = np.isclose(j["p"], j["p_author"], rtol=1e-9)
    j["rel"] = np.log(j["p"] / j["p_author"])

    reg = tiers()
    rows = []
    for (m, prov), g in j.groupby(["model_id", "provider_name"]):
        if g["dt"].nunique() < MIN_DAYS:
            continue
        share_at = float(g["at_anchor"].mean())
        med_rel = float(g["rel"].median())
        cls = (
            "adopter"
            if share_at >= ADOPT_SHARE
            else ("below" if med_rel < 0 else "above")
        )
        rows.append(
            {
                "model_id": m,
                "provider_name": prov,
                "tier": tier_of(prov, reg),
                "anchor_class": cls,
                "share_days_at_anchor": round(share_at, 3),
                "median_log_rel_to_anchor": round(med_rel, 4),
                "n_days": int(g["dt"].nunique()),
            }
        )
    df = pd.DataFrame(rows)
    if len(df) < 30:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(df)}/30 pairs"}
        save_json(summary, out_dir, "wf13_summary")
        return summary

    # repricing activity per pair (changes per day in panel)
    ch = data.q(
        f"""
        select model_id, provider_name, count(*) as n_changes
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' group by 1, 2
        """
    ).df()
    df = df.merge(ch, on=["model_id", "provider_name"], how="left")
    df["n_changes"] = df["n_changes"].fillna(0)
    df["changes_per_day"] = df["n_changes"] / df["n_days"]
    save(df, out_dir, "wf13_strata")

    xtab = (
        df.groupby(["tier", "anchor_class"]).size().unstack(fill_value=0)
    )
    xtab_share = (xtab.T / xtab.sum(axis=1)).T.round(3)
    by_class = df.groupby("anchor_class").agg(
        n=("model_id", "size"),
        changes_per_day=("changes_per_day", "mean"),
        median_rel=("median_log_rel_to_anchor", "median"),
    )
    by_tier = df.groupby("tier").agg(
        n=("model_id", "size"),
        adopter_share=("anchor_class", lambda s: float((s == "adopter").mean())),
        below_share=("anchor_class", lambda s: float((s == "below").mean())),
        changes_per_day=("changes_per_day", "mean"),
    )
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_pairs": int(len(df)),
        "n_models_with_author": int(df["model_id"].nunique()),
        "anchor_class_shares": df["anchor_class"].value_counts(normalize=True).round(3).to_dict(),
        "tier_x_class_share": {
            str(t): xtab_share.loc[t].to_dict() for t in xtab_share.index
        },
        "behavior_by_class": by_class.round(4).to_dict("index"),
        "behavior_by_tier": by_tier.round(4).to_dict("index"),
        "read": (
            "adopters = the Together/BaseTen default-at-author-price pattern; "
            "below-deviators = the undercutting cohort; compare repricing activity "
            "and tier composition across classes"
        ),
        "claim_boundary": (
            "Capital tiers are a manually-curated registry with confidence flags "
            "(funding/ownership approximations, not audited financials); anchor "
            "classes only defined where an author-operated endpoint exists; "
            "author identification via the alias crosswalk."
        ),
    }
    save_json(summary, out_dir, "wf13_summary")
    return summary
