"""H13 — Venue basis: OpenRouter quote vs the provider's own list price.

RFQ-consistent null: basis ≡ 0 (aggregator displays maker quotes verbatim,
take levied off-quote). Panel version (pre-registered): transient deviations
around provider repricing events measure the router's quote-refresh latency.

Providers covered = whatever ``capture_direct`` parses (currently DeepInfra's
structured API and Together's published serverless-price table).  Source type
is retained in the output: a docs-table observation is a posted list quote,
not evidence of an API-level firm quote or a fill.

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

# OpenRouter display name -> capture_direct provider key.  The model identifier
# is joined exactly: provider aliases or product-name similarities never count
# as a venue-basis match.
PROVIDER_MAP = {"DeepInfra": "deepinfra", "Together": "together"}


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
    return data.q(
        f"""
        with latest_per_day as (
            select cast(dt as varchar) as dt, run_ts, provider, model_name,
                   price_input_usd as direct_in, price_output_usd as direct_out,
                   coalesce(source_type, 'structured_public_api') as source_type,
                   source_url,
                   row_number() over (
                       partition by dt, provider, model_name order by run_ts desc
                   ) as recency_rank
            from read_parquet('{data.table_glob("direct_prices_daily")}', union_by_name=true)
            where not deprecated and price_input_usd > 0 and price_output_usd > 0
        )
        select * exclude (recency_rank) from latest_per_day where recency_rank = 1
        """
    ).df()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    routed, direct = load_routed(), load_direct()
    m = routed.merge(direct, on=["dt", "provider", "model_name"])
    m = m[(m["routed_out"] > 0) & (m["direct_out"] > 0)].copy()
    m["basis_out_pct"] = (m["routed_out"] / m["direct_out"] - 1) * 100
    m["basis_in_pct"] = (m["routed_in"] / m["direct_in"] - 1) * 100
    save(m, out_dir, "h13_basis")
    if m.empty:
        results = {"n_pairs": 0, "note": "no overlapping (dt, provider, model) yet"}
    else:
        results = {
            "n_pairs": int(len(m)),
            "n_days": int(m["dt"].nunique()),
            "providers": sorted(m["provider"].unique()),
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
        }
    save_json(results, out_dir, "h13_summary")
    log.info("H13: %s", results)
    return results
