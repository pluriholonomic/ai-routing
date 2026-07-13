"""H72 — OpenRouter's documented public-app ranking panel.

The source excludes hidden/private apps, merges aliases, and exposes only a
bounded rank window.  H72 therefore measures concentration and turnover among
public attributed apps; it never interprets an absent app as zero traffic and
does not construct app-by-model or provider routing shares.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

SOURCE = "openrouter_app_rankings_daily"
MIN_DAYS = 90
MIN_APPS_PER_DAY = 50
KEYS = ["source_date", "app_id", "ranking_sort", "category", "subcategory"]
REVISION_COLUMNS = [
    *KEYS,
    "app_name",
    "rank",
    "total_requests",
    "total_tokens",
    "is_public_attributed_only",
    "is_top_n_censored",
    "latest_run_ts",
    "n_revisions",
]
DAILY_COLUMNS = [
    "source_date",
    "ranking_sort",
    "category",
    "subcategory",
    "visible_apps",
    "visible_total_requests",
    "visible_total_tokens",
    "top1_request_share_visible",
    "top10_request_share_visible",
    "request_hhi_visible",
    "top1_token_share_visible",
    "top10_token_share_visible",
    "token_hhi_visible",
    "token_entropy_visible",
    "max_observed_rank",
    "is_public_attributed_only",
    "is_top_n_censored",
]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def load_app_rankings() -> pd.DataFrame:
    required = {
        "run_ts",
        "source",
        "source_date",
        "app_id",
        "app_name",
        "rank",
        "total_requests",
        "total_tokens",
        "ranking_sort",
        "category",
        "subcategory",
        "is_public_attributed_only",
        "is_top_n_censored",
    }
    try:
        glob = data.table_glob(SOURCE)
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return _empty(REVISION_COLUMNS)
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(source_date as varchar) as source_date,
                   cast(app_id as varchar) as app_id,
                   cast(app_name as varchar) as app_name,
                   rank, total_requests, total_tokens,
                   cast(ranking_sort as varchar) as ranking_sort,
                   cast(category as varchar) as category,
                   cast(subcategory as varchar) as subcategory,
                   is_public_attributed_only, is_top_n_censored
            from read_parquet('{glob}', union_by_name=true)
            where source = '{SOURCE}'
            """
        ).df()
    except Exception:
        return _empty(REVISION_COLUMNS)


def latest_revisions(rows: pd.DataFrame) -> pd.DataFrame:
    required = {
        "run_ts",
        "source_date",
        "app_id",
        "app_name",
        "rank",
        "total_requests",
        "total_tokens",
        "ranking_sort",
        "category",
        "subcategory",
        "is_public_attributed_only",
        "is_top_n_censored",
    }
    if rows.empty or not required.issubset(rows.columns):
        return _empty(REVISION_COLUMNS)
    panel = rows.copy()
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    panel["source_date"] = pd.to_datetime(panel["source_date"], utc=True, errors="coerce")
    for column in ["rank", "total_requests", "total_tokens"]:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    panel = panel.dropna(
        subset=[
            "captured_at",
            "source_date",
            "app_id",
            "app_name",
            "rank",
            "total_requests",
            "total_tokens",
            "ranking_sort",
        ]
    )
    panel = panel.loc[
        panel["rank"].ge(1)
        & panel["total_requests"].ge(0)
        & panel["total_tokens"].ge(0)
        & panel["app_id"].ne("")
    ].copy()
    if panel.empty:
        return _empty(REVISION_COLUMNS)
    panel["source_date"] = panel["source_date"].dt.strftime("%Y-%m-%d")
    panel["category"] = panel["category"].fillna("")
    panel["subcategory"] = panel["subcategory"].fillna("")
    revisions = panel.groupby(KEYS, dropna=False).size().rename("n_revisions").reset_index()
    latest = panel.sort_values("captured_at").drop_duplicates(KEYS, keep="last")
    latest = latest.merge(revisions, on=KEYS, how="inner", validate="one_to_one")
    latest = latest.rename(columns={"run_ts": "latest_run_ts"})
    return latest.loc[:, REVISION_COLUMNS].sort_values(KEYS).reset_index(drop=True)


def _shares(values: pd.Series) -> tuple[float | None, float | None, float | None]:
    values = pd.to_numeric(values, errors="coerce").fillna(0).clip(lower=0).sort_values(
        ascending=False
    )
    total = float(values.sum())
    if total <= 0:
        return None, None, None
    shares = values / total
    return float(shares.iloc[0]), float(shares.iloc[:10].sum()), float((shares**2).sum())


def daily_panel(revisions: pd.DataFrame) -> pd.DataFrame:
    if revisions.empty or not set(REVISION_COLUMNS).issubset(revisions.columns):
        return _empty(DAILY_COLUMNS)
    output = []
    scope = ["source_date", "ranking_sort", "category", "subcategory"]
    for key, group in revisions.groupby(scope, dropna=False, sort=True):
        request_top1, request_top10, request_hhi = _shares(group["total_requests"])
        token_top1, token_top10, token_hhi = _shares(group["total_tokens"])
        token_values = pd.to_numeric(group["total_tokens"], errors="coerce").fillna(0).clip(lower=0)
        token_total = float(token_values.sum())
        token_entropy = None
        if token_total > 0:
            shares = token_values[token_values.gt(0)] / token_total
            token_entropy = float(-(shares * np.log(shares)).sum())
        output.append(
            {
                "source_date": key[0],
                "ranking_sort": key[1],
                "category": key[2],
                "subcategory": key[3],
                "visible_apps": int(group["app_id"].nunique()),
                "visible_total_requests": int(group["total_requests"].sum()),
                "visible_total_tokens": int(group["total_tokens"].sum()),
                "top1_request_share_visible": request_top1,
                "top10_request_share_visible": request_top10,
                "request_hhi_visible": request_hhi,
                "top1_token_share_visible": token_top1,
                "top10_token_share_visible": token_top10,
                "token_hhi_visible": token_hhi,
                "token_entropy_visible": token_entropy,
                "max_observed_rank": int(group["rank"].max()),
                "is_public_attributed_only": bool(group["is_public_attributed_only"].all()),
                "is_top_n_censored": bool(group["is_top_n_censored"].all()),
            }
        )
    return pd.DataFrame(output, columns=DAILY_COLUMNS)


def coverage_gate(panel: pd.DataFrame) -> dict:
    popular = (
        panel.loc[
            panel["ranking_sort"].eq("popular")
            & panel["category"].fillna("").eq("")
            & panel["subcategory"].fillna("").eq("")
        ].copy()
        if not panel.empty
        else panel
    )
    if popular.empty:
        return {
            "status": "not_identified",
            "source_days": 0,
            "complete_source_days": 0,
            "minimum_days": MIN_DAYS,
            "minimum_visible_apps": MIN_APPS_PER_DAY,
        }
    complete = popular.loc[
        popular["visible_apps"].ge(MIN_APPS_PER_DAY)
        & popular["is_public_attributed_only"].eq(True)
        & popular["is_top_n_censored"].eq(True)
    ]
    dates = pd.to_datetime(popular["source_date"], utc=True, errors="coerce").dropna()
    missing_days = int((dates.max() - dates.min()).days + 1 - dates.nunique()) if len(dates) else 0
    reasons = []
    if len(popular) < MIN_DAYS:
        reasons.append(f"only {len(popular)}/{MIN_DAYS} public-app source days")
    if len(complete) < MIN_DAYS:
        reasons.append(
            f"only {len(complete)}/{MIN_DAYS} days with at least {MIN_APPS_PER_DAY} visible apps"
        )
    if missing_days:
        reasons.append(f"{missing_days} calendar day(s) missing inside observed range")
    return {
        "status": "public_app_panel_ready" if not reasons else "power_gated",
        "source_days": int(len(popular)),
        "complete_source_days": int(len(complete)),
        "minimum_days": MIN_DAYS,
        "minimum_visible_apps": MIN_APPS_PER_DAY,
        "missing_calendar_days": missing_days,
        "gate_reasons": reasons,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_app_rankings()
    revisions = latest_revisions(rows)
    daily = daily_panel(revisions)
    result = {
        "captured_rows": int(len(rows)),
        "latest_app_day_rows": int(len(revisions)),
        "coverage_gate": coverage_gate(daily),
        "claim_boundary": (
            "H72 measures concentration and turnover only among OpenRouter public attributed "
            "apps in the observed rank window. Hidden/private apps are excluded, aliases are "
            "merged, token accounting can differ by upstream provider, and absent ranks are "
            "censored rather than zero. It is not app-by-model or provider routing."
        ),
    }
    save(revisions, out_dir, "h72_openrouter_app_revisions")
    save(daily, out_dir, "h72_openrouter_app_daily")
    save_json(result, out_dir, "h72_summary")
    return result
