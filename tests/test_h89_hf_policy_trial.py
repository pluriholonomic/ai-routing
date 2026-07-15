import json
import random

import pandas as pd

from orcap.analysis.h89_hf_policy_trial import analyze
from orcap.capture_hf_policy_probes import POLICIES, STUDY_ID


def _seed_for(policy: str, start: int) -> int:
    seed = start
    while random.Random(seed).choice(POLICIES) != policy:
        seed += 1
    return seed


def _candidate(index: int, policy: str, ts: pd.Timestamp):
    seed = _seed_for(policy, 1000 + index * 10)
    assigned = {
        "hf_fastest": "fast",
        "hf_cheapest": "cheap",
        "public_cost_caliper": "frontier",
    }[policy]
    suffix = assigned if policy == "public_cost_caliper" else policy.removeprefix("hf_")
    return {
        "study_id": STUDY_ID,
        "run_ts": ts.strftime("%Y%m%dT%H%M%SZ"),
        "dt": ts.strftime("%Y-%m-%d"),
        "block_id": f"block-{index}",
        "model_id": f"model-{index % 2}",
        "request_observed_at": ts.isoformat(),
        "block_seed": str(seed),
        "assignment_probability": 1 / 3,
        "eligible_model": True,
        "request_sent": True,
        "assignment": policy,
        "assigned_requested_model": f"model-{index % 2}:{suffix}",
        "assigned_requested_provider": assigned if policy == "public_cost_caliper" else None,
        "public_assigned_provider": assigned,
        "public_assigned_quote_cap_usd": 1e-6,
        "public_cheapest_provider": "cheap",
        "public_fastest_provider": "fast",
        "public_cost_caliper_provider": "frontier",
        "candidate_state_hash": f"hash-{index}",
        "exclusion_reason": None,
    }


def _attempt(index: int, policy: str, ts: pd.Timestamp, success: bool):
    assigned = {
        "hf_fastest": "fast",
        "hf_cheapest": "cheap",
        "public_cost_caliper": "frontier",
    }[policy]
    suffix = assigned if policy == "public_cost_caliper" else policy.removeprefix("hf_")
    return {
        "event_id": f"event-{index}",
        "observed_at": ts.isoformat(),
        "router": "huggingface_inference_providers",
        "source": "huggingface_inference_providers",
        "study_id": STUDY_ID,
        "request_ref": f"event-{index}",
        "model_id": f"model-{index % 2}",
        "requested_provider": assigned if policy == "public_cost_caliper" else None,
        "selected_provider": assigned if success else None,
        "attempt_index": 0,
        "outcome": "succeeded" if success else "failed",
        "retry_reason": None if success else "http_503",
        "fallback_triggered": False,
        "policy": policy,
        "cost_usd": 1e-6 if success else None,
        "latency_ms": 50 if policy == "hf_fastest" and success else 200,
        "metadata_json": json.dumps(
            {
                "block_id": f"block-{index}",
                "candidate_state_hash": f"hash-{index}",
                "requested_model_suffix": suffix,
                "status_code": 200 if success else 503,
            }
        ),
    }


def _panel():
    start = pd.Timestamp("2026-07-16T00:00:00Z")
    policies = [
        "hf_fastest",
        "hf_cheapest",
        "public_cost_caliper",
        "hf_fastest",
        "hf_cheapest",
        "public_cost_caliper",
    ]
    candidates, attempts = [], []
    for index, policy in enumerate(policies):
        ts = start + pd.Timedelta(hours=index)
        candidates.append(_candidate(index, policy, ts))
        attempts.append(_attempt(index, policy, ts, success=policy != "hf_cheapest"))
    return pd.DataFrame(candidates), pd.DataFrame(attempts)


def test_h89_masks_outcomes_before_fixed_gate(tmp_path):
    candidates, attempts = _panel()
    summary = analyze(candidates, attempts, tmp_path)
    assert summary["outcomes_released"] is False
    assert "released_results" not in summary
    support = pd.read_parquet(tmp_path / "h89_assignment_support.parquet")
    assert "outcome" not in support.columns
    assert "success" not in support.columns
    assert (tmp_path / "h89_hf_policy_support.pdf").exists()
    assert not (tmp_path / "h89_released_trial_rows.parquet").exists()


def test_h89_releases_earliest_qualifying_prefix(tmp_path):
    candidates, attempts = _panel()
    requirements = {
        "elapsed_hours": 4,
        "assignments_per_arm": 1,
        "models": 1,
        "candidate_providers": 2,
        "max_public_provider_dominance": 1.0,
        "min_treatment_compliance": 0.9,
        "require_seed_replay": True,
    }
    summary = analyze(
        candidates,
        attempts,
        tmp_path,
        requirements=requirements,
        bootstrap_draws=200,
        randomization_draws=500,
    )
    assert summary["outcomes_released"] is True
    assert len(summary["released_results"]["primary_contrasts"]) == 4
    assert (tmp_path / "h89_released_trial_rows.parquet").exists()
    assert (tmp_path / "h89_primary_contrasts.parquet").exists()
    assert (tmp_path / "h89_hf_policy_trial.pdf").exists()
