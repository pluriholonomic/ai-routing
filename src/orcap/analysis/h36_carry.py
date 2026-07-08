"""H36 — The carry trade as an inefficiency meter.

Compute is non-storable, so the executable cash-and-carry is:
  SHORT the tenor-T forward at F, deliver by ROLLING SPOT purchases over
  [t, t+T]. P&L per GPU-hour = F − avg(spot path) − frictions.

Frictions band (the no-arb tolerance): delivery must be contract-grade —
we price the spot leg at marketplace ON-DEMAND (not interruptible), and
report the quality band up to the hyperscaler segment. Persistent P&L outside
the band = inefficiency; its sign estimates the forward risk premium
(commodity-carry literature: hedgers pay speculators).

Inputs: data-static/gpu_forward_anchors.csv (F observations; Compute Desk /
SemiAnalysis / AIX curves drop in), Silicon Data segment history + our
vast.ai capture (realized spot path). Nightly: marks open positions to
market as the spot capture extends the path.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h35_term import ANCHORS, SPOT_HIST, TENOR_YEARS

log = logging.getLogger(__name__)


def daily_spot_path() -> pd.DataFrame:
    """Marketplace on-demand H100 $/hr, daily: SD periods expanded + our capture."""
    frames = []
    if SPOT_HIST.exists():
        sd = pd.read_csv(SPOT_HIST, parse_dates=["period_start", "period_end"])
        sd = sd[sd["segment"] == "marketplace"]
        for r in sd.itertuples(index=False):
            days = pd.date_range(r.period_start, r.period_end, freq="D")
            frames.append(pd.DataFrame({"day": days, "spot": r.usd_hr, "src": "silicondata"}))
    ours = data.q(
        f"""
        select cast(dt as date) as day, median(dph_total) as spot
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}')
        where gpu_class = 'H100 SXM' and offer_type = 'on-demand' and num_gpus = 1
        group by 1
        """
    ).df()
    ours["day"] = pd.to_datetime(ours["day"])
    ours["src"] = "orcap_vast"
    frames.append(ours)
    path = pd.concat(frames, ignore_index=True)
    return path.sort_values("day").drop_duplicates("day", keep="last")


def carry_book(spot: pd.DataFrame) -> pd.DataFrame:
    if not ANCHORS.exists():
        return pd.DataFrame()
    fwd = pd.read_csv(ANCHORS, parse_dates=["obs_date"])
    today = spot["day"].max()
    rows = []
    for r in fwd.itertuples(index=False):
        tenor_y = TENOR_YEARS.get(r.tenor, 1.0)
        end = r.obs_date + pd.Timedelta(days=int(365 * tenor_y))
        window = spot[(spot["day"] >= r.obs_date) & (spot["day"] <= min(end, today))]
        if window.empty:
            continue
        realized = float(window["spot"].mean())
        coverage = len(window) / max(1, (min(end, today) - r.obs_date).days + 1)
        entry_spot = (
            float(spot[spot["day"] <= r.obs_date]["spot"].iloc[-1])
            if len(spot[spot["day"] <= r.obs_date])
            else np.nan
        )
        rows.append(
            {
                "entered": str(r.obs_date)[:10],
                "gpu_class": r.gpu_class,
                "tenor": r.tenor,
                "forward": float(r.usd_hr),
                "entry_spot": entry_spot,
                "ex_ante_carry_pct": round(100 * (r.usd_hr / entry_spot - 1), 1)
                if entry_spot
                else None,
                "realized_avg_spot": round(realized, 3),
                "path_coverage": round(coverage, 2),
                "status": "closed" if today >= end else "open (marked to date)",
                "short_fwd_pnl_per_hr": round(float(r.usd_hr) - realized, 3),
                "short_fwd_pnl_pct": round(100 * (r.usd_hr - realized) / r.usd_hr, 1),
            }
        )
    return pd.DataFrame(rows)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    spot = daily_spot_path()
    book = carry_book(spot)
    save(book, out_dir, "h36_carry_book")
    save(spot, out_dir, "h36_spot_path")
    if book.empty:
        return {"note": "no forward anchors"}
    # quality/friction band: marketplace->hyperscaler spread bounds the SLA premium
    band = None
    if SPOT_HIST.exists():
        sd = pd.read_csv(SPOT_HIST)
        last_h = sd[sd["segment"] == "hyperscaler"]["usd_hr"].iloc[-1]
        last_m = sd[sd["segment"] == "marketplace"]["usd_hr"].iloc[-1]
        band = round(float(last_h / last_m - 1) * 100, 1)
    results = {
        "positions": book.to_dict("records"),
        "mean_abs_short_pnl_pct": float(book["short_fwd_pnl_pct"].abs().mean()),
        "inefficiency_read": (
            "persistent |PnL| beyond the delivery-quality band = inefficiency; "
            "signed mean = forward risk premium"
        ),
        "quality_band_marketplace_to_hyperscaler_pct": band,
        "n_positions": int(len(book)),
        "executability_note": (
            "hypothetical until AIX/ComputeConnect EFP go live; then this book is tradeable"
        ),
    }
    save_json(results, out_dir, "h36_summary")
    log.info("H36: %s", results["positions"])
    return results
