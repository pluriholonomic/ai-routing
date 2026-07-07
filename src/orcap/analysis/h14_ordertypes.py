"""H14 — Order-type mix: OpenRouter variants as order types.

`:floor` = market-at-best-price (price priority), `:nitro` = speed priority,
default = smart-routed, `:free` = subsidized flow. The mix is the inference
analog of market/limit order composition. Level facts now; the pre-registered
dynamic test (floor share rising with within-model dispersion) needs weeks of
variance.

  h14_variant_shares   tokens by variant × day (+ per-model breakdown)
  h14_summary          global shares
"""

import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_variant_flow() -> pd.DataFrame:
    return data.q(
        f"""
        select cast(date as varchar) as date, variant,
               sum(total_prompt_tokens + total_completion_tokens) as tokens,
               sum(request_count) as requests,
               count(distinct model_permaslug) as n_models
        from read_parquet('{data.table_glob("model_activity_daily")}')
        group by 1, 2 order by 1, 2
        """
    ).df()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_variant_flow()
    save(df, out_dir, "h14_variant_shares")
    latest_day = df["date"].max()
    day = df[df["date"] == latest_day].copy()
    tot = day["tokens"].sum()
    shares = {r.variant: round(float(r.tokens / tot), 4) for r in day.itertuples(index=False)}
    results = {
        "date": latest_day,
        "token_share_by_variant": shares,
        "n_variants": int(day["variant"].nunique()),
        "note": "floor-share vs dispersion interaction pre-registered; needs weeks of variance",
    }
    save_json(results, out_dir, "h14_summary")
    log.info("H14: %s", results)
    return results
