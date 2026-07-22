from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from orcap.analysis.score_memory import (
    MemoryConfig,
    build_history_panel,
    compare_models,
    support_summary,
)
from orcap.analysis.score_memory_monitor import run as run_monitor
from orcap.price_experiments import (
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
)


def _observations(blocks: int = 80) -> list[dict]:
    start = datetime(2026, 7, 22, tzinfo=UTC)
    providers = ["a", "b", "c"]
    rows = []
    prior_a_low = False
    for block in range(blocks):
        a_low = block % 4 in (0, 1)
        costs = np.asarray([0.6 if a_low else 1.2, 1.0, 1.1])
        # Realized choice depends on prior price state after conditioning on the
        # current menu, producing a recoverable temporal effect.
        selected = 0 if prior_a_low else 1
        for replicate in range(2):
            rows.append(
                {
                    "block_id": f"b-{block:03d}",
                    "task_id": f"b-{block:03d}-{replicate}",
                    "observed_at": start + timedelta(minutes=15 * block),
                    "providers": providers,
                    "costs": costs,
                    "selected_index": selected,
                }
            )
        prior_a_low = a_low
    return rows


def test_history_is_strictly_lagged_and_same_block_quality_cannot_leak():
    observations = _observations(4)
    first_time = observations[0]["observed_at"]
    quality = [{"observed_at": first_time, "provider": "a", "success": False, "latency_ms": 5000}]
    panel = build_history_panel(
        observations,
        quality,
        config=MemoryConfig(lag_blocks=(1, 4), finite_runs=(1,)),
    )
    first = panel[0]
    second_block = next(row for row in panel if row["block_id"] == "b-001")
    a = first["providers"].index("a")
    assert first["features"]["seen_h1"][a] == 0.0
    assert second_block["features"]["seen_h1"][a] > 0.0
    assert first["features"]["future_price_lead"][a] != first["features"]["price_h1"][a]


def test_future_fold_comparison_recovers_planted_memory():
    config = MemoryConfig(lag_blocks=(1, 4), finite_runs=(1, 4))
    panel = build_history_panel(_observations(), config=config)
    models, losses = compare_models(panel, config=config)
    assert not models.empty
    assert not losses.empty
    assert models["choices"].nunique() == 1
    dynamic = models[~models["model"].str.startswith("placebo") & models["model"].ne("no_memory")]
    assert dynamic.iloc[0]["gain_bits_per_choice"] > 0.01
    assert dynamic.iloc[0]["log_loss"] < models[models["model"] == "no_memory"].iloc[0]["log_loss"]


def test_support_gate_stays_accruing_on_short_panel():
    panel = build_history_panel(_observations(10), config=MemoryConfig(lag_blocks=(1,)))
    summary = support_summary(panel, [], pd.DataFrame())
    assert summary["support_status"] == "accruing"
    assert {"choices", "blocks", "duration", "quality_events"}.issubset(summary["support_failures"])


def test_support_gate_measures_coverage_only_within_default_broad_eligibility():
    panel = build_history_panel(_observations(2), config=MemoryConfig(lag_blocks=(1,)))
    summary = support_summary(
        panel,
        [],
        pd.DataFrame(),
        eligible_choices=5,
        minimum_menu_coverage=0.90,
    )
    assert summary["eligible_default_broad_choices"] == 5
    assert summary["covered_choices"] == 4
    assert summary["menu_coverage_rate"] == 0.8
    assert "menu_coverage" in summary["support_failures"]


def _write(table: pa.Table, root, name: str):
    path = root / "curated" / name / "dt=2026-07-22" / "run.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def test_monitor_writes_only_aggregate_release(tmp_path):
    observed = "2026-07-22T00:15:00Z"
    candidate_rows = []
    for index, provider in enumerate(("A", "B", "C")):
        candidate_rows.append(
            {
                "run_id": "run",
                "observed_at": observed,
                "study_id": "openrouter-glm52-routing-v1",
                "plan_version": "glm52-routing-plan-v1",
                "block_id": "block",
                "model_id": "z-ai/glm-5.2",
                "shape_id": "short_chat",
                "provider_name": provider,
                "endpoint_tag": f"tag-{index}",
                "endpoint_name": f"endpoint-{index}",
                "prompt_price_per_token": (index + 1) * 1e-6,
                "completion_price_per_token": (index + 1) * 2e-6,
                "expected_quote_usd": float(index + 1) * 1e-4,
                "conservative_quote_usd": float(index + 1) * 1e-4,
                "conservative_input_tokens": 96,
                "max_output_tokens": 8,
                "compatible": True,
                "exclusion_reason": None,
                "snapshot_sha256": "a" * 64,
                "payload_retained": False,
                "run_ts": "run",
                "dt": "2026-07-22",
            }
        )
    assignment = {
        "study_id": "openrouter-glm52-routing-v1",
        "plan_version": "glm52-routing-plan-v1",
        "run_id": "run",
        "block_id": "block",
        "task_id": "task",
        "model_id": "z-ai/glm-5.2",
        "shape_id": "short_chat",
        "policy": "default_broad",
        "replicate_index": 0,
        "policy_order": 0,
        "requested_provider": None,
        "requested_endpoint_tag": None,
        "provider_order_tags": None,
        "provider_only_tags": None,
        "provider_sort": None,
        "allow_fallbacks": True,
        "max_price_prompt_per_mtok": 10.0,
        "max_price_completion_per_mtok": 10.0,
        "task_quote_cap_usd": 0.01,
        "conservative_input_tokens": 96,
        "max_output_tokens": 8,
        "session_group": "fresh",
        "assignment_seed": "1",
        "manifest_sha256": "b" * 64,
        "preflight_only": True,
        "payload_retained": False,
        "run_ts": "run",
        "dt": "2026-07-22",
    }
    attempt = {
        "event_id": "event",
        "observed_at": observed,
        "router_id": "openrouter",
        "route_request_id": "task",
        "attempt_index": 0,
        "model_id": "z-ai/glm-5.2",
        "requested_provider": None,
        "selected_provider": "A",
        "provider_variant": None,
        "policy": "default_broad",
        "policy_score": None,
        "fallback_triggered": False,
        "retry_reason": None,
        "outcome": "succeeded",
        "latency_ms": 10.0,
        "input_tokens": 7,
        "output_tokens": 1,
        "cost_usd": 1e-6,
        "metadata_json": json.dumps({"task_id": "task"}),
        "schema_version": "router-route-attempt-v1",
        "payload_retained": False,
        "run_ts": "run",
        "dt": "2026-07-22",
        "study_id": "openrouter-glm52-routing-v1",
    }
    _write(
        pa.Table.from_pylist(candidate_rows, schema=PRICE_RESPONSE_CANDIDATE_SCHEMA),
        tmp_path,
        "glm52_routing_candidates",
    )
    _write(
        pa.Table.from_pylist([assignment], schema=PRICE_RESPONSE_ASSIGNMENT_SCHEMA),
        tmp_path,
        "glm52_routing_assignments",
    )
    # Dedicated attempt tables are schemaless in production; use all expected fields.
    _write(pa.Table.from_pylist([attempt]), tmp_path, "glm52_routing_attempts")
    output = tmp_path / "analysis"
    summary = run_monitor(tmp_path, output, source_revision="test")
    assert summary["support_status"] == "accruing"
    assert summary["eligible_default_broad_choices"] == 1
    assert summary["covered_choices"] == 1
    assert summary["menu_coverage_rate"] == 1.0
    assert (output / "score_memory_model_comparison.parquet").is_file()
    assert (output / "score_memory_quality_aggregate.parquet").is_file()
    assert (output / "score_memory_policy_aggregate.parquet").is_file()
    assert (output / "score_memory_panel.png").is_file()
    assert (output / "score-memory.html").is_file()
    assert not (output / "score_memory_choice_panel.parquet").exists()


def test_monitor_handles_assignment_only_preflight(tmp_path):
    observed = "2026-07-22T00:15:00Z"
    candidate = {
        "run_id": "run",
        "observed_at": observed,
        "study_id": "openrouter-glm52-routing-v1",
        "plan_version": "glm52-routing-plan-v1",
        "block_id": "block",
        "model_id": "z-ai/glm-5.2",
        "shape_id": "short_chat",
        "provider_name": "A",
        "endpoint_tag": "tag-a",
        "endpoint_name": "endpoint-a",
        "prompt_price_per_token": 1e-6,
        "completion_price_per_token": 2e-6,
        "expected_quote_usd": 1e-4,
        "conservative_quote_usd": 1e-4,
        "conservative_input_tokens": 96,
        "max_output_tokens": 8,
        "compatible": True,
        "exclusion_reason": None,
        "snapshot_sha256": "a" * 64,
        "payload_retained": False,
        "run_ts": "run",
        "dt": "2026-07-22",
    }
    assignment = {
        "study_id": "openrouter-glm52-routing-v1",
        "plan_version": "glm52-routing-plan-v1",
        "run_id": "run",
        "block_id": "block",
        "task_id": "task",
        "model_id": "z-ai/glm-5.2",
        "shape_id": "short_chat",
        "policy": "default_broad",
        "replicate_index": 0,
        "policy_order": 0,
        "requested_provider": None,
        "requested_endpoint_tag": None,
        "provider_order_tags": None,
        "provider_only_tags": None,
        "provider_sort": None,
        "allow_fallbacks": True,
        "max_price_prompt_per_mtok": 10.0,
        "max_price_completion_per_mtok": 10.0,
        "task_quote_cap_usd": 0.01,
        "conservative_input_tokens": 96,
        "max_output_tokens": 8,
        "session_group": "fresh",
        "assignment_seed": "1",
        "manifest_sha256": "b" * 64,
        "preflight_only": True,
        "payload_retained": False,
        "run_ts": "run",
        "dt": "2026-07-22",
    }
    _write(
        pa.Table.from_pylist([candidate], schema=PRICE_RESPONSE_CANDIDATE_SCHEMA),
        tmp_path,
        "glm52_routing_candidates",
    )
    _write(
        pa.Table.from_pylist([assignment], schema=PRICE_RESPONSE_ASSIGNMENT_SCHEMA),
        tmp_path,
        "glm52_routing_assignments",
    )
    summary = run_monitor(tmp_path, tmp_path / "analysis", source_revision="preflight")
    assert summary["covered_choices"] == 0
    assert summary["support_status"] == "accruing"
