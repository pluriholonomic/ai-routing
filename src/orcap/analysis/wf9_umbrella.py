"""WF-9 — Bos-Harrington umbrella cross-section: core-slack vs fringe-full.

If the tie at the author's price is a collusive umbrella, the tied core acts
as residual supplier (restricts output, holds slack) while the below-tie
fringe prices lower and runs at full utilization. Competitive twin: the tie
is just the competitive price and utilization is unrelated to tie membership.

Per model with an exact tie at the minimum and at least one below/around
provider: compare utilization (fortuna peak/ceiling) and rate-limit incidence
of tied vs non-tied providers.

  wf9_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    cong = data.q(
        f"""
        select model_permaslug, provider_name,
               avg(try_cast(recent_peak_rpm as double)/nullif(try_cast(capacity_ceiling_rpm as double),0)) as util,
               sum(try_cast(rate_limited_30m as double))/nullif(sum(try_cast(request_count_30m as double)),0) as rl,
               median(try_cast(price_completion as double)) as price
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where try_cast(price_completion as double) > 0
        group by 1, 2
        """
    ).df()
    rows = []
    for model, g in cong.groupby("model_permaslug"):
        if len(g) < 3:
            continue
        pmin = g["price"].min()
        g = g.assign(tied=np.isclose(g["price"], pmin, rtol=1e-9))
        if g["tied"].sum() < 2 or (~g["tied"]).sum() < 1:
            continue  # need a tie (>=2 at min) and a fringe... note: fringe is ABOVE min here
        rows.append(
            {
                "model": model,
                "core_util": float(g.loc[g["tied"], "util"].mean()),
                "fringe_util": float(g.loc[~g["tied"], "util"].mean()),
                "core_rl": float(g.loc[g["tied"], "rl"].mean()),
                "fringe_rl": float(g.loc[~g["tied"], "rl"].mean()),
                "n_core": int(g["tied"].sum()),
                "n_fringe": int((~g["tied"]).sum()),
            }
        )
    df = pd.DataFrame(rows).dropna(subset=["core_util", "fringe_util"])
    if len(df) < 8:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(df)}/8 tied hot models"}
        save_json(summary, out_dir, "wf9_summary")
        return summary
    diff = df["fringe_util"] - df["core_util"]
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_models": int(len(df)),
        "median_core_utilization": round(float(df["core_util"].median()), 3),
        "median_fringe_utilization": round(float(df["fringe_util"].median()), 3),
        "share_models_fringe_hotter": round(float((diff > 0).mean()), 3),
        "note_on_direction": (
            "classic Bos-Harrington puts the fringe BELOW the cartel price; here ties "
            "are at the minimum, so the 'fringe' is the above-tie tail — umbrella logic "
            "then predicts the CORE (tied, price-competitive) runs hot and the expensive "
            "tail slack UNDER COMPETITION, while a collusive residual-supplier core "
            "predicts core-slack. Read: core-slack + fringe-hot = collusion cell."
        ),
        "claim_boundary": (
            "Hot-model panel; fortuna utilization is router-estimated; quality "
            "differences across tie membership uncontrolled."
        ),
    }
    save_json(summary, out_dir, "wf9_summary")
    return summary
