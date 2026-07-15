"""H89 prospective randomized Hugging Face routing-policy probes.

Each run snapshots Hugging Face's public multi-provider surface, then sends at
most one fixed one-token request per model.  The randomized arms are the two
documented server-side policies (``:fastest`` and ``:cheapest``) and a pinned
public cost-caliper frontier.  Candidate rows contain no request outcomes;
redacted attempts retain the selected provider response header, wall-clock
latency, estimated cost, and success status without prompt or completion text.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import secrets
import time
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, dt_partition, run_timestamp
from .route_telemetry import write_attempts

log = logging.getLogger(__name__)

STUDY_ID = "huggingface-policy-frontier-v1"
SCENARIO = "fixed_one_token_short_chat"
POLICIES = ("hf_fastest", "hf_cheapest", "public_cost_caliper")
HF_MODELS_URL = "https://router.huggingface.co/v1/models"
HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
PROBE_PROMPT = "Reply with the single word: pong"
REQUEST_TIMEOUT_SECONDS = 60.0
QUOTE_CAP_INPUT_TOKENS = 64
QUOTE_CAP_OUTPUT_TOKENS = 1
COST_CALIPER_RATIO = 1.25
MAX_REQUEST_QUOTE_CAP_USD = 0.001
MONTHLY_QUOTE_CAP_USD = 5.0
MAX_RUN_QUOTE_CAP_USD = MONTHLY_QUOTE_CAP_USD / (31 * 24)

# Frozen before confirmatory enrollment.  Eligibility still fails closed when
# a model no longer has at least two live, fully priced providers with public
# throughput or when its public cheapest and fastest providers coincide.
FIXED_MODELS = (
    "meta-llama/Llama-3.1-8B-Instruct",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "meta-llama/Llama-4-Scout-17B-16E-Instruct",
    "Qwen/Qwen3-32B",
    "google/gemma-3-27b-it",
    "deepseek-ai/DeepSeek-V4-Flash",
    "MiniMaxAI/MiniMax-M2.7",
    "google/gemma-4-31B-it",
    "google/gemma-4-26B-A4B-it",
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "deepseek-ai/DeepSeek-V3.1-Terminus",
)
PUBLIC_STATE_FIELDS = (
    "public_provider_count",
    "public_cheapest_provider",
    "public_cheapest_quote_cap_usd",
    "public_cheapest_throughput_tps",
    "public_fastest_provider",
    "public_fastest_quote_cap_usd",
    "public_fastest_throughput_tps",
    "public_cost_caliper_provider",
    "public_cost_caliper_quote_cap_usd",
    "public_cost_caliper_throughput_tps",
    "public_minimum_total_quote_cap_usd",
    "public_provider_state_json",
)


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['HF_TOKEN']}",
        "Content-Type": "application/json",
        "User-Agent": "orcap-h89-policy-trial/1",
    }


def _provider_rows(models_body: Any, model_id: str) -> list[dict[str, Any]]:
    models = (models_body or {}).get("data") or []
    model = next(
        (row for row in models if isinstance(row, dict) and row.get("id") == model_id), None
    )
    rows: list[dict[str, Any]] = []
    for provider in (model or {}).get("providers") or []:
        if not isinstance(provider, dict) or provider.get("status") not in {None, "live"}:
            continue
        name = provider.get("provider")
        pricing = provider.get("pricing") or {}
        input_price = _float(pricing.get("input"))
        output_price = _float(pricing.get("output"))
        throughput = _float(provider.get("throughput"))
        if (
            not name
            or input_price is None
            or output_price is None
            or throughput is None
            or input_price < 0
            or output_price < 0
            or throughput <= 0
        ):
            continue
        expected_cost = (
            input_price * QUOTE_CAP_INPUT_TOKENS
            + output_price * QUOTE_CAP_OUTPUT_TOKENS
        ) / 1_000_000
        rows.append(
            {
                "provider": str(name),
                "input_price_usd_per_mtok": input_price,
                "output_price_usd_per_mtok": output_price,
                "throughput_tps": throughput,
                "quote_cap_usd": expected_cost,
            }
        )
    return sorted(rows, key=lambda row: row["provider"])


def public_policy_state(models_body: Any, model_id: str) -> tuple[dict[str, Any] | None, str]:
    """Return the frozen public treatment state or a fail-closed reason."""
    rows = _provider_rows(models_body, model_id)
    if len(rows) < 2:
        return None, "fewer_than_two_live_fully_priced_providers"
    # HF documents :cheapest as the lowest output-token price.  Tie-breaking
    # here is merely an outcome-free public prediction; the response header is
    # the realized provider source of truth after release.
    cheapest = min(
        rows,
        key=lambda row: (
            row["output_price_usd_per_mtok"],
            row["input_price_usd_per_mtok"],
            row["provider"],
        ),
    )
    fastest = min(rows, key=lambda row: (-row["throughput_tps"], row["provider"]))
    minimum_total = min(row["quote_cap_usd"] for row in rows)
    caliper_rows = [
        row
        for row in rows
        if row["quote_cap_usd"] <= COST_CALIPER_RATIO * minimum_total + 1e-15
    ]
    frontier = min(
        caliper_rows,
        key=lambda row: (-row["throughput_tps"], row["quote_cap_usd"], row["provider"]),
    )
    if cheapest["provider"] == fastest["provider"]:
        return None, "public_cheapest_equals_public_fastest"
    state = {
        "public_provider_count": len(rows),
        "public_cheapest_provider": cheapest["provider"],
        "public_cheapest_quote_cap_usd": cheapest["quote_cap_usd"],
        "public_cheapest_throughput_tps": cheapest["throughput_tps"],
        "public_fastest_provider": fastest["provider"],
        "public_fastest_quote_cap_usd": fastest["quote_cap_usd"],
        "public_fastest_throughput_tps": fastest["throughput_tps"],
        "public_cost_caliper_provider": frontier["provider"],
        "public_cost_caliper_quote_cap_usd": frontier["quote_cap_usd"],
        "public_cost_caliper_throughput_tps": frontier["throughput_tps"],
        "public_minimum_total_quote_cap_usd": minimum_total,
        "public_provider_state_json": json.dumps(
            rows, sort_keys=True, separators=(",", ":")
        ),
    }
    return state, "eligible"


def candidate_state_hash(model_id: str, state: dict[str, Any]) -> str:
    payload = json.dumps(
        {"model_id": model_id, **state},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _assignment_fields(
    model_id: str, policy: str, state: dict[str, Any]
) -> tuple[str, str | None, str, float]:
    if policy == "hf_fastest":
        return (
            f"{model_id}:fastest",
            None,
            str(state["public_fastest_provider"]),
            float(state["public_fastest_quote_cap_usd"]),
        )
    if policy == "hf_cheapest":
        return (
            f"{model_id}:cheapest",
            None,
            str(state["public_cheapest_provider"]),
            float(state["public_cheapest_quote_cap_usd"]),
        )
    provider = str(state["public_cost_caliper_provider"])
    return (
        f"{model_id}:{provider}",
        provider,
        provider,
        float(state["public_cost_caliper_quote_cap_usd"]),
    )


def _send_probe(
    client: httpx.Client,
    *,
    model_id: str,
    requested_model: str,
    requested_provider: str | None,
    policy: str,
    block_id: str,
    state_hash: str,
    public_predicted_provider: str,
    public_quote_cap_usd: float,
    block_seed: int,
    run_seed: int,
) -> dict[str, Any]:
    started_at = run_timestamp()
    started = time.monotonic()
    response: httpx.Response | None = None
    body: dict[str, Any] = {}
    error: str | None = None
    try:
        response = client.post(
            HF_CHAT_URL,
            headers=_headers(),
            json={
                "model": requested_model,
                "messages": [{"role": "user", "content": PROBE_PROMPT}],
                "max_tokens": 1,
                "temperature": 0,
                "stream": False,
            },
        )
        if response.headers.get("content-type", "").startswith("application/json"):
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        if response.status_code != 200:
            error = f"http_{response.status_code}"
    except httpx.HTTPError as exc:
        error = type(exc).__name__
    latency_ms = (time.monotonic() - started) * 1000
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    selected_provider = response.headers.get("x-inference-provider") if response else None
    request_id = response.headers.get("x-request-id") if response else None
    event_id = body.get("id") or request_id or f"{block_id}|{started_at}"
    status_code = response.status_code if response else None
    return {
        "event_id": str(event_id),
        "observed_at": started_at,
        "router": "huggingface_inference_providers",
        "source": "huggingface_inference_providers",
        "study_id": STUDY_ID,
        "request_ref": request_id or body.get("id"),
        "model_id": model_id,
        "requested_provider": requested_provider,
        "selected_provider": selected_provider,
        "attempt_index": 0,
        "outcome": "succeeded" if status_code == 200 and error is None else "failed",
        "retry_reason": error,
        "fallback_triggered": False,
        "policy": policy,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "cost_usd": usage.get("estimated_cost"),
        "latency_ms": latency_ms,
        "metadata": {
            "scenario": SCENARIO,
            "status_code": status_code,
            "request_type": "probe",
            "block_id": block_id,
            "candidate_state_hash": state_hash,
            "requested_model_suffix": requested_model.rsplit(":", 1)[-1],
            "public_predicted_provider": public_predicted_provider,
            "public_quote_cost_cap_usd": public_quote_cap_usd,
            "assignment_probability": 1 / len(POLICIES),
            "block_seed": str(block_seed),
            "run_seed": str(run_seed),
            "first_and_only_exposure": True,
            "server_side_failover_unobserved": policy != "public_cost_caliper",
            "request_timeout_ms": REQUEST_TIMEOUT_SECONDS * 1000,
        },
    }


def run_hf_policy_probes(
    model_ids: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    """Collect one H89 run while returning no arm outcomes."""
    run_id, dt = run_timestamp(), dt_partition()
    seed_text = os.environ.get("ORCAP_H89_RANDOMIZATION_SEED")
    run_seed = int(seed_text, 0) if seed_text else secrets.randbits(64)
    rng = random.Random(run_seed)
    own_client = client is None
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
    candidates: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    running_quote_cap = 0.0
    try:
        response = http.get(HF_MODELS_URL, headers=_headers())
        response.raise_for_status()
        models_body = response.json()
        selected_models = list(model_ids or FIXED_MODELS)
        rng.shuffle(selected_models)
        for evaluation_order, model_id in enumerate(selected_models):
            block_seed = rng.getrandbits(64)
            block_id = f"{STUDY_ID}|{run_id}|{model_id}"
            state, reason = public_policy_state(models_body, model_id)
            base: dict[str, Any] = {
                "study_id": STUDY_ID,
                "run_ts": run_id,
                "dt": dt,
                "block_id": block_id,
                "model_id": model_id,
                "evaluation_order": evaluation_order,
                "run_seed": str(run_seed),
                "block_seed": str(block_seed),
                "assignment_probability": 1 / len(POLICIES),
                "eligible_model": state is not None,
                "request_sent": False,
                "exclusion_reason": None if state is not None else reason,
                "assignment": None,
                "assigned_requested_model": None,
                "assigned_requested_provider": None,
                "public_assigned_provider": None,
                "public_assigned_quote_cap_usd": None,
                "candidate_state_hash": None,
                "attempt_event_id": None,
                "request_observed_at": None,
                **{field: None for field in PUBLIC_STATE_FIELDS},
            }
            if state is None:
                candidates.append(base)
                continue
            state_hash = candidate_state_hash(model_id, state)
            assignment = random.Random(block_seed).choice(POLICIES)
            requested_model, requested_provider, predicted_provider, quote_cap = (
                _assignment_fields(model_id, assignment, state)
            )
            base.update(
                {
                    **state,
                    "assignment": assignment,
                    "assigned_requested_model": requested_model,
                    "assigned_requested_provider": requested_provider,
                    "public_assigned_provider": predicted_provider,
                    "public_assigned_quote_cap_usd": quote_cap,
                    "candidate_state_hash": state_hash,
                }
            )
            if quote_cap > MAX_REQUEST_QUOTE_CAP_USD:
                base["eligible_model"] = False
                base["exclusion_reason"] = "assigned_quote_cap_above_request_limit"
                candidates.append(base)
                continue
            if running_quote_cap + quote_cap > MAX_RUN_QUOTE_CAP_USD:
                base["eligible_model"] = False
                base["exclusion_reason"] = "run_quote_cap_exceeded"
                candidates.append(base)
                continue
            attempt = _send_probe(
                http,
                model_id=model_id,
                requested_model=requested_model,
                requested_provider=requested_provider,
                policy=assignment,
                block_id=block_id,
                state_hash=state_hash,
                public_predicted_provider=predicted_provider,
                public_quote_cap_usd=quote_cap,
                block_seed=block_seed,
                run_seed=run_seed,
            )
            attempts.append(attempt)
            base["request_sent"] = True
            base["attempt_event_id"] = attempt["event_id"]
            base["request_observed_at"] = attempt["observed_at"]
            candidates.append(base)
            running_quote_cap += quote_cap
    finally:
        if own_client:
            http.close()

    candidate_path = None
    if candidates:
        candidate_path = write_partition(
            pa.Table.from_pylist(candidates),
            "h89_hf_policy_candidates",
            run_id,
            dt,
            curated_dir,
        )
    attempt_path = write_attempts(attempts, run_ts=run_id, dt=dt, curated_dir=curated_dir)
    # Arm outcomes are deliberately absent from logs and the returned summary.
    return {
        "study_id": STUDY_ID,
        "run_ts": run_id,
        "candidate_models": len(candidates),
        "eligible_models": sum(bool(row.get("eligible_model")) for row in candidates),
        "assignments_sent": sum(bool(row.get("request_sent")) for row in candidates),
        "assignment_counts": {
            policy: sum(
                row.get("assignment") == policy and bool(row.get("request_sent"))
                for row in candidates
            )
            for policy in POLICIES
        },
        "public_quote_cap_usd": running_quote_cap,
        "candidate_path": str(candidate_path) if candidate_path else None,
        "attempt_path": str(attempt_path) if attempt_path else None,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(json.dumps(run_hf_policy_probes(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
