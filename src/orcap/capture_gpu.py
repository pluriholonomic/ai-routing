"""Hourly GPU rental-price capture.

Sources:
  - vast.ai public bundles API (no auth): per-offer $/hr for a set of GPU
    classes -> gpu_offers_snapshots. This is the marketplace (spot-like) side.
  - fabryka.ai H100-equivalent index (/api/prices): their `history` array is
    short but grows; we snapshot it so the accumulated union preserves it ->
    gpu_price_indices.
  - Ornn AI public GPU compute-index history for H100 SXM, H200, B200,
    A100 SXM4, and RTX 5090 -> ornn_gpu_index_history.

Historical backfill (one-time, separate): Wayback snapshots of provider
pricing pages + published monthly medians — see analysis/h7 notes.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

VAST_URL = "https://console.vast.ai/api/v0/bundles/"
FABRYKA_URL = "https://gpu-price-index.vercel.app/api/prices"
ORNN_URL = "https://api.ornnai.com/api/gpu/{gpu_name}/index-history"

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
        fabryka = await fetcher.get_json(FABRYKA_URL)
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
    if ornn_rows:
        tbl = pa.Table.from_pylist(ornn_rows)
        write_partition(tbl, "ornn_gpu_index_history", run_ts, dt, curated_dir)
    summary["ornn_index_rows"] = len(ornn_rows)
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
