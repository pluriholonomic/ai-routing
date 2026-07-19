from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from orcap.price_experiments import (
    ARM_COUNTS,
    BudgetLimits,
    build_response_assignments,
    campaign_open,
    check_budget,
    collapse_provider_candidates,
    plan_manifest,
    rectangular_cap,
    spent_from_rows,
    validate_manifest,
)


def candidate(
    provider: str,
    quote: float,
    *,
    prompt: float | None = None,
    completion: float | None = None,
    block: str = "block-1",
) -> dict:
    return {
        "block_id": block,
        "model_id": "author/model",
        "shape_id": "short_chat",
        "provider_name": provider,
        "endpoint_tag": f"tag-{provider}",
        "prompt_price_per_token": prompt or quote / 104,
        "completion_price_per_token": completion or quote / 104,
        "expected_quote_usd": quote,
        "conservative_input_tokens": 96,
        "max_output_tokens": 8,
        "compatible": True,
    }


def test_candidate_collapse_keeps_cheapest_endpoint_per_provider():
    rows = [candidate("a", 0.03), candidate("a", 0.01), candidate("b", 0.02)]
    collapsed = collapse_provider_candidates(rows)
    assert [row["provider_key"] for row in collapsed] == ["a", "b"]
    assert collapsed[0]["expected_quote_usd"] == 0.01


@pytest.mark.parametrize("providers", [2, 3, 5, 8])
def test_rectangular_cap_exact_for_monotone_price_menus(providers: int):
    rows = [candidate(f"p{i}", 0.01 * (i + 1)) for i in range(providers)]
    for target in range(1, providers + 1):
        cap = rectangular_cap(rows, target)
        assert cap is not None
        assert len(cap["admitted_provider_keys"]) == target


def test_rectangular_cap_rejects_nonseparable_target():
    rows = [
        candidate("a", 1.0, prompt=1e-6, completion=9e-6),
        candidate("b", 2.0, prompt=9e-6, completion=1e-6),
        candidate("c", 3.0, prompt=5e-6, completion=5e-6),
    ]
    assert rectangular_cap(rows, 2) is None


def test_assignment_plan_is_deterministic_balanced_and_bounded():
    rows = [candidate(f"p{i}", 0.001 * (i + 1)) for i in range(4)]
    first, first_summary = build_response_assignments(
        rows, run_id="r1", seed=17, max_tasks=48
    )
    second, second_summary = build_response_assignments(
        rows, run_id="r1", seed=17, max_tasks=48
    )
    assert first == second
    assert first_summary == second_summary
    assert len(first) == sum(ARM_COUNTS.values())
    counts = {}
    for row in first:
        counts[row["policy"]] = counts.get(row["policy"], 0) + 1
        assert row["task_quote_cap_usd"] > 0
        assert row["payload_retained"] is False
    assert counts == ARM_COUNTS
    assert len({row["task_id"] for row in first}) == len(first)


def test_manifest_rejects_candidate_assignment_or_summary_tampering():
    rows = [candidate(f"p{i}", 0.001 * (i + 1)) for i in range(3)]
    assignments, summary = build_response_assignments(rows, run_id="r1", seed=4)
    manifest = plan_manifest(rows, assignments, summary)
    validate_manifest(manifest, rows, assignments, summary)
    for index in range(3):
        changed = [copy.deepcopy(rows), copy.deepcopy(assignments), copy.deepcopy(summary)]
        if index == 0:
            changed[0][0]["expected_quote_usd"] = 99.0
        elif index == 1:
            changed[1][0]["policy"] = "tampered"
        else:
            changed[2]["planned_tasks"] += 1
        with pytest.raises(ValueError, match="manifest mismatch"):
            validate_manifest(manifest, changed[0], changed[1], changed[2])


@pytest.mark.parametrize(
    ("planned", "day", "campaign", "message"),
    [
        (1.01, 0.0, 0.0, "per-run"),
        (0.5, 24.6, 0.0, "day"),
        (0.5, 0.0, 299.6, "campaign"),
    ],
)
def test_budget_limits_fail_closed(planned, day, campaign, message):
    limits = BudgetLimits(1.0, 25.0, 300.0)
    with pytest.raises(RuntimeError, match=message):
        check_budget(
            planned_usd=planned,
            spent_day_usd=day,
            spent_campaign_usd=campaign,
            limits=limits,
        )


def test_campaign_boundaries_are_half_open():
    start, end = "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z"
    assert campaign_open(start, end, datetime(2026, 8, 1, tzinfo=UTC))
    assert not campaign_open(start, end, datetime(2026, 8, 2, tzinfo=UTC))


def test_spend_ledger_deduplicates_tasks_and_ignores_invalid_rows():
    rows = [
        {"study_id": "openrouter-price-response-v1", "task_id": "a", "cost_usd": 1},
        {"study_id": "openrouter-price-response-v1", "task_id": "a", "cost_usd": 9},
        {"study_id": "openrouter-price-response-v1", "task_id": "b", "cost_usd": -2},
        {"study_id": "other", "task_id": "c", "cost_usd": 3},
    ]
    assert spent_from_rows(rows) == 1.0
