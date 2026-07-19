"""Plan-first primitives for paid OpenRouter price-response experiments.

The functions in this module are deliberately independent from network I/O.
They turn an outcome-free public candidate menu into deterministic assignments,
validate rectangular OpenRouter price caps, hash immutable plans, and enforce
run/day/campaign spend limits before any request can be sent.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa

STUDY_ID = "openrouter-price-response-v1"
EVENT_STUDY_ID = "openrouter-price-event-v1"
PLAN_VERSION = "price-response-plan-v1"

ARM_COUNTS: dict[str, int] = {
    "default_loose_fresh": 6,
    "default_top2_cap": 2,
    "default_top1_cap": 2,
    "sort_price_loose": 2,
    "ordered_ab": 1,
    "ordered_ba": 1,
    "pinned_a": 1,
    "pinned_b": 1,
}

PRICE_RESPONSE_CANDIDATE_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("observed_at", pa.string()),
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("block_id", pa.string()),
        ("model_id", pa.string()),
        ("shape_id", pa.string()),
        ("provider_name", pa.string()),
        ("endpoint_tag", pa.string()),
        ("endpoint_name", pa.string()),
        ("prompt_price_per_token", pa.float64()),
        ("completion_price_per_token", pa.float64()),
        ("expected_quote_usd", pa.float64()),
        ("conservative_quote_usd", pa.float64()),
        ("conservative_input_tokens", pa.int64()),
        ("max_output_tokens", pa.int64()),
        ("compatible", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("snapshot_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

PRICE_RESPONSE_ASSIGNMENT_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("run_id", pa.string()),
        ("block_id", pa.string()),
        ("task_id", pa.string()),
        ("model_id", pa.string()),
        ("shape_id", pa.string()),
        ("policy", pa.string()),
        ("replicate_index", pa.int32()),
        ("policy_order", pa.int32()),
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
        ("assignment_seed", pa.string()),
        ("manifest_sha256", pa.string()),
        ("preflight_only", pa.bool_()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

PAID_SPEND_LEDGER_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("run_id", pa.string()),
        ("task_id", pa.string()),
        ("observed_at", pa.string()),
        ("cost_usd", pa.float64()),
        ("attempted", pa.bool_()),
        ("manifest_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


@dataclass(frozen=True)
class BudgetLimits:
    per_run_usd: float
    per_day_usd: float
    campaign_usd: float

    def validate(self) -> None:
        values = (self.per_run_usd, self.per_day_usd, self.campaign_usd)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("budget limits must be finite and positive")
        if self.per_run_usd > self.per_day_usd or self.per_day_usd > self.campaign_usd:
            raise ValueError("budget limits must satisfy run <= day <= campaign")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _canonical(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def provider_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def collapse_provider_candidates(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse endpoint variants to the cheapest compatible row per provider."""
    best: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not bool(raw.get("compatible", True)):
            continue
        provider = provider_key(raw.get("provider_name"))
        prompt = _number(raw.get("prompt_price_per_token"))
        completion = _number(raw.get("completion_price_per_token"))
        quote = _number(raw.get("expected_quote_usd"))
        if not provider or prompt is None or completion is None or quote is None:
            continue
        if min(prompt, completion, quote) <= 0:
            continue
        row = dict(raw)
        row["provider_key"] = provider
        current = best.get(provider)
        if current is None or quote < float(current["expected_quote_usd"]):
            best[provider] = row
    return sorted(
        best.values(),
        key=lambda row: (float(row["expected_quote_usd"]), str(row["provider_key"])),
    )


def rectangular_cap(
    rows: Sequence[Mapping[str, Any]], target_count: int
) -> dict[str, Any] | None:
    """Return a component-wise cap admitting exactly the cheapest ``target_count``.

    OpenRouter's max-price control is rectangular in prompt/completion prices.
    A target set ordered by all-in quote is not always separable by such a
    rectangle. Nonseparable sets return ``None`` rather than silently admitting
    extra providers.
    """
    candidates = collapse_provider_candidates(rows)
    if target_count <= 0 or len(candidates) < target_count:
        return None
    included = candidates[:target_count]
    prompt = max(float(row["prompt_price_per_token"]) for row in included)
    completion = max(float(row["completion_price_per_token"]) for row in included)
    tolerance = 1e-15
    admitted = [
        row
        for row in candidates
        if float(row["prompt_price_per_token"]) <= prompt + tolerance
        and float(row["completion_price_per_token"]) <= completion + tolerance
    ]
    if {row["provider_key"] for row in admitted} != {
        row["provider_key"] for row in included
    }:
        return None
    return {
        "target_count": target_count,
        "prompt_per_mtok": prompt * 1_000_000,
        "completion_per_mtok": completion * 1_000_000,
        "admitted_provider_keys": [str(row["provider_key"]) for row in included],
    }


def broad_cap(rows: Sequence[Mapping[str, Any]], reference_count: int = 3) -> dict[str, Any]:
    candidates = collapse_provider_candidates(rows)
    if len(candidates) < 2:
        raise ValueError("broad price cap needs at least two compatible providers")
    reference = candidates[: min(reference_count, len(candidates))]
    return {
        "prompt_per_mtok": 2
        * max(float(row["prompt_price_per_token"]) for row in reference)
        * 1_000_000,
        "completion_per_mtok": 2
        * max(float(row["completion_price_per_token"]) for row in reference)
        * 1_000_000,
    }


def _task_cap(row: Mapping[str, Any], cap: Mapping[str, Any]) -> float:
    input_tokens = int(row.get("conservative_input_tokens") or 96)
    output_tokens = int(row.get("max_output_tokens") or 8)
    return (
        float(cap["prompt_per_mtok"]) / 1_000_000 * input_tokens
        + float(cap["completion_per_mtok"]) / 1_000_000 * output_tokens
    )


def build_response_assignments(
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    seed: int,
    max_tasks: int = 48,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create deterministic randomized assignments from frozen public menus."""
    if max_tasks <= 0:
        raise ValueError("max_tasks must be positive")
    by_block: dict[str, list[Mapping[str, Any]]] = {}
    for row in candidate_rows:
        block_id = str(row.get("block_id") or "")
        if block_id:
            by_block.setdefault(block_id, []).append(row)

    rng = random.Random(seed)
    block_ids = sorted(by_block)
    rng.shuffle(block_ids)
    assignments: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for block_id in block_ids:
        rows = by_block[block_id]
        candidates = collapse_provider_candidates(rows)
        if len(candidates) < 2:
            skipped.append({"block_id": block_id, "reason": "fewer_than_two_providers"})
            continue
        if len(assignments) + sum(ARM_COUNTS.values()) > max_tasks:
            skipped.append({"block_id": block_id, "reason": "max_tasks"})
            continue
        loose = broad_cap(rows)
        cap_two = rectangular_cap(rows, 2)
        cap_one = rectangular_cap(rows, 1)
        a, b = candidates[0], candidates[1]
        arm_rows: list[dict[str, Any]] = []
        for arm, count in ARM_COUNTS.items():
            for replicate in range(count):
                if arm == "default_top2_cap" and cap_two is None:
                    continue
                if arm == "default_top1_cap" and cap_one is None:
                    continue
                if arm == "default_top2_cap":
                    cap = cap_two
                elif arm == "default_top1_cap":
                    cap = cap_one
                else:
                    cap = loose
                requested_provider = None
                requested_endpoint_tag = None
                order_tags: list[str] | None = None
                only_tags: list[str] | None = None
                allow_fallbacks = True
                provider_sort = None
                if arm == "sort_price_loose":
                    provider_sort = "price"
                elif arm in {"ordered_ab", "ordered_ba"}:
                    pair = [a, b] if arm == "ordered_ab" else [b, a]
                    order_tags = [str(item.get("endpoint_tag") or "") for item in pair]
                    if any(not tag for tag in order_tags):
                        continue
                elif arm in {"pinned_a", "pinned_b"}:
                    selected = a if arm == "pinned_a" else b
                    requested_provider = str(selected.get("provider_name") or "")
                    requested_endpoint_tag = str(selected.get("endpoint_tag") or "")
                    if not requested_provider or not requested_endpoint_tag:
                        continue
                    order_tags = [requested_endpoint_tag]
                    only_tags = [requested_endpoint_tag]
                    allow_fallbacks = False
                shape_row = candidates[0]
                arm_rows.append(
                    {
                        "study_id": STUDY_ID,
                        "plan_version": PLAN_VERSION,
                        "run_id": run_id,
                        "block_id": block_id,
                        "task_id": f"{block_id}|{arm}|{replicate}",
                        "model_id": str(shape_row.get("model_id") or ""),
                        "shape_id": str(shape_row.get("shape_id") or ""),
                        "policy": arm,
                        "replicate_index": replicate,
                        "requested_provider": requested_provider,
                        "requested_endpoint_tag": requested_endpoint_tag,
                        "provider_order_tags": order_tags,
                        "provider_only_tags": only_tags,
                        "provider_sort": provider_sort,
                        "allow_fallbacks": allow_fallbacks,
                        "max_price_prompt_per_mtok": float(cap["prompt_per_mtok"]),
                        "max_price_completion_per_mtok": float(
                            cap["completion_per_mtok"]
                        ),
                        "task_quote_cap_usd": _task_cap(shape_row, cap),
                        "conservative_input_tokens": int(
                            shape_row.get("conservative_input_tokens") or 96
                        ),
                        "max_output_tokens": int(shape_row.get("max_output_tokens") or 8),
                        "session_group": f"fresh|{block_id}|{arm}|{replicate}",
                        "assignment_seed": str(seed),
                        "payload_retained": False,
                    }
                )
        rng.shuffle(arm_rows)
        for position, row in enumerate(arm_rows):
            row["policy_order"] = position
        assignments.extend(arm_rows)

    summary = {
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "candidate_blocks": len(by_block),
        "planned_blocks": len({row["block_id"] for row in assignments}),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(
            float(row["task_quote_cap_usd"]) for row in assignments
        ),
        "skipped_blocks": skipped,
    }
    return assignments, summary


def plan_manifest(
    candidate_rows: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_payload = sorted((dict(row) for row in candidate_rows), key=_canonical)
    assignment_payload = sorted((dict(row) for row in assignments), key=_canonical)
    manifest = {
        "candidate_sha256": sha256_json(candidate_payload),
        "assignment_sha256": sha256_json(assignment_payload),
        "summary_sha256": sha256_json(dict(summary)),
        "candidate_rows": len(candidate_payload),
        "assignment_rows": len(assignment_payload),
        "planned_quote_cap_usd": float(summary.get("planned_quote_cap_usd") or 0),
        "study_id": str(summary.get("study_id") or STUDY_ID),
        "run_id": str(summary.get("run_id") or ""),
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    return manifest


def validate_manifest(
    manifest: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    expected = plan_manifest(candidate_rows, assignments, summary)
    if dict(manifest) != expected:
        raise ValueError("price-experiment plan manifest mismatch")


def check_budget(
    *,
    planned_usd: float,
    spent_day_usd: float,
    spent_campaign_usd: float,
    limits: BudgetLimits,
) -> None:
    limits.validate()
    values = (planned_usd, spent_day_usd, spent_campaign_usd)
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("spend inputs must be finite and non-negative")
    if planned_usd > limits.per_run_usd + 1e-12:
        raise RuntimeError("planned spend exceeds per-run cap")
    if spent_day_usd + planned_usd > limits.per_day_usd + 1e-12:
        raise RuntimeError("planned spend exceeds rolling day cap")
    if spent_campaign_usd + planned_usd > limits.campaign_usd + 1e-12:
        raise RuntimeError("planned spend exceeds campaign cap")


def campaign_open(start: str, end: str, now: datetime | None = None) -> bool:
    def parse(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    now = (now or datetime.now(UTC)).astimezone(UTC)
    return parse(start) <= now < parse(end)


def spent_from_rows(rows: Iterable[Mapping[str, Any]], *, study_id: str = STUDY_ID) -> float:
    seen: set[str] = set()
    total = 0.0
    for row in rows:
        if str(row.get("study_id") or "") != study_id:
            continue
        task_id = str(row.get("task_id") or row.get("event_id") or "")
        if not task_id or task_id in seen:
            continue
        amount = _number(row.get("cost_usd"))
        if amount is None or amount < 0:
            continue
        seen.add(task_id)
        total += amount
    return total
