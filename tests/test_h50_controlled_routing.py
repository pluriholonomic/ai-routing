import hashlib

import pandas as pd
import pytest

from orcap.analysis.h50_controlled_routing import (
    design_audit,
    epoch_outcomes,
    study_status,
    treatment_effects,
)
from orcap.study_registry import validate_assignment, validate_manifest


def _manifest():
    return validate_manifest(
        {
            "manifest_id": "routing-rct-v1",
            "study_id": "routing-rct",
            "registered_at": "2026-07-10T00:00:00Z",
            "planned_start_at": "2026-07-11T00:00:00Z",
            "planned_end_at": "2026-07-12T00:00:00Z",
            "randomization_unit": "model_epoch",
            "randomization_seed_commitment": hashlib.sha256(b"test-seed").hexdigest(),
            "baseline_arm": "inverse_square_price",
            "arms": [
                {
                    "name": "inverse_square_price",
                    "policy": "inverse_square_price",
                    "assignment_probability": 0.5,
                },
                {
                    "name": "capacity_certified",
                    "policy": "capacity_certified",
                    "assignment_probability": 0.5,
                },
            ],
            "primary_outcomes": [
                "attempt_success_rate",
                "mean_cost_usd",
                "capacity_shortfall_rate",
            ],
            "negative_control_outcome": "mean_latency_ms",
            "min_clusters_per_arm": 20,
            "min_attempts_per_arm": 100,
            "stopping_rule": "Stop after 20 model epochs and 100 attempts per arm.",
        }
    )


def _synthetic_inputs():
    assignments, attempts, outcomes = [], [], []
    start = pd.Timestamp("2026-07-11T00:00:00Z")
    for epoch in range(40):
        arm = "inverse_square_price" if epoch < 20 else "capacity_certified"
        epoch_start = start + pd.Timedelta(15 * epoch, unit="min")
        epoch_end = epoch_start + pd.Timedelta(15, unit="min")
        assignments.append(
            validate_assignment(
                {
                    "assignment_id": f"assignment-{epoch:03d}",
                    "manifest_id": "routing-rct-v1",
                    "study_id": "routing-rct",
                    "model_id": "model-a",
                    "epoch_start": epoch_start.isoformat().replace("+00:00", "Z"),
                    "epoch_end": epoch_end.isoformat().replace("+00:00", "Z"),
                    "assigned_at": (epoch_start - pd.Timedelta(1, unit="min"))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "treatment_arm": arm,
                    "randomization_stratum": "short-chat",
                    "assignment_probability": 0.5,
                }
            )
        )
        for request in range(5):
            succeeded = arm == "capacity_certified" or request < 4
            attempts.append(
                {
                    "event_id": f"event-{epoch:03d}-{request}",
                    "observed_at": (epoch_start + pd.Timedelta(request, unit="s")).isoformat(),
                    "study_id": "routing-rct",
                    "model_id": "model-a",
                    "policy": arm,
                    "outcome": "succeeded" if succeeded else "failed",
                    "cost_usd": 0.008 if arm == "capacity_certified" else 0.01,
                    "latency_ms": 100.0,
                    "fallback_triggered": False,
                }
            )
        outcomes.append(
            {
                "outcome_id": f"outcome-{epoch:03d}",
                "study_id": "routing-rct",
                "model_id": "model-a",
                "provider": "provider-a",
                "epoch_start": epoch_start.isoformat().replace("+00:00", "Z"),
                "epoch_end": epoch_end.isoformat().replace("+00:00", "Z"),
                "allocated_requests": 5,
                "served_requests": 5 if arm == "capacity_certified" else 4,
                "shortfall_requests": 0 if arm == "capacity_certified" else 1,
            }
        )
    return pd.DataFrame(assignments), pd.DataFrame(attempts), pd.DataFrame(outcomes)


def test_h50_recovers_registered_epoch_randomized_policy_contrasts():
    manifests = pd.DataFrame([_manifest()])
    assignments, attempts, outcomes = _synthetic_inputs()
    panel, audit = epoch_outcomes(manifests, assignments, attempts, outcomes)
    assert audit["design_valid"].all()
    assert len(panel) == 40
    assert panel["attempt_policy_mismatch_count"].sum() == 0

    effects = treatment_effects(manifests, panel).set_index("outcome")
    estimate = effects["estimate_treatment_minus_baseline"]
    assert estimate.loc["attempt_success_rate"] == pytest.approx(0.2)
    assert estimate.loc["mean_cost_usd"] == pytest.approx(-0.002)
    assert estimate.loc["capacity_shortfall_rate"] == pytest.approx(-0.2)
    status = study_status(manifests, audit, panel)[0]
    assert status["status"] == "randomized_estimate_ready"


def test_h50_rejects_unregistered_arm_and_overlapping_epoch_assignment():
    manifest = pd.DataFrame([_manifest()])
    assignments, _, _ = _synthetic_inputs()
    assignments.loc[0, "treatment_arm"] = "posthoc_policy"
    audit = design_audit(manifest, assignments)
    assert not audit["design_valid"].all()
    assert "unregistered_treatment_arm" in audit.iloc[0]["design_errors"]

    assignments, _, _ = _synthetic_inputs()
    assignments.loc[1, "epoch_start"] = assignments.loc[0, "epoch_start"]
    assignments.loc[1, "epoch_end"] = assignments.loc[0, "epoch_end"]
    assignments.loc[1, "assigned_at"] = assignments.loc[0, "assigned_at"]
    audit = design_audit(manifest, assignments)
    overlap = audit[audit["assignment_id"].isin(["assignment-000", "assignment-001"])]
    assert not overlap["design_valid"].any()
    assert overlap["design_errors"].str.contains("overlapping_assignment").all()


def test_h50_treats_attempt_policy_divergence_as_a_design_failure():
    manifests = pd.DataFrame([_manifest()])
    assignments, attempts, outcomes = _synthetic_inputs()
    attempts.loc[0, "policy"] = "posthoc_policy"
    panel, audit = epoch_outcomes(manifests, assignments, attempts, outcomes)
    assert panel["attempt_policy_mismatch_count"].sum() == 1
    assert study_status(manifests, audit, panel)[0]["status"] == "invalid_design"
