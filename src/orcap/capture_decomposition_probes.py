"""Randomized fallback-versus-selection decomposition probes.

This study is separate from the four-arm quote-firmness holdout.  It uses the
next two ranked models so it does not alter that experiment's treatment set.
Three policies share the same public quote snapshot:

* price_only_no_fallback: cheapest public provider, no fallback;
* price_order_fallback: all public providers in price order, fallback allowed;
* delegated_default: no provider restriction.

The first contrast isolates the option value of fallback while holding the
first provider fixed.  The second isolates the value of delegating selection
relative to an explicit public-price order with the same fallback permission.
Only randomized first-position requests are confirmatory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import secrets
from typing import Any

import httpx

from .capture_probes import (
    MODELS_URL,
    RANKINGS_URL,
    _quoted_endpoints,
    _send_probe,
    hot_model_ids,
    probe_record,
)
from .config import run_timestamp
from .route_telemetry import write_attempts

log = logging.getLogger(__name__)

STUDY_ID = "openrouter-fallback-selection-decomposition-v1"
SCENARIO = "probe_short_chat_decomposition"
POLICIES = (
    "delegated_default",
    "price_only_no_fallback",
    "price_order_fallback",
)
MODEL_OFFSET = int(os.environ.get("ORCAP_DECOMP_MODEL_OFFSET", "4"))
MODEL_COUNT = int(os.environ.get("ORCAP_DECOMP_MODEL_COUNT", "2"))


def public_provider_order(endpoints: list[dict[str, Any]]) -> list[str]:
    """Deduplicate provider identities while retaining cheapest-first order."""
    seen: set[str] = set()
    ordered = []
    for endpoint in endpoints:
        provider = str(endpoint["provider"])
        if provider not in seen:
            ordered.append(provider)
            seen.add(provider)
    return ordered


def decomposition_tasks(
    endpoints: list[dict[str, Any]], rng: random.Random
) -> list[dict[str, Any]]:
    """Build and uniformly permute the three prespecified policies."""
    order = public_provider_order(endpoints)
    if len(order) < 2:
        return []
    tasks = [
        {
            "policy": "delegated_default",
            "provider_order": None,
            "allow_fallbacks": True,
        },
        {
            "policy": "price_only_no_fallback",
            "provider_order": [order[0]],
            "allow_fallbacks": False,
        },
        {
            "policy": "price_order_fallback",
            "provider_order": order,
            "allow_fallbacks": True,
        },
    ]
    rng.shuffle(tasks)
    return tasks


def run_decomposition_probes(model_ids: list[str] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seed_text = os.environ.get("ORCAP_DECOMP_RANDOMIZATION_SEED")
    run_seed = int(seed_text, 0) if seed_text else secrets.randbits(64)
    rng = random.Random(run_seed)
    run_id = run_timestamp()
    with httpx.Client(timeout=60) as client:
        if model_ids is None:
            rankings = client.get(RANKINGS_URL).json()
            models = client.get(MODELS_URL).json()
            ranked = hot_model_ids(rankings, models, n=MODEL_OFFSET + MODEL_COUNT)
            model_ids = ranked[MODEL_OFFSET : MODEL_OFFSET + MODEL_COUNT]
        else:
            model_ids = list(model_ids[:MODEL_COUNT])
        rng.shuffle(model_ids)

        for model_id in model_ids:
            endpoints = _quoted_endpoints(client, model_id)
            provider_order = public_provider_order(endpoints)
            if len(provider_order) < 2:
                log.warning("skip decomposition model=%s: fewer than two quotes", model_id)
                continue
            block_seed = rng.getrandbits(64)
            tasks = decomposition_tasks(endpoints, random.Random(block_seed))
            block_id = f"{STUDY_ID}|{run_id}|{model_id}"
            order_text = json.dumps(provider_order, separators=(",", ":"))
            order_hash = hashlib.sha256(order_text.encode()).hexdigest()
            cheapest_price = float(endpoints[0]["price"])

            for position, task in enumerate(tasks):
                order = task["provider_order"]
                first_provider = order[0] if order else None
                observed_at = run_timestamp()
                completion, generation, error, status = _send_probe(
                    client,
                    model_id,
                    provider_order=order,
                    allow_fallbacks=bool(task["allow_fallbacks"]),
                )
                record = probe_record(
                    model_id,
                    completion,
                    generation,
                    observed_at=observed_at,
                    error=error,
                    status_code=status,
                    requested_provider=first_provider,
                    policy=str(task["policy"]),
                    study_id=STUDY_ID,
                    scenario=SCENARIO,
                    extra_metadata={
                        "block_id": block_id,
                        "block_policy_count": len(POLICIES),
                        "policy_order": position,
                        "block_seed": block_seed,
                        "run_seed": run_seed,
                        "assignment_probability_first": 1.0 / len(POLICIES),
                        "randomized_order": True,
                        "primary_estimand": "first_position_no_prior_probe",
                        "public_provider_order": provider_order,
                        "public_provider_order_sha256": order_hash,
                        "public_provider_count": len(provider_order),
                        "public_cheapest_provider": provider_order[0],
                        "public_cheapest_completion_price": cheapest_price,
                        "requested_order_length": len(order) if order else 0,
                        "allow_fallbacks": bool(task["allow_fallbacks"]),
                    },
                )
                if completion is None:
                    record["event_id"] = f"{block_id}|{position}|{task['policy']}"
                selected = record.get("selected_provider")
                record["fallback_triggered"] = bool(
                    first_provider and selected and selected != first_provider
                )
                records.append(record)
                log.info(
                    "decomposition block=%s position=%d policy=%s model=%s "
                    "requested=%s selected=%s outcome=%s",
                    block_id,
                    position,
                    task["policy"],
                    model_id,
                    first_provider,
                    selected,
                    record["outcome"],
                )
    return records


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    records = run_decomposition_probes()
    out = write_attempts(records)
    print(
        json.dumps(
            {
                "study_id": STUDY_ID,
                "probes": len(records),
                "blocks": len({record["metadata"]["block_id"] for record in records}),
                "with_selected_provider": sum(
                    1 for record in records if record["selected_provider"]
                ),
                "total_cost_usd": sum(record["cost_usd"] or 0 for record in records),
                "path": str(out),
            }
        )
    )


if __name__ == "__main__":
    main()
