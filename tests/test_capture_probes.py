import random

from orcap.capture_decomposition_probes import decomposition_tasks, public_provider_order
from orcap.capture_probes import hot_model_ids, probe_record
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
    assert by_policy["price_order_fallback"]["provider_order"] == [
        "Cheap",
        "Middle",
        "Expensive",
    ]
    assert by_policy["price_order_fallback"]["allow_fallbacks"] is True
