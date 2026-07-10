"""H56 — verified block-pinned Uniswap V3 initialized-tick snapshots.

H56 makes the collector's complete TickLens state visible without promoting
virtual liquidity into dollar depth, an executable quote, or a market-wide
order book. A snapshot enters the panel only when its source-run ledger says
every registered pool and every usable bitmap word completed at one finalized
block.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

PANEL_COLUMNS = [
    "run_ts",
    "dt",
    "pool_id",
    "pool_map_id",
    "block_number",
    "current_tick",
    "active_liquidity_raw",
    "metric",
    "value",
    "n_ticks",
]
MIN_SNAPSHOT_DAYS = 7
MIN_SNAPSHOTS = 20


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=PANEL_COLUMNS)


def _load(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def complete_snapshot_manifests(source_runs: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Return full source-run keys and their certified initialized-tick row counts."""
    required = {"run_ts", "dt", "source", "status", "detail_json"}
    if source_runs.empty or not required.issubset(source_runs.columns):
        return {}
    result = {}
    candidates = source_runs[
        source_runs["source"].eq("uniswap_tick_book") & source_runs["status"].eq("success")
    ]
    for row in candidates.itertuples(index=False):
        try:
            detail = json.loads(row.detail_json)
            pool_details = detail["pool_details"]
            expected_rows = int(detail["initialized_tick_rows"])
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if detail.get("coverage_complete") is not True or not isinstance(pool_details, dict):
            continue
        if expected_rows < 0 or not pool_details or not all(
            isinstance(pool, dict) and pool.get("complete") is True
            for pool in pool_details.values()
        ):
            continue
        try:
            per_pool_rows = sum(
                int(pool["initialized_tick_rows"]) for pool in pool_details.values()
            )
        except (KeyError, TypeError, ValueError):
            continue
        if per_pool_rows != expected_rows:
            continue
        run_ts, dt = getattr(row, "run_ts", None), getattr(row, "dt", None)
        if run_ts is not None and dt is not None:
            result[(str(run_ts), str(dt))] = expected_rows
    return result


def complete_snapshot_keys(source_runs: pd.DataFrame) -> set[tuple[str, str]]:
    """Return source-run keys certified as a full registered-pool tick book."""
    return set(complete_snapshot_manifests(source_runs))


def tick_book_panel(
    ticks: pd.DataFrame,
    complete_keys: set[tuple[str, str]],
    expected_rows: dict[tuple[str, str], int] | None = None,
) -> pd.DataFrame:
    """Summarize only source-ledger-verified, complete pool snapshots."""
    required = {"run_ts", "dt", "pool_id", "block_number", "tick"}
    if ticks.empty or not required.issubset(ticks.columns) or not complete_keys:
        return _empty()
    frame = ticks.copy()
    keys = list(zip(frame["run_ts"].astype(str), frame["dt"].astype(str), strict=True))
    frame = frame.loc[[key in complete_keys for key in keys]].copy()
    if frame.empty:
        return _empty()
    if expected_rows is not None:
        frame["_snapshot_key"] = list(
            zip(frame["run_ts"].astype(str), frame["dt"].astype(str), strict=True)
        )
        observed_rows = frame.groupby("_snapshot_key").size().to_dict()
        valid_keys = {
            key
            for key, count in observed_rows.items()
            if expected_rows.get(key) == int(count)
        }
        frame = frame.loc[frame["_snapshot_key"].isin(valid_keys)].copy()
        if frame.empty:
            return _empty()
    for column in ("tick", "current_tick", "block_number"):
        frame[column] = (
            pd.to_numeric(frame[column], errors="coerce")
            if column in frame
            else pd.Series(float("nan"), index=frame.index)
        )
    if "liquidity_net_raw" in frame:
        frame["liquidity_net_raw"] = frame["liquidity_net_raw"].map(
            lambda value: int(value) if pd.notna(value) else None
        )
    else:
        frame["liquidity_net_raw"] = None
    frame = frame.dropna(subset=["tick", "block_number"])
    if frame.empty:
        return _empty()
    for column in ("pool_map_id", "current_tick", "active_liquidity_raw"):
        if column not in frame:
            frame[column] = None
    rows = []
    keys = ["run_ts", "dt", "pool_id", "pool_map_id", "block_number"]
    for key, group in frame.groupby(keys, dropna=False):
        run_ts, dt, pool_id, pool_map_id, block_number = key
        unique_ticks = group.drop_duplicates("tick").copy()
        # A complete V3 initialized-tick map must sum signed liquidity deltas
        # to zero. It is a snapshot-integrity diagnostic, not a depth estimate.
        net_values = [value for value in unique_ticks["liquidity_net_raw"] if value is not None]
        current_tick = pd.to_numeric(unique_ticks["current_tick"], errors="coerce").dropna()
        active = unique_ticks["active_liquidity_raw"].dropna()
        base = {
            "run_ts": run_ts,
            "dt": dt,
            "pool_id": pool_id,
            "pool_map_id": pool_map_id,
            "block_number": int(block_number),
            "current_tick": int(current_tick.iloc[0]) if not current_tick.empty else None,
            "active_liquidity_raw": str(active.iloc[0]) if not active.empty else None,
            "n_ticks": int(len(unique_ticks)),
        }
        metrics = {
            "initialized_tick_count": int(len(unique_ticks)),
            "minimum_initialized_tick": float(unique_ticks["tick"].min()),
            "maximum_initialized_tick": float(unique_ticks["tick"].max()),
            "positive_net_liquidity_tick_count": int(sum(value > 0 for value in net_values)),
            "negative_net_liquidity_tick_count": int(sum(value < 0 for value in net_values)),
            "signed_liquidity_net_sums_to_zero": int(bool(net_values) and sum(net_values) == 0),
        }
        rows.extend(base | {"metric": metric, "value": value} for metric, value in metrics.items())
    return pd.DataFrame(rows, columns=PANEL_COLUMNS) if rows else _empty()


def coverage_gate(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "status": "not_identified",
            "snapshot_days": 0,
            "snapshots": 0,
            "minimum_snapshot_days": MIN_SNAPSHOT_DAYS,
            "minimum_snapshots": MIN_SNAPSHOTS,
        }
    snapshots = panel.loc[:, ["run_ts", "dt", "pool_id", "block_number"]].drop_duplicates()
    dates = sorted(str(value) for value in snapshots["dt"].dropna().unique())
    status = (
        "state_panel_ready"
        if len(dates) >= MIN_SNAPSHOT_DAYS and len(snapshots) >= MIN_SNAPSHOTS
        else "power_gated"
    )
    return {
        "status": status,
        "snapshot_days": len(dates),
        "snapshots": int(len(snapshots)),
        "minimum_snapshot_days": MIN_SNAPSHOT_DAYS,
        "minimum_snapshots": MIN_SNAPSHOTS,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ticks = _load("uniswap_tick_book")
    source_runs = _load("source_runs")
    manifests = complete_snapshot_manifests(source_runs)
    panel = tick_book_panel(ticks, set(manifests), manifests)
    gate = coverage_gate(panel)
    save(panel, out_dir, "h56_uniswap_tick_book")
    summary = {
        "tick_rows": int(len(ticks)),
        "verified_complete_source_runs": len(manifests),
        "coverage_gate": gate,
        "claim_boundary": (
            "H56 reports only complete, block-pinned initialized virtual-liquidity tick state "
            "for the registered Uniswap V3 pools. It does not estimate dollar executable depth, "
            "a swap traversal, a firm quote, a market-wide book, routing flow, or welfare."
        ),
    }
    save_json(summary, out_dir, "h56_summary")
    return summary
