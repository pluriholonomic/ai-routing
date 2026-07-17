from __future__ import annotations

import random

import pyarrow.parquet as pq

import orcap.capture_decomposition_replication as replication
from orcap.capture_decomposition_probes import POLICIES


def _catalog(n: int = 12):
    models = {
        "data": [
            {
                "id": f"org/model-{index}",
                "canonical_slug": f"org/model-{index}",
                "hugging_face_id": (
                    f"org/model-{index}" if index not in {8, 10} else ""
                ),
            }
            for index in range(1, n + 1)
        ]
    }
    rankings = {
        "data": [
            {
                "model_permaslug": f"org/model-{index}",
                "total_prompt_tokens": 10_000 - index,
                "total_completion_tokens": 0,
            }
            for index in range(1, n + 1)
        ]
    }
    return rankings, models


def _endpoints():
    return [
        {"provider": "cheap", "price": 2e-6, "input_price": 1e-6},
        {"provider": "backup", "price": 4e-6, "input_price": 2e-6},
    ]


def test_ranked_candidates_exclude_h80_h81_and_missing_hf_links() -> None:
    rankings, models = _catalog()
    candidates = replication.ranked_open_weight_candidates(
        rankings, models, min_rank=7, max_rank=12
    )

    assert [row["ranking_position"] for row in candidates] == [7, 9, 11, 12]
    assert all(row["hugging_face_id"] for row in candidates)


def test_tasks_fix_assigned_first_and_randomize_only_the_remainder() -> None:
    tasks = replication.tasks_with_assigned_first(
        _endpoints(), "price_order_fallback", random.Random(7)
    )

    assert tasks[0]["policy"] == "price_order_fallback"
    assert {task["policy"] for task in tasks} == set(POLICIES)
    assert tasks[0]["allow_fallbacks"] is True
    assert tasks[0]["provider_order"] == ["cheap", "backup"]


def test_plan_selects_three_eligible_models_and_balances_first_policy(monkeypatch) -> None:
    rankings, models = _catalog()

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    class FakeClient:
        def get(self, url):
            if url == replication.RANKINGS_URL:
                return FakeResponse(rankings)
            if url == replication.MODELS_URL:
                return FakeResponse(models)
            raise AssertionError(url)

    def fake_audit(client, model_id):
        return _endpoints(), {
            "endpoint_fetch_status": "ok",
            "endpoint_http_status": 200,
            "raw_endpoint_count": 2,
            "positive_quote_count": 2,
            "distinct_provider_count": 2,
        }

    monkeypatch.setattr(replication, "quoted_endpoints_audit", fake_audit)
    plan, eligibility, summary = replication.build_replication_plan(
        FakeClient(), run_id="20260717T050000Z", run_seed=19
    )

    assert summary["triplet_planned"] is True
    assert len(plan) == 3
    assert {row["assigned_first_policy"] for row in plan} == set(POLICIES)
    assert all(row["tasks"][0]["policy"] == row["assigned_first_policy"] for row in plan)
    selected = [row for row in eligibility if row["selected_for_triplet"]]
    assert len(selected) == 3
    assert {row["assigned_first_policy"] for row in selected} == set(POLICIES)
    assert all(row["selection_probability"] == 0.75 for row in selected)


def test_replication_eligibility_writer_preserves_assignment_without_payload(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(replication, "run_timestamp", lambda: "20260717T050001Z")
    rankings, models = _catalog()

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    class FakeClient:
        def get(self, url):
            return FakeResponse(rankings if url == replication.RANKINGS_URL else models)

    monkeypatch.setattr(
        replication,
        "quoted_endpoints_audit",
        lambda client, model_id: (
            _endpoints(),
            {
                "endpoint_fetch_status": "ok",
                "endpoint_http_status": 200,
                "raw_endpoint_count": 2,
                "positive_quote_count": 2,
                "distinct_provider_count": 2,
            },
        ),
    )
    _, eligibility, _ = replication.build_replication_plan(
        FakeClient(), run_id="20260717T050000Z", run_seed=23
    )
    path = replication.write_replication_eligibility(
        eligibility,
        run_ts="20260717T050000Z",
        dt="2026-07-17",
        curated_dir=tmp_path,
    )

    frame = pq.ParquetFile(path).read().to_pandas()
    assert frame["payload_retained"].eq(False).all()  # noqa: E712
    assert frame["selected_for_triplet"].sum() == 3
    assert frame.loc[frame["selected_for_triplet"], "assigned_first_policy"].nunique() == 3
