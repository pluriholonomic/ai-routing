from __future__ import annotations

import numpy as np

from orcap.analysis.nonprice_scoring import (
    estimate_nonprice_scoring,
    price_sort_rule_contrast,
)


def _synthetic_choices(
    *,
    alpha: np.ndarray,
    choices: int = 600,
    seed: int = 11,
) -> list[dict]:
    rng = np.random.default_rng(seed)
    providers = ["cheap", "z.ai", "premium"]
    costs = np.asarray([0.60, 1.00, 1.20])
    eta = 1.6482780609377246
    logits = -eta * np.log(costs) + alpha
    probabilities = np.exp(logits - np.logaddexp.reduce(logits))
    rows = []
    for index in range(choices):
        selected = int(rng.choice(len(providers), p=probabilities))
        rows.append(
            {
                "block_id": f"block-{index // 2:04d}",
                "providers": providers,
                "costs": costs,
                "selected_index": selected,
            }
        )
    return rows


def test_nonprice_score_recovers_relative_order_and_attenuates_cheap_undercut():
    eta = 1.6482780609377246
    rows = _synthetic_choices(alpha=np.asarray([-1.0, 0.0, 0.8]))
    summary, providers, manipulation = estimate_nonprice_scoring(
        rows,
        eta=eta,
        benchmark_provider="z.ai",
        null_draws=500,
    )
    assert summary["status"] == "ready"
    assert summary["fit_ready"]
    assert summary["mean_probability_mass_reallocated_by_scoring"] > 0.10
    assert summary["cross_validated"]["nonprice_information_bits_per_choice"] > 0.05
    assert summary["price_only_null"]["monte_carlo_p_value"] < 0.01
    scores = providers.set_index("provider")
    assert scores.loc["premium", "relative_log_score"] > 0
    assert scores.loc["cheap", "relative_log_score"] < 0
    assert scores.loc["z.ai", "price_equivalent_discount_vs_reference"] == 0
    cheap = manipulation.set_index("provider").loc["cheap"]
    assert cheap["mean_scoring_interaction_share"] < 0
    assert cheap["scoring_attenuation_fraction"] > 0


def test_price_equivalent_score_identity():
    eta = 1.6482780609377246
    rows = _synthetic_choices(alpha=np.asarray([-0.5, 0.0, 0.5]), choices=400, seed=23)
    _, providers, _ = estimate_nonprice_scoring(
        rows,
        eta=eta,
        benchmark_provider="z.ai",
        null_draws=100,
    )
    for row in providers.to_dict("records"):
        reconstructed = 1 - np.exp(-row["relative_log_score"] / eta)
        assert row["price_equivalent_discount_vs_reference"] == reconstructed
        assert row["odds_multiplier_vs_reference"] == np.exp(row["relative_log_score"])


def test_nonprice_model_fails_closed_before_prospective_support():
    summary, providers, manipulation = estimate_nonprice_scoring(
        _synthetic_choices(alpha=np.zeros(3), choices=12),
        eta=1.6482780609377246,
        benchmark_provider="z.ai",
        null_draws=20,
    )
    assert summary["status"] == "accruing"
    assert not summary["fit_ready"]
    assert {"choices", "blocks"}.issubset(summary["support_failures"])
    assert providers.empty
    assert manipulation.empty


def test_price_sorted_arm_identifies_cheapest_selection_rule_effect():
    rows = []
    for block in range(24):
        for replicate in range(2):
            rows.append(
                {
                    "block_id": f"block-{block}",
                    "task_id": f"default-{block}-{replicate}",
                    "policy": "default_broad",
                    "providers": ["cheap", "other"],
                    "costs": np.asarray([1.0, 2.0]),
                    "selected_index": 1,
                }
            )
        rows.append(
            {
                "block_id": f"block-{block}",
                "task_id": f"sorted-{block}",
                "policy": "price_sorted",
                "providers": ["cheap", "other"],
                "costs": np.asarray([1.0, 2.0]),
                "selected_index": 0,
            }
        )
    summary, panel = price_sort_rule_contrast(rows, draws=200)
    assert summary["status"] == "ready"
    assert summary["complete_blocks"] == 24
    assert summary["price_sorted_minus_default_cheapest_rate"] == 1.0
    assert summary["block_bootstrap_95ci"] == [1.0, 1.0]
    assert len(panel) == 72
