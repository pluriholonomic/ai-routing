from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

import orcap.capture_glm52_routing as capture
from orcap.analysis.glm52_routing_monitor import run as run_monitor
from orcap.glm52_routing import PLAN_VERSION, STUDY_ID, build_assignments, manifest


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
                "run_id": "run-1",
                "observed_at": "2026-07-21T21:00:00Z",
                "study_id": STUDY_ID,
                "plan_version": PLAN_VERSION,
                "block_id": "glm-block",
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


def _bundle() -> dict:
    candidates = _candidates()
    assignments, summary = build_assignments(candidates, run_id="run-1", seed=17)
    summary = summary | {
        "source_healthy": True,
        "source_failures": [],
        "preflight_only": True,
        "created_at": "2026-07-21T20:59:00+00:00",
        "claim_boundary": "owned requests only",
    }
    return {
        "format": "orcap-glm52-routing-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
        "manifest": manifest(candidates, assignments, summary),
    }


def test_assignment_panel_is_targeted_deterministic_and_complete():
    first, summary = build_assignments(_candidates(), run_id="run-1", seed=17)
    second, second_summary = build_assignments(_candidates(), run_id="run-1", seed=17)
    assert first == second
    assert summary == second_summary
    assert len(first) == 10
    assert len({row["task_id"] for row in first}) == 10
    assert sum(row["policy"] == "default_broad" for row in first) == 2
    assert {
        "price_sorted",
        "pinned_streamlake",
        "pinned_novita",
        "pinned_z_ai",
        "exclude_streamlake",
        "exclude_novita",
        "exclude_both_cutters",
        "pair_only",
    }.issubset({row["policy"] for row in first})
    assert all(row["session_group"].startswith("fresh|") for row in first)
    assert all(row["task_quote_cap_usd"] > 0 for row in first)
    pair = next(row for row in first if row["policy"] == "pair_only")
    assert set(pair["provider_only_tags"]) == {"tag-0", "tag-1"}
    excluded = next(row for row in first if row["policy"] == "exclude_both_cutters")
    assert not {"tag-0", "tag-1"}.intersection(excluded["provider_only_tags"])
    pinned = [row for row in first if row["policy"].startswith("pinned_")]
    assert all(row["allow_fallbacks"] is False for row in pinned)
    assert all(row["provider_only_tags"] == row["provider_order_tags"] for row in pinned)


def test_missing_target_provider_fails_closed_without_paid_tasks():
    assignments, summary = build_assignments(_candidates()[:-1], run_id="run-1", seed=5)
    assert assignments == []
    assert summary["planned_tasks"] == 0
    assert summary["missing_target_provider_keys"] == ["z.ai"]


def _enable(monkeypatch):
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    monkeypatch.setenv("ORCAP_GLM52_ROUTING_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")
    monkeypatch.setenv("ORCAP_GLM52_ROUTING_START_UTC", "2026-07-21T00:00:00Z")
    monkeypatch.setenv("ORCAP_GLM52_ROUTING_END_UTC", "2026-07-23T00:00:00Z")


def test_execution_is_exact_once_redacted_budgeted_and_monitored(monkeypatch, tmp_path):
    _enable(monkeypatch)
    bundle = _bundle()
    capture.write_plan_bundle(
        bundle,
        bundle_path=tmp_path / "glm52-routing-plan.json",
        curated_dir=tmp_path / "curated",
    )

    def fake_send(_client, assignment):
        provider = assignment.get("requested_provider") or "StreamLake"
        completion = {
            "id": "generation-" + str(abs(hash(assignment["task_id"]))),
            "provider": provider,
            "usage": {"prompt_tokens": 7, "completion_tokens": 1, "cost": 1e-6},
        }
        generation = {
            "data": {
                "provider_name": provider,
                "native_tokens_prompt": 7,
                "native_tokens_completion": 1,
                "total_cost": 1e-6,
                "latency": 12,
            }
        }
        return completion, generation, None, 200

    result = capture.execute_bundle(
        bundle,
        curated_dir=tmp_path / "curated",
        data_root=tmp_path,
        # Keep this fixture explicitly before the prospective scoring cutoff;
        # wall-clock time must never decide whether legacy choices enter it.
        now=datetime(2026, 7, 21, 21, 30, tzinfo=UTC),
        send=fake_send,
    )
    assert result["attempted_requests"] == 10
    assert result["successful_requests"] == 10
    dedicated = next((tmp_path / "curated" / "glm52_routing_attempts").glob("dt=*/*.parquet"))
    attempts = pq.ParquetFile(dedicated).read().to_pandas()
    assert len(attempts) == 10
    assert not attempts["payload_retained"].any()
    serialized = " ".join(attempts["metadata_json"].astype(str)).lower()
    for forbidden in ('"messages":', '"completion":', "test-only", '"authorization":'):
        assert forbidden not in serialized

    output = tmp_path / "analysis"
    summary = run_monitor(tmp_path, output, source_revision="test-revision")
    assert summary["covered_default_choices"] == 2
    assert summary["observed_pair_share"] == 1.0
    assert summary["support_status"] == "accruing"
    assert (output / "glm52-routing.html").is_file()
    assert (output / "glm52_routing_monitor.png").is_file()
    assert (output / "glm52_nonprice_provider_scores.parquet").is_file()
    assert (output / "glm52_score_adjusted_undercutting.parquet").is_file()
    assert (output / "glm52_price_sort_rule_contrast.parquet").is_file()
    assert summary["nonprice_scoring"]["status"] == "accruing"
    assert summary["nonprice_scoring"]["covered_choices"] == 0

    with pytest.raises(RuntimeError, match="re-execute"):
        capture.execute_bundle(
            bundle,
            curated_dir=tmp_path / "curated",
            data_root=tmp_path,
            now=datetime(2026, 7, 21, 21, 30, tzinfo=UTC),
            send=fake_send,
        )


def test_execution_rejects_manifest_tampering_and_disabled_gate(monkeypatch, tmp_path):
    bundle = _bundle()
    with pytest.raises(RuntimeError, match="paid price studies are disabled"):
        capture.execute_bundle(bundle, curated_dir=tmp_path / "curated")
    _enable(monkeypatch)
    tampered = copy.deepcopy(bundle)
    tampered["assignments"][0]["policy"] = "changed"
    with pytest.raises(ValueError, match="manifest mismatch"):
        capture.execute_bundle(
            tampered,
            curated_dir=tmp_path / "curated",
            now=datetime(2026, 7, 22, tzinfo=UTC),
        )


def test_plan_contains_no_payload_or_secret_fields():
    serialized = json.dumps(_bundle()).lower()
    for forbidden in ('"prompt"', '"messages"', '"completion"', "api_key", "authorization"):
        assert forbidden not in serialized
