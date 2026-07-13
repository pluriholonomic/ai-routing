"""CBH-6 (was H75) — Ben-Yehuda administered-price forensics on provider quotes.

Ben-Yehuda et al. (2013) exposed pre-2017 AWS spot prices as administered
(hidden reserve-price algorithm) rather than market-clearing, using purely
observational signatures. The translated battery:

  F1 round-number clustering   auction-cleared prices aren't round
  F2 provider-day batching     one provider repricing many models at once =
                               calendar/administered updates, not per-market
  F3 hour-of-day concentration repricing at fixed clock hours = batch jobs
  F4 synchrony                 multiple providers moving the same model the
                               same day (follow-the-leader oligopoly)

  h75_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json
from .h68_competition import daily_quotes

log = logging.getLogger(__name__)


def _round_share(prices_per_mtok: np.ndarray) -> dict:
    x = prices_per_mtok
    return {
        "share_integer": float(np.mean(np.isclose(x, np.round(x), atol=1e-9))),
        "share_half": float(np.mean(np.isclose(x * 2, np.round(x * 2), atol=1e-9))),
        "share_tenth": float(np.mean(np.isclose(x * 10, np.round(x * 10), atol=1e-9))),
        "share_hundredth": float(np.mean(np.isclose(x * 100, np.round(x * 100), atol=1e-9))),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quotes = daily_quotes()
    latest = quotes[quotes["dt"] == quotes["dt"].max()]
    rounding = _round_share((latest["price"] * 1e6).to_numpy())

    changes = data.q(
        f"""
        select changed_at_run_ts, cast(dt as varchar) as dt, model_id, provider_name
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field like 'price_%' and model_id not like '%:%'
        """
    ).df()
    if changes.empty:
        summary = {"evidence_status": "power_gated", "gate": "no change events"}
        save_json(summary, out_dir, "cbh6_summary")
        return summary
    changes["hour"] = pd.to_datetime(
        changes["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True
    ).dt.hour

    # F2: batching — models repriced per provider-day
    per_pd = changes.groupby(["provider_name", "dt"])["model_id"].nunique()
    # F3: hour concentration — normalized entropy of change hours (1 = uniform)
    hour_counts = changes["hour"].value_counts(normalize=True)
    entropy = float(-(hour_counts * np.log(hour_counts)).sum() / np.log(24))
    top_hour_share = float(hour_counts.max())
    # F4: synchrony — providers moving the same model the same day
    per_md = changes.groupby(["model_id", "dt"])["provider_name"].nunique()

    summary = {
        "evidence_status": "provisional_descriptive",
        "n_change_events": int(len(changes)),
        "f1_round_number_clustering": {
            **rounding,
            "n_quotes": int(len(latest)),
            "read": "administered prices cluster on round $/Mtok gridpoints",
        },
        "f2_provider_day_batching": {
            "median_models_per_repricing_day": float(per_pd.median()),
            "p90_models_per_repricing_day": float(per_pd.quantile(0.9)),
            "share_batch_days_ge_5_models": float((per_pd >= 5).mean()),
            "read": "mass >> 1 = catalog-wide administered updates",
        },
        "f3_hour_concentration": {
            "normalized_entropy": round(entropy, 3),
            "top_hour_share": round(top_hour_share, 3),
            "read": "entropy << 1 with a dominant hour = scheduled batch repricing",
        },
        "f4_same_model_same_day_synchrony": {
            "share_model_days_multi_provider_moves": float((per_md >= 2).mean()),
            "n_model_days_with_changes": int(len(per_md)),
            "read": "high share = follow-the-leader within a day",
        },
        "claim_boundary": (
            "Signatures indicate administered (menu/batch) price setting vs continuous "
            "market clearing; they cannot distinguish cost-based batch updates from "
            "strategic ones. Hour concentration partially reflects our capture cadence "
            "for sub-hourly timing."
        ),
    }
    save_json(summary, out_dir, "cbh6_summary")
    return summary
