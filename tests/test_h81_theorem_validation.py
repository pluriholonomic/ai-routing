from __future__ import annotations

from orcap.analysis.h81_theorem_validation import (
    POLICIES,
    simulate_bias,
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

