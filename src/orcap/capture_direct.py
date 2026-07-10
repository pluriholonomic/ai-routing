"""Daily capture of DIRECT provider list prices, for the venue-basis test (H13):
what does the same model cost from the provider's own API vs via OpenRouter?

Three source tiers, kept explicitly separate in the curated provenance:
  - Structured public API: DeepInfra's model-list JSON.
  - Published docs table: Together's public serverless catalog.  It has exact
    API model IDs and per-million-token list prices, but it is a rendered
    documentation table rather than a versioned pricing API.  A header change
    yields zero Together rows (and a degraded source-run) rather than a
    best-effort or fuzzy parse.
  - Published model page: Fireworks' public serverless pages for a bounded,
    explicit list of current models.  Each page must state the exact Fireworks
    API model ID and its three per-million-token rates.  We do not crawl the
    provider's broad historical sitemap every day.

The remaining provider pages are raw-archived for later parser work.  Raw
evidence alone is not a usable H13 list-price observation.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import pyarrow as pa
from lxml import etree, html

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

DEEPINFRA_URL = "https://api.deepinfra.com/models/list"
CEREBRAS_MODELS_URL = "https://api.cerebras.ai/public/v1/models"
TOGETHER_SERVERLESS_MODELS_URL = "https://docs.together.ai/docs/serverless/models"
GROQ_MODELS_URL = "https://console.groq.com/docs/models"
FIREWORKS_MODEL_PAGES = {
    "accounts/fireworks/models/gpt-oss-20b": "https://fireworks.ai/models/fireworks/gpt-oss-20b",
    "accounts/fireworks/models/gpt-oss-120b": "https://fireworks.ai/models/fireworks/gpt-oss-120b",
}

RAW_PAGES = {
    "groq": GROQ_MODELS_URL,
    "novita_llm": "https://novita.ai/pricing",
    "together": TOGETHER_SERVERLESS_MODELS_URL,
    "fireworks": "https://fireworks.ai/pricing",
    "lambda": "https://lambda.ai/inference",
    "hyperbolic": "https://hyperbolic.ai/pricing",
    "cerebras": "https://www.cerebras.ai/pricing",
}

_MILLION = 1_000_000
_USD_PRICE = re.compile(r"^\$(\d+(?:\.\d+)?)$")
_GROQ_PRICE = re.compile(r"^\$(\d+(?:\.\d+)?)\s*input\s*\$(\d+(?:\.\d+)?)\s*output$")
_FIREWORKS_SERVERLESS_PRICE = re.compile(
    r"Available Serverless\s*Run queries immediately, pay only for usage\s*"
    r"\$(?P<input>\d+(?:\.\d+)?)\s*/\s*\$(?P<cached>\d+(?:\.\d+)?)\s*/\s*"
    r"\$(?P<output>\d+(?:\.\d+)?)\s*Per 1M Tokens \(input/cached input/output\)"
)
DIRECT_PRICE_SCHEMA = pa.schema(
    [
        pa.field("run_ts", pa.string()),
        pa.field("dt", pa.string()),
        pa.field("provider", pa.string()),
        pa.field("model_name", pa.string()),
        pa.field("direct_provider_model_id", pa.string()),
        pa.field("model_identifier_type", pa.string()),
        pa.field("model_type", pa.string()),
        pa.field("price_input_usd", pa.float64()),
        pa.field("price_output_usd", pa.float64()),
        pa.field("price_cached_input_usd", pa.float64()),
        pa.field("deprecated", pa.bool_()),
        pa.field("preview", pa.bool_()),
        pa.field("quote_unit", pa.string()),
        pa.field("source_type", pa.string()),
        pa.field("source_url", pa.string()),
        pa.field("source_schema_version", pa.string()),
        pa.field("record_json", pa.string()),
    ]
)


def _text(node: Any) -> str:
    return " ".join(node.text_content().replace("\xa0", " ").split())


def _header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usd_per_token(value: str) -> float | None:
    """Convert a literal public ``$X per 1M tokens`` cell to USD/token.

    The parser deliberately accepts only a single dollar price.  Ranges,
    marketing copy, blank cells, and changed table formats are excluded rather
    than silently interpreted as executable list quotes.
    """
    match = _USD_PRICE.fullmatch(value.strip())
    return float(match.group(1)) / _MILLION if match else None


def direct_price_table(rows: list[dict[str, Any]]) -> pa.Table:
    """Construct a stable union schema for heterogeneous provider adapters.

    ``Table.from_pylist`` otherwise adopts the first row's keys, which can
    silently discard provenance columns introduced by a later provider.
    """
    fields = DIRECT_PRICE_SCHEMA.names
    normalized = [{field: row.get(field) for field in fields} for row in rows]
    return pa.Table.from_pylist(normalized, schema=DIRECT_PRICE_SCHEMA)


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
                "quote_unit": "usd_per_token",
                "source_type": "structured_public_api",
                "source_url": DEEPINFRA_URL,
                "source_schema_version": "deepinfra_models_list_v1",
                "record_json": json.dumps(m, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def cerebras_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize Cerebras's documented public model catalog.

    The API reports token prices in USD/token and exposes both a Cerebras API
    id and (when available) a first-party Hugging Face repository id. The
    latter is used as the H13 match key only because it is a literal field in
    Cerebras's own response; the provider API id is retained separately.
    """
    models = body.get("data") if isinstance(body, dict) else body
    if not isinstance(models, list):
        return []
    rows = []
    for item in models:
        if not isinstance(item, dict):
            continue
        provider_model_id = item.get("id")
        pricing = item.get("pricing") or {}
        prompt, completion = _number(pricing.get("prompt")), _number(pricing.get("completion"))
        if not provider_model_id or prompt is None or completion is None:
            continue
        if prompt <= 0 or completion <= 0:
            continue
        canonical_model_id = item.get("hugging_face_id") or provider_model_id
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "provider": "cerebras",
                "model_name": str(canonical_model_id),
                "direct_provider_model_id": str(provider_model_id),
                "model_identifier_type": (
                    "first_party_hugging_face_id"
                    if item.get("hugging_face_id")
                    else "provider_api_id"
                ),
                "model_type": "chat",
                "price_input_usd": prompt,
                "price_output_usd": completion,
                "price_cached_input_usd": _number(pricing.get("input_cache_read")),
                "deprecated": bool(item.get("deprecated")),
                "preview": bool(item.get("preview")),
                "quote_unit": "usd_per_token",
                "source_type": "structured_public_api",
                "source_url": CEREBRAS_MODELS_URL,
                "source_schema_version": "cerebras_public_models_v1",
                "record_json": json.dumps(item, separators=(",", ":"), sort_keys=True),
            }
        )
    return rows


def together_rows(body: str | None, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize only Together's explicit chat price table.

    The source labels these columns as prices per 1M tokens.  We require the
    exact API-model and input/output-token columns, retain their original cells
    in ``record_json``, and keep Together's published docs provenance distinct
    from an API quote.  We deliberately do not fuzzy-match product names.
    """
    if not body:
        return []
    try:
        tree = html.fromstring(body)
    except (TypeError, ValueError, etree.ParserError):
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for table in tree.xpath("//table"):
        table_rows = table.xpath(".//tr")
        if not table_rows:
            continue
        headers = [_header(_text(cell)) for cell in table_rows[0].xpath("./th|./td")]
        try:
            model_idx = headers.index("api model string")
            input_idx = headers.index("input pricing (per 1m tokens)")
            output_idx = headers.index("output pricing (per 1m tokens)")
        except ValueError:
            continue
        cached_idx = next(
            (
                i
                for i, label in enumerate(headers)
                if label == "cached input pricing (per 1m tokens)"
            ),
            None,
        )
        required_width = max(model_idx, input_idx, output_idx) + 1
        for tr in table_rows[1:]:
            cells = [_text(cell) for cell in tr.xpath("./td")]
            if len(cells) < required_width:
                continue
            model_name = cells[model_idx].strip()
            price_input = _usd_per_token(cells[input_idx])
            price_output = _usd_per_token(cells[output_idx])
            if not model_name or model_name in seen or price_input is None or price_output is None:
                continue
            cached = (
                _usd_per_token(cells[cached_idx])
                if cached_idx is not None and cached_idx < len(cells)
                else None
            )
            seen.add(model_name)
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "provider": "together",
                    "model_name": model_name,
                    "model_type": "chat",
                    "price_input_usd": price_input,
                    "price_output_usd": price_output,
                    "price_cached_input_usd": cached,
                    "deprecated": False,
                    "quote_unit": "usd_per_token",
                    "source_type": "published_docs_table",
                    "source_url": TOGETHER_SERVERLESS_MODELS_URL,
                    "source_schema_version": "together_serverless_chat_v1",
                    "record_json": json.dumps(
                        {"headers": headers, "cells": cells}, separators=(",", ":"), sort_keys=True
                    ),
                }
            )
    return rows


def groq_rows(body: str | None, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize Groq's public exact-ID synchronous model price table."""
    if not body:
        return []
    try:
        tree = html.fromstring(body)
    except (TypeError, ValueError, etree.ParserError):
        return []
    rows, seen = [], set()
    for table in tree.xpath("//table"):
        table_rows = table.xpath(".//tr")
        if not table_rows:
            continue
        headers = [_header(_text(cell)) for cell in table_rows[0].xpath("./th|./td")]
        try:
            model_idx = headers.index("model id")
            price_idx = headers.index("price per 1m tokens")
        except ValueError:
            continue
        for tr in table_rows[1:]:
            cells = [_text(cell) for cell in tr.xpath("./td")]
            if len(cells) <= max(model_idx, price_idx):
                continue
            model_name = cells[model_idx].strip()
            match = _GROQ_PRICE.fullmatch(cells[price_idx])
            if not model_name or model_name in seen or not match:
                continue
            seen.add(model_name)
            rows.append(
                {
                    "run_ts": run_ts, "dt": dt, "provider": "groq", "model_name": model_name,
                    "model_type": "chat", "price_input_usd": float(match.group(1)) / _MILLION,
                    "price_output_usd": float(match.group(2)) / _MILLION,
                    "price_cached_input_usd": None, "deprecated": False,
                    "quote_unit": "usd_per_token", "source_type": "published_docs_table",
                    "source_url": GROQ_MODELS_URL, "source_schema_version": "groq_models_v1",
                    "record_json": json.dumps(
                        {"headers": headers, "cells": cells}, separators=(",", ":"), sort_keys=True
                    ),
                }
            )
    return rows


def fireworks_rows(
    body_by_model_id: dict[str, str | None], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize a bounded set of first-party Fireworks serverless model pages.

    The expected key is the literal provider API model ID, previously verified
    in OpenRouter's endpoint record.  The collector rejects pages that omit
    that exact ID or the labeled serverless input/cached/output price block.
    This is an identity assertion from two first-party sources, not a model-name
    crosswalk.
    """
    rows = []
    for model_id, body in body_by_model_id.items():
        if not body:
            continue
        try:
            tree = html.fromstring(body)
        except (TypeError, ValueError, etree.ParserError):
            continue
        for node in tree.xpath("//script|//style"):
            node.getparent().remove(node)
        visible = " ".join(tree.text_content().split())
        match = _FIREWORKS_SERVERLESS_PRICE.search(visible)
        if model_id not in visible or not match:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "provider": "fireworks",
                "model_name": model_id,
                "model_type": "chat",
                "price_input_usd": float(match["input"]) / _MILLION,
                "price_output_usd": float(match["output"]) / _MILLION,
                "price_cached_input_usd": float(match["cached"]) / _MILLION,
                "deprecated": False,
                "quote_unit": "usd_per_token",
                "source_type": "published_model_page",
                "source_url": FIREWORKS_MODEL_PAGES[model_id],
                "source_schema_version": "fireworks_serverless_model_page_v1",
                "record_json": json.dumps(
                    {
                        "direct_provider_model_id": model_id,
                        "prices_usd_per_million_tokens": match.groupdict(),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            }
        )
    return rows


async def capture_direct(
    raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR
) -> dict[str, Any]:
    run_ts = run_timestamp()
    dt = dt_partition()
    page_urls = {
        **RAW_PAGES,
        **{f"fireworks_model:{model_id}": url for model_id, url in FIREWORKS_MODEL_PAGES.items()},
    }
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        deepinfra, cerebras, *raw_pages = await asyncio.gather(
            fetcher.get_json(DEEPINFRA_URL),
            fetcher.get_json(CEREBRAS_MODELS_URL),
            *(fetcher.get_text(url) for url in page_urls.values()),
        )
        write_raw(fetcher.records, "direct_providers", raw_dir, run_ts, dt)

    raw_by_source = dict(zip(page_urls, raw_pages, strict=True))
    deepinfra = deepinfra_rows(deepinfra, run_ts, dt)
    cerebras = cerebras_rows(cerebras, run_ts, dt)
    groq = groq_rows(raw_by_source.get("groq"), run_ts, dt)
    together = together_rows(raw_by_source.get("together"), run_ts, dt)
    fireworks = fireworks_rows(
        {
            model_id: raw_by_source.get(f"fireworks_model:{model_id}")
            for model_id in FIREWORKS_MODEL_PAGES
        },
        run_ts,
        dt,
    )
    rows = deepinfra + cerebras + groq + together + fireworks
    if rows:
        write_partition(direct_price_table(rows), "direct_prices_daily", run_ts, dt, curated_dir)
    write_source_run(
        "direct_groq_docs",
        status="success" if groq else "degraded",
        rows=len(groq), run_ts=run_ts, dt=dt, curated_dir=curated_dir,
        detail={"url": GROQ_MODELS_URL, "source_type": "published_docs_table"},
    )
    write_source_run(
        "direct_deepinfra_api",
        status="success" if deepinfra else "degraded",
        rows=len(deepinfra),
        run_ts=run_ts,
        dt=dt,
        curated_dir=curated_dir,
        detail={"url": DEEPINFRA_URL, "source_type": "structured_public_api"},
    )
    write_source_run(
        "direct_cerebras_api",
        status="success" if cerebras else "degraded",
        rows=len(cerebras),
        run_ts=run_ts,
        dt=dt,
        curated_dir=curated_dir,
        detail={
            "url": CEREBRAS_MODELS_URL,
            "source_type": "structured_public_api",
            "schema_version": "cerebras_public_models_v1",
        },
    )
    write_source_run(
        "direct_together_docs",
        status="success" if together else "degraded",
        rows=len(together),
        run_ts=run_ts,
        dt=dt,
        curated_dir=curated_dir,
        detail={
            "url": TOGETHER_SERVERLESS_MODELS_URL,
            "source_type": "published_docs_table",
            "schema_version": "together_serverless_chat_v1",
        },
    )
    write_source_run(
        "direct_fireworks_pages",
        status="success" if fireworks else "degraded",
        rows=len(fireworks),
        run_ts=run_ts,
        dt=dt,
        curated_dir=curated_dir,
        detail={
            "model_pages": FIREWORKS_MODEL_PAGES,
            "source_type": "published_model_page",
            "schema_version": "fireworks_serverless_model_page_v1",
        },
    )
    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "deepinfra_models": len(deepinfra),
        "cerebras_models": len(cerebras),
        "groq_models": len(groq),
        "together_models": len(together),
        "fireworks_models": len(fireworks),
        "direct_price_rows": len(rows),
        "raw_pages": len(page_urls),
    }
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
