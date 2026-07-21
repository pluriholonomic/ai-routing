"""Audit and persist the paid-only empirical population.

Pricing and provider-behavior tests use the paid population.  Subsidized free
routes remain available as a separate demand-creation treatment; they are not
silently mixed into price, competition, or pass-through estimates.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .market_scope import is_free_model_id, paid_activity_mask, paid_model_mask


def load_activity() -> pd.DataFrame:
    return data.q(
        f"""
        select substr(cast(date as varchar), 1, 10) as day,
               cast(model_permaslug as varchar) as model_permaslug,
               cast(variant as varchar) as variant,
               sum(total_prompt_tokens + total_completion_tokens) as tokens,
               sum(request_count) as requests
        from read_parquet('{data.table_glob("model_activity_daily")}', union_by_name=true)
        group by 1, 2, 3
        """
    ).df()


def activity_scope_panel(activity: pd.DataFrame) -> pd.DataFrame:
    """Daily paid/free accounting with an explicit, auditable denominator."""

    columns = [
        "day",
        "paid_tokens",
        "free_tokens",
        "unclassified_tokens",
        "all_tokens",
        "paid_requests",
        "free_requests",
        "unclassified_requests",
        "all_requests",
        "free_token_share",
        "free_request_share",
    ]
    if activity.empty:
        return pd.DataFrame(columns=columns)
    frame = activity.copy()
    frame["tokens"] = pd.to_numeric(frame["tokens"], errors="coerce").fillna(0.0)
    frame["requests"] = pd.to_numeric(frame["requests"], errors="coerce").fillna(0.0)
    frame["is_paid"] = paid_activity_mask(frame)
    variant = frame["variant"].astype("string").str.strip().str.casefold()
    frame["is_free"] = variant.eq("free").fillna(False) | frame["model_permaslug"].map(
        is_free_model_id
    )
    frame["scope"] = "unclassified"
    frame.loc[frame["is_free"], "scope"] = "free"
    frame.loc[frame["is_paid"], "scope"] = "paid"
    grouped = (
        frame.groupby(["day", "scope"], as_index=False)[["tokens", "requests"]]
        .sum()
        .pivot(index="day", columns="scope", values=["tokens", "requests"])
        .fillna(0.0)
    )
    grouped.columns = [f"{scope}_{measure}" for measure, scope in grouped.columns]
    grouped = grouped.reset_index()
    for column in (
        "paid_tokens",
        "free_tokens",
        "unclassified_tokens",
        "paid_requests",
        "free_requests",
        "unclassified_requests",
    ):
        if column not in grouped:
            grouped[column] = 0.0
    grouped["all_tokens"] = (
        grouped["paid_tokens"] + grouped["free_tokens"] + grouped["unclassified_tokens"]
    )
    grouped["all_requests"] = (
        grouped["paid_requests"]
        + grouped["free_requests"]
        + grouped["unclassified_requests"]
    )
    grouped["free_token_share"] = grouped["free_tokens"] / grouped["all_tokens"].replace(0, pd.NA)
    grouped["free_request_share"] = grouped["free_requests"] / grouped[
        "all_requests"
    ].replace(0, pd.NA)
    return grouped[columns].sort_values("day").reset_index(drop=True)


def load_latest_catalog() -> pd.DataFrame:
    return data.q(
        f"""
        with catalog as (
          select * from read_parquet(
            '{data.table_glob("models_snapshots")}', union_by_name=true
          )
        ), latest as (select max(run_ts) as run_ts from catalog)
        select cast(id as varchar) as model_id,
               cast(canonical_slug as varchar) as canonical_slug,
               try_cast(price_prompt as double) as price_prompt,
               try_cast(price_completion as double) as price_completion
        from catalog join latest using (run_ts)
        """
    ).df()


def load_latest_endpoints() -> pd.DataFrame:
    return data.q(
        f"""
        select cast(model_id as varchar) as model_id,
               cast(provider_name as varchar) as provider_name,
               try_cast(price_prompt as double) as price_prompt,
               try_cast(price_completion as double) as price_completion
        from {data.latest_endpoints()}
        """
    ).df()


def load_completion_events() -> pd.DataFrame:
    return data.q(
        f"""
        select cast(dt as varchar) as day, cast(model_id as varchar) as model_id,
               cast(provider_name as varchar) as provider_name,
               try_cast(old_value as double) as old_price,
               try_cast(new_value as double) as new_price
        from read_parquet(
          '{data.table_glob("pricing_changes", layer="derived")}', union_by_name=true
        )
        where field = 'price_completion'
          and try_cast(old_value as double) > 0
          and try_cast(new_value as double) > 0
          and try_cast(old_value as double) != try_cast(new_value as double)
        """
    ).df()


def _scope_counts(
    catalog: pd.DataFrame,
    endpoints: pd.DataFrame,
    events: pd.DataFrame,
) -> dict[str, Any]:
    catalog_paid = paid_model_mask(catalog["model_id"])
    endpoint_paid = paid_model_mask(endpoints["model_id"])
    event_paid = paid_model_mask(events["model_id"])
    catalog_free = catalog["model_id"].map(is_free_model_id)
    endpoint_free = endpoints["model_id"].map(is_free_model_id)
    event_free = events["model_id"].map(is_free_model_id)
    positive_endpoint = pd.to_numeric(endpoints["price_completion"], errors="coerce").gt(0)
    paid_variants = catalog["model_id"].astype("string").str.contains(":", regex=False, na=False)
    paid_variants &= catalog_paid
    return {
        "catalog_models": int(len(catalog)),
        "catalog_free_models": int(catalog_free.sum()),
        "catalog_paid_models": int(catalog_paid.sum()),
        "catalog_unclassified_models": int((~catalog_paid & ~catalog_free).sum()),
        "catalog_paid_colon_variants": int(paid_variants.sum()),
        "latest_endpoint_rows": int(len(endpoints)),
        "latest_positive_paid_endpoint_rows": int((endpoint_paid & positive_endpoint).sum()),
        "latest_free_endpoint_rows": int(endpoint_free.sum()),
        "latest_unclassified_endpoint_rows": int((~endpoint_paid & ~endpoint_free).sum()),
        "positive_completion_price_events": int(len(events)),
        "paid_completion_price_events": int(event_paid.sum()),
        "free_completion_price_events": int(event_free.sum()),
        "unclassified_completion_price_events": int((~event_paid & ~event_free).sum()),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    activity = load_activity()
    daily = activity_scope_panel(activity)
    catalog = load_latest_catalog()
    endpoints = load_latest_endpoints()
    events = load_completion_events()
    catalog = catalog.assign(is_free_model=catalog["model_id"].map(is_free_model_id))
    scope_counts = _scope_counts(catalog, endpoints, events)
    complete = daily.iloc[-2] if len(daily) >= 2 else (daily.iloc[-1] if len(daily) else None)
    summary: dict[str, Any] = {
        "population": "paid_only_primary_free_tier_separate",
        "definition": (
            "exclude model IDs ending :free and openrouter/free; exclude activity rows "
            "whose variant is free; require positive completion prices in completion-price tests"
        ),
        "hf_revision": os.environ.get("ORCAP_HF_REVISION") or None,
        **scope_counts,
        "latest_complete_activity_day": str(complete["day"]) if complete is not None else None,
        "latest_complete_paid_tokens": float(complete["paid_tokens"])
        if complete is not None
        else None,
        "latest_complete_free_tokens": float(complete["free_tokens"])
        if complete is not None
        else None,
        "latest_complete_free_token_share": float(complete["free_token_share"])
        if complete is not None and pd.notna(complete["free_token_share"])
        else None,
        "pricing_results_affected_by_free_filter": bool(
            scope_counts["free_completion_price_events"]
        ),
        "unfilterable_sources": [
            "source-defined aggregate Other rows without model or variant identity",
            "public app-wide rankings without model or variant identity",
        ],
        "claim_boundary": (
            "Paid-only removes observed subsidized/free routes from the estimand. It does not "
            "identify provider marginal cost, subsidy incidence, private eligibility, or flow."
        ),
    }
    save(daily, out_dir, "paid_market_activity_daily")
    save(catalog, out_dir, "paid_market_catalog_scope")
    save_json(summary, out_dir, "paid_market_scope_summary")
    return summary
