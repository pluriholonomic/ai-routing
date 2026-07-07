"""Turn raw OpenRouter JSON into Arrow tables.

Every table keeps the full source record as a JSON string column (`record_json`)
so schema drift on OpenRouter's side never loses data — explicit columns are a
convenience layer, the raw record is the contract.

Prices arrive as decimal strings (e.g. "0.00000043"); we store both the original
string and a float64 in USD per token.
"""

import hashlib
import json
from typing import Any

import pyarrow as pa


def _f(x: Any) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _s(x: Any) -> str | None:
    return None if x is None else str(x)


def _json(x: Any) -> str:
    return json.dumps(x, separators=(",", ":"), sort_keys=True)


PRICE_FIELDS = [
    "prompt",
    "completion",
    "request",
    "image",
    "audio",
    "web_search",
    "internal_reasoning",
    "input_cache_read",
    "input_cache_write",
]


def _price_columns(pricing: dict[str, Any] | None, row: dict[str, Any]) -> None:
    pricing = pricing or {}
    for field in PRICE_FIELDS:
        row[f"price_{field}"] = _f(pricing.get(field))
        row[f"price_{field}_str"] = _s(pricing.get(field))
    row["price_discount"] = _f(pricing.get("discount"))


def models_table(models: list[dict[str, Any]], run_ts: str, dt: str) -> pa.Table:
    rows = []
    for m in models:
        arch = m.get("architecture") or {}
        top = m.get("top_provider") or {}
        row: dict[str, Any] = {
            "run_ts": run_ts,
            "dt": dt,
            "id": m.get("id"),
            "canonical_slug": m.get("canonical_slug"),
            "name": m.get("name"),
            "author": (m.get("id") or "").split("/")[0] or None,
            "created": m.get("created"),
            "context_length": m.get("context_length"),
            "modality": arch.get("modality"),
            "tokenizer": arch.get("tokenizer"),
            "input_modalities": arch.get("input_modalities") or [],
            "output_modalities": arch.get("output_modalities") or [],
            "top_context_length": top.get("context_length"),
            "top_max_completion_tokens": top.get("max_completion_tokens"),
            "is_moderated": top.get("is_moderated"),
            "supported_parameters": m.get("supported_parameters") or [],
            "expiration_date": m.get("expiration_date"),
            "hugging_face_id": m.get("hugging_face_id"),
            "record_json": _json(m),
        }
        _price_columns(m.get("pricing"), row)
        rows.append(row)
    return pa.Table.from_pylist(rows, schema=_models_schema())


def endpoints_table(endpoint_docs: list[dict[str, Any]], run_ts: str, dt: str) -> pa.Table:
    """endpoint_docs: list of `data` objects from /models/{slug}/endpoints responses.

    The v1 API has no endpoint UUID, and (model, provider, tag) is not unique —
    a provider can serve two SKUs under one tag (e.g. with/without tool support).
    `endpoint_fingerprint` hashes the stable capability fields to tell them apart.
    """
    rows = []
    for doc in endpoint_docs:
        model_id = doc.get("id")
        for ep in doc.get("endpoints") or []:
            fingerprint = hashlib.sha1(
                _json(
                    [
                        ep.get("quantization"),
                        ep.get("context_length"),
                        ep.get("max_completion_tokens"),
                        ep.get("max_prompt_tokens"),
                        sorted(ep.get("supported_parameters") or []),
                    ]
                ).encode()
            ).hexdigest()[:12]
            row: dict[str, Any] = {
                "endpoint_fingerprint": fingerprint,
                "run_ts": run_ts,
                "dt": dt,
                "model_id": model_id,
                "model_name": doc.get("name"),
                "endpoint_name": ep.get("name"),
                "provider_name": ep.get("provider_name"),
                "tag": ep.get("tag"),
                "quantization": ep.get("quantization"),
                "context_length": ep.get("context_length"),
                "max_completion_tokens": ep.get("max_completion_tokens"),
                "max_prompt_tokens": ep.get("max_prompt_tokens"),
                "status": ep.get("status"),
                "uptime_last_5m": _f(ep.get("uptime_last_5m")),
                "uptime_last_30m": _f(ep.get("uptime_last_30m")),
                "uptime_last_1d": _f(ep.get("uptime_last_1d")),
                "latency_last_30m": _f(ep.get("latency_last_30m")),
                "throughput_last_30m": _f(ep.get("throughput_last_30m")),
                "supports_implicit_caching": ep.get("supports_implicit_caching"),
                "supported_parameters": ep.get("supported_parameters") or [],
                "record_json": _json(ep),
            }
            _price_columns(ep.get("pricing"), row)
            rows.append(row)
    return pa.Table.from_pylist(rows, schema=_endpoints_schema())


def providers_table(providers: list[dict[str, Any]], run_ts: str, dt: str) -> pa.Table:
    rows = [
        {
            "run_ts": run_ts,
            "dt": dt,
            "slug": p.get("slug"),
            "name": p.get("name"),
            "headquarters": p.get("headquarters"),
            "datacenters": p.get("datacenters") or [],
            "privacy_policy_url": p.get("privacy_policy_url"),
            "terms_of_service_url": p.get("terms_of_service_url"),
            "status_page_url": p.get("status_page_url"),
            "record_json": _json(p),
        }
        for p in providers
    ]
    return pa.Table.from_pylist(rows, schema=_providers_schema())


def _price_schema_fields() -> list[pa.Field]:
    fields = []
    for f in PRICE_FIELDS:
        fields.append(pa.field(f"price_{f}", pa.float64()))
        fields.append(pa.field(f"price_{f}_str", pa.string()))
    fields.append(pa.field("price_discount", pa.float64()))
    return fields


def _models_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("run_ts", pa.string()),
            pa.field("dt", pa.string()),
            pa.field("id", pa.string()),
            pa.field("canonical_slug", pa.string()),
            pa.field("name", pa.string()),
            pa.field("author", pa.string()),
            pa.field("created", pa.int64()),
            pa.field("context_length", pa.int64()),
            pa.field("modality", pa.string()),
            pa.field("tokenizer", pa.string()),
            pa.field("input_modalities", pa.list_(pa.string())),
            pa.field("output_modalities", pa.list_(pa.string())),
            pa.field("top_context_length", pa.int64()),
            pa.field("top_max_completion_tokens", pa.int64()),
            pa.field("is_moderated", pa.bool_()),
            pa.field("supported_parameters", pa.list_(pa.string())),
            pa.field("expiration_date", pa.string()),
            pa.field("hugging_face_id", pa.string()),
            pa.field("record_json", pa.string()),
            *_price_schema_fields(),
        ]
    )


def _endpoints_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("run_ts", pa.string()),
            pa.field("dt", pa.string()),
            pa.field("endpoint_fingerprint", pa.string()),
            pa.field("model_id", pa.string()),
            pa.field("model_name", pa.string()),
            pa.field("endpoint_name", pa.string()),
            pa.field("provider_name", pa.string()),
            pa.field("tag", pa.string()),
            pa.field("quantization", pa.string()),
            pa.field("context_length", pa.int64()),
            pa.field("max_completion_tokens", pa.int64()),
            pa.field("max_prompt_tokens", pa.int64()),
            pa.field("status", pa.int64()),
            pa.field("uptime_last_5m", pa.float64()),
            pa.field("uptime_last_30m", pa.float64()),
            pa.field("uptime_last_1d", pa.float64()),
            pa.field("latency_last_30m", pa.float64()),
            pa.field("throughput_last_30m", pa.float64()),
            pa.field("supports_implicit_caching", pa.bool_()),
            pa.field("supported_parameters", pa.list_(pa.string())),
            pa.field("record_json", pa.string()),
            *_price_schema_fields(),
        ]
    )


def _providers_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("run_ts", pa.string()),
            pa.field("dt", pa.string()),
            pa.field("slug", pa.string()),
            pa.field("name", pa.string()),
            pa.field("headquarters", pa.string()),
            pa.field("datacenters", pa.list_(pa.string())),
            pa.field("privacy_policy_url", pa.string()),
            pa.field("terms_of_service_url", pa.string()),
            pa.field("status_page_url", pa.string()),
            pa.field("record_json", pa.string()),
        ]
    )
