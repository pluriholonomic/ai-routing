from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from orcap.analysis.live_router_exponent import (
    _read_tables,
    build_observations,
    estimate_windows,
    render_dashboard,
)
from orcap.analysis.router_exponent import probabilities


def test_candidate_assignment_attempt_join_preserves_missing_menu_selection():
    candidates = pd.DataFrame(
        [
            {
                "block_id": "b1",
                "provider_name": provider,
                "expected_quote_usd": quote,
                "compatible": True,
            }
            for provider, quote in (("A", 1.0), ("B", 2.0))
        ]
    )
    assignments = pd.DataFrame(
        [
            {
                "task_id": "t1",
                "run_id": "r1",
                "block_id": "b1",
                "model_id": "m1",
                "shape_id": "short_chat",
                "policy": "default_loose_fresh",
            },
            {
                "task_id": "t2",
                "run_id": "r1",
                "block_id": "b1",
                "model_id": "m1",
                "shape_id": "short_chat",
                "policy": "pinned_a",
            },
        ]
    )
    attempts = pd.DataFrame(
        [
            {
                "study_id": "openrouter-price-response-v1",
                "metadata_json": json.dumps({"task_id": "t1"}),
                "observed_at": "2026-07-19T00:00:00Z",
                "selected_provider": "B",
                "outcome": "succeeded",
                "cost_usd": 0.1,
                "latency_ms": 10,
            },
            {
                "study_id": "openrouter-price-response-v1",
                "metadata_json": json.dumps({"task_id": "t2"}),
                "observed_at": "2026-07-19T00:00:00Z",
                "selected_provider": "outside",
                "outcome": "succeeded",
                "cost_usd": 0.1,
                "latency_ms": 10,
            },
        ]
    )
    observations = build_observations(candidates, assignments, attempts)
    assert len(observations) == 1
    assert observations[0]["selected_index"] == 1
    assert observations[0]["providers"] == ["a", "b"]


def test_market_measurement_default_choices_enter_exponent_without_duplicate_attempts():
    candidates = pd.DataFrame(
        [
            {
                "block_id": "market-block",
                "provider_name": provider,
                "expected_quote_usd": quote,
                "compatible": True,
            }
            for provider, quote in (("A", 1.0), ("B", 2.0), ("C", 3.0))
        ]
    )
    assignments = pd.DataFrame(
        [
            {
                "task_id": "market-task",
                "run_id": "market-run",
                "block_id": "market-block",
                "model_id": "model/market",
                "shape_id": "short_chat",
                "policy": "default_broad",
                "observed_at": "assignment-time-must-not-shadow-attempt",
            }
        ]
    )
    attempt = {
        "study_id": "openrouter-market-measurement-v1",
        "metadata_json": json.dumps({"task_id": "market-task"}),
        "observed_at": "2026-07-19T00:00:00Z",
        "selected_provider": "B",
        "outcome": "succeeded",
        "cost_usd": 0.1,
        "latency_ms": 10,
    }
    observations = build_observations(candidates, assignments, pd.DataFrame([attempt, attempt]))

    assert len(observations) == 1
    assert observations[0]["policy"] == "default_broad"
    assert observations[0]["selected_index"] == 1


def test_end_to_end_live_estimator_recovers_exponent_and_gates_thin_windows(tmp_path):
    rng = np.random.default_rng(12)
    rows = []
    for index in range(1500):
        ratio = 1.05 + 0.8 * (index % 31) / 30
        costs = np.array([1.0, ratio, ratio**2, ratio**3, ratio**4])
        selected = int(rng.choice(5, p=probabilities(costs, 2.0)))
        rows.append(
            {
                "block_id": f"b-{index}",
                "model_id": f"m-{index % 10}",
                "shape_id": "short_chat",
                "selected_provider": f"p-{selected}",
                "selected_index": selected,
                "costs": costs,
                "observed_at": "2026-07-19T00:00:00Z",
            }
        )
    estimates, scores = estimate_windows(
        rows,
        now=datetime(2026, 7, 19, 1, tzinfo=UTC),
        bootstrap_draws=25,
    )
    expanding = estimates[estimates["window_id"] == "expanding"].iloc[0]
    assert expanding["support_status"] == "ready"
    assert abs(expanding["eta_published"] - 2.0) < 0.25
    assert not scores.empty
    thin, _ = estimate_windows(rows[:20], bootstrap_draws=0)
    assert thin["eta_published"].isna().all()
    dashboard = tmp_path / "exponent.html"
    render_dashboard(estimates, scores, dashboard)
    text = dashboard.read_text()
    assert "Live owned-routing price exponent" in text
    assert "task_id" not in text


def test_table_reader_avoids_partition_column_type_merging(tmp_path):
    path = tmp_path / "curated/sample/dt=2026-07-19/row.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pandas(
            pd.DataFrame([{"dt": "2026-07-19", "value": 1}]), preserve_index=False
        ),
        path,
    )
    frame = _read_tables(tmp_path, ("sample",))
    assert frame.to_dict("records") == [{"dt": "2026-07-19", "value": 1}]
