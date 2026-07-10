"""Canonical configuration snapshots for account-configured routers.

Cloudflare, Portkey, and LiteLLM are not assumed to share a default routing
algorithm.  Their owners import a redacted, normalized policy document, which
is then replayed exactly by the shadow engine.  Credentials and native config
exports remain outside this repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, dt_partition, run_timestamp
from .router_registry import router_spec

POLICY_TYPES = {
    "ordered_failover",
    "weighted",
    "inverse_square_price",
    "lowest_cost",
    "highest_throughput",
}
ACCOUNT_CONFIGURED_ROUTERS = {"cloudflare_ai_gateway", "portkey", "litellm"}
FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "completion",
    "messages",
    "prompt",
    "raw_request",
    "raw_response",
    "secret",
    "token",
}


def _forbidden_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = {str(key).lower() for key in value}.intersection(FORBIDDEN_KEYS)
        for nested in value.values():
            found |= _forbidden_keys(nested)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for nested in value:
            found |= _forbidden_keys(nested)
        return found
    return set()


def normalize_policy_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the portable redacted policy export.

    Expected shape::

      {"router": "cloudflare_ai_gateway", "config_id": "...",
       "observed_at": "...", "policies": [{"model_id": "...",
       "policy_type": "ordered_failover", "providers": [{"name": "...",
       "order": 1, "weight": 1.0}]}]}
    """
    forbidden = sorted(_forbidden_keys(document))
    if forbidden:
        raise ValueError(
            "router policy document contains sensitive/payload keys: " + ", ".join(forbidden)
        )
    router = str(document.get("router") or "")
    if router not in ACCOUNT_CONFIGURED_ROUTERS:
        raise ValueError("router policy import supports Cloudflare, Portkey, or LiteLLM only")
    router_spec(router)
    config_id = str(document.get("config_id") or "")
    observed_at = str(document.get("observed_at") or "")
    if not config_id or not observed_at:
        raise ValueError("router policy document requires config_id and observed_at")
    rows = []
    for policy in document.get("policies") or []:
        if not isinstance(policy, dict):
            raise ValueError("router policy entries must be objects")
        model_id = str(policy.get("model_id") or "")
        policy_type = str(policy.get("policy_type") or "")
        if not model_id or policy_type not in POLICY_TYPES:
            raise ValueError("each policy needs model_id and a supported policy_type")
        providers = policy.get("providers") or []
        if not providers:
            raise ValueError("each policy needs at least one redacted provider entry")
        for default_order, provider in enumerate(providers, start=1):
            if not isinstance(provider, dict) or not provider.get("name"):
                raise ValueError("policy provider entries require name")
            order = provider.get("order", default_order)
            try:
                order = int(order)
            except (TypeError, ValueError) as exc:
                raise ValueError("provider order must be an integer") from exc
            if order < 1:
                raise ValueError("provider order must be positive")
            weight = provider.get("weight")
            if weight is not None:
                try:
                    weight = float(weight)
                except (TypeError, ValueError) as exc:
                    raise ValueError("provider weight must be numeric") from exc
                if weight < 0:
                    raise ValueError("provider weight must be non-negative")
            rows.append(
                {
                    "router": router,
                    "config_id": config_id,
                    "observed_at": observed_at,
                    "model_id": model_id,
                    "policy_type": policy_type,
                    "provider_name": str(provider["name"]),
                    "provider_order": order,
                    "provider_weight": weight,
                    "allow_fallbacks": bool(policy.get("allow_fallbacks", True)),
                    "config_version": policy.get("config_version"),
                    "metadata_json": json.dumps(
                        policy.get("metadata") or {}, separators=(",", ":"), sort_keys=True
                    ),
                    "payload_retained": False,
                }
            )
    if not rows:
        raise ValueError("router policy document contains no policies")
    keys = [
        (row["router"], row["config_id"], row["model_id"], row["provider_name"])
        for row in rows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("router policy document repeats a provider within one config/model")
    return rows


def load_policy_document(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"router policy file is not valid JSON: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError("router policy file must contain one JSON object")
    return document


def write_policy_snapshot(
    document: dict[str, Any],
    *,
    run_ts: str | None = None,
    dt: str | None = None,
    curated_dir: Path = CURATED_DIR,
) -> Path:
    rows = normalize_policy_document(document)
    run_ts, dt = run_ts or run_timestamp(), dt or dt_partition()
    for row in rows:
        row["run_ts"] = run_ts
        row["dt"] = dt
    return write_partition(
        pa.Table.from_pylist(rows), "router_policy_snapshots", run_ts, dt, curated_dir
    )
