import json
import os
import random

import pyarrow.parquet as pq

from orcap.capture_decomposition_probes import (
    decomposition_tasks,
    public_provider_order,
    write_decomposition_plan,
    write_decomposition_plan_audit,
    write_eligibility_audit,
)
from orcap.capture_probes import (
    _send_probe,
    hot_model_ids,
    probe_record,
    quoted_endpoints_audit,
)
from orcap.route_telemetry import validate_attempt


def test_hot_model_ids_resolves_permaslugs_and_skips_variants():
    rankings = {
        "data": [
            {"model_permaslug": "a/one-20260101", "total_prompt_tokens": 100},
            {"model_permaslug": "b/two", "total_completion_tokens": 50},
            {"model_permaslug": "c/missing", "total_prompt_tokens": 10},
        ]
    }
    models = {
        "data": [
            {"id": "a/one", "canonical_slug": "a/one-20260101"},
            {"id": "b/two", "canonical_slug": "b/two"},
            {"id": "b/two:free", "canonical_slug": "b/two:free"},
        ]
    }
    assert hot_model_ids(rankings, models, n=5) == ["a/one", "b/two"]


def test_probe_record_validates_and_keeps_no_payload():
    completion = {"id": "gen-123", "provider": "DeepInfra"}
    generation = {
        "data": {
            "provider_name": "DeepInfra",
            "latency": 412,
            "native_tokens_prompt": 9,
            "native_tokens_completion": 1,
            "total_cost": 0.0000021,
        }
    }
    rec = probe_record(
        "a/one", completion, generation, observed_at="20260712T130000Z", status_code=200
    )
    validated = validate_attempt(rec)
    assert validated["selected_provider"] == "DeepInfra"
    assert validated["outcome"] == "succeeded"
    assert validated["cost_usd"] == 0.0000021
    assert validated["payload_retained"] is False


def test_probe_record_failure_path_still_validates():
    rec = probe_record(
        "a/one", None, None, observed_at="20260712T130000Z", error="http_429", status_code=429
    )
    validated = validate_attempt(rec)
    assert validated["outcome"] == "failed"
    assert validated["selected_provider"] is None
    assert validated["retry_reason"] == "http_429"


def test_decomposition_tasks_hold_public_order_fixed_and_randomize_policy():
    endpoints = [
        {"provider": "Cheap", "price": 1.0},
        {"provider": "Cheap", "price": 1.1},
        {"provider": "Middle", "price": 2.0},
        {"provider": "Expensive", "price": 3.0},
    ]
    assert public_provider_order(endpoints) == ["Cheap", "Middle", "Expensive"]
    tasks = decomposition_tasks(endpoints, random.Random(17))
    assert {task["policy"] for task in tasks} == {
        "delegated_default",
        "price_only_no_fallback",
        "price_order_fallback",
    }
    by_policy = {task["policy"]: task for task in tasks}
    assert by_policy["price_only_no_fallback"]["provider_order"] == ["Cheap"]
    assert by_policy["price_only_no_fallback"]["provider_only"] == ["Cheap"]
    assert by_policy["price_order_fallback"]["provider_order"] == [
        "Cheap",
        "Middle",
        "Expensive",
    ]
    assert by_policy["price_order_fallback"]["provider_only"] == [
        "Cheap",
        "Middle",
        "Expensive",
    ]
    assert by_policy["price_order_fallback"]["allow_fallbacks"] is True


def test_send_probe_can_restrict_fallback_to_explicit_provider_set():
    class Response:
        status_code = 429

    class Client:
        body = None

        def post(self, _url, *, headers, json):
            assert headers["Authorization"].startswith("Bearer ")
            self.body = json
            return Response()

    client = Client()
    previous = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    try:
        _, _, error, status = _send_probe(
            client,
            "model/a",
            provider_order=["A", "B"],
            provider_only=["A", "B"],
            allow_fallbacks=True,
        )
    finally:
        if previous is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = previous
    assert status == 429 and error == "http_429"
    assert client.body["provider"] == {
        "order": ["A", "B"],
        "only": ["A", "B"],
        "allow_fallbacks": True,
    }


def test_quoted_endpoints_audit_separates_fetch_and_eligibility_inputs():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "data": {
                    "endpoints": [
                        {
                            "provider_name": "Expensive",
                            "pricing": {"prompt": "0.000002", "completion": "0.000004"},
                        },
                        {
                            "provider_name": "Cheap",
                            "pricing": {"prompt": "0.000001", "completion": "0.000003"},
                        },
                        {
                            "provider_name": "Free",
                            "pricing": {"prompt": "0", "completion": "0"},
                        },
                    ]
                }
            }

    class Client:
        @staticmethod
        def get(_url):
            return Response()

    endpoints, audit = quoted_endpoints_audit(Client(), "model/a")

    assert [endpoint["provider"] for endpoint in endpoints] == ["Cheap", "Expensive"]
    assert endpoints[0]["input_price"] == 0.000001
    assert audit == {
        "endpoint_fetch_status": "ok",
        "endpoint_http_status": 200,
        "raw_endpoint_count": 3,
        "positive_quote_count": 2,
        "distinct_provider_count": 2,
    }


def test_write_eligibility_audit_uses_stable_privacy_safe_schema(tmp_path):
    path = write_eligibility_audit(
        [
            {
                "run_id": "20260715T120000Z",
                "observed_at": "20260715T120001Z",
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "ranking_position": 5,
                "evaluation_order": 0,
                "model_id": "model/a",
                "endpoint_fetch_status": "ok",
                "endpoint_http_status": 200,
                "raw_endpoint_count": 3,
                "positive_quote_count": 3,
                "distinct_provider_count": 2,
                "eligible": True,
                "exclusion_reason": "eligible",
                "provider_order_sha256": "abc",
                "public_min_completion_price": 0.000001,
                "public_max_completion_price": 0.000003,
                "public_quote_cost_cap_usd": 0.0001,
                "quote_cap_input_tokens": 64,
                "request_timeout_ms": 60_000.0,
                "block_id": "block-a",
                "block_seed": "17",
                "first_policy_planned": "delegated_default",
                "assignment_probability_first": 1 / 3,
                "randomized_order": True,
                "run_seed": "18446744073709551615",
            }
        ],
        run_ts="20260715T120000Z",
        dt="2026-07-15",
        curated_dir=tmp_path,
    )

    assert path is not None
    row = pq.ParquetFile(path).read().to_pylist()[0]
    assert row["eligible"] is True
    assert row["payload_retained"] is False
    assert row["run_seed"] == "18446744073709551615"
    assert row["block_seed"] == "17"
    assert row["first_policy_planned"] == "delegated_default"


def test_write_decomposition_plan_is_outcome_free_and_pre_request(tmp_path):
    path = write_decomposition_plan(
        {
            "plan_id": "block-a",
            "planned_at": "20260715T120001Z",
            "run_id": "20260715T120000Z",
            "study_id": "openrouter-fallback-selection-decomposition-v1",
            "ranking_position": 5,
            "evaluation_order": 0,
            "model_id": "model/a",
            "block_id": "block-a",
            "block_seed": "17",
            "first_policy_planned": "delegated_default",
            "assignment_probability_first": 1 / 3,
            "randomized_order": True,
            "public_provider_count": 3,
            "public_provider_order_sha256": "abc",
        },
        run_ts="20260715T120000Z-000",
        dt="2026-07-15",
        curated_dir=tmp_path,
    )

    row = pq.ParquetFile(path).read().to_pylist()[0]
    assert row["first_policy_planned"] == "delegated_default"
    assert row["payload_retained"] is False
    assert not {"outcome", "cost_usd", "latency_ms", "selected_provider"} & set(row)


def test_write_decomposition_plan_audit_is_separate_and_outcome_free(tmp_path):
    run_id = "20260715T120000Z"
    plan_path = write_decomposition_plan(
        {
            "plan_id": "block-a",
            "planned_at": "20260715T120001Z",
            "run_id": run_id,
            "study_id": "openrouter-fallback-selection-decomposition-v1",
            "ranking_position": 5,
            "evaluation_order": 0,
            "model_id": "model/a",
            "block_id": "block-a",
            "block_seed": "17",
            "first_policy_planned": "delegated_default",
            "assignment_probability_first": 1 / 3,
            "randomized_order": True,
            "public_provider_count": 3,
            "public_provider_order_sha256": "abc",
        },
        run_ts=f"{run_id}-000",
        dt="2026-07-15",
        curated_dir=tmp_path / "curated",
    )
    output_path = tmp_path / "audit" / "plan.json"

    result = write_decomposition_plan_audit(
        [plan_path],
        run_id=run_id,
        output_path=output_path,
        source_commit="abc123",
        workflow_run_id="42",
    )

    manifest = json.loads(result.read_text())
    assert manifest["plan_file_count"] == 1
    assert manifest["plan_row_count"] == 1
    assert manifest["run_id_match"] is True
    assert manifest["study_id_match"] is True
    assert manifest["forbidden_fields_present"] == []
    assert manifest["outcomes_included"] is False
    assert manifest["request_records_included"] is False
    assert manifest["capture_log_outcome_fields"] is False
    assert manifest["plan_persisted_before_probe_call_by_program_order"] is True
