"""CBH-2 (was H71) — Baye-Morgan gap(N) curve: dispersion between the two cheapest quotes.

Benchmark (Baye-Morgan-Scholten 2004, Shopper.com): gap between the two lowest
posted prices averages 22% with N=2 sellers, falling to 3.5% at N=17, and
never converges to the law of one price. Clearinghouse equilibria sustain
dispersion through 'loyal' (price-insensitive) traffic.

Compute Brokerage Hypothesis prediction Q3: quality-adjusted gap stays >= ~3%
at every N — the pinned/BYOK share funds it. Bertrand-commodity alternative:
gap -> 0 for N >= 3 because the router automates shopping.

  h71_gap_by_n.parquet    per-N: mean/median gap, n obs
  h71_summary.json        curve + benchmark comparison
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes

log = logging.getLogger(__name__)


def gaps(quotes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model, dt), g in quotes.groupby(["model_id", "dt"]):
        p = np.sort(g["price"].to_numpy())
        if len(p) < 2 or p[0] <= 0:
            continue
        rows.append(
            {
                "model_id": model,
                "dt": dt,
                "n_providers": len(p),
                "gap_pct": 100.0 * (p[1] - p[0]) / p[0],
                "range_pct": 100.0 * (p[-1] - p[0]) / p[0],
            }
        )
    return pd.DataFrame(rows)


BMS_BENCHMARK = {2: 22.0, 17: 3.5}  # Baye-Morgan-Scholten 2004


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    day = gaps(daily_quotes())
    if day.empty:
        summary = {"evidence_status": "power_gated", "gate": "no multi-provider model-days"}
        save_json(summary, out_dir, "cbh2_summary")
        return summary
    day["n_bucket"] = day["n_providers"].clip(upper=15)
    curve = (
        day.groupby("n_bucket")
        .agg(
            mean_gap_pct=("gap_pct", "mean"),
            median_gap_pct=("gap_pct", "median"),
            share_gap_lt_1pct=("gap_pct", lambda s: float((s < 1.0).mean())),
            mean_range_pct=("range_pct", "mean"),
            n_model_days=("gap_pct", "size"),
        )
        .reset_index()
    )
    save(curve, out_dir, "cbh2_gap_by_n")
    lo = day[day["n_providers"] == 2]
    hi = day[day["n_providers"] >= 10]
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_model_days": int(len(day)),
        "n_models": int(day["model_id"].nunique()),
        "gap_at_n2_median_pct": float(lo["gap_pct"].median()) if len(lo) else None,
        "gap_at_n10plus_median_pct": float(hi["gap_pct"].median()) if len(hi) else None,
        "share_exact_tie_at_min": float((day["gap_pct"] < 0.01).mean()),
        "curve": curve.to_dict("records"),
        "benchmark_bms2004": BMS_BENCHMARK,
        "prediction_q3": "quality-unadjusted gap floor >= ~3% at high N (clearinghouse); "
        "Bertrand alternative: gap -> 0 for N >= 3",
        "claim_boundary": (
            "Posted completion quotes, standard variants, not quality-adjusted; a nonzero "
            "gap can reflect quality differentiation as well as loyal-flow rents. The "
            "quality-adjusted version gates on the fingerprint probe panel."
        ),
    }
    save_json(summary, out_dir, "cbh2_summary")
    return summary
