"""H26 — Entry pass-through: what happens to incumbent prices when a new
provider starts serving a model?

HISTORICAL ARM (runs now): LiteLLM archive, 2023-2026. A provider's first
observation of a base model (>=14d after the model first appeared anywhere)
is an entry event. Outcome: incumbents' log price change over the 90 days
after entry vs incumbents' unconditional 90-day change (matched on calendar
window). Base-model matching strips provider prefixes — approximate; treated
as a lower bound on precision, not on effect.

PROSPECTIVE ARM (gated): endpoint-level `__endpoint_added__` events from our
own panel; unlocks at >=100 post-day-0 entry events with 30-day post windows.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def _base(model: str) -> str:
    return model.split("/")[-1].lower()


def load_litellm() -> pd.DataFrame:
    df = data.q(
        f"""
        select obs_date, model, litellm_provider as provider,
               output_cost_per_token as p
        from {data.external("litellm_price_history")}
        where output_cost_per_token > 0 and litellm_provider is not null
        """
    ).df()
    df["base"] = df["model"].map(_base)
    df["obs_date"] = pd.to_datetime(df["obs_date"])
    return df


def historical_entry_study(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    first_any = df.groupby("base")["obs_date"].min().rename("model_birth")
    first_prov = (
        df.groupby(["base", "provider"])["obs_date"].min().rename("provider_entry").reset_index()
    )
    first_prov = first_prov.merge(first_any, on="base")
    entries = first_prov[
        first_prov["provider_entry"] > first_prov["model_birth"] + pd.Timedelta(days=14)
    ]

    events = []
    for r in entries.itertuples(index=False):
        inc = df[(df["base"] == r.base) & (df["provider"] != r.provider)]
        pre = inc[
            inc["obs_date"].between(r.provider_entry - pd.Timedelta(days=45), r.provider_entry)
        ]
        post = inc[
            inc["obs_date"].between(
                r.provider_entry + pd.Timedelta(days=45), r.provider_entry + pd.Timedelta(days=135)
            )
        ]
        if pre.empty or post.empty:
            continue
        pre_p = pre.groupby("provider")["p"].median()
        post_p = post.groupby("provider")["p"].median()
        common = pre_p.index.intersection(post_p.index)
        if not len(common):
            continue
        dlog = float(np.log(post_p[common] / pre_p[common]).mean())
        events.append(
            {
                "base": r.base,
                "entrant": r.provider,
                "entry_date": r.provider_entry,
                "n_incumbents": int(len(common)),
                "incumbent_dlog_90d": dlog,
            }
        )
    ev = pd.DataFrame(events)

    # baseline: unconditional ~90-day change (price at t vs obs nearest t+90d)
    df_s = df.sort_values("obs_date")
    base_changes = []
    for (_b, _pv), g in df_s.groupby(["base", "provider"]):
        if len(g) < 3:
            continue
        p = g["p"].to_numpy()
        t = g["obs_date"].to_numpy()
        for i in range(len(g)):
            target = t[i] + np.timedelta64(90, "D")
            j = int(np.searchsorted(t, target))
            for cand in (j - 1, j):
                if i < cand < len(g):
                    gap = (t[cand] - t[i]) / np.timedelta64(1, "D")
                    if 45 <= gap <= 135:
                        base_changes.append(np.log(p[cand] / p[i]))
                        break
    baseline = float(np.mean(base_changes)) if base_changes else np.nan

    stats = {
        "n_entry_events": int(len(ev)),
        "mean_incumbent_dlog_after_entry": float(ev["incumbent_dlog_90d"].mean())
        if len(ev)
        else None,
        "se": float(ev["incumbent_dlog_90d"].std() / np.sqrt(max(1, len(ev)))) if len(ev) else None,
        "share_incumbent_cuts": float((ev["incumbent_dlog_90d"] < 0).mean()) if len(ev) else None,
        "unconditional_90d_dlog_baseline": baseline,
        "excess_entry_effect": float(ev["incumbent_dlog_90d"].mean() - baseline)
        if len(ev) and not np.isnan(baseline)
        else None,
    }
    return ev, stats


def prospective_gate() -> dict:
    try:
        n = data.q(
            f"""
            select count(*) from read_parquet('{data.table_glob("pricing_changes", "derived")}')
            where field = '__endpoint_added__'
              and changed_at_run_ts > '20260708T000000Z'
            """
        ).fetchone()[0]
    except Exception:
        n = 0
    return {
        "gated": True,
        "entry_events_since_day1": int(n),
        "unlocks_at": "100 entry events with 30-day post windows (~6-10 weeks)",
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_litellm()
    ev, stats = historical_entry_study(df)
    save(ev, out_dir, "h26_entry_events_historical")
    results = {"historical": stats, "prospective": prospective_gate()}
    save_json(results, out_dir, "h26_summary")
    log.info("H26: %s", stats)
    return results
