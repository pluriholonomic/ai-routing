from __future__ import annotations

from orcap.analysis.h81_theorem_validation import (
    POLICIES,
    exact_joint_holm_power,
    exact_pairwise_bernoulli_power,
    simulate_bias,
    simulate_interval_coverage,
    simulate_nuisance_arm_size,
    simulate_randomization_size,
    stopped_assignment,
    summarize,
)


def test_stopped_assignment_hits_gate_and_preterminal_counts_are_positive():
    import numpy as np

    labels = stopped_assignment(np.random.default_rng(7), 5)
    counts = [(labels == index).sum() for index in range(len(POLICIES))]
    preterminal = [(labels[:-1] == index).sum() for index in range(len(POLICIES))]
    assert min(counts) == 5
    assert min(preterminal) == 4
    assert sum(value == 4 for value in preterminal) == 1


def test_preterminal_estimator_is_nearly_unbiased_in_monte_carlo():
    bias = simulate_bias(draws=4_000, target_per_arm=8, seed=11)
    summary = summarize(
        bias,
        simulate_randomization_size(
            experiments=80,
            permutations=199,
            target_per_arm=8,
            seed=12,
        ),
    )
    for row in summary["contrast_validation"]:
        assert abs(row["corrected_bias"]) <= 3.5 * row["corrected_monte_carlo_se"] + 0.002
    assert 0.0 <= summary["randomization_test_rejection_rate_5pct"] <= 0.125


def test_pairwise_test_controls_size_with_a_nonnull_nuisance_arm():
    audit = simulate_nuisance_arm_size(experiments=500, target_per_arm=8, seed=23)
    rates = audit.groupby("scenario")[["pairwise_reject_5pct", "all_arm_reject_5pct"]].mean()

    # Exact randomization tests may be conservative because their support is
    # discrete, but the corrected pairwise law must not be anti-conservative.
    assert rates["pairwise_reject_5pct"].max() <= 0.08
    assert audit["pairwise_p_greater"].between(0.0, 1.0).all()


def test_exact_pairwise_power_increases_with_effect_size():
    powers = [
        exact_pairwise_bernoulli_power(
            n_positive=12,
            n_negative=12,
            p_positive=0.5 + effect,
            p_negative=0.5,
            alpha=0.05,
        )
        for effect in (0.0, 0.15, 0.30)
    ]
    assert powers == sorted(powers)
    assert powers[-1] > powers[0]


def test_interval_coverage_audit_emits_both_descriptive_and_design_intervals():
    audit = simulate_interval_coverage(experiments_per_scenario=20, target_per_arm=8, seed=31)
    assert set(audit["estimand"]) == {"fallback_option", "hidden_selection"}
    assert audit["newcombe_marginal_covers"].dtype == bool
    assert audit["design_serfling_covers"].dtype == bool
    assert (audit["design_serfling_low"] <= audit["truth"]).mean() >= 0.95
    assert (audit["truth"] <= audit["design_serfling_high"]).mean() >= 0.95


def test_exact_joint_holm_power_controls_global_and_mixed_null_fwer():
    counts = dict.fromkeys(POLICIES, 8)
    global_null = exact_joint_holm_power(
        counts=counts,
        probabilities=dict.fromkeys(POLICIES, 0.5),
    )
    assert global_null["any_rejection_probability"] <= 0.05 + 1e-12

    mixed = exact_joint_holm_power(
        counts=counts,
        probabilities={
            "price_only_no_fallback": 0.1,
            "price_order_fallback": 0.9,
            "delegated_default": 0.9,
        },
    )
    assert mixed["fallback_rejection_probability"] > global_null["any_rejection_probability"]
    assert mixed["selection_rejection_probability"] <= 0.05 + 1e-12
