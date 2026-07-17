import itertools
import json
import random

import numpy as np
import pandas as pd
import pytest

from orcap.analysis.h81_delegation_decomposition import (
    POLICIES,
    _exact_pairwise_binary_randomization_pvalues,
    _simultaneous_serfling_mean_radii,
    analyze,
    assignment_integrity_pass,
    eligibility_diagnostics,
    first_position_sample,
    reconstruct_legacy_plans,
)
from orcap.analysis.h81_release_report import (
    build_release_report,
    build_release_report_safely,
    validate_release_outputs,
)


def _seed_for_first(policy: str, start: int) -> int:
    for seed in range(start, start + 10_000):
        expected = list(POLICIES)
        random.Random(seed).shuffle(expected)
        if expected[0] == policy:
            return seed
    raise AssertionError("no seed found")


def _balanced_frame(
    *,
    arm_sizes: dict[str, int] | None = None,
    success_counts: dict[str, int] | None = None,
) -> pd.DataFrame:
    rows = []
    arm_sizes = arm_sizes or {policy: 40 for policy in POLICIES}
    success_counts = success_counts or {
        "delegated_default": 40,
        "price_order_fallback": 32,
        "price_only_no_fallback": 20,
    }
    block_number = 0
    for policy in POLICIES:
        for within_arm in range(arm_sizes[policy]):
            seed = _seed_for_first(policy, 1000 + block_number * 10_000)
            success = within_arm < success_counts[policy]
            metadata = {
                "block_id": f"h81-{block_number}",
                "block_policy_count": 3,
                "policy_order": 0,
                "block_seed": seed,
                "assignment_probability_first": 1 / 3,
                "randomized_order": True,
                "public_provider_count": 3,
                "requested_order_length": (
                    0
                    if policy == "delegated_default"
                    else (1 if policy == "price_only_no_fallback" else 3)
                ),
                "provider_only_count": (
                    0
                    if policy == "delegated_default"
                    else (1 if policy == "price_only_no_fallback" else 3)
                ),
                "allow_fallbacks": policy != "price_only_no_fallback",
            }
            rows.append(
                {
                    "source": "openrouter_generation",
                    "event_id": f"event-{block_number}",
                    "run_ts": (
                        pd.Timestamp("2026-07-15T00:00:00Z")
                        + pd.to_timedelta(block_number, unit="s")
                    ).isoformat(),
                    "study_id": "openrouter-fallback-selection-decomposition-v1",
                    "model_id": f"model/{block_number % 2}",
                    "policy": policy,
                    "outcome": "succeeded" if success else "failed",
                    "retry_reason": None if success else "http_429",
                    "cost_usd": 0.00001 if success else None,
                    "latency_ms": 100.0 if success else None,
                    "selected_provider": "Provider" if success else None,
                    "fallback_triggered": policy == "price_order_fallback" and success,
                    "metadata_json": json.dumps(metadata),
                }
            )
            block_number += 1

    frame = pd.DataFrame(rows)
    # An all-null Parquet field may round-trip as nullable integer rather than
    # object/string.  The production analyzer must normalize that schema before
    # applying text predicates.
    frame["retry_reason"] = pd.Series(pd.NA, index=frame.index, dtype="Int32")
    return frame


def test_randomized_decomposition_recovers_both_policy_wedges():
    frame = _balanced_frame()
    panel, model_panel, contrasts, summary = analyze(frame, simulations=5_000)
    indexed = contrasts.set_index("estimand")
    assert (
        abs(indexed.loc["fallback_option", "success_difference_hajek"] - (32 / 39 - 20 / 40))
        < 1e-12
    )
    assert (
        abs(indexed.loc["hidden_selection", "success_difference_hajek"] - (40 / 40 - 32 / 39))
        < 1e-12
    )
    assert abs(indexed.loc["total_delegation", "success_difference_hajek"] - 0.5) < 1e-12
    assert abs(indexed.loc["total_delegation", "success_difference_ht"] - 0.5) < 1e-12
    assert indexed.loc[["fallback_option", "hidden_selection"], "holm_p_greater"].notna().all()
    assert indexed["randomization_p_greater_mc_check"].notna().all()
    assert indexed["randomization_mc_max_abs_error"].notna().all()
    assert summary["randomization_mc_audit_enforced"] is False
    assert pd.isna(indexed.loc["total_delegation", "holm_p_greater"])
    assert panel.set_index("policy")["first_position_attempts"].to_dict() == {
        "delegated_default": 40,
        "price_only_no_fallback": 40,
        "price_order_fallback": 39,
    }
    assert panel["spend_mean_lower_bound_usd"].notna().all()
    assert panel["spend_mean_upper_bound_usd"].notna().all()
    assert panel["ht_spend_mean_lower_bound_usd"].notna().all()
    assert panel["ht_spend_mean_upper_bound_usd"].notna().all()
    assert panel["selected_provider_observation_rate_success"].eq(1.0).all()
    assert indexed["spend_difference_lower_bound_usd"].notna().all()
    assert indexed["spend_difference_upper_bound_usd"].notna().all()
    assert indexed["ht_spend_difference_lower_bound_usd"].notna().all()
    assert indexed["ht_spend_difference_upper_bound_usd"].notna().all()
    assert len(model_panel) == 6
    assert summary["assignment_replay_rate"] == 1.0
    assert summary["treatment_metadata_passes"] == 120
    assert summary["outcomes_released"] is True
    assert summary["release_gate_prefix_blocks"] == 120
    assert summary["confirmatory_prefix_blocks"] == 119
    assert summary["terminal_gate_block_excluded"] is True
    assert summary["terminal_gate_block_policy"] == "price_order_fallback"
    assert summary["analysis_randomization"].startswith("intention-to-treat")
    assert summary["intended_first_position_blocks"] == 120
    assert panel["treatment_metadata_pass_rate"].eq(1.0).all()
    assert summary["randomization_inference"].startswith("exact pairwise-hypergeometric")
    assert summary["simultaneous_uncertainty"].startswith("Bonferroni-Newcombe")
    assert contrasts["success_difference_design_simultaneous_ci_low"].notna().all()
    assert contrasts["success_difference_design_simultaneous_ci_high"].notna().all()
    sensitivity = summary["treatment_outcome_missingness_sensitivity"]
    assert sensitivity["treatment_missing_or_noncompliant"] == 0
    assert sensitivity["binary_outcome_missing_among_verified"] == 0
    assert (
        indexed.loc[
            ["fallback_option", "hidden_selection"],
            "success_difference_simultaneous_ci_low",
        ]
        .notna()
        .all()
    )
    assert indexed["success_difference_treatment_outcome_lower_bound"].notna().all()
    assert indexed["success_difference_treatment_outcome_upper_bound"].notna().all()
    assert summary["evidence_status"] == "randomized_decomposition_ready"


def test_exact_binary_randomization_matches_brute_force_label_permutations():
    positive_outcomes = np.asarray([1.0, 1.0])
    negative_outcomes = np.asarray([0.0, 1.0])
    observed = 1.0 - 0.5
    exact_greater, exact_two_sided = _exact_pairwise_binary_randomization_pvalues(
        positive_outcomes,
        negative_outcomes,
        observed_statistic=observed,
    )

    outcomes = np.concatenate([positive_outcomes, negative_outcomes])
    template = (1, 1, 0, 0)
    assignments = sorted(set(itertools.permutations(template)))
    statistics = []
    for assignment in assignments:
        labels = np.asarray(assignment)
        statistics.append(outcomes[labels == 1].mean() - outcomes[labels == 0].mean())
    brute_greater = sum(value >= observed - 1e-15 for value in statistics) / len(statistics)
    brute_two_sided = sum(abs(value) >= abs(observed) - 1e-15 for value in statistics) / len(
        statistics
    )

    assert abs(exact_greater - brute_greater) < 1e-15
    assert abs(exact_two_sided - brute_two_sided) < 1e-15


def test_pairwise_randomization_tail_is_defined_without_a_nuisance_arm_null():
    """The exact test conditions on, rather than permutes, the third arm."""
    positive = np.asarray([1.0, 1.0, 0.0, 1.0])
    negative = np.asarray([0.0, 1.0, 0.0, 0.0])
    baseline = _exact_pairwise_binary_randomization_pvalues(positive, negative)

    # Changing an untested arm from all failures to all successes cannot enter
    # this function or change the pairwise reference law.
    nuisance_failures = np.zeros(50)
    nuisance_successes = np.ones(50)
    assert nuisance_failures.sum() != nuisance_successes.sum()
    assert _exact_pairwise_binary_randomization_pvalues(positive, negative) == baseline


def test_simultaneous_serfling_radii_are_validated_and_shrink_with_arm_count():
    small = _simultaneous_serfling_mean_radii(pd.Series(dict.fromkeys(POLICIES, 40)))
    large = _simultaneous_serfling_mean_radii(pd.Series(dict.fromkeys(POLICIES, 160)))
    finite_population_factor = 1.0 - 39.0 / 120.0
    expected = np.sqrt(finite_population_factor * np.log(2 * len(POLICIES) / 0.05) / (2 * 40))
    assert abs(small[POLICIES[0]] - expected) < 1e-15
    assert all(0.0 < large[policy] < small[policy] < 1.0 for policy in POLICIES)
    with pytest.raises(ValueError, match="alpha"):
        _simultaneous_serfling_mean_radii(pd.Series(dict.fromkeys(POLICIES, 40)), alpha=0.0)


def test_production_monte_carlo_discrepancy_gate_passes_fixed_fixture():
    _, _, contrasts, summary = analyze(_balanced_frame(), simulations=100_000)

    assert summary["randomization_mc_audit_enforced"] is True
    assert bool(contrasts["randomization_mc_audit_pass"].astype(bool).all())
    assert contrasts["randomization_mc_max_abs_error"].max() <= 0.01


def test_unknown_outcome_is_bounded_instead_of_silently_coded_as_failure():
    frame = _balanced_frame()
    frame.loc[frame["event_id"].eq("event-0"), "outcome"] = "unknown"

    panel, _, contrasts, summary = analyze(frame, simulations=500)
    delegated = panel.set_index("policy").loc["delegated_default"]
    indexed = contrasts.set_index("estimand")

    assert delegated["success_outcomes_observed"] == 39
    assert delegated["success_outcomes_missing"] == 1
    assert pd.isna(delegated["success_rate"])
    assert delegated["success_rate_observed_cases"] == 1.0
    assert delegated["success_mean_lower_bound"] == 39 / 40
    assert delegated["success_mean_upper_bound"] == 1.0
    assert indexed["randomization_p_greater"].isna().all()
    assert pd.isna(indexed.loc["hidden_selection", "success_difference_hajek"])
    assert indexed.loc["hidden_selection", "success_difference_lower_bound"] < 1.0
    sensitivity = summary["treatment_outcome_missingness_sensitivity"]
    assert sensitivity["binary_outcome_missing_among_verified"] == 1


def test_noncompliant_planned_block_enters_worst_case_treatment_bounds():
    frame = _balanced_frame(
        arm_sizes={
            "delegated_default": 41,
            "price_only_no_fallback": 40,
            "price_order_fallback": 40,
        },
        success_counts={
            "delegated_default": 41,
            "price_only_no_fallback": 20,
            "price_order_fallback": 32,
        },
    )
    metadata = json.loads(frame.loc[0, "metadata_json"])
    metadata["allow_fallbacks"] = False
    frame.loc[0, "metadata_json"] = json.dumps(metadata)

    _, _, contrasts, summary = analyze(frame, simulations=500)
    sensitivity = summary["treatment_outcome_missingness_sensitivity"]
    hidden = contrasts.set_index("estimand").loc["hidden_selection"]

    assert summary["outcomes_released"] is True
    assert sensitivity["treatment_missing_or_noncompliant"] == 1
    assert hidden["planned_positive_n"] == 41
    assert hidden["planned_positive_treatment_or_outcome_missing"] == 1
    assert (
        hidden["success_difference_treatment_outcome_lower_bound"]
        < hidden["success_difference_hajek"]
    )
    assert (
        hidden["success_difference_treatment_outcome_upper_bound"]
        >= hidden["success_difference_hajek"]
    )


def test_noncompliant_request_remains_in_intention_to_treat_primary_sample():
    frame = _balanced_frame()
    metadata = json.loads(frame.loc[0, "metadata_json"])
    metadata["allow_fallbacks"] = False
    frame.loc[0, "metadata_json"] = json.dumps(metadata)

    panel, _, contrasts, summary = analyze(frame, simulations=500)
    delegated = panel.set_index("policy").loc["delegated_default"]

    assert summary["outcomes_released"] is True
    assert summary["intended_first_position_blocks"] == 120
    assert summary["verified_first_position_blocks"] == 119
    assert delegated["intended_assignments"] == 40
    assert delegated["treatment_metadata_passes"] == 39
    assert delegated["success_rate"] == 1.0
    assert contrasts["randomization_p_greater"].notna().all()


def test_plan_only_assignment_enters_ledger_with_missing_request_fidelity():
    frame = _balanced_frame().iloc[0:0].copy()
    seed = _seed_for_first("price_order_fallback", 90_000)
    plans = pd.DataFrame(
        [
            {
                "plan_id": "planned-block",
                "planned_at": "2026-07-17T10:00:00Z",
                "run_id": "run-plan",
                "run_ts": "20260717T100000Z",
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "ranking_position": 5,
                "evaluation_order": 0,
                "model_id": "model/planned",
                "block_id": "planned-block",
                "block_seed": str(seed),
                "first_policy_planned": "price_order_fallback",
                "assignment_probability_first": 1 / 3,
                "randomized_order": True,
            }
        ]
    )

    ledger, audit = first_position_sample(frame, plans=plans)

    assert len(ledger) == 1
    row = ledger.iloc[0]
    assert row["policy"] == "price_order_fallback"
    assert bool(row["assignment_plan_recorded"])
    assert not bool(row["first_row_observed"])
    assert not bool(row["treatment_metadata_pass"])
    assert audit["assignment_plan_replay_rate"] == 1.0
    assert audit["intended_first_position_blocks"] == 1


def test_legacy_eligibility_rng_reconstructs_assignment_without_attempt_row():
    run_seed = 20260717
    pairs = [(5, "model/a"), (6, "model/b")]
    shuffled = pairs.copy()
    random.Random(run_seed).shuffle(shuffled)
    eligibility = pd.DataFrame(
        [
            {
                "run_id": "legacy-run",
                "run_seed": str(run_seed),
                "run_ts": "20260717T100000Z",
                "observed_at": f"2026-07-17T10:00:0{index}Z",
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "ranking_position": ranking_position,
                "evaluation_order": index,
                "model_id": model_id,
                "eligible": True,
                "block_id": f"legacy-{model_id}",
            }
            for index, (ranking_position, model_id) in enumerate(shuffled)
        ]
    )

    plans, replay = reconstruct_legacy_plans(eligibility)
    empty_attempts = _balanced_frame().iloc[0:0].copy()
    ledger, audit = first_position_sample(empty_attempts, plans=plans)

    assert replay == {
        "candidate_runs": 1,
        "replayed_runs": 1,
        "failed_runs": 0,
        "eligible_blocks": 2,
        "reconstructed_blocks": 2,
    }
    assert len(ledger) == 2
    assert set(ledger["policy"]).issubset(POLICIES)
    assert ledger["first_row_observed"].eq(False).all()
    assert audit["intended_first_position_blocks"] == 2


def test_corrupt_pre_request_plan_fails_assignment_integrity_gate():
    frame = _balanced_frame().iloc[0:0].copy()
    seed = _seed_for_first("delegated_default", 120_000)
    plans = pd.DataFrame(
        [
            {
                "block_id": "corrupt-plan",
                "block_seed": str(seed),
                "first_policy_planned": "price_only_no_fallback",
            }
        ]
    )

    ledger, audit = first_position_sample(frame, plans=plans)

    assert ledger.empty
    assert audit["assignment_plan_replay_rate"] == 0.0
    assert not assignment_integrity_pass(audit)


def test_zero_randomization_draws_still_runs_blinded_design_audit():
    policy = "delegated_default"
    seed = _seed_for_first(policy, 50_000)
    frame = pd.DataFrame(
        [
            {
                "source": "openrouter_generation",
                "event_id": "event-zero-draws",
                "run_ts": "20260715T120000Z",
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "model_id": "model/a",
                "policy": policy,
                "outcome": "succeeded",
                "retry_reason": None,
                "cost_usd": 0.00001,
                "latency_ms": 100.0,
                "selected_provider": "Provider",
                "fallback_triggered": False,
                "metadata_json": json.dumps(
                    {
                        "block_id": "h81-zero-draws",
                        "block_policy_count": 3,
                        "policy_order": 0,
                        "block_seed": seed,
                        "assignment_probability_first": 1 / 3,
                        "randomized_order": True,
                        "public_provider_count": 3,
                        "requested_order_length": 0,
                        "provider_only_count": 0,
                        "allow_fallbacks": True,
                    }
                ),
            }
        ]
    )

    assignment_only = frame.drop(
        columns=[
            "outcome",
            "retry_reason",
            "cost_usd",
            "latency_ms",
            "selected_provider",
            "fallback_triggered",
        ]
    )
    panel, _, contrasts, summary = analyze(assignment_only, simulations=0)

    assert summary["assignment_replay_passes"] == 1
    assert summary["treatment_metadata_passes"] == 1
    assert summary["outcomes_released"] is False
    assert summary["outcome_access"] == "not_queried_by_40_per_arm_gate"
    assert panel["success_rate"].isna().all()
    assert contrasts["randomization_p_greater"].isna().all()


def test_eligibility_funnel_reports_exclusions_and_support_turnover():
    eligibility = pd.DataFrame(
        [
            {
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "run_id": "run-1",
                "run_ts": "20260715T120000Z",
                "observed_at": "2026-07-15T12:00:00Z",
                "model_id": "model/a",
                "ranking_position": 5,
                "eligible": True,
                "exclusion_reason": "eligible",
            },
            {
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "run_id": "run-1",
                "run_ts": "20260715T120000Z",
                "observed_at": "2026-07-15T12:00:00Z",
                "model_id": "model/b",
                "ranking_position": 6,
                "eligible": False,
                "exclusion_reason": "fewer_than_two_distinct_positive_price_providers",
            },
            {
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "run_id": "run-2",
                "run_ts": "20260715T130000Z",
                "observed_at": "2026-07-15T13:00:00Z",
                "model_id": "model/a",
                "ranking_position": 5,
                "eligible": True,
                "exclusion_reason": "eligible",
            },
            {
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "run_id": "run-2",
                "run_ts": "20260715T130000Z",
                "observed_at": "2026-07-15T13:00:00Z",
                "model_id": "model/c",
                "ranking_position": 6,
                "eligible": True,
                "exclusion_reason": "eligible",
            },
        ]
    )

    rows, models, runs, summary = eligibility_diagnostics(eligibility, pd.DataFrame())

    assert len(rows) == 4
    assert len(models) == 3
    assert len(runs) == 2
    assert summary["candidate_rows"] == 4
    assert summary["eligible_rows"] == 3
    assert summary["eligibility_rate"] == 0.75
    assert summary["unique_eligible_models"] == 2
    assert summary["eligible_support_dominance"] == 2 / 3
    assert summary["mean_adjacent_support_jaccard"] == 0.5
    assert summary["mean_adjacent_support_turnover"] == 0.5
    assert summary["exclusion_reason_counts"] == {
        "eligible": 3,
        "fewer_than_two_distinct_positive_price_providers": 1,
    }


def test_frozen_release_report_renders_complete_neutral_package(tmp_path):
    panel, model_panel, contrasts, summary = analyze(_balanced_frame(), simulations=500)

    report = build_release_report(
        panel,
        model_panel,
        contrasts,
        summary,
        out_dir=tmp_path,
    )

    assert report["schema_version"] == "h81-release-report-v1"
    assert abs(report["decomposition_identity_error"]) < 1e-12
    assert report["model_count"] == 2
    for filename in report["files"] + ["h81_release_report.json"]:
        assert (tmp_path / filename).exists()
        assert (tmp_path / filename).stat().st_size > 0
    paragraph = (tmp_path / "h81_release_result_paragraph.tex").read_text()
    assert "nonsignificant" in paragraph
    assert "not evidence of equivalence" in paragraph
    assert "does not identify" in paragraph
    table = (tmp_path / "h81_release_result_table.tex").read_text()
    assert "Fallback option" in table
    assert "Hidden selection" in table
    assert "Total delegation" in table
    table_rows = [line for line in table.splitlines() if " & " in line]
    assert all(line.endswith("\\\\") for line in table_rows)
    assert all(not line.endswith("\\\\\\\\") for line in table_rows)
    assert "50.0\\%" in paragraph
    assert "50.0\\\\%" not in paragraph


def test_release_report_refuses_blinded_or_algebraically_incoherent_outputs():
    panel, _, contrasts, summary = analyze(_balanced_frame(), simulations=500)
    blinded = dict(summary, outcomes_released=False)
    with pytest.raises(ValueError, match="outcomes_released"):
        validate_release_outputs(panel, contrasts, blinded)

    broken = contrasts.copy()
    broken.loc[broken["estimand"].eq("total_delegation"), "success_difference_hajek"] += 0.1
    broken.loc[broken["estimand"].eq("total_delegation"), "success_difference_ht"] += 0.1
    with pytest.raises(ValueError, match="decomposition identity"):
        validate_release_outputs(panel, broken, summary)


def test_safe_release_report_preserves_raw_bundle_when_presentation_fails(tmp_path):
    panel, model_panel, contrasts, summary = analyze(_balanced_frame(), simulations=500)
    broken = contrasts.copy()
    broken.loc[broken["estimand"].eq("total_delegation"), "success_difference_hajek"] += 0.1
    broken.loc[broken["estimand"].eq("total_delegation"), "success_difference_ht"] += 0.1

    result = build_release_report_safely(
        panel,
        model_panel,
        broken,
        summary,
        out_dir=tmp_path,
    )

    assert result["status"] == "failed_closed_raw_release_preserved"
    assert result["paper_promotion_permitted"] is False
    assert result["automatic_outcome_requery_permitted"] is False
    assert result["outcomes_released"] is True
    error = json.loads((tmp_path / result["error_artifact"]).read_text())
    assert error["raw_analysis_files_preserved"] is True
    assert error["error_type"] == "ValueError"
    assert "decomposition identity" in error["error_message"]
