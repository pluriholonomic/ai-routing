"""H41 — auditable common-metric panel for DeFi and open-compute sources.

This is intentionally a coverage-and-estimand panel, not a forced common price
index. It reports only metrics that have the same economic interpretation
within a source family and labels the cross-market comparison provisional until
matched instrument/quality cohorts accumulate.
"""

import json
import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

COLUMNS = [
    "dt",
    "market",
    "source",
    "resource_kind",
    "quote_unit",
    "cohort",
    "metric",
    "value",
    "n_observations",
]
MARKETS = {
    "defillama": "defi_aggregate",
    "cow": "defi_rfq",
    "uniswap": "defi_amm",
    "geckoterminal": "defi_amm_indexed_control",
    "golem": "decentralized_compute",
    "akash": "decentralized_compute",
    "chutes": "decentralized_compute",
}


def _table(name: str, columns: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select {columns} from read_parquet('{data.table_glob(name)}', union_by_name = true)"
        ).df()
    except Exception as exc:
        log.info("H41 table %s unavailable: %s", name, exc)
        return pd.DataFrame()


def finalized_log_window_coverage(source_runs: pd.DataFrame, source: str) -> dict:
    """Measure whether repeated finalized-log query ranges leave block gaps.

    A valid individual Uniswap or CoW window does not create a time series if
    successive windows are disjoint. The coverage union is based on the
    collector's finality-buffered query bounds, not on event incidence: empty
    blocks are still observed blocks.
    """
    empty = {
        "source": source,
        "window_count": 0,
        "earliest_block": None,
        "latest_block": None,
        "covered_blocks": 0,
        "uncovered_blocks_between_windows": None,
        "contiguous_observed": None,
        "observation_dates": [],
        "observation_days": 0,
        "dynamic_panel_ready": False,
    }
    if source_runs.empty or "source" not in source_runs or "detail_json" not in source_runs:
        return empty
    windows: list[tuple[int, int]] = []
    observation_dates: set[str] = set()
    runs = source_runs[source_runs["source"].astype(str) == source]
    for row in runs.itertuples(index=False):
        try:
            detail = json.loads(row.detail_json)
            start, end = int(detail["from_block"]), int(detail["to_block"])
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        # Before this field was introduced, a row with query bounds could have
        # been a failed request. Do not backfill continuity from that ambiguous
        # history; a successful empty response is explicitly marked instead.
        if detail.get("log_query_succeeded") is True and start >= 0 and end >= start:
            windows.append((start, end))
            date = getattr(row, "dt", None)
            if date is not None:
                observation_dates.add(str(date))
    if not windows:
        return empty
    windows.sort()
    covered_blocks = 0
    gaps = 0
    current_start, current_end = windows[0]
    for start, end in windows[1:]:
        if start > current_end + 1:
            covered_blocks += current_end - current_start + 1
            gaps += start - current_end - 1
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    covered_blocks += current_end - current_start + 1
    contiguous_observed = gaps == 0 if len(windows) > 1 else None
    dates = sorted(observation_dates)
    return {
        "source": source,
        "window_count": len(windows),
        "earliest_block": windows[0][0],
        "latest_block": max(end for _, end in windows),
        "covered_blocks": covered_blocks,
        "uncovered_blocks_between_windows": gaps,
        "contiguous_observed": contiguous_observed,
        "observation_dates": dates,
        "observation_days": len(dates),
        "dynamic_panel_ready": bool(contiguous_observed and len(dates) >= 7),
    }


def metric_panel(
    participants: pd.DataFrame,
    executions: pd.DataFrame,
    quotes: pd.DataFrame,
    capacity: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []
    if not participants.empty:
        for (dt, source), group in participants.groupby(["dt", "source"]):
            rows.append(
                _row(dt, source, "participants", group["participant_id"].nunique(), len(group))
            )
            values = pd.to_numeric(group["value"], errors="coerce")
            if values.notna().any():
                rows.append(
                    _row(
                        dt,
                        source,
                        "median_reported_value",
                        values.median(),
                        int(values.notna().sum()),
                    )
                )
    if not executions.empty:
        executed = executions.copy()
        if {"source", "execution_id"}.issubset(executed.columns):
            sort_columns = [
                column for column in ("source", "execution_id", "run_ts") if column in executed
            ]
            executed = executed.sort_values(sort_columns).drop_duplicates(
                ["source", "execution_id"], keep="last"
            )
        for (dt, source), group in executed.groupby(["dt", "source"]):
            finalized = (
                group["finalized"].eq(True)
                if "finalized" in group
                else pd.Series(False, index=group.index)
            )
            rows.extend(
                [
                    _row(dt, source, "executions", len(group), len(group)),
                    _row(dt, source, "execution_success_rate", group["success"].mean(), len(group)),
                    _row(
                        dt,
                        source,
                        "finalized_executions",
                        int(finalized.sum()),
                        len(group),
                    ),
                ]
            )
            if {"price_usdc_per_weth", "price_unit", "side"}.issubset(group.columns):
                prices = pd.to_numeric(group["price_usdc_per_weth"], errors="coerce")
                comparable = group["price_unit"].eq("usdc_per_weth") & prices.notna()
                for side, price_group in group.loc[comparable].assign(
                    price_usdc_per_weth=prices.loc[comparable]
                ).groupby("side", dropna=False):
                    cohort = f"side:{side}" if pd.notna(side) else None
                    rows.append(
                        _row(
                            dt,
                            source,
                            "median_execution_price_usdc_per_weth",
                            price_group["price_usdc_per_weth"].median(),
                            len(price_group),
                            quote_unit="usdc_per_weth",
                            cohort=cohort,
                        )
                    )
    if not quotes.empty:
        quoted = quotes.copy()
        if "quote_unit" in quoted:
            quoted["quote_unit"] = quoted["quote_unit"].fillna("unspecified")
        else:
            quoted["quote_unit"] = "unspecified"
        quoted["price_usd"] = pd.to_numeric(quoted.get("price_usd"), errors="coerce")
        quoted["depth_usd"] = pd.to_numeric(quoted.get("depth_usd"), errors="coerce")
        quoted["price_usdc_per_weth"] = pd.to_numeric(
            (
                quoted["price_usdc_per_weth"]
                if "price_usdc_per_weth" in quoted
                else pd.Series(index=quoted.index, dtype="float64")
            ),
            errors="coerce",
        )
        buckets = pd.to_numeric(
            (
                quoted["input_bucket_usdc"]
                if "input_bucket_usdc" in quoted
                else pd.Series(index=quoted.index, dtype="float64")
            ),
            errors="coerce",
        )
        pools = (
            quoted["pool_id"]
            if "pool_id" in quoted
            else pd.Series(index=quoted.index, dtype="object")
        )
        quoted["cohort"] = [
            (
                f"pool:{pool};input_bucket_usdc:{bucket:g}"
                if pd.notna(pool) and pd.notna(bucket)
                else (f"input_bucket_usdc:{bucket:g}" if pd.notna(bucket) else None)
            )
            for pool, bucket in zip(pools, buckets, strict=True)
        ]
        if "impact_capacity_lower_bound_usdc" in quoted:
            impact_capacity = pd.to_numeric(
                quoted["impact_capacity_lower_bound_usdc"], errors="coerce"
            )
            impact_target = pd.to_numeric(quoted.get("impact_target_bps"), errors="coerce")
            impact_pool = quoted.get("pool_id", pd.Series(index=quoted.index, dtype="object"))
            impact = quoted.assign(
                impact_capacity_lower_bound_usdc=impact_capacity,
                impact_target_bps=impact_target,
                impact_pool=impact_pool,
            )
            impact = impact.dropna(subset=["impact_capacity_lower_bound_usdc", "impact_target_bps"])
            for (dt, source, pool, target_bps), group in impact.groupby(
                ["dt", "source", "impact_pool", "impact_target_bps"], dropna=False
            ):
                pool_label = "unknown" if pd.isna(pool) else str(pool)
                rows.append(
                    _row(
                        dt,
                        source,
                        "state_impact_capacity_lower_bound_usdc",
                        group["impact_capacity_lower_bound_usdc"].median(),
                        len(group),
                        quote_unit="usdc",
                        cohort=f"pool:{pool_label};impact_target_bps:{target_bps:g}",
                    )
                )
        for (dt, source, quote_unit, cohort), group in quoted.groupby(
            ["dt", "source", "quote_unit", "cohort"], dropna=False
        ):
            cohort = None if pd.isna(cohort) else cohort
            price_count = int(group["price_usd"].notna().sum())
            depth_count = int(group["depth_usd"].notna().sum())
            usdc_price_count = int(
                (group["price_usdc_per_weth"].notna() & (quote_unit == "usdc_per_weth")).sum()
            )
            rows.extend(
                [
                    _row(
                        dt,
                        source,
                        "quotes",
                        len(group),
                        len(group),
                        quote_unit=quote_unit,
                        cohort=cohort,
                    ),
                    _row(
                        dt,
                        source,
                        "median_quote_price_usd",
                        group["price_usd"].median() if price_count else None,
                        price_count,
                        quote_unit=quote_unit,
                        cohort=cohort,
                    ),
                    _row(
                        dt,
                        source,
                        "median_depth_usd",
                        group["depth_usd"].median() if depth_count else None,
                        depth_count,
                        quote_unit=quote_unit,
                        cohort=cohort,
                    ),
                ]
            )
            if usdc_price_count:
                rows.append(
                    _row(
                        dt,
                        source,
                        "median_quote_price_usdc_per_weth",
                        group["price_usdc_per_weth"].median(),
                        usdc_price_count,
                        quote_unit="usdc_per_weth",
                        cohort=cohort,
                    )
                )
    if not capacity.empty:
        cap = capacity.copy()
        if "resource_kind" in cap:
            cap["resource_kind"] = cap["resource_kind"].fillna("unclassified")
        else:
            cap["resource_kind"] = "unclassified"
        for column in ("total", "available", "used"):
            cap[column] = pd.to_numeric(cap.get(column), errors="coerce")
        for (dt, source, resource_kind), group in cap.groupby(["dt", "source", "resource_kind"]):
            reported = group.dropna(subset=["total"])
            total = reported["total"].sum(min_count=1)
            available = reported["available"].sum(min_count=1)
            used = reported["used"].sum(min_count=1)
            denom = total if pd.notna(total) else None
            rows.extend(
                [
                    _row(
                        dt,
                        source,
                        "capacity_participants",
                        reported["participant_id"].nunique(),
                        len(reported),
                        resource_kind,
                    ),
                    _row(dt, source, "reported_capacity", total, len(reported), resource_kind),
                    _row(
                        dt,
                        source,
                        "reported_available_capacity",
                        available,
                        len(reported),
                        resource_kind,
                    ),
                    _row(
                        dt,
                        source,
                        "reported_used_capacity",
                        used,
                        len(reported),
                        resource_kind,
                    ),
                    _row(
                        dt,
                        source,
                        "reported_utilization",
                        used / denom if denom and denom > 0 else None,
                        len(reported),
                        resource_kind,
                    ),
                    _row(
                        dt,
                        source,
                        "capacity_reporting_share",
                        len(reported) / len(group) if len(group) else None,
                        len(group),
                        resource_kind,
                    ),
                ]
            )
    return pd.DataFrame(rows, columns=COLUMNS)


def _row(
    dt: str,
    source: str,
    metric: str,
    value,
    n: int,
    resource_kind: str | None = None,
    quote_unit: str | None = None,
    cohort: str | None = None,
) -> dict:
    return {
        "dt": str(dt),
        "market": MARKETS.get(source, "unknown"),
        "source": source,
        "resource_kind": resource_kind,
        "quote_unit": quote_unit,
        "cohort": cohort,
        "metric": metric,
        "value": float(value) if pd.notna(value) else None,
        "n_observations": int(n),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    participants = _table("market_participants", "dt, source, participant_id, value")
    executions = _table("market_executions", "*")
    quotes = _table("market_quotes", "*")
    capacity = _table("market_capacity", "*")
    source_runs = _table("source_runs", "dt, source, status, detail_json")
    panel = metric_panel(participants, executions, quotes, capacity)
    log_coverage = {
        source: finalized_log_window_coverage(source_runs, source)
        for source in ("uniswap", "cow")
    }
    finalized_log_panel_ready = all(
        coverage["dynamic_panel_ready"] for coverage in log_coverage.values()
    )
    save(panel, out_dir, "h41_market_comparison")
    sources = sorted(panel["source"].unique()) if not panel.empty else []
    source_coverage = {
        source: {
            "metric_rows": int(len(group)),
            "days": int(group["dt"].nunique()),
            "first_day": str(group["dt"].min()),
            "last_day": str(group["dt"].max()),
        }
        for source, group in panel.groupby("source")
    }
    compute_capacity = panel[
        (panel["market"] == "decentralized_compute")
        & (panel["metric"] == "reported_capacity")
    ]
    has_compute_capacity = bool(compute_capacity["value"].notna().any())
    execution_sources = (
        executions["source"] if "source" in executions else pd.Series("", index=executions.index)
    )
    uniswap_executions = executions[execution_sources == "uniswap"]
    uniswap_finalized = (
        uniswap_executions["finalized"]
        if "finalized" in uniswap_executions
        else pd.Series(False, index=uniswap_executions.index)
    )
    finalized_uniswap = (
        uniswap_finalized.eq(True).any()
    )
    quote_sources = quotes["source"] if "source" in quotes else pd.Series("", index=quotes.index)
    uniswap_quotes = quotes[quote_sources == "uniswap"]
    uniswap_depth = (
        pd.to_numeric(uniswap_quotes["depth_usd"], errors="coerce")
        if "depth_usd" in uniswap_quotes
        else pd.Series(float("nan"), index=uniswap_quotes.index)
    )
    uniswap_depth_finalized = (
        uniswap_quotes["finalized"]
        if "finalized" in uniswap_quotes
        else pd.Series(False, index=uniswap_quotes.index)
    )
    finalized_uniswap_depth = (
        uniswap_depth.notna() & uniswap_depth_finalized.eq(True)
    ).any()
    uniswap_quote_side = (
        uniswap_quotes["quote_side"]
        if "quote_side" in uniswap_quotes
        else pd.Series("", index=uniswap_quotes.index)
    )
    finalized_uniswap_quote_curve = bool(
        (
            uniswap_depth_finalized.eq(True)
            & uniswap_quote_side.eq("usdc_to_weth_exact_input_simulation")
        ).any()
    )
    impact_capacity = (
        pd.to_numeric(uniswap_quotes["impact_capacity_lower_bound_usdc"], errors="coerce")
        if "impact_capacity_lower_bound_usdc" in uniswap_quotes
        else pd.Series(float("nan"), index=uniswap_quotes.index)
    )
    finalized_uniswap_impact_capacity = bool(
        (impact_capacity.notna() & uniswap_depth_finalized.eq(True)).any()
    )
    has_rfq_executions = bool((execution_sources == "cow").any())
    if not sources:
        comparison_status = "gated: no canonical market-source tables available"
    elif not has_compute_capacity:
        comparison_status = "gated: no non-null decentralized-compute capacity observation"
    elif not finalized_uniswap:
        comparison_status = (
            "gated: decentralized-compute supply-state observations are present, but no "
            "finalized Uniswap swap execution panel is available"
        )
    elif not finalized_uniswap_depth or not has_rfq_executions:
        uniswap_object = (
            "finalized fixed-notional quote curves"
            if finalized_uniswap_quote_curve
            else "finalized Uniswap swaps"
        )
        comparison_status = (
            f"gated: {uniswap_object} are observed, but finalized depth and/or market-wide "
            "RFQ execution panels are incomplete"
        )
    elif not finalized_log_panel_ready:
        comparison_status = (
            "gated: finalized market events are present, but the Uniswap and CoW panels do not "
            "yet have seven days of explicitly contiguous successful log windows"
        )
    else:
        comparison_status = (
            "provisional: source metrics observed; matched executable cohorts remain gated"
        )
    summary = {
        "sources_observed": sources,
        "markets_observed": sorted(panel["market"].unique()) if not panel.empty else [],
        "metrics_observed": sorted(panel["metric"].unique()) if not panel.empty else [],
        "source_coverage": source_coverage,
        "indexed_amm_controls": [source for source in sources if source == "geckoterminal"],
        "finalized_uniswap_swap_observed": bool(finalized_uniswap),
        "finalized_uniswap_depth_observed": bool(finalized_uniswap_depth),
        "finalized_uniswap_quote_curve_observed": finalized_uniswap_quote_curve,
        "finalized_uniswap_impact_capacity_observed": finalized_uniswap_impact_capacity,
        "cow_execution_observed": has_rfq_executions,
        "finalized_log_window_coverage": log_coverage,
        "finalized_log_panel_ready": finalized_log_panel_ready,
        "comparison_status": comparison_status,
        "required_next": [
            "at least seven days of contiguous finalized Uniswap and CoW log windows",
            "finalized Uniswap depth and swap events",
            "state-derived Uniswap impact-capacity lower bounds remain distinct from full depth",
            "market-wide CoW auction/settlement feed",
            "at least seven daily Akash GPU-capacity snapshots before dynamic estimates",
            (
                "repeated Chutes active-deployment configuration snapshots; they remain a supply "
                "proxy, not availability, utilization, or routing outcomes"
            ),
        ],
    }
    save_json(summary, out_dir, "h41_summary")
    return summary
