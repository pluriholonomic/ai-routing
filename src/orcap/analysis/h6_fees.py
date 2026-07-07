"""H6 — Fee/take-rate structure, and quoted-vs-effective price gaps.

Two computations:
  1. Realized effective/listed price ratio per (model, provider) — the
     inference analog of effective vs quoted spread. Cache hits make the
     effective input price << listed; dispersion in this ratio measures how
     misleading listed prices are (like quoted vs realized execution).
  2. A static comparison table of platform take rates (OpenRouter ~5.5%
     credit fee vs DEX aggregator 0-30bps vs AMM LP fees vs solver rewards) —
     filled with cited constants in the memo; here we compute the OpenRouter-
     side quantities only.

  h6_effective_vs_listed   ratio table
  h6_summary               distribution stats
"""

import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_ratios() -> pd.DataFrame:
    return data.q(
        f"""
        with latest_ep as (
          select model_id, provider_name,
                 min(price_prompt) listed_in, min(price_completion) listed_out
          from {data.latest_endpoints()}
          where price_completion > 0
          group by 1, 2
        ),
        latest_eff as (
          select model_permaslug, provider_name,
                 avg(effective_input_price) eff_in_per_mtok,
                 avg(effective_output_price) eff_out_per_mtok,
                 avg(cache_hit_rate) cache_hit_rate,
                 sum(total_tokens) tokens
          from {data.effective_pricing()}
          where dt = (select max(dt) from {data.effective_pricing()})
          group by 1, 2
        ),
        slug_map as (
          select distinct canonical_slug, id
          from {data.models_snapshots()}
          where run_ts = (select max(run_ts) from {data.models_snapshots()})
            and id not like '%:%'
        )
        select e.model_permaslug, e.provider_name,
               l.listed_in * 1e6 as listed_in_per_mtok,
               l.listed_out * 1e6 as listed_out_per_mtok,
               e.eff_in_per_mtok, e.eff_out_per_mtok, e.cache_hit_rate, e.tokens,
               e.eff_in_per_mtok / nullif(l.listed_in * 1e6, 0) as in_ratio,
               e.eff_out_per_mtok / nullif(l.listed_out * 1e6, 0) as out_ratio
        from latest_eff e
        join slug_map s on s.canonical_slug = e.model_permaslug
        join latest_ep l on l.model_id = s.id and l.provider_name = e.provider_name
        """
    ).df()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_ratios()
    save(df, out_dir, "h6_effective_vs_listed")
    r = df["in_ratio"].dropna()
    results = {
        "n_pairs": int(len(df)),
        "median_effective_over_listed_input": float(r.median()) if len(r) else None,
        "p10": float(r.quantile(0.1)) if len(r) else None,
        "p90": float(r.quantile(0.9)) if len(r) else None,
        "median_cache_hit_rate": float(df["cache_hit_rate"].median()) if len(df) else None,
        "platform_take_rate_openrouter": 0.055,
        "note": "comparator take rates (aggregators, LPs, solvers) cited in memo",
    }
    save_json(results, out_dir, "h6_summary")
    log.info("H6: %s", results)
    return results
