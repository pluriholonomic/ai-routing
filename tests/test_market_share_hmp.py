from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from orcap.capture_market_share_hmp import (
    _existing_tasks,
    build_plan_bundle,
    validate_bundle,
    write_plan_bundle,
)
from orcap.market_share_hmp import (
    MODEL_ID,
    build_paid_assignments,
    build_wave_plans,
    detect_events,
    elasticity_identity,
    finite_path_elasticity,
    routing_shares,
)


def _run(base: datetime, minutes: int) -> str:
    return (base + timedelta(minutes=minutes)).strftime("%Y%m%dT%H%M%SZ")


def _snapshot_frame(base: datetime) -> pd.DataFrame:
    providers = ["Novita", "StreamLake", "Inceptron", "Together", "Ambient", "Z.AI"]
    prices = {provider: 1e-6 for provider in providers}
    rows = []
    for minute in range(0, 76, 5):
        if minute == 10:
            prices["Novita"] = 0.90e-6
        if minute == 15:
            prices["StreamLake"] = 0.95e-6
        for index, provider in enumerate(providers):
            rows.append(
                {
                    "run_ts": _run(base, minute),
                    "model_id": MODEL_ID,
                    "provider_name": provider,
                    "tag": f"tag-{index}",
                    "price_prompt": prices[provider],
                    "price_completion": prices[provider],
                    "price_request": 0.0,
                    "status": "ok",
                    "uptime_last_5m": 1.0,
                }
            )
    return pd.DataFrame(rows)


def _candidates() -> list[dict]:
    providers = [
        "Novita",
        "StreamLake",
        "Inceptron",
        "Together",
        "Ambient",
        "Z.AI",
    ]
    rows = []
    for index, provider in enumerate(providers):
        price = (1.0 + 0.05 * index) * 1e-6
        rows.append(
            {
                "run_id": "run-1",
                "observed_at": "20260722T032000Z",
                "study_id": "source",
                "plan_version": "source",
                "block_id": "source",
                "model_id": MODEL_ID,
                "shape_id": "short_chat",
                "provider_name": provider,
                "endpoint_tag": f"tag-{index}",
                "endpoint_name": provider,
                "prompt_price_per_token": price,
                "completion_price_per_token": price,
                "expected_quote_usd": price * 104,
                "conservative_quote_usd": price * 104,
                "conservative_input_tokens": 96,
                "max_output_tokens": 8,
                "compatible": True,
                "exclusion_reason": None,
                "snapshot_sha256": f"sha-{index}",
                "payload_retained": False,
            }
        )
    return rows


def test_path_identity_has_singleton_zero_and_multi_cutter_wedge():
    shares = routing_shares([0.65, 0.65, 0.65, 1.0, 1.0], eta=1.6482780609377246)
    singleton = elasticity_identity(shares, focal=0, cutters=[0], eta=1.6482780609377246)
    group = elasticity_identity(shares, focal=0, cutters=[0, 1, 2], eta=1.6482780609377246)
    assert singleton["path_wedge"] == pytest.approx(0.0, abs=1e-14)
    assert group["path_wedge"] > 0
    finite = finite_path_elasticity(
        [0.65, 0.65, 0.65, 1.0, 1.0],
        focal=0,
        cutters=[0, 1, 2],
        cut_fraction=0.10,
        eta=1.6482780609377246,
    )
    assert np.isfinite(finite["finite_path_elasticity"])
    assert finite["active_group_share_change"] > 0


def test_event_finalization_uses_future_public_captures_but_no_paid_outcome():
    base = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
    events = detect_events(
        _snapshot_frame(base),
        active_providers=["Novita", "StreamLake", "Inceptron"],
        author_providers=["Z.AI"],
        eta=1.6482780609377246,
        minimum_cut_fraction=0.02,
        comove_window_minutes=15,
        maximum_snapshot_gap_minutes=12,
        minimum_post_captures=2,
        now=base + timedelta(minutes=75),
    )
    assert len(events) == 1
    event = events[0]
    assert event["focal_provider"] == "Novita"
    assert event["multiplicity"] == "pair"
    assert event["co_cutters"] == ["StreamLake"]
    assert event["co_cutter_count"] == 1
    assert event["co_cutter_share_mass"] > 0
    assert event["co_cutter_exposure"] > 0
    assert event["clean_event"] is True
    assert event["event_status"] == "final"
    assert event["contamination_window_complete"] is True
    assert "selected_provider" not in event


def test_provisional_event_creates_only_the_event_time_wave():
    base = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
    frame = _snapshot_frame(base)
    frame = frame[frame["run_ts"].map(lambda value: value <= _run(base, 10))]
    events = detect_events(
        frame,
        active_providers=["Novita", "StreamLake", "Inceptron"],
        author_providers=["Z.AI"],
        eta=1.6482780609377246,
        minimum_cut_fraction=0.02,
        comove_window_minutes=15,
        maximum_snapshot_gap_minutes=12,
        minimum_post_captures=2,
        now=base + timedelta(minutes=10),
    )
    assert len(events) == 1
    assert events[0]["event_status"] == "provisional"
    assert events[0]["multiplicity"] == "pending"
    assert events[0]["clean_event"] is False
    waves = build_wave_plans(
        events,
        offsets_minutes=[0, 15, 60],
        tolerances_minutes=[10, 20, 45],
        seed=9,
    )
    assert [row["wave_id"] for row in waves] == ["m0"]


def test_author_quote_change_excludes_the_cluster_without_erasing_it():
    base = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
    frame = _snapshot_frame(base)
    changed = frame["run_ts"].eq(_run(base, 15)) & frame["provider_name"].eq("Z.AI")
    frame.loc[changed, ["price_prompt", "price_completion"]] = 1.10e-6
    after = frame["run_ts"].map(lambda value: value >= _run(base, 15))
    author = frame["provider_name"].eq("Z.AI")
    frame.loc[after & author, ["price_prompt", "price_completion"]] = 1.10e-6
    events = detect_events(
        frame,
        active_providers=["Novita", "StreamLake", "Inceptron"],
        author_providers=["Z.AI"],
        eta=1.6482780609377246,
        minimum_cut_fraction=0.02,
        comove_window_minutes=15,
        maximum_snapshot_gap_minutes=12,
        minimum_post_captures=2,
        now=base + timedelta(minutes=75),
    )
    assert len(events) == 1
    assert events[0]["clean_event"] is False
    assert "author_price_changed" in events[0]["exclusion_reason"]


def test_public_derank_contaminates_the_full_frozen_window():
    base = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
    enforcement = pd.DataFrame(
        [
            {
                "run_ts": _run(base, 40),
                "model_permaslug": "z-ai/glm-5.2",
                "provider_name": "Novita",
                "is_deranked": True,
            }
        ]
    )
    events = detect_events(
        _snapshot_frame(base),
        active_providers=["Novita", "StreamLake", "Inceptron"],
        author_providers=["Z.AI"],
        eta=1.6482780609377246,
        minimum_cut_fraction=0.02,
        comove_window_minutes=15,
        maximum_snapshot_gap_minutes=12,
        minimum_post_captures=2,
        enforcement=enforcement,
        now=base + timedelta(minutes=75),
    )
    assert events[0]["clean_event"] is False
    assert "public_derank" in events[0]["exclusion_reason"]


def test_six_menu_arms_are_randomized_complete_and_exact():
    wave = {
        "event_id": "event-1",
        "wave_id": "m15",
        "focal_provider": "Novita",
        "co_cutters": ["StreamLake"],
    }
    assignments, summary = build_paid_assignments(
        _candidates(),
        wave,
        active_providers=["Novita", "StreamLake", "Inceptron"],
        anchor_providers=["Together", "Ambient"],
        replicates_per_arm=4,
        run_id="run-1",
        seed=17,
    )
    assert len(assignments) == 24
    assert len({row["task_id"] for row in assignments}) == 24
    assert set(summary["policy_counts"].values()) == {4}
    policies = {row["policy"] for row in assignments}
    assert policies == {
        "broad_default",
        "broad_price_sort",
        "singleton_with_anchors",
        "pair_with_anchors",
        "active_group_with_anchors",
        "anchor_only",
    }
    singleton = next(row for row in assignments if row["policy"] == "singleton_with_anchors")
    pair = next(row for row in assignments if row["policy"] == "pair_with_anchors")
    anchors = next(row for row in assignments if row["policy"] == "anchor_only")
    assert set(singleton["provider_only_tags"]) == {"tag-0", "tag-3", "tag-4"}
    assert set(pair["provider_only_tags"]) == {"tag-0", "tag-1", "tag-3", "tag-4"}
    assert set(anchors["provider_only_tags"]) == {"tag-3", "tag-4"}
    assert all(row["session_group"].startswith("fresh|") for row in assignments)


def test_uploaded_assignment_is_an_at_most_once_reservation():
    spent = pd.DataFrame(
        [{"study_id": "openrouter-glm52-market-share-hmp-v1", "task_id": "attempted"}]
    )
    assigned = pd.DataFrame(
        [{"study_id": "openrouter-glm52-market-share-hmp-v1", "task_id": "reserved"}]
    )
    assert _existing_tasks(spent, assigned) == {"attempted", "reserved"}


def test_plan_is_protocol_hashed_assignment_first_and_tamper_evident(monkeypatch, tmp_path):
    base = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
    path = tmp_path / "curated" / "endpoints_snapshots" / "dt=2026-07-22"
    path.mkdir(parents=True)
    _snapshot_frame(base).to_parquet(path / "snapshots.parquet", index=False)
    monkeypatch.setattr(
        "orcap.capture_market_share_hmp.freeze_candidates",
        lambda *_args, **_kwargs: (_candidates(), []),
    )
    bundle = build_plan_bundle(
        object(),
        data_root=tmp_path,
        run_id="run-1",
        seed=19,
        now=base + timedelta(minutes=75),
    )
    validate_bundle(bundle)
    assert bundle["summary"]["planned_tasks"] == 24
    assert bundle["summary"]["new_public_panel_rows"] > 0
    assert all("selected_provider" not in row for row in bundle["public_panel"])
    assert len(bundle["summary"]["protocol_sha256"]) == 64
    assert all(
        row["protocol_sha256"] == bundle["summary"]["protocol_sha256"]
        for row in bundle["assignments"]
    )
    assert bundle["summary"]["claims"]["collusion_identified"] is False
    paths = write_plan_bundle(
        bundle,
        bundle_path=tmp_path / "plan.json",
        curated_dir=tmp_path / "written" / "curated",
    )
    assert Path(paths["run_ledger_path"]).is_file()
    assert Path(paths["assignment_path"]).is_file()
    assert Path(paths["public_panel_path"]).is_file()
    assignment = pd.read_parquet(paths["assignment_path"])
    assert assignment["protocol_sha256"].eq(bundle["summary"]["protocol_sha256"]).all()
    serialized = str(bundle).lower()
    for forbidden in ("messages", "response_text", "authorization", "api_key"):
        assert forbidden not in serialized
    tampered = copy.deepcopy(bundle)
    tampered["assignments"][0]["policy"] = "tampered"
    with pytest.raises(ValueError, match="manifest mismatch"):
        validate_bundle(tampered)


def test_hourly_background_block_is_separate_and_lower_priority(monkeypatch, tmp_path):
    base = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
    frame = _snapshot_frame(base)
    frame.loc[:, ["price_prompt", "price_completion"]] = 1e-6
    path = tmp_path / "curated" / "endpoints_snapshots" / "dt=2026-07-22"
    path.mkdir(parents=True)
    frame.to_parquet(path / "snapshots.parquet", index=False)
    monkeypatch.setattr(
        "orcap.capture_market_share_hmp.freeze_candidates",
        lambda *_args, **_kwargs: (_candidates(), []),
    )
    bundle = build_plan_bundle(
        object(),
        data_root=tmp_path,
        run_id="run-background",
        seed=23,
        now=base + timedelta(minutes=75),
    )
    assert bundle["summary"]["selected_wave"]["multiplicity"] == "background"
    assert bundle["summary"]["planned_tasks"] == 12
    assert all("mshmp-background-" in row["event_id"] for row in bundle["assignments"])
    assert bundle["event_registry"] == []
