import json
import random

import pandas as pd

from orcap.analysis.h81_delegation_decomposition import (
    POLICIES,
    analyze,
    eligibility_diagnostics,
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
    assert abs(
        indexed.loc["fallback_option", "success_difference_hajek"] - (32 / 39 - 20 / 40)
    ) < 1e-12
    assert abs(
        indexed.loc["hidden_selection", "success_difference_hajek"] - (40 / 40 - 32 / 39)
    ) < 1e-12
    assert abs(indexed.loc["total_delegation", "success_difference_hajek"] - 0.5) < 1e-12
    assert abs(indexed.loc["total_delegation", "success_difference_ht"] - 0.5) < 1e-12
    assert indexed.loc[["fallback_option", "hidden_selection"], "holm_p_greater"].notna().all()
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
    assert summary["analysis_randomization"].startswith("fixed-count")
    assert summary["simultaneous_uncertainty"].startswith("Bonferroni-Newcombe")
    sensitivity = summary["treatment_outcome_missingness_sensitivity"]
    assert sensitivity["treatment_missing_or_noncompliant"] == 0
    assert sensitivity["binary_outcome_missing_among_verified"] == 0
    assert indexed.loc[
        ["fallback_option", "hidden_selection"],
        "success_difference_simultaneous_ci_low",
    ].notna().all()
    assert indexed["success_difference_treatment_outcome_lower_bound"].notna().all()
    assert indexed["success_difference_treatment_outcome_upper_bound"].notna().all()
    assert summary["evidence_status"] == "randomized_decomposition_ready"


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
    assert hidden["success_difference_treatment_outcome_lower_bound"] < hidden[
        "success_difference_hajek"
    ]
    assert hidden["success_difference_treatment_outcome_upper_bound"] >= hidden[
        "success_difference_hajek"
    ]


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
