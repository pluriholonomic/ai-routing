"""H45 — router-agnostic shadow-routing policy and resilience screen.

This module joins two kinds of disclosed inputs into one reproducible surface:

* OpenRouter and Hugging Face public quote/performance policies; and
* redacted policy snapshots imported by an owner of Cloudflare AI Gateway,
  Portkey, or LiteLLM.

It never issues an inference request and it does not treat a public policy
calculation or an imported configuration as a realized provider selection.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..shadow_routing import allocate, flip_conditions, stress_states, summarize_states
from . import data
from .common import DEFAULT_OUT, save, save_json

CANDIDATE_COLUMNS = [
    "router",
    "policy_type",
    "model_id",
    "scenario",
    "provider_name",
    "expected_quote_usd",
    "throughput_tps",
    "uptime_last_5m",
    "provider_order",
    "provider_weight",
    "source_run_ts",
    "config_id",
]
STATE_COLUMNS = CANDIDATE_COLUMNS + [
    "simulated_route_share",
    "provider_rank",
    "health_state",
    "excluded_providers",
]
FLIP_COLUMNS = [
    "router",
    "policy_type",
    "model_id",
    "scenario",
    "provider_name",
    "current_quote_usd",
    "best_quote_usd",
    "required_quote_cut_pct_to_tie_best",
    "is_current_lowest_quote",
]
SUMMARY_COLUMNS = [
    "router",
    "policy_type",
    "model_id",
    "scenario",
    "base_winner",
    "base_winner_share",
    "base_entropy",
    "n_health_states",
    "base_winner_state_robustness",
    "n_distinct_state_winners",
]


def _empty_candidates() -> pd.DataFrame:
    return pd.DataFrame(columns=CANDIDATE_COLUMNS)


def _latest_rows(table: str, columns: str) -> pd.DataFrame:
    """Read one latest full table snapshot, returning no rows when absent."""
    try:
        glob = data.table_glob(table)
        return data.q(
            f"""
            with latest as (select max(run_ts) as run_ts from read_parquet('{glob}'))
            select {columns}
            from read_parquet('{glob}') as source, latest
            where source.run_ts = latest.run_ts
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def _latest_configured_rows() -> pd.DataFrame:
    """Read each configured router's latest imported policy, not one global run."""
    try:
        glob = data.table_glob("router_policy_snapshots")
        return data.q(
            f"""
            with latest as (
              select router, max(run_ts) as run_ts
              from read_parquet('{glob}')
              group by router
            )
            select source.run_ts, source.router, source.config_id, source.model_id,
                   source.policy_type, source.provider_name, source.provider_order,
                   source.provider_weight
            from read_parquet('{glob}') as source
            join latest on source.router = latest.router and source.run_ts = latest.run_ts
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def openrouter_candidates(rows: pd.DataFrame) -> pd.DataFrame:
    """Translate the existing OpenRouter public route simulation to H45 input."""
    if rows.empty:
        return _empty_candidates()
    result = pd.DataFrame(
        {
            "router": "openrouter",
            "policy_type": "inverse_square_price",
            "model_id": rows["model_id"],
            "scenario": rows["scenario"],
            "provider_name": rows["provider_name"],
            "expected_quote_usd": rows["expected_quote_usd"],
            "throughput_tps": rows.get("throughput_last_30m"),
            "uptime_last_5m": rows.get("uptime_last_5m"),
            "provider_order": None,
            "provider_weight": None,
            "source_run_ts": rows["run_ts"],
            "config_id": None,
        }
    )
    return result.loc[:, CANDIDATE_COLUMNS]


def huggingface_candidates(rows: pd.DataFrame) -> pd.DataFrame:
    """Translate public HF cheapest and reported-fastest policy surfaces."""
    if rows.empty:
        return _empty_candidates()
    policy_types = {
        "hf_cheapest_public_quote": "lowest_cost",
        "hf_fastest_reported_throughput": "highest_throughput",
    }
    selected = rows[rows["policy"].isin(policy_types)].copy()
    if selected.empty:
        return _empty_candidates()
    selected["policy_type"] = selected["policy"].map(policy_types)
    result = pd.DataFrame(
        {
            "router": "huggingface_inference_providers",
            "policy_type": selected["policy_type"],
            "model_id": selected["model_id"],
            "scenario": selected["scenario"],
            "provider_name": selected["provider_name"],
            "expected_quote_usd": selected["expected_quote_usd"],
            "throughput_tps": selected["throughput_tps"],
            "uptime_last_5m": None,
            "provider_order": None,
            "provider_weight": None,
            "source_run_ts": selected["run_ts"],
            "config_id": None,
        }
    )
    return result.loc[:, CANDIDATE_COLUMNS]


def configured_router_candidates(rows: pd.DataFrame) -> pd.DataFrame:
    """Translate an owned redacted policy snapshot to the common input shape."""
    if rows.empty:
        return _empty_candidates()
    result = pd.DataFrame(
        {
            "router": rows["router"],
            "policy_type": rows["policy_type"],
            "model_id": rows["model_id"],
            "scenario": "configured",
            "provider_name": rows["provider_name"],
            "expected_quote_usd": None,
            "throughput_tps": None,
            "uptime_last_5m": None,
            "provider_order": rows["provider_order"],
            "provider_weight": rows["provider_weight"],
            "source_run_ts": rows["run_ts"],
            "config_id": rows["config_id"],
        }
    )
    return result.loc[:, CANDIDATE_COLUMNS]


def load_candidates() -> pd.DataFrame:
    openrouter = _latest_rows(
        "routing_simulation",
        "run_ts, model_id, scenario, provider_name, expected_quote_usd, "
        "uptime_last_5m, throughput_last_30m",
    )
    huggingface = _latest_rows(
        "hf_router_policy_simulation",
        "run_ts, policy, model_id, scenario, provider_name, expected_quote_usd, throughput_tps",
    )
    configured = _latest_configured_rows()
    frames = [
        openrouter_candidates(openrouter),
        huggingface_candidates(huggingface),
        configured_router_candidates(configured),
    ]
    nonempty = [frame for frame in frames if not frame.empty]
    if not nonempty:
        return _empty_candidates()
    return pd.concat(nonempty, ignore_index=True).drop_duplicates().reset_index(drop=True)


def simulated_base_routes(candidates: pd.DataFrame) -> pd.DataFrame:
    """Return the base policy allocation before availability stress is applied."""
    if candidates.empty:
        return candidates.assign(simulated_route_share=pd.Series(dtype="float64"))
    frames = []
    group_columns = ["router", "policy_type", "model_id", "scenario"]
    for _, group in candidates.groupby(group_columns, dropna=False, sort=False):
        frames.append(allocate(group, str(group.iloc[0]["policy_type"])))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _source_counts(candidates: pd.DataFrame) -> dict[str, int]:
    if candidates.empty:
        return {}
    return {
        str(router): int(count)
        for router, count in candidates.groupby("router", dropna=False).size().items()
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    candidates = load_candidates()
    base = simulated_base_routes(candidates)
    states = stress_states(candidates)
    flips = flip_conditions(candidates)
    summary = summarize_states(states)
    states = states.reindex(columns=STATE_COLUMNS)
    flips = flips.reindex(columns=FLIP_COLUMNS)
    summary = summary.reindex(columns=SUMMARY_COLUMNS)
    save(candidates, out_dir, "h45_shadow_candidates")
    save(base, out_dir, "h45_shadow_base_routes")
    save(states, out_dir, "h45_shadow_route_states")
    save(flips, out_dir, "h45_shadow_flip_conditions")
    save(summary, out_dir, "h45_shadow_summary")
    result = {
        "router_candidate_rows": _source_counts(candidates),
        "base_route_rows": int(len(base)),
        "stress_route_rows": int(len(states)),
        "price_flip_rows": int(len(flips)),
        "policy_groups": int(len(summary)),
        "claim_boundary": (
            "OpenRouter and Hugging Face rows replay public quote/performance policies; "
            "Cloudflare, Portkey, and LiteLLM rows replay only a current owner-imported, "
            "redacted configuration. None establishes realized provider fills, private health, "
            "or market-wide routed share. Realized outcomes require router_route_attempts."
        ),
    }
    save_json(result, out_dir, "h45_shadow_execution_summary")
    return result
