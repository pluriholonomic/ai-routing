"""Assignment-first paid measurement of routing competition and liquidity.

The plan command uses public endpoint menus and a public benchmark item pool.
The execute command consumes the exact uploaded manifest, sends owned requests,
and persists only redacted route attempts, graded answer summaries, and spend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from .capture_api import write_partition
from .capture_evals import ITEMS, extract_answer
from .capture_price_response import (
    _attempt,
    _fetch_generation,
    _headers,
    _materialize,
    _selected_models,
    _send_assignment,
    _session_id,
    _spend_rows,
    freeze_candidates,
    reconstruct_spend,
)
from .capture_probes import CHAT_URL
from .capture_route_calibration import REQUEST_TIMEOUT_SECONDS, SHAPES
from .config import CURATED_DIR, dt_partition, run_timestamp
from .market_measurement import (
    MARKET_MEASUREMENT_ASSIGNMENT_SCHEMA,
    MARKET_MEASUREMENT_QUALITY_SCHEMA,
    PLAN_VERSION,
    STUDY_ID,
    build_market_assignments,
    market_manifest,
    select_quality_items,
)
from .price_experiments import (
    PAID_SPEND_LEDGER_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
    BudgetLimits,
    campaign_open,
    check_budget,
    validate_manifest,
)
from .route_telemetry import validate_attempt, write_attempts

DEFAULT_MAX_TASKS = 48


def _public_items() -> list[dict[str, Any]]:
    return [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]


def _short_shape():
    return next(shape for shape in SHAPES if shape.shape_id == "short_chat")


def build_plan_bundle(
    client: httpx.Client,
    *,
    run_id: str,
    seed: int,
    models: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    candidates, source_failures = freeze_candidates(
        client,
        run_id=run_id,
        seed=seed,
        models=models or _selected_models(),
        shapes=(_short_shape(),),
    )
    for row in candidates:
        row["study_id"] = STUDY_ID
        row["plan_version"] = PLAN_VERSION
        row["block_id"] = (
            f"{STUDY_ID}|{run_id}|{row['model_id']}|{row['shape_id']}"
        )
    quality_items = select_quality_items(_public_items(), seed=seed, count=2)
    assignments, summary = build_market_assignments(
        candidates,
        quality_items,
        run_id=run_id,
        seed=seed,
    )
    source_healthy = not source_failures and bool(assignments)
    summary = summary | {
        "source_failures": source_failures,
        "source_healthy": source_healthy,
        "preflight_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "claim_boundary": (
            "Controlled owned-request effects only; no market-wide flow, private router "
            "scores, cross-user ordering, provider capacity stocks, costs, or intent."
        ),
    }
    manifest = market_manifest(candidates, assignments, summary)
    return {
        "format": "orcap-market-measurement-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
        "manifest": manifest,
    }


def write_plan_bundle(
    bundle: dict[str, Any], *, bundle_path: Path, curated_dir: Path = CURATED_DIR
) -> dict[str, str]:
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    run_id = str(bundle["summary"]["run_id"])
    dt = dt_partition()
    candidate_path = write_partition(
        _materialize(
            bundle["candidates"], PRICE_RESPONSE_CANDIDATE_SCHEMA, run_id=run_id, dt=dt
        ),
        "market_measurement_candidates",
        run_id,
        dt,
        curated_dir,
    )
    assignments = [
        row
        | {
            "manifest_sha256": bundle["manifest"]["manifest_sha256"],
            "preflight_only": True,
        }
        for row in bundle["assignments"]
    ]
    assignment_path = write_partition(
        _materialize(
            assignments,
            MARKET_MEASUREMENT_ASSIGNMENT_SCHEMA,
            run_id=run_id,
            dt=dt,
        ),
        "market_measurement_assignments",
        run_id,
        dt,
        curated_dir,
    )
    return {
        "bundle_path": str(bundle_path),
        "candidate_path": str(candidate_path),
        "assignment_path": str(assignment_path),
    }


def _quality_item_map() -> dict[str, dict[str, Any]]:
    return {str(item["item_id"]): item for item in _public_items()}


def _send_quality_assignment(
    client: httpx.Client,
    assignment: dict[str, Any],
    item: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, int | None]:
    if hashlib.sha256(str(item["answer"]).encode()).hexdigest() != assignment.get(
        "quality_answer_sha256"
    ):
        raise RuntimeError("quality item answer no longer matches the frozen assignment")
    provider: dict[str, Any] = {
        "allow_fallbacks": bool(assignment["allow_fallbacks"]),
        "max_price": {
            "prompt": float(assignment["max_price_prompt_per_mtok"]),
            "completion": float(assignment["max_price_completion_per_mtok"]),
        },
    }
    if assignment.get("provider_sort"):
        provider["sort"] = assignment["provider_sort"]
    if assignment.get("provider_order_tags"):
        provider["order"] = assignment["provider_order_tags"]
    if assignment.get("provider_only_tags"):
        provider["only"] = assignment["provider_only_tags"]
    body = {
        "model": assignment["model_id"],
        "messages": [{"role": "user", "content": item["prompt"]}],
        "max_tokens": int(assignment["max_output_tokens"]),
        "temperature": 0,
        # Public model metadata may expose only high reasoning efforts.  Asking
        # for "minimal" can then be mapped upward and consume the entire small
        # answer budget.  The benchmark needs only the final multiple-choice
        # letter, so disable optional reasoning prospectively.
        "reasoning": {"effort": "none", "exclude": True},
        "usage": {"include": True},
        "session_id": _session_id(assignment),
        "provider": provider,
    }
    try:
        response = client.post(CHAT_URL, headers=_headers(), json=body)
        if response.status_code != 200:
            return None, None, f"http_{response.status_code}", response.status_code
        completion = response.json()
        generation = (
            _fetch_generation(client, str(completion["id"]))
            if completion.get("id")
            else None
        )
        return completion, generation, None, response.status_code
    except httpx.HTTPError as exc:
        return None, None, type(exc).__name__, None


def _quality_row(
    assignment: dict[str, Any],
    item: dict[str, Any],
    completion: dict[str, Any] | None,
    generation: dict[str, Any] | None,
    status: int | None,
    *,
    manifest_sha256: str,
    observed_at: str,
) -> dict[str, Any]:
    choice = ((completion or {}).get("choices") or [{}])[0]
    text = str((choice.get("message") or {}).get("content") or "")
    extracted = extract_answer(text, str(item["grade"])) if text else None
    usage = (completion or {}).get("usage") or {}
    gen = (generation or {}).get("data") or {}
    return {
        "study_id": STUDY_ID,
        "run_id": assignment["run_id"],
        "task_id": assignment["task_id"],
        "observed_at": observed_at,
        "model_id": assignment["model_id"],
        "policy": assignment["policy"],
        "quality_item_id": assignment["quality_item_id"],
        "quality_source": assignment["quality_source"],
        "requested_provider": assignment.get("requested_provider"),
        "selected_provider": gen.get("provider_name") or (completion or {}).get("provider"),
        "http_status": status,
        "extracted_answer": extracted,
        "correct": extracted == str(item["answer"]) if extracted is not None else None,
        "output_sha256": hashlib.sha256(text.encode()).hexdigest() if text else None,
        "output_norm_sha256": (
            hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()
            if text
            else None
        ),
        "output_len_chars": len(text),
        "input_tokens": gen.get("native_tokens_prompt") or usage.get("prompt_tokens"),
        "output_tokens": gen.get("native_tokens_completion")
        or usage.get("completion_tokens"),
        "cost_usd": gen.get("total_cost") or usage.get("cost"),
        "latency_ms": gen.get("latency"),
        "manifest_sha256": manifest_sha256,
        "payload_retained": False,
    }


def _augment_attempt(attempt: dict[str, Any], assignment: dict[str, Any]) -> None:
    attempt["metadata"].update(
        {
            "request_type": "market_measurement_probe",
            "experiment_axis": assignment["experiment_axis"],
            "execution_batch": assignment["execution_batch"],
            "concurrency_level": assignment["concurrency_level"],
            "concurrency_slot": assignment["concurrency_slot"],
            "quality_item_id": assignment.get("quality_item_id"),
        }
    )


def _execute_batch(
    client: httpx.Client,
    batch: list[dict[str, Any]],
    item_map: dict[str, dict[str, Any]],
    send: Any,
) -> list[
    tuple[
        dict[str, Any],
        dict[str, Any] | None,
        dict[str, Any] | None,
        str | None,
        int | None,
    ]
]:
    barrier = threading.Barrier(len(batch)) if len(batch) > 1 else None

    def worker(assignment: dict[str, Any]):
        if barrier is not None:
            barrier.wait(timeout=10)
        if send is not None:
            result = send(client, assignment)
        elif assignment["experiment_axis"] == "quality":
            item = item_map[str(assignment["quality_item_id"])]
            result = _send_quality_assignment(client, assignment, item)
        else:
            result = _send_assignment(client, assignment)
        return (assignment, *result)

    if len(batch) == 1:
        return [worker(batch[0])]
    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        return list(executor.map(worker, batch))


def execute_bundle(
    bundle: dict[str, Any],
    *,
    curated_dir: Path = CURATED_DIR,
    data_root: Path | None = None,
    now: datetime | None = None,
    send: Any = None,
) -> dict[str, Any]:
    """Validate, budget, and execute exactly one immutable measurement plan."""
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    assignments = list(bundle["assignments"])
    if not assignments:
        raise RuntimeError("validated plan contains no executable assignments")
    if not bool(bundle["summary"].get("source_healthy")):
        raise RuntimeError("source-health gate failed; refusing paid execution")
    task_ids = [str(row["task_id"]) for row in assignments]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeError("duplicate task ids in uploaded plan")
    if os.environ.get("ORCAP_PAID_PRICE_STUDIES_ENABLED", "").lower() != "true":
        raise RuntimeError("paid price studies are disabled")
    if os.environ.get("ORCAP_MARKET_MEASUREMENT_ENABLED", "").lower() != "true":
        raise RuntimeError("market measurement is disabled")
    if not os.environ.get("OPENROUTER_PRICE_EXPERIMENT_KEY"):
        raise RuntimeError("dedicated paid experiment key is unavailable")
    start = os.environ.get("ORCAP_MARKET_MEASUREMENT_START_UTC")
    end = os.environ.get("ORCAP_MARKET_MEASUREMENT_END_UTC")
    if not start or not end or not campaign_open(start, end, now):
        raise RuntimeError("paid execution refused outside the configured campaign")

    now = (now or datetime.now(UTC)).astimezone(UTC)
    limits = BudgetLimits(
        float(os.environ.get("ORCAP_MARKET_MEASUREMENT_MAX_RUN_USD", "0.50")),
        float(os.environ.get("ORCAP_MARKET_MEASUREMENT_MAX_DAY_USD", "3.00")),
        float(os.environ.get("ORCAP_MARKET_MEASUREMENT_MAX_CAMPAIGN_USD", "20.00")),
    )
    historical = _spend_rows(data_root or curated_dir.parent)
    existing = {
        str(row.get("task_id") or "")
        for row in historical
        if str(row.get("study_id") or "") == STUDY_ID
    }
    overlap = sorted(set(task_ids) & existing)
    if overlap:
        raise RuntimeError(
            f"refusing to re-execute {len(overlap)} task(s) already present in spend ledger"
        )
    day, campaign = reconstruct_spend(historical, now=now, study_id=STUDY_ID)
    check_budget(
        planned_usd=float(bundle["summary"]["planned_quote_cap_usd"]),
        spent_day_usd=day,
        spent_campaign_usd=campaign,
        limits=limits,
    )

    by_batch: dict[str, list[dict[str, Any]]] = {}
    for assignment in assignments:
        by_batch.setdefault(str(assignment["execution_batch"]), []).append(assignment)
    ordered_batches = sorted(
        by_batch.values(), key=lambda batch: min(int(row["policy_order"]) for row in batch)
    )
    item_map = _quality_item_map()
    attempts_by_task: dict[str, dict[str, Any]] = {}
    quality_by_task: dict[str, dict[str, Any]] = {}
    manifest_sha = str(bundle["manifest"]["manifest_sha256"])
    run_id = str(bundle["summary"]["run_id"])
    dt = dt_partition(now)

    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for batch in ordered_batches:
            for assignment, completion, generation, error, status in _execute_batch(
                client, batch, item_map, send
            ):
                attempt = _attempt(
                    assignment,
                    completion,
                    generation,
                    error,
                    status,
                    manifest_sha256=manifest_sha,
                    study_id=STUDY_ID,
                )
                _augment_attempt(attempt, assignment)
                attempts_by_task[str(assignment["task_id"])] = attempt
                if assignment["experiment_axis"] == "quality":
                    quality_by_task[str(assignment["task_id"])] = _quality_row(
                        assignment,
                        item_map[str(assignment["quality_item_id"])],
                        completion,
                        generation,
                        status,
                        manifest_sha256=manifest_sha,
                        observed_at=str(attempt["observed_at"]),
                    )
            # Checkpoint after every synchronized batch. A failed CI step can
            # still upload completed redacted rows in its always() artifact.
            ordered_attempts = [
                attempts_by_task[task_id] for task_id in task_ids if task_id in attempts_by_task
            ]
            write_attempts(ordered_attempts, run_ts=run_id, dt=dt, curated_dir=curated_dir)
            dedicated_attempts = [
                validate_attempt(attempt) | {"run_ts": run_id, "dt": dt}
                for attempt in ordered_attempts
            ]
            write_partition(
                pa.Table.from_pylist(dedicated_attempts),
                "market_measurement_attempts",
                run_id,
                dt,
                curated_dir,
            )
            ledger_rows = [
                {
                    "study_id": STUDY_ID,
                    "run_id": run_id,
                    "task_id": assignment["task_id"],
                    "observed_at": attempts_by_task[str(assignment["task_id"])]["observed_at"],
                    "cost_usd": float(
                        attempts_by_task[str(assignment["task_id"])].get("cost_usd") or 0.0
                    ),
                    "attempted": True,
                    "manifest_sha256": manifest_sha,
                    "payload_retained": False,
                }
                for assignment in assignments
                if str(assignment["task_id"]) in attempts_by_task
            ]
            write_partition(
                _materialize(ledger_rows, PAID_SPEND_LEDGER_SCHEMA, run_id=run_id, dt=dt),
                "paid_spend_ledger",
                run_id,
                dt,
                curated_dir,
            )
            if quality_by_task:
                write_partition(
                    _materialize(
                        [
                            quality_by_task[task_id]
                            for task_id in task_ids
                            if task_id in quality_by_task
                        ],
                        MARKET_MEASUREMENT_QUALITY_SCHEMA,
                        run_id=run_id,
                        dt=dt,
                    ),
                    "market_measurement_quality",
                    run_id,
                    dt,
                    curated_dir,
                )

    attempts = [attempts_by_task[task_id] for task_id in task_ids]
    result = {
        "study_id": STUDY_ID,
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "planned_requests": len(assignments),
        "attempted_requests": len(attempts),
        "successful_requests": sum(row["outcome"] == "succeeded" for row in attempts),
        "quality_rows": len(quality_by_task),
        "realized_cost_usd": sum(float(row.get("cost_usd") or 0.0) for row in attempts),
        "claim_boundary": bundle["summary"]["claim_boundary"],
    }
    report_path = curated_dir.parent / "analysis" / "market-measurement-execution.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--bundle", type=Path, default=Path("market-measurement-plan.json"))
    plan.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    validate = subparsers.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()

    if args.command == "plan":
        run_id = os.environ.get("ORCAP_MARKET_MEASUREMENT_RUN_ID") or run_timestamp()
        seed = int(
            os.environ.get("ORCAP_MARKET_MEASUREMENT_SEED", secrets.randbits(64))
        )
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_plan_bundle(client, run_id=run_id, seed=seed)
        paths = write_plan_bundle(
            bundle, bundle_path=args.bundle, curated_dir=args.curated_dir
        )
        print(json.dumps(bundle["summary"] | bundle["manifest"] | paths, indent=2))
    elif args.command == "execute":
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        print(
            json.dumps(
                execute_bundle(
                    bundle,
                    curated_dir=args.curated_dir,
                    data_root=args.curated_dir.parent,
                ),
                indent=2,
            )
        )
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_manifest(
            bundle["manifest"],
            bundle["candidates"],
            bundle["assignments"],
            bundle["summary"],
        )
        if not bundle["summary"].get("source_healthy"):
            raise RuntimeError("public candidate source failed health validation")
        if args.require_tasks and not bundle["assignments"]:
            raise RuntimeError("validated plan contains no executable assignments")
        print(
            json.dumps(
                {
                    "manifest_sha256": bundle["manifest"]["manifest_sha256"],
                    "source_healthy": True,
                    "planned_tasks": len(bundle["assignments"]),
                    "planned_quote_cap_usd": bundle["summary"]["planned_quote_cap_usd"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
