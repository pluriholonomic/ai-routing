"""Public Hugging Face Inference Providers quote/performance capture.

This is a cross-router comparator, not a routed-volume feed.  The public
``/v1/models`` response exposes a provider surface (price, latency,
throughput, context, and selected capabilities) but no market-wide request
counts or route-decision tape.  We preserve the raw response and explicitly
label all derived allocation rows as simulations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .routing_simulation import SCENARIOS, RoutingScenario

log = logging.getLogger(__name__)

HF_INFERENCE_PROVIDERS_MODELS_URL = "https://router.huggingface.co/v1/models"
ELIGIBILITY_BASIS = (
    "public Hugging Face provider metadata; status=live where reported; does not observe "
    "the router's private live-health state, fallback chain, or realized selection"
)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _model_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    for model in (body or {}).get("data") or []:
        if not isinstance(model, dict) or not model.get("id"):
            continue
        architecture = model.get("architecture") or {}
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "router": "huggingface_inference_providers",
                "model_id": model["id"],
                "model_created": model.get("created"),
                "owned_by": model.get("owned_by"),
                "input_modalities": architecture.get("input_modalities") or [],
                "output_modalities": architecture.get("output_modalities") or [],
                "provider_count": len(model.get("providers") or []),
                "record_json": _json(model),
            }
        )
    return rows


def provider_endpoint_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize the public model/provider surface without inventing usage.

    Hugging Face reports price as USD per million tokens.  ``record_json``
    retains both the model and provider object because provider fields are
    intentionally sparse for some listings.
    """
    rows = []
    for model in (body or {}).get("data") or []:
        if not isinstance(model, dict) or not model.get("id"):
            continue
        architecture = model.get("architecture") or {}
        for provider in model.get("providers") or []:
            if not isinstance(provider, dict) or not provider.get("provider"):
                continue
            pricing = provider.get("pricing") or {}
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "router": "huggingface_inference_providers",
                    "model_id": model["id"],
                    "model_created": model.get("created"),
                    "owned_by": model.get("owned_by"),
                    "input_modalities": architecture.get("input_modalities") or [],
                    "output_modalities": architecture.get("output_modalities") or [],
                    "provider_name": provider["provider"],
                    "status": provider.get("status"),
                    "context_length": provider.get("context_length"),
                    "price_input_usd_per_mtok": _float(pricing.get("input")),
                    "price_output_usd_per_mtok": _float(pricing.get("output")),
                    "is_free": provider.get("is_free"),
                    "supports_tools": provider.get("supports_tools"),
                    "supports_structured_output": provider.get("supports_structured_output"),
                    "first_token_latency_ms": _float(provider.get("first_token_latency_ms")),
                    "throughput_tps": _float(provider.get("throughput")),
                    "is_model_author": provider.get("is_model_author"),
                    "metric_definition": (
                        "Public Hugging Face Inference Providers listing: quoted provider "
                        "price/performance metadata, not requests, tokens consumed, or fills"
                    ),
                    "record_json": _json({"model": model, "provider": provider}),
                }
            )
    return rows


def _meets_scenario(row: dict[str, Any], scenario: RoutingScenario) -> bool:
    if row.get("status") not in {None, "live"}:
        return False
    context = _float(row.get("context_length"))
    if context is not None and context < scenario.input_tokens + scenario.output_tokens:
        return False
    if "tools" in scenario.required_parameters and row.get("supports_tools") is not True:
        return False
    if (
        "response_format" in scenario.required_parameters
        and row.get("supports_structured_output") is not True
    ):
        return False
    return True


def _quote_cost(row: dict[str, Any], scenario: RoutingScenario) -> float | None:
    """Return the public per-request cost implied by USD-per-million quotes."""
    pin = _float(row.get("price_input_usd_per_mtok"))
    pout = _float(row.get("price_output_usd_per_mtok"))
    if pin is None or pout is None or pin < 0 or pout < 0:
        return None
    return (pin * scenario.input_tokens + pout * scenario.output_tokens) / 1_000_000


def _policy_rows_for(
    candidates: list[dict[str, Any]],
    *,
    run_ts: str,
    dt: str,
    model_id: str,
    scenario: RoutingScenario,
    policy: str,
    score_name: str,
    descending: bool = False,
) -> list[dict[str, Any]]:
    eligible = [
        candidate
        for candidate in candidates
        if _float(candidate.get(score_name)) is not None
        and math.isfinite(float(candidate[score_name]))
    ]
    if not eligible:
        return []
    eligible.sort(key=lambda row: float(row[score_name]), reverse=descending)
    best = float(eligible[0][score_name])
    winners = [
        row
        for row in eligible
        if math.isclose(float(row[score_name]), best, rel_tol=1e-12, abs_tol=1e-15)
    ]
    rows = []
    for rank, row in enumerate(eligible, 1):
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "router": "huggingface_inference_providers",
                "policy": policy,
                "eligibility_basis": ELIGIBILITY_BASIS,
                "model_id": model_id,
                "scenario": scenario.name,
                "input_tokens": scenario.input_tokens,
                "output_tokens": scenario.output_tokens,
                "required_parameters": ",".join(scenario.required_parameters),
                "provider_name": row["provider_name"],
                "eligible_provider_count": len(eligible),
                "provider_rank": rank,
                "policy_score": float(row[score_name]),
                "policy_score_field": score_name,
                "expected_quote_usd": row["expected_quote_usd"],
                "throughput_tps": row.get("throughput_tps"),
                "first_token_latency_ms": row.get("first_token_latency_ms"),
                "simulated_route_share": 1.0 / len(winners) if row in winners else 0.0,
            }
        )
    return rows


def policy_simulation_rows(
    endpoint_rows: list[dict[str, Any]], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Derive public cheapest/fastest policy surfaces.

    ``cheapest`` is the exact public minimum-quote calculation.  ``fastest``
    only ranks endpoints with a reported positive throughput, so it is called a
    public throughput proxy rather than a claim about hidden router state.
    """
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in endpoint_rows:
        by_model.setdefault(str(row["model_id"]), []).append(row)

    out: list[dict[str, Any]] = []
    for model_id, model_rows in by_model.items():
        for scenario in SCENARIOS:
            candidates = []
            for row in model_rows:
                if not _meets_scenario(row, scenario):
                    continue
                cost = _quote_cost(row, scenario)
                if cost is None:
                    continue
                candidate = dict(row)
                candidate["expected_quote_usd"] = cost
                candidates.append(candidate)
            if not candidates:
                continue

            out.extend(
                _policy_rows_for(
                    candidates,
                    run_ts=run_ts,
                    dt=dt,
                    model_id=model_id,
                    scenario=scenario,
                    policy="hf_cheapest_public_quote",
                    score_name="expected_quote_usd",
                )
            )
            out.extend(
                _policy_rows_for(
                    candidates,
                    run_ts=run_ts,
                    dt=dt,
                    model_id=model_id,
                    scenario=scenario,
                    policy="hf_fastest_reported_throughput",
                    score_name="throughput_tps",
                    descending=True,
                )
            )
    return out


async def capture_hf_router(
    raw_dir: Path = RAW_DIR, curated_dir: Path = CURATED_DIR
) -> dict[str, Any]:
    run_ts, dt = run_timestamp(), dt_partition()
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        body = await fetcher.get_json(HF_INFERENCE_PROVIDERS_MODELS_URL)
        write_raw(fetcher.records, "hf_inference_providers", raw_dir, run_ts, dt)
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise RuntimeError("Hugging Face Inference Providers /v1/models returned no model list")

    models = _model_rows(body, run_ts, dt)
    endpoints = provider_endpoint_rows(body, run_ts, dt)
    policy_rows = policy_simulation_rows(endpoints, run_ts, dt)
    if not models or not endpoints:
        raise RuntimeError(
            "Hugging Face Inference Providers /v1/models returned no provider surface"
        )
    write_partition(
        pa.Table.from_pylist(models), "hf_router_models_snapshots", run_ts, dt, curated_dir
    )
    write_partition(
        pa.Table.from_pylist(endpoints), "hf_router_endpoint_snapshots", run_ts, dt, curated_dir
    )
    if policy_rows:
        write_partition(
            pa.Table.from_pylist(policy_rows),
            "hf_router_policy_simulation",
            run_ts,
            dt,
            curated_dir,
        )
    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "models": len(models),
        "rows": len(endpoints),
        "policy_rows": len(policy_rows),
    }
    log.info("Hugging Face Inference Providers capture: %s", summary)
    return summary


async def capture_loop(samples: int, interval_seconds: float) -> list[dict[str, Any]]:
    if samples < 1:
        raise ValueError("samples must be positive")
    summaries = []
    for index in range(samples):
        started = time.monotonic()
        summaries.append(await capture_hf_router())
        if index < samples - 1:
            await asyncio.sleep(max(0.0, interval_seconds - (time.monotonic() - started)))
    return summaries


def main(samples: int = 1, interval_seconds: float = 900.0) -> list[dict[str, Any]]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(capture_loop(samples, interval_seconds))


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
