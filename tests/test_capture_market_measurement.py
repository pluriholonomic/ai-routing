from __future__ import annotations

import copy
import json
import threading
import time
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

import orcap.capture_market_measurement as capture
from orcap.analysis.market_measurement_monitor import run as run_monitor
from orcap.market_measurement import build_market_assignments, market_manifest


def _candidates() -> list[dict]:
    return [
        {
            "block_id": "block-1",
            "model_id": "author/model",
            "shape_id": "short_chat",
            "provider_name": provider,
            "endpoint_tag": f"tag-{provider}",
            "prompt_price_per_token": price,
            "completion_price_per_token": price,
            "expected_quote_usd": price * 104,
            "conservative_quote_usd": price * 104,
            "conservative_input_tokens": 96,
            "max_output_tokens": 8,
            "compatible": True,
        }
        for provider, price in (("a", 1e-8), ("b", 2e-8), ("c", 3e-8))
    ]


def _items() -> list[dict]:
    return [
        {
            "item_id": "mmlu-a",
            "source": "mmlu",
            "grade": "letter",
            "prompt": "Choose A.",
            "answer": "A",
            "max_tokens": 6,
        },
        {
            "item_id": "mmlu-b",
            "source": "mmlu",
            "grade": "letter",
            "prompt": "Choose B.",
            "answer": "B",
            "max_tokens": 6,
        },
    ]


def _bundle() -> dict:
    assignments, summary = build_market_assignments(
        _candidates(), _items(), run_id="20260719T000000Z", seed=5
    )
    summary = summary | {
        "source_healthy": True,
        "claim_boundary": "owned requests only",
    }
    return {
        "format": "orcap-market-measurement-plan-v1",
        "candidates": _candidates(),
        "assignments": assignments,
        "summary": summary,
        "manifest": market_manifest(_candidates(), assignments, summary),
    }


def _enable(monkeypatch):
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    monkeypatch.setenv("ORCAP_MARKET_MEASUREMENT_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_PRICE_EXPERIMENT_KEY", "test-only")
    monkeypatch.setenv("ORCAP_MARKET_MEASUREMENT_START_UTC", "2026-07-18T00:00:00Z")
    monkeypatch.setenv("ORCAP_MARKET_MEASUREMENT_END_UTC", "2026-07-20T00:00:00Z")


def test_execute_refuses_disabled_missing_specific_gate_tamper_and_budget(
    monkeypatch, tmp_path
):
    bundle = _bundle()
    with pytest.raises(RuntimeError, match="paid price studies are disabled"):
        capture.execute_bundle(bundle, curated_dir=tmp_path / "curated")
    monkeypatch.setenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", "true")
    with pytest.raises(RuntimeError, match="market measurement is disabled"):
        capture.execute_bundle(bundle, curated_dir=tmp_path / "curated")
    _enable(monkeypatch)
    tampered = copy.deepcopy(bundle)
    tampered["assignments"][0]["policy"] = "changed"
    with pytest.raises(ValueError, match="manifest mismatch"):
        capture.execute_bundle(tampered, curated_dir=tmp_path / "curated")
    monkeypatch.setenv("ORCAP_MARKET_MEASUREMENT_MAX_RUN_USD", "0.000000001")
    with pytest.raises(RuntimeError, match="per-run cap"):
        capture.execute_bundle(
            bundle,
            curated_dir=tmp_path / "curated",
            now=datetime(2026, 7, 19, tzinfo=UTC),
        )


def test_execute_is_concurrent_redacted_graded_exact_once_and_monitored(
    monkeypatch, tmp_path
):
    _enable(monkeypatch)
    monkeypatch.setattr(capture, "_quality_item_map", lambda: {i["item_id"]: i for i in _items()})
    bundle = _bundle()
    capture.write_plan_bundle(
        bundle,
        bundle_path=tmp_path / "market-measurement-plan.json",
        curated_dir=tmp_path / "curated",
    )
    lock = threading.Lock()
    active = 0
    max_active = 0
    sent = []

    def fake_send(_client, assignment):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            sent.append(assignment["task_id"])
        time.sleep(0.005)
        with lock:
            active -= 1
        provider = assignment.get("requested_provider") or "a"
        completion = {
            "id": "generation-" + str(abs(hash(assignment["task_id"]))),
            "provider": provider,
            "choices": [{"message": {"content": "B"}}],
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
        now=datetime(2026, 7, 19, tzinfo=UTC),
        send=fake_send,
    )
    assert result["attempted_requests"] == len(bundle["assignments"])
    assert result["successful_requests"] == len(bundle["assignments"])
    assert set(sent) == {row["task_id"] for row in bundle["assignments"]}
    assert max_active >= 4

    dedicated_path = next(
        (tmp_path / "curated" / "market_measurement_attempts").glob("dt=*/*.parquet")
    )
    attempts = pq.ParquetFile(dedicated_path).read().to_pandas()
    assert len(attempts) == len(bundle["assignments"])
    assert not attempts["payload_retained"].any()
    serialized = " ".join(attempts["metadata_json"].astype(str)).lower()
    for forbidden in ('"messages"', '"completion"', "choose a", "test-only"):
        assert forbidden not in serialized

    quality_path = next(
        (tmp_path / "curated" / "market_measurement_quality").glob("dt=*/*.parquet")
    )
    quality = pq.ParquetFile(quality_path).read().to_pandas()
    assert len(quality) == 8
    assert quality[quality["quality_item_id"] == "mmlu-b"]["correct"].all()
    assert not quality[quality["quality_item_id"] == "mmlu-a"]["correct"].any()
    assert "prompt" not in quality.columns

    output = tmp_path / "monitor"
    summary = run_monitor(tmp_path, output, source_revision="test-revision")
    assert summary["assignment_rows"] == len(bundle["assignments"])
    assert summary["attempt_rows"] == len(bundle["assignments"])
    assert summary["complete_runs"] == 1
    assert (output / "market-measurement.html").exists()
    assert (output / "liquidity-metrics.parquet").exists()

    with pytest.raises(RuntimeError, match="already present"):
        capture.execute_bundle(
            bundle,
            curated_dir=tmp_path / "curated",
            data_root=tmp_path,
            now=datetime(2026, 7, 19, tzinfo=UTC),
            send=fake_send,
        )


def test_monitor_never_reads_the_mixed_generic_attempt_table(tmp_path):
    mixed = tmp_path / "curated" / "router_route_attempts" / "dt=2026-07-19"
    mixed.mkdir(parents=True)
    import pandas as pd

    pd.DataFrame(
        [{"study_id": "h95-blinded", "metadata_json": json.dumps({"task_id": "secret"})}]
    ).to_parquet(mixed / "mixed.parquet", index=False)
    output = tmp_path / "out"
    summary = run_monitor(tmp_path, output, source_revision="test")
    assert summary["assignment_rows"] == 0
    assert summary["attempt_rows"] == 0


def test_frozen_bundle_quality_hash_is_rechecked_before_real_send(monkeypatch):
    assignment = next(
        row for row in _bundle()["assignments"] if row["experiment_axis"] == "quality"
    )
    bad = copy.deepcopy(_items()[0])
    bad["answer"] = "D"
    _enable(monkeypatch)
    with pytest.raises(RuntimeError, match="no longer matches"):
        capture._send_quality_assignment(None, assignment, bad)  # type: ignore[arg-type]


def test_quality_send_uses_prospective_token_floor_and_minimal_reasoning(monkeypatch):
    _enable(monkeypatch)
    assignment = next(
        row for row in _bundle()["assignments"] if row["experiment_axis"] == "quality"
    )
    item = {row["item_id"]: row for row in _items()}[assignment["quality_item_id"]]
    seen = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "B"}}]}

    class Client:
        @staticmethod
        def post(_url, *, headers, json):
            seen["headers"] = headers
            seen["body"] = json
            return Response()

    completion, generation, error, status = capture._send_quality_assignment(
        Client(), assignment, item  # type: ignore[arg-type]
    )
    assert completion is not None and generation is None and error is None and status == 200
    assert seen["body"]["max_tokens"] == 64
    assert seen["body"]["reasoning"] == {"effort": "minimal", "exclude": True}
