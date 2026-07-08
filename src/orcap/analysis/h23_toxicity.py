"""H23 — Flow-toxicity index, validated against provider defenses.

Toxic flow = realized serving cost per billed token above average: long-context
low-cache agentic retry loops, subsidized free traffic. Components (model-day,
from model_activity_daily): low cache-hit share, tokens/request, reasoning
share, tool-call error rate, free-tier share. Index = mean of per-day z-scores
(cache share sign-flipped).

Validation (the definition of toxicity is flow that quoters ration): the index
must predict same-model-day provider defenses — reject rates and deranks from
endpoint_stats_daily. Runs nightly; power grows with the daily panel.
"""

import json
import logging
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def build_index() -> pd.DataFrame:
    df = data.q(
        f"""
        select substr(cast(date as varchar), 1, 10) as day, model_permaslug,
               sum(total_prompt_tokens) prompt_toks,
               sum(total_completion_tokens) completion_toks,
               sum(total_native_tokens_cached) cached_toks,
               sum(total_native_tokens_reasoning) reasoning_toks,
               sum(request_count) requests,
               sum(requests_with_tool_call_errors) tool_err_reqs,
               sum(total_prompt_tokens) filter (where variant = 'free') free_prompt
        from read_parquet('{data.table_glob("model_activity_daily")}')
        group by 1, 2
        having sum(request_count) >= 100
        """
    ).df()
    df["cache_share"] = df["cached_toks"] / df["prompt_toks"].clip(lower=1)
    df["tokens_per_request"] = (df["prompt_toks"] + df["completion_toks"]) / df["requests"]
    df["reasoning_share"] = df["reasoning_toks"] / df["completion_toks"].clip(lower=1)
    df["tool_err_rate"] = df["tool_err_reqs"] / df["requests"]
    df["free_share"] = (df["free_prompt"].fillna(0)) / df["prompt_toks"].clip(lower=1)

    comps = ["cache_share", "tokens_per_request", "reasoning_share", "tool_err_rate", "free_share"]
    z = df.groupby("day")[comps].transform(lambda s: (s - s.mean()) / (s.std() + 1e-9))
    z["cache_share"] = -z["cache_share"]  # low cache = costlier per billed token
    df["toxicity"] = z.mean(axis=1)
    return df


def defenses() -> pd.DataFrame:
    rows = data.q(
        f"""
        select cast(dt as varchar) as day, model_permaslug, record_json
        from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        where variant = 'standard'
        """
    ).df()
    recs = []
    for r in rows.itertuples(index=False):
        d = json.loads(r.record_json)
        sh = d.get("status_heuristics_1d") or {}
        tot = sum(v or 0 for v in sh.values())
        if tot < 100:
            continue
        recs.append(
            {
                "day": r.day,
                "model_permaslug": r.model_permaslug,
                "rejects": (sh.get("rateLimited") or 0) + (sh.get("derankableError") or 0),
                "total": tot,
                "deranked": bool(d.get("is_deranked")),
            }
        )
    g = (
        pd.DataFrame(recs)
        .groupby(["day", "model_permaslug"])
        .agg(rejects=("rejects", "sum"), total=("total", "sum"), deranked=("deranked", "mean"))
        .reset_index()
    )
    g["reject_rate"] = g["rejects"] / g["total"]
    return g


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    idx = build_index()
    save(idx, out_dir, "h23_toxicity_index")
    dfn = defenses()
    m = idx.merge(dfn, on=["day", "model_permaslug"])
    results: dict = {
        "n_model_days": int(len(idx)),
        "n_matched_defense_days": int(len(m)),
        "n_days": int(idx["day"].nunique()),
    }
    if len(m) >= 200:
        m["day_f"] = m["day"]
        reg = smf.ols("reject_rate ~ toxicity + C(day_f)", data=m).fit(cov_type="HC1")
        results["validation"] = {
            "reject_on_toxicity": float(reg.params["toxicity"]),
            "se": float(reg.bse["toxicity"]),
            "pvalue": float(reg.pvalues["toxicity"]),
            "interpretation": "positive & significant = quoters ration flow the index calls toxic",
        }
        top = m.nlargest(8, "toxicity")[["model_permaslug", "toxicity", "reject_rate"]]
        results["most_toxic_model_days"] = top.round(3).to_dict("records")
    else:
        results["gated"] = f"validation needs >=200 matched model-days (have {len(m)})"
    save_json(results, out_dir, "h23_summary")
    log.info("H23: %s", {k: v for k, v in results.items() if k != "most_toxic_model_days"})
    return results
