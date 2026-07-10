"""Hourly GPU rental-price capture.

Sources:
  - vast.ai public bundles API (no auth): per-offer $/hr for a set of GPU
    classes -> gpu_offers_snapshots. This is the marketplace (spot-like) side.
  - fabryka.ai H100-equivalent index (/api/prices): their `history` array is
    short but grows; we snapshot it so the accumulated union preserves it ->
    gpu_price_indices.
  - Ornn AI public GPU compute-index history for H100 SXM, H200, B200,
    A100 SXM4, and RTX 5090 -> ornn_gpu_index_history.
  - Lambda's public instance page: literal per-GPU-hour list prices by GPU
    family and 1x/2x/4x/8x instance size -> gpu_published_prices. These are
    commercial posted quotes, not offer-book depth, utilization, or fills.

Historical backfill (one-time, separate): Wayback snapshots of provider
pricing pages + published monthly medians — see analysis/h7 notes.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa
from lxml import etree, html

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

VAST_URL = "https://console.vast.ai/api/v0/bundles/"
FABRYKA_URL = "https://gpu-price-index.vercel.app/api/prices"
ORNN_URL = "https://api.ornnai.com/api/gpu/{gpu_name}/index-history"
LAMBDA_GPU_PRICING_URL = "https://lambda.ai/instances"

GPU_CLASSES = [
    "H100 SXM",
    "H100 NVL",
    "H200",
    "B200",
    "A100 SXM4",
    "A100 PCIE",
    "RTX 4090",
    "RTX 5090",
    "RTX 3090",
]

# Matches the currently documented public Ornn API universe. Keep this
# separate from GPU_CLASSES: Vast offer availability and index coverage
# need not coincide.
ORNN_GPU_CLASSES = ["H100 SXM", "H200", "B200", "A100 SXM4", "RTX 5090"]

OFFER_FIELDS = [
    "id",
    "machine_id",
    "host_id",
    "gpu_name",
    "num_gpus",
    "dph_base",
    "dph_total",
    "min_bid",
    "rentable",
    "rented",
    "verification",
    "geolocation",
    "reliability2",
    "dlperf",
    "dlperf_per_dphtotal",
    "flops_per_dphtotal",
    "gpu_ram",
    "cuda_max_good",
    "inet_down",
    "inet_up",
    "duration",
]

_LAMBDA_HEADERS = ["plan", "vram/gpu", "vcpus", "ram", "storage", "price/gpu/hr*"]
_LAMBDA_DOLLAR = re.compile(r"^\$(\d+(?:\.\d+)?)$")
_LAMBDA_VRAM_GB = re.compile(r"^(\d+(?:\.\d+)?)\s*gb$", re.IGNORECASE)
_LAMBDA_INSTANCE_SIZE = re.compile(r"^(\d+)x$")


def _vast_query(gpu_name: str, offer_type: str) -> str:
    q = {
        "gpu_name": {"eq": gpu_name},
        "rentable": {"eq": True},
        "type": offer_type,
        "limit": 1000,
        "order": [["dph_total", "asc"]],
    }
    return f"{VAST_URL}?q={quote(json.dumps(q))}"


def _offer_rows(
    body: Any, gpu_class: str, offer_type: str, run_ts: str, dt: str
) -> list[dict[str, Any]]:
    rows = []
    for o in (body or {}).get("offers", []) or []:
        row = {f: o.get(f) for f in OFFER_FIELDS}
        row.update(
            {
                "run_ts": run_ts,
                "dt": dt,
                "gpu_class": gpu_class,
                "offer_type": offer_type,
                "source": "vast.ai",
            }
        )
        rows.append(row)
    return rows


def _index_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    entries = list((body or {}).get("history") or [])
    current = (body or {}).get("current")
    if current:
        entries.append(current)
    for e in entries:
        fam = e.get("family") or {}
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "fabryka",
                "index_date": e.get("date"),
                "basis": fam.get("basis"),
                "offer_count": fam.get("offerCount"),
                "usd_min": fam.get("min"),
                "usd_p25": fam.get("p25"),
                "usd_median": fam.get("median"),
                "usd_p75": fam.get("p75"),
                "usd_max": fam.get("max"),
                "record_json": json.dumps(e, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def _ornn_index_rows(
    body: Any, requested_gpu_class: str, run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize Ornn's complete public history without inventing units.

    Index_value is Ornn's own reported compute-index value. Consumers should
    use the source/unit fields to distinguish it from a raw Vast offer.
    Repeated hourly captures intentionally preserve the full history; H7
    deduplicates historical observations by gpu_class and observed_at, retaining
    the latest capture.
    """
    if not isinstance(body, dict) or not body.get("success"):
        return []
    gpu_class = str(body.get("gpu_type") or requested_gpu_class)
    rows = []
    for entry in body.get("data") or []:
        if not isinstance(entry, dict):
            continue
        index_value = _float(entry.get("index_value"))
        observed_at = entry.get("timestamp")
        if index_value is None or not observed_at:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "ornn",
                "gpu_class": gpu_class,
                "observed_at": observed_at,
                "index_value": index_value,
                "source_unit": "ornn_compute_index",
                "record_json": json.dumps(entry, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def _lambda_gpu_price_rows(body: str | None, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Parse Lambda's literal, server-rendered per-GPU-hour instance tables.

    Every accepted row must belong to a labeled 1x/2x/4x/8x tab and preserve
    exact GPU plan, VRAM, and USD-per-GPU-hour values. A table header or price
    format change intentionally yields no rows rather than a best-effort quote.
    """
    if not body:
        return []
    try:
        tree = html.fromstring(body)
    except (TypeError, ValueError, etree.ParserError):
        return []
    tab_labels = {
        button.get("aria-controls"): " ".join(button.text_content().split())
        for button in tree.xpath("//button[@role='tab'][@aria-controls]")
    }
    rows = []
    seen: set[tuple[str, str]] = set()
    for panel in tree.xpath("//*[@role='tabpanel'][@id]"):
        tab = tab_labels.get(panel.get("id"))
        instance_match = _LAMBDA_INSTANCE_SIZE.fullmatch(tab or "")
        if not instance_match:
            continue
        for table in panel.xpath(".//table"):
            headers = [
                " ".join(cell.text_content().split()).lower()
                for cell in table.xpath(".//thead//th")
            ]
            if headers != _LAMBDA_HEADERS:
                continue
            for tr in table.xpath(".//tbody/tr"):
                cells = [" ".join(cell.text_content().split()) for cell in tr.xpath("./th|./td")]
                if len(cells) != len(_LAMBDA_HEADERS):
                    continue
                plan, vram, vcpus, ram, storage, price = cells
                price_match = _LAMBDA_DOLLAR.fullmatch(price)
                vram_match = _LAMBDA_VRAM_GB.fullmatch(vram)
                key = (tab, plan)
                if not plan or key in seen or not price_match or not vram_match:
                    continue
                seen.add(key)
                record = {
                    "instance_size": tab,
                    "plan": plan,
                    "vram_per_gpu": vram,
                    "vcpus": vcpus,
                    "ram": ram,
                    "storage": storage,
                    "price_per_gpu_hour": price,
                }
                rows.append(
                    {
                        "run_ts": run_ts,
                        "dt": dt,
                        "source": "lambda",
                        "gpu_class": plan,
                        "instance_gpu_count": int(instance_match.group(1)),
                        "gpu_vram_gb": float(vram_match.group(1)),
                        "usd_per_gpu_hour": float(price_match.group(1)),
                        "quote_unit": "usd_per_gpu_hour",
                        "quote_type": "published_on_demand_instance_list_price",
                        "source_url": LAMBDA_GPU_PRICING_URL,
                        "source_schema_version": "lambda_instances_pricing_tabs_v1",
                        "record_json": json.dumps(record, separators=(",", ":"), sort_keys=True),
                    }
                )
    return rows


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def capture_gpu(raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()

    async with make_client() as client:
        fetcher = Fetcher(client, rps=2.0)
        ornn_fetcher = Fetcher(client, rps=1.0)

        combos = [(g, t) for g in GPU_CLASSES for t in ("on-demand", "bid")]
        vast_bodies = await asyncio.gather(
            *(fetcher.get_json(_vast_query(g, t)) for g, t in combos)
        )
        fabryka, lambda_pricing = await asyncio.gather(
            fetcher.get_json(FABRYKA_URL),
            fetcher.get_text(LAMBDA_GPU_PRICING_URL),
        )
        ornn_bodies = await asyncio.gather(
            *(
                ornn_fetcher.get_json(
                    ORNN_URL.format(gpu_name=quote(gpu_class, safe=""))
                )
                for gpu_class in ORNN_GPU_CLASSES
            )
        )
        write_raw(fetcher.records, "gpu", raw_dir, run_ts, dt)
        write_raw(ornn_fetcher.records, "ornn", raw_dir, run_ts, dt)

    offer_rows: list[dict[str, Any]] = []
    for (gpu_class, offer_type), body in zip(combos, vast_bodies, strict=True):
        offer_rows += _offer_rows(body, gpu_class, offer_type, run_ts, dt)
    index_rows = _index_rows(fabryka, run_ts, dt)
    lambda_rows = _lambda_gpu_price_rows(lambda_pricing, run_ts, dt)
    ornn_rows: list[dict[str, Any]] = []
    for gpu_class, body in zip(ORNN_GPU_CLASSES, ornn_bodies, strict=True):
        ornn_rows += _ornn_index_rows(body, gpu_class, run_ts, dt)

    summary: dict[str, Any] = {"run_ts": run_ts, "dt": dt}
    if offer_rows:
        tbl = pa.Table.from_pylist(offer_rows)
        write_partition(tbl, "gpu_offers_snapshots", run_ts, dt, curated_dir)
    summary["gpu_offers"] = len(offer_rows)
    if index_rows:
        tbl = pa.Table.from_pylist(index_rows)
        write_partition(tbl, "gpu_price_indices", run_ts, dt, curated_dir)
    summary["gpu_index_rows"] = len(index_rows)
    if lambda_rows:
        tbl = pa.Table.from_pylist(lambda_rows)
        write_partition(tbl, "gpu_published_prices", run_ts, dt, curated_dir)
    summary["lambda_gpu_price_rows"] = len(lambda_rows)
    if ornn_rows:
        tbl = pa.Table.from_pylist(ornn_rows)
        write_partition(tbl, "ornn_gpu_index_history", run_ts, dt, curated_dir)
    summary["ornn_index_rows"] = len(ornn_rows)
    write_source_run(
        "lambda_gpu_pricing",
        status="success" if lambda_rows else "degraded",
        rows=len(lambda_rows),
        detail={
            "url": LAMBDA_GPU_PRICING_URL,
            "source_type": "published_on_demand_instance_list_price",
            "schema_version": "lambda_instances_pricing_tabs_v1",
        },
        run_ts=run_ts,
        dt=dt,
        curated_dir=curated_dir,
    )
    write_source_run(
        "ornn",
        status="success" if ornn_rows else "degraded",
        rows=len(ornn_rows),
        detail={
            "requested_gpu_classes": ORNN_GPU_CLASSES,
            "successful_gpu_classes": sum(
                bool(isinstance(body, dict) and body.get("success")) for body in ornn_bodies
            ),
        },
        run_ts=run_ts,
        dt=dt,
        curated_dir=curated_dir,
    )
    log.info("gpu capture complete: %s", summary)
    return summary


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    summary = asyncio.run(capture_gpu())
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
