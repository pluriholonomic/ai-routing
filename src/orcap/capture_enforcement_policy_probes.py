"""H88 prospective randomized public-enforcement routing policy probes.

For each eligible hot-model block, capture quote and five-minute router
enforcement state before assignment, construct a price-calipered lower/higher
enforcement-stress pair, randomize exactly one of ``enforcement_safe``,
``enforcement_risky``, or ``openrouter_default``, and send one one-token
request. Candidate records are outcome-free; realized records use the redacted
``router_route_attempts`` contract. See the frozen H88 section in
``docs/h86-h87-capacity-state-execution-preregistration.md``.
"""

from __future__ import annotations

import json
import logging
import os
import random
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd
import pyarrow as pa

from .capture_api import STATS_URL, write_partition
from .capture_capacity_policy_probes import (
    MAX_REQUEST_QUOTE_CAP_USD,
    MAX_RUN_QUOTE_CAP_USD,
    PRICE_CALIPER_RATIO,
    QUOTE_CAP_INPUT_TOKENS,
    _float,
    candidate_state_hash,
    hot_model_specs,
)
from .capture_probes import MODELS_URL, RANKINGS_URL, _send_probe, probe_record
from .config import API_V1, CURATED_DIR, dt_partition, run_timestamp
from .route_telemetry import write_attempts

log = logging.getLogger(__name__)

STUDY_ID = "openrouter-enforcement-policy-v1"
SCENARIO = "enforcement_policy_one_token"
POLICIES = ("enforcement_safe", "enforcement_risky", "openrouter_default")
MAX_MODELS = int(os.environ.get("ORCAP_H88_MAX_MODELS", "8"))
MIN_PUBLIC_ATTEMPTS_5M = 10
CANDIDATE_OPTIONAL_FIELDS = (
    "safe_provider",
    "risky_provider",
    "safe_completion_price",
    "risky_completion_price",
    "safe_prompt_price",
    "risky_prompt_price",
    "safe_success_5m",
    "risky_success_5m",
    "safe_rate_limited_5m",
    "risky_rate_limited_5m",
    "safe_attempts_5m",
    "risky_attempts_5m",
    "safe_enforcement_stress",
    "risky_enforcement_stress",
    "enforcement_stress_gap",
    "price_ratio",
    "candidate_state_hash",
    "assignment",
    "assigned_requested_provider",
    "public_quote_cost_cap_usd",
    "attempt_event_id",
    "request_observed_at",
)


def public_enforcement_states(endpoints_body: Any, stats_body: Any) -> pd.DataFrame:
    """Join exact provider quotes to same-fetch five-minute enforcement counts."""
    quote_rows: list[dict[str, Any]] = []
    endpoints = ((endpoints_body or {}).get("data") or {}).get("endpoints") or []
    for endpoint in endpoints:
        provider = endpoint.get("provider_name")
        pricing = endpoint.get("pricing") or {}
        completion = _float(pricing.get("completion"))
        prompt = _float(pricing.get("prompt"))
        if provider and completion is not None and completion > 0:
            quote_rows.append(
                {
                    "provider_name": str(provider),
                    "completion_price": completion,
                    "prompt_price": prompt,
                }
            )
    if not quote_rows:
        return pd.DataFrame()
    # A provider can expose multiple endpoint variants. The lowest positive
    # completion quote, then prompt quote, is a deterministic public offer.
    quotes = pd.DataFrame(quote_rows).sort_values(
        ["provider_name", "completion_price", "prompt_price"], na_position="last"
    )
    quotes = quotes.drop_duplicates("provider_name", keep="first")

    stat_rows: list[dict[str, Any]] = []
    for endpoint in (stats_body or {}).get("data") or []:
        provider = endpoint.get("provider_display_name") or endpoint.get("provider_name")
        heuristics = endpoint.get("status_heuristics_5m") or {}
        success = _float(heuristics.get("success"))
        rate_limited = _float(heuristics.get("rateLimited"))
        if not provider or (success is None and rate_limited is None):
            continue
        stat_rows.append(
            {
                "provider_name": str(provider),
                "success_5m": max(0.0, success or 0.0),
                "rate_limited_5m": max(0.0, rate_limited or 0.0),
                "is_deranked": bool(endpoint.get("is_deranked", False)),
            }
        )
    if not stat_rows:
        return pd.DataFrame()
    stats = (
        pd.DataFrame(stat_rows)
        .groupby("provider_name", sort=False)
        .agg(
            success_5m=("success_5m", "sum"),
            rate_limited_5m=("rate_limited_5m", "sum"),
            is_deranked=("is_deranked", "max"),
        )
        .reset_index()
    )
    stats["attempts_5m"] = stats["success_5m"] + stats["rate_limited_5m"]
    states = quotes.merge(stats, on="provider_name", how="inner", validate="one_to_one")
    states = states[
        states["attempts_5m"].ge(MIN_PUBLIC_ATTEMPTS_5M) & ~states["is_deranked"].astype(bool)
    ].copy()
    if states.empty:
        return states
    states["enforcement_stress"] = (states["rate_limited_5m"] + 1.0) / (states["attempts_5m"] + 2.0)
    return states.sort_values("provider_name").reset_index(drop=True)


def select_enforcement_pair(states: pd.DataFrame) -> tuple[dict[str, Any] | None, str]:
    """Choose the largest frozen stress gap within the 25% price caliper."""
    if len(states) < 2:
        return None, "fewer_than_two_enforcement_complete_providers"
    pairs: list[tuple[float, str, str, pd.Series, pd.Series]] = []
    for i, left in states.iterrows():
        for j, right in states.iterrows():
            if i >= j:
                continue
            ratio = max(left["completion_price"], right["completion_price"]) / min(
                left["completion_price"], right["completion_price"]
            )
            if (
                ratio > PRICE_CALIPER_RATIO
                or left["enforcement_stress"] == right["enforcement_stress"]
            ):
                continue
            safe, risky = (
                (left, right)
                if left["enforcement_stress"] < right["enforcement_stress"]
                else (right, left)
            )
            gap = float(risky["enforcement_stress"] - safe["enforcement_stress"])
            pairs.append(
                (
                    -gap,
                    str(safe["provider_name"]),
                    str(risky["provider_name"]),
                    safe,
                    risky,
                )
            )
    if not pairs:
        return None, "no_distinct_stress_pair_within_price_caliper"
    _negative_gap, _safe_name, _risky_name, safe, risky = sorted(
        pairs, key=lambda item: (item[0], item[1], item[2])
    )[0]
    ratio = max(safe["completion_price"], risky["completion_price"]) / min(
        safe["completion_price"], risky["completion_price"]
    )
    pair: dict[str, Any] = {
        "safe_provider": str(safe["provider_name"]),
        "risky_provider": str(risky["provider_name"]),
        "safe_completion_price": float(safe["completion_price"]),
        "risky_completion_price": float(risky["completion_price"]),
        "safe_prompt_price": _float(safe["prompt_price"]),
        "risky_prompt_price": _float(risky["prompt_price"]),
        "enforcement_stress_gap": float(risky["enforcement_stress"] - safe["enforcement_stress"]),
        "price_ratio": float(ratio),
    }
    for prefix, row in (("safe", safe), ("risky", risky)):
        pair[f"{prefix}_success_5m"] = float(row["success_5m"])
        pair[f"{prefix}_rate_limited_5m"] = float(row["rate_limited_5m"])
        pair[f"{prefix}_attempts_5m"] = float(row["attempts_5m"])
        pair[f"{prefix}_enforcement_stress"] = float(row["enforcement_stress"])
    return pair, "eligible"


def quote_cost_cap(pair: dict[str, Any], assignment: str) -> float | None:
    if assignment == "openrouter_default":
        return None
    prefix = "safe" if assignment == "enforcement_safe" else "risky"
    prompt = _float(pair.get(f"{prefix}_prompt_price"))
    completion = _float(pair.get(f"{prefix}_completion_price"))
    if prompt is None or completion is None:
        return None
    return prompt * QUOTE_CAP_INPUT_TOKENS + completion


def run_enforcement_policy_probes(
    model_specs: list[dict[str, str]] | None = None,
    *,
    client: httpx.Client | None = None,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    """Collect one outcome-masked H88 run and return support metadata only."""
    run_id = run_timestamp()
    dt = dt_partition()
    seed_text = os.environ.get("ORCAP_H88_RANDOMIZATION_SEED")
    run_seed = int(seed_text, 0) if seed_text else secrets.randbits(64)
    rng = random.Random(run_seed)
    own_client = client is None
    http = client or httpx.Client(timeout=60)
    candidate_rows: list[dict[str, Any]] = []
    attempt_rows: list[dict[str, Any]] = []
    running_quote_cap = 0.0
    try:
        if model_specs is None:
            rankings_response = http.get(RANKINGS_URL)
            models_response = http.get(MODELS_URL)
            rankings_response.raise_for_status()
            models_response.raise_for_status()
            model_specs = hot_model_specs(rankings_response.json(), models_response.json())
        selected = list(model_specs[:MAX_MODELS])
        rng.shuffle(selected)
        for evaluation_order, spec in enumerate(selected):
            model_id = spec["model_id"]
            canonical_slug = spec["canonical_slug"]
            block_seed = rng.getrandbits(64)
            block_id = f"{STUDY_ID}|{run_id}|{model_id}"
            endpoints_url = f"{API_V1}/models/{model_id}/endpoints"
            stats_url = f"{STATS_URL}?permaslug={quote(canonical_slug, safe='')}&variant=standard"
            endpoint_status = stats_status = None
            pair = None
            reason = "fetch_failed"
            try:
                endpoint_response = http.get(endpoints_url)
                stats_response = http.get(stats_url)
                endpoint_status = int(endpoint_response.status_code)
                stats_status = int(stats_response.status_code)
                if endpoint_response.status_code == 200 and stats_response.status_code == 200:
                    states = public_enforcement_states(
                        endpoint_response.json(), stats_response.json()
                    )
                    pair, reason = select_enforcement_pair(states)
            except httpx.HTTPError as exc:
                reason = type(exc).__name__

            base: dict[str, Any] = {
                "study_id": STUDY_ID,
                "run_ts": run_id,
                "dt": dt,
                "block_id": block_id,
                "model_id": model_id,
                "canonical_slug": canonical_slug,
                "evaluation_order": evaluation_order,
                "run_seed": str(run_seed),
                "block_seed": str(block_seed),
                "assignment_probability": 1 / len(POLICIES),
                "endpoint_http_status": endpoint_status,
                "stats_http_status": stats_status,
                "eligible_pair": pair is not None,
                "request_sent": False,
                "exclusion_reason": None if pair is not None else reason,
                **{column: None for column in CANDIDATE_OPTIONAL_FIELDS},
            }
            if pair is None:
                candidate_rows.append(base)
                continue
            assignment = random.Random(block_seed).choice(POLICIES)
            state_hash = candidate_state_hash(model_id, canonical_slug, pair)
            requested_provider = (
                pair["safe_provider"]
                if assignment == "enforcement_safe"
                else pair["risky_provider"]
                if assignment == "enforcement_risky"
                else None
            )
            cost_cap = quote_cost_cap(pair, assignment)
            base.update(
                {
                    **pair,
                    "candidate_state_hash": state_hash,
                    "assignment": assignment,
                    "assigned_requested_provider": requested_provider,
                    "public_quote_cost_cap_usd": cost_cap,
                }
            )
            if assignment != "openrouter_default" and cost_cap is None:
                base["eligible_pair"] = False
                base["exclusion_reason"] = "assigned_quote_cost_cap_missing"
                candidate_rows.append(base)
                continue
            if cost_cap is not None and cost_cap > MAX_REQUEST_QUOTE_CAP_USD:
                base["eligible_pair"] = False
                base["exclusion_reason"] = "assigned_quote_cost_cap_above_request_limit"
                candidate_rows.append(base)
                continue
            if cost_cap is not None and running_quote_cap + cost_cap > MAX_RUN_QUOTE_CAP_USD:
                base["eligible_pair"] = False
                base["exclusion_reason"] = "run_quote_cap_exceeded"
                candidate_rows.append(base)
                continue

            observed = run_timestamp()
            completion, generation, error, status = _send_probe(
                http,
                model_id,
                provider=requested_provider,
                allow_fallbacks=False,
            )
            attempt = probe_record(
                model_id,
                completion,
                generation,
                observed_at=observed,
                error=error,
                status_code=status,
                requested_provider=requested_provider,
                policy=assignment,
                study_id=STUDY_ID,
                scenario=SCENARIO,
                extra_metadata={
                    "block_id": block_id,
                    "block_seed": str(block_seed),
                    "run_seed": str(run_seed),
                    "assignment_probability": 1 / len(POLICIES),
                    "candidate_state_hash": state_hash,
                    "safe_provider": pair["safe_provider"],
                    "risky_provider": pair["risky_provider"],
                    "safe_enforcement_stress": pair["safe_enforcement_stress"],
                    "risky_enforcement_stress": pair["risky_enforcement_stress"],
                    "public_quote_cost_cap_usd": cost_cap,
                    "first_and_only_exposure": True,
                },
            )
            attempt_rows.append(attempt)
            base["request_sent"] = True
            base["attempt_event_id"] = attempt["event_id"]
            base["request_observed_at"] = observed
            candidate_rows.append(base)
            running_quote_cap += cost_cap or 0.0
    finally:
        if own_client:
            http.close()

    candidate_path = None
    if candidate_rows:
        candidate_path = write_partition(
            pa.Table.from_pylist(candidate_rows),
            "h88_enforcement_policy_candidates",
            run_id,
            dt,
            curated_dir,
        )
    attempt_path = write_attempts(attempt_rows, run_ts=run_id, dt=dt, curated_dir=curated_dir)
    # Never print or return an arm outcome before the analyzer's release gate.
    return {
        "study_id": STUDY_ID,
        "run_ts": run_id,
        "candidate_models": len(candidate_rows),
        "eligible_pairs": sum(bool(row.get("eligible_pair")) for row in candidate_rows),
        "assignments_sent": sum(bool(row.get("request_sent")) for row in candidate_rows),
        "assignment_counts": {
            policy: sum(
                row.get("assignment") == policy and bool(row.get("request_sent"))
                for row in candidate_rows
            )
            for policy in POLICIES
        },
        "pinned_public_quote_cap_usd": running_quote_cap,
        "candidate_path": str(candidate_path) if candidate_path else None,
        "attempt_path": str(attempt_path) if attempt_path else None,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(json.dumps(run_enforcement_policy_probes(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
