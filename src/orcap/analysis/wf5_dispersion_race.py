"""WF-5 — Dispersion horse race: commitment asymmetry vs loyal flow.

Two theories of the gap floor (why the 2nd-cheapest sits ~8% above min even
at high N): Brown-MacKay commitment (the slow firm rationally sits high; gap
should track the CADENCE GAP between the two cheapest) vs clearinghouse loyal
flow (pinned demand funds it; gap should track demand concentration /
non-shopped share). Rank regression per model:

  gap_pct ~ cadence_gap(two cheapest) + demand_hhi + n_providers

  wf5_summary.json
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


def provider_cadence() -> pd.Series:
    ch = data.q(
        f"""
        select provider_name, count(*) as n
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion'
        group by 1
        """
    ).df()
    return ch.set_index("provider_name")["n"]


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quotes = daily_quotes()
    cadence = provider_cadence()
    shares = demand_shares()
    hhi = (
        shares.groupby(["model_id", "dt"])
        .apply(
            lambda g: float(((g["tokens"] / g["tokens"].sum()) ** 2).sum()),
            include_groups=False,
        )
        .rename("hhi")
        .reset_index()
    )
    rows = []
    for (model, dt), g in quotes.groupby(["model_id", "dt"]):
        if len(g) < 3:
            continue
        g = g.sort_values("price").reset_index(drop=True)
        if g["price"].iloc[0] <= 0:
            continue
        gap = 100.0 * (g["price"].iloc[1] - g["price"].iloc[0]) / g["price"].iloc[0]
        c0 = cadence.get(g["provider_name"].iloc[0], 0)
        c1 = cadence.get(g["provider_name"].iloc[1], 0)
        rows.append(
            {
                "model_id": model,
                "dt": dt,
                "gap_pct": gap,
                "cadence_gap": float(c0 - c1),  # fast cheapest minus slower second
                "abs_cadence_gap": float(abs(c0 - c1)),
                "n_providers": len(g),
            }
        )
    df = pd.DataFrame(rows).merge(hhi, on=["model_id", "dt"], how="left").dropna()
    df = df[df["gap_pct"] > 0.01]  # the race is about the non-tied segment
    if len(df) < 60:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(df)}/60 non-tied model-days"}
        save_json(summary, out_dir, "wf5_summary")
        return summary
    r = df[["gap_pct", "abs_cadence_gap", "hhi", "n_providers"]].rank()
    X = np.column_stack([r["abs_cadence_gap"], r["hhi"], r["n_providers"], np.ones(len(r))])
    beta, *_ = np.linalg.lstsq(X, r["gap_pct"].to_numpy(), rcond=None)
    # model-level block bootstrap
    rng = np.random.default_rng(5)
    models = df["model_id"].unique()
    draws = []
    for _ in range(300):
        pick = rng.choice(models, len(models), replace=True)
        b = pd.concat([df[df["model_id"] == m] for m in pick])
        rb = b[["gap_pct", "abs_cadence_gap", "hhi", "n_providers"]].rank()
        Xb = np.column_stack([rb["abs_cadence_gap"], rb["hhi"], rb["n_providers"], np.ones(len(rb))])
        bb, *_ = np.linalg.lstsq(Xb, rb["gap_pct"].to_numpy(), rcond=None)
        draws.append(bb[:2])
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_nontied_model_days": int(len(df)),
        "rank_beta_cadence_gap": round(float(beta[0]), 3),
        "cadence_ci95": [round(float(lo[0]), 3), round(float(hi[0]), 3)],
        "rank_beta_demand_hhi": round(float(beta[1]), 3),
        "hhi_ci95": [round(float(lo[1]), 3), round(float(hi[1]), 3)],
        "read": (
            "cadence beta > 0 with hhi ~ 0 = Brown-MacKay commitment funds the gap; "
            "hhi beta > 0 with cadence ~ 0 = loyal/pinned flow funds it; both = mixed"
        ),
        "claim_boundary": (
            "Cadence measured on an ~11-day window (coarse classes); demand HHI is a "
            "proxy for pinned share, not a measurement of it; non-tied segment only."
        ),
    }
    save_json(summary, out_dir, "wf5_summary")
    return summary
