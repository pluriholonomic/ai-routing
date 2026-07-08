"""H40 — How much demand does the router GENERATE (vs merely intermediate)?

Decomposition of routed volume into channels of incrementality:

  (a) subsidy-created   :free variant tokens — demand that exists only at
      router-subsidized prices (would not clear at market rates).
  (b) access-created    tokens to models whose author runs no first-party
      API (OSS long tail served only by hosts) — in a no-router world this
      demand requires per-host integrations; lower bound on access effect.
  (c) reliability-created  traffic absorbed by failover: share gains by
      non-primary providers on days the primary's uptime dips — demand a
      single-provider integration would have dropped.
  (d) price-response    H29 elasticity × router effective-price improvement
      (gated on H29).

Plus the aggregate: total routed tokens/week (rankings incl. "Others").
Pre-registered: listing diff-in-diff — HF-download trajectories around
OpenRouter listing events vs unlisted peers (hf_model_stats_daily powers it;
~6-8 weeks of listings needed).
"""

import logging
from pathlib import Path

from . import data
from .common import DEFAULT_OUT, save_json
from .h19_provider_types import provider_family, serves_own

log = logging.getLogger(__name__)


def aggregate_tokens() -> dict:
    wk = data.q(
        f"""
        select cast(week as varchar) as week, sum(total_tokens) as toks
        from read_parquet('{data.table_glob("rankings_weekly")}')
        group by 1 order by 1
        """
    ).df()
    if wk.empty:
        return {}
    recent = wk.tail(4)
    return {
        "latest_week_tokens_T": round(float(wk["toks"].iloc[-1]) / 1e12, 2),
        "avg_4w_tokens_T": round(float(recent["toks"].mean()) / 1e12, 2),
        "yoy_growth_pct": round(
            100 * (float(wk["toks"].iloc[-1]) / float(wk["toks"].iloc[0]) - 1), 1
        )
        if len(wk) > 40
        else None,
        "weeks": int(len(wk)),
    }


def first_party_authors() -> set[str]:
    prov = data.q(
        f"""
        select distinct provider_name from {data.latest_endpoints()}
        """
    ).df()
    fams = {provider_family(p) for p in prov["provider_name"]}
    authors = data.q(
        f"""
        select distinct split_part(model_permaslug, '/', 1) as author
        from read_parquet('{data.table_glob("model_activity_daily")}')
        """
    ).df()["author"]
    return {a for a in authors if any(serves_own(f, a) for f in fams)}


def channel_shares() -> dict:
    act = data.q(
        f"""
        select model_permaslug, variant,
               sum(total_prompt_tokens + total_completion_tokens) as toks
        from read_parquet('{data.table_glob("model_activity_daily")}')
        where date = (select distinct date
               from read_parquet('{data.table_glob("model_activity_daily")}')
               order by 1 desc limit 1 offset 1)
        group by 1, 2
        """
    ).df()
    total = act["toks"].sum()
    free = act.loc[act["variant"] == "free", "toks"].sum()
    fp = first_party_authors()
    act["author"] = act["model_permaslug"].str.split("/").str[0]
    access = act.loc[~act["author"].isin(fp), "toks"].sum()
    union = act.loc[(act["variant"] == "free") | (~act["author"].isin(fp)), "toks"].sum()
    return {
        "union_incremental_share_lower_bound": round(float(union / total), 4),
        "total_tokens_last_complete_day_T": round(float(total) / 1e12, 3),
        "subsidy_created_share": round(float(free / total), 4),
        "access_created_share_lower_bound": round(float(access / total), 4),
        "first_party_authors_n": len(fp),
        "note_access": "models whose author runs no first-party API — host/router-only tail",
    }


def failover_absorbed() -> dict:
    """Share gained by non-primary providers on primary-uptime-dip days."""
    up = data.q(
        f"""
        select cast(dt as varchar) as day, model_permaslug, provider_name,
               total_tokens,
               total_tokens / sum(total_tokens) over (partition by dt, model_permaslug, variant)
                 as share
        from read_parquet('{data.table_glob("effective_pricing_daily")}')
        where variant = 'standard'
        """
    ).df()
    days = up["day"].nunique()
    if days < 7:
        return {"gated": f"needs >=7 days of share panel (have {days})"}
    # primary = max-share provider per model; dip day = primary share drops >20% d/d
    up = up.sort_values(["model_permaslug", "provider_name", "day"])
    up["dshare"] = up.groupby(["model_permaslug", "provider_name"])["share"].diff()
    primaries = up.groupby(["model_permaslug"])["share"].transform("max") == up["share"]
    dips = up[primaries & (up["dshare"] < -0.2)]
    return {
        "n_dip_events": int(len(dips)),
        "absorbed_share_mean": round(float(-dips["dshare"].mean()), 3) if len(dips) else None,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    results = {
        "aggregate": aggregate_tokens(),
        "channels": channel_shares(),
        "failover": failover_absorbed(),
        "price_response": {"gated": "H29 demand elasticity × routing surplus; unlocks with H29"},
        "pre_registered": (
            "listing DiD: HF-download trajectories around OpenRouter listing events vs "
            "unlisted peers (hf_model_stats_daily), ~6-8 weeks of listings"
        ),
    }
    save_json(results, out_dir, "h40_summary")
    log.info("H40: %s", results)
    return results
