"""H52 — gross CoW execution basis versus parent-block Uniswap simulations.

The panel compares an exact USDC-to-WETH CoW settlement price with QuoterV2's
simulation of the *same* USDC input at the parent block of that settlement,
separately for each registered Uniswap pool. This is a reproducible pre-block
cross-venue price basis. CoW's finalized ``Trade.feeAmount`` is retained as a
separate sell-token fee adjustment; the AMM counterfactual remains at the
pre-fee stated CoW input. It is not an intra-block quote, same-all-in-notional
best-execution result, user-surplus measure, or adverse-selection estimate.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

MIN_FILLS = 500
MIN_DAYS = 7
MIN_POOLS = 2
COLUMNS = [
    "dt",
    "execution_id",
    "executed_at",
    "event_block_number",
    "state_block_number",
    "pool_id",
    "input_amount_usdc",
    "cow_gross_price_usdc_per_weth",
    "cow_reported_fee_usdc",
    "cow_reported_fee_bps",
    "cow_fee_adjusted_price_usdc_per_weth",
    "amm_parent_block_price_usdc_per_weth",
    "cow_over_amm_gross_basis_pct",
    "cow_fee_adjusted_over_amm_stated_input_basis_pct",
]


def _load(name: str, columns: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select {columns} from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception as exc:
        log.info("H52 %s unavailable: %s", name, exc)
        return pd.DataFrame()


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    executions = _load(
        "market_executions",
        "run_ts, dt, source, execution_id, executed_at, event_block_number, side, "
        "price_unit, price_usdc_per_weth, requested_size, fee_amount_raw",
    )
    quotes = _load("market_counterfactual_quotes", "*")
    return executions, quotes


def basis_panel(executions: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Join only identical CoW executions to parent-block exact-input AMM quotes."""
    if executions.empty or quotes.empty:
        return pd.DataFrame(columns=COLUMNS)
    required_execution = {
        "source",
        "execution_id",
        "side",
        "price_unit",
        "price_usdc_per_weth",
    }
    required_quote = {
        "reference_source",
        "reference_execution_id",
        "state_block_number",
        "pool_id",
        "input_amount",
        "price_usdc_per_weth",
        "quote_side",
        "quote_unit",
    }
    if not required_execution.issubset(executions) or not required_quote.issubset(quotes):
        return pd.DataFrame(columns=COLUMNS)
    fills = executions[
        (executions["source"] == "cow")
        & (executions["side"] == "usdc_to_weth")
        & (executions["price_unit"] == "usdc_per_weth")
    ].copy()
    fills["price_usdc_per_weth"] = pd.to_numeric(fills["price_usdc_per_weth"], errors="coerce")
    fills["requested_size"] = pd.to_numeric(fills.get("requested_size"), errors="coerce")
    fills["fee_amount_raw"] = pd.to_numeric(fills.get("fee_amount_raw"), errors="coerce")
    fills = fills.dropna(subset=["execution_id", "price_usdc_per_weth", "requested_size"])
    # GPv2Settlement's Trade event defines feeAmount in the sell-token's raw
    # units. The H52 cohort is USDC-to-WETH, so the registered 6-decimal USDC
    # conversion is exact at the instrument level. Missing fee data remains
    # missing; it must not be converted to zero.
    fills["cow_reported_fee_usdc"] = fills["fee_amount_raw"] / 1_000_000
    fills.loc[fills["cow_reported_fee_usdc"] < 0, "cow_reported_fee_usdc"] = pd.NA
    fills["cow_reported_fee_bps"] = (
        fills["cow_reported_fee_usdc"] / fills["requested_size"] * 10_000
    )
    fills["cow_fee_adjusted_price_usdc_per_weth"] = fills["price_usdc_per_weth"] * (
        1 + fills["cow_reported_fee_usdc"] / fills["requested_size"]
    )
    if "run_ts" in fills:
        fills = fills.sort_values("run_ts").drop_duplicates("execution_id", keep="last")
    counterfactuals = quotes[
        (quotes["reference_source"] == "cow")
        & (quotes.get("quote_side") == "usdc_to_weth_preblock_exact_input_counterfactual")
        & (quotes.get("quote_unit") == "usdc_per_weth")
    ].copy()
    counterfactuals["price_usdc_per_weth"] = pd.to_numeric(
        counterfactuals["price_usdc_per_weth"], errors="coerce"
    )
    counterfactuals["input_amount"] = pd.to_numeric(
        counterfactuals["input_amount"], errors="coerce"
    )
    counterfactuals = counterfactuals.dropna(
        subset=["reference_execution_id", "pool_id", "input_amount", "price_usdc_per_weth"]
    )
    if "run_ts" in counterfactuals:
        counterfactuals = counterfactuals.sort_values("run_ts")
    counterfactuals = counterfactuals.drop_duplicates(
        ["reference_execution_id", "pool_id"], keep="last"
    )
    merged = fills.merge(
        counterfactuals,
        left_on="execution_id",
        right_on="reference_execution_id",
        suffixes=("_cow", "_amm"),
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame(columns=COLUMNS)
    panel = pd.DataFrame(
        {
            "dt": merged["dt_cow" if "dt_cow" in merged else "dt"].astype(str),
            "execution_id": merged["execution_id"].astype(str),
            "executed_at": merged.get("executed_at"),
            "event_block_number": pd.to_numeric(merged.get("event_block_number"), errors="coerce"),
            "state_block_number": pd.to_numeric(merged["state_block_number"], errors="coerce"),
            "pool_id": merged["pool_id"].astype(str),
            "input_amount_usdc": merged["input_amount"],
            "cow_gross_price_usdc_per_weth": merged["price_usdc_per_weth_cow"],
            "cow_reported_fee_usdc": merged["cow_reported_fee_usdc"],
            "cow_reported_fee_bps": merged["cow_reported_fee_bps"],
            "cow_fee_adjusted_price_usdc_per_weth": merged["cow_fee_adjusted_price_usdc_per_weth"],
            "amm_parent_block_price_usdc_per_weth": merged["price_usdc_per_weth_amm"],
        }
    )
    panel["cow_over_amm_gross_basis_pct"] = (
        panel["cow_gross_price_usdc_per_weth"] / panel["amm_parent_block_price_usdc_per_weth"] - 1
    ) * 100
    panel["cow_fee_adjusted_over_amm_stated_input_basis_pct"] = (
        panel["cow_fee_adjusted_price_usdc_per_weth"]
        / panel["amm_parent_block_price_usdc_per_weth"]
        - 1
    ) * 100
    panel = panel.replace([float("inf"), float("-inf")], pd.NA).dropna(
        subset=["cow_over_amm_gross_basis_pct"]
    )
    return panel.loc[:, COLUMNS].sort_values(["dt", "execution_id", "pool_id"])


def summarize(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "evidence_status": "not_identified",
            "n_unique_cow_fills": 0,
            "n_fee_observed_fills": 0,
            "n_nonzero_reported_fee_fills": 0,
            "claim_boundary": _claim_boundary(),
        }
    fills = int(panel["execution_id"].nunique())
    days = int(panel["dt"].nunique())
    pools = int(panel["pool_id"].nunique())
    reasons = []
    if fills < MIN_FILLS:
        reasons.append(f"only {fills}/{MIN_FILLS} exact CoW fills")
    if days < MIN_DAYS:
        reasons.append(f"only {days}/{MIN_DAYS} days")
    if pools < MIN_POOLS:
        reasons.append(f"only {pools}/{MIN_POOLS} registered pools")
    by_pool = {
        str(pool): {
            "n_counterfactuals": int(len(group)),
            "median_cow_over_amm_gross_basis_pct": _median(group["cow_over_amm_gross_basis_pct"]),
            "median_cow_fee_adjusted_over_amm_stated_input_basis_pct": _median(
                group["cow_fee_adjusted_over_amm_stated_input_basis_pct"].dropna()
            ),
        }
        for pool, group in panel.groupby("pool_id")
    }
    fee_fills = panel.drop_duplicates("execution_id")
    fee_observed = fee_fills["cow_reported_fee_bps"].dropna()
    return {
        "evidence_status": "descriptive_cross_venue_basis" if not reasons else "power_gated",
        "n_unique_cow_fills": fills,
        "n_counterfactual_quotes": int(len(panel)),
        "n_days": days,
        "n_pools": pools,
        "median_cow_over_amm_gross_basis_pct": _median(panel["cow_over_amm_gross_basis_pct"]),
        "n_fee_observed_fills": int(len(fee_observed)),
        "n_nonzero_reported_fee_fills": int((fee_observed > 0).sum()),
        "median_cow_reported_fee_bps": _median(fee_observed),
        "median_cow_fee_adjusted_over_amm_stated_input_basis_pct": _median(
            panel["cow_fee_adjusted_over_amm_stated_input_basis_pct"].dropna()
        ),
        "by_pool": by_pool,
        "power_gate": {"min_fills": MIN_FILLS, "min_days": MIN_DAYS, "min_pools": MIN_POOLS},
        "gate_reasons": reasons,
        "claim_boundary": _claim_boundary(),
    }


def _median(values: pd.Series) -> float | None:
    value = values.median()
    return float(value) if pd.notna(value) else None


def _claim_boundary() -> str:
    return (
        "This is a parent-block, exact stated-sell-input cross-venue simulation for finalized "
        "USDC-to-WETH CoW fills. The CoW side includes the finalized Trade-event sell-token "
        "fee when available, but the AMM counterfactual remains at CoW's pre-fee stated input. "
        "It excludes batch gas, surplus, intra-block ordering, and post-parent-block price "
        "movement; it is not same-all-in-notional best execution, causal adverse selection, "
        "AMM depth, or a market-wide CoW execution estimate."
    )


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    executions, quotes = load_inputs()
    panel = basis_panel(executions, quotes)
    save(panel, out_dir, "h52_cow_amm_basis")
    result = summarize(panel)
    save_json(result, out_dir, "h52_summary")
    return result
