import hashlib

import pandas as pd

from orcap.analysis.h54_reliability_audit import _attempt_audit as attempt_audit
from orcap.analysis.h54_reliability_audit import certificates, design_audit
from orcap.route_telemetry import validate_attempt
from orcap.study_registry import (
    validate_reliability_audit_assignment,
    validate_reliability_audit_manifest,
)


def _manifest():
    return validate_reliability_audit_manifest(
        {
            "audit_manifest_id": "reliability-audit-v1",
            "study_id": "reliability-audit",
            "registered_at": "2026-07-10T00:00:00Z",
            "planned_start_at": "2026-07-11T00:00:00Z",
            "planned_end_at": "2026-07-12T00:00:00Z",
            "randomization_unit": "provider_model_epoch",
            "randomization_seed_commitment": hashlib.sha256(b"audit-seed").hexdigest(),
            "routing_mode": "direct_provider",
            "outcome_definition": "completed_attempt_success",
            "confidence_level": 0.95,
            "minimum_attempts_per_provider_model": 100,
            "minimum_reliability_lower_bound": 0.95,
            "stopping_rule": "Stop only after the registered direct-attempt minimum.",
        }
    )


def _assignment():
    return validate_reliability_audit_assignment(
        {
            "audit_assignment_id": "reliability-audit-a001",
            "audit_manifest_id": "reliability-audit-v1",
            "study_id": "reliability-audit",
            "provider": "provider-a",
            "model_id": "model-a",
            "epoch_start": "2026-07-11T00:00:00Z",
            "epoch_end": "2026-07-11T01:00:00Z",
            "assigned_at": "2026-07-10T00:01:00Z",
            "randomization_stratum": "fixed-chat-us",
            "assignment_probability": 1.0,
        }
    )


def _attempt(number: int, *, selected_provider: str = "provider-a"):
    return validate_attempt(
        {
            "event_id": f"direct-{number:03d}",
            "observed_at": f"2026-07-11T00:{number // 60:02d}:{number % 60:02d}Z",
            "router": "owned-router",
            "source": "litellm",
            "study_id": "reliability-audit",
            "model_id": "model-a",
            "requested_provider": "provider-a",
            "selected_provider": selected_provider,
            "outcome": "succeeded",
            "reliability_audit_assignment_id": "reliability-audit-a001",
        }
    )


def test_h54_certifies_only_preassigned_completed_direct_provider_attempts():
    manifests = pd.DataFrame([_manifest()])
    assignments = pd.DataFrame([_assignment()])
    attempts = pd.DataFrame([_attempt(number) for number in range(100)])
    design = design_audit(manifests, assignments)
    panel, _ = attempt_audit(assignments, attempts, design)
    result = certificates(manifests, design, panel).iloc[0]

    assert design["design_valid"].all()
    assert result["completed_attempts"] == 100
    assert result["one_sided_lower_reliability_bound"] > 0.97
    assert result["certification_status"] == "reliability_certified"


def test_h54_fails_closed_when_a_linked_attempt_is_not_directly_served_by_target():
    manifests = pd.DataFrame([_manifest()])
    assignments = pd.DataFrame([_assignment()])
    attempts = pd.DataFrame(
        [_attempt(number) for number in range(99)] + [_attempt(99, selected_provider="b")]
    )
    design = design_audit(manifests, assignments)
    panel, detail = attempt_audit(assignments, attempts, design)
    result = certificates(manifests, design, panel).iloc[0]

    assert detail["attempt_design_errors"].str.contains("selected_provider_mismatch").any()
    assert result["attempt_design_mismatch_count"] == 1
    assert result["certification_status"] == "invalid_design"
