"""CBH-8 (was H77) — Rockets and feathers: asymmetric GPU-cost pass-through (gated).

Borenstein-Cameron-Gilbert (QJE 1997) / Peltzman (JPE 2000): retail prices
rise faster after cost increases than they fall after decreases. Retail-
electricity benchmark: 43-47% pass-through with a volatility-loaded markup
(Zarnikau-Woo 2020). Administered/strategic alternative: pass-through ~ 0
with repricing timed to competitor/model events.

Full asymmetric ECM gates on >= 90 overlapping daily observations of both a
token price index and a GPU rental index. Until then this module reports the
coverage clock and the coarse period-level correlation (from H7's segments).

  h77_summary.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

MIN_OVERLAP_DAYS = 90


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    gpu_days = data.q(
        f"""
        select count(distinct cast(dt as varchar)) as d
        from read_parquet('{data.table_glob("gpu_price_indices")}', union_by_name=true)
        """
    ).df()["d"].iloc[0]
    token_days = data.q(
        f"""
        select count(distinct cast(dt as varchar)) as d
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        """
    ).df()["d"].iloc[0]
    h7_path = Path(out_dir) / "h7_summary.json"
    coarse = None
    if h7_path.exists():
        h7 = json.loads(h7_path.read_text())
        coarse = {
            seg: {
                "corr_dlog": round(float(v["corr_dlog"]), 3),
                "n_periods": v["n_periods"],
            }
            for seg, v in h7.get("by_segment", {}).items()
            if isinstance(v, dict) and "corr_dlog" in v
        }
    overlap = int(min(gpu_days, token_days))
    summary = {
        "evidence_status": "power_gated",
        "gate": f"asymmetric ECM needs {MIN_OVERLAP_DAYS} overlapping daily obs; have {overlap}",
        "overlap_days": overlap,
        "coarse_period_correlations_h7": coarse,
        "pre_registered_tests": {
            "ecm": "Δp_token on lags of Δc_gpu⁺ and Δc_gpu⁻ + ECM term, daily and weekly",
            "hypotheses": {
                "rockets_and_feathers": "Σβ⁺ > Σβ⁻ at 2-8wk horizons",
                "retail_electricity": "β ≈ 0.4-0.5 with volatility-loaded markup",
                "administered": "β ≈ 0 both directions; changes cluster on model/competitor events",
                "quality_ladder": "pass-through via new-model introduction, not incumbent repricing",
            },
        },
    }
    save_json(summary, out_dir, "cbh8_summary")
    return summary
