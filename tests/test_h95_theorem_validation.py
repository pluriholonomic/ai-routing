from __future__ import annotations

import numpy as np

import orcap.analysis.h95_theorem_validation as validation


def test_fixed_schedules_encode_the_registered_pairwise_nulls() -> None:
    schedules = validation.fixed_potential_outcome_schedules()
    fallback = schedules["fallback_null_delegation_nuisance"]
    selection = schedules["selection_null_no_fallback_nuisance"]
    index = validation.POLICY_INDEX

    assert np.array_equal(
        fallback[:, :, index["price_only_no_fallback"]],
        fallback[:, :, index["price_order_fallback"]],
    )
    assert np.array_equal(
        selection[:, :, index["price_order_fallback"]],
        selection[:, :, index["delegated_default"]],
    )


def test_pairwise_conditioning_repairs_nuisance_arm_size() -> None:
    audit = validation.simulate_pairwise_nuisance_size(experiments=3_000)
    corrected = audit.loc[audit["method"].eq("pairwise_conditional")]
    superseded = audit.loc[audit["method"].eq("superseded_all_policy")]

    assert corrected["raw_rejection_rate"].max() <= 0.055
    assert corrected["holm_true_null_rejection_rate"].max() <= 0.055
    assert superseded["raw_rejection_rate"].min() >= 0.07
    assert superseded["holm_true_null_rejection_rate"].min() >= 0.07


def test_design_interval_covers_fixed_schedule_family() -> None:
    audit = validation.simulate_interval_coverage(experiments_per_scenario=2_000)
    family = audit.loc[audit["estimand"].eq("two_primary_family")]
    component = audit.loc[audit["estimand"].ne("two_primary_family")]

    assert family["design_hoeffding_family_coverage"].min() >= 0.99
    assert component["monte_carlo_bias"].abs().max() <= 0.005
    assert family["design_hoeffding_mean_width"].mean() > family["paired_t_mean_width"].mean()
