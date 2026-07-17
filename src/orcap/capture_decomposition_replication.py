"""H95 fixed-horizon replication of fallback and delegated selection.

Each accepted run forms one randomized triplet from three competitively quoted,
Hugging Face-linked models ranked below the H80/H81 support.  The three H81
policies are assigned once each to first position within the triplet; all three
policies are still sent for every selected model.  The confirmatory horizon is
the first 120 fully planned triplets (360 first-position blocks, 120 per arm).

The Hugging Face link is an operational open-weight screen, not a license audit.
No prompt or completion payload is retained.
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
from .capture_decomposition_probes import POLICIES, public_provider_order
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

STUDY_ID = "openrouter-delegation-replication-v1"
SCENARIO = "probe_short_chat_decomposition_replication"
MIN_RANK = int(os.environ.get("ORCAP_REPLICATION_MIN_RANK", "7"))
MAX_RANK = int(os.environ.get("ORCAP_REPLICATION_MAX_RANK", "30"))
MODELS_PER_TRIPLET = 3
TARGET_TRIPLETS = 120

REPLICATION_ELIGIBILITY_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("observed_at", pa.string()),
        ("study_id", pa.string()),
        ("triplet_id", pa.string()),
        ("ranking_position", pa.int32()),
        ("model_id", pa.string()),
        ("hugging_face_id", pa.string()),
        ("open_weight_screen", pa.string()),
        ("endpoint_fetch_status", pa.string()),
        ("endpoint_http_status", pa.int32()),
        ("raw_endpoint_count", pa.int32()),
        ("positive_quote_count", pa.int32()),
        ("distinct_provider_count", pa.int32()),
        ("eligible", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("eligible_pool_size", pa.int32()),
        ("selected_for_triplet", pa.bool_()),
        ("selection_probability", pa.float64()),
        ("triplet_position", pa.int32()),
        ("assigned_first_policy", pa.string()),
        ("provider_order_sha256", pa.string()),
        ("public_min_completion_price", pa.float64()),
        ("public_max_completion_price", pa.float64()),
        ("public_quote_cost_cap_usd", pa.float64()),
        ("quote_cap_input_tokens", pa.int32()),
        ("request_timeout_ms", pa.float64()),
        ("block_id", pa.string()),
        ("block_seed", pa.string()),
        ("run_seed", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def ranked_open_weight_candidates(
    rankings: Any,
    models: Any,
    *,
    min_rank: int = MIN_RANK,
    max_rank: int = MAX_RANK,
) -> list[dict[str, Any]]:
    """Return ranked API ids with a nonempty OpenRouter Hugging Face link."""
    catalog = {
        str(model["id"]): model for model in (models or {}).get("data") or [] if model.get("id")
    }
    ranked = hot_model_ids(rankings, models, n=max_rank)
    candidates: list[dict[str, Any]] = []
    for ranking_position, model_id in enumerate(ranked, start=1):
        if ranking_position < min_rank:
            continue
        hugging_face_id = str(catalog.get(model_id, {}).get("hugging_face_id") or "").strip()
        if not hugging_face_id:
            continue
        candidates.append(
            {
                "ranking_position": ranking_position,
                "model_id": model_id,
                "hugging_face_id": hugging_face_id,
            }
        )
    return candidates


def tasks_with_assigned_first(
    endpoints: list[dict[str, Any]],
    assigned_first_policy: str,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Construct all policies while fixing the randomized first position."""
    order = public_provider_order(endpoints)
    if len(order) < 2 or assigned_first_policy not in POLICIES:
        return []
    by_policy = {
        "delegated_default": {
            "policy": "delegated_default",
            "provider_order": None,
            "provider_only": None,
            "allow_fallbacks": True,
        },
        "price_only_no_fallback": {
            "policy": "price_only_no_fallback",
            "provider_order": [order[0]],
            "provider_only": [order[0]],
            "allow_fallbacks": False,
        },
        "price_order_fallback": {
            "policy": "price_order_fallback",
            "provider_order": order,
            "provider_only": order,
            "allow_fallbacks": True,
        },
    }
    remaining = [policy for policy in POLICIES if policy != assigned_first_policy]
    rng.shuffle(remaining)
    return [by_policy[assigned_first_policy], *(by_policy[policy] for policy in remaining)]


def build_replication_plan(
    client: httpx.Client,
    *,
    run_id: str,
    run_seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Freeze eligibility, model selection, and blocked assignments pre-outcome."""
    rng = random.Random(run_seed)
    rankings = client.get(RANKINGS_URL).json()
    models = client.get(MODELS_URL).json()
    candidates = ranked_open_weight_candidates(rankings, models)
    audited: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for candidate in candidates:
        endpoints, endpoint_audit = quoted_endpoints_audit(client, candidate["model_id"])
        provider_order = public_provider_order(endpoints)
        order_hash = hashlib.sha256(
            json.dumps(provider_order, separators=(",", ":")).encode()
        ).hexdigest()
        is_eligible = endpoint_audit["endpoint_fetch_status"] == "ok" and len(provider_order) >= 2
        if endpoint_audit["endpoint_fetch_status"] != "ok":
            reason = str(endpoint_audit["endpoint_fetch_status"])
        elif len(provider_order) < 2:
            reason = "fewer_than_two_distinct_positive_price_providers"
        else:
            reason = "eligible"
        input_complete = bool(endpoints) and all(
            endpoint.get("input_price") is not None for endpoint in endpoints
        )
        quote_cost_cap = (
            max(float(quoted_probe_cost_cap(endpoint)) for endpoint in endpoints)
            if input_complete
            else None
        )
        row = {
            **candidate,
            **endpoint_audit,
            "eligible": is_eligible,
            "exclusion_reason": reason,
            "provider_order": provider_order,
            "provider_order_sha256": order_hash,
            "endpoints": endpoints,
            "public_min_completion_price": (float(endpoints[0]["price"]) if endpoints else None),
            "public_max_completion_price": (
                max(float(endpoint["price"]) for endpoint in endpoints) if endpoints else None
            ),
            "public_quote_cost_cap_usd": quote_cost_cap,
        }
        audited.append(row)
        if is_eligible:
            eligible.append(row)

    selected = rng.sample(eligible, MODELS_PER_TRIPLET) if len(eligible) >= 3 else []
    first_policies = list(POLICIES)
    rng.shuffle(first_policies)
    triplet_id = f"{STUDY_ID}|{run_id}" if selected else None
    selected_lookup: dict[str, tuple[int, str, int]] = {}
    plan: list[dict[str, Any]] = []
    for triplet_position, (candidate, first_policy) in enumerate(
        zip(selected, first_policies, strict=True)
    ):
        block_seed = rng.getrandbits(64)
        block_id = f"{triplet_id}|{candidate['model_id']}"
        selected_lookup[candidate["model_id"]] = (
            triplet_position,
            first_policy,
            block_seed,
        )
        plan.append(
            {
                **candidate,
                "triplet_id": triplet_id,
                "triplet_position": triplet_position,
                "assigned_first_policy": first_policy,
                "block_seed": block_seed,
                "block_id": block_id,
                "tasks": tasks_with_assigned_first(
                    candidate["endpoints"], first_policy, random.Random(block_seed)
                ),
            }
        )

    selection_probability = 3.0 / len(eligible) if len(eligible) >= 3 else None
    eligibility_rows: list[dict[str, Any]] = []
    for row in audited:
        assignment = selected_lookup.get(row["model_id"])
        eligibility_rows.append(
            {
                "run_id": run_id,
                "observed_at": run_timestamp(),
                "study_id": STUDY_ID,
                "triplet_id": triplet_id,
                "ranking_position": row["ranking_position"],
                "model_id": row["model_id"],
                "hugging_face_id": row["hugging_face_id"],
                "open_weight_screen": "nonempty_openrouter_hugging_face_id",
                "endpoint_fetch_status": row["endpoint_fetch_status"],
                "endpoint_http_status": row["endpoint_http_status"],
                "raw_endpoint_count": row["raw_endpoint_count"],
                "positive_quote_count": row["positive_quote_count"],
                "distinct_provider_count": row["distinct_provider_count"],
                "eligible": row["eligible"],
                "exclusion_reason": row["exclusion_reason"],
                "eligible_pool_size": len(eligible),
                "selected_for_triplet": assignment is not None,
                "selection_probability": (
                    selection_probability if assignment is not None else None
                ),
                "triplet_position": assignment[0] if assignment else None,
                "assigned_first_policy": assignment[1] if assignment else None,
                "provider_order_sha256": row["provider_order_sha256"],
                "public_min_completion_price": row["public_min_completion_price"],
                "public_max_completion_price": row["public_max_completion_price"],
                "public_quote_cost_cap_usd": row["public_quote_cost_cap_usd"],
                "quote_cap_input_tokens": QUOTE_CAP_INPUT_TOKENS,
                "request_timeout_ms": REQUEST_TIMEOUT_MS,
                "block_id": (f"{triplet_id}|{row['model_id']}" if assignment is not None else None),
                "block_seed": str(assignment[2]) if assignment else None,
                "run_seed": str(run_seed),
            }
        )
    summary = {
        "study_id": STUDY_ID,
        "run_id": run_id,
        "candidate_models": len(audited),
        "eligible_models": len(eligible),
        "selected_models": len(selected),
        "triplet_planned": len(selected) == MODELS_PER_TRIPLET,
        "target_triplets": TARGET_TRIPLETS,
        "target_first_position_blocks": TARGET_TRIPLETS * MODELS_PER_TRIPLET,
        "claim_boundary": (
            "A nonempty OpenRouter Hugging Face id is an operational open-weight screen, "
            "not a verified license. Eligibility and model selection are fixed before outcomes."
        ),
    }
    return plan, eligibility_rows, summary


def execute_replication_plan(
    client: httpx.Client,
    plan: list[dict[str, Any]],
    *,
    run_seed: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in plan:
        endpoints = block["endpoints"]
        provider_order = block["provider_order"]
        cheapest_price = float(endpoints[0]["price"])
        for position, task in enumerate(block["tasks"]):
            order = task["provider_order"]
            first_provider = order[0] if order else None
            observed_at = run_timestamp()
            completion, generation, error, status = _send_probe(
                client,
                block["model_id"],
                provider_order=order,
                provider_only=task["provider_only"],
                allow_fallbacks=bool(task["allow_fallbacks"]),
            )
            record = probe_record(
                block["model_id"],
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
                    "triplet_id": block["triplet_id"],
                    "triplet_position": block["triplet_position"],
                    "block_id": block["block_id"],
                    "block_policy_count": len(POLICIES),
                    "policy_order": position,
                    "assigned_first_policy": block["assigned_first_policy"],
                    "block_seed": block["block_seed"],
                    "run_seed": run_seed,
                    "assignment_probability_first": 1.0 / len(POLICIES),
                    "randomized_triplet_assignment": True,
                    "fixed_horizon_target_triplets": TARGET_TRIPLETS,
                    "primary_estimand": "first_position_no_prior_probe",
                    "public_provider_order": provider_order,
                    "public_provider_order_sha256": block["provider_order_sha256"],
                    "public_provider_count": len(provider_order),
                    "public_cheapest_provider": provider_order[0],
                    "public_cheapest_completion_price": cheapest_price,
                    "public_quote_cost_cap_usd": block["public_quote_cost_cap_usd"],
                    "quote_cap_input_tokens": QUOTE_CAP_INPUT_TOKENS,
                    "request_timeout_ms": REQUEST_TIMEOUT_MS,
                    "ranking_position": block["ranking_position"],
                    "hugging_face_id": block["hugging_face_id"],
                    "open_weight_screen": "nonempty_openrouter_hugging_face_id",
                    "requested_order_length": len(order) if order else 0,
                    "provider_only_count": len(task["provider_only"] or []),
                    "allow_fallbacks": bool(task["allow_fallbacks"]),
                },
            )
            if completion is None:
                record["event_id"] = f"{block['block_id']}|{position}|{task['policy']}"
            selected = record.get("selected_provider")
            record["fallback_triggered"] = bool(
                first_provider and selected and selected != first_provider
            )
            records.append(record)
    return records


def write_replication_eligibility(
    records: list[dict[str, Any]],
    *,
    run_ts: str,
    dt: str | None = None,
    curated_dir: Path = CURATED_DIR,
) -> Path | None:
    if not records:
        return None
    dt = dt or dt_partition()
    rows = [record | {"payload_retained": False, "run_ts": run_ts, "dt": dt} for record in records]
    return write_partition(
        pa.Table.from_pylist(rows, schema=REPLICATION_ELIGIBILITY_SCHEMA),
        "router_replication_eligibility",
        run_ts,
        dt,
        curated_dir,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run_id = run_timestamp()
    seed_text = os.environ.get("ORCAP_REPLICATION_RANDOMIZATION_SEED")
    run_seed = int(seed_text, 0) if seed_text else secrets.randbits(64)
    with httpx.Client(timeout=60) as client:
        plan, eligibility, summary = build_replication_plan(
            client, run_id=run_id, run_seed=run_seed
        )
        eligibility_out = write_replication_eligibility(eligibility, run_ts=run_id)
        records = execute_replication_plan(client, plan, run_seed=run_seed)
    attempts_out = write_attempts(records, run_ts=run_id)
    print(
        json.dumps(
            summary
            | {
                "attempts": len(records),
                "eligibility_path": str(eligibility_out) if eligibility_out else None,
                "attempts_path": str(attempts_out) if attempts_out else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
