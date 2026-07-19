"""Pure planning primitives for the paid market-measurement campaign.

Network I/O lives in :mod:`orcap.capture_market_measurement`.  Keeping the
planner pure makes the candidate freeze, assignment randomization, quote-cap
budget, and manifest replay independently testable.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

import pyarrow as pa

from .price_experiments import (
    broad_cap,
    collapse_provider_candidates,
    plan_manifest,
    rectangular_cap,
)

STUDY_ID = "openrouter-market-measurement-v1"
PLAN_VERSION = "market-measurement-plan-v1"

MARKET_MEASUREMENT_ASSIGNMENT_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("run_id", pa.string()),
        ("block_id", pa.string()),
        ("task_id", pa.string()),
        ("model_id", pa.string()),
        ("shape_id", pa.string()),
        ("experiment_axis", pa.string()),
        ("policy", pa.string()),
        ("replicate_index", pa.int32()),
        ("policy_order", pa.int32()),
        ("execution_batch", pa.string()),
        ("concurrency_level", pa.int32()),
        ("concurrency_slot", pa.int32()),
        ("requested_provider", pa.string()),
        ("requested_endpoint_tag", pa.string()),
        ("provider_order_tags", pa.list_(pa.string())),
        ("provider_only_tags", pa.list_(pa.string())),
        ("provider_sort", pa.string()),
        ("allow_fallbacks", pa.bool_()),
        ("max_price_prompt_per_mtok", pa.float64()),
        ("max_price_completion_per_mtok", pa.float64()),
        ("task_quote_cap_usd", pa.float64()),
        ("conservative_input_tokens", pa.int64()),
        ("max_output_tokens", pa.int64()),
        ("session_group", pa.string()),
        ("quality_item_id", pa.string()),
        ("quality_source", pa.string()),
        ("quality_grade", pa.string()),
        ("quality_answer_sha256", pa.string()),
        ("assignment_seed", pa.string()),
        ("manifest_sha256", pa.string()),
        ("preflight_only", pa.bool_()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

MARKET_MEASUREMENT_QUALITY_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("run_id", pa.string()),
        ("task_id", pa.string()),
        ("observed_at", pa.string()),
        ("model_id", pa.string()),
        ("policy", pa.string()),
        ("quality_item_id", pa.string()),
        ("quality_source", pa.string()),
        ("requested_provider", pa.string()),
        ("selected_provider", pa.string()),
        ("http_status", pa.int32()),
        ("extracted_answer", pa.string()),
        ("correct", pa.bool_()),
        ("output_sha256", pa.string()),
        ("output_norm_sha256", pa.string()),
        ("output_len_chars", pa.int64()),
        ("input_tokens", pa.int64()),
        ("output_tokens", pa.int64()),
        ("cost_usd", pa.float64()),
        ("latency_ms", pa.float64()),
        ("manifest_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _quote_cap(
    cap: Mapping[str, Any], *, input_tokens: int, output_tokens: int
) -> float:
    return (
        float(cap["prompt_per_mtok"]) * input_tokens / 1_000_000
        + float(cap["completion_per_mtok"]) * output_tokens / 1_000_000
    )


def _block_score(rows: Sequence[Mapping[str, Any]]) -> float:
    candidates = collapse_provider_candidates(rows)
    if len(candidates) < 3:
        return float("-inf")
    quotes = [float(row["conservative_quote_usd"]) for row in candidates]
    positive = [value for value in quotes if math.isfinite(value) and value > 0]
    if len(positive) < 3:
        positive = [float(row["expected_quote_usd"]) for row in candidates]
        positive = [value for value in positive if math.isfinite(value) and value > 0]
    if len(positive) < 3:
        return float("-inf")
    return math.log1p(len(candidates)) * math.log(max(positive) / min(positive))


def select_quality_items(
    items: Sequence[Mapping[str, Any]], *, seed: int, count: int = 2
) -> list[dict[str, Any]]:
    """Choose a deterministic outcome-free MMLU subset."""
    eligible = [
        dict(item)
        for item in items
        if item.get("source") == "mmlu"
        and item.get("grade") == "letter"
        and item.get("item_id")
        and item.get("answer")
        and int(item.get("max_tokens") or 0) > 0
    ]
    if len(eligible) < count:
        raise ValueError("quality item pool is too small")
    rng = random.Random(seed ^ 0x51A17)
    return rng.sample(sorted(eligible, key=lambda item: str(item["item_id"])), count)


def build_market_assignments(
    candidate_rows: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    seed: int,
    max_blocks: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create the frozen competition, memory, liquidity, and quality panel."""
    if max_blocks != 1:
        raise ValueError("v1 freezes exactly one information-maximizing block")
    by_block: dict[str, list[Mapping[str, Any]]] = {}
    for row in candidate_rows:
        block_id = str(row.get("block_id") or "")
        if block_id:
            by_block.setdefault(block_id, []).append(row)
    rng = random.Random(seed)
    tie_breaks = {block_id: rng.random() for block_id in sorted(by_block)}
    ranked = sorted(
        by_block,
        key=lambda block_id: (_block_score(by_block[block_id]), tie_breaks[block_id]),
        reverse=True,
    )
    eligible = [block_id for block_id in ranked if math.isfinite(_block_score(by_block[block_id]))]
    if not eligible:
        return [], {
            "study_id": STUDY_ID,
            "plan_version": PLAN_VERSION,
            "run_id": run_id,
            "seed": str(seed),
            "candidate_blocks": len(by_block),
            "planned_blocks": 0,
            "planned_tasks": 0,
            "planned_quote_cap_usd": 0.0,
            "selected_block_scores": [],
            "skipped_blocks": [
                {"block_id": block_id, "reason": "fewer_than_three_or_unpriced_providers"}
                for block_id in sorted(by_block)
            ],
        }

    block_id = eligible[0]
    rows = by_block[block_id]
    candidates = collapse_provider_candidates(rows)
    a, b, c = candidates[0], candidates[1], candidates[2]
    broad = broad_cap(rows)
    top_two = rectangular_cap(rows, 2)
    shape_row = candidates[0]
    input_tokens = int(shape_row.get("conservative_input_tokens") or 96)
    output_tokens = int(shape_row.get("max_output_tokens") or 8)
    model_id = str(shape_row.get("model_id") or "")
    shape_id = str(shape_row.get("shape_id") or "short_chat")
    a_tag = str(a.get("endpoint_tag") or "")
    b_tag = str(b.get("endpoint_tag") or "")
    c_tag = str(c.get("endpoint_tag") or "")
    all_tags = [str(row.get("endpoint_tag") or "") for row in candidates]
    if not a_tag or not b_tag or not c_tag or any(not tag for tag in all_tags):
        raise ValueError("eligible market-measurement candidates need exact endpoint tags")

    assignments: list[dict[str, Any]] = []

    def add(
        *,
        axis: str,
        policy: str,
        replicate: int,
        cap: Mapping[str, Any] = broad,
        requested: Mapping[str, Any] | None = None,
        order: list[str] | None = None,
        only: list[str] | None = None,
        provider_sort: str | None = None,
        allow_fallbacks: bool = True,
        execution_batch: str | None = None,
        concurrency_level: int = 1,
        concurrency_slot: int = 0,
        session_group: str | None = None,
        quality_item: Mapping[str, Any] | None = None,
    ) -> None:
        quality = quality_item is not None
        task_shape = "quality_mmlu" if quality else shape_id
        task_input = (
            max(128, math.ceil(len(str(quality_item["prompt"])) / 3))
            if quality
            else input_tokens
        )
        # Six tokens can be consumed entirely by mandatory/minimal reasoning.
        # The first paid pilot established 64 as the prospective floor.
        task_output = max(int(quality_item["max_tokens"]), 64) if quality else output_tokens
        task_id = f"{STUDY_ID}|{run_id}|{block_id}|{policy}|{replicate}"
        requested_provider = str(requested.get("provider_name") or "") if requested else None
        requested_tag = str(requested.get("endpoint_tag") or "") if requested else None
        assignments.append(
            {
                "study_id": STUDY_ID,
                "plan_version": PLAN_VERSION,
                "run_id": run_id,
                "block_id": block_id,
                "task_id": task_id,
                "model_id": model_id,
                "shape_id": task_shape,
                "experiment_axis": axis,
                "policy": policy,
                "replicate_index": replicate,
                "execution_batch": execution_batch or task_id,
                "concurrency_level": concurrency_level,
                "concurrency_slot": concurrency_slot,
                "requested_provider": requested_provider,
                "requested_endpoint_tag": requested_tag,
                "provider_order_tags": order,
                "provider_only_tags": only,
                "provider_sort": provider_sort,
                "allow_fallbacks": allow_fallbacks,
                "max_price_prompt_per_mtok": float(cap["prompt_per_mtok"]),
                "max_price_completion_per_mtok": float(cap["completion_per_mtok"]),
                "task_quote_cap_usd": _quote_cap(
                    cap, input_tokens=task_input, output_tokens=task_output
                ),
                "conservative_input_tokens": task_input,
                "max_output_tokens": task_output,
                "session_group": session_group or f"fresh|{task_id}",
                "quality_item_id": str(quality_item["item_id"]) if quality else None,
                "quality_source": str(quality_item["source"]) if quality else None,
                "quality_grade": str(quality_item["grade"]) if quality else None,
                "quality_answer_sha256": _sha(str(quality_item["answer"])) if quality else None,
                "assignment_seed": str(seed),
                "payload_retained": False,
            }
        )

    for policy, count in {
        "default_broad": 4,
        "price_sorted": 2,
        "capped_top2": 2,
        "ordered_ab": 1,
        "ordered_ba": 1,
        "leave_cheapest_out": 2,
        "pinned_a": 1,
        "pinned_b": 1,
    }.items():
        if policy == "capped_top2" and top_two is None:
            continue
        for replicate in range(count):
            kwargs: dict[str, Any] = {}
            cap = top_two if policy == "capped_top2" else broad
            if policy == "price_sorted":
                kwargs["provider_sort"] = "price"
            elif policy == "ordered_ab":
                kwargs["order"] = [a_tag, b_tag]
            elif policy == "ordered_ba":
                kwargs["order"] = [b_tag, a_tag]
            elif policy == "leave_cheapest_out":
                kwargs["only"] = all_tags[1:]
            elif policy in {"pinned_a", "pinned_b"}:
                selected = a if policy == "pinned_a" else b
                tag = a_tag if policy == "pinned_a" else b_tag
                kwargs.update(
                    requested=selected,
                    order=[tag],
                    only=[tag],
                    allow_fallbacks=False,
                )
            add(
                axis="competition",
                policy=policy,
                replicate=replicate,
                cap=cap or broad,
                **kwargs,
            )

    sticky_group = f"sticky|{STUDY_ID}|{run_id}|{block_id}"
    add(
        axis="memory",
        policy="default_sticky_seed",
        replicate=0,
        session_group=sticky_group,
    )
    add(
        axis="memory",
        policy="default_sticky_repeat",
        replicate=0,
        session_group=sticky_group,
    )

    for label, selected, tag in (("a", a, a_tag), ("b", b, b_tag), ("c", c, c_tag)):
        for level in (1, 2, 4):
            batch = f"liquidity|{block_id}|{label}|c{level}"
            for slot in range(level):
                add(
                    axis="liquidity",
                    policy=f"liquidity_{label}_c{level}",
                    replicate=slot,
                    requested=selected,
                    order=[tag],
                    only=[tag],
                    allow_fallbacks=False,
                    execution_batch=batch,
                    concurrency_level=level,
                    concurrency_slot=slot,
                )

    for item in quality_items:
        for label, selected, tag in (
            ("default", None, None),
            ("a", a, a_tag),
            ("b", b, b_tag),
            ("c", c, c_tag),
        ):
            kwargs = {}
            if selected is not None and tag is not None:
                kwargs = {
                    "requested": selected,
                    "order": [tag],
                    "only": [tag],
                    "allow_fallbacks": False,
                }
            add(
                axis="quality",
                policy=f"quality_{label}",
                replicate=int(_sha(str(item["item_id"]))[:6], 16),
                quality_item=item,
                **kwargs,
            )

    rng.shuffle(assignments)
    for position, assignment in enumerate(assignments):
        assignment["policy_order"] = position

    summary = {
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "candidate_blocks": len(by_block),
        "planned_blocks": 1,
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(
            float(row["task_quote_cap_usd"]) for row in assignments
        ),
        "selected_block_scores": [
            {"block_id": block_id, "public_information_score": _block_score(rows)}
        ],
        "selected_quality_items": [str(item["item_id"]) for item in quality_items],
        "axis_counts": {
            axis: sum(row["experiment_axis"] == axis for row in assignments)
            for axis in ("competition", "memory", "liquidity", "quality")
        },
        "skipped_blocks": [
            {"block_id": other, "reason": "lower_public_information_score"}
            for other in eligible[1:]
        ],
    }
    return assignments, summary


def market_manifest(
    candidates: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    return plan_manifest(candidates, assignments, summary)
