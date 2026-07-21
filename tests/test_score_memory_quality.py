from __future__ import annotations

import json
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

import orcap.capture_score_memory_quality as capture


def _candidates():
    rows = []
    for index, (provider, price) in enumerate(
        (("A", 1e-6), ("B", 1.2e-6), ("C", 1.4e-6), ("D", 1.6e-6))
    ):
        rows.append(
            {
                "run_id": "run",
                "observed_at": "2026-07-22T00:00:00Z",
                "study_id": "openrouter-price-response-v1",
                "plan_version": "price-response-plan-v1",
                "block_id": "old",
                "model_id": "z-ai/glm-5.2",
                "shape_id": "short_chat",
                "provider_name": provider,
                "endpoint_tag": f"tag-{index}",
                "endpoint_name": f"endpoint-{index}",
                "prompt_price_per_token": price,
                "completion_price_per_token": price * 2,
                "expected_quote_usd": price * 112,
                "conservative_quote_usd": price * 112,
                "conservative_input_tokens": 96,
                "max_output_tokens": 8,
                "compatible": True,
                "exclusion_reason": None,
                "snapshot_sha256": "a" * 64,
                "payload_retained": False,
            }
        )
    return rows


def _items():
    return [
        {
            "item_id": f"mmlu-{letter}",
            "source": "mmlu",
            "grade": "letter",
            "answer": letter,
            "prompt": f"Choose {letter}.",
            "max_tokens": 8,
        }
        for letter in ("A", "B", "C")
    ]


def _bundle(monkeypatch):
    monkeypatch.setattr(capture, "freeze_candidates", lambda *args, **kwargs: (_candidates(), []))
    monkeypatch.setattr(capture, "_public_items", _items)
    return capture.build_plan_bundle(None, run_id="run", seed=7)  # type: ignore[arg-type]


def test_quality_plan_is_eleven_tasks_deterministic_and_redacted(monkeypatch):
    bundle = _bundle(monkeypatch)
    assert bundle["summary"]["source_healthy"] is True
    assert len(bundle["assignments"]) == 11
    assert {
        "quality_default",
        "quality_a",
        "quality_b",
        "quality_c",
    }.issubset({row["policy"] for row in bundle["assignments"]})
    assert {
        "router_no_memory",
        "router_geometric_quality",
        "router_finite_failure",
    }.issubset({row["policy"] for row in bundle["assignments"]})
    router_rows = [row for row in bundle["assignments"] if row["policy"].startswith("router_")]
    assert all(
        len(row["provider_order_tags"]) == len(set(row["provider_order_tags"]))
        for row in router_rows
    )
    assert all(row["max_output_tokens"] >= 64 for row in bundle["assignments"])
    serialized = json.dumps(bundle).lower()
    for forbidden in ('"prompt"', '"messages"', "api_key", "authorization"):
        assert forbidden not in serialized


def test_quality_plan_fails_closed_on_incomplete_public_menu(monkeypatch):
    monkeypatch.setattr(
        capture,
        "freeze_candidates",
        lambda *args, **kwargs: (_candidates()[:2], []),
    )
    monkeypatch.setattr(capture, "_public_items", _items)
    bundle = capture.build_plan_bundle(None, run_id="run", seed=7)  # type: ignore[arg-type]
    assert bundle["assignments"] == []
    assert bundle["summary"]["source_healthy"] is False
    assert bundle["summary"]["planned_quote_cap_usd"] == 0.0


def test_policy_state_uses_prior_non_arm_quality_only():
    now = datetime(2026, 7, 22, 1, tzinfo=UTC)
    history = [
        {
            "observed_at": "2026-07-22T00:00:00Z",
            "policy": "quality_a",
            "requested_provider": "A",
            "http_status": 500,
            "correct": False,
            "latency_ms": 5000,
        },
        {
            "observed_at": "2026-07-22T00:00:00Z",
            "policy": "quality_b",
            "requested_provider": "B",
            "http_status": 200,
            "correct": True,
            "latency_ms": 50,
        },
        {
            "observed_at": "2026-07-22T00:30:00Z",
            "policy": "router_geometric_quality",
            "selected_provider": "A",
            "http_status": 200,
            "correct": True,
            "latency_ms": 1,
        },
    ]
    orders = capture._policy_orders(_candidates(), history, now=now)
    assert orders["router_no_memory"][0] == "tag-0"
    assert orders["router_geometric_quality"][0] == "tag-1"
    assert orders["router_finite_failure"][0] == "tag-1"


def test_quality_execution_is_exact_once_budgeted_and_private(monkeypatch, tmp_path):
    bundle = _bundle(monkeypatch)
    monkeypatch.setattr(capture, "_quality_item_map", lambda: {i["item_id"]: i for i in _items()})
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_QUALITY_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_QUALITY_START_UTC", "2026-07-22T00:00:00Z")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_QUALITY_END_UTC", "2026-07-23T00:00:00Z")
    capture.write_plan_bundle(
        bundle,
        bundle_path=tmp_path / "plan.json",
        curated_dir=tmp_path / "curated",
    )

    def send(_client, assignment):
        provider = assignment.get("requested_provider") or "A"
        completion = {
            "id": assignment["task_id"],
            "provider": provider,
            "choices": [{"message": {"content": "A"}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 1, "cost": 1e-6},
        }
        generation = {
            "data": {
                "provider_name": provider,
                "native_tokens_prompt": 4,
                "native_tokens_completion": 1,
                "total_cost": 1e-6,
                "latency": 20,
            }
        }
        return completion, generation, None, 200

    result = capture.execute_bundle(
        bundle,
        curated_dir=tmp_path / "curated",
        data_root=tmp_path,
        now=datetime(2026, 7, 22, 1, tzinfo=UTC),
        send=send,
    )
    assert result["quality_rows"] == 11
    quality_path = next((tmp_path / "curated" / "score_memory_quality").glob("dt=*/*.parquet"))
    quality = pq.ParquetFile(quality_path).read().to_pandas()
    assert len(quality) == 11
    assert not quality["payload_retained"].any()
    assert "prompt" not in quality.columns
    with pytest.raises(RuntimeError, match="re-execute"):
        capture.execute_bundle(
            bundle,
            curated_dir=tmp_path / "curated",
            data_root=tmp_path,
            now=datetime(2026, 7, 22, 1, tzinfo=UTC),
            send=send,
        )


def test_quality_execution_fails_closed_without_feature_gate(monkeypatch):
    bundle = _bundle(monkeypatch)
    with pytest.raises(RuntimeError, match="paid price studies are disabled"):
        capture.execute_bundle(bundle)
