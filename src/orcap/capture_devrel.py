"""Daily developer-adoption telemetry — public leading indicators of inference
demand (H20 features; H40's generation channels).

  npm        weekly downloads for AI SDKs / router clients (public API)
  pypistats  recent downloads for python SDKs (etiquette: few calls, skip on 429)
  HN         story mentions per top model name, trailing 7d (Algolia public)
  GitHub     stars + last push for harness/serving repos (public API;
             GITHUB_TOKEN honored when present for rate limits)

Table: devrel_daily (source, name, metric, value). Historical PyPI series
comes from BigQuery public data via `orcap defi` (pypi_downloads_daily).
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa

from .capture_api import write_partition
from .config import API_V1, CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)

NPM_PACKAGES = [
    "ai",
    "@openrouter/ai-sdk-provider",
    "@anthropic-ai/sdk",
    "openai",
    "@google/genai",
    "@ai-sdk/openai",
    "langchain",
    "ollama",
]
PYPI_PACKAGES = ["openai", "anthropic", "litellm", "vllm", "langchain", "transformers"]
GITHUB_REPOS = [
    "cline/cline",
    "RooCodeInc/Roo-Code",
    "Kilo-Org/kilocode",
    "BerriAI/litellm",
    "vllm-project/vllm",
    "sgl-project/sglang",
    "ollama/ollama",
    "OpenRouterTeam/ai-sdk-provider",
]


async def capture_devrel(
    raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR
) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()
    rows: list[dict[str, Any]] = []

    def add(source: str, name: str, metric: str, value):
        if value is not None:
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "source": source,
                    "name": name,
                    "metric": metric,
                    "value": float(value),
                }
            )

    async with make_client() as client:
        fetcher = Fetcher(client, rps=2)

        for pkg in NPM_PACKAGES:
            b = await fetcher.get_json(
                f"https://api.npmjs.org/downloads/point/last-week/{quote(pkg, safe='@/')}"
            )
            add("npm", pkg, "downloads_7d", (b or {}).get("downloads"))

        for pkg in PYPI_PACKAGES:
            b = await fetcher.get_json(f"https://pypistats.org/api/packages/{pkg}/recent")
            d = (b or {}).get("data") if isinstance(b, dict) else None
            add("pypi", pkg, "downloads_7d", (d or {}).get("last_week"))
            await asyncio.sleep(1.5)  # pypistats etiquette

        gh_headers = {}
        if os.environ.get("GITHUB_TOKEN"):
            gh_headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        for repo in GITHUB_REPOS:
            b = await fetcher.get_json(
                f"https://api.github.com/repos/{repo}", headers=gh_headers or None
            )
            if isinstance(b, dict):
                add("github", repo, "stars", b.get("stargazers_count"))
                add("github", repo, "open_issues", b.get("open_issues_count"))

        # HN mentions for top-20 model short names (trailing 7 days)
        models = await fetcher.get_json(f"{API_V1}/models")
        names: list[str] = []
        for m in (models or {}).get("data", []):
            short = (m.get("canonical_slug") or "").split("/")[-1]
            short = short.split("-2025")[0].split("-2026")[0]
            if short and short not in names:
                names.append(short)
        week_ago = int(time.time()) - 7 * 86400
        for name in names[:20]:
            b = await fetcher.get_json(
                "https://hn.algolia.com/api/v1/search?query="
                + quote(f'"{name}"')
                + f"&tags=story&numericFilters=created_at_i>{week_ago}"
            )
            add("hn", name, "stories_7d", (b or {}).get("nbHits"))

        write_raw(fetcher.records, "devrel", raw_dir, run_ts, dt)

    if rows:
        write_partition(pa.Table.from_pylist(rows), "devrel_daily", run_ts, dt, curated_dir)
    summary = {"run_ts": run_ts, "dt": dt, "rows": len(rows)}
    log.info("devrel capture: %s", summary)
    return summary


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    summary = asyncio.run(capture_devrel())
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
