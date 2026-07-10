"""H55 — source-bounded Akash open GPU provider-bid snapshots.

The Akash LCD exposes block-pinned on-chain provider bids. H55 summarizes the
GPU-bearing bids from the current live-GPU-provider coverage universe without
equating a bid with capacity, an order with realized demand, or a native field
with a USD rate.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

PANEL_COLUMNS = [
    "run_ts",
    "dt",
    "snapshot_height",
    "snapshot_time",
    "side",
    "metric",
    "native_price_denom",
    "value",
    "n_records",
]
MIN_SNAPSHOT_DAYS = 7
MIN_BID_SNAPSHOTS = 20


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=PANEL_COLUMNS)


def _load(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def _number(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _text(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series("", index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str)


def _rows_for_side(frame: pd.DataFrame, side: str) -> list[dict]:
    if frame.empty:
        return []
    values = frame.copy()
    values["gpu_units_total"] = _number(values, "gpu_units_total")
    values["native_price_amount"] = _number(values, "native_price_amount")
    for column in ("run_ts", "dt", "snapshot_height", "snapshot_time"):
        if column not in values:
            values[column] = None
    rows = []
    keys = ["run_ts", "dt", "snapshot_height", "snapshot_time"]
    for key, group in values.groupby(keys, dropna=False):
        run_ts, dt, height, snapshot_time = key
        def emit(
            metric: str,
            value: float | int | None,
            n_records: int,
            denom=None,
            run_ts=run_ts,
            dt=dt,
            height=height,
            snapshot_time=snapshot_time,
        ) -> None:
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "snapshot_height": height,
                    "snapshot_time": snapshot_time,
                    "side": side,
                    "metric": metric,
                    "native_price_denom": denom,
                    "value": value,
                    "n_records": n_records,
                }
            )

        emit("gpu_resource_rows", int(len(group)), int(len(group)))
        identifier = "bid_id" if side == "provider_open_bid" else "order_id"
        if identifier in group:
            emit(f"distinct_{identifier}s", int(group[identifier].nunique()), int(len(group)))
        participant = "provider" if side == "provider_open_bid" else "owner"
        if participant in group:
            emit(
                f"distinct_{participant}s",
                int(_text(group, participant).replace("", pd.NA).nunique()),
                int(len(group)),
            )
        gpu = group["gpu_units_total"].dropna()
        emit(
            "gpu_units_offered" if side == "provider_open_bid" else "gpu_units_requested",
            float(gpu.sum()) if not gpu.empty else None,
            int(gpu.notna().sum()),
        )
        priced = group.dropna(subset=["native_price_amount"]).copy()
        priced["_native_price_denom"] = _text(priced, "native_price_denom").replace("", pd.NA)
        for denom, denom_rows in priced.groupby("_native_price_denom", dropna=True):
            metric = (
                "median_native_bid_price"
                if side == "provider_open_bid"
                else "median_native_order_price_cap"
            )
            emit(
                metric,
                float(denom_rows["native_price_amount"].median()),
                int(len(denom_rows)),
                str(denom),
            )
    return rows


def market_book_panel(bids: pd.DataFrame) -> pd.DataFrame:
    """Return time-indexed source-bounded provider-bid totals and native prices."""
    rows = _rows_for_side(bids, "provider_open_bid")
    return pd.DataFrame(rows, columns=PANEL_COLUMNS) if rows else _empty()


def coverage_gate(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "status": "not_identified",
            "snapshot_days": 0,
            "bid_snapshots": 0,
            "minimum_snapshot_days": MIN_SNAPSHOT_DAYS,
            "minimum_bid_snapshots": MIN_BID_SNAPSHOTS,
        }
    snapshots = panel.loc[:, ["run_ts", "dt", "snapshot_height"]].drop_duplicates()
    dates = sorted(str(value) for value in snapshots["dt"].dropna().unique())
    bid_runs = set(panel.loc[panel["side"].eq("provider_open_bid"), "run_ts"].dropna())
    status = (
        "source_bounded_dynamic_panel_ready"
        if len(dates) >= MIN_SNAPSHOT_DAYS and len(bid_runs) >= MIN_BID_SNAPSHOTS
        else "power_gated"
    )
    return {
        "status": status,
        "snapshot_days": len(dates),
        "bid_snapshots": len(bid_runs),
        "minimum_snapshot_days": MIN_SNAPSHOT_DAYS,
        "minimum_bid_snapshots": MIN_BID_SNAPSHOTS,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    bids = _load("akash_market_open_bids")
    panel = market_book_panel(bids)
    gate = coverage_gate(panel)
    save(panel, out_dir, "h55_akash_open_market_book")
    summary = {
        "bid_resource_rows": int(len(bids)),
        "coverage_gate": gate,
        "claim_boundary": (
            "H55 reports only block-pinned, GPU-bearing open provider bids from the current "
            "Console live-GPU-provider coverage universe. Bids are not delivered capacity or "
            "fills; their native price fields are not USD or GPU-hour clearing prices; the "
            "coverage universe is not the whole Akash market; and it is not an LLM-routing "
            "allocation panel."
        ),
    }
    save_json(summary, out_dir, "h55_summary")
    return summary
