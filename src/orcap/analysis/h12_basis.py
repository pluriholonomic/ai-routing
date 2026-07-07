"""H12 — Compute basis: on-demand vs interruptible GPU pricing as a
funding-rate / spot-forward basis analog.

  h12_basis_daily   per (gpu_class, run): on-demand median, bid median, basis
  h12_summary       basis level & dispersion per class; duration term structure

Level facts now; dynamics (mean reversion, spikes vs perp funding) accrue with
the hourly panel.
"""

import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_basis() -> pd.DataFrame:
    return data.q(
        f"""
        select run_ts, gpu_class,
               median(dph_total) filter (where offer_type = 'on-demand') as ondemand,
               median(dph_total) filter (where offer_type = 'bid') as bid,
               count(*) filter (where offer_type = 'on-demand') as n_od,
               count(*) filter (where offer_type = 'bid') as n_bid
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}')
        where num_gpus = 1 and dph_total > 0
        group by 1, 2
        """
    ).df()


def term_structure() -> pd.DataFrame:
    return data.q(
        f"""
        select gpu_class, offer_type,
               case when duration < 86400*7 then '<1w'
                    when duration < 86400*30 then '1w-1mo'
                    when duration < 86400*90 then '1-3mo'
                    else '3mo+' end as duration_bucket,
               median(dph_total) as med_dph, count(*) as n
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}')
        where run_ts = (select max(run_ts)
                        from read_parquet('{data.table_glob("gpu_offers_snapshots")}'))
          and num_gpus = 1 and dph_total > 0 and duration is not null
        group by 1, 2, 3
        """
    ).df()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_basis()
    df["basis_ratio"] = df["ondemand"] / df["bid"]
    save(df, out_dir, "h12_basis_daily")
    ts = term_structure()
    save(ts, out_dir, "h12_term_structure")
    latest = df[df["run_ts"] == df["run_ts"].max()]
    per_class = {
        r.gpu_class: {
            "ondemand": round(float(r.ondemand), 3) if pd.notna(r.ondemand) else None,
            "bid": round(float(r.bid), 3) if pd.notna(r.bid) else None,
            "basis_ratio": round(float(r.basis_ratio), 2) if pd.notna(r.basis_ratio) else None,
        }
        for r in latest.itertuples(index=False)
    }
    valid = df.dropna(subset=["basis_ratio"])
    results = {
        "runs": int(df["run_ts"].nunique()),
        "latest_per_class": per_class,
        "median_basis_ratio_all": float(valid["basis_ratio"].median()) if len(valid) else None,
        "comparator": "perp funding / spot-forward basis: small, mean-reverting; "
        "compute basis is large (interruption risk premium), like pre-2020 futures basis",
    }
    save_json(results, out_dir, "h12_summary")
    log.info("H12: %s", results)
    return results
