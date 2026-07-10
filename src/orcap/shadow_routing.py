"""Router-agnostic shadow execution, stress states, and quote flip conditions."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pandas as pd

POLICY_TYPES = {
    "inverse_square_price",
    "lowest_cost",
    "highest_throughput",
    "ordered_failover",
    "weighted",
}
GROUP_COLUMNS = ["router", "policy_type", "model_id", "scenario"]


def _numeric(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce")


def _numeric_column(frame: pd.DataFrame, name: str, default: float = np.nan) -> pd.Series:
    if name not in frame:
        return pd.Series(default, index=frame.index, dtype="float64")
    return _numeric(frame[name])


def _entropy(shares: pd.Series) -> float:
    positive = shares[shares > 0]
    return float(-(positive * np.log(positive)).sum()) if len(positive) else np.nan


def allocate(candidates: pd.DataFrame, policy_type: str) -> pd.DataFrame:
    """Allocate a first-route shadow share under one disclosed policy.

    Ordered routes expose a deterministic first candidate and a fallback order.
    Weighted and inverse-square policies expose a stochastic first-route share.
    No function here claims an unobserved live-health decision was replayed.
    """
    if policy_type not in POLICY_TYPES:
        raise ValueError(f"unsupported shadow policy: {policy_type}")
    if candidates.empty:
        return candidates.assign(simulated_route_share=pd.Series(dtype="float64"))
    rows = candidates.copy()
    rows["expected_quote_usd"] = _numeric_column(rows, "expected_quote_usd")
    rows["throughput_tps"] = _numeric_column(rows, "throughput_tps")
    rows["provider_order"] = _numeric_column(rows, "provider_order").fillna(np.inf)
    rows["provider_weight"] = _numeric_column(rows, "provider_weight").fillna(0.0)

    if policy_type == "inverse_square_price":
        rows = rows[rows["expected_quote_usd"] > 0].copy()
        rows["_weight"] = rows["expected_quote_usd"] ** -2
    elif policy_type == "lowest_cost":
        rows = rows[rows["expected_quote_usd"] >= 0].copy()
        if rows.empty:
            return rows.assign(simulated_route_share=pd.Series(dtype="float64"))
        best = rows["expected_quote_usd"].min()
        rows["_weight"] = np.isclose(rows["expected_quote_usd"], best).astype(float)
    elif policy_type == "highest_throughput":
        rows = rows[rows["throughput_tps"] > 0].copy()
        if rows.empty:
            return rows.assign(simulated_route_share=pd.Series(dtype="float64"))
        best = rows["throughput_tps"].max()
        rows["_weight"] = np.isclose(rows["throughput_tps"], best).astype(float)
    elif policy_type == "ordered_failover":
        rows = rows.sort_values(["provider_order", "provider_name"])
        if rows.empty:
            return rows.assign(simulated_route_share=pd.Series(dtype="float64"))
        best = rows["provider_order"].min()
        rows["_weight"] = np.isclose(rows["provider_order"], best).astype(float)
    else:  # weighted
        rows = rows[rows["provider_weight"] > 0].copy()
        rows["_weight"] = rows["provider_weight"]

    total = rows["_weight"].sum()
    if not math.isfinite(float(total)) or total <= 0:
        return rows.assign(simulated_route_share=0.0, provider_rank=np.nan)
    rows["simulated_route_share"] = rows["_weight"] / total
    rows["provider_rank"] = rows["simulated_route_share"].rank(
        method="min", ascending=False
    ).astype(int)
    return rows.drop(columns="_weight")


def _state_specs(base: pd.DataFrame) -> Iterable[tuple[str, list[str]]]:
    providers = base.sort_values(["provider_rank", "provider_name"])["provider_name"].tolist()
    yield "base", []
    for provider in providers:
        yield f"provider_down:{provider}", [provider]
    if len(providers) >= 2:
        yield "top_two_down", providers[:2]
    uptime = _numeric_column(base, "uptime_last_5m")
    if uptime.notna().any():
        low_uptime = base.loc[uptime < 0.98, "provider_name"].tolist()
        if low_uptime:
            yield "public_low_uptime_down", low_uptime


def stress_states(candidates: pd.DataFrame) -> pd.DataFrame:
    """Enumerate provider-outage states for every router/model/scenario policy."""
    if candidates.empty:
        return pd.DataFrame()
    records = []
    for group, raw in candidates.groupby(GROUP_COLUMNS, dropna=False, sort=False):
        router, policy_type, model_id, scenario = group
        base = allocate(raw, policy_type)
        if base.empty:
            continue
        for state, excluded in _state_specs(base):
            simulated = allocate(base[~base["provider_name"].isin(excluded)], policy_type)
            if simulated.empty:
                continue
            simulated = simulated.copy()
            simulated["router"] = router
            simulated["policy_type"] = policy_type
            simulated["model_id"] = model_id
            simulated["scenario"] = scenario
            simulated["health_state"] = state
            simulated["excluded_providers"] = ",".join(sorted(excluded))
            records.append(simulated)
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


def flip_conditions(candidates: pd.DataFrame) -> pd.DataFrame:
    """Price reduction required for each provider to become the lowest quote."""
    if candidates.empty:
        return pd.DataFrame()
    rows = []
    for group, frame in candidates.groupby(GROUP_COLUMNS, dropna=False, sort=False):
        priced = frame.copy()
        priced["expected_quote_usd"] = _numeric(priced["expected_quote_usd"])
        priced = priced[priced["expected_quote_usd"] > 0]
        if priced.empty:
            continue
        best = float(priced["expected_quote_usd"].min())
        router, policy_type, model_id, scenario = group
        for candidate in priced.itertuples(index=False):
            cost = float(candidate.expected_quote_usd)
            rows.append(
                {
                    "router": router,
                    "policy_type": policy_type,
                    "model_id": model_id,
                    "scenario": scenario,
                    "provider_name": candidate.provider_name,
                    "current_quote_usd": cost,
                    "best_quote_usd": best,
                    "required_quote_cut_pct_to_tie_best": max(0.0, (1.0 - best / cost) * 100),
                    "is_current_lowest_quote": bool(math.isclose(cost, best)),
                }
            )
    return pd.DataFrame(rows)


def summarize_states(states: pd.DataFrame) -> pd.DataFrame:
    """Summarize winner robustness and entropy across health stress states."""
    if states.empty:
        return pd.DataFrame()
    rows = []
    group_cols = GROUP_COLUMNS
    for group, frame in states.groupby(group_cols, dropna=False, sort=False):
        base = frame[frame["health_state"] == "base"]
        if base.empty:
            continue
        base_winner = base.sort_values(["provider_rank", "provider_name"]).iloc[0]["provider_name"]
        base_share = float(
            base.loc[base["provider_name"] == base_winner, "simulated_route_share"].iloc[0]
        )
        winners = (
            frame.sort_values(["health_state", "provider_rank", "provider_name"])
            .groupby("health_state", as_index=False)
            .first()["provider_name"]
        )
        router, policy_type, model_id, scenario = group
        rows.append(
            {
                "router": router,
                "policy_type": policy_type,
                "model_id": model_id,
                "scenario": scenario,
                "base_winner": base_winner,
                "base_winner_share": base_share,
                "base_entropy": _entropy(base["simulated_route_share"]),
                "n_health_states": int(frame["health_state"].nunique()),
                "base_winner_state_robustness": float((winners == base_winner).mean()),
                "n_distinct_state_winners": int(winners.nunique()),
            }
        )
    return pd.DataFrame(rows)
