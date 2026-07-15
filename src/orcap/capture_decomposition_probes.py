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
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from .capture_api import write_partition
from .capture_probes import (
    MODELS_URL,
    QUOTE_CAP_INPUT_TOKENS,
    RANKINGS_URL,
    REQUEST_TIMEOUT_MS,
    _send_probe,
    hot_model_ids,
    probe_record,
    quoted_endpoints_audit,
    quoted_probe_cost_cap,
)
from .config import CURATED_DIR, dt_partition, run_timestamp
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

ELIGIBILITY_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("observed_at", pa.string()),
        ("study_id", pa.string()),
        ("ranking_position", pa.int32()),
        ("evaluation_order", pa.int32()),
        ("model_id", pa.string()),
        ("endpoint_fetch_status", pa.string()),
        ("endpoint_http_status", pa.int32()),
        ("raw_endpoint_count", pa.int32()),
        ("positive_quote_count", pa.int32()),
        ("distinct_provider_count", pa.int32()),
        ("eligible", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("provider_order_sha256", pa.string()),
        ("public_min_completion_price", pa.float64()),
        ("public_max_completion_price", pa.float64()),
        ("public_quote_cost_cap_usd", pa.float64()),
        ("quote_cap_input_tokens", pa.int32()),
        ("request_timeout_ms", pa.float64()),
        ("block_id", pa.string()),
        ("run_seed", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


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
            "provider_only": None,
            "allow_fallbacks": True,
        },
        {
            "policy": "price_only_no_fallback",
            "provider_order": [order[0]],
            "provider_only": [order[0]],
            "allow_fallbacks": False,
        },
        {
            "policy": "price_order_fallback",
            "provider_order": order,
            "provider_only": order,
            "allow_fallbacks": True,
        },
    ]
    rng.shuffle(tasks)
    return tasks


def write_eligibility_audit(
    records: list[dict[str, Any]],
    *,
    run_ts: str,
    dt: str | None = None,
    curated_dir: Path = CURATED_DIR,
) -> Path | None:
    """Persist the outcome-free H81 candidate funnel with a stable schema."""
    if not records:
        return None
    dt = dt or dt_partition()
    rows = [
        record
        | {
            "payload_retained": False,
            "run_ts": run_ts,
            "dt": dt,
        }
        for record in records
    ]
    return write_partition(
        pa.Table.from_pylist(rows, schema=ELIGIBILITY_SCHEMA),
        "router_probe_eligibility",
        run_ts,
        dt,
        curated_dir,
    )


def run_decomposition_probes(
    model_ids: list[str] | None = None,
    *,
    eligibility_records: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seed_text = os.environ.get("ORCAP_DECOMP_RANDOMIZATION_SEED")
    run_seed = int(seed_text, 0) if seed_text else secrets.randbits(64)
    rng = random.Random(run_seed)
    run_id = run_id or run_timestamp()
    with httpx.Client(timeout=60) as client:
        if model_ids is None:
            rankings = client.get(RANKINGS_URL).json()
            models = client.get(MODELS_URL).json()
            ranked = hot_model_ids(rankings, models, n=MODEL_OFFSET + MODEL_COUNT)
            candidates = list(
                enumerate(
                    ranked[MODEL_OFFSET : MODEL_OFFSET + MODEL_COUNT],
                    start=MODEL_OFFSET + 1,
                )
            )
        else:
            candidates = list(enumerate(list(model_ids[:MODEL_COUNT]), start=MODEL_OFFSET + 1))
        rng.shuffle(candidates)

        for evaluation_order, (ranking_position, model_id) in enumerate(candidates):
            endpoints, endpoint_audit = quoted_endpoints_audit(client, model_id)
            provider_order = public_provider_order(endpoints)
            order_text = json.dumps(provider_order, separators=(",", ":"))
            order_hash = hashlib.sha256(order_text.encode()).hexdigest()
            eligible = len(provider_order) >= 2
            if endpoint_audit["endpoint_fetch_status"] != "ok":
                exclusion_reason = str(endpoint_audit["endpoint_fetch_status"])
            elif not eligible:
                exclusion_reason = "fewer_than_two_distinct_positive_price_providers"
            else:
                exclusion_reason = "eligible"
            input_complete = bool(endpoints) and all(
                endpoint.get("input_price") is not None for endpoint in endpoints
            )
            quote_cost_cap = (
                max(float(quoted_probe_cost_cap(endpoint)) for endpoint in endpoints)
                if input_complete
                else None
            )
            block_id = f"{STUDY_ID}|{run_id}|{model_id}" if eligible else None
            if eligibility_records is not None:
                eligibility_records.append(
                    {
                        "run_id": run_id,
                        "observed_at": run_timestamp(),
                        "study_id": STUDY_ID,
                        "ranking_position": ranking_position,
                        "evaluation_order": evaluation_order,
                        "model_id": model_id,
                        **endpoint_audit,
                        "eligible": eligible,
                        "exclusion_reason": exclusion_reason,
                        "provider_order_sha256": order_hash,
                        "public_min_completion_price": (
                            float(endpoints[0]["price"]) if endpoints else None
                        ),
                        "public_max_completion_price": (
                            max(float(endpoint["price"]) for endpoint in endpoints)
                            if endpoints
                            else None
                        ),
                        "public_quote_cost_cap_usd": quote_cost_cap,
                        "quote_cap_input_tokens": QUOTE_CAP_INPUT_TOKENS,
                        "request_timeout_ms": REQUEST_TIMEOUT_MS,
                        "block_id": block_id,
                        "run_seed": str(run_seed),
                    }
                )
            if not eligible:
                log.warning(
                    "skip decomposition model=%s rank=%d reason=%s",
                    model_id,
                    ranking_position,
                    exclusion_reason,
                )
                continue
            block_seed = rng.getrandbits(64)
            tasks = decomposition_tasks(endpoints, random.Random(block_seed))
            cheapest_price = float(endpoints[0]["price"])

            for position, task in enumerate(tasks):
                order = task["provider_order"]
                first_provider = order[0] if order else None
                observed_at = run_timestamp()
                completion, generation, error, status = _send_probe(
                    client,
                    model_id,
                    provider_order=order,
                    provider_only=task["provider_only"],
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
                        "public_quote_cost_cap_usd": quote_cost_cap,
                        "quote_cap_input_tokens": QUOTE_CAP_INPUT_TOKENS,
                        "request_timeout_ms": REQUEST_TIMEOUT_MS,
                        "ranking_position": ranking_position,
                        "eligibility_run_id": run_id,
                        "requested_order_length": len(order) if order else 0,
                        "provider_only_count": len(task["provider_only"] or []),
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
    run_id = run_timestamp()
    eligibility_records: list[dict[str, Any]] = []
    records = run_decomposition_probes(
        eligibility_records=eligibility_records,
        run_id=run_id,
    )
    out = write_attempts(records, run_ts=run_id)
    eligibility_out = write_eligibility_audit(eligibility_records, run_ts=run_id)
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
                "path": str(out) if out else None,
                "eligibility_candidates": len(eligibility_records),
                "eligibility_eligible": sum(
                    1 for record in eligibility_records if record["eligible"]
                ),
                "eligibility_path": (str(eligibility_out) if eligibility_out else None),
            }
        )
    )


if __name__ == "__main__":
    main()
