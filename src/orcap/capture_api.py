"""High-frequency snapshot job: models + providers + per-provider endpoints,
plus live congestion stats for the hottest models.

Fan-out: 1x /models, 1x /providers, one /models/{slug}/endpoints call per
unique canonical_slug, and — for the top ORCAP_HOTLIST models by weekly
volume — the frontend stats/endpoint call, whose `stats` block carries live
30-minute latency/throughput percentiles and `fortuna` utilization
(recent_peak_rpm vs capacity_ceiling_rpm). That block is the demand-side
panel: it lets us measure how aggressively providers move quotes (and their
shadow price, latency) in response to load.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq

from . import normalize
from .config import API_V1, BASE_URL, CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)

HOTLIST_SIZE = int(os.environ.get("ORCAP_HOTLIST", "40"))
RANKINGS_URL = f"{BASE_URL}/api/frontend/v1/rankings/models?view=week"
STATS_URL = f"{BASE_URL}/api/frontend/v1/stats/endpoint"


def _endpoint_urls(models: list[dict[str, Any]]) -> list[str]:
    """One endpoints URL per unique model, preferring the API-provided details link."""
    seen: set[str] = set()
    urls: list[str] = []
    for m in models:
        slug = m.get("canonical_slug") or m.get("id")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        details = (m.get("links") or {}).get("details")
        url = f"https://openrouter.ai{details}" if details else f"{API_V1}/models/{slug}/endpoints"
        urls.append(url)
    return urls


def _hot_permaslugs(rankings: Any, n: int = HOTLIST_SIZE) -> list[str]:
    rows = (rankings or {}).get("data") or []
    totals: dict[str, int] = {}
    for r in rows:
        slug = r.get("model_permaslug")
        if slug:
            tokens = (r.get("total_prompt_tokens") or 0) + (r.get("total_completion_tokens") or 0)
            totals[slug] = totals.get(slug, 0) + tokens
    return [s for s, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:n]]


def _congestion_rows(body: Any, permaslug: str, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    for ep in (body or {}).get("data") or []:
        st = ep.get("stats") or {}
        f = ep.get("fortuna") or {}
        sh30 = ep.get("status_heuristics") or {}
        sh5 = ep.get("status_heuristics_5m") or {}
        pricing = ep.get("pricing") or {}
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "model_permaslug": permaslug,
                "endpoint_uuid": ep.get("id"),
                "provider_name": ep.get("provider_display_name") or ep.get("provider_name"),
                "price_completion": _sf(pricing.get("completion")),
                "p50_latency_ms": st.get("p50_latency"),
                "p90_latency_ms": st.get("p90_latency"),
                "p99_latency_ms": st.get("p99_latency"),
                "p50_throughput": st.get("p50_throughput"),
                "p90_throughput": st.get("p90_throughput"),
                "request_count_30m": st.get("request_count"),
                "recent_peak_rpm": f.get("recent_peak_rpm"),
                "capacity_ceiling_rpm": f.get("capacity_ceiling_rpm"),
                "success_30m": sh30.get("success"),
                "rate_limited_30m": sh30.get("rateLimited"),
                "derankable_error_30m": sh30.get("derankableError"),
                "success_5m": sh5.get("success"),
                "rate_limited_5m": sh5.get("rateLimited"),
                "is_deranked": bool(ep.get("is_deranked")),
            }
        )
    return rows


def _sf(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def write_partition(
    table, name: str, run_ts: str, dt: str, curated_dir: Path = CURATED_DIR
) -> Path:
    out_dir = curated_dir / name / f"dt={dt}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run_ts}.parquet"
    pq.write_table(table, out, compression="zstd")
    return out


def write_event_burst_manifest(
    models: set[str],
    run_ts: str,
    dt: str,
    planned_post_seconds: int,
    curated_dir: Path = CURATED_DIR,
) -> Path | None:
    """Persist the intended event-study window when a price change is detected.

    The normal panel provides the pre-event five-minute quote observations;
    minute-level burst sampling begins only after detection.  Recording that
    asymmetry prevents downstream analysis from presenting post-only bursts as
    symmetric high-frequency evidence.
    """
    if not models:
        return None
    rows = [
        {
            "event_id": f"{run_ts}|{model}",
            "detected_at_run_ts": run_ts,
            "dt": dt,
            "model_id": model,
            "trigger": "price_change",
            "pre_event_resolution_seconds": 300,
            "post_event_resolution_seconds": 60,
            "planned_post_seconds": planned_post_seconds,
            "post_burst_attempted": planned_post_seconds > 0,
        }
        for model in sorted(models)
    ]
    return write_partition(
        pa.Table.from_pylist(rows), "event_burst_manifest", run_ts, dt, curated_dir
    )


async def capture(raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()
    async with make_client() as client:
        fetcher = Fetcher(client)

        models_doc, providers_doc = await asyncio.gather(
            fetcher.get_json(f"{API_V1}/models"),
            fetcher.get_json(f"{API_V1}/providers"),
        )
        if not models_doc or "data" not in models_doc:
            raise RuntimeError("failed to fetch /api/v1/models — aborting run")
        models = models_doc["data"]
        providers = (providers_doc or {}).get("data", [])

        urls = _endpoint_urls(models)
        log.info("fetching endpoints for %d models", len(urls))
        endpoint_docs_raw = await asyncio.gather(*(fetcher.get_json(u) for u in urls))
        endpoint_docs = [d["data"] for d in endpoint_docs_raw if d and "data" in d]
        failures = len(urls) - len(endpoint_docs)

        # live congestion stats for the hottest models (demand-side panel)
        congestion_rows: list[dict[str, Any]] = []
        rankings = await fetcher.get_json(RANKINGS_URL)
        hot = _hot_permaslugs(rankings)
        if hot:
            stat_urls = [f"{STATS_URL}?permaslug={quote(s, safe='')}&variant=standard" for s in hot]
            stat_bodies = await asyncio.gather(*(fetcher.get_json(u) for u in stat_urls))
            for slug, body in zip(hot, stat_bodies, strict=True):
                congestion_rows += _congestion_rows(body, slug, run_ts, dt)

        write_raw(fetcher.records, "api_v1", raw_dir, run_ts, dt)

    models_tbl = normalize.models_table(models, run_ts, dt)
    endpoints_tbl = normalize.endpoints_table(endpoint_docs, run_ts, dt)
    providers_tbl = normalize.providers_table(providers, run_ts, dt)

    paths = {
        "models_snapshots": write_partition(
            models_tbl, "models_snapshots", run_ts, dt, curated_dir
        ),
        "endpoints_snapshots": write_partition(
            endpoints_tbl, "endpoints_snapshots", run_ts, dt, curated_dir
        ),
        "providers_snapshots": write_partition(
            providers_tbl, "providers_snapshots", run_ts, dt, curated_dir
        ),
    }
    if congestion_rows:
        write_partition(
            pa.Table.from_pylist(congestion_rows),
            "congestion_intraday",
            run_ts,
            dt,
            curated_dir,
        )
    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "models": models_tbl.num_rows,
        "endpoints": endpoints_tbl.num_rows,
        "providers": providers_tbl.num_rows,
        "endpoint_fetch_failures": failures,
        "congestion_rows": len(congestion_rows),
        "paths": {k: str(v) for k, v in paths.items()},
    }
    log.info("capture complete: %s", summary)
    return summary


def price_map(summary_paths: dict[str, Any]) -> dict[tuple, float]:
    """(model, provider, tag, fingerprint) -> completion price from a snapshot file."""
    tbl = pq.ParquetFile(summary_paths["endpoints_snapshots"]).read(
        columns=[
            "model_id",
            "provider_name",
            "tag",
            "endpoint_fingerprint",
            "price_completion",
        ]
    )
    out = {}
    for r in tbl.to_pylist():
        if r["price_completion"] is not None:
            out[(r["model_id"], r["provider_name"], r["tag"], r["endpoint_fingerprint"])] = r[
                "price_completion"
            ]
    return out


def diff_models(prev: dict[tuple, float], cur: dict[tuple, float]) -> set[str]:
    """Models whose any endpoint changed price between consecutive samples."""
    changed = set()
    for k, v in cur.items():
        if ":" in k[0]:  # variant ids share the base model's endpoints
            continue
        if k in prev and prev[k] != v:
            changed.add(k[0])
    return changed


async def burst_sample(
    models: set[str],
    canonical_slugs: dict[str, str] | None = None,
    curated_dir: Path = CURATED_DIR,
    raw_dir: Path = RAW_DIR,
) -> int:
    """One focused 60s-cadence tick: endpoints + live stats for changed models.

    Captures the minutes right after a repricing event — competitor reactions
    and congestion response at 1-min resolution (H8 event studies).
    """
    run_ts = run_timestamp()
    dt = dt_partition()
    canonical_slugs = canonical_slugs or {}
    model_ids = sorted(models)
    async with make_client() as client:
        fetcher = Fetcher(client, rps=8)
        ep_urls = [f"{API_V1}/models/{m}/endpoints" for m in model_ids]
        # The public endpoint route accepts the stable model id, while the
        # frontend stats route requires the versioned canonical permaslug.
        stat_urls = [
            f"{STATS_URL}?permaslug={quote(canonical_slugs.get(m, m), safe='')}&variant=standard"
            for m in model_ids
        ]
        bodies = await asyncio.gather(*(fetcher.get_json(u) for u in ep_urls + stat_urls))
        write_raw(fetcher.records, "event_bursts", raw_dir, run_ts, dt)
    ep_docs = [b["data"] for b in bodies[: len(ep_urls)] if b and "data" in b]
    rows = normalize.endpoints_table(ep_docs, run_ts, dt)
    cong_rows: list[dict[str, Any]] = []
    for m, b in zip(model_ids, bodies[len(ep_urls) :], strict=True):
        cong_rows += _congestion_rows(b, canonical_slugs.get(m, m), run_ts, dt)
    if rows.num_rows:
        write_partition(rows, "event_bursts", run_ts, dt, curated_dir)
    if cong_rows:
        write_partition(
            pa.Table.from_pylist(cong_rows), "event_bursts_congestion", run_ts, dt, curated_dir
        )
    return rows.num_rows


def canonical_slug_map(snapshot_path: str | Path, model_ids: set[str]) -> dict[str, str]:
    """Map endpoint model ids to the frontend stats route's canonical slugs."""
    if not model_ids:
        return {}
    table = pq.ParquetFile(snapshot_path).read(columns=["id", "canonical_slug"])
    return {
        row["id"]: row["canonical_slug"]
        for row in table.to_pylist()
        if row.get("id") in model_ids and row.get("canonical_slug")
    }


async def capture_loop(samples: int, interval_seconds: float) -> list[dict[str, Any]]:
    """Take N snapshots spaced interval_seconds apart within one job.

    EVENT-DRIVEN LAYER: consecutive samples are diffed in-flight; when an
    endpoint's price changes, the inter-sample sleep is replaced by 60-second
    burst sampling of the affected models (endpoints + congestion), and a
    marker file is written so CI can trigger the reanalysis workflow.
    """
    import time

    summaries: list[dict[str, Any]] = []
    prev: dict[tuple, float] = {}
    hot: set[str] = set()
    hot_canonical_slugs: dict[str, str] = {}
    for i in range(samples):
        start = time.monotonic()
        summary = await capture()
        summaries.append(summary)
        cur = price_map(summary["paths"])
        changed = diff_models(prev, cur) if prev else set()
        if changed:
            hot |= changed
            hot_canonical_slugs.update(
                canonical_slug_map(summary["paths"]["models_snapshots"], changed)
            )
            log.warning("PRICE EVENT detected: %s", sorted(changed))
            Path("events_detected").write_text("\n".join(sorted(hot)))
            write_event_burst_manifest(
                changed,
                summary["run_ts"],
                summary["dt"],
                max(0, int(interval_seconds - 65)) if i < samples - 1 else 0,
            )
        prev = cur
        if i < samples - 1:
            deadline = start + interval_seconds
            if hot:
                while time.monotonic() < deadline - 65:
                    tick = time.monotonic()
                    try:
                        await burst_sample(hot, canonical_slugs=hot_canonical_slugs)
                    except Exception:
                        log.exception("burst tick failed")
                    await asyncio.sleep(max(0.0, 60 - (time.monotonic() - tick)))
            await asyncio.sleep(max(0.0, deadline - time.monotonic()))
    return summaries


def consolidate_local(curated_dir: Path = CURATED_DIR) -> int:
    """Merge this job's per-sample parquet files into one file per table/day
    before pushing — an 11-sample job otherwise ships ~100 small files, which
    multiplies both HF upload and later hydration request counts (rate limits).
    """
    merged = 0
    for dt_dir in curated_dir.glob("*/dt=*"):
        files = sorted(dt_dir.glob("*.parquet"))
        if len(files) < 2:
            continue
        tables = [pq.ParquetFile(f).read() for f in files]
        out = dt_dir / files[-1].name
        combined = pa.concat_tables(tables, promote_options="default")
        for f in files:
            f.unlink()
        pq.write_table(combined, out, compression="zstd")
        merged += len(files)
    log.info("consolidated %d per-sample files", merged)
    return merged


def main(samples: int = 1, interval_seconds: float = 300.0) -> list[dict[str, Any]]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    out = asyncio.run(capture_loop(samples, interval_seconds))
    consolidate_local()
    return out


if __name__ == "__main__":
    main()
