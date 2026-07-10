"""H13 — Venue basis: OpenRouter quote vs the provider's own list price.

RFQ-consistent null: basis ≡ 0 (aggregator displays maker quotes verbatim,
take levied off-quote). Panel version (pre-registered): transient deviations
around provider repricing events measure the router's quote-refresh latency.

Providers covered = whatever ``capture_direct`` parses (currently DeepInfra's
structured API, Together's published serverless-price table, and a bounded
Fireworks first-party model-page list).  Source type is retained in the output:
published-page observations are posted list quotes, not evidence of an
API-level firm quote or a fill.

  h13_basis          per provider × model × day: routed vs direct price, basis
  h13_summary        share of exact matches, basis distribution
"""

import json
import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

MIN_DAYS = 7
MIN_PAIRS = 50
MIN_PROVIDERS = 3
MIN_PAIRS_PER_PROVIDER = 10

# OpenRouter display name -> capture_direct provider key. The model key is
# joined exactly: it is usually the provider API id, can be a literal
# first-party ``hugging_face_id`` (Cerebras), or a versioned, evidence-backed
# one-to-one canonical map (SambaNova). Provider aliases or product-name
# similarities never count as a venue-basis match.
PROVIDER_MAP = {
    "Cerebras": "cerebras",
    "DeepInfra": "deepinfra",
    "Together": "together",
    "Fireworks": "fireworks",
    "Groq": "groq",
    "Novita": "novita",
    "SambaNova": "sambanova",
}


def load_routed() -> pd.DataFrame:
    rows = data.q(
        f"""
        select cast(dt as varchar) as dt, provider_display_name, record_json
        from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        where variant = 'standard'
        """
    ).df()
    out = []
    for r in rows.itertuples(index=False):
        if r.provider_display_name not in PROVIDER_MAP:
            continue
        d = json.loads(r.record_json)
        pricing = d.get("pricing") or {}
        # The documented REST endpoint calls this field ``model_id`` while
        # older frontend captures use ``provider_model_id``.  Both are source
        # identifiers, unlike the human-readable model name, so this preserves
        # the exact-ID join across a harmless upstream field rename.
        model_name = d.get("provider_model_id") or d.get("model_id")
        try:
            pin, pout = float(pricing.get("prompt")), float(pricing.get("completion"))
        except (TypeError, ValueError):
            continue
        if not model_name:
            continue
        out.append(
            {
                "dt": r.dt,
                "provider": PROVIDER_MAP[r.provider_display_name],
                "model_name": model_name,
                "routed_in": pin,
                "routed_out": pout,
            }
        )
    return pd.DataFrame(out).drop_duplicates(["dt", "provider", "model_name"])


def load_direct() -> pd.DataFrame:
    glob = data.table_glob("direct_prices_daily")
    try:
        schema = data.q(
            f"describe select * from read_parquet('{glob}', union_by_name=true)"
        ).df()
        columns = set(schema["column_name"])
    except Exception:
        columns = set()
    source_type = (
        "coalesce(direct.source_type, 'structured_public_api')"
        if "source_type" in columns
        else "'structured_public_api'"
    )
    source_url = "direct.source_url" if "source_url" in columns else "cast(null as varchar)"
    model_name = (
        "coalesce(nullif(direct.canonical_model_id, ''), direct.model_name)"
        if "canonical_model_id" in columns
        else "direct.model_name"
    )
    # materialize the scan before filtering: planning comparisons directly over a
    # union_by_name parquet scan can hit DuckDB's NumericValueUnionToValue internal
    # error when merging file-level column statistics (duckdb/duckdb#18267)
    con = data.connect()
    con.execute(
        f"create temp table _h13_direct as select * from read_parquet('{glob}', union_by_name=true)"
    )
    return con.sql(
        f"""
        with latest_per_day as (
            select cast(direct.dt as varchar) as dt, direct.run_ts, direct.provider,
                   {model_name} as model_name, direct.price_input_usd as direct_in,
                   direct.price_output_usd as direct_out,
                   {source_type} as source_type,
                   {source_url} as source_url,
                   row_number() over (
                       partition by direct.dt, direct.provider, {model_name}
                       order by direct.run_ts desc
                   ) as recency_rank
            from _h13_direct as direct
            where not direct.deprecated
              and direct.price_input_usd > 0
              and direct.price_output_usd > 0
        )
        select * exclude (recency_rank) from latest_per_day where recency_rank = 1
        """
    ).df()


def summarize(m: pd.DataFrame) -> dict:
    """Report H13 coverage before interpreting a broker-basis estimate.

    An exact match between one router price and one posted provider page is a
    useful source check.  It is not evidence that the inference market as a
    whole passes through maker quotes.  The pre-declared gate requires breadth
    across providers, repeated daily observations, and enough matches within
    each provider to prevent a single catalog from carrying the conclusion.
    """
    if m.empty:
        return {
            "n_pairs": 0,
            "evidence_status": "power_gated",
            "note": "no overlapping (dt, provider, model) yet",
        }
    provider_counts = m.groupby("provider").size().sort_index()
    days = int(m["dt"].nunique())
    reasons = []
    if days < MIN_DAYS:
        reasons.append(f"only {days}/{MIN_DAYS} daily observations")
    if len(m) < MIN_PAIRS:
        reasons.append(f"only {len(m)}/{MIN_PAIRS} matched pairs")
    if len(provider_counts) < MIN_PROVIDERS:
        reasons.append(f"only {len(provider_counts)}/{MIN_PROVIDERS} providers")
    thin = provider_counts[provider_counts < MIN_PAIRS_PER_PROVIDER]
    if not thin.empty:
        reasons.append(
            "providers below "
            f"{MIN_PAIRS_PER_PROVIDER} pairs: {', '.join(thin.index.tolist())}"
        )
    return {
        "n_pairs": int(len(m)),
        "n_days": days,
        "providers": sorted(m["provider"].unique()),
        "provider_pairs": {provider: int(count) for provider, count in provider_counts.items()},
        "source_types": {
            provider: sorted(group["source_type"].dropna().unique())
            for provider, group in m.groupby("provider")
        },
        "share_exact_zero_basis": float((m["basis_out_pct"].abs() < 0.01).mean()),
        "max_abs_basis_pct": float(m["basis_out_pct"].abs().max()),
        "rfq_null": "basis ≡ 0 (quote passthrough); deviations = stale-quote windows",
        "temporal_boundary": (
            "daily matched posted quotes; this panel cannot identify intraday refresh latency"
        ),
        "power_gate": {
            "min_days": MIN_DAYS,
            "min_pairs": MIN_PAIRS,
            "min_providers": MIN_PROVIDERS,
            "min_pairs_per_provider": MIN_PAIRS_PER_PROVIDER,
        },
        "evidence_status": "provisional_descriptive" if not reasons else "power_gated",
        "gate_reasons": reasons,
        "claim_boundary": (
            "posted list-price comparison only; it does not identify executable fills, "
            "routing decisions, or market-wide quote passthrough"
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    routed, direct = load_routed(), load_direct()
    m = routed.merge(direct, on=["dt", "provider", "model_name"])
    m = m[(m["routed_out"] > 0) & (m["direct_out"] > 0)].copy()
    m["basis_out_pct"] = (m["routed_out"] / m["direct_out"] - 1) * 100
    m["basis_in_pct"] = (m["routed_in"] / m["direct_in"] - 1) * 100
    save(m, out_dir, "h13_basis")
    if not m.empty:
        provider_day = (
            m.groupby(["dt", "provider", "source_type"], as_index=False)
            .agg(
                matched_models=("model_name", "nunique"),
                median_basis_out_pct=("basis_out_pct", "median"),
                median_basis_in_pct=("basis_in_pct", "median"),
                exact_zero_share=("basis_out_pct", lambda x: (x.abs() < 0.01).mean()),
            )
            .sort_values(["dt", "provider"])
        )
        save(provider_day, out_dir, "h13_provider_day")
    results = summarize(m)
    save_json(results, out_dir, "h13_summary")
    log.info("H13: %s", results)
    return results
