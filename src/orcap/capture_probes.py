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
import random
import secrets
import time
from typing import Any

import httpx

from .config import API_V1, BASE_URL, run_timestamp
from .route_telemetry import write_attempts

log = logging.getLogger(__name__)

# v1 always sent the default policy first and therefore confounded policy with
# within-block order.  v2 randomizes the full four-policy crossover and records
# the assignment.  The primary estimand uses only first-position attempts, so
# it remains identified even if a probe changes the rate limit faced by later
# probes in the same block.
STUDY_ID = "openrouter-routing-crossover-v2"
SCENARIO = "probe_short_chat"
PROBE_PROMPT = "Reply with the single word: pong"
MAX_PROBES = int(os.environ.get("ORCAP_PROBE_MAX_MODELS", "8"))
# For the first N probed models, also send pinned-provider one-token probes
# (cheapest, 2nd-cheapest, one random) — the firmness / tokenizer-inflation /
# neutrality feed. ~12 extra probes/hour, still cents per month.
PINNED_MODELS = int(os.environ.get("ORCAP_PROBE_PINNED_MODELS", "4"))
GENERATION_POLL_ATTEMPTS = 5
GENERATION_POLL_SECONDS = 2.0
REQUEST_TIMEOUT_MS = 60_000.0
QUOTE_CAP_INPUT_TOKENS = 64
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
    requested_provider: str | None = None,
    policy: str = "openrouter_default",
    study_id: str = STUDY_ID,
    scenario: str = SCENARIO,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map one probe's API responses into the redacted attempt contract."""
    gen = (generation or {}).get("data") or {}
    usage = (completion or {}).get("usage") or {}  # inline accounting fallback
    event_id = (completion or {}).get("id") or f"{observed_at}|{model_id}|{requested_provider}"
    latency = gen.get("latency")
    return {
        "event_id": str(event_id),
        "observed_at": observed_at,
        "router": "openrouter",
        "source": "openrouter_generation",
        "study_id": study_id,
        "request_ref": (completion or {}).get("id"),
        "model_id": model_id,
        "requested_provider": requested_provider,
        "selected_provider": gen.get("provider_name") or (completion or {}).get("provider"),
        "attempt_index": 0,
        "outcome": "succeeded" if completion and not error else "failed",
        "retry_reason": error,
        "fallback_triggered": False,
        "policy": policy,
        "input_tokens": gen.get("native_tokens_prompt") or usage.get("prompt_tokens"),
        "output_tokens": gen.get("native_tokens_completion") or usage.get("completion_tokens"),
        "cost_usd": gen.get("total_cost") or usage.get("cost"),
        "latency_ms": latency,
        "metadata": {
            "scenario": scenario,
            "status_code": status_code,
            "request_type": "probe",
            **(extra_metadata or {}),
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


def _send_probe(
    client: httpx.Client,
    model_id: str,
    provider: str | None = None,
    *,
    provider_order: list[str] | None = None,
    provider_only: list[str] | None = None,
    allow_fallbacks: bool = False,
) -> tuple[dict | None, dict | None, str | None, int | None]:
    completion = generation = None
    error = None
    status = None
    body: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": PROBE_PROMPT}],
        "max_tokens": 1,
        "temperature": 0,
        "usage": {"include": True},
    }
    if provider is not None and provider_order is not None:
        raise ValueError("provide either provider or provider_order, not both")
    order = provider_order if provider_order is not None else ([provider] if provider else None)
    if order is not None or provider_only is not None:
        body["provider"] = {"allow_fallbacks": allow_fallbacks}
        if order is not None:
            body["provider"]["order"] = order
        if provider_only is not None:
            body["provider"]["only"] = provider_only
    try:
        r = client.post(CHAT_URL, headers=_headers(), json=body)
        status = r.status_code
        if r.status_code == 200:
            completion = r.json()
            if completion.get("id"):
                generation = _fetch_generation(client, completion["id"])
        else:
            error = f"http_{r.status_code}"
    except httpx.HTTPError as exc:
        error = type(exc).__name__
    return completion, generation, error, status


def quoted_endpoints_audit(
    client: httpx.Client, model_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch positive public quotes and return an outcome-free fetch audit."""
    try:
        r = client.get(f"{API_V1}/models/{model_id}/endpoints")
        if r.status_code != 200:
            return [], {
                "endpoint_fetch_status": f"http_{r.status_code}",
                "endpoint_http_status": int(r.status_code),
                "raw_endpoint_count": 0,
                "positive_quote_count": 0,
                "distinct_provider_count": 0,
            }
    except httpx.HTTPError as exc:
        return [], {
            "endpoint_fetch_status": type(exc).__name__,
            "endpoint_http_status": None,
            "raw_endpoint_count": 0,
            "positive_quote_count": 0,
            "distinct_provider_count": 0,
        }

    def _sf(x: Any) -> float | None:
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    raw = (r.json().get("data") or {}).get("endpoints") or []
    eps = []
    for ep in raw:
        pricing = ep.get("pricing") or {}
        price = _sf(pricing.get("completion"))
        input_price = _sf(pricing.get("prompt"))
        name = ep.get("provider_name")
        if name and price is not None and price > 0:
            eps.append(
                {
                    "provider": name,
                    "price": price,
                    "input_price": input_price,
                }
            )
    eps = sorted(eps, key=lambda e: e["price"])
    return eps, {
        "endpoint_fetch_status": "ok",
        "endpoint_http_status": int(r.status_code),
        "raw_endpoint_count": len(raw),
        "positive_quote_count": len(eps),
        "distinct_provider_count": len({str(endpoint["provider"]) for endpoint in eps}),
    }


def _quoted_endpoints(client: httpx.Client, model_id: str) -> list[dict[str, Any]]:
    """Public endpoint list with completion quotes, cheapest first."""
    endpoints, _ = quoted_endpoints_audit(client, model_id)
    return endpoints


def _pinned_targets(eps: list[dict[str, Any]], rng: random.Random) -> list[tuple[str, dict]]:
    """(policy, endpoint) picks: cheapest, second-cheapest, one random other."""
    if len(eps) < 2:
        return []
    picks = [("pinned_cheapest", eps[0]), ("pinned_second", eps[1])]
    rest = eps[2:]
    if rest:
        picks.append(("pinned_random", rng.choice(rest)))
    return picks


def quoted_probe_cost_cap(endpoint: dict[str, Any]) -> float | None:
    """Conservative quote-implied cap for the fixed prompt and one output token."""
    input_price = endpoint.get("input_price")
    completion_price = endpoint.get("price")
    if input_price is None or completion_price is None:
        return None
    return float(input_price) * QUOTE_CAP_INPUT_TOKENS + float(completion_price)


def randomized_probe_tasks(
    eps: list[dict[str, Any]], rng: random.Random
) -> list[tuple[str, dict[str, Any] | None]]:
    """Return default plus pinned policies in a uniformly random order.

    Endpoint selection happens before the shuffle.  This keeps the treatment
    arms fixed within a block while making policy position auditable from the
    published seed and metadata.
    """
    tasks: list[tuple[str, dict[str, Any] | None]] = [("openrouter_default", None)]
    tasks.extend(_pinned_targets(eps, rng))
    rng.shuffle(tasks)
    return tasks


def run_probes(model_ids: list[str] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seed_text = os.environ.get("ORCAP_PROBE_RANDOMIZATION_SEED")
    run_seed = int(seed_text, 0) if seed_text else secrets.randbits(64)
    rng = random.Random(run_seed)
    run_id = run_timestamp()
    with httpx.Client(timeout=60) as client:
        if model_ids is None:
            rankings = client.get(RANKINGS_URL).json()
            models = client.get(MODELS_URL).json()
            model_ids = hot_model_ids(rankings, models)

        # Choose the hot-model study set before randomizing model order.  This
        # avoids systematically exposing the same model to earlier clock time.
        selected_models = list(model_ids[:MAX_PROBES])
        pinned_models = set(selected_models[:PINNED_MODELS])
        rng.shuffle(selected_models)
        for model_id in selected_models:
            eps = _quoted_endpoints(client, model_id) if model_id in pinned_models else []
            block_seed = rng.getrandbits(64)
            block_rng = random.Random(block_seed)
            tasks = (
                randomized_probe_tasks(eps, block_rng)
                if model_id in pinned_models and len(eps) >= 2
                else [("openrouter_default", None)]
            )
            block_id = f"{STUDY_ID}|{run_id}|{model_id}"
            for position, (policy, ep) in enumerate(tasks):
                provider = ep["provider"] if ep is not None else None
                obs = run_timestamp()
                completion, generation, error, status = _send_probe(
                    client, model_id, provider=provider
                )
                quote_metadata: dict[str, Any] = {}
                if ep is not None:
                    quote_metadata = {
                        "quoted_price_completion": ep["price"],
                        "public_quote_cost_cap_usd": quoted_probe_cost_cap(ep),
                        "quote_cap_input_tokens": QUOTE_CAP_INPUT_TOKENS,
                        "quoted_rank": next(
                            (k for k, endpoint in enumerate(eps) if endpoint is ep), None
                        ),
                        "n_quoted": len(eps),
                    }
                records.append(
                    probe_record(
                        model_id,
                        completion,
                        generation,
                        observed_at=obs,
                        error=error,
                        status_code=status,
                        requested_provider=provider,
                        policy=policy,
                        extra_metadata={
                            "block_id": block_id,
                            "block_policy_count": len(tasks),
                            "policy_order": position,
                            "block_seed": block_seed,
                            "run_seed": run_seed,
                            "assignment_probability_first": 1.0 / len(tasks),
                            "randomized_order": len(tasks) > 1,
                            "primary_estimand": "first_position_no_prior_probe",
                            "request_timeout_ms": REQUEST_TIMEOUT_MS,
                            "n_quoted": len(eps),
                            **quote_metadata,
                        },
                    )
                )
                log.info(
                    "probe block=%s position=%d policy=%s model=%s provider=%s outcome=%s",
                    block_id,
                    position,
                    policy,
                    model_id,
                    provider,
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
