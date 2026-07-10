import hashlib

import pytest

from orcap.reliability import (
    exact_one_sided_binomial_lower_bound,
    meets_reliability_threshold,
)


def test_exact_one_sided_binomial_lower_bound_has_exact_boundary_cases():
    assert exact_one_sided_binomial_lower_bound(0, 100, confidence_level=0.95) == 0.0
    assert exact_one_sided_binomial_lower_bound(100, 100, confidence_level=0.95) == pytest.approx(
        0.05 ** 0.01
    )
    assert exact_one_sided_binomial_lower_bound(95, 100, confidence_level=0.95) < 0.95


def test_reliability_bound_rejects_invalid_counts_and_uses_a_fixed_floor():
    with pytest.raises(ValueError, match="between zero"):
        exact_one_sided_binomial_lower_bound(11, 10, confidence_level=0.95)
    with pytest.raises(ValueError, match="positive integer"):
        exact_one_sided_binomial_lower_bound(0, 0, confidence_level=0.95)
    assert meets_reliability_threshold(0.97, minimum_reliability=0.95)
    assert not meets_reliability_threshold(0.94, minimum_reliability=0.95)


def test_reliability_manifest_rejects_non_direct_or_post_registered_designs():
    from orcap.study_registry import validate_reliability_audit_manifest

    manifest = {
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
        "stopping_rule": "Stop only after 100 completed direct attempts per provider/model.",
    }
    assert validate_reliability_audit_manifest(manifest)["routing_mode"] == "direct_provider"
    with pytest.raises(ValueError, match="direct_provider"):
        validate_reliability_audit_manifest(manifest | {"routing_mode": "router_selected"})
    with pytest.raises(ValueError, match="registered_at"):
        validate_reliability_audit_manifest(
            manifest | {"registered_at": "2026-07-11T00:01:00Z"}
        )


def test_reliability_audit_registry_is_payload_free_and_immutable(tmp_path):
    from orcap.study_registry import (
        validate_reliability_audit_assignment,
        validate_reliability_audit_manifest,
        write_reliability_audit_assignments,
        write_reliability_audit_manifest,
    )

    manifest = {
        "audit_manifest_id": "reliability-audit-v2",
        "study_id": "reliability-audit-v2",
        "registered_at": "2026-07-10T00:00:00Z",
        "planned_start_at": "2026-07-11T00:00:00Z",
        "planned_end_at": "2026-07-12T00:00:00Z",
        "randomization_unit": "provider_model_epoch",
        "randomization_seed_commitment": hashlib.sha256(b"audit-seed-v2").hexdigest(),
        "routing_mode": "direct_provider",
        "outcome_definition": "completed_attempt_success",
        "confidence_level": 0.95,
        "minimum_attempts_per_provider_model": 100,
        "minimum_reliability_lower_bound": 0.95,
        "stopping_rule": "Stop only after 100 completed direct attempts per provider/model.",
    }
    assignment = {
        "audit_assignment_id": "reliability-audit-v2-a001",
        "audit_manifest_id": "reliability-audit-v2",
        "study_id": "reliability-audit-v2",
        "provider": "provider-a",
        "model_id": "model-a",
        "epoch_start": "2026-07-11T00:00:00Z",
        "epoch_end": "2026-07-11T00:15:00Z",
        "assigned_at": "2026-07-10T00:01:00Z",
        "randomization_stratum": "fixed-chat",
        "assignment_probability": 1.0,
    }
    assert validate_reliability_audit_manifest(manifest)["payload_retained"] is False
    assert validate_reliability_audit_assignment(assignment)["payload_retained"] is False
    write_reliability_audit_manifest(manifest, curated_dir=tmp_path)
    write_reliability_audit_assignments([assignment], curated_dir=tmp_path)
    with pytest.raises(ValueError, match="immutable"):
        write_reliability_audit_manifest(manifest, curated_dir=tmp_path)
    with pytest.raises(ValueError, match="immutable"):
        write_reliability_audit_assignments([assignment], curated_dir=tmp_path)
