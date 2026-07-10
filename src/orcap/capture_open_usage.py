"""Public open-model adoption and consumption-proxy capture.

This collector deliberately separates three non-interchangeable measures:

* Hugging Face rolling model downloads: public weight-distribution activity,
  not inference tokens or unique users.
* Ollama Library cumulative pulls: local-model acquisition, not completions.
* Docker Hub runtime-image pulls: serving-runtime adoption; Docker counts some
  version checks as pulls, so this is a deployment proxy only.

The source-specific fields and raw responses are retained so downstream work
cannot silently treat any of these as routed request volume.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import pyarrow as pa
from lxml import html

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

HF_OPEN_MODELS_URL = (
    "https://huggingface.co/api/models?pipeline_tag=text-generation&sort=downloads"
    "&direction=-1&limit=500&full=true"
)
OLLAMA_LIBRARY_URL = "https://ollama.com/library"
DOCKER_REPOSITORIES = ("ollama/ollama", "vllm/vllm-openai", "lmsysorg/sglang")


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _number(value: str) -> int | None:
    """Parse a public abbreviated counter such as ``89.4M`` without rounding."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMB]?)\s*", value, re.I)
    if not match:
        return None
    scale = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2).upper()]
    return int(float(match.group(1)) * scale)


def _license(tags: list[Any]) -> str | None:
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("license:"):
            return tag.removeprefix("license:")
    return None


def hf_open_model_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalise public, text-generation Hub rankings by rolling downloads."""
    rows = []
    for rank, item in enumerate(body if isinstance(body, list) else [], start=1):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        gated = item.get("gated")
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "huggingface_open_models",
                "model_id": item["id"],
                "rank": rank,
                "downloads_30d": item.get("downloads"),
                "likes": item.get("likes"),
                "trending_score": item.get("trendingScore"),
                "cumulative_pulls": None,
                "pipeline_tag": item.get("pipeline_tag"),
                "library_name": item.get("library_name"),
                "license": _license(item.get("tags") or []),
                "gated": bool(gated),
                "public_ungated": not bool(item.get("private")) and not bool(gated),
                "metric_definition": "Hub rolling model-download counter; not inference usage",
                "quality_tier": "public-platform-counter",
                "record_json": _json(item),
            }
        )
    return rows


def ollama_library_rows(body: str | None, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Parse the public popular-library ranking and its cumulative pull counter."""
    if not body:
        return []
    tree = html.fromstring(body)
    seen: set[str] = set()
    rows = []
    for anchor in tree.xpath("//a[starts-with(@href, '/library/')]"):
        href = anchor.get("href") or ""
        model_id = href.removeprefix("/library/").strip("/")
        text = " ".join(anchor.text_content().split())
        match = re.search(r"(\d+(?:\.\d+)?[KMB]?)\s+Pulls\b", text, re.I)
        if not model_id or model_id in seen or not match:
            continue
        seen.add(model_id)
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "ollama_library",
                "model_id": model_id,
                "rank": len(rows) + 1,
                "downloads_30d": None,
                "likes": None,
                "trending_score": None,
                "cumulative_pulls": _number(match.group(1)),
                "pipeline_tag": None,
                "library_name": "ollama",
                "license": None,
                "gated": False,
                "public_ungated": True,
                "metric_definition": (
                    "Ollama Library cumulative model pulls; not inference requests"
                ),
                "quality_tier": "public-platform-counter",
                "record_json": _json({"href": href, "text": text}),
            }
        )
    return rows


def docker_runtime_rows(body_by_repo: dict[str, Any], run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Record deployment-runtime image pulls without calling them model usage."""
    rows = []
    for image, body in body_by_repo.items():
        if not isinstance(body, dict) or not body.get("name"):
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "docker_hub",
                "runtime": image.split("/", 1)[-1],
                "image": image,
                "pull_count": body.get("pull_count"),
                "star_count": body.get("star_count"),
                "last_updated": body.get("last_updated"),
                "metric_definition": (
                    "Docker Hub cumulative repository pulls; includes some version checks and "
                    "is a serving-runtime deployment proxy, not model consumption"
                ),
                "quality_tier": "public-platform-counter",
                "record_json": _json(body),
            }
        )
    return rows


def _status(source: str, rows: int, run_ts: str, dt: str, curated_dir: Path, url: str) -> None:
    write_source_run(
        source,
        status="success" if rows else "degraded",
        rows=rows,
        run_ts=run_ts,
        dt=dt,
        detail={"url": url},
        curated_dir=curated_dir,
    )


async def capture_open_usage(
    raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR
) -> dict[str, Any]:
    run_ts, dt = run_timestamp(), dt_partition()
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        hf, ollama, *docker = await asyncio.gather(
            fetcher.get_json(HF_OPEN_MODELS_URL),
            fetcher.get_text(OLLAMA_LIBRARY_URL),
            *(
                fetcher.get_json(
                    "https://hub.docker.com/v2/namespaces/"
                    f"{image.split('/', 1)[0]}/repositories/{image.split('/', 1)[1]}"
                )
                for image in DOCKER_REPOSITORIES
            ),
        )
        write_raw(fetcher.records, "open_usage", raw_dir, run_ts, dt)

    hf_rows = hf_open_model_rows(hf, run_ts, dt)
    ollama_rows = ollama_library_rows(ollama, run_ts, dt)
    model_rows = hf_rows + ollama_rows
    runtime_rows = docker_runtime_rows(
        dict(zip(DOCKER_REPOSITORIES, docker, strict=True)), run_ts, dt
    )
    if model_rows:
        write_partition(
            pa.Table.from_pylist(model_rows), "open_model_usage_daily", run_ts, dt, curated_dir
        )
    if runtime_rows:
        write_partition(
            pa.Table.from_pylist(runtime_rows),
            "oss_runtime_adoption_daily",
            run_ts,
            dt,
            curated_dir,
        )
    _status(
        "huggingface_open_models", len(hf_rows), run_ts, dt, curated_dir, HF_OPEN_MODELS_URL
    )
    _status("ollama_library", len(ollama_rows), run_ts, dt, curated_dir, OLLAMA_LIBRARY_URL)
    _status("docker_hub", len(runtime_rows), run_ts, dt, curated_dir, "https://hub.docker.com/v2")
    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "open_model_usage_rows": len(model_rows),
        "runtime_adoption_rows": len(runtime_rows),
    }
    log.info("open-model usage capture: %s", summary)
    return summary


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    summary = asyncio.run(capture_open_usage())
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
