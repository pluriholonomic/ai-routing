import json
import random

import pandas as pd

from orcap.analysis.h81_delegation_decomposition import POLICIES, analyze


def _seed_for_first(policy: str, start: int) -> int:
    for seed in range(start, start + 10_000):
        expected = list(POLICIES)
        random.Random(seed).shuffle(expected)
        if expected[0] == policy:
            return seed
    raise AssertionError("no seed found")


def test_randomized_decomposition_recovers_both_policy_wedges():
    rows = []
    success_counts = {
        "delegated_default": 40,
        "price_order_fallback": 32,
        "price_only_no_fallback": 20,
    }
    block_number = 0
    for policy in POLICIES:
        for within_arm in range(40):
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
                    "run_ts": f"20260715T{block_number:06d}Z",
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
    panel, model_panel, contrasts, summary = analyze(frame, simulations=5_000)
    indexed = contrasts.set_index("estimand")
    assert abs(indexed.loc["fallback_option", "success_difference_hajek"] - 0.3) < 1e-12
    assert abs(indexed.loc["hidden_selection", "success_difference_hajek"] - 0.2) < 1e-12
    assert abs(indexed.loc["total_delegation", "success_difference_hajek"] - 0.5) < 1e-12
    assert abs(indexed.loc["total_delegation", "success_difference_ht"] - 0.5) < 1e-12
    assert indexed.loc[["fallback_option", "hidden_selection"], "holm_p_greater"].notna().all()
    assert pd.isna(indexed.loc["total_delegation", "holm_p_greater"])
    assert panel["first_position_attempts"].eq(40).all()
    assert len(model_panel) == 6
    assert summary["assignment_replay_rate"] == 1.0
    assert summary["treatment_metadata_passes"] == 120
    assert summary["outcomes_released"] is True
    assert summary["confirmatory_prefix_blocks"] == 120
    assert summary["evidence_status"] == "randomized_decomposition_ready"
