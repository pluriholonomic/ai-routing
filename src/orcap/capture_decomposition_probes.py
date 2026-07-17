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
import pyarrow.parquet as pq

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
        ("block_seed", pa.string()),
        ("first_policy_planned", pa.string()),
        ("assignment_probability_first", pa.float64()),
        ("randomized_order", pa.bool_()),
        ("run_seed", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

PLAN_SCHEMA = pa.schema(
    [
        ("plan_id", pa.string()),
        ("planned_at", pa.string()),
        ("run_id", pa.string()),
        ("study_id", pa.string()),
        ("ranking_position", pa.int32()),
        ("evaluation_order", pa.int32()),
        ("model_id", pa.string()),
        ("block_id", pa.string()),
        ("block_seed", pa.string()),
        ("first_policy_planned", pa.string()),
        ("assignment_probability_first", pa.float64()),
        ("randomized_order", pa.bool_()),
        ("public_provider_count", pa.int32()),
        ("public_provider_order_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

PLAN_AUDIT_FORBIDDEN_FIELDS = frozenset(
    {
        "outcome",
        "cost_usd",
        "latency_ms",
        "selected_provider",
        "retry_reason",
        "generation_id",
    }
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


def write_decomposition_plan(
    record: dict[str, Any],
    *,
    run_ts: str,
    dt: str | None = None,
    curated_dir: Path = CURATED_DIR,
) -> Path:
    """Persist one outcome-free randomized block plan before its first request."""
    dt = dt or dt_partition()
    row = record | {"payload_retained": False, "run_ts": run_ts, "dt": dt}
    return write_partition(
        pa.Table.from_pylist([row], schema=PLAN_SCHEMA),
        "router_decomposition_plans",
        run_ts,
        dt,
        curated_dir,
    )


def write_decomposition_plan_audit(
    plan_paths: list[Path],
    *,
    run_id: str,
    output_path: Path = Path("data/outcome_free_audit/decomposition-plan-audit.json"),
    source_commit: str | None = None,
    workflow_run_id: str | None = None,
) -> Path:
    """Write an aggregate outcome-free commitment to this run's plan rows."""
    if not plan_paths:
        raise ValueError("at least one decomposition plan is required")

    rows: list[dict[str, Any]] = []
    file_commitments = []
    schema_fields: set[str] = set()
    for path in sorted(plan_paths, key=lambda item: str(item)):
        table = pq.ParquetFile(path).read()
        schema_fields.update(table.column_names)
        rows.extend(table.to_pylist())
        file_commitments.append(hashlib.sha256(path.read_bytes()).hexdigest())

    forbidden_fields = sorted(schema_fields & PLAN_AUDIT_FORBIDDEN_FIELDS)
    run_ids = sorted({str(row.get("run_id")) for row in rows})
    study_ids = sorted({str(row.get("study_id")) for row in rows})
    commitment_payload = json.dumps(file_commitments, separators=(",", ":"))
    manifest = {
        "audit_schema_version": 1,
        "study_id": STUDY_ID,
        "run_id": run_id,
        "source_commit": source_commit,
        "workflow_run_id": workflow_run_id,
        "plan_file_count": len(plan_paths),
        "plan_row_count": len(rows),
        "plan_run_ids": run_ids,
        "plan_study_ids": study_ids,
        "plan_schema_fields": sorted(schema_fields),
        "plan_commitment_sha256": hashlib.sha256(commitment_payload.encode()).hexdigest(),
        "payload_retained_all_false": all(row.get("payload_retained") is False for row in rows),
        "randomized_order_all_true": all(row.get("randomized_order") is True for row in rows),
        "assignment_probability_first_all_one_third": all(
            abs(float(row.get("assignment_probability_first", 0.0)) - 1.0 / 3.0) < 1e-12
            for row in rows
        ),
        "run_id_match": run_ids == [run_id],
        "study_id_match": study_ids == [STUDY_ID],
        "forbidden_fields_present": forbidden_fields,
        "outcomes_included": False,
        "request_records_included": False,
        "plan_persisted_before_probe_call_by_program_order": True,
        "capture_log_outcome_fields": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output_path


def run_decomposition_probes(
    model_ids: list[str] | None = None,
    *,
    eligibility_records: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    persist_plans: bool = True,
    curated_dir: Path = CURATED_DIR,
    plan_paths: list[Path] | None = None,
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
            block_seed = rng.getrandbits(64) if eligible else None
            tasks = (
                decomposition_tasks(endpoints, random.Random(block_seed))
                if block_seed is not None
                else []
            )
            first_policy_planned = str(tasks[0]["policy"]) if tasks else None
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
                        "block_seed": str(block_seed) if block_seed is not None else None,
                        "first_policy_planned": first_policy_planned,
                        "assignment_probability_first": 1.0 / len(POLICIES),
                        "randomized_order": True,
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
            planned_at = run_timestamp()
            if persist_plans:
                plan_path = write_decomposition_plan(
                    {
                        "plan_id": block_id,
                        "planned_at": planned_at,
                        "run_id": run_id,
                        "study_id": STUDY_ID,
                        "ranking_position": ranking_position,
                        "evaluation_order": evaluation_order,
                        "model_id": model_id,
                        "block_id": block_id,
                        "block_seed": str(block_seed),
                        "first_policy_planned": first_policy_planned,
                        "assignment_probability_first": 1.0 / len(POLICIES),
                        "randomized_order": True,
                        "public_provider_count": len(provider_order),
                        "public_provider_order_sha256": order_hash,
                    },
                    run_ts=f"{run_id}-{evaluation_order:03d}",
                    curated_dir=curated_dir,
                )
                if plan_paths is not None:
                    plan_paths.append(plan_path)
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
                    "decomposition assignment persisted block=%s position=%d policy=%s model=%s",
                    block_id,
                    position,
                    task["policy"],
                    model_id,
                )
    return records


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run_id = run_timestamp()
    eligibility_records: list[dict[str, Any]] = []
    plan_paths: list[Path] = []
    records = run_decomposition_probes(
        eligibility_records=eligibility_records,
        run_id=run_id,
        plan_paths=plan_paths,
    )
    out = write_attempts(records, run_ts=run_id)
    eligibility_out = write_eligibility_audit(eligibility_records, run_ts=run_id)
    plan_audit_out = write_decomposition_plan_audit(
        plan_paths,
        run_id=run_id,
        source_commit=os.environ.get("GITHUB_SHA"),
        workflow_run_id=os.environ.get("GITHUB_RUN_ID"),
    )
    print(
        json.dumps(
            {
                "study_id": STUDY_ID,
                "probes": len(records),
                "blocks": len({record["metadata"]["block_id"] for record in records}),
                "plan_rows": len(plan_paths),
                "plan_audit_path": str(plan_audit_out),
                "outcome_fields_logged": False,
                "request_artifact_written": out is not None,
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
