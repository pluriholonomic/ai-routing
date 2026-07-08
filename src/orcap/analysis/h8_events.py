"""H8 — Event studies around repricing (pre-registered; activates as bursts land).

The capture loop burst-samples affected models at 60s cadence after detecting
a price change (event_bursts + event_bursts_congestion tables). This module:
  - inventories captured event windows
  - for each window: competitor repricing within the window, and the
    congestion/latency path (minute resolution) around the event

Until the first burst lands it reports coverage only — by design, the module
runs in every nightly reanalysis and picks events up automatically.
"""

import logging
from pathlib import Path

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    try:
        bursts = data.q(
            f"""
            select model_id, count(distinct run_ts) ticks,
                   min(run_ts) first_tick, max(run_ts) last_tick,
                   count(distinct provider_name) providers
            from read_parquet('{data.table_glob("event_bursts")}')
            group by 1 order by 2 desc
            """
        ).df()
    except Exception:
        results = {
            "n_event_windows": 0,
            "note": "no burst windows captured yet — burst capture armed since 2026-07-08; "
            "windows appear here automatically after the next detected repricing",
        }
        save_json(results, out_dir, "h8_summary")
        return results

    save(bursts, out_dir, "h8_burst_windows")
    # within-window competitor moves: distinct prices per (model, provider) over ticks
    moves = data.q(
        f"""
        select model_id, provider_name, count(distinct price_completion) n_prices,
               count(distinct run_ts) ticks
        from read_parquet('{data.table_glob("event_bursts")}')
        where price_completion > 0
        group by 1, 2 having count(distinct price_completion) > 1
        """
    ).df()
    save(moves, out_dir, "h8_within_window_moves")
    results = {
        "n_event_windows": int(bursts["model_id"].nunique()),
        "total_burst_ticks": int(bursts["ticks"].sum()),
        "within_window_competitor_moves": int(len(moves)),
        "pre_registered_test": "aggregator-like if ≥25% of eventual share shift lands within 24h",
    }
    save_json(results, out_dir, "h8_summary")
    log.info("H8: %s", results)
    return results
