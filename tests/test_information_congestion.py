from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

import orcap.capture_information_congestion as capture
import orcap.capture_information_congestion_quality as quality_capture
from orcap.analysis.information_congestion_monitor import (
    estimate_beta,
    estimate_tau,
    fit_congestion_gamma,
    identifying_rank_model_count,
    kstar_by_n,
    outcome_surface,
)
from orcap.analysis.information_congestion_readiness import (
    assignment_support,
    capture_continuity,
    privacy_gate,
    reconciliation,
)
from orcap.analysis.information_congestion_shocks import (
    endpoint_shocks,
    mark_event_contamination,
)
from orcap.information_congestion import (
    DEFAULT_CONFIG,
    build_factorial_assignments,
    canonical_bundle_hash,
    classify_provider_roles,
    load_protocol,
    market_epoch,
    select_responsive_subset,
    subset_overlap,
    validate_factorial_assignments,
)


def _candidate(model: str, provider: str, price: float) -> dict:
    key = provider.casefold()
    return {
        "run_id": "run-1",
        "observed_at": "2026-07-23T01:00:00+00:00",
        "study_id": "openrouter-information-congestion-v1",
        "plan_version": "information-congestion-plan-v1",
        "block_id": f"block-{model}",
        "model_id": model,
        "shape_id": "short_chat",
        "provider_name": provider,
        "endpoint_tag": f"tag-{key}",
        "endpoint_name": provider,
        "prompt_price_per_token": price,
        "completion_price_per_token": price * 2,
        "expected_quote_usd": price * 112,
        "conservative_quote_usd": price * 112,
        "conservative_input_tokens": 96,
        "max_output_tokens": 8,
        "compatible": True,
        "exclusion_reason": None,
        "snapshot_sha256": f"sha-{key}",
        "payload_retained": False,
    }


def _protocol() -> tuple[dict, str]:
    protocol, digest = load_protocol(DEFAULT_CONFIG)
    protocol = json.loads(json.dumps(protocol))
    protocol["design"].update(
        {
            "menu_sizes": [4, 6],
            "responsive_counts": [0, 1, 2, 3],
            "overlap_arms": ["high", "low"],
            "router_rules": ["default", "price"],
            "replicates_per_cell": 2,
            "maximum_tasks_per_run": 48,
        }
    )
    return protocol, digest


def test_protocol_is_prospective_and_claims_start_false():
    protocol, digest = load_protocol(DEFAULT_CONFIG)
    assert len(digest) == 64
    assert protocol["study"]["prospective_start_utc"] == "2026-07-23T00:00:00Z"
    assert protocol["rank"]["primary_tau_margin"] == 0.05
    assert protocol["rank"]["minimum_model_cohorts"] == 4
    assert len(protocol["study"]["models"]) == 7
    assert "openai/gpt-oss-120b" in protocol["study"]["models"]
    assert "google/gemma-4-31b-it" in protocol["study"]["models"]
    assert "minimax/minimax-m2.7" in protocol["study"]["models"]
    assert protocol["rank"]["subset_sizes"][:2] == [2, 3]
    assert protocol["budget"]["maximum_campaign_usd"] == 500.0
    assert not any(protocol["claims"].values())


def test_role_classifier_uses_only_pre_cutoff_price_changes():
    start = datetime(2026, 7, 22, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(120):
        ts = start + timedelta(minutes=5 * index)
        run_ts = ts.strftime("%Y%m%dT%H%M%SZ")
        for provider in ("A", "B", "C", "Anchor", "Z.AI"):
            base = {"A": 1.0, "B": 1.2, "C": 1.4, "Anchor": 2.0, "Z.AI": 2.2}[provider]
            if provider in {"A", "B", "C"}:
                base *= 1.0 - 0.01 * (index // 30)
            rows.append(
                {
                    "run_ts": run_ts,
                    "model_id": "z-ai/glm-5.2",
                    "provider_name": provider,
                    "price_prompt": base / 104,
                    "price_completion": base / 104,
                    "price_request": 0.0,
                }
            )
    roles, correlations = classify_provider_roles(
        pd.DataFrame(rows),
        "z-ai/glm-5.2",
        cutoff=pd.Timestamp("2026-07-23T00:00:00Z"),
        minimum_price_changes=2,
        minimum_history_snapshots=96,
        minimum_provider_coverage=0.7,
        author_keys={"Z.AI"},
    )
    by_key = roles.set_index("provider_key")
    assert bool(by_key.loc["a", "responsive"])
    assert bool(by_key.loc["b", "responsive"])
    assert not bool(by_key.loc["anchor", "responsive"])
    assert by_key.loc["a", "price_change_count"] == 3
    assert correlations


def test_high_and_low_overlap_selection_are_ordered_and_deterministic():
    correlations = {
        ("a", "b"): 0.95,
        ("a", "c"): 0.20,
        ("a", "d"): 0.10,
        ("b", "c"): 0.15,
        ("b", "d"): 0.05,
        ("c", "d"): 0.80,
    }
    high, high_score = select_responsive_subset(
        ["a", "b", "c", "d"], 2, "high", correlations, seed=1
    )
    low, low_score = select_responsive_subset(
        ["a", "b", "c", "d"], 2, "low", correlations, seed=1
    )
    assert high == ["a", "b"]
    assert low == ["b", "d"]
    assert high_score == pytest.approx(0.95)
    assert low_score == pytest.approx(0.05)
    assert subset_overlap(high, correlations) > subset_overlap(low, correlations)


def test_factorial_assignments_are_exact_balanced_outcome_blind_and_replayable():
    protocol, digest = _protocol()
    model = "z-ai/glm-5.2"
    candidates = [_candidate(model, f"P{index}", 0.00001 * (index + 1)) for index in range(8)]
    roles = [
        {
            "model_id": model,
            "provider_key": f"p{index}",
            "responsive": index < 3,
        }
        for index in range(8)
    ]
    correlations = {
        model: {
            ("p0", "p1"): 0.9,
            ("p0", "p2"): 0.1,
            ("p1", "p2"): 0.2,
        }
    }
    epoch = market_epoch(
        candidates,
        study_id=protocol["study"]["study_id"],
        plan_version=protocol["study"]["plan_version"],
        run_id="run-1",
        model_id=model,
        responsive_keys={"p0", "p1", "p2"},
        protocol_sha256=digest,
    )
    first, summary = build_factorial_assignments(
        candidates,
        roles,
        [epoch],
        correlations,
        protocol=protocol,
        protocol_sha256=digest,
        run_id="run-1",
        seed=123,
    )
    second, _ = build_factorial_assignments(
        candidates,
        roles,
        [epoch],
        correlations,
        protocol=protocol,
        protocol_sha256=digest,
        run_id="run-1",
        seed=123,
    )
    assert first == second
    assert summary["planned_tasks"] == len(first) <= 48
    validate_factorial_assignments(first)
    assert all(len(row["selected_provider_keys"]) == row["target_n"] for row in first)
    assert all(len(row["responsive_provider_keys"]) == row["target_k"] for row in first)
    assert not any("outcome" in row or "selected_provider" in row for row in first)
    assert {row["router_rule"] for row in first} == {"default", "price"}


def test_assignment_validator_rejects_outcome_leak_and_wrong_k():
    base = {
        "task_id": "task",
        "target_n": 2,
        "target_k": 1,
        "provider_only_tags": ["a", "b"],
        "selected_provider_keys": ["a", "b"],
        "responsive_provider_keys": ["a"],
    }
    validate_factorial_assignments([base])
    with pytest.raises(ValueError, match="outcome field"):
        validate_factorial_assignments([base | {"outcome": "succeeded"}])
    with pytest.raises(ValueError, match="target_k"):
        validate_factorial_assignments([base | {"responsive_provider_keys": []}])


def test_bundle_hash_changes_on_assignment_mutation():
    bundle = {
        "candidates": [{"a": 1}],
        "assignments": [{"task_id": "a"}],
        "market_epochs": [],
        "provider_roles": [],
        "summary": {"source_healthy": True},
    }
    original = canonical_bundle_hash(bundle)
    bundle["assignments"][0]["task_id"] = "b"
    assert canonical_bundle_hash(bundle) != original


def test_capture_continuity_detects_complete_and_gapped_series():
    now = datetime(2026, 7, 23, 0, 0, tzinfo=UTC)
    rows = [
        {"run_ts": (now - timedelta(minutes=5 * offset)).strftime("%Y%m%dT%H%M%SZ")}
        for offset in range(12)
    ]
    complete = capture_continuity(pd.DataFrame(rows), now=now, lookback_hours=1)
    assert complete["coverage"] == 1.0
    assert complete["maximum_gap_minutes"] == 5.0
    gapped = capture_continuity(
        pd.DataFrame([rows[0], rows[-1]]), now=now, lookback_hours=1
    )
    assert gapped["maximum_gap_minutes"] == 55.0


def test_reconciliation_fails_closed_on_duplicates_or_missing_spend():
    assignments = pd.DataFrame(
        [{"study_id": "s", "task_id": "a"}, {"study_id": "s", "task_id": "b"}]
    )
    attempts = pd.DataFrame(
        [
            {"study_id": "s", "metadata_json": json.dumps({"task_id": "a"})},
            {"study_id": "s", "metadata_json": json.dumps({"task_id": "b"})},
        ]
    )
    spend = pd.DataFrame([{"study_id": "s", "task_id": "a"}])
    result = reconciliation(assignments, attempts, spend, study_id="s", require_paid=True)
    assert result["healthy"] is False
    assert result["attempted_without_spend"] == ["b"]
    repaired = reconciliation(
        assignments,
        attempts,
        pd.DataFrame(
            [{"study_id": "s", "task_id": "a"}, {"study_id": "s", "task_id": "b"}]
        ),
        study_id="s",
        require_paid=True,
    )
    assert repaired["healthy"] is True


def test_privacy_gate_rejects_payload_columns_and_retained_rows():
    assert privacy_gate({"safe": pd.DataFrame([{"payload_retained": False}])})["healthy"]
    unsafe = privacy_gate(
        {"bad": pd.DataFrame([{"payload_retained": True, "prompt": "secret"}])}
    )
    assert unsafe["healthy"] is False
    assert unsafe["failures"][0]["forbidden_columns"] == ["prompt"]


def test_assignment_only_confirmatory_support_is_strict_and_outcome_blind():
    protocol, _ = _protocol()
    protocol["design"]["menu_sizes"] = [4, 8]
    protocol["design"]["responsive_counts"] = [0, 2]
    protocol["support"].update(
        {
            "confirmatory_days": 4,
            "minimum_holdout_days": 2,
            "minimum_randomized_blocks_per_cell": 2,
            "minimum_choices_per_multiplicity": 4,
            "minimum_provider_pair_clusters": 1,
            "minimum_clean_shocks_per_size_bin": 2,
        }
    )
    protocol["rank"].update(
        {"minimum_market_size_bins": 2, "minimum_model_cohorts": 2}
    )
    start = datetime(2026, 7, 23, tzinfo=UTC)
    rows = []
    position = 0
    for n in (4, 8):
        for k in (0, 2):
            for block in range(2):
                providers = [f"p{index}" for index in range(n)]
                responsive = providers[:k]
                day = 0 if block == 0 else 3 + ((position // 2) % 2)
                rows.append(
                    {
                        "study_id": protocol["study"]["study_id"],
                        "task_id": f"task-{position}",
                        "run_id": f"github-{position}",
                        "block_id": f"block-{position}",
                        "model_id": "m1" if position % 2 else "m2",
                        "target_n": n,
                        "target_k": k,
                        "overlap_arm": "none" if k < 2 else "high",
                        "router_rule": "default",
                        "selected_provider_keys": providers,
                        "responsive_provider_keys": responsive,
                        "provider_only_tags": [f"tag-{value}" for value in providers],
                        "run_ts": (start + timedelta(days=day)).strftime(
                            "%Y%m%dT%H%M%SZ"
                        ),
                    }
                )
                position += 1
    run_ledger = pd.DataFrame(
        [
            {
                "study_id": protocol["study"]["study_id"],
                "run_id": row["run_id"],
                "created_at": datetime.strptime(
                    row["run_ts"], "%Y%m%dT%H%M%SZ"
                ).replace(tzinfo=UTC).isoformat(),
            }
            for row in rows
        ]
    )
    for row in rows:
        row["run_ts"] = row["run_id"]
    shocks = pd.DataFrame(
        [
            {
                "study_id": protocol["study"]["study_id"],
                "event_id": f"shock-{index}",
                "model_id": "m1",
                "event_ts": (start + timedelta(hours=index + 1)).isoformat(),
                "eligible_n": 8,
                "placebo": False,
                "contaminated": False,
            }
            for index in range(2)
        ]
    )
    result = assignment_support(
        pd.DataFrame(rows),
        shocks,
        protocol=protocol,
        now=start + timedelta(days=4, hours=1),
        run_ledger=run_ledger,
    )
    assert result["healthy"] is True, json.dumps(result, indent=2)
    assert result["gates"]["fixed_confirmatory_horizon"] is True
    assert "outcome" not in json.dumps(result)
    underpowered = assignment_support(
        pd.DataFrame(rows[:-1]),
        shocks,
        protocol=protocol,
        now=start + timedelta(days=4, hours=1),
        run_ledger=run_ledger,
    )
    assert underpowered["healthy"] is False
    assert underpowered["gates"]["randomized_blocks_per_cell"] is False


def test_public_shock_registry_requires_adjacent_captures_and_labels_coincidence():
    model = "z-ai/glm-5.2"
    start = datetime(2026, 7, 23, tzinfo=UTC)
    rows = []
    quotes = {
        0: {"A": 1.0, "B": 1.2, "Z.AI": 1.4},
        1: {"A": 1.0, "B": 1.2, "Z.AI": 1.4},
        2: {"A": 0.9, "B": 1.1, "Z.AI": 1.4, "C": 1.3},
        3: {"A": 0.8, "B": 1.1, "Z.AI": 1.4, "C": 1.3},
    }
    minutes = {0: 0, 1: 5, 2: 10, 3: 40}
    for index, menu in quotes.items():
        for provider, quote in menu.items():
            rows.append(
                {
                    "run_ts": (start + timedelta(minutes=minutes[index])).strftime(
                        "%Y%m%dT%H%M%SZ"
                    ),
                    "model_id": model,
                    "provider_name": provider,
                    "price_prompt": quote / 104,
                    "price_completion": quote / 104,
                    "price_request": 0.0,
                }
            )
    events = endpoint_shocks(
        pd.DataFrame(rows),
        models=[model],
        study_id="s",
        protocol_sha256="a" * 64,
        maximum_adjacency_minutes=15,
        author_aliases={"z.ai"},
    )
    types = [row["event_type"] for row in events]
    assert types.count("provider_price_change") == 2
    assert types.count("coincident_price_change") == 1
    assert types.count("provider_entry") == 1
    assert not any(
        row["provider_key"] == "a" and row["post_run_ts"].endswith("004000Z")
        for row in events
    )
    assert all(row["payload_retained"] is False for row in events)


def test_shock_isolation_marks_nearby_clocks_but_not_simultaneous_cluster_rows():
    base = {
        "model_id": "m",
        "event_type": "provider_price_change",
        "contaminated": False,
    }
    events = [
        base | {"event_id": "a", "event_ts": "2026-07-23T00:00:00+00:00"},
        base | {"event_id": "b", "event_ts": "2026-07-23T00:00:00+00:00"},
        base | {"event_id": "c", "event_ts": "2026-07-23T00:20:00+00:00"},
        base | {"event_id": "d", "event_ts": "2026-07-23T02:00:00+00:00"},
    ]
    marked = mark_event_contamination(events, isolation_window_minutes=30)
    by_id = {row["event_id"]: row["contaminated"] for row in marked}
    assert by_id == {"a": True, "b": True, "c": True, "d": False}


def test_quality_balancer_selects_least_measured_model_and_providers():
    candidates = [
        _candidate(model, f"P{provider}", 0.00001 * (provider + 1))
        for model in ("m1", "m2")
        for provider in range(4)
    ]
    history = pd.DataFrame(
        [
            {
                "model_id": "m1",
                "requested_provider": "P1",
                "task_id": f"m1-{index}",
            }
            for index in range(10)
        ]
        + [
            {
                "model_id": "m2",
                "requested_provider": "P0",
                "task_id": f"m2-{index}",
            }
            for index in range(2)
        ]
    )
    selected, model, providers = quality_capture._balanced_candidates(
        candidates, history, models=["m1", "m2"], seed=7
    )
    assert model == "m2"
    assert providers == ["p1", "p2", "p3"]
    assert len(selected) == 3


def test_quality_plan_has_eight_hashed_tasks_and_execution_fails_closed(
    monkeypatch, tmp_path
):
    protocol, _ = load_protocol(DEFAULT_CONFIG)
    candidates = [
        _candidate(model, f"P{provider}", 0.00001 * (provider + 1))
        for model in protocol["study"]["models"]
        for provider in range(4)
    ]

    def fake_freeze(_client, *, run_id, seed, models, shapes):
        assert set(models) == set(protocol["study"]["models"])
        return [dict(row) for row in candidates], []

    monkeypatch.setattr(quality_capture, "freeze_candidates", fake_freeze)
    monkeypatch.setattr(quality_capture, "_history", lambda _root: pd.DataFrame())
    bundle = quality_capture.build_plan_bundle(
        object(), data_root=tmp_path, run_id="quality-run", seed=11
    )
    quality_capture.validate_bundle(bundle, require_tasks=True)
    assert len(bundle["assignments"]) == 8
    assert len({row["task_id"] for row in bundle["assignments"]}) == 8
    assert all(row["experiment_axis"] == "quality" for row in bundle["assignments"])
    assert all(row["payload_retained"] is False for row in bundle["assignments"])
    monkeypatch.delenv("ORCAP_PAID_PRICE_STUDIES_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        quality_capture.execute_bundle(bundle, data_root=tmp_path)


def test_direct_tau_recovers_a_shrinking_optimal_share():
    rows = []
    optima = {4: 1, 9: 2, 16: 2, 25: 3}
    for n, optimum in optima.items():
        for k in range(0, 6):
            rows.append(
                {
                    "target_n": n,
                    "target_k": k,
                    "overlap_arm": "none" if k < 2 else "high",
                    "router_rule": "default",
                    "choices": 200,
                    "blocks": 100,
                    "success_rate": 1.0,
                    "mean_cost_usd": 0.0,
                    "mean_latency_ms": 10.0,
                    "fallback_rate": 0.0,
                    "exact_menu_coverage": 1.0,
                    "mean_operational_surplus": -float((k - optimum) ** 2),
                }
            )
    kstars = kstar_by_n(pd.DataFrame(rows))
    tau = estimate_tau(kstars)
    assert tau is not None and tau > 0
    assert kstars["k_star_share"].is_monotonic_decreasing


def test_beta_and_gamma_recover_registered_synthetic_laws():
    curve = pd.DataFrame(
        [
            {"model_id": model, "target_n": n, "effective_rank": n**0.5}
            for model in ("m1", "m2", "m3")
            for n in (4, 8, 16, 32)
        ]
    )
    assert estimate_beta(curve) == pytest.approx(0.5, abs=1e-10)
    misleading = pd.DataFrame(
        [
            {"model_id": "identifying", "target_n": n, "effective_rank": n**0.5}
            for n in (2, 4)
        ]
        + [
            {"model_id": f"one-point-{index}", "target_n": 2, "effective_rank": 1.5}
            for index in range(4)
        ]
    )
    assert identifying_rank_model_count(misleading) == 1
    rows = []
    for n in (4, 8, 16, 32):
        rank = n**0.5
        for k in (0, 1, 2, 3, 4):
            x = k / n
            y = 2.0 + 1.5 * x - 3.0 * x * x * (k / rank if rank else 0.0) ** 1.0
            rows.append(
                {
                    "target_n": n,
                    "target_k": k,
                    "overlap_arm": "none" if k < 2 else "high",
                    "router_rule": "default",
                    "choices": 100,
                    "mean_operational_surplus": y,
                }
            )
    fit = fit_congestion_gamma(pd.DataFrame(rows), curve)
    assert fit is not None
    assert fit["gamma"] == pytest.approx(1.0, abs=0.05)


def test_outcome_surface_uses_only_observed_attempts():
    panel = pd.DataFrame(
        [
            {
                "task_id": "a",
                "block_id": "b1",
                "target_n": 4,
                "target_k": 1,
                "overlap_arm": "none",
                "router_rule": "default",
                "attempt_observed": True,
                "outcome": "succeeded",
                "cost_usd": 0.01,
                "latency_ms": 100.0,
                "fallback_triggered": False,
                "exact_menu_covered": True,
                "operational_surplus": 0.98,
            },
            {
                "task_id": "c",
                "block_id": "b2",
                "target_n": 4,
                "target_k": 1,
                "overlap_arm": "none",
                "router_rule": "default",
                "attempt_observed": False,
                "outcome": None,
                "cost_usd": None,
                "latency_ms": None,
                "fallback_triggered": None,
                "exact_menu_covered": False,
                "operational_surplus": -1.0,
            },
        ]
    )
    surface = outcome_surface(panel)
    assert surface.iloc[0]["choices"] == 1
    assert surface.iloc[0]["mean_operational_surplus"] == pytest.approx(0.98)


def test_plan_bundle_integration_is_hashed_written_and_source_gated(monkeypatch, tmp_path):
    model = "z-ai/glm-5.2"
    start = datetime(2026, 7, 22, 13, 0, tzinfo=UTC)
    history = []
    for index in range(145):
        ts = start + timedelta(minutes=5 * index)
        for provider_index in range(8):
            provider = f"P{provider_index}"
            price = 1.0 + provider_index / 10
            if provider_index < 3:
                price *= 1.0 - 0.01 * (index // 30)
            history.append(
                {
                    "run_ts": ts.strftime("%Y%m%dT%H%M%SZ"),
                    "model_id": model,
                    "provider_name": provider,
                    "price_prompt": price / 104,
                    "price_completion": price / 104,
                    "price_request": 0.0,
                }
            )
    snapshots = pd.DataFrame(history)
    candidates = [_candidate(model, f"P{index}", 0.00001 * (index + 1)) for index in range(8)]

    def fake_read(_root, table):
        return snapshots.copy() if table == "endpoints_snapshots" else pd.DataFrame()

    def fake_freeze(_client, *, run_id, seed, models, shapes):
        assert run_id == "integration-run"
        assert seed == 42
        assert model in models
        return [dict(row) for row in candidates], [
            {"model_id": "z-ai/glm-5", "reason": "not_yet_available"}
        ]

    monkeypatch.setattr(capture, "_read", fake_read)
    monkeypatch.setattr(capture, "freeze_candidates", fake_freeze)
    bundle = capture.build_plan_bundle(
        object(),
        data_root=tmp_path,
        run_id="integration-run",
        seed=42,
        now=datetime(2026, 7, 23, 1, 0, tzinfo=UTC),
    )
    assert bundle["summary"]["source_healthy"] is True
    assert bundle["summary"]["source_failures"]
    assert bundle["assignments"]
    capture.validate_bundle(bundle)
    paths = capture.write_plan_bundle(
        bundle,
        bundle_path=tmp_path / "plan.json",
        curated_dir=tmp_path / "curated",
    )
    assert Path(paths["assignment_path"]).is_file()
    assert Path(paths["provider_role_path"]).is_file()
    tampered = json.loads(json.dumps(bundle))
    tampered["assignments"][0]["target_k"] += 1
    with pytest.raises(ValueError):
        capture.validate_bundle(tampered)
