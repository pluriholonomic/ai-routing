"""H64 — OpenRouter's documented aggregate daily model-token demand panel.

This source publishes the top 50 public models by daily total token usage plus
one source-defined long-tail aggregate. It measures model-demand concentration
within OpenRouter's reported aggregate, not provider routing, request flow,
prompt content, user behaviour, or comparable tokens across providers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

SOURCE = "openrouter_rankings_daily"
MIN_DAYS = 30
MIN_TOP_MODELS_PER_DAY = 50
REVISIONS_COLUMNS = [
    "source_date",
    "model_permaslug",
    "total_tokens",
    "is_other_aggregate",
    "latest_run_ts",
    "n_revisions",
]
DAILY_COLUMNS = [
    "source_date",
    "total_tokens",
    "source_reported_top50_model_tokens",
    "source_reported_other_tokens",
    "source_reported_top50_token_share",
    "source_reported_other_token_share",
    "top1_model_token_share_total",
    "top50_observed_models",
    "has_source_reported_other",
]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def load_rankings_daily() -> pd.DataFrame:
    """Load the opt-in aggregate usage table if it has been captured."""
    required = {
        "run_ts",
        "source",
        "source_date",
        "model_permaslug",
        "total_tokens",
        "is_other_aggregate",
    }
    try:
        glob = data.table_glob(SOURCE)
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return _empty(REVISIONS_COLUMNS)
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(source_date as varchar) as source_date,
                   cast(model_permaslug as varchar) as model_permaslug,
                   total_tokens,
                   is_other_aggregate
            from read_parquet('{glob}', union_by_name=true)
            where source = '{SOURCE}'
            """
        ).df()
    except Exception:
        return _empty(REVISIONS_COLUMNS)


def latest_revisions(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest immutable capture for each source-day/model revision."""
    required = {
        "run_ts",
        "source_date",
        "model_permaslug",
        "total_tokens",
        "is_other_aggregate",
    }
    if rows.empty or not required.issubset(rows.columns):
        return _empty(REVISIONS_COLUMNS)
    panel = rows.copy()
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    panel["source_date"] = pd.to_datetime(panel["source_date"], utc=True, errors="coerce")
    panel["total_tokens"] = pd.to_numeric(panel["total_tokens"], errors="coerce")
    panel["is_other_aggregate"] = panel["is_other_aggregate"].astype("boolean")
    panel = panel.dropna(
        subset=[
            "captured_at",
            "source_date",
            "model_permaslug",
            "total_tokens",
            "is_other_aggregate",
        ]
    )
    panel = panel.loc[(panel["total_tokens"] >= 0) & panel["model_permaslug"].ne("")].copy()
    if panel.empty:
        return _empty(REVISIONS_COLUMNS)
    panel["source_date"] = panel["source_date"].dt.strftime("%Y-%m-%d")
    keys = ["source_date", "model_permaslug"]
    revisions = panel.groupby(keys).size().rename("n_revisions").reset_index()
    latest = panel.sort_values("captured_at").drop_duplicates(keys, keep="last")
    latest = latest.merge(revisions, on=keys, how="inner", validate="one_to_one")
    latest = latest.rename(columns={"run_ts": "latest_run_ts"})
    return latest.loc[:, REVISIONS_COLUMNS].sort_values(keys).reset_index(drop=True)


def daily_panel(revisions: pd.DataFrame) -> pd.DataFrame:
    """Summarize daily top-50 and source-defined long-tail concentration."""
    if revisions.empty or not set(REVISIONS_COLUMNS).issubset(revisions.columns):
        return _empty(DAILY_COLUMNS)
    panel = revisions.copy()
    panel["total_tokens"] = pd.to_numeric(panel["total_tokens"], errors="coerce")
    panel = panel.dropna(subset=["source_date", "model_permaslug", "total_tokens"])
    panel = panel.loc[panel["total_tokens"] >= 0].copy()
    if panel.empty:
        return _empty(DAILY_COLUMNS)
    output = []
    for source_date, group in panel.groupby("source_date", sort=True):
        other = group.loc[group["is_other_aggregate"]]
        models = group.loc[~group["is_other_aggregate"]]
        total = int(group["total_tokens"].sum())
        top50_tokens = int(models["total_tokens"].sum())
        other_tokens = int(other["total_tokens"].sum())
        output.append(
            {
                "source_date": source_date,
                "total_tokens": total,
                "source_reported_top50_model_tokens": top50_tokens,
                "source_reported_other_tokens": other_tokens,
                "source_reported_top50_token_share": top50_tokens / total if total else None,
                "source_reported_other_token_share": other_tokens / total if total else None,
                "top1_model_token_share_total": (
                    float(models["total_tokens"].max()) / total
                    if total and not models.empty
                    else None
                ),
                "top50_observed_models": int(models["model_permaslug"].nunique()),
                "has_source_reported_other": len(other) == 1,
            }
        )
    return pd.DataFrame(output, columns=DAILY_COLUMNS)


def coverage_gate(panel: pd.DataFrame) -> dict:
    """Require a complete 30-day aggregate panel before trend interpretation."""
    if panel.empty:
        return {
            "status": "not_identified",
            "source_days": 0,
            "complete_source_days": 0,
            "minimum_days": MIN_DAYS,
            "minimum_top_models_per_day": MIN_TOP_MODELS_PER_DAY,
        }
    complete = panel.loc[
        panel["has_source_reported_other"].eq(True)
        & panel["top50_observed_models"].ge(MIN_TOP_MODELS_PER_DAY)
    ]
    dates = pd.to_datetime(panel["source_date"], utc=True, errors="coerce").dropna().sort_values()
    missing_calendar_days = 0
    if not dates.empty:
        missing_calendar_days = int((dates.max() - dates.min()).days + 1 - dates.nunique())
    reasons = []
    if len(panel) < MIN_DAYS:
        reasons.append(f"only {len(panel)}/{MIN_DAYS} source days")
    if len(complete) < MIN_DAYS:
        reasons.append(
            f"only {len(complete)}/{MIN_DAYS} days with 50 ranked models and one other row"
        )
    if len(complete) != len(panel):
        reasons.append("one or more observed days lacks 50 ranked models or one other row")
    if missing_calendar_days:
        reasons.append(f"{missing_calendar_days} calendar day(s) missing inside observed range")
    return {
        "status": "aggregate_demand_panel_ready" if not reasons else "power_gated",
        "source_days": int(len(panel)),
        "complete_source_days": int(len(complete)),
        "minimum_days": MIN_DAYS,
        "minimum_top_models_per_day": MIN_TOP_MODELS_PER_DAY,
        "missing_calendar_days": missing_calendar_days,
        "gate_reasons": reasons,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_rankings_daily()
    revisions = latest_revisions(rows)
    daily = daily_panel(revisions)
    result = {
        "aggregate_usage_rows": int(len(rows)),
        "latest_model_day_rows": int(len(revisions)),
        "coverage_gate": coverage_gate(daily),
        "claim_boundary": (
            "H64 measures only OpenRouter's documented aggregate daily total-token ranking: "
            "the top 50 public models plus one source-defined other aggregate. It does not "
            "identify provider routing/allocation, requests, prompts, completions, users, "
            "prices, latency, revenue, model quality, causal demand, or tokens comparable "
            "across providers."
        ),
    }
    save(revisions, out_dir, "h64_openrouter_usage_revisions")
    save(daily, out_dir, "h64_openrouter_usage_daily")
    save_json(result, out_dir, "h64_summary")
    return result
