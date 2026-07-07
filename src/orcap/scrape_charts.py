"""Daily capture of OpenRouter's frontend (undocumented) v1 API.

Discovered via orcap.discover (Playwright network sniff) on 2026-07-06 — these
are the JSON endpoints behind the model-page charts and rankings/apps pages.
They need no auth or cookies, just plain GETs. If they move again, re-run
`orcap discover` and update FRONTEND paths here.

Global (once per run):
  /api/frontend/v1/rankings/model-rankings-chart   weekly tokens per model since 2025-07
  /api/frontend/v1/rankings/models?view=week       current model rankings
  /api/frontend/v1/apps/marketplace/marketplace    global app/harness leaderboard
  /api/frontend/all-providers                      rich provider directory
  /api/frontend/v1/catalog/models                  full catalog (raw layer only, ~4MB)

Per model×variant (~400 combos):
  stats/model-activity        trailing 31 days of daily token/request usage
  stats/top-apps-for-model    per-model app leaderboard (e.g. Hermes Agent)
  stats/endpoint              per-provider endpoint detail incl. UUID map + heuristics
  stats/uptime-recent         3 days of daily uptime per endpoint UUID
  stats/effective-pricing     transacted effective prices per provider
  stats/{throughput,latency,latency-e2e}-comparison?timeRange=1w
  stats/{tool-call,structured-output}-error-rate, cache-hit-rate-comparison
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa

from .capture_api import write_partition
from .config import API_V1, BASE_URL, CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)

FRONTEND = f"{BASE_URL}/api/frontend"

GLOBAL_ENDPOINTS = {
    "rankings_chart": f"{FRONTEND}/v1/rankings/model-rankings-chart",
    "rankings_models": f"{FRONTEND}/v1/rankings/models?view=week",
    "apps_marketplace": f"{FRONTEND}/v1/apps/marketplace/marketplace",
    "all_providers": f"{FRONTEND}/all-providers",
    "catalog_models": f"{FRONTEND}/v1/catalog/models",
}

PER_MODEL_STATS = [
    "model-activity",
    "top-apps-for-model",
    "endpoint",
    "uptime-recent",
    "effective-pricing",
]
PER_MODEL_COMPARISONS = [
    "throughput-comparison",
    "latency-comparison",
    "latency-e2e-comparison",
    "tool-call-error-rate",
    "structured-output-error-rate",
    "cache-hit-rate-comparison",
]


def model_variants(models: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(permaslug, variant) pairs from the v1 models list.

    Model ids look like 'z-ai/glm-4.6' or 'tencent/hy3:free'; the frontend API
    keys everything by the dated canonical_slug (permaslug) plus a variant name
    ('standard' when no ':variant' suffix).
    """
    pairs: dict[tuple[str, str], None] = {}
    for m in models:
        permaslug = m.get("canonical_slug") or m.get("id", "")
        mid = m.get("id", "")
        variant = mid.split(":", 1)[1] if ":" in mid else "standard"
        if permaslug:
            pairs[(permaslug, variant)] = None
    return list(pairs)


def _stat_url(stat: str, permaslug: str, variant: str) -> str:
    q = f"permaslug={quote(permaslug, safe='')}"
    if stat in ("model-activity", "top-apps-for-model", "endpoint", "effective-pricing"):
        q += f"&variant={quote(variant)}"
    if stat in PER_MODEL_COMPARISONS:
        q += "&timeRange=1w"
    return f"{FRONTEND}/v1/stats/{stat}?{q}"


# ---------------------------------------------------------------- normalizers


def _rows_activity(body: Any, permaslug: str, variant: str) -> list[dict[str, Any]]:
    rows = []
    for r in (body or {}).get("data", {}).get("analytics", []) or []:
        rows.append(
            {
                "date": r.get("date"),
                "model_permaslug": r.get("model_permaslug") or permaslug,
                "variant": r.get("variant") or variant,
                "total_prompt_tokens": r.get("total_prompt_tokens"),
                "total_completion_tokens": r.get("total_completion_tokens"),
                "total_native_tokens_reasoning": r.get("total_native_tokens_reasoning"),
                "total_native_tokens_cached": r.get("total_native_tokens_cached"),
                "request_count": r.get("count"),
                "total_tool_calls": r.get("total_tool_calls"),
                "requests_with_tool_call_errors": r.get("requests_with_tool_call_errors"),
                "record_json": json.dumps(r, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def _rows_top_apps(body: Any, permaslug: str, variant: str) -> list[dict[str, Any]]:
    rows = []
    for r in (body or {}).get("data", {}).get("top_apps", []) or []:
        app = r.get("app") or {}
        rows.append(
            {
                "scope": "model",
                "model_permaslug": permaslug,
                "variant": variant,
                "section": None,
                "rank": r.get("rank"),
                "app_id": r.get("app_id"),
                "app_title": app.get("title"),
                "app_slug": app.get("slug"),
                "app_origin_url": app.get("origin_url"),
                "app_categories": app.get("categories") or [],
                "total_tokens": _int(r.get("total_tokens")),
                "total_requests": _int(r.get("total_requests")),
                "record_json": json.dumps(r, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def _rows_marketplace(body: Any) -> list[dict[str, Any]]:
    rows = []
    data = (body or {}).get("data", {}) or {}
    for section, entries in data.items():
        if not isinstance(entries, list):
            continue
        for r in entries:
            if not isinstance(r, dict) or "app" not in r:
                continue
            app = r.get("app") or {}
            rows.append(
                {
                    "scope": "global",
                    "model_permaslug": None,
                    "variant": None,
                    "section": section,
                    "rank": r.get("rank"),
                    "app_id": r.get("app_id"),
                    "app_title": app.get("title"),
                    "app_slug": app.get("slug"),
                    "app_origin_url": app.get("origin_url"),
                    "app_categories": app.get("categories") or [],
                    "total_tokens": _int(r.get("total_tokens")),
                    "total_requests": _int(r.get("total_requests")),
                    "record_json": json.dumps(r, separators=(",", ":"), sort_keys=True),
                }
            )
    return rows


def _rows_endpoint_stats(body: Any, permaslug: str, variant: str) -> list[dict[str, Any]]:
    rows = []
    for r in (body or {}).get("data", []) or []:
        provider_info = r.get("provider_info") or {}
        rows.append(
            {
                "endpoint_uuid": r.get("id"),
                "endpoint_name": r.get("name"),
                "model_permaslug": permaslug,
                "variant": variant,
                "provider_slug": provider_info.get("slug") or r.get("provider_slug"),
                "provider_display_name": provider_info.get("displayName")
                or r.get("provider_display_name"),
                "quantization": r.get("quantization"),
                "context_length": r.get("context_length"),
                "record_json": json.dumps(r, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def _rows_uptime(body: Any, permaslug: str, variant: str) -> list[dict[str, Any]]:
    rows = []
    for endpoint_uuid, series in ((body or {}).get("data", {}) or {}).items():
        if not isinstance(series, list):
            continue
        for pt in series:
            rows.append(
                {
                    "model_permaslug": permaslug,
                    "variant": variant,
                    "endpoint_uuid": endpoint_uuid,
                    "date": pt.get("date"),
                    "uptime": pt.get("uptime"),
                }
            )
    return rows


def _rows_effective_pricing(body: Any, permaslug: str, variant: str) -> list[dict[str, Any]]:
    data = (body or {}).get("data", {}) or {}
    rows = []
    for r in data.get("providerSummaries", []) or []:
        rows.append(
            {
                "model_permaslug": permaslug,
                "variant": variant,
                "provider_slug": r.get("providerSlug"),
                "provider_name": r.get("providerName"),
                "effective_input_price": r.get("effectiveInputPrice"),
                "effective_output_price": r.get("effectiveOutputPrice"),
                "cache_hit_rate": r.get("cacheHitRate"),
                "total_tokens": _int(r.get("totalTokens")),
                "weighted_input_price": data.get("weightedInputPrice"),
                "weighted_output_price": data.get("weightedOutputPrice"),
                "weighted_cache_hit_rate": data.get("weightedCacheHitRate"),
            }
        )
    return rows


def _rows_comparison(body: Any, permaslug: str, variant: str, metric: str) -> list[dict[str, Any]]:
    rows = []
    for pt in (body or {}).get("data", []) or []:
        x = pt.get("x")
        for series_key, value in (pt.get("y") or {}).items():
            endpoint_uuid = series_key.split("::", 1)[0]
            rows.append(
                {
                    "metric": metric,
                    "model_permaslug": permaslug,
                    "variant": variant,
                    "endpoint_uuid": endpoint_uuid,
                    "series_key": series_key,
                    "date": x,
                    "value": _float(value),
                }
            )
    return rows


def _rows_rankings_chart(body: Any) -> list[dict[str, Any]]:
    rows = []
    for pt in ((body or {}).get("data", {}) or {}).get("data", []) or []:
        week = pt.get("x")
        for model_id, tokens in (pt.get("ys") or {}).items():
            rows.append({"week": week, "model_id": model_id, "total_tokens": _int(tokens)})
    return rows


def _int(x: Any) -> int | None:
    try:
        return None if x is None else int(x)
    except (TypeError, ValueError):
        return None


def _float(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------- capture


async def scrape(
    limit: int | None = None,
    include_comparisons: bool = True,
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()

    async with make_client() as client:
        fetcher = Fetcher(client)

        models_doc = await fetcher.get_json(f"{API_V1}/models")
        if not models_doc or "data" not in models_doc:
            raise RuntimeError("failed to fetch /api/v1/models — aborting scrape")
        pairs = model_variants(models_doc["data"])
        if limit:
            pairs = pairs[:limit]

        globals_res = dict(
            zip(
                GLOBAL_ENDPOINTS,
                await asyncio.gather(*(fetcher.get_json(u) for u in GLOBAL_ENDPOINTS.values())),
                strict=True,
            )
        )

        stats = PER_MODEL_STATS + (PER_MODEL_COMPARISONS if include_comparisons else [])

        async def fetch_model(permaslug: str, variant: str) -> dict[str, Any]:
            urls = {s: _stat_url(s, permaslug, variant) for s in stats}
            bodies = await asyncio.gather(*(fetcher.get_json(u) for u in urls.values()))
            return dict(zip(urls, bodies, strict=True))

        log.info("scraping %d model×variant combos × %d stats", len(pairs), len(stats))
        per_model = await asyncio.gather(*(fetch_model(p, v) for p, v in pairs))

        write_raw(fetcher.records, "frontend_v1", raw_dir, run_ts, dt)

    activity, apps, endpoint_stats, uptime, pricing, comparisons = [], [], [], [], [], []
    for (permaslug, variant), res in zip(pairs, per_model, strict=True):
        activity += _rows_activity(res.get("model-activity"), permaslug, variant)
        apps += _rows_top_apps(res.get("top-apps-for-model"), permaslug, variant)
        endpoint_stats += _rows_endpoint_stats(res.get("endpoint"), permaslug, variant)
        uptime += _rows_uptime(res.get("uptime-recent"), permaslug, variant)
        pricing += _rows_effective_pricing(res.get("effective-pricing"), permaslug, variant)
        for metric in PER_MODEL_COMPARISONS:
            comparisons += _rows_comparison(res.get(metric), permaslug, variant, metric)
    apps += _rows_marketplace(globals_res.get("apps_marketplace"))
    rankings = _rows_rankings_chart(globals_res.get("rankings_chart"))

    tables = {
        "model_activity_daily": activity,
        "apps_leaderboards": apps,
        "endpoint_stats_daily": endpoint_stats,
        "uptime_daily": uptime,
        "effective_pricing_daily": pricing,
        "perf_comparisons_daily": comparisons,
        "rankings_weekly": rankings,
    }
    summary: dict[str, Any] = {"run_ts": run_ts, "dt": dt, "combos": len(pairs)}
    for name, rows in tables.items():
        if not rows:
            summary[name] = 0
            continue
        tbl = pa.Table.from_pylist([{"run_ts": run_ts, "dt": dt, **r} for r in rows])
        write_partition(tbl, name, run_ts, dt, curated_dir)
        summary[name] = len(rows)
    log.info("scrape complete: %s", summary)
    return summary


def main(limit: int | None = None, headed: bool = False, **_: Any) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    summary = asyncio.run(scrape(limit=limit))
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
