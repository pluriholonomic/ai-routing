from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from orcap.adaptive_router import POLICY_SPECS, build_adaptive_assignments
from orcap.analysis.adaptive_router_monitor import analyze, assignment_integrity


def _rows():
    return [
        {
            "run_id": "run-1",
            "block_id": "block-1",
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
        }
        for provider, quote, quality in (
            ("A", 0.0010, 0.99),
            ("B", 0.0012, 0.995),
            ("C", 0.0015, 0.98),
        )
    ]


def test_monitor_keeps_arm_outcomes_frozen_before_horizon(tmp_path):
    assignments, _ = build_adaptive_assignments(_rows(), run_id="run-1", seed=5, max_blocks=1)
    for row in assignments:
        row.update({"run_ts": "run-1", "dt": "2026-07-22"})
    assert assignment_integrity(pa.Table.from_pylist(assignments).to_pandas())["status"] == "pass"
    assignment_dir = tmp_path / "curated" / "adaptive_router_assignments" / "dt=2026-07-22"
    assignment_dir.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(assignments), assignment_dir / "part-0.parquet")
    attempt_rows = []
    for assignment in assignments:
        attempt_rows.append(
            {
                "study_id": assignment["study_id"],
                "task_id": assignment["task_id"],
                "observed_at": "2026-07-22T00:00:00Z",
                "outcome": "succeeded",
                "selected_provider": assignment["requested_provider"],
                "cost_usd": 0.001,
                "latency_ms": 100.0,
                "fallback_triggered": False,
                "metadata_json": json.dumps({"task_id": assignment["task_id"]}),
            }
        )
    attempt_dir = tmp_path / "curated" / "adaptive_router_attempts" / "dt=2026-07-22"
    attempt_dir.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(attempt_rows), attempt_dir / "part-0.parquet")
    out = tmp_path / "analysis"
    status = analyze(data_root=tmp_path, out_dir=out)
    assert status["complete_blocks"] == 1
    assert status["confirmatory_released"] is False
    assert not (out / "adaptive-router-policy-results.csv").exists()
    health = (out / "adaptive-router-arm-health.csv").read_text()
    for spec in POLICY_SPECS:
        assert str(spec["policy"]) in health


def test_monitor_reports_waiting_before_first_assignment(tmp_path):
    status = analyze(data_root=tmp_path, out_dir=tmp_path / "analysis")
    assert status["status"] == "collecting"
    assert status["launched_blocks"] == 0
    assert status["assignment_integrity"]["status"] == "waiting"
