"""Opt-in capture of OpenRouter's documented aggregate daily usage dataset.

The API returns the top 50 public models per UTC day by total token usage and
one aggregated ``other`` row. It is authenticated, aggregate-only, and never
contains prompts, completions, user identifiers, provider allocation, or
individual generation records.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

RANKINGS_DAILY_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily"
APP_RANKINGS_URL = "https://openrouter.ai/api/v1/datasets/app-rankings"
SOURCE = "openrouter_rankings_daily"
APP_SOURCE = "openrouter_app_rankings_daily"
APP_PAGE_LIMIT = 100
APP_PAGE_OFFSETS = (0, 100)
MAX_APP_BACKFILL_DAYS = 200


def _date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _tokens(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _api_token() -> str | None:
    """Use the dataset-specific name first, then the existing probe secret name."""
    return os.environ.get("ORCAP_OPENROUTER_DATASET_API_KEY") or os.environ.get(
        "OPENROUTER_API_KEY"
    )


def _resolved_daily_range(start_date: str | None, end_date: str | None) -> list[str]:
    """Return inclusive closed UTC days, bounded to protect the account API quota."""
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None and _date(value) is None:
            raise ValueError(f"{name} must be YYYY-MM-DD")
    latest_closed = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    start_date = start_date or end_date or latest_closed
    end_date = end_date or start_date
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days = (end - start).days + 1
    if days > MAX_APP_BACKFILL_DAYS:
        raise ValueError(
            f"app rankings backfill is capped at {MAX_APP_BACKFILL_DAYS} days per run"
        )
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days)]


def rankings_daily_rows(
    body: Any,
    run_ts: str,
    dt: str,
    *,
    requested_start_date: str | None = None,
    requested_end_date: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fail closed unless every published aggregate row has the documented keys."""
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        return [], {"coverage_complete": False, "reason": "missing_data_list"}
    meta = body.get("meta")
    if not isinstance(meta, dict):
        return [], {"coverage_complete": False, "reason": "missing_meta"}
    start_date, end_date = _date(meta.get("start_date")), _date(meta.get("end_date"))
    as_of, version = meta.get("as_of"), meta.get("version")
    if (
        not start_date
        or not end_date
        or start_date > end_date
        or not isinstance(as_of, str)
        or not as_of
    ):
        return [], {"coverage_complete": False, "reason": "invalid_meta_dates"}
    if not isinstance(version, str) or not version:
        return [], {"coverage_complete": False, "reason": "missing_meta_version"}

    rows = []
    seen: set[tuple[str, str]] = set()
    other_per_day: dict[str, int] = {}
    models_per_day: dict[str, int] = {}
    for rank, item in enumerate(body["data"], start=1):
        if not isinstance(item, dict):
            return [], {"coverage_complete": False, "reason": "non_object_data_row"}
        observed_date = _date(item.get("date"))
        model = item.get("model_permaslug")
        total_tokens = _tokens(item.get("total_tokens"))
        if (
            not observed_date
            or observed_date < start_date
            or observed_date > end_date
            or not isinstance(model, str)
            or not model
            or total_tokens is None
        ):
            return [], {"coverage_complete": False, "reason": "invalid_data_row"}
        key = (observed_date, model)
        if key in seen:
            return [], {"coverage_complete": False, "reason": "duplicate_model_day"}
        seen.add(key)
        if model == "other":
            other_per_day[observed_date] = other_per_day.get(observed_date, 0) + 1
        else:
            models_per_day[observed_date] = models_per_day.get(observed_date, 0) + 1
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": SOURCE,
                "source_date": observed_date,
                "model_permaslug": model,
                "total_tokens": total_tokens,
                "is_other_aggregate": model == "other",
                "source_response_row_order": rank,
                "api_as_of": as_of,
                "api_start_date": start_date,
                "api_end_date": end_date,
                "api_version": version,
                "requested_start_date": requested_start_date,
                "requested_end_date": requested_end_date,
                "metric_definition": (
                    "OpenRouter documented daily aggregate: top 50 public models by total "
                    "prompt-plus-completion token usage plus one source-defined other row; "
                    "not provider allocation, a request tape, prompts, completions, users, "
                    "or executable routing flow"
                ),
                "record_json": json.dumps(item, separators=(",", ":"), sort_keys=True),
            }
        )
    if not rows:
        return [], {"coverage_complete": False, "reason": "empty_data"}
    observed_dates = {row["source_date"] for row in rows}
    if any(other_per_day.get(observed_date, 0) != 1 for observed_date in observed_dates):
        return [], {"coverage_complete": False, "reason": "missing_or_duplicate_other_row"}
    if any(count > 50 for count in models_per_day.values()):
        return [], {"coverage_complete": False, "reason": "more_than_top50_models"}
    if any(models_per_day.get(observed_date, 0) == 0 for observed_date in observed_dates):
        return [], {"coverage_complete": False, "reason": "missing_ranked_models"}
    return rows, {
        "coverage_complete": True,
        "source_dates": len(observed_dates),
        "top50_or_other_rows": len(rows),
        "other_rows": sum(row["is_other_aggregate"] for row in rows),
        "api_as_of": as_of,
        "api_start_date": start_date,
        "api_end_date": end_date,
        "api_version": version,
    }


def _url(start_date: str | None, end_date: str | None) -> str:
    query = {
        key: value
        for key, value in {"start_date": start_date, "end_date": end_date}.items()
        if value is not None
    }
    return RANKINGS_DAILY_URL if not query else f"{RANKINGS_DAILY_URL}?{urlencode(query)}"


def _app_url(
    source_date: str,
    *,
    sort: str,
    category: str | None,
    subcategory: str | None,
    offset: int,
) -> str:
    query: dict[str, Any] = {
        "start_date": source_date,
        "end_date": source_date,
        "sort": sort,
        "limit": APP_PAGE_LIMIT,
        "offset": offset,
    }
    if category:
        query["category"] = category
    if subcategory:
        query["subcategory"] = subcategory
    return f"{APP_RANKINGS_URL}?{urlencode(query)}"


def app_rankings_page_rows(
    body: Any,
    run_ts: str,
    dt: str,
    *,
    requested_date: str,
    sort: str,
    category: str | None,
    subcategory: str | None,
    offset: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize one documented app-ranking page without treating censoring as zero."""
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        return [], {"coverage_complete": False, "reason": "missing_data_list"}
    meta = body.get("meta")
    if not isinstance(meta, dict):
        return [], {"coverage_complete": False, "reason": "missing_meta"}
    api_start = _date(meta.get("start_date"))
    api_end = _date(meta.get("end_date"))
    as_of, version = meta.get("as_of"), meta.get("version")
    if api_start != requested_date or api_end != requested_date:
        return [], {"coverage_complete": False, "reason": "resolved_date_mismatch"}
    if not isinstance(as_of, str) or not as_of:
        return [], {"coverage_complete": False, "reason": "missing_meta_as_of"}
    if not isinstance(version, str) or not version:
        return [], {"coverage_complete": False, "reason": "missing_meta_version"}
    if offset not in APP_PAGE_OFFSETS:
        return [], {"coverage_complete": False, "reason": "unsupported_offset"}

    rows: list[dict[str, Any]] = []
    seen_apps: set[str] = set()
    seen_ranks: set[int] = set()
    for item in body["data"]:
        if not isinstance(item, dict):
            return [], {"coverage_complete": False, "reason": "non_object_data_row"}
        app_id_raw = item.get("app_id")
        app_id = str(app_id_raw) if isinstance(app_id_raw, (int, str)) else ""
        app_name = item.get("app_name")
        rank = _tokens(item.get("rank"))
        total_requests = _tokens(item.get("total_requests"))
        total_tokens = _tokens(item.get("total_tokens"))
        if (
            not app_id
            or not isinstance(app_name, str)
            or not app_name
            or rank is None
            or rank < 1
            or total_requests is None
            or total_tokens is None
        ):
            return [], {"coverage_complete": False, "reason": "invalid_data_row"}
        if app_id in seen_apps or rank in seen_ranks:
            return [], {"coverage_complete": False, "reason": "duplicate_app_or_rank"}
        if rank <= offset or rank > offset + APP_PAGE_LIMIT:
            return [], {"coverage_complete": False, "reason": "rank_outside_page"}
        seen_apps.add(app_id)
        seen_ranks.add(rank)
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": APP_SOURCE,
                "source_date": requested_date,
                "app_id": app_id,
                "app_name": app_name,
                "rank": rank,
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "ranking_sort": sort,
                "category": category,
                "subcategory": subcategory,
                "page_offset": offset,
                "page_limit": APP_PAGE_LIMIT,
                "api_as_of": as_of,
                "api_start_date": api_start,
                "api_end_date": api_end,
                "api_version": version,
                "is_public_attributed_only": True,
                "is_top_n_censored": True,
                "metric_definition": (
                    "OpenRouter documented public-app ranking for one UTC day; hidden and "
                    "private apps are excluded, aliases are merged, and only the requested "
                    "top-N rank window is observed. This is not an app-by-model or provider "
                    "routing ledger."
                ),
                "record_json": json.dumps(item, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows, {
        "coverage_complete": True,
        "source_date": requested_date,
        "page_offset": offset,
        "page_rows": len(rows),
        "api_as_of": as_of,
        "api_version": version,
    }


async def capture_openrouter_app_rankings_daily(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    sort: str = "popular",
    category: str | None = None,
    subcategory: str | None = None,
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    """Capture per-day public-app rankings with an explicit top-200 censoring bound."""
    if sort not in {"popular", "trending"}:
        raise ValueError("sort must be popular or trending")
    source_dates = _resolved_daily_range(start_date, end_date)
    run_ts, dt = run_timestamp(), dt_partition()
    token = _api_token()
    if not token:
        detail = {
            "reason": (
                "ORCAP_OPENROUTER_DATASET_API_KEY or OPENROUTER_API_KEY not configured"
            ),
            "url": APP_RANKINGS_URL,
        }
        write_source_run(
            APP_SOURCE,
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail=detail,
            curated_dir=curated_dir,
        )
        return {"run_ts": run_ts, "dt": dt, "rows": 0, "source_status": "skipped", **detail}

    rows: list[dict[str, Any]] = []
    page_details: list[dict[str, Any]] = []
    failed_detail: dict[str, Any] | None = None
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        for source_date in source_dates:
            for offset in APP_PAGE_OFFSETS:
                if offset and page_details[-1]["page_rows"] < APP_PAGE_LIMIT:
                    break
                body = await fetcher.get_json(
                    _app_url(
                        source_date,
                        sort=sort,
                        category=category,
                        subcategory=subcategory,
                        offset=offset,
                    ),
                    headers={"Authorization": f"Bearer {token}"},
                )
                page_rows, page_detail = app_rankings_page_rows(
                    body,
                    run_ts,
                    dt,
                    requested_date=source_date,
                    sort=sort,
                    category=category,
                    subcategory=subcategory,
                    offset=offset,
                )
                page_details.append(page_detail)
                if page_detail.get("coverage_complete") is not True:
                    failed_detail = page_detail
                    break
                rows.extend(page_rows)
            if failed_detail:
                break
        write_raw(fetcher.records, "openrouter_datasets", raw_dir, run_ts, dt)

    unique_keys = {
        (
            row["source_date"],
            row["app_id"],
            row["ranking_sort"],
            row["category"],
            row["subcategory"],
        )
        for row in rows
    }
    duplicate_rows = len(unique_keys) != len(rows)
    complete_dates = len({detail["source_date"] for detail in page_details})
    complete = failed_detail is None and not duplicate_rows and complete_dates == len(source_dates)
    if rows and complete:
        write_partition(pa.Table.from_pylist(rows), APP_SOURCE, run_ts, dt, curated_dir)
    detail = {
        "url": APP_RANKINGS_URL,
        "requested_start_date": source_dates[0],
        "requested_end_date": source_dates[-1],
        "requested_source_days": len(source_dates),
        "complete_source_days": complete_dates if complete else 0,
        "page_requests": len(page_details),
        "ranking_sort": sort,
        "category": category,
        "subcategory": subcategory,
        "rank_cap": max(APP_PAGE_OFFSETS) + APP_PAGE_LIMIT,
        "rank_window_censored": True,
        "duplicate_rows": duplicate_rows,
        "failed_detail": failed_detail,
        "metric_boundary": (
            "public attributed app rankings, top-200 maximum per requested daily scope; "
            "not complete app traffic, app-by-model allocation, provider routing, or users"
        ),
    }
    write_source_run(
        APP_SOURCE,
        status="success" if complete and rows else "degraded",
        rows=len(rows),
        run_ts=run_ts,
        dt=dt,
        detail=detail,
        curated_dir=curated_dir,
    )
    return {
        "run_ts": run_ts,
        "dt": dt,
        "rows": len(rows),
        "source_status": "success" if complete and rows else "degraded",
        **detail,
    }


async def capture_openrouter_rankings_daily(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    """Capture aggregate usage only when an explicitly configured API key exists."""
    if start_date is not None and _date(start_date) is None:
        raise ValueError("start_date must be YYYY-MM-DD")
    if end_date is not None and _date(end_date) is None:
        raise ValueError("end_date must be YYYY-MM-DD")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    run_ts, dt = run_timestamp(), dt_partition()
    token = _api_token()
    if not token:
        detail = {
            "reason": (
                "ORCAP_OPENROUTER_DATASET_API_KEY or OPENROUTER_API_KEY not configured"
            ),
            "url": RANKINGS_DAILY_URL,
        }
        write_source_run(
            SOURCE,
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail=detail,
            curated_dir=curated_dir,
        )
        return {"run_ts": run_ts, "dt": dt, "rows": 0, "source_status": "skipped", **detail}

    url = _url(start_date, end_date)
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        body = await fetcher.get_json(url, headers={"Authorization": f"Bearer {token}"})
        write_raw(fetcher.records, "openrouter_datasets", raw_dir, run_ts, dt)
    rows, detail = rankings_daily_rows(
        body,
        run_ts,
        dt,
        requested_start_date=start_date,
        requested_end_date=end_date,
    )
    if rows:
        write_partition(pa.Table.from_pylist(rows), SOURCE, run_ts, dt, curated_dir)
    complete = detail.get("coverage_complete") is True and bool(rows)
    write_source_run(
        SOURCE,
        status="success" if complete else "degraded",
        rows=len(rows),
        run_ts=run_ts,
        dt=dt,
        detail={
            "url": RANKINGS_DAILY_URL,
            "metric_boundary": (
                "authenticated OpenRouter aggregate top-50 model token totals and other row; "
                "not provider allocation, individual requests, prompts, completions, or users"
            ),
            **detail,
        },
        curated_dir=curated_dir,
    )
    return {
        "run_ts": run_ts,
        "dt": dt,
        "rows": len(rows),
        "source_status": "success" if complete else "degraded",
        **detail,
    }


def main(*, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(
        capture_openrouter_rankings_daily(start_date=start_date, end_date=end_date)
    )
    print(json.dumps(result, indent=2, default=str))
    return result


def app_main(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    sort: str = "popular",
    category: str | None = None,
    subcategory: str | None = None,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(
        capture_openrouter_app_rankings_daily(
            start_date=start_date,
            end_date=end_date,
            sort=sort,
            category=category,
            subcategory=subcategory,
        )
    )
    print(json.dumps(result, indent=2, default=str))
    return result
