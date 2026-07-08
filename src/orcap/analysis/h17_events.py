"""H17 — What drives repricing events?

Two evidence layers:

LIVE (derived/pricing_changes, 5-min resolution, grows daily):
  Each endpoint-event is classified by candidate driver signatures:
    - provider_wave: same provider repriced other models within ±12h
      (supply-side/cost shock or fleet policy change)
    - launch_experiment: model younger than 30 days at event
      (price discovery on new listings)
    - reversal: opposite-direction change on the same endpoint within the
      window (experimentation; menu-cost/cost-shock stories predict few)
    - competitor_reaction: another provider on the same model repriced in the
      prior 48h (strategic complementarity — H8's object)
    - undercut_position: whether the mover was above or below the model's
      median price before moving
  Plus congestion covariates (utilization, p90 latency, reject rate) in the
  samples before the event, where the model is on the hot-40 panel.

HISTORICAL (wayback, model-level, 2023-2026, n≈1,082 changes):
    - lifecycle: change frequency and direction vs model age
    - market-wide waves: calendar clustering of changes across models

  h17_events           enriched live event table
  h17_wayback_ages     age at change, direction (historical)
  h17_summary          driver-signature shares + lifecycle stats
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_events() -> pd.DataFrame:
    ev = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name, tag, endpoint_fingerprint,
               field, cast(old_value as double) old_v, cast(new_value as double) new_v
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and old_value is not null and new_value is not null
        """
    ).df()
    ev["ts"] = pd.to_datetime(ev["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    ev["dlog"] = np.log(ev["new_v"] / ev["old_v"])
    return ev


def _model_created() -> pd.DataFrame:
    return data.q(
        f"""
        select id as model_id, to_timestamp(max(created)) created_at
        from {data.models_snapshots()} group by 1
        """
    ).df()


def classify_events(ev: pd.DataFrame) -> pd.DataFrame:
    ev = ev.sort_values("ts").copy()
    created = _model_created()
    ev = ev.merge(created, on="model_id", how="left")
    ev["model_age_days"] = (
        ev["ts"] - pd.to_datetime(ev["created_at"], utc=True)
    ).dt.total_seconds() / 86400

    flags = []
    for r in ev.itertuples(index=False):
        others_same_provider = ev[
            (ev["provider_name"] == r.provider_name)
            & (ev["model_id"] != r.model_id)
            & ((ev["ts"] - r.ts).abs() <= pd.Timedelta("12h"))
        ]
        same_endpoint = ev[
            (ev["provider_name"] == r.provider_name)
            & (ev["model_id"] == r.model_id)
            & (ev["tag"] == r.tag)
            & (ev["ts"] != r.ts)
        ]
        competitor_prior = ev[
            (ev["model_id"] == r.model_id)
            & (ev["provider_name"] != r.provider_name)
            & (ev["ts"] < r.ts)
            & (r.ts - ev["ts"] <= pd.Timedelta("48h"))
        ]
        flags.append(
            {
                "provider_wave": len(others_same_provider) > 0,
                "reversal": bool((np.sign(same_endpoint["dlog"]) == -np.sign(r.dlog)).any()),
                "competitor_reaction": len(competitor_prior) > 0,
                "launch_experiment": bool(r.model_age_days is not None and r.model_age_days < 30),
            }
        )
    return pd.concat([ev.reset_index(drop=True), pd.DataFrame(flags)], axis=1)


def pre_event_congestion(ev: pd.DataFrame) -> pd.DataFrame:
    """Mean utilization / p90 latency / reject rate for the mover's model in the
    6h before each event vs the model-day mean (hot-40 coverage only)."""
    try:
        cong = data.q(
            f"""
            select run_ts, model_permaslug, provider_name,
                   p90_latency_ms, recent_peak_rpm, capacity_ceiling_rpm,
                   rate_limited_30m, success_30m
            from read_parquet('{data.table_glob("congestion_intraday")}')
            """
        ).df()
    except Exception as exc:
        log.warning("no congestion panel: %s", exc)
        return ev.assign(pre_utilization=np.nan, pre_p90_latency=np.nan, pre_reject=np.nan)
    cong["ts"] = pd.to_datetime(cong["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    cong["util"] = cong["recent_peak_rpm"] / cong["capacity_ceiling_rpm"].replace(0, np.nan)
    cong["reject"] = cong["rate_limited_30m"] / (
        cong["rate_limited_30m"] + cong["success_30m"]
    ).replace(0, np.nan)
    slug_map = data.q(
        f"""select distinct canonical_slug, id from {data.models_snapshots()}
        where id not like '%:%'"""
    ).df()
    cong = cong.merge(slug_map, left_on="model_permaslug", right_on="canonical_slug")

    outs = []
    for r in ev.itertuples(index=False):
        c = cong[
            (cong["id"] == r.model_id)
            & (cong["provider_name"] == r.provider_name)
            & (cong["ts"] < r.ts)
            & (r.ts - cong["ts"] <= pd.Timedelta("6h"))
        ]
        outs.append(
            {
                "pre_utilization": float(c["util"].mean()) if len(c) else np.nan,
                "pre_p90_latency": float(c["p90_latency_ms"].mean()) if len(c) else np.nan,
                "pre_reject": float(c["reject"].mean()) if len(c) else np.nan,
            }
        )
    return pd.concat([ev.reset_index(drop=True), pd.DataFrame(outs)], axis=1)


def wayback_lifecycle() -> tuple[pd.DataFrame, dict]:
    ages = data.q(
        f"""
        with panel as (
          select id as model_id, run_ts, price_completion,
                 to_timestamp(max(created) over (partition by id)) created_at
          from {data.wayback_models()}
          where price_completion > 0
        ),
        chg as (
          select model_id, run_ts, created_at, price_completion,
                 lag(price_completion) over (partition by model_id order by run_ts) prev
          from panel
        )
        select model_id, run_ts, created_at,
               ln(price_completion / prev) as dlog,
               date_diff('day', created_at,
                         strptime(run_ts, '%Y%m%dT%H%M%SZ')) as age_days
        from chg where prev is not null and prev != price_completion
        """
    ).df()
    ages = ages[ages["age_days"] >= 0]
    buckets = pd.cut(
        ages["age_days"],
        [0, 30, 90, 180, 365, 10000],
        labels=["<1mo", "1-3mo", "3-6mo", "6-12mo", ">1yr"],
    )
    by_age = ages.groupby(buckets, observed=True).agg(
        n=("dlog", "size"),
        share_cuts=("dlog", lambda s: float((s < 0).mean())),
        median_abs_dlog=("dlog", lambda s: float(s.abs().median())),
    )
    # market-wide waves: changes per snapshot date, top concentrations
    ages["snap"] = ages["run_ts"].str[:8]
    per_snap = ages.groupby("snap").size()
    stats = {
        "n_changes": int(len(ages)),
        "by_age": by_age.reset_index().to_dict("records"),
        "top_wave_days": per_snap.sort_values(ascending=False).head(5).to_dict(),
        "share_of_changes_in_top5_snapshots": float(
            per_snap.sort_values(ascending=False).head(5).sum() / len(ages)
        ),
    }
    return ages, stats


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ev = load_events()
    if len(ev):
        ev = classify_events(ev)
        ev = pre_event_congestion(ev)
        save(ev, out_dir, "h17_events")
    ages, wb = wayback_lifecycle()
    save(ages, out_dir, "h17_wayback_ages")
    results: dict = {"n_live_events": int(len(ev)), "wayback": wb}
    if len(ev):
        results["live"] = {
            "share_cuts": float((ev["dlog"] < 0).mean()),
            "median_abs_dlog": float(ev["dlog"].abs().median()),
            "share_provider_wave": float(ev["provider_wave"].mean()),
            "share_reversal": float(ev["reversal"].mean()),
            "share_competitor_reaction_48h": float(ev["competitor_reaction"].mean()),
            "share_launch_experiment_lt30d": float(ev["launch_experiment"].mean()),
            "median_model_age_days_at_event": float(ev["model_age_days"].median()),
            "pre_event_utilization_mean": float(ev["pre_utilization"].mean()),
        }
    save_json(results, out_dir, "h17_summary")
    log.info("H17: %s", results)
    return results
