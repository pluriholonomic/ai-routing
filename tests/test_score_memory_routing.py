from __future__ import annotations

from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

import orcap.capture_score_memory_routing as capture
from orcap.glm52_routing import build_assignments
from orcap.price_experiments import plan_manifest


def _candidates() -> list[dict]:
    rows = []
    for index, (provider, price) in enumerate(
        (
            ("StreamLake", 0.4e-6),
            ("Novita", 0.41e-6),
            ("Other A", 1.0e-6),
            ("Other B", 1.5e-6),
            ("Z.AI", 2.5e-6),
        )
    ):
        rows.append(
            {
                "run_id": "run",
                "observed_at": "2026-08-05T00:00:00Z",
                "study_id": "openrouter-glm52-routing-v1",
                "plan_version": "glm52-routing-plan-v1",
                "block_id": "old-block",
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


def _base_bundle() -> dict:
    candidates = _candidates()
    assignments, summary = build_assignments(candidates, run_id="run", seed=5)
    summary.update(
        {
            "source_healthy": True,
            "source_failures": [],
            "preflight_only": True,
            "created_at": "2026-08-05T00:00:00Z",
            "claim_boundary": "base",
        }
    )
    return {
        "format": "orcap-glm52-routing-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
        "manifest": plan_manifest(candidates, assignments, summary),
    }


def _bundle(monkeypatch):
    monkeypatch.setattr(capture.base, "build_plan_bundle", lambda *args, **kwargs: _base_bundle())
    return capture.build_plan_bundle(None, run_id="run", seed=5)  # type: ignore[arg-type]


def test_successor_rewrites_every_identifier_and_preserves_ten_policies(monkeypatch):
    bundle = _bundle(monkeypatch)
    assert bundle["summary"]["study_id"] == capture.STUDY_ID
    assert len(bundle["assignments"]) == 10
    assert all(row["study_id"] == capture.STUDY_ID for row in bundle["candidates"])
    assert all(row["study_id"] == capture.STUDY_ID for row in bundle["assignments"])
    assert all("openrouter-glm52-routing-v1" not in row["task_id"] for row in bundle["assignments"])
    assert bundle["manifest"] == plan_manifest(
        bundle["candidates"], bundle["assignments"], bundle["summary"]
    )


def test_successor_execution_uses_separate_window_budget_and_exact_once(monkeypatch, tmp_path):
    bundle = _bundle(monkeypatch)
    capture.write_plan_bundle(
        bundle,
        bundle_path=tmp_path / "plan.json",
        curated_dir=tmp_path / "curated",
    )
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_ROUTING_START_UTC", "2026-08-04T21:15:00Z")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_ROUTING_END_UTC", "2026-08-19T00:00:00Z")

    def send(_client, assignment):
        provider = assignment.get("requested_provider") or "StreamLake"
        return (
            {
                "id": assignment["task_id"],
                "provider": provider,
                "usage": {"prompt_tokens": 7, "completion_tokens": 1, "cost": 1e-6},
            },
            {
                "data": {
                    "provider_name": provider,
                    "native_tokens_prompt": 7,
                    "native_tokens_completion": 1,
                    "total_cost": 1e-6,
                    "latency": 10,
                }
            },
            None,
            200,
        )

    result = capture.execute_bundle(
        bundle,
        curated_dir=tmp_path / "curated",
        data_root=tmp_path,
        now=datetime(2026, 8, 5, tzinfo=UTC),
        send=send,
    )
    assert result["study_id"] == capture.STUDY_ID
    attempts_path = next((tmp_path / "curated" / "glm52_routing_attempts").glob("dt=*/*.parquet"))
    attempts = pq.ParquetFile(attempts_path).read().to_pandas()
    assert set(attempts["study_id"]) == {capture.STUDY_ID}
    with pytest.raises(RuntimeError, match="re-execute"):
        capture.execute_bundle(
            bundle,
            curated_dir=tmp_path / "curated",
            data_root=tmp_path,
            now=datetime(2026, 8, 5, tzinfo=UTC),
            send=send,
        )


def test_successor_refuses_before_frozen_start(monkeypatch):
    bundle = _bundle(monkeypatch)
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_ROUTING_START_UTC", "2026-08-04T21:15:00Z")
    monkeypatch.setenv("ORCAP_SCORE_MEMORY_ROUTING_END_UTC", "2026-08-19T00:00:00Z")
    with pytest.raises(RuntimeError, match="outside the score-memory successor campaign"):
        capture.execute_bundle(bundle, now=datetime(2026, 8, 4, tzinfo=UTC))
