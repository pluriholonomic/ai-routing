import json
import random

import pandas as pd
import pytest

from orcap.analysis.h87_capacity_policy_trial import analyze, prepare_candidates
from orcap.capture_capacity_policy_probes import POLICIES, STUDY_ID


def _seed_for(policy: str, start: int) -> int:
    seed = start
    while random.Random(seed).choice(POLICIES) != policy:
        seed += 1
    return seed


def _candidate(index: int, policy: str, ts: pd.Timestamp):
    seed = _seed_for(policy, 1000 + index * 10)
    safe = f"safe-{index}"
    risky = f"risky-{index}"
    requested = safe if policy == "capacity_safe" else risky if policy == "capacity_risky" else None
    return {
        "study_id": STUDY_ID,
        "run_ts": ts.strftime("%Y%m%dT%H%M%SZ"),
        "dt": ts.strftime("%Y-%m-%d"),
        "block_id": f"block-{index}",
        "model_id": f"model-{index % 2}",
        "canonical_slug": f"model-{index % 2}-canonical",
        "request_observed_at": ts.isoformat(),
        "block_seed": str(seed),
        "assignment_probability": 1 / 3,
        "eligible_pair": True,
        "request_sent": True,
        "assignment": policy,
        "assigned_requested_provider": requested,
        "safe_provider": safe,
        "risky_provider": risky,
        "candidate_state_hash": f"hash-{index}",
        "capacity_risk_gap": 1.0,
        "price_ratio": 1.1,
        "exclusion_reason": None,
    }


def _attempt(index: int, policy: str, ts: pd.Timestamp, success: bool):
    requested = (
        f"safe-{index}"
        if policy == "capacity_safe"
        else f"risky-{index}"
        if policy == "capacity_risky"
        else None
    )
    return {
        "event_id": f"event-{index}",
        "observed_at": ts.isoformat(),
        "router": "openrouter",
        "source": "openrouter_generation",
        "study_id": STUDY_ID,
        "request_ref": f"event-{index}",
        "model_id": f"model-{index % 2}",
        "requested_provider": requested,
        "selected_provider": (
            requested if success and requested else "default-provider" if success else None
        ),
        "attempt_index": 0,
        "outcome": "succeeded" if success else "failed",
        "retry_reason": None if success else "http_429",
        "fallback_triggered": False,
        "policy": policy,
        "cost_usd": 0.000001 if success else None,
        "latency_ms": 100 if success else None,
        "metadata_json": json.dumps(
            {"block_id": f"block-{index}", "candidate_state_hash": f"hash-{index}"}
        ),
    }


def _panel():
    start = pd.Timestamp("2026-07-16T00:00:00Z")
    policies = [
        "capacity_safe",
        "capacity_risky",
        "openrouter_default",
        "capacity_safe",
        "capacity_risky",
        "openrouter_default",
    ]
    candidates = []
    attempts = []
    for index, policy in enumerate(policies):
        ts = start + pd.Timedelta(f"{index} hours")
        candidates.append(_candidate(index, policy, ts))
        attempts.append(_attempt(index, policy, ts, success=policy != "capacity_risky"))
    return pd.DataFrame(candidates), pd.DataFrame(attempts)


def test_h87_masks_all_outcomes_before_sample_gate(tmp_path):
    candidates, attempts = _panel()
    summary = analyze(candidates.iloc[:1], attempts.iloc[:1], attempts.iloc[:1], tmp_path)
    assert summary["outcomes_released"] is False
    assert "released_results" not in summary
    assert (tmp_path / "h87_assignment_support.parquet").exists()
    assert not (tmp_path / "h87_released_trial_rows.parquet").exists()
    assert not (tmp_path / "h87_capacity_policy_trial.pdf").exists()
    support = pd.read_parquet(tmp_path / "h87_assignment_support.parquet")
    assert "outcome" not in support.columns
    assert "success" not in support.columns


def test_h87_prepare_candidates_tolerates_unassigned_support_rows():
    row = _candidate(0, "capacity_safe", pd.Timestamp("2026-07-16T00:00:00Z"))
    row.update(
        {
            "assignment": pd.NA,
            "assigned_requested_provider": pd.NA,
            "safe_provider": pd.NA,
            "risky_provider": pd.NA,
            "eligible_pair": False,
            "request_sent": False,
            "exclusion_reason": "fewer_than_two_capacity_complete_providers",
        }
    )
    prepared = prepare_candidates(pd.DataFrame([row]))
    assert prepared.loc[0, "seed_replay_pass"] is False or not prepared.loc[0, "seed_replay_pass"]
    assert pd.isna(prepared.loc[0, "expected_requested_provider"])
    summary = analyze(pd.DataFrame([row]), pd.DataFrame(), pd.DataFrame())
    assert summary["outcomes_released"] is False
    assert summary["support"]["candidate_rows"] == 1
    assert summary["support"]["valid_assignments"] == 0


def test_h87_releases_earliest_supported_randomized_effect(tmp_path):
    candidates, attempts = _panel()
    requirements = {
        "complete_days": 0,
        "assignments_per_arm": 2,
        "models": 1,
        "candidate_providers": 2,
        "max_requested_provider_dominance": 1.0,
        "min_pinned_treatment_compliance": 0.9,
        "require_seed_replay": True,
        "require_no_cross_study_overlap": True,
    }
    summary = analyze(
        candidates,
        attempts,
        attempts,
        tmp_path,
        requirements=requirements,
        bootstrap_draws=500,
        randomization_draws=1000,
    )
    assert summary["outcomes_released"] is True
    contrasts = {row["comparison"]: row for row in summary["released_results"]["primary_contrasts"]}
    assert contrasts["capacity_safe_minus_capacity_risky"]["mean"] == pytest.approx(1.0)
    assert contrasts["openrouter_default_minus_capacity_safe"]["mean"] == pytest.approx(0.0)
    assert (tmp_path / "h87_released_trial_rows.parquet").exists()
    assert (tmp_path / "h87_primary_contrasts.parquet").exists()
    assert (tmp_path / "h87_capacity_policy_trial.pdf").exists()
