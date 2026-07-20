from __future__ import annotations

import copy

import pytest

from orcap.market_measurement import (
    build_market_assignments,
    market_manifest,
    select_quality_items,
)
from orcap.price_experiments import validate_manifest


def candidates() -> list[dict]:
    rows = []
    for block, model, multiplier in (
        ("block-low", "author/low", 1.0),
        ("block-high", "author/high", 4.0),
    ):
        for provider, price in (("a", 1e-7), ("b", 2e-7), ("c", 3e-7)):
            rows.append(
                {
                    "block_id": block,
                    "model_id": model,
                    "shape_id": "short_chat",
                    "provider_name": provider,
                    "endpoint_tag": f"{block}-{provider}",
                    "prompt_price_per_token": price,
                    "completion_price_per_token": price * multiplier,
                    "expected_quote_usd": price * (96 + 8 * multiplier),
                    "conservative_quote_usd": price * (96 + 8 * multiplier),
                    "conservative_input_tokens": 96,
                    "max_output_tokens": 8,
                    "compatible": True,
                }
            )
    return rows


def quality_items() -> list[dict]:
    return [
        {
            "item_id": "mmlu-a",
            "source": "mmlu",
            "grade": "letter",
            "prompt": "Question A. Answer with only A, B, C, or D.",
            "answer": "A",
            "max_tokens": 6,
        },
        {
            "item_id": "mmlu-b",
            "source": "mmlu",
            "grade": "letter",
            "prompt": "Question B. Answer with only A, B, C, or D.",
            "answer": "B",
            "max_tokens": 6,
        },
    ]


def test_assignment_panel_is_deterministic_rectangular_and_complete():
    first, summary = build_market_assignments(
        candidates(), quality_items(), run_id="run-1", seed=17
    )
    second, second_summary = build_market_assignments(
        candidates(), quality_items(), run_id="run-1", seed=17
    )
    assert first == second
    assert summary == second_summary
    assert len(first) == 45
    assert len({row["task_id"] for row in first}) == len(first)
    assert summary["axis_counts"] == {
        "competition": 14,
        "memory": 2,
        "liquidity": 21,
        "quality": 8,
    }
    assert all(row["task_quote_cap_usd"] > 0 for row in first)
    assert all(row["payload_retained"] is False for row in first)
    assert {row["concurrency_level"] for row in first if row["experiment_axis"] == "liquidity"} == {
        1,
        2,
        4,
    }
    batches = {}
    for row in first:
        if row["experiment_axis"] == "liquidity":
            batches.setdefault(row["execution_batch"], []).append(row)
    assert all(len(rows) == rows[0]["concurrency_level"] for rows in batches.values())
    assert {row["policy"] for row in first if row["experiment_axis"] == "quality"} == {
        "quality_default",
        "quality_a",
        "quality_b",
        "quality_c",
    }
    assert all(
        row["max_output_tokens"] == 64 for row in first if row["experiment_axis"] == "quality"
    )


def test_plan_has_no_prompt_answer_or_secret_payload_fields():
    assignments, summary = build_market_assignments(
        candidates(), quality_items(), run_id="run-1", seed=17
    )
    bundle = {
        "candidates": candidates(),
        "assignments": assignments,
        "summary": summary,
    }

    def keys(value):
        if isinstance(value, dict):
            nested = set().union(*(keys(item) for item in value.values()))
            return set(value) | nested
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    present = {str(key).lower() for key in keys(bundle)}
    for forbidden in (
        "prompt",
        "messages",
        "answer",
        "completion",
        "api_key",
        "authorization",
        "raw_response",
    ):
        assert forbidden not in present
    assert "quality_answer_sha256" in present


def test_quality_item_selection_is_seeded_and_mmlu_only():
    pool = quality_items() + [
        {
            "item_id": "gsm",
            "source": "gsm8k",
            "grade": "numeric",
            "prompt": "1+1",
            "answer": "2",
            "max_tokens": 10,
        }
    ]
    assert select_quality_items(pool, seed=3) == select_quality_items(pool, seed=3)
    assert {item["source"] for item in select_quality_items(pool, seed=3)} == {"mmlu"}


def test_manifest_replay_detects_assignment_tampering():
    assignments, summary = build_market_assignments(
        candidates(), quality_items(), run_id="run-1", seed=17
    )
    manifest = market_manifest(candidates(), assignments, summary)
    validate_manifest(manifest, candidates(), assignments, summary)
    changed = copy.deepcopy(assignments)
    changed[0]["policy"] = "tampered"
    with pytest.raises(ValueError, match="manifest mismatch"):
        validate_manifest(manifest, candidates(), changed, summary)


def test_fewer_than_three_providers_produces_no_paid_plan():
    assignments, summary = build_market_assignments(
        candidates()[:2], quality_items(), run_id="run-1", seed=17
    )
    assert assignments == []
    assert summary["planned_tasks"] == 0
    assert summary["planned_quote_cap_usd"] == 0


def test_seeded_top_pool_rotation_diversifies_models_without_outcomes():
    rows = []
    for index in range(6):
        for provider_index, provider in enumerate(("a", "b", "c"), start=1):
            price = provider_index * (1 + index / 20) * 1e-7
            rows.append(
                {
                    "block_id": f"block-{index}",
                    "model_id": f"author/model-{index}",
                    "shape_id": "short_chat",
                    "provider_name": provider,
                    "endpoint_tag": f"tag-{index}-{provider}",
                    "prompt_price_per_token": price,
                    "completion_price_per_token": price,
                    "expected_quote_usd": price * 104,
                    "conservative_quote_usd": price * 104,
                    "conservative_input_tokens": 96,
                    "max_output_tokens": 8,
                    "compatible": True,
                }
            )
    selected = set()
    for seed in range(12):
        assignments, summary = build_market_assignments(
            rows, quality_items(), run_id=f"run-{seed}", seed=seed
        )
        selected.add(assignments[0]["model_id"])
        assert summary["selection_pool_size"] == 5
        assert 1 <= summary["selected_information_rank"] <= 5
        assert summary["selection_rule"].startswith("seeded_rotation")

    assert len(selected) >= 3
