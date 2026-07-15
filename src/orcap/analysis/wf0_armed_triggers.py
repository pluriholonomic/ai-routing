"""WF-0 — Armed triggers for the event-gated framework tests.

  wf1  pass-through at large cost shocks (ABS vs menu-cost): fires when the
       H100-class spot index moves >20% within 30d or a new GPU generation
       reprices the cost base; monitors gpu_offers_snapshots.
  wf8  capacity ~ derank-severity comovement: fires at >=10 derank
       transitions (congestion panel).
  wf10 merger amplification: fires on any provider M&A announcement
       (manual/news trigger).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    spot = data.q(
        f"""
        select cast(dt as varchar) as dt,
               median(try_cast(dph_base as double)/greatest(num_gpus,1)) as p
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}', union_by_name=true)
        where gpu_name like '%H100%' and offer_type = 'on-demand' and rentable
        group by 1 order by 1
        """
    ).df()
    move_30d = None
    if len(spot) >= 2:
        move_30d = float(abs(np.log(spot["p"].iloc[-1] / spot["p"].iloc[0])))
    deranks = data.q(
        f"""
        with x as (select endpoint_uuid, run_ts, cast(is_deranked as boolean) d,
          lag(cast(is_deranked as boolean)) over (partition by endpoint_uuid order by run_ts) pd
          from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true))
        select count(*) filter (where d and not pd) n from x
        """
    ).df()["n"].iloc[0]
    summary = {
        "wf1_cost_shock": {
            "trigger": "abs dlog H100 spot > 0.20 within 30d",
            "current_window_move": round(move_30d, 4) if move_30d is not None else None,
            "armed": bool(move_30d is not None and move_30d < 0.20),
        },
        "wf8_derank_comovement": {
            "trigger": ">= 10 derank transitions",
            "transitions_observed": int(deranks),
            "armed": bool(deranks < 10),
        },
        "wf10_merger": {"trigger": "provider M&A event (manual)", "armed": True},
    }
    save_json(summary, out_dir, "wf0_armed_triggers")
    return summary
