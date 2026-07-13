"""H76 — retained Akash bid-set to accepted-lease selection comparator."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

SOURCE_TABLE = "akash_market_choice_bids"
EVENT_TABLE = "akash_market_bid_events"
MIN_ORDERS = 1000
MIN_DAYS = 30
PANEL_COLUMNS = [
    "order_id",
    "choice_set_id",
    "run_ts",
    "dt",
    "snapshot_height",
    "snapshot_time",
    "retained_bids",
    "retained_providers",
    "native_price_denom",
    "selected_provider",
    "selected_native_price",
    "lowest_native_price",
    "selected_price_rank",
    "selected_is_lowest_price",
    "selected_price_premium_to_lowest",
    "retained_price_dispersion",
    "choice_set_pagination_complete",
    "post_selection_query",
]


def load_choice_bids() -> pd.DataFrame:
    try:
        glob = data.table_glob(SOURCE_TABLE)
        return data.q(f"select * from read_parquet('{glob}', union_by_name=true)").df()
    except Exception:
        return pd.DataFrame()


def load_bid_events() -> pd.DataFrame:
    try:
        glob = data.table_glob(EVENT_TABLE)
        return data.q(f"select * from read_parquet('{glob}', union_by_name=true)").df()
    except Exception:
        return pd.DataFrame()


def retained_choice_panel(rows: pd.DataFrame) -> pd.DataFrame:
    required = {
        "order_id",
        "choice_set_id",
        "run_ts",
        "dt",
        "snapshot_height",
        "snapshot_time",
        "bid_id",
        "provider",
        "resource_index",
        "native_price_amount",
        "native_price_denom",
        "selected_contract",
        "choice_set_pagination_complete",
        "post_selection_query",
    }
    if rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame(columns=PANEL_COLUMNS)
    frame = rows.copy()
    frame["captured_at"] = pd.to_datetime(frame["run_ts"], utc=True, errors="coerce")
    frame["native_price_amount"] = pd.to_numeric(
        frame["native_price_amount"], errors="coerce"
    )
    frame = frame.dropna(
        subset=[
            "order_id",
            "choice_set_id",
            "captured_at",
            "bid_id",
            "provider",
            "native_price_amount",
            "native_price_denom",
        ]
    )
    frame = frame.loc[
        frame["native_price_amount"].ge(0)
        & frame["choice_set_pagination_complete"].astype(bool)
        & frame["post_selection_query"].astype(bool)
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)

    # A bid can contain multiple resources with the same contract price. Keep
    # one contract row so resource multiplicity cannot inflate choice-set size.
    frame = frame.sort_values("resource_index").drop_duplicates(
        ["choice_set_id", "bid_id"], keep="first"
    )
    output = []
    for choice_set_id, group in frame.groupby("choice_set_id", sort=True):
        selected = group.loc[group["selected_contract"].astype(bool)]
        denoms = group["native_price_denom"].dropna().unique()
        if len(selected) != 1 or len(denoms) != 1:
            continue
        selected_row = selected.iloc[0]
        prices = group["native_price_amount"].sort_values(kind="stable")
        lowest = float(prices.iloc[0])
        selected_price = float(selected_row["native_price_amount"])
        rank = int((prices < selected_price).sum() + 1)
        output.append(
            {
                "order_id": group["order_id"].iloc[0],
                "choice_set_id": choice_set_id,
                "run_ts": group["run_ts"].iloc[0],
                "dt": group["dt"].iloc[0],
                "snapshot_height": group["snapshot_height"].iloc[0],
                "snapshot_time": group["snapshot_time"].iloc[0],
                "retained_bids": int(group["bid_id"].nunique()),
                "retained_providers": int(group["provider"].nunique()),
                "native_price_denom": denoms[0],
                "selected_provider": selected_row["provider"],
                "selected_native_price": selected_price,
                "lowest_native_price": lowest,
                "selected_price_rank": rank,
                "selected_is_lowest_price": rank == 1,
                "selected_price_premium_to_lowest": (
                    selected_price / lowest - 1 if lowest > 0 else None
                ),
                "retained_price_dispersion": (
                    float(prices.max() / prices.min() - 1) if prices.min() > 0 else None
                ),
                "choice_set_pagination_complete": True,
                "post_selection_query": True,
            }
        )
    panel = pd.DataFrame(output, columns=PANEL_COLUMNS)
    if panel.empty:
        return panel
    # Repeated hourly runs can see the same lease. Use the earliest retained
    # complete set because it is closest to the public selection event.
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    return (
        panel.sort_values("captured_at")
        .drop_duplicates("order_id", keep="first")
        .drop(columns="captured_at")
        .reset_index(drop=True)
    )


def event_choice_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Build pre-selection price choice sets from a complete indexed event window."""
    required = {
        "order_id",
        "choice_set_id",
        "run_ts",
        "dt",
        "bid_id",
        "provider",
        "native_price_amount",
        "native_price_denom",
        "selected_contract",
        "event_window_end_height_inclusive",
        "event_window_complete",
    }
    if rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame(columns=PANEL_COLUMNS)
    frame = rows.copy()
    frame = frame.loc[frame["event_window_complete"].astype(bool)].copy()
    frame["native_price_amount"] = pd.to_numeric(
        frame["native_price_amount"], errors="coerce"
    )
    frame["captured_at"] = pd.to_datetime(frame["run_ts"], utc=True, errors="coerce")
    frame = frame.dropna(
        subset=[
            "order_id",
            "choice_set_id",
            "captured_at",
            "bid_id",
            "provider",
            "native_price_amount",
            "native_price_denom",
        ]
    )
    frame = frame.loc[frame["native_price_amount"].ge(0)].drop_duplicates(
        ["choice_set_id", "bid_id"], keep="last"
    )
    output = []
    for choice_set_id, group in frame.groupby("choice_set_id", sort=True):
        selected = group.loc[group["selected_contract"].astype(bool)]
        denoms = group["native_price_denom"].dropna().unique()
        if len(selected) != 1 or len(denoms) != 1:
            continue
        selected_row = selected.iloc[0]
        prices = group["native_price_amount"].sort_values(kind="stable")
        lowest = float(prices.iloc[0])
        selected_price = float(selected_row["native_price_amount"])
        rank = int((prices < selected_price).sum() + 1)
        output.append(
            {
                "order_id": group["order_id"].iloc[0],
                "choice_set_id": choice_set_id,
                "run_ts": group["run_ts"].iloc[0],
                "dt": group["dt"].iloc[0],
                "snapshot_height": group["event_window_end_height_inclusive"].iloc[0],
                "snapshot_time": None,
                "retained_bids": int(group["bid_id"].nunique()),
                "retained_providers": int(group["provider"].nunique()),
                "native_price_denom": denoms[0],
                "selected_provider": selected_row["provider"],
                "selected_native_price": selected_price,
                "lowest_native_price": lowest,
                "selected_price_rank": rank,
                "selected_is_lowest_price": rank == 1,
                "selected_price_premium_to_lowest": (
                    selected_price / lowest - 1 if lowest > 0 else None
                ),
                "retained_price_dispersion": (
                    float(prices.max() / prices.min() - 1) if prices.min() > 0 else None
                ),
                "choice_set_pagination_complete": True,
                "post_selection_query": False,
            }
        )
    panel = pd.DataFrame(output, columns=PANEL_COLUMNS)
    if panel.empty:
        return panel
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    return (
        panel.sort_values("captured_at")
        .drop_duplicates("order_id", keep="first")
        .drop(columns="captured_at")
        .reset_index(drop=True)
    )


def coverage_gate(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "status": "not_identified",
            "retained_choice_sets": 0,
            "source_days": 0,
            "minimum_orders": MIN_ORDERS,
            "minimum_days": MIN_DAYS,
        }
    eligible = panel.loc[panel["retained_providers"].ge(2)]
    source_days = pd.to_datetime(eligible["dt"], utc=True, errors="coerce").dt.date.nunique()
    reasons = []
    if len(eligible) < MIN_ORDERS:
        reasons.append(f"only {len(eligible)}/{MIN_ORDERS} retained multi-provider choice sets")
    if source_days < MIN_DAYS:
        reasons.append(f"only {source_days}/{MIN_DAYS} source days")
    return {
        "status": "retained_selection_panel_ready" if not reasons else "power_gated",
        "retained_choice_sets": int(len(panel)),
        "retained_multi_provider_choice_sets": int(len(eligible)),
        "source_days": int(source_days),
        "minimum_orders": MIN_ORDERS,
        "minimum_days": MIN_DAYS,
        "gate_reasons": reasons,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    bids = load_choice_bids()
    events = load_bid_events()
    event_panel = event_choice_panel(events)
    retained_panel = retained_choice_panel(bids)
    panel = event_panel if not event_panel.empty else retained_panel
    eligible = panel.loc[panel["retained_providers"].ge(2)] if not panel.empty else panel
    result = {
        "captured_bid_rows": int(len(bids)),
        "captured_bid_event_rows": int(len(events)),
        "primary_choice_source": (
            "indexed_bid_create_events"
            if not event_panel.empty
            else "retained_post_selection_state"
        ),
        "coverage_gate": coverage_gate(panel),
        "selected_lowest_price_share": (
            float(eligible["selected_is_lowest_price"].mean()) if not eligible.empty else None
        ),
        "median_selected_price_premium_to_lowest": (
            float(eligible["selected_price_premium_to_lowest"].median())
            if not eligible.empty
            else None
        ),
        "claim_boundary": (
            "H76 prefers complete bounded public bid-create event windows linked to public "
            "lease IDs; it falls back to post-selection retained state only when no event "
            "choice set is available. It observes procurement prices and selected contracts, "
            "not workload delivery, LLM routing, cost, profit, or welfare."
        ),
    }
    save(panel, out_dir, "h76_akash_retained_lease_choice")
    save_json(result, out_dir, "h76_summary")
    return result
