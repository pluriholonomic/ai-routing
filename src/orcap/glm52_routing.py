"""Pure prospective assignment logic for the GLM-5.2 routing campaign."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from .price_experiments import collapse_provider_candidates, plan_manifest, provider_key

STUDY_ID = "openrouter-glm52-routing-v1"
PLAN_VERSION = "glm52-routing-plan-v1"
MODEL_ID = "z-ai/glm-5.2"
PAIR_KEYS = ("streamlake", "novita")
BENCHMARK_KEY = "z.ai"
TARGET_KEYS = PAIR_KEYS + (BENCHMARK_KEY,)


def _cap(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    if not rows:
        raise ValueError("a routing policy cannot have an empty provider set")
    # A one-percent numeric margin prevents decimal serialization from turning
    # an intended inclusive cap into an accidental exclusion.
    return {
        "prompt_per_mtok": 1.01
        * max(float(row["prompt_price_per_token"]) for row in rows)
        * 1_000_000,
        "completion_per_mtok": 1.01
        * max(float(row["completion_price_per_token"]) for row in rows)
        * 1_000_000,
    }


def _quote_cap(cap: Mapping[str, float], *, input_tokens: int, output_tokens: int) -> float:
    return (
        float(cap["prompt_per_mtok"]) * input_tokens / 1_000_000
        + float(cap["completion_per_mtok"]) * output_tokens / 1_000_000
    )


def build_assignments(
    candidate_rows: Sequence[Mapping[str, Any]], *, run_id: str, seed: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Freeze ten low-cost tasks around one complete GLM-5.2 public menu."""
    candidates = collapse_provider_candidates(candidate_rows)
    by_key = {provider_key(row.get("provider_name")): row for row in candidates}
    missing = [key for key in TARGET_KEYS if key not in by_key]
    if missing or len(candidates) < 5:
        return [], {
            "study_id": STUDY_ID,
            "plan_version": PLAN_VERSION,
            "run_id": run_id,
            "seed": str(seed),
            "planned_blocks": 0,
            "planned_tasks": 0,
            "planned_quote_cap_usd": 0.0,
            "candidate_provider_count": len(candidates),
            "target_provider_keys": list(TARGET_KEYS),
            "missing_target_provider_keys": missing,
            "skip_reason": "missing_target_or_fewer_than_five_compatible_providers",
        }

    shape = candidates[0]
    block_id = str(shape.get("block_id") or "")
    input_tokens = int(shape.get("conservative_input_tokens") or 96)
    output_tokens = int(shape.get("max_output_tokens") or 8)
    all_tags = [str(row.get("endpoint_tag") or "") for row in candidates]
    if not block_id or any(not tag for tag in all_tags):
        raise ValueError("GLM-5.2 assignments require a block id and exact endpoint tags")

    all_cap = _cap(candidates)
    pair_rows = [by_key[key] for key in PAIR_KEYS]
    policies: list[dict[str, Any]] = [
        {"policy": "default_broad", "replicate": 0},
        {"policy": "default_broad", "replicate": 1},
        {"policy": "price_sorted", "replicate": 0, "provider_sort": "price"},
    ]
    for key in TARGET_KEYS:
        row = by_key[key]
        tag = str(row["endpoint_tag"])
        policies.append(
            {
                "policy": f"pinned_{key.replace('.', '_')}",
                "replicate": 0,
                "requested": row,
                "only": [tag],
                "order": [tag],
                "allow_fallbacks": False,
                "cap": _cap([row]),
            }
        )
    for key in PAIR_KEYS:
        kept = [row for row in candidates if provider_key(row.get("provider_name")) != key]
        policies.append(
            {
                "policy": f"exclude_{key}",
                "replicate": 0,
                "only": [str(row["endpoint_tag"]) for row in kept],
                "cap": _cap(kept),
            }
        )
    without_pair = [
        row for row in candidates if provider_key(row.get("provider_name")) not in PAIR_KEYS
    ]
    policies.extend(
        [
            {
                "policy": "exclude_both_cutters",
                "replicate": 0,
                "only": [str(row["endpoint_tag"]) for row in without_pair],
                "cap": _cap(without_pair),
            },
            {
                "policy": "pair_only",
                "replicate": 0,
                "only": [str(row["endpoint_tag"]) for row in pair_rows],
                "cap": _cap(pair_rows),
            },
        ]
    )

    assignments: list[dict[str, Any]] = []
    for spec in policies:
        requested = spec.get("requested")
        cap = spec.get("cap") or all_cap
        policy = str(spec["policy"])
        replicate = int(spec["replicate"])
        task_id = f"{block_id}|{policy}|{replicate}"
        assignments.append(
            {
                "study_id": STUDY_ID,
                "plan_version": PLAN_VERSION,
                "run_id": run_id,
                "block_id": block_id,
                "task_id": task_id,
                "model_id": MODEL_ID,
                "shape_id": str(shape.get("shape_id") or "short_chat"),
                "policy": policy,
                "replicate_index": replicate,
                "requested_provider": (
                    str(requested.get("provider_name") or "") if requested else None
                ),
                "requested_endpoint_tag": (
                    str(requested.get("endpoint_tag") or "") if requested else None
                ),
                "provider_order_tags": spec.get("order"),
                "provider_only_tags": spec.get("only"),
                "provider_sort": spec.get("provider_sort"),
                "allow_fallbacks": bool(spec.get("allow_fallbacks", True)),
                "max_price_prompt_per_mtok": float(cap["prompt_per_mtok"]),
                "max_price_completion_per_mtok": float(cap["completion_per_mtok"]),
                "task_quote_cap_usd": _quote_cap(
                    cap, input_tokens=input_tokens, output_tokens=output_tokens
                ),
                "conservative_input_tokens": input_tokens,
                "max_output_tokens": output_tokens,
                "session_group": f"fresh|{task_id}",
                "assignment_seed": str(seed),
                "payload_retained": False,
            }
        )

    random.Random(seed).shuffle(assignments)
    for position, assignment in enumerate(assignments):
        assignment["policy_order"] = position
    summary = {
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "planned_blocks": 1,
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(float(row["task_quote_cap_usd"]) for row in assignments),
        "candidate_provider_count": len(candidates),
        "target_provider_keys": list(TARGET_KEYS),
        "missing_target_provider_keys": [],
        "policy_counts": {
            policy: sum(row["policy"] == policy for row in assignments)
            for policy in sorted({row["policy"] for row in assignments})
        },
        "randomization": "seeded_within-block policy order; every task uses a fresh session",
    }
    return assignments, summary


def manifest(
    candidates: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    return plan_manifest(candidates, assignments, summary)
