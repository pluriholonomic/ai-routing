"""PM-2 — Sufficient statistics of price adjustment (Alvarez-Le Bihan-Lippi).

Kurtosis of nonzero log price changes positions the market on the
Calvo(Kur=6) <-> Golosov-Lucas menu-cost(Kur=1) line; with frequency N,
Kur/(6N) is proportional to the cumulated real effect of a small nominal
shock (ALL, AER 2016). The small-change hole (mass at |dlog|<5%) tests for
an inaction band. Our quotes are exact (no time-averaging/imputation), so
these moments are unusually clean (EJRS 2014 critique does not bite).

  pm2_changes.parquet   per-event dlog + spell age (where computable)
  pm2_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .vintage import canonical_date, clip_date_range, date_support

log = logging.getLogger(__name__)


def changes(
    *, start_date: str | None = None, end_date: str | None = None
) -> pd.DataFrame:
    df = data.q(
        f"""
        select cast(dt as varchar) as dt, changed_at_run_ts, model_id,
               provider_name, endpoint_fingerprint,
               try_cast(old_value as double) o, try_cast(new_value as double) n
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and model_id not like '%:%'
          and try_cast(old_value as double) > 0 and try_cast(new_value as double) > 0
        """
    ).df()
    df = clip_date_range(df, start_date=start_date, end_date=end_date)
    df["ts"] = pd.to_datetime(df["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    df["dlog"] = np.log(df["n"] / df["o"])
    df = df[df["dlog"] != 0].sort_values("ts")
    key = ["model_id", "provider_name", "endpoint_fingerprint"]
    df["prev_ts"] = df.groupby(key)["ts"].shift()
    df["spell_days"] = (df["ts"] - df["prev_ts"]).dt.total_seconds() / 86400.0
    return df


def endpoint_days(
    *, start_date: str | None = None, end_date: str | None = None
) -> float:
    start = canonical_date(start_date)
    end = canonical_date(end_date)
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must not follow end_date")
    date_filter = ""
    if start is not None:
        date_filter += f" and cast(dt as varchar) >= '{start}'"
    if end is not None:
        date_filter += f" and cast(dt as varchar) <= '{end}'"
    df = data.q(
        f"""
        select count(*) as n from (
          select distinct cast(dt as varchar), model_id, provider_name
          from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
          where price_completion > 0 and model_id not like '%:%'
            {date_filter}
        )
        """
    ).df()
    return float(df["n"].iloc[0])


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    ch = changes(start_date=start_date, end_date=end_date)
    if len(ch) < 50:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(ch)}/50 changes"}
        save_json(summary, out_dir, "pm2_summary")
        return summary
    save(
        ch.assign(ts=ch["ts"].astype(str), prev_ts=ch["prev_ts"].astype(str)),
        out_dir,
        "pm2_changes",
    )
    d = ch["dlog"].to_numpy()
    kur = float(pd.Series(d).kurt() + 3.0)  # raw kurtosis (normal=3, Laplace=6)
    # ALL theory wants within-unit standardized changes: pooled kurtosis is
    # inflated by scale heterogeneity across endpoints. Standardize within
    # provider (the pricing decision-maker) where >=3 changes exist.
    grp = ch.groupby("provider_name")["dlog"]
    z = (ch["dlog"] - grp.transform("mean")) / grp.transform("std")
    z = z[grp.transform("count") >= 3].dropna()
    kur_std = float(pd.Series(z).kurt() + 3.0) if len(z) >= 50 else None
    n_freq = float(
        len(ch) / endpoint_days(start_date=start_date, end_date=end_date)
    )  # changes per endpoint-day
    spells = ch.dropna(subset=["spell_days"])
    # E[|dlog| | spell age] slope: rank corr (flat = Calvo-consistent size)
    size_age = (
        float(spells["spell_days"].rank().corr(spells["dlog"].abs().rank()))
        if len(spells) >= 30
        else None
    )
    summary = {
        "evidence_status": "provisional_descriptive",
        "analysis_vintage": date_support(ch),
        "n_changes": int(len(ch)),
        "kurtosis_raw_pooled": round(kur, 2),
        "kurtosis_within_provider_standardized": round(kur_std, 2) if kur_std else None,
        "n_standardized_changes": int(len(z)) if kur_std else 0,
        "benchmarks": {"calvo": 6.0, "golosov_lucas_menu_cost": 1.0, "micro_data_typical": 4.0},
        "freq_per_endpoint_day": round(n_freq, 5),
        "implied_duration_days": round(1.0 / n_freq, 1) if n_freq > 0 else None,
        "cir_index_kur_over_6N": round(kur / (6.0 * n_freq), 1) if n_freq > 0 else None,
        "small_change_mass_lt5pct": round(float((np.abs(d) < 0.05).mean()), 3),
        "small_change_mass_lt1pct": round(float((np.abs(d) < 0.01).mean()), 3),
        "median_abs_dlog": round(float(np.median(np.abs(d))), 3),
        "share_cuts": round(float((d < 0).mean()), 3),
        "size_vs_age_rank_corr": round(size_age, 3) if size_age is not None else None,
        "n_completed_spells": int(len(spells)),
        "claim_boundary": (
            "Panel-window spells only (first spells left-censored, excluded from the "
            "age moment); kurtosis pools heterogeneous endpoints — ALL theory wants "
            "within-unit standardization, which gates on more events per endpoint."
        ),
    }
    save_json(summary, out_dir, "pm2_summary")
    return summary
