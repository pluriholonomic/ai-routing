"""H13 — Venue basis: OpenRouter quote vs the provider's own list price.

RFQ-consistent null: basis ≡ 0 (aggregator displays maker quotes verbatim,
take levied off-quote). Panel version (pre-registered): transient deviations
around provider repricing events measure the router's quote-refresh latency.

Providers covered = whatever capture_direct parses (DeepInfra today; others
join as parsers land on their raw-archived pages).

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

# OpenRouter display name -> capture_direct provider key
PROVIDER_MAP = {"DeepInfra": "deepinfra"}


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
        try:
            pin, pout = float(pricing.get("prompt")), float(pricing.get("completion"))
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "dt": r.dt,
                "provider": PROVIDER_MAP[r.provider_display_name],
                "model_name": d.get("provider_model_id"),
                "routed_in": pin,
                "routed_out": pout,
            }
        )
    return pd.DataFrame(out).drop_duplicates(["dt", "provider", "model_name"])


def load_direct() -> pd.DataFrame:
    return data.q(
        f"""
        select cast(dt as varchar) as dt, provider, model_name,
               avg(price_input_usd) as direct_in, avg(price_output_usd) as direct_out
        from read_parquet('{data.table_glob("direct_prices_daily")}')
        where not deprecated and price_output_usd > 0
        group by 1, 2, 3
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
            "share_exact_zero_basis": float((m["basis_out_pct"].abs() < 0.01).mean()),
            "max_abs_basis_pct": float(m["basis_out_pct"].abs().max()),
            "rfq_null": "basis ≡ 0 (quote passthrough); deviations = stale-quote windows",
        }
    save_json(results, out_dir, "h13_summary")
    log.info("H13: %s", results)
    return results
