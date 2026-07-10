"""H57 — direction-specific V3 virtual-liquidity impact traversal.

This is a state-derived AMM calculation, not an execution, fill, or market-wide
depth panel. It traverses only source-ledger-verified H56 initialized-tick
snapshots and independently compares its post-swap sqrt price with same-block
QuoterV2 simulations when those are available.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from pathlib import Path

import pandas as pd

from ..capture_markets import uniswap_pool_specs
from . import data
from .common import DEFAULT_OUT, save, save_json
from .h56_uniswap_tick_book import complete_snapshot_manifests, snapshot_key

Q96 = Decimal(2**96)
FEE_DENOMINATOR = Decimal(1_000_000)
IMPACT_TARGET_BPS = (100, 500)
VALIDATION_TOLERANCE_BPS = Decimal("0.01")
DEPTH_COLUMNS = [
    "run_ts",
    "dt",
    "pool_id",
    "pool_map_id",
    "block_number",
    "impact_target_bps",
    "metric",
    "value",
    "state_status",
    "n_initialized_ticks",
]
VALIDATION_COLUMNS = [
    "run_ts",
    "dt",
    "pool_id",
    "block_number",
    "input_amount_usdc",
    "estimated_sqrt_price_x96_after",
    "quoted_sqrt_price_x96_after",
    "absolute_sqrt_price_error_bps",
]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _load(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def _sqrt_at_tick(tick: int) -> Decimal:
    """Return sqrt(1.0001**tick) with enough precision for raw-token traversal."""
    with localcontext() as context:
        context.prec = 90
        return (Decimal(10001) / Decimal(10000)) ** (Decimal(tick) / Decimal(2))


def _snapshot_records(group: pd.DataFrame) -> list[dict] | None:
    """Validate one homogeneous H56 pool snapshot before any traversal."""
    required = {
        "tick",
        "tick_spacing",
        "current_tick",
        "sqrt_price_x96",
        "active_liquidity_raw",
        "liquidity_net_raw",
    }
    if not required.issubset(group.columns):
        return None
    records = []
    for row in group.itertuples(index=False):
        try:
            records.append(
                {
                    "tick": int(row.tick),
                    "tick_spacing": int(row.tick_spacing),
                    "current_tick": int(row.current_tick),
                    "sqrt_price_x96": int(row.sqrt_price_x96),
                    "active_liquidity_raw": int(row.active_liquidity_raw),
                    "liquidity_net_raw": int(row.liquidity_net_raw),
                }
            )
        except (AttributeError, TypeError, ValueError):
            return None
    if not records or records[0]["sqrt_price_x96"] <= 0 or records[0]["active_liquidity_raw"] <= 0:
        return None
    state = {
        key: records[0][key]
        for key in ("tick_spacing", "current_tick", "sqrt_price_x96", "active_liquidity_raw")
    }
    if any(any(record[key] != value for key, value in state.items()) for record in records):
        return None
    if len({record["tick"] for record in records}) != len(records):
        return None
    if any(record["tick"] % state["tick_spacing"] for record in records):
        return None
    return sorted(records, key=lambda record: record["tick"], reverse=True)


def post_sqrt_after_usdc_input(
    records: list[dict], fee: int, gross_input_raw: int | Decimal
) -> Decimal | None:
    """Traverse zero-for-one V3 state for a gross USDC input, excluding EVM rounding.

    The direction is explicit: registered pools have USDC as token0 and WETH
    as token1, so USDC input moves sqrt price down. The fee is applied to input
    before each virtual-liquidity step; because it is constant for a pool, the
    continuous calculation uses one aggregate net input. The result is a
    deterministic state calculation that must still be checked against Quoter.
    """
    if not records or not 0 <= fee < int(FEE_DENOMINATOR):
        return None
    try:
        gross = Decimal(gross_input_raw)
    except (TypeError, ValueError):
        return None
    if gross < 0:
        return None
    with localcontext() as context:
        context.prec = 90
        ordered = sorted(records, key=lambda record: record["tick"], reverse=True)
        sqrt_price = Decimal(ordered[0]["sqrt_price_x96"]) / Q96
        liquidity = Decimal(ordered[0]["active_liquidity_raw"])
        remaining = gross * (FEE_DENOMINATOR - Decimal(fee)) / FEE_DENOMINATOR
        if remaining == 0:
            return sqrt_price * Q96
        current_tick = ordered[0]["current_tick"]
        for record in (record for record in ordered if record["tick"] < current_tick):
            boundary = _sqrt_at_tick(record["tick"])
            if boundary >= sqrt_price:
                return None
            input_to_boundary = liquidity * (sqrt_price - boundary) / (sqrt_price * boundary)
            if remaining <= input_to_boundary:
                return liquidity * sqrt_price / (liquidity + remaining * sqrt_price) * Q96
            remaining -= input_to_boundary
            sqrt_price = boundary
            # Crossing a tick from higher to lower price subtracts liquidityNet.
            liquidity -= Decimal(record["liquidity_net_raw"])
            if liquidity <= 0:
                return None
    return None


def gross_usdc_for_post_spot_impact(
    records: list[dict], fee: int, impact_bps: int
) -> Decimal | None:
    """Compute gross USDC needed for a declared post-swap spot-price increase."""
    if not records or impact_bps <= 0 or not 0 <= fee < int(FEE_DENOMINATOR):
        return None
    with localcontext() as context:
        context.prec = 90
        ordered = sorted(records, key=lambda record: record["tick"], reverse=True)
        sqrt_price = Decimal(ordered[0]["sqrt_price_x96"]) / Q96
        target = sqrt_price / (Decimal(1) + Decimal(impact_bps) / Decimal(10_000)).sqrt()
        liquidity = Decimal(ordered[0]["active_liquidity_raw"])
        total_net = Decimal(0)
        current_tick = ordered[0]["current_tick"]
        for record in (record for record in ordered if record["tick"] < current_tick):
            boundary = _sqrt_at_tick(record["tick"])
            if boundary >= sqrt_price:
                return None
            if target >= boundary:
                total_net += liquidity * (sqrt_price - target) / (sqrt_price * target)
                return total_net * FEE_DENOMINATOR / (FEE_DENOMINATOR - Decimal(fee))
            total_net += liquidity * (sqrt_price - boundary) / (sqrt_price * boundary)
            sqrt_price = boundary
            liquidity -= Decimal(record["liquidity_net_raw"])
            if liquidity <= 0:
                return None
    return None


def verified_tick_rows(ticks: pd.DataFrame, manifests: dict[tuple[str, str], int]) -> pd.DataFrame:
    """Keep a snapshot only when the curated tick count matches its source manifest."""
    required = {"run_ts", "dt", "pool_id", "block_number", "tick"}
    if ticks.empty or not required.issubset(ticks.columns) or not manifests:
        return pd.DataFrame()
    frame = ticks.copy()
    frame["_snapshot_key"] = [
        snapshot_key(run_ts, dt) for run_ts, dt in zip(frame["run_ts"], frame["dt"], strict=True)
    ]
    frame = frame.loc[frame["_snapshot_key"].isin(manifests)].copy()
    counts = frame.groupby("_snapshot_key").size().to_dict()
    valid = {key for key, count in counts.items() if manifests.get(key) == int(count)}
    return frame.loc[frame["_snapshot_key"].isin(valid)].copy()


def virtual_depth_panel(ticks: pd.DataFrame, manifests: dict[tuple[str, str], int]) -> pd.DataFrame:
    """Return USDC-to-WETH post-spot-impact capacities for verified H56 snapshots."""
    frame = verified_tick_rows(ticks, manifests)
    if frame.empty:
        return _empty(DEPTH_COLUMNS)
    specs = uniswap_pool_specs()
    rows = []
    keys = ["run_ts", "dt", "pool_id", "pool_map_id", "block_number"]
    for key, group in frame.groupby(keys, dropna=False):
        run_ts, dt, pool_id, pool_map_id, block_number = key
        spec = specs.get(str(pool_id).lower())
        records = _snapshot_records(group)
        if (
            spec is None
            or records is None
            or spec["token0_symbol"] != "USDC"
            or spec["token1_symbol"] != "WETH"
        ):
            continue
        for target_bps in IMPACT_TARGET_BPS:
            gross_raw = gross_usdc_for_post_spot_impact(records, int(spec["fee"]), target_bps)
            if gross_raw is None:
                continue
            gross_usdc = gross_raw / Decimal(10 ** int(spec["token0_decimals"]))
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "pool_id": pool_id,
                    "pool_map_id": pool_map_id,
                    "block_number": int(block_number),
                    "impact_target_bps": target_bps,
                    "metric": "virtual_liquidity_post_spot_impact_capacity_usdc",
                    "value": float(gross_usdc),
                    "state_status": "model_implied_pending_quoter_validation",
                    "n_initialized_ticks": int(len(records)),
                }
            )
    return pd.DataFrame(rows, columns=DEPTH_COLUMNS) if rows else _empty(DEPTH_COLUMNS)


def quoter_validation_panel(
    ticks: pd.DataFrame, quotes: pd.DataFrame, manifests: dict[tuple[str, str], int]
) -> pd.DataFrame:
    """Compare the state traversal with same-block QuoterV2 post-sqrt prices."""
    frame = verified_tick_rows(ticks, manifests)
    if frame.empty or quotes.empty:
        return _empty(VALIDATION_COLUMNS)
    required = {
        "run_ts",
        "dt",
        "pool_id",
        "block_number",
        "input_amount_raw",
        "sqrt_price_x96_after",
    }
    if not required.issubset(quotes.columns):
        return _empty(VALIDATION_COLUMNS)
    specs = uniswap_pool_specs()
    quote_frame = quotes.copy()
    quote_frame = quote_frame.loc[
        quote_frame.get("quote_side", pd.Series("", index=quote_frame.index)).eq(
            "usdc_to_weth_exact_input_simulation"
        )
    ].copy()
    quote_frame["_snapshot_key"] = [
        snapshot_key(run_ts, dt)
        for run_ts, dt in zip(quote_frame["run_ts"], quote_frame["dt"], strict=True)
    ]
    rows = []
    for key, group in frame.groupby(["run_ts", "dt", "pool_id", "block_number"], dropna=False):
        run_ts, dt, pool_id, block_number = key
        spec = specs.get(str(pool_id).lower())
        records = _snapshot_records(group)
        if spec is None or records is None:
            continue
        target_key = snapshot_key(run_ts, dt)
        candidates = quote_frame.loc[
            quote_frame["_snapshot_key"].map(
                lambda value, target_key=target_key: value == target_key
            )
            & quote_frame["pool_id"].astype(str).str.lower().eq(str(pool_id).lower())
            & pd.to_numeric(quote_frame["block_number"], errors="coerce").eq(block_number)
        ]
        for quote in candidates.itertuples(index=False):
            try:
                gross_raw = int(quote.input_amount_raw)
                quoted = Decimal(int(quote.sqrt_price_x96_after))
            except (AttributeError, TypeError, ValueError):
                continue
            estimated = post_sqrt_after_usdc_input(records, int(spec["fee"]), gross_raw)
            if estimated is None or quoted <= 0:
                continue
            error_bps = abs(estimated / quoted - Decimal(1)) * Decimal(10_000)
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "pool_id": pool_id,
                    "block_number": int(block_number),
                    "input_amount_usdc": gross_raw / 10 ** int(spec["token0_decimals"]),
                    "estimated_sqrt_price_x96_after": str(estimated),
                    "quoted_sqrt_price_x96_after": str(quoted),
                    "absolute_sqrt_price_error_bps": float(error_bps),
                }
            )
    return pd.DataFrame(rows, columns=VALIDATION_COLUMNS) if rows else _empty(VALIDATION_COLUMNS)


def validation_gate(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {"status": "not_validated", "matched_same_block_quotes": 0}
    errors = pd.to_numeric(panel["absolute_sqrt_price_error_bps"], errors="coerce").dropna()
    valid = len(errors) > 0 and Decimal(str(errors.max())) <= VALIDATION_TOLERANCE_BPS
    return {
        "status": "same_block_quoter_consistent" if valid else "validation_failed",
        "matched_same_block_quotes": int(len(errors)),
        "maximum_absolute_sqrt_price_error_bps": float(errors.max()) if len(errors) else None,
        "validation_tolerance_bps": float(VALIDATION_TOLERANCE_BPS),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ticks = _load("uniswap_tick_book")
    quotes = _load("market_quotes")
    manifests = complete_snapshot_manifests(_load("source_runs"))
    depth = virtual_depth_panel(ticks, manifests)
    validation = quoter_validation_panel(ticks, quotes, manifests)
    gate = validation_gate(validation)
    save(depth, out_dir, "h57_uniswap_virtual_depth")
    save(validation, out_dir, "h57_uniswap_quoter_validation")
    summary = {
        "verified_snapshot_runs": len(manifests),
        "virtual_depth_rows": int(len(depth)),
        "quoter_validation": gate,
        "claim_boundary": (
            "H57 is a direction-specific, fee-aware continuous traversal of complete H56 "
            "virtual-liquidity state for USDC-to-WETH. It is neither a realized trade nor a "
            "firm fill, and it excludes EVM step rounding, gas, transaction ordering, other "
            "pools, routes, market-wide liquidity, and routed inference flow. Same-block QuoterV2 "
            "agreement validates the state formula only, not execution or welfare."
        ),
    }
    save_json(summary, out_dir, "h57_summary")
    return summary
