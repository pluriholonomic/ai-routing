from __future__ import annotations

from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

import orcap.capture_route_calibration as h96
from orcap.route_telemetry import validate_attempt


def _endpoint(
    provider: str,
    tag: str,
    prompt: float,
    completion: float,
    *,
    tools: bool = True,
) -> dict:
    parameters = ["max_tokens", "temperature"]
    if tools:
        parameters += ["tools", "tool_choice"]
    return {
        "name": f"{provider} endpoint",
        "provider_name": provider,
        "tag": tag,
        "context_length": 32_768,
        "max_completion_tokens": 4_096,
        "pricing": {"prompt": str(prompt), "completion": str(completion)},
        "supported_parameters": parameters,
    }


def _endpoints() -> list[dict]:
    return [
        _endpoint("Cheap", "cheap/fp8", 1e-7, 2e-7),
        _endpoint("Cheap", "cheap/fp16", 1.2e-7, 2.2e-7),
        _endpoint("Backup", "backup/fp8", 2e-7, 3e-7),
        _endpoint("No tools", "no-tools/fp8", 3e-7, 4e-7, tools=False),
    ]


class _Response:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body

    def raise_for_status(self):
        return None


class _PlanClient:
    def get(self, url):
        return _Response({"data": {"endpoints": _endpoints()}})


def test_build_plan_has_eight_randomized_tasks_and_only_one_sticky_session() -> None:
    shape = h96.RequestShape("short_chat", 64, 96, 8)
    candidates, assignments, executable, summary = h96.build_plan(
        _PlanClient(),
        run_id="20260719T013700Z",
        run_seed=17,
        preflight_only=True,
        models=("org/model",),
        shapes=(shape,),
    )

    assert summary["planned_requests"] == 8
    assert len(assignments) == len(executable) == 8
    assert len(candidates) == 4
    assert {row["policy"] for row in assignments} == set(h96.POLICY_COUNTS)
    iid = [row for row in assignments if row["policy"] == "default_budgeted_iid"]
    assert len(iid) == 3
    assert len({row["session_id_sha256"] for row in iid}) == 3
    sticky = [row for row in assignments if row["policy"].startswith("default_sticky_")]
    assert len({row["session_id_sha256"] for row in sticky}) == 1
    seed = next(row for row in sticky if row["policy"] == "default_sticky_seed")
    repeat = next(row for row in sticky if row["policy"] == "default_sticky_repeat")
    assert seed["policy_order"] < repeat["policy_order"]
    assert "session_id" not in assignments[0]
    assert "prompt_nonce" not in assignments[0]


def test_pins_use_exact_tags_and_distinct_provider_names() -> None:
    _, assignments, executable, _ = h96.build_plan(
        _PlanClient(),
        run_id="20260719T013700Z",
        run_seed=19,
        preflight_only=True,
        models=("org/model",),
        shapes=(h96.RequestShape("short_chat", 64, 96, 8),),
    )
    pinned = [row for row in assignments if row["policy"].startswith("pinned_")]
    assert {row["requested_provider"] for row in pinned} == {"Cheap", "Backup"}
    assert {row["requested_endpoint_tag"] for row in pinned} == {
        "cheap/fp8",
        "backup/fp8",
    }
    executable_pins = [row for row in executable if row["policy"].startswith("pinned_")]
    assert all(row["provider_control"]["allow_fallbacks"] is False for row in executable_pins)
    assert all(
        row["provider_control"]["only"] == [row["requested_endpoint_tag"]]
        for row in executable_pins
    )


def test_tool_shape_excludes_incompatible_endpoint_and_requires_parameters() -> None:
    candidates, assignments, executable, _ = h96.build_plan(
        _PlanClient(),
        run_id="20260719T013700Z",
        run_seed=23,
        preflight_only=True,
        models=("org/model",),
        shapes=(h96.RequestShape("tool_call", 256, 512, 32, ("tools", "tool_choice")),),
    )
    excluded = next(row for row in candidates if row["provider_name"] == "No tools")
    assert excluded["compatible"] is False
    assert excluded["exclusion_reason"].startswith("missing_parameters")
    assert all(row["require_parameters"] for row in assignments)
    assert all(row["provider_control"]["require_parameters"] for row in executable)


def test_preflight_tables_are_payload_free(tmp_path) -> None:
    candidates, assignments, _, _ = h96.build_plan(
        _PlanClient(),
        run_id="20260719T013700Z",
        run_seed=29,
        preflight_only=True,
        models=("org/model",),
        shapes=(h96.RequestShape("short_chat", 64, 96, 8),),
    )
    candidate_path = h96._write_rows(
        candidates,
        h96.CALIBRATION_CANDIDATE_SCHEMA,
        "router_calibration_candidates",
        run_id="20260719T013700Z",
        curated_dir=tmp_path,
    )
    assignment_path = h96._write_rows(
        assignments,
        h96.CALIBRATION_ASSIGNMENT_SCHEMA,
        "router_calibration_assignments",
        run_id="20260719T013700Z",
        curated_dir=tmp_path,
    )
    candidate_frame = pq.ParquetFile(candidate_path).read().to_pandas()
    assignment_frame = pq.ParquetFile(assignment_path).read().to_pandas()
    assert candidate_frame["payload_retained"].eq(False).all()  # noqa: E712
    assert assignment_frame["payload_retained"].eq(False).all()  # noqa: E712
    forbidden = {"messages", "prompt", "completion", "session_id", "api_key"}
    assert forbidden.isdisjoint(candidate_frame.columns)
    assert forbidden.isdisjoint(assignment_frame.columns)


def test_execute_plan_aborts_before_request_when_quote_cap_exceeds_budget(monkeypatch) -> None:
    task = {"task_id": "task-1", "task_quote_cap_usd": 0.02}
    called = False

    def fake_send(client, row):
        nonlocal called
        called = True
        raise AssertionError("must not send")

    monkeypatch.setattr(h96, "_send_task", fake_send)
    with pytest.raises(RuntimeError, match="exceeds per-run cap"):
        h96.execute_plan(object(), [task], max_run_usd=0.01, jitter=False)
    assert called is False


def test_send_task_uses_unique_session_and_tool_controls(monkeypatch) -> None:
    seen = {}

    class FakeClient:
        def post(self, url, headers, json):
            seen.update(json)
            return _Response({"id": "generation-1", "provider": "Cheap"})

    monkeypatch.setattr(h96, "_headers", lambda: {})
    monkeypatch.setattr(h96, "_fetch_generation", lambda client, generation_id: None)
    task = {
        "model_id": "org/model",
        "shape": h96.RequestShape(
            "tool_call", 256, 512, 32, ("tools", "tool_choice")
        ),
        "prompt_nonce": "nonce",
        "session_id": "secret-session",
        "provider_control": {"require_parameters": True},
    }
    completion, _, error, status = h96._send_task(FakeClient(), task)

    assert completion["id"] == "generation-1"
    assert error is None and status == 200
    assert seen["session_id"] == "secret-session"
    assert seen["provider"]["require_parameters"] is True
    assert seen["tool_choice"]["function"]["name"] == "calibration_echo"


def test_attempt_record_satisfies_redacted_route_contract() -> None:
    task = {
        "task_id": "task-1",
        "block_id": "block-1",
        "model_id": "org/model",
        "shape_id": "short_chat",
        "policy": "default_budgeted_iid",
        "policy_order": 0,
        "replicate_index": 0,
        "requested_provider": None,
        "requested_endpoint_tag": None,
        "session_id_sha256": "hash",
        "sticky_pair_id": None,
        "provider_sort": None,
        "allow_fallbacks": True,
        "require_parameters": False,
        "max_price_prompt_per_mtok": 1.0,
        "max_price_completion_per_mtok": 2.0,
        "task_quote_cap_usd": 0.001,
    }
    attempt = h96._attempt_record(
        task,
        {"id": "gen-1", "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        {"data": {"provider_name": "Cheap", "total_cost": 1e-5, "latency": 20}},
        None,
        200,
    )
    normalized = validate_attempt(attempt)
    assert normalized["selected_provider"] == "Cheap"
    assert normalized["payload_retained"] is False
    assert "secret-session" not in normalized["metadata_json"]


def test_campaign_window_is_half_open() -> None:
    assert h96.campaign_open(datetime(2026, 7, 19, 1, 0, tzinfo=UTC))
    assert h96.campaign_open(datetime(2026, 7, 21, 0, 59, 59, tzinfo=UTC))
    assert not h96.campaign_open(datetime(2026, 7, 21, 1, 0, tzinfo=UTC))
