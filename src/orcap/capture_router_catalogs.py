"""Credential-free quote capture for public inference-router catalogs.

The three sources in this module expose different surfaces:

* Requesty and NemoRouter return structured provider/model prices.
* Glama's OpenAI-compatible model list omits prices, while its public model
  pages expose the provider menu and posted USD-per-million-token prices.

All prices are normalized to USD per million tokens.  The rows are posted
catalog quotes, not market-wide demand, realized selections, executable firm
quotes, or evidence that two routers apply the same eligibility rules.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow as pa
from lxml import html

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

GLAMA_MODELS_URL = "https://gateway.glama.ai/v1/models"
GLAMA_MODEL_PAGE_TEMPLATE = "https://glama.ai/gateway/models/{model_key}"
REQUESTY_MODELS_URL = "https://router.requesty.ai/v1/models"
NEMO_MODELS_URL = "https://nemorouter.ai/api/public/models"
MILLION = 1_000_000.0

PUBLIC_ROUTER_QUOTE_SCHEMA = pa.schema(
    [
        pa.field("run_ts", pa.string()),
        pa.field("dt", pa.string()),
        pa.field("router", pa.string()),
        pa.field("source_model_id", pa.string()),
        pa.field("source_model_key", pa.string()),
        pa.field("model_creator", pa.string()),
        pa.field("provider_name", pa.string()),
        pa.field("mode", pa.string()),
        pa.field("status", pa.string()),
        pa.field("price_input_usd_per_mtok", pa.float64()),
        pa.field("price_output_usd_per_mtok", pa.float64()),
        pa.field("price_cache_read_usd_per_mtok", pa.float64()),
        pa.field("price_cache_write_usd_per_mtok", pa.float64()),
        pa.field("context_length", pa.int64()),
        pa.field("max_output_tokens", pa.int64()),
        pa.field("supports_caching", pa.bool_()),
        pa.field("supports_vision", pa.bool_()),
        pa.field("supports_tools", pa.bool_()),
        pa.field("supports_reasoning", pa.bool_()),
        pa.field("supports_structured_output", pa.bool_()),
        pa.field("catalog_url", pa.string()),
        pa.field("model_join_basis", pa.string()),
        pa.field("quote_kind", pa.string()),
        pa.field("metric_definition", pa.string()),
        pa.field("record_json", pa.string()),
    ]
)


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _per_million(value: Any) -> float | None:
    number = _float(value)
    return None if number is None else number * MILLION


def _text(node: Any) -> str:
    return " ".join(node.text_content().replace("\xa0", " ").split())


def _source_model_key(model_id: str) -> str:
    """Strip only a documented router/provider prefix; do no fuzzy mapping."""
    return model_id.rsplit("/", 1)[-1].strip().lower()


def _base_row(
    *,
    run_ts: str,
    dt: str,
    router: str,
    source_model_id: str,
    provider_name: str,
    catalog_url: str,
) -> dict[str, Any]:
    return {
        "run_ts": run_ts,
        "dt": dt,
        "router": router,
        "source_model_id": source_model_id,
        "source_model_key": _source_model_key(source_model_id),
        "model_creator": None,
        "provider_name": provider_name,
        "mode": None,
        "status": None,
        "price_input_usd_per_mtok": None,
        "price_output_usd_per_mtok": None,
        "price_cache_read_usd_per_mtok": None,
        "price_cache_write_usd_per_mtok": None,
        "context_length": None,
        "max_output_tokens": None,
        "supports_caching": None,
        "supports_vision": None,
        "supports_tools": None,
        "supports_reasoning": None,
        "supports_structured_output": None,
        "catalog_url": catalog_url,
        "model_join_basis": (
            "literal source model suffix only; cross-router use requires a unique exact "
            "match to the official OpenRouter model catalog"
        ),
        "quote_kind": "public_posted_catalog_quote",
        "metric_definition": (
            "Public router catalog price normalized to USD per million tokens; not a "
            "request, token-consumption measure, selected route, firm fill, or capacity quote"
        ),
        "record_json": "{}",
    }


def requesty_quote_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize Requesty's public OpenAI-compatible model catalog."""
    rows: list[dict[str, Any]] = []
    for item in (body or {}).get("data") or []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        model_id = item["id"].strip()
        if not model_id or "/" not in model_id:
            continue
        provider = model_id.split("/", 1)[0].lower()
        row = _base_row(
            run_ts=run_ts,
            dt=dt,
            router="requesty",
            source_model_id=model_id,
            provider_name=provider,
            catalog_url=REQUESTY_MODELS_URL,
        )
        row.update(
            {
                "mode": item.get("api"),
                "price_input_usd_per_mtok": _per_million(item.get("input_price")),
                "price_output_usd_per_mtok": _per_million(item.get("output_price")),
                "price_cache_read_usd_per_mtok": _per_million(item.get("cached_price")),
                "context_length": _int(item.get("context_window")),
                "max_output_tokens": _int(item.get("max_output_tokens")),
                "supports_caching": item.get("supports_caching"),
                "supports_vision": item.get("supports_vision"),
                "supports_tools": item.get("supports_tool_calling"),
                "supports_reasoning": item.get("supports_reasoning"),
                "supports_structured_output": item.get("supports_output_json_schema"),
                "record_json": _json(item),
            }
        )
        rows.append(row)
    return rows


def nemo_quote_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize NemoRouter's public LiteLLM-style model catalog."""
    rows: list[dict[str, Any]] = []
    for item in (body or {}).get("data") or []:
        if not isinstance(item, dict) or not isinstance(item.get("model_id"), str):
            continue
        model_id = item["model_id"].strip()
        provider = str(item.get("provider") or "").strip().lower()
        if not model_id or not provider:
            continue
        info = item.get("model_info") if isinstance(item.get("model_info"), dict) else {}
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        source_record_id = str(params.get("model") or f"{provider}/{model_id}")
        row = _base_row(
            run_ts=run_ts,
            dt=dt,
            router="nemorouter",
            source_model_id=source_record_id,
            provider_name=provider,
            catalog_url=NEMO_MODELS_URL,
        )
        # The public model_id is the provider-neutral key Nemo displays; retain
        # it rather than deriving the join key from an upstream deployment id.
        row["source_model_key"] = model_id.lower()
        row.update(
            {
                "mode": item.get("mode") or info.get("mode"),
                "price_input_usd_per_mtok": _per_million(
                    info.get("input_cost_per_token")
                ),
                "price_output_usd_per_mtok": _per_million(
                    info.get("output_cost_per_token")
                ),
                "price_cache_read_usd_per_mtok": _per_million(
                    info.get("cache_read_input_token_cost")
                ),
                "price_cache_write_usd_per_mtok": _per_million(
                    info.get("cache_creation_input_token_cost")
                ),
                "context_length": _int(
                    info.get("max_input_tokens") or info.get("max_context_tokens")
                ),
                "max_output_tokens": _int(info.get("max_tokens")),
                "supports_caching": info.get("supports_prompt_caching"),
                "supports_vision": info.get("supports_vision"),
                "supports_tools": info.get("supports_function_calling"),
                "supports_reasoning": info.get("supports_reasoning"),
                "supports_structured_output": info.get("supports_response_schema"),
                "record_json": _json(item),
            }
        )
        rows.append(row)
    return rows


def _glama_price(value: str) -> float | None:
    compact = re.sub(r"\s+", "", value).replace("$", "").replace(",", "")
    if compact in {"", "-", "–", "—"}:
        return None
    return _float(compact)


def _glama_property(document: Any, name: str) -> Any | None:
    for tr in document.xpath("//tr"):
        cells = tr.xpath("./th|./td")
        if len(cells) == 2 and _text(cells[0]) == name:
            return cells[1]
    return None


def _glama_token_limits(document: Any) -> tuple[int | None, int | None]:
    cell = _glama_property(document, "Token limits")
    if cell is None:
        return None, None
    limits: dict[str, int | None] = {}
    for section in cell.xpath(".//section"):
        heading = " ".join(section.xpath("./h4//text()")).strip().lower()
        value = " ".join(section.xpath("./p//text()")).replace(",", "").strip()
        limits[heading] = _int(value)
    return limits.get("input token limit"), limits.get("output token limit")


def glama_quote_rows(
    page: str | None,
    expected_model_key: str,
    run_ts: str,
    dt: str,
    catalog_url: str,
) -> list[dict[str, Any]]:
    """Parse one public Glama model page and its nested provider-price table."""
    if not page:
        return []
    try:
        document = html.fromstring(page)
    except (ValueError, TypeError):
        return []

    model_cell = _glama_property(document, "Model ID")
    model_ids = model_cell.xpath(".//code/text()") if model_cell is not None else []
    model_id = model_ids[0].strip() if model_ids else expected_model_key
    if not model_id:
        return []
    creator_cell = _glama_property(document, "Creator")
    creator = _text(creator_cell).lower() if creator_cell is not None else None
    context_length, max_output_tokens = _glama_token_limits(document)
    capability_cell = _glama_property(document, "Capabilities")
    capabilities = {
        value.lower() for value in capability_cell.xpath(".//p//text()")
    } if capability_cell is not None else set()

    provider_tables = [
        table
        for table in document.xpath("//table")
        if not table.xpath(".//table") and "USD / M Tokens" in _text(table)
    ]
    if len(provider_tables) != 1:
        return []

    rows: list[dict[str, Any]] = []
    for tr in provider_tables[0].xpath(".//tr"):
        cells = tr.xpath("./td")
        if len(cells) != 5:
            continue
        provider_links = cells[0].xpath(".//a[contains(@href, '/providers/')]")
        if len(provider_links) != 1:
            continue
        provider = _text(provider_links[0]).lower()
        modes = cells[0].xpath(".//button/span/text()")
        statuses = tr.xpath(".//*[@data-status]/@data-status")
        row = _base_row(
            run_ts=run_ts,
            dt=dt,
            router="glama",
            source_model_id=model_id,
            provider_name=provider,
            catalog_url=catalog_url,
        )
        row.update(
            {
                "source_model_key": model_id.lower(),
                "model_creator": creator,
                "mode": modes[0].strip().lower() if modes else None,
                "status": statuses[0].strip().lower() if statuses else None,
                "price_input_usd_per_mtok": _glama_price(_text(cells[1])),
                "price_output_usd_per_mtok": _glama_price(_text(cells[2])),
                "price_cache_read_usd_per_mtok": _glama_price(_text(cells[3])),
                "price_cache_write_usd_per_mtok": _glama_price(_text(cells[4])),
                "context_length": context_length,
                "max_output_tokens": max_output_tokens,
                "supports_caching": "caching" in capabilities,
                "supports_vision": "vision" in capabilities,
                "supports_tools": "function calling" in capabilities,
                "supports_reasoning": "reasoning" in capabilities,
                "supports_structured_output": "structured outputs" in capabilities,
                "record_json": _json(
                    {
                        "expected_model_key": expected_model_key,
                        "reported_model_id": model_id,
                        "creator": creator,
                        "provider": provider,
                        "mode": modes[0].strip() if modes else None,
                        "status": statuses[0] if statuses else None,
                        "price_cells": [_text(cell) for cell in cells[1:]],
                    }
                ),
            }
        )
        rows.append(row)
    return rows


def _model_list(body: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise RuntimeError(f"{source} public models endpoint returned no data list")
    return [item for item in body["data"] if isinstance(item, dict)]


async def capture_router_catalogs(
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    """Capture all credential-free router quote surfaces at one timestamp."""
    run_ts, dt = run_timestamp(), dt_partition()
    async with make_client() as client:
        requesty_fetcher = Fetcher(client, rps=2.0)
        nemo_fetcher = Fetcher(client, rps=2.0)
        glama_fetcher = Fetcher(client, rps=2.0)
        requesty_body, nemo_body, glama_body = await asyncio.gather(
            requesty_fetcher.get_json(REQUESTY_MODELS_URL),
            nemo_fetcher.get_json(NEMO_MODELS_URL),
            glama_fetcher.get_json(GLAMA_MODELS_URL),
        )

        requesty_models = _model_list(requesty_body, "Requesty")
        nemo_models = _model_list(nemo_body, "NemoRouter")
        glama_models = _model_list(glama_body, "Glama")
        glama_keys = sorted(
            {
                _source_model_key(str(item["id"]))
                for item in glama_models
                if isinstance(item.get("id"), str) and item["id"].strip()
            }
        )
        glama_urls = [
            GLAMA_MODEL_PAGE_TEMPLATE.format(model_key=quote(key, safe=""))
            for key in glama_keys
        ]
        glama_pages = await asyncio.gather(
            *(glama_fetcher.get_text(url) for url in glama_urls)
        )

        write_raw(requesty_fetcher.records, "requesty_public_catalog", raw_dir, run_ts, dt)
        write_raw(nemo_fetcher.records, "nemo_public_catalog", raw_dir, run_ts, dt)
        write_raw(glama_fetcher.records, "glama_public_catalog", raw_dir, run_ts, dt)

    requesty_rows = requesty_quote_rows(requesty_body, run_ts, dt)
    nemo_rows = nemo_quote_rows(nemo_body, run_ts, dt)
    glama_rows = [
        row
        for key, url, page in zip(glama_keys, glama_urls, glama_pages, strict=True)
        for row in glama_quote_rows(page, key, run_ts, dt, url)
    ]
    all_rows = requesty_rows + nemo_rows + glama_rows
    if not requesty_rows or not nemo_rows or not glama_rows:
        raise RuntimeError(
            "one or more public router catalogs normalized to zero quote rows: "
            f"requesty={len(requesty_rows)}, nemo={len(nemo_rows)}, glama={len(glama_rows)}"
        )

    write_partition(
        pa.Table.from_pylist(all_rows, schema=PUBLIC_ROUTER_QUOTE_SCHEMA),
        "router_public_quote_snapshots",
        run_ts,
        dt,
        curated_dir,
    )

    glama_pages_with_quotes = sum(
        bool(glama_quote_rows(page, key, run_ts, dt, url))
        for key, url, page in zip(glama_keys, glama_urls, glama_pages, strict=True)
    )
    source_details = {
        "requesty_public_catalog": {
            "rows": len(requesty_rows),
            "catalog_models": len(requesty_models),
            "url": REQUESTY_MODELS_URL,
            "source_type": "structured_public_api",
        },
        "nemo_public_catalog": {
            "rows": len(nemo_rows),
            "catalog_models": len(nemo_models),
            "url": NEMO_MODELS_URL,
            "source_type": "structured_public_api",
        },
        "glama_public_catalog": {
            "rows": len(glama_rows),
            "catalog_models": len(glama_models),
            "model_pages_attempted": len(glama_keys),
            "model_pages_with_quotes": glama_pages_with_quotes,
            "url": GLAMA_MODELS_URL,
            "source_type": "structured_public_api_plus_public_ssr_model_pages",
        },
    }
    for source, detail in source_details.items():
        write_source_run(
            source,
            status="success",
            rows=detail["rows"],
            run_ts=run_ts,
            dt=dt,
            curated_dir=curated_dir,
            detail=detail,
        )

    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "rows": len(all_rows),
        "requesty_rows": len(requesty_rows),
        "nemo_rows": len(nemo_rows),
        "glama_rows": len(glama_rows),
        "glama_model_pages": len(glama_keys),
        "glama_pages_with_quotes": glama_pages_with_quotes,
    }
    log.info("public router catalog capture complete: %s", summary)
    return summary


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        summary = asyncio.run(capture_router_catalogs())
    except Exception as exc:
        failure_ts, failure_dt = run_timestamp(), dt_partition()
        for source in (
            "glama_public_catalog",
            "requesty_public_catalog",
            "nemo_public_catalog",
        ):
            write_source_run(
                source,
                status="failed",
                rows=0,
                run_ts=failure_ts,
                dt=failure_dt,
                detail={"error_type": type(exc).__name__, "message": str(exc)},
            )
        raise
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
