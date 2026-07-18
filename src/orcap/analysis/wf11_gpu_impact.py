"""WF-11 — The GPU spot book's impact curve and the overflow-sourcing cost.

A provider whose demand burst exceeds owned capacity must source on the GPU
rental spot market. That market has an observable ORDER BOOK (vast.ai offer
ladder), so the marginal-sourcing cost is not 'the spot price' but the
walk-the-book fill — a market-impact cost in the Kyle sense. This module
computes the daily impact curve per GPU class and the token-margin breakeven
it implies, and registers the cross-market test: provider rationing (429s)
should intensify when the book is thin (impact high), demand held fixed —
rationing as the rational alternative to paying impact at a fixed menu price.

  wf11_impact_curve.parquet   per day x class: fill price at k GPUs
  wf11_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

SIZES = (8, 40, 100, 300, 800)
CLASSES = ("H100", "A100", "RTX 4090")


def book(dt: str | None, gpu_like: str, offer_type: str) -> pd.DataFrame:
    price_col = "dph_base" if offer_type == "on-demand" else "min_bid"
    where_dt = f"and cast(dt as varchar) = '{dt}'" if dt else ""
    df = data.q(
        f"""
        select cast(dt as varchar) as dt,
               try_cast({price_col} as double)/greatest(num_gpus,1) as px, num_gpus
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}', union_by_name=true)
        where gpu_name like '%{gpu_like}%' and offer_type = '{offer_type}' and rentable
        {where_dt}
        """
    ).df().dropna()
    return df[df["px"].between(0.05, 30)]


def walk(day_book: pd.DataFrame, k: int) -> tuple[float, float] | None:
    b = day_book.sort_values("px").reset_index(drop=True)
    cum = b["num_gpus"].cumsum()
    m = cum >= k
    if not m.any():
        return None
    i = int(m.idxmax())
    take = b.iloc[: i + 1]
    fill = float((take["px"] * take["num_gpus"]).sum() / take["num_gpus"].sum())
    return fill, float(b["px"].iloc[i])


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = []
    for cls in CLASSES:
        od = book(None, cls, "on-demand")
        for dt, day_book in od.groupby("dt"):
            best = float(day_book["px"].min())
            for k in SIZES:
                w = walk(day_book, k)
                if w:
                    rows.append(
                        {
                            "dt": dt,
                            "gpu_class": cls,
                            "k_gpus": k,
                            "best_ask": best,
                            "avg_fill": w[0],
                            "marginal_ask": w[1],
                            "impact_pct": 100.0 * (w[0] / best - 1.0),
                        }
                    )
    df = pd.DataFrame(rows)
    if df.empty:
        summary = {"evidence_status": "power_gated", "gate": "no offer books"}
        save_json(summary, out_dir, "wf11_summary")
        return summary
    save(df, out_dir, "wf11_impact_curve")
    latest = df[df["dt"] == df["dt"].max()]
    h100 = latest[latest["gpu_class"] == "H100"].set_index("k_gpus")
    # token-margin breakeven: serve overflow iff posted p >= fill/theta,
    # theta = millions of tokens per GPU-hour (reported as a grid, not assumed)
    breakeven = {}
    if 300 in h100.index:
        fill = h100.loc[300, "avg_fill"]
        breakeven = {
            f"theta_{t}M_tok_per_gpu_hr": round(fill / t, 3) for t in (1, 3, 10)
        }
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_day_class_sizes": int(len(df)),
        "latest_h100": h100[["best_ask", "avg_fill", "impact_pct"]].round(3).to_dict("index")
        if len(h100)
        else None,
        "impact_stability": {
            cls: round(float(df[(df.gpu_class == cls) & (df.k_gpus == 300)]["impact_pct"].median()), 1)
            for cls in CLASSES
            if len(df[(df.gpu_class == cls) & (df.k_gpus == 300)])
        },
        "overflow_breakeven_usd_per_mtok_at_300gpus": breakeven,
        "registered_test": (
            "cross-market rationing: provider 429 incidence rises with same-day book "
            "impact (thinness), demand controls included — rationing as the rational "
            "alternative to paying impact at a fixed menu price; gates on 30 joint days"
        ),
        "claim_boundary": (
            "Vast.ai book only (one venue; hyperscaler/neocloud reserved capacity "
            "unobserved); walking the book ignores multi-GPU node constraints and "
            "geographic/interconnect requirements, so impact is a LOWER bound for "
            "training-grade sourcing and an approximation for inference-grade."
        ),
    }
    save_json(summary, out_dir, "wf11_summary")
    return summary
