from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pyarrow.parquet as pq

from orcap.adaptive_router import (
    POLICY_SPECS,
    adaptive_manifest,
    allocation_probabilities,
    build_adaptive_assignments,
    policy_metrics,
    projected_policy,
)
from orcap.capture_adaptive_router import execute_bundle


def _candidates(run_id: str = "run-1"):
    rows = []
    for index, (provider, quote, quality) in enumerate(
        (("A", 0.0010, 0.99), ("B", 0.0012, 0.995), ("C", 0.0015, 0.98))
    ):
        rows.append(
            {
                "run_id": run_id,
                "block_id": f"block-{run_id}",
                "model_id": "example/model",
                "shape_id": "short_chat",
                "provider_name": provider,
                "endpoint_tag": provider.lower(),
                "prompt_price_per_token": quote / 104,
                "completion_price_per_token": quote / 104,
                "expected_quote_usd": quote,
                "conservative_quote_usd": quote,
                "public_uptime_30m": quality,
                "compatible": True,
                "conservative_input_tokens": 96,
                "max_output_tokens": 8,
                "snapshot_sha256": str(index),
            }
        )
    return rows


def test_monotone_probabilities_and_projection_constraints():
    costs = [1.0, 1.2, 1.5]
    qualities = [0.99, 0.99, 0.99]
    shares = allocation_probabilities(costs, qualities, eta=2.0, exploration=0.1)
    assert np.isclose(shares.sum(), 1.0)
    assert shares[0] > shares[1] > shares[2]

    projected = projected_policy(costs, qualities)
    baseline = policy_metrics(costs, qualities, eta=2.0)
    metrics = projected["metrics"]
    assert metrics["expected_quote_usd"] <= baseline["expected_quote_usd"] * 1.02
    assert metrics["expected_reliability"] >= baseline["expected_reliability"] - 0.002
    assert metrics["cross_provider_gain"] <= baseline["cross_provider_gain"] + 1e-12


def test_assignment_plan_is_rectangular_deterministic_and_logs_propensity():
    rows = _candidates()
    first, summary = build_adaptive_assignments(rows, run_id="run-1", seed=17, max_blocks=1)
    second, _ = build_adaptive_assignments(rows, run_id="run-1", seed=17, max_blocks=1)
    assert first == second
    assert len(first) == len(POLICY_SPECS) == 5
    assert summary["planned_blocks"] == 1
    assert {row["policy"] for row in first} == {
        str(spec["policy"]) for spec in POLICY_SPECS
    }
    assert sorted(row["policy_order"] for row in first) == list(range(len(POLICY_SPECS)))
    for assignment in first:
        target = json.loads(assignment["target_probabilities_json"])
        assert np.isclose(sum(target.values()), 1.0)
        assert np.isclose(
            target[assignment["requested_provider"].casefold()],
            assignment["provider_probability"],
        )
        assert assignment["provider_only_tags"] == [assignment["requested_endpoint_tag"]]
        assert assignment["allow_fallbacks"] is False
        assert assignment["joint_probability"] == assignment["provider_probability"]


def test_paid_execution_is_gated_checkpointed_and_isolated(monkeypatch, tmp_path):
    candidates = _candidates()
    assignments, summary = build_adaptive_assignments(
        candidates, run_id="run-1", seed=29, max_blocks=1
    )
    summary = summary | {
        "source_healthy": True,
        "claim_boundary": "test boundary",
        "horizon_reached": False,
    }
    bundle = {
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
    }
    bundle["manifest"] = adaptive_manifest(candidates, assignments, summary)
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    monkeypatch.setenv("ORCAP_ADAPTIVE_ROUTER_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")

    def send(_client, assignment):
        provider = assignment["requested_provider"]
        return (
            {"id": assignment["task_id"], "provider": provider, "usage": {"cost": 0.001}},
            {"data": {"provider_name": provider, "latency": 100.0, "total_cost": 0.001}},
            None,
            200,
        )

    result = execute_bundle(
        bundle,
        curated_dir=tmp_path / "curated",
        data_root=tmp_path,
        now=datetime(2026, 7, 22, tzinfo=UTC),
        send=send,
    )
    assert result["successful_requests"] == len(POLICY_SPECS)
    attempts = list((tmp_path / "curated" / "adaptive_router_attempts").glob("dt=*/*.parquet"))
    assert len(attempts) == 1
    table = pq.ParquetFile(attempts[0]).read()
    assert table.num_rows == len(POLICY_SPECS)
    assert not (tmp_path / "curated" / "router_route_attempts").exists()
