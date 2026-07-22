from __future__ import annotations

import copy
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

from orcap.capture_price_response import _send_assignment, execute_bundle, reconstruct_spend
from orcap.price_experiments import build_response_assignments, plan_manifest


def _bundle() -> dict:
    candidates = [
        {
            "block_id": "block-1",
            "model_id": "author/model",
            "shape_id": "short_chat",
            "provider_name": provider,
            "endpoint_tag": f"tag-{provider}",
            "prompt_price_per_token": price,
            "completion_price_per_token": price,
            "expected_quote_usd": price * 104,
            "conservative_input_tokens": 96,
            "max_output_tokens": 8,
            "compatible": True,
        }
        for provider, price in (("a", 1e-8), ("b", 2e-8), ("c", 3e-8))
    ]
    assignments, summary = build_response_assignments(
        candidates, run_id="20260719T000000Z", seed=5
    )
    summary = summary | {"source_healthy": True}
    return {
        "format": "orcap-price-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
        "manifest": plan_manifest(candidates, assignments, summary),
    }


def _enable(monkeypatch):
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")
    monkeypatch.setenv("ORCAP_PRICE_CAMPAIGN_START_UTC", "2026-07-18T00:00:00Z")
    monkeypatch.setenv("ORCAP_PRICE_CAMPAIGN_END_UTC", "2026-07-20T00:00:00Z")


def test_execute_refuses_disabled_missing_key_tampered_and_unhealthy(monkeypatch, tmp_path):
    bundle = _bundle()
    with pytest.raises(RuntimeError, match="disabled"):
        execute_bundle(bundle, curated_dir=tmp_path / "curated")
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    with pytest.raises(RuntimeError, match="dedicated"):
        execute_bundle(bundle, curated_dir=tmp_path / "curated")
    _enable(monkeypatch)
    unhealthy = copy.deepcopy(bundle)
    unhealthy["summary"]["source_healthy"] = False
    unhealthy["manifest"] = plan_manifest(
        unhealthy["candidates"], unhealthy["assignments"], unhealthy["summary"]
    )
    with pytest.raises(RuntimeError, match="source-health"):
        execute_bundle(unhealthy, curated_dir=tmp_path / "curated")
    tampered = copy.deepcopy(bundle)
    tampered["assignments"][0]["policy"] = "changed"
    with pytest.raises(ValueError, match="manifest mismatch"):
        execute_bundle(tampered, curated_dir=tmp_path / "curated")


def test_exact_uploaded_plan_executes_once_and_writes_only_redacted_rows(
    monkeypatch, tmp_path
):
    _enable(monkeypatch)
    bundle = _bundle()
    sent = []

    def fake_send(_client, assignment):
        sent.append(assignment["task_id"])
        completion = {
            "id": f"generation-{len(sent)}",
            "provider": "a",
            "usage": {"prompt_tokens": 7, "completion_tokens": 1, "cost": 1e-6},
        }
        generation = {
            "data": {
                "provider_name": "a",
                "native_tokens_prompt": 7,
                "native_tokens_completion": 1,
                "total_cost": 1e-6,
                "latency": 12,
            }
        }
        return completion, generation, None, 200

    result = execute_bundle(
        bundle,
        curated_dir=tmp_path / "curated",
        data_root=tmp_path,
        now=datetime(2026, 7, 19, tzinfo=UTC),
        send=fake_send,
    )
    assert sent == [row["task_id"] for row in bundle["assignments"]]
    assert result["attempted_requests"] == len(bundle["assignments"])
    assert result["realized_cost_usd"] == pytest.approx(len(sent) * 1e-6)
    attempt_path = next(
        (tmp_path / "curated" / "router_route_attempts").glob("dt=*/*.parquet")
    )
    frame = pq.ParquetFile(attempt_path).read().to_pandas()
    assert not frame["payload_retained"].any()
    serialized = " ".join(frame["metadata_json"].astype(str)).lower()
    for forbidden in ('"messages"', '"completion"', "test-only", '"raw_response"'):
        assert forbidden not in serialized


def test_reconstruct_spend_is_rolling_and_deduplicated():
    now = datetime(2026, 7, 19, tzinfo=UTC)
    rows = [
        {
            "study_id": "openrouter-price-response-v1",
            "task_id": "a",
            "observed_at": "2026-07-18T12:00:00Z",
            "cost_usd": 2,
        },
        {
            "study_id": "openrouter-price-response-v1",
            "task_id": "a",
            "observed_at": "2026-07-18T12:00:00Z",
            "cost_usd": 2,
        },
        {
            "study_id": "openrouter-price-response-v1",
            "task_id": "b",
            "observed_at": "2026-07-17T12:00:00Z",
            "cost_usd": 3,
        },
    ]
    day, campaign = reconstruct_spend(rows, now=now)
    assert day == 2
    assert campaign == 5


def test_retry_of_same_uploaded_tasks_is_refused(monkeypatch, tmp_path):
    _enable(monkeypatch)
    bundle = _bundle()

    def fake_send(_client, assignment):
        return (
            {"id": assignment["task_id"], "provider": "a", "usage": {"cost": 0}},
            {"data": {"provider_name": "a", "total_cost": 0}},
            None,
            200,
        )

    execute_bundle(
        bundle,
        curated_dir=tmp_path / "curated",
        data_root=tmp_path,
        now=datetime(2026, 7, 19, tzinfo=UTC),
        send=fake_send,
    )
    with pytest.raises(RuntimeError, match="already present"):
        execute_bundle(
            bundle,
            curated_dir=tmp_path / "curated",
            data_root=tmp_path,
            now=datetime(2026, 7, 19, tzinfo=UTC),
            send=fake_send,
        )


def test_plan_bundle_contains_no_payload_or_secret_fields():
    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    present = {str(key).lower() for key in keys(_bundle())}
    for forbidden in ("messages", "prompt_nonce", "completion", "api_key", "authorization"):
        assert forbidden not in present


def test_sender_honors_the_immutable_assignment_output_cap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")
    assignment = copy.deepcopy(_bundle()["assignments"][0])
    assignment["max_output_tokens"] = 1
    observed = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"provider": "a", "usage": {"completion_tokens": 1}}

    class Client:
        @staticmethod
        def post(_url, *, headers, json):
            observed["headers"] = headers
            observed["body"] = json
            return Response()

    completion, _generation, error, status = _send_assignment(Client(), assignment)

    assert completion is not None
    assert error is None
    assert status == 200
    assert observed["body"]["max_tokens"] == 1
    assert "test-only" not in str(observed["body"])
