from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from orcap.analysis.h81_release_recovery import (
    recover_release_report,
    validate_recovery_inputs,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    policy = pd.DataFrame(
        [
            {
                "policy": "price_only_no_fallback",
                "first_position_attempts": 45,
                "success_outcomes_observed": 44,
                "success_outcomes_missing": 1,
                "success_mean_lower_bound": 42 / 45,
                "success_mean_upper_bound": 43 / 45,
                "success_design_simultaneous_ci_low": np.nan,
                "success_design_simultaneous_ci_high": np.nan,
                "treatment_metadata_passes": 44,
            },
            {
                "policy": "price_order_fallback",
                "first_position_attempts": 39,
                "success_outcomes_observed": 39,
                "success_outcomes_missing": 0,
                "success_mean_lower_bound": 1.0,
                "success_mean_upper_bound": 1.0,
                "success_design_simultaneous_ci_low": 0.79,
                "success_design_simultaneous_ci_high": 1.0,
                "treatment_metadata_passes": 39,
            },
            {
                "policy": "delegated_default",
                "first_position_attempts": 49,
                "success_outcomes_observed": 49,
                "success_outcomes_missing": 0,
                "success_mean_lower_bound": 1.0,
                "success_mean_upper_bound": 1.0,
                "success_design_simultaneous_ci_low": 0.82,
                "success_design_simultaneous_ci_high": 1.0,
                "treatment_metadata_passes": 49,
            },
        ]
    )
    contrast = pd.DataFrame(
        [
            {
                "estimand": "fallback_option",
                "primary": True,
                "positive_n": 39,
                "negative_n": 45,
                "success_difference_hajek": np.nan,
                "success_difference_design_simultaneous_ci_low": np.nan,
                "success_difference_design_simultaneous_ci_high": np.nan,
                "success_difference_treatment_outcome_lower_bound": 2 / 45,
                "success_difference_treatment_outcome_upper_bound": 3 / 45,
                "randomization_p_greater": np.nan,
                "holm_p_greater": np.nan,
            },
            {
                "estimand": "hidden_selection",
                "primary": True,
                "positive_n": 49,
                "negative_n": 39,
                "success_difference_hajek": 0.0,
                "success_difference_design_simultaneous_ci_low": -0.386,
                "success_difference_design_simultaneous_ci_high": 0.386,
                "success_difference_treatment_outcome_lower_bound": 0.0,
                "success_difference_treatment_outcome_upper_bound": 0.0,
                "randomization_p_greater": np.nan,
                "holm_p_greater": np.nan,
            },
            {
                "estimand": "total_delegation",
                "primary": False,
                "positive_n": 49,
                "negative_n": 45,
                "success_difference_hajek": np.nan,
                "success_difference_design_simultaneous_ci_low": np.nan,
                "success_difference_design_simultaneous_ci_high": np.nan,
                "success_difference_treatment_outcome_lower_bound": 2 / 45,
                "success_difference_treatment_outcome_upper_bound": 3 / 45,
                "randomization_p_greater": np.nan,
                "holm_p_greater": np.nan,
            },
        ]
    )
    return policy, contrast


def _metadata() -> tuple[dict, dict, dict]:
    summary = {
        "outcomes_released": True,
        "evidence_status": "randomized_decomposition_ready",
        "terminal_gate_block_excluded": True,
        "terminal_gate_block_policy": "price_order_fallback",
        "release_gate_prefix_blocks": 134,
        "confirmatory_prefix_blocks": 133,
    }
    manifest = {
        "protocol_version": "confirmatory-release-v1",
        "study": "h81",
        "first_access_marker_commit": "marker",
        "code_commit": "code",
        "dataset": {"revision": "dataset"},
        "files": [],
    }
    failure = {
        "status": "failed_closed_raw_release_preserved",
        "automatic_outcome_requery_permitted": False,
    }
    return summary, manifest, failure


def test_missingness_recovery_preserves_frozen_claim_boundary() -> None:
    policy, contrast = _frames()
    summary, manifest, failure = _metadata()
    validation = validate_recovery_inputs(policy, contrast, summary, manifest, failure)
    assert validation["binary_outcomes_missing"] == 1
    assert validation["formal_primary_decision_available"] is False
    assert validation["source_outcome_requery_permitted"] is False


def test_missingness_recovery_rejects_partial_holm_family() -> None:
    policy, contrast = _frames()
    summary, manifest, failure = _metadata()
    contrast.loc[contrast["estimand"] == "hidden_selection", "holm_p_greater"] = 1.0
    with pytest.raises(ValueError, match="partial Holm family"):
        validate_recovery_inputs(policy, contrast, summary, manifest, failure)


def test_recover_release_report_validates_hashes_and_renders(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    output = tmp_path / "output"
    bundle.mkdir()
    policy, contrast = _frames()
    summary, manifest, failure = _metadata()
    policy.to_parquet(bundle / "h81_policy_panel.parquet", index=False)
    contrast.to_parquet(bundle / "h81_contrasts.parquet", index=False)
    (bundle / "h81_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (bundle / "h81_release_report_error.json").write_text(
        json.dumps(failure), encoding="utf-8"
    )
    payloads = [
        "h81_policy_panel.parquet",
        "h81_contrasts.parquet",
        "h81_summary.json",
        "h81_release_report_error.json",
    ]
    manifest["files"] = [
        {"path": name, "sha256": _sha256(bundle / name)} for name in payloads
    ]
    (bundle / "release_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = recover_release_report(bundle, output)
    assert report["status"] == "missingness_aware_recovery_rendered"
    assert report["contrast_identified_sets"]["fallback_option"]["lower"] == pytest.approx(
        2 / 45
    )
    assert (output / "h81_release_recovery.pdf").is_file()
    assert (output / "h81_release_recovery.png").is_file()
    table = (output / "h81_release_recovery_table.tex").read_text()
    assert table.startswith("\\begin{tabular}")
    assert not table.startswith("\\\\begin{tabular}")
    assert "not released" in table
    assert "no formal primary rejection" in (
        output / "h81_release_recovery_paragraph.tex"
    ).read_text()
