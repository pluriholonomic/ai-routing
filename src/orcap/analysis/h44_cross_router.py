"""H44 — public cross-router quote and policy-surface comparison.

H44 matches only explicitly versioned model aliases and public provider quotes.
It is designed to compare routing rules and quote/performance surfaces, not to
estimate either router's market-wide routed volume.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_MAP_PATH = REPO_ROOT / "config" / "router_model_map.toml"
PROVIDER_ALIASES = {
    "fireworks": "fireworks",
    "fireworksai": "fireworks",
    "together": "together",
    "togetherai": "together",
    "deepinfra": "deepinfra",
    "novita": "novita",
    "groq": "groq",
    "cerebras": "cerebras",
}


def model_map() -> tuple[str, dict[str, str]]:
    with MODEL_MAP_PATH.open("rb") as f:
        raw = tomllib.load(f)
    return str(raw["mapping_version"]), dict(raw["openrouter_to_huggingface"])


def canonical_provider(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    compact = re.sub(r"[^a-z0-9]+", "", str(value).lower())
    return PROVIDER_ALIASES.get(compact, compact or None)


def match_quotes(
    openrouter: pd.DataFrame, huggingface: pd.DataFrame, aliases: dict[str, str]
) -> pd.DataFrame:
    """Match quote pairs only after explicit model and provider canonicalization."""
    columns = [
        "openrouter_model_id",
        "huggingface_model_id",
        "provider_id",
        "openrouter_price_input_usd_per_mtok",
        "openrouter_price_output_usd_per_mtok",
        "huggingface_price_input_usd_per_mtok",
        "huggingface_price_output_usd_per_mtok",
        "input_basis_pct",
        "output_basis_pct",
    ]
    if openrouter.empty or huggingface.empty or not aliases:
        return pd.DataFrame(columns=columns)
    mapping = pd.DataFrame(
        [
            {"openrouter_model_id": left, "huggingface_model_id": right}
            for left, right in aliases.items()
        ]
    )
    left = openrouter.copy()
    left = left[(left["price_prompt"] > 0) & (left["price_completion"] > 0)].copy()
    left["provider_id"] = left["provider_name"].map(canonical_provider)
    left["openrouter_price_input_usd_per_mtok"] = left["price_prompt"] * 1_000_000
    left["openrouter_price_output_usd_per_mtok"] = left["price_completion"] * 1_000_000
    left = left.rename(columns={"model_id": "openrouter_model_id"}).merge(
        mapping, on="openrouter_model_id", how="inner"
    )
    # OpenRouter can expose several compatible variants for one provider.  The
    # public HF listing has one provider row, so use the cheapest output quote
    # deterministically rather than turning an SKU difference into duplicate
    # cross-router observations.
    left = left.sort_values(
        ["openrouter_model_id", "provider_id", "price_completion", "price_prompt"]
    ).drop_duplicates(["openrouter_model_id", "provider_id"], keep="first")
    right = huggingface.copy()
    right = right[
        (right["price_input_usd_per_mtok"] > 0)
        & (right["price_output_usd_per_mtok"] > 0)
    ].copy()
    right["provider_id"] = right["provider_name"].map(canonical_provider)
    right = right.rename(columns={"model_id": "huggingface_model_id"})
    merged = left.merge(
        right[
            [
                "huggingface_model_id",
                "provider_id",
                "price_input_usd_per_mtok",
                "price_output_usd_per_mtok",
            ]
        ],
        on=["huggingface_model_id", "provider_id"],
        how="inner",
    ).rename(
        columns={
            "price_input_usd_per_mtok": "huggingface_price_input_usd_per_mtok",
            "price_output_usd_per_mtok": "huggingface_price_output_usd_per_mtok",
        }
    )
    if merged.empty:
        return pd.DataFrame(columns=columns)
    merged["input_basis_pct"] = (
        merged["openrouter_price_input_usd_per_mtok"]
        / merged["huggingface_price_input_usd_per_mtok"]
        - 1.0
    ) * 100
    merged["output_basis_pct"] = (
        merged["openrouter_price_output_usd_per_mtok"]
        / merged["huggingface_price_output_usd_per_mtok"]
        - 1.0
    ) * 100
    return merged.loc[:, columns].drop_duplicates().sort_values(columns[:3]).reset_index(drop=True)


def compare_policy_surfaces(
    openrouter: pd.DataFrame, huggingface: pd.DataFrame, aliases: dict[str, str]
) -> pd.DataFrame:
    """Align public allocation proxies without treating either as realized flow."""
    columns = [
        "openrouter_model_id",
        "huggingface_model_id",
        "scenario",
        "provider_id",
        "openrouter_simulated_share",
        "hf_cheapest_public_share",
        "hf_fastest_reported_share",
    ]
    if openrouter.empty or huggingface.empty or not aliases:
        return pd.DataFrame(columns=columns)
    mapping = pd.DataFrame(
        [
            {"openrouter_model_id": left, "huggingface_model_id": right}
            for left, right in aliases.items()
        ]
    )
    left = openrouter.copy().rename(columns={"model_id": "openrouter_model_id"})
    left["provider_id"] = left["provider_name"].map(canonical_provider)
    left = left.merge(mapping, on="openrouter_model_id", how="inner")
    left = left.rename(columns={"simulated_route_share": "openrouter_simulated_share"})
    right = huggingface.copy().rename(columns={"model_id": "huggingface_model_id"})
    right["provider_id"] = right["provider_name"].map(canonical_provider)
    index = ["huggingface_model_id", "scenario", "provider_id"]
    right = right.pivot_table(
        index=index,
        columns="policy",
        values="simulated_route_share",
        aggfunc="first",
    ).reset_index()
    right = right.rename(
        columns={
            "hf_cheapest_public_quote": "hf_cheapest_public_share",
            "hf_fastest_reported_throughput": "hf_fastest_reported_share",
        }
    )
    merged = left.merge(right, on=index, how="inner")
    for column in ("hf_cheapest_public_share", "hf_fastest_reported_share"):
        if column not in merged:
            merged[column] = np.nan
    return merged.loc[:, columns].drop_duplicates().sort_values(columns[:4]).reset_index(drop=True)


def _latest_openrouter() -> pd.DataFrame:
    glob = data.table_glob("endpoints_snapshots")
    try:
        return data.q(
            f"""
            with latest as (select max(run_ts) as run_ts from read_parquet('{glob}'))
            select model_id, provider_name, price_prompt, price_completion
            from read_parquet('{glob}') as s, latest
            where s.run_ts = latest.run_ts
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def _latest_huggingface() -> pd.DataFrame:
    glob = data.table_glob("hf_router_endpoint_snapshots")
    try:
        return data.q(
            f"""
            with latest as (select max(run_ts) as run_ts from read_parquet('{glob}'))
            select model_id, provider_name, price_input_usd_per_mtok, price_output_usd_per_mtok
            from read_parquet('{glob}') as s, latest
            where s.run_ts = latest.run_ts
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def _latest_openrouter_policy() -> pd.DataFrame:
    glob = data.table_glob("routing_simulation")
    try:
        return data.q(
            f"""
            with latest as (select max(run_ts) as run_ts from read_parquet('{glob}'))
            select model_id, scenario, provider_name, simulated_route_share
            from read_parquet('{glob}') as s, latest
            where s.run_ts = latest.run_ts
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def _latest_huggingface_policy() -> pd.DataFrame:
    glob = data.table_glob("hf_router_policy_simulation")
    try:
        return data.q(
            f"""
            with latest as (select max(run_ts) as run_ts from read_parquet('{glob}'))
            select model_id, scenario, provider_name, policy, simulated_route_share
            from read_parquet('{glob}') as s, latest
            where s.run_ts = latest.run_ts
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    version, aliases = model_map()
    quote_panel = match_quotes(_latest_openrouter(), _latest_huggingface(), aliases)
    policy_panel = compare_policy_surfaces(
        _latest_openrouter_policy(), _latest_huggingface_policy(), aliases
    )
    save(quote_panel, out_dir, "h44_cross_router_quotes")
    save(policy_panel, out_dir, "h44_cross_router_policy_surface")
    result = {
        "mapping_version": version,
        "mapped_models": len(aliases),
        "matched_provider_quote_pairs": int(len(quote_panel)),
        "matched_policy_provider_rows": int(len(policy_panel)),
        "median_output_basis_pct": (
            float(quote_panel["output_basis_pct"].median()) if not quote_panel.empty else None
        ),
        "claim_boundary": (
            "Public provider quote/performance metadata and simulated policy surfaces only; "
            "not either router's global routed volume or realized provider selections."
        ),
    }
    save_json(result, out_dir, "h44_cross_router_summary")
    return result
