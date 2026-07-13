"""CBH-9 (was H78) — Bessembinder-Lemmon v2: skewness-signed GPU forward premium (gated).

B-L (JF 2002): for non-storables, forward premium = a·Var(spot) + b·Skew(spot)
with a<0, b>0; Longstaff-Wang (JF 2004) confirm empirically on PJM. The
Douglas-Popova (2008) translation: aggregate provider overcapacity (our ED
buffer measure) plays gas-storage's premium-compressing role. Prediction P4:
the backwardation→contango flip (H35/H36 anchors: 1y H100 $1.70 Oct-25 →
$2.35 Mar-26) is dated by the sign change in conditional skewness of spot.

Gates on >= 60 daily spot observations for conditional moments. Reports the
coverage clock and current descriptive moments meanwhile.

  h78_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

MIN_SPOT_DAYS = 60


def spot_daily() -> pd.DataFrame:
    return data.q(
        f"""
        select cast(dt as varchar) as dt,
               median(try_cast(dph_base as double) / greatest(num_gpus, 1)) as spot
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}', union_by_name=true)
        where gpu_name like '%H100%' and offer_type = 'on-demand' and rentable
        group by 1 order by 1
        """
    ).df()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    spot = spot_daily().dropna()
    n = len(spot)
    desc = {}
    if n >= 5:
        r = np.diff(np.log(spot["spot"].to_numpy()))
        desc = {
            "spot_latest": float(spot["spot"].iloc[-1]),
            "dlog_std": round(float(np.std(r, ddof=1)), 4) if len(r) > 2 else None,
            "dlog_skew_preliminary": round(float(pd.Series(r).skew()), 3) if len(r) > 3 else None,
        }
    summary = {
        "evidence_status": "power_gated",
        "gate": f"conditional moments need {MIN_SPOT_DAYS} daily spot obs; have {n}",
        "spot_days": int(n),
        "descriptive": desc,
        "pre_registered_tests": {
            "premium_regression": "forward premium on rolling Var and Skew of spot (a<0, b>0)",
            "storability_proxy": "aggregate ED-buffer share compresses premium (Douglas-Popova)",
            "flip_dating": "backwardation→contango flip coincides with skewness sign change",
            "maturation": "premium magnitude decays as CME/ICE listings mature (Haugom-Ullrich)",
        },
        "anchors": {"2025-10-15": {"fwd_1y": 1.70, "spot": 1.95}, "2026-03-15": {"fwd_1y": 2.35, "spot": 2.18}},
    }
    save_json(summary, out_dir, "cbh9_summary")
    return summary
