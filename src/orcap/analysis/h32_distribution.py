"""H32b — Distributional price dynamics: the quote distribution F_mt(p) as the
macro object.

Builds the model×run quantile panel (min/p25/median/p75/p95, n quotes) from
endpoints_snapshots at 5-min resolution, plus daily aggregates. First
diagnostics: which margin moves — phase-1 evidence says the min (wars,
entrants) while p95 is inert, i.e. distributions compress from below.
The DFL-style decomposition (repricing vs composition vs reweighting) joins
as events accumulate; see docs/elasticity-plan.md.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def build_quantile_panel() -> pd.DataFrame:
    return data.q(
        f"""
        select run_ts, cast(dt as varchar) as dt, model_id,
               count(*) as n_quotes,
               min(price_completion) as p_min,
               quantile_cont(price_completion, 0.25) as p25,
               median(price_completion) as p50,
               quantile_cont(price_completion, 0.75) as p75,
               quantile_cont(price_completion, 0.95) as p95
        from read_parquet('{data.table_glob("endpoints_snapshots")}')
        where price_completion > 0 and model_id not like '%:%'
        group by 1, 2, 3
        having count(*) >= 2
        """
    ).df()


def margin_activity(panel: pd.DataFrame) -> dict:
    """Which quantile moves? Share of run-over-run changes per functional."""
    panel = panel.sort_values(["model_id", "run_ts"])
    out = {}
    for q in ["p_min", "p25", "p50", "p75", "p95"]:
        prev = panel.groupby("model_id")[q].shift()
        moved = (panel[q] != prev) & prev.notna()
        out[q] = float(moved.mean())
    return out


def compression(panel: pd.DataFrame) -> pd.DataFrame:
    """Daily model-level dispersion functionals (for compression-from-below)."""
    daily = (
        panel.groupby(["dt", "model_id"])
        .agg(
            p_min=("p_min", "median"),
            p50=("p50", "median"),
            p95=("p95", "median"),
            n_quotes=("n_quotes", "median"),
        )
        .reset_index()
    )
    daily["p95_over_min"] = daily["p95"] / daily["p_min"]
    daily["min_over_p50"] = daily["p_min"] / daily["p50"]
    return daily


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = build_quantile_panel()
    save(panel, out_dir, "h32_quantile_panel")
    daily = compression(panel)
    save(daily, out_dir, "h32_daily_dispersion")

    act = margin_activity(panel)
    # case study: the most price-active model by min-quote variance
    var_by_model = (
        panel.groupby("model_id")["p_min"].agg(lambda s: float(np.std(np.log(s)))).sort_values()
    )
    hot = var_by_model.index[-1] if len(var_by_model) else None
    hot_path = None
    if hot:
        h = daily[daily["model_id"] == hot].sort_values("dt")
        hot_path = {
            "model": hot,
            "min_path": [round(v * 1e6, 3) for v in h["p_min"]],
            "p95_path": [round(v * 1e6, 3) for v in h["p95"]],
            "days": list(h["dt"]),
        }
    results = {
        "n_model_runs": int(len(panel)),
        "n_models": int(panel["model_id"].nunique()),
        "share_of_runs_each_margin_moved": {k: round(v, 5) for k, v in act.items()},
        "median_p95_over_min": float(daily["p95_over_min"].median()),
        "most_active_model": hot_path,
        "note": "DFL decomposition (repricing vs composition vs reweighting) gates on events",
    }
    save_json(results, out_dir, "h32_summary")
    log.info(
        "H32: %s models, margins moved %s",
        results["n_models"],
        results["share_of_runs_each_margin_moved"],
    )
    return results
