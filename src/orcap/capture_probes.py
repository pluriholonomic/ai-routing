"""Realized-routing probes: tiny owned requests through OpenRouter's default policy.

Each run sends a bounded number of one-token completions (no provider
preference, temperature 0) against the hottest models, then fetches the
generation metadata to learn which provider the router actually selected,
at what latency and cost. Records land in ``router_route_attempts`` via the
redacted telemetry contract — prompts and completions are never persisted.

Cost is bounded by construction: MAX_PROBES requests × (a ~10-token prompt +
1 output token). Even at frontier-model prices one run costs well under a
cent; the hourly panel costs a few dollars per month.

This measures the router's *own* selection for our probe flow. It does not
observe other customers' traffic, provider queue state, or market-wide
allocation; analyses must treat it as a realized sample of the default
policy, not routed volume.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from .config import BASE_URL, run_timestamp
from .route_telemetry import write_attempts

log = logging.getLogger(__name__)

STUDY_ID = "openrouter-default-probes-v1"
SCENARIO = "probe_short_chat"
PROBE_PROMPT = "Reply with the single word: pong"
MAX_PROBES = int(os.environ.get("ORCAP_PROBE_MAX_MODELS", "8"))
GENERATION_POLL_ATTEMPTS = 5
GENERATION_POLL_SECONDS = 2.0
RANKINGS_URL = f"{BASE_URL}/api/frontend/v1/rankings/models?view=week"
MODELS_URL = f"{BASE_URL}/api/v1/models"
CHAT_URL = f"{BASE_URL}/api/v1/chat/completions"
GENERATION_URL = f"{BASE_URL}/api/v1/generation"


def hot_model_ids(rankings: Any, models: Any, n: int = MAX_PROBES) -> list[str]:
    """Top-n rankings models resolved to chat-API model ids, skipping variants."""
    catalog = {}
    for m in (models or {}).get("data") or []:
        if m.get("id") and ":" not in m["id"]:
            catalog[m.get("canonical_slug") or m["id"]] = m["id"]
            catalog[m["id"]] = m["id"]
    totals: dict[str, int] = {}
    for r in (rankings or {}).get("data") or []:
        slug = r.get("model_permaslug")
        if slug:
            tokens = (r.get("total_prompt_tokens") or 0) + (r.get("total_completion_tokens") or 0)
            totals[slug] = totals.get(slug, 0) + tokens
    out: list[str] = []
    for slug, _ in sorted(totals.items(), key=lambda kv: -kv[1]):
        model_id = catalog.get(slug)
        if model_id and model_id not in out:
            out.append(model_id)
        if len(out) >= n:
            break
    return out


def probe_record(
    model_id: str,
    completion: dict[str, Any] | None,
    generation: dict[str, Any] | None,
    *,
    observed_at: str,
    error: str | None = None,
    status_code: int | None = None,
) -> dict[str, Any]:
    """Map one probe's API responses into the redacted attempt contract."""
    gen = (generation or {}).get("data") or {}
    usage = (completion or {}).get("usage") or {}  # inline accounting fallback
    event_id = (completion or {}).get("id") or f"{observed_at}|{model_id}"
    latency = gen.get("latency")
    return {
        "event_id": str(event_id),
        "observed_at": observed_at,
        "router": "openrouter",
        "source": "openrouter_generation",
        "study_id": STUDY_ID,
        "request_ref": (completion or {}).get("id"),
        "model_id": model_id,
        "requested_provider": None,  # default routing: the router's own choice
        "selected_provider": gen.get("provider_name") or (completion or {}).get("provider"),
        "attempt_index": 0,
        "outcome": "succeeded" if completion and not error else "failed",
        "retry_reason": error,
        "fallback_triggered": False,
        "policy": "openrouter_default",
        "input_tokens": gen.get("native_tokens_prompt") or usage.get("prompt_tokens"),
        "output_tokens": gen.get("native_tokens_completion") or usage.get("completion_tokens"),
        "cost_usd": gen.get("total_cost") or usage.get("cost"),
        "latency_ms": latency,
        "metadata": {
            "scenario": SCENARIO,
            "status_code": status_code,
            "request_type": "probe",
        },
    }


def _headers() -> dict[str, str]:
    key = os.environ["OPENROUTER_API_KEY"]
    return {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://github.com/pluriholonomic/ai-routing",
        "X-Title": "orcap realized-routing probes",
    }


def _fetch_generation(client: httpx.Client, generation_id: str) -> dict[str, Any] | None:
    """Generation metadata is written asynchronously; poll briefly."""
    for _ in range(GENERATION_POLL_ATTEMPTS):
        time.sleep(GENERATION_POLL_SECONDS)
        r = client.get(GENERATION_URL, params={"id": generation_id}, headers=_headers())
        if r.status_code == 200:
            return r.json()
    log.warning("generation metadata unavailable for %s", generation_id)
    return None


def run_probes(model_ids: list[str] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with httpx.Client(timeout=60) as client:
        if model_ids is None:
            rankings = client.get(RANKINGS_URL).json()
            models = client.get(MODELS_URL).json()
            model_ids = hot_model_ids(rankings, models)
        for model_id in model_ids[:MAX_PROBES]:
            observed_at = run_timestamp()
            completion = generation = None
            error = None
            status = None
            try:
                r = client.post(
                    CHAT_URL,
                    headers=_headers(),
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": PROBE_PROMPT}],
                        "max_tokens": 1,
                        "temperature": 0,
                        "usage": {"include": True},
                    },
                )
                status = r.status_code
                if r.status_code == 200:
                    completion = r.json()
                    if completion.get("id"):
                        generation = _fetch_generation(client, completion["id"])
                else:
                    error = f"http_{r.status_code}"
            except httpx.HTTPError as exc:
                error = type(exc).__name__
            records.append(
                probe_record(
                    model_id,
                    completion,
                    generation,
                    observed_at=observed_at,
                    error=error,
                    status_code=status,
                )
            )
            log.info(
                "probe %s -> provider=%s outcome=%s",
                model_id,
                records[-1]["selected_provider"],
                records[-1]["outcome"],
            )
    return records


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    records = run_probes()
    out = write_attempts(records)
    selected = sum(1 for r in records if r["selected_provider"])
    print(
        json.dumps(
            {
                "probes": len(records),
                "with_selected_provider": selected,
                "total_cost_usd": sum(r["cost_usd"] or 0 for r in records),
                "path": str(out),
            }
        )
    )


if __name__ == "__main__":
    main()
