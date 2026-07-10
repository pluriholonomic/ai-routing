"""H41 — auditable common-metric panel for DeFi and open-compute sources.

This is intentionally a coverage-and-estimand panel, not a forced common price
index. It reports only metrics that have the same economic interpretation
within a source family and labels the cross-market comparison provisional until
matched instrument/quality cohorts accumulate.
"""

import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

COLUMNS = ["dt", "market", "source", "metric", "value", "n_observations"]
MARKETS = {
    "defillama": "defi_aggregate",
    "cow": "defi_rfq",
    "uniswap": "defi_amm",
    "golem": "decentralized_compute",
    "akash": "decentralized_compute",
}


def _table(name: str, columns: str) -> pd.DataFrame:
    try:
        return data.q(f"select {columns} from read_parquet('{data.table_glob(name)}')").df()
    except Exception as exc:
        log.info("H41 table %s unavailable: %s", name, exc)
        return pd.DataFrame()


def metric_panel(
    participants: pd.DataFrame,
    executions: pd.DataFrame,
    quotes: pd.DataFrame,
    capacity: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []
    if not participants.empty:
        for (dt, source), group in participants.groupby(["dt", "source"]):
            rows.extend(
                [
                    _row(dt, source, "participants", group["participant_id"].nunique(), len(group)),
                    _row(dt, source, "median_reported_value", group["value"].median(), len(group)),
                ]
            )
    if not executions.empty:
        for (dt, source), group in executions.groupby(["dt", "source"]):
            rows.extend(
                [
                    _row(dt, source, "executions", len(group), len(group)),
                    _row(dt, source, "execution_success_rate", group["success"].mean(), len(group)),
                ]
            )
    if not quotes.empty:
        for (dt, source), group in quotes.groupby(["dt", "source"]):
            rows.extend(
                [
                    _row(dt, source, "quotes", len(group), len(group)),
                    _row(dt, source, "median_depth_usd", group["depth_usd"].median(), len(group)),
                ]
            )
    if not capacity.empty:
        for (dt, source), group in capacity.groupby(["dt", "source"]):
            rows.extend(
                [
                    _row(
                        dt,
                        source,
                        "capacity_participants",
                        group["participant_id"].nunique(),
                        len(group),
                    ),
                    _row(dt, source, "reported_capacity", group["total"].sum(), len(group)),
                ]
            )
    return pd.DataFrame(rows, columns=COLUMNS)


def _row(dt: str, source: str, metric: str, value, n: int) -> dict:
    return {
        "dt": str(dt),
        "market": MARKETS.get(source, "unknown"),
        "source": source,
        "metric": metric,
        "value": float(value) if pd.notna(value) else None,
        "n_observations": int(n),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    participants = _table("market_participants", "dt, source, participant_id, value")
    executions = _table("market_executions", "dt, source, success")
    quotes = _table("market_quotes", "dt, source, depth_usd")
    capacity = _table("market_capacity", "dt, source, participant_id, total")
    panel = metric_panel(participants, executions, quotes, capacity)
    save(panel, out_dir, "h41_market_comparison")
    sources = sorted(panel["source"].unique()) if not panel.empty else []
    summary = {
        "sources_observed": sources,
        "markets_observed": sorted(panel["market"].unique()) if not panel.empty else [],
        "metrics_observed": sorted(panel["metric"].unique()) if not panel.empty else [],
        "comparison_status": (
            "provisional: source metrics observed; matched executable cohorts remain gated"
            if sources
            else "gated: no canonical market-source tables available"
        ),
        "required_next": [
            "finalized Uniswap depth and swap events",
            "market-wide CoW auction/settlement feed",
            "normalized Akash and Golem capacity snapshots",
        ],
    }
    save_json(summary, out_dir, "h41_summary")
    return summary
