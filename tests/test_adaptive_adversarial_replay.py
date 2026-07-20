from __future__ import annotations

import numpy as np
import pandas as pd

from orcap.analysis.adaptive_adversarial_replay import (
    POLICIES,
    _attack_one_menu,
    _cluster_intervals,
    policy_shares,
)


def _menu() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "run_ts": ["20260720T000000Z"] * 3,
            "dt": ["2026-07-20"] * 3,
            "model_id": ["example/model"] * 3,
            "provider_name": ["A", "B", "C"],
            "expected_quote_usd": [1.0, 1.2, 1.5],
            "quality": [0.99, 0.98, 0.97],
        }
    )


def test_all_replay_policies_normalize_and_hardened_groups_sybil():
    providers = ["a", "b", "c"]
    costs = np.array([1.0, 1.2, 1.5])
    qualities = np.array([0.99, 0.98, 0.97])
    for policy in POLICIES:
        shares = policy_shares(policy, providers, costs, qualities)
        assert np.isclose(sum(shares.values()), 1.0)
        assert all(value >= 0 for value in shares.values())
    split_providers = providers + ["a#clone"]
    split_costs = np.append(costs, costs[0])
    split_qualities = np.append(qualities, qualities[0])
    hardened = policy_shares(
        "menu_adaptive_hardened",
        split_providers,
        split_costs,
        split_qualities,
        operator_groups={"a": "a", "a#clone": "a", "b": "b", "c": "c"},
    )
    assert hardened["a"] + hardened["a#clone"] <= 0.60 + 1e-12


def test_hardened_piecewise_elasticity_is_dimensionless_and_monotone():
    providers = ["a", "b", "c"]
    reference = np.array([0.0008, 0.0012, 0.0015])
    qualities = np.array([0.99, 0.98, 0.97])
    baseline = policy_shares(
        "menu_adaptive_hardened", providers, reference, qualities
    )
    raised = reference.copy()
    raised[0] *= 1.5
    changed = policy_shares(
        "menu_adaptive_hardened",
        providers,
        raised,
        qualities,
        previous=baseline,
        reference_costs=reference,
    )
    assert changed["a"] < baseline["a"]


def test_attack_panel_is_rectangular_and_profit_sensitivity_is_explicit():
    attacks, summaries = _attack_one_menu(_menu(), max_attack_providers=2)
    assert len(summaries) == len(POLICIES)
    assert len(attacks) == len(POLICIES) * 2 * 9
    assert {row["policy"] for row in summaries} == set(POLICIES)
    assert all("max_profit_gain_cost_frac_0.50" in row for row in summaries)
    hardened = next(row for row in summaries if row["policy"] == "menu_adaptive_hardened")
    assert hardened["sybil_combined_share_gain"] <= 0.60


def test_cluster_intervals_resample_model_days():
    _, summaries = _attack_one_menu(_menu(), max_attack_providers=2)
    frame = pd.DataFrame(summaries)
    second = frame.copy()
    second["dt"] = "2026-07-21"
    combined = pd.concat([frame, second], ignore_index=True)
    intervals = _cluster_intervals(combined, draws=20, seed=7)
    assert len(intervals) == (len(POLICIES) - 1) * 6
    assert set(intervals["clusters"]) == {2}
