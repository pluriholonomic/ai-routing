"""Daily capture of DIRECT provider list prices, for the venue-basis test (H13):
what does the same model cost from the provider's own API vs via OpenRouter?

Two tiers:
  - Parsed now: DeepInfra (public JSON with per-token pricing) ->
    direct_prices_daily rows.
  - Raw-archived for later parsing: pricing pages of other majors (Groq,
    Novita, Together, Fireworks, Lambda, Hyperbolic, Parasail) — stored
    verbatim in the raw layer so history exists from today even before a
    parser does.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw

log = logging.getLogger(__name__)

DEEPINFRA_URL = "https://api.deepinfra.com/models/list"

RAW_PAGES = {
    "groq": "https://groq.com/pricing",
    "novita_llm": "https://novita.ai/pricing",
    "together": "https://www.together.ai/pricing",
    "fireworks": "https://fireworks.ai/pricing",
    "lambda": "https://lambda.ai/inference",
    "hyperbolic": "https://hyperbolic.ai/pricing",
    "cerebras": "https://www.cerebras.ai/pricing",
}


def deepinfra_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    for m in body or []:
        pricing = m.get("pricing") or {}
        if pricing.get("type") != "tokens":
            continue
        cin, cout = pricing.get("cents_per_input_token"), pricing.get("cents_per_output_token")
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "provider": "deepinfra",
                "model_name": m.get("model_name"),
                "model_type": m.get("type"),
                "price_input_usd": cin / 100 if cin is not None else None,
                "price_output_usd": cout / 100 if cout is not None else None,
                "price_cached_input_usd": (pricing.get("rate_per_input_token_cached") or 0) / 100
                if pricing.get("rate_per_input_token_cached") is not None
                else None,
                "deprecated": bool(m.get("deprecated")),
                "record_json": json.dumps(m, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


async def capture_direct(
    raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR
) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        deepinfra = await fetcher.get_json(DEEPINFRA_URL)
        # raw-archive pricing pages (HTML lands in the record body)
        for _name, url in RAW_PAGES.items():
            await fetcher.get_json(url)
        write_raw(fetcher.records, "direct_providers", raw_dir, run_ts, dt)

    rows = deepinfra_rows(deepinfra, run_ts, dt)
    if rows:
        write_partition(
            pa.Table.from_pylist(rows), "direct_prices_daily", run_ts, dt, curated_dir
        )
    summary = {"run_ts": run_ts, "dt": dt, "deepinfra_models": len(rows),
               "raw_pages": len(RAW_PAGES)}
    log.info("direct capture complete: %s", summary)
    return summary


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    summary = asyncio.run(capture_direct())
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
