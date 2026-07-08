"""Daily HF Hub stats for listed models — a leading demand indicator (H20).

Downloads/likes/trendingScore move before routed volume does, especially at
launch, which is where 73% of repricing happens (H17). One public API call per
model with an hf_slug (from the OpenRouter models list).
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa

from .capture_api import write_partition
from .config import API_V1, CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)

HF_URL = (
    "https://huggingface.co/api/models/{slug}"
    "?expand[]=downloads&expand[]=likes&expand[]=trendingScore&expand[]=downloadsAllTime"
)


async def capture_hf_stats(
    raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR
) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()
    async with make_client() as client:
        fetcher = Fetcher(client, rps=3)
        models_doc = await fetcher.get_json(f"{API_V1}/models")
        pairs: dict[str, str] = {}
        for m in (models_doc or {}).get("data", []):
            hf = m.get("hugging_face_id")
            if hf and ":" not in (m.get("id") or ""):
                pairs[hf] = m.get("canonical_slug") or m.get("id")
        bodies = await asyncio.gather(
            *(fetcher.get_json(HF_URL.format(slug=quote(hf, safe="/"))) for hf in pairs)
        )
        write_raw(fetcher.records, "hf_stats", raw_dir, run_ts, dt)

    rows = []
    for (hf, permaslug), b in zip(pairs.items(), bodies, strict=True):
        if not isinstance(b, dict) or "id" not in b:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "hf_slug": hf,
                "model_permaslug": permaslug,
                "downloads_30d": b.get("downloads"),
                "downloads_all_time": b.get("downloadsAllTime"),
                "likes": b.get("likes"),
                "trending_score": b.get("trendingScore"),
            }
        )
    if rows:
        write_partition(pa.Table.from_pylist(rows), "hf_model_stats_daily", run_ts, dt, curated_dir)
    summary = {"run_ts": run_ts, "dt": dt, "hf_models": len(rows), "requested": len(pairs)}
    log.info("hf stats capture: %s", summary)
    return summary


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    summary = asyncio.run(capture_hf_stats())
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
