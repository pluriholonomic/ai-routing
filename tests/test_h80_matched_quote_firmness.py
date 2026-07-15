import json
import random

import pandas as pd

from orcap.analysis.h80_matched_quote_firmness import (
    POLICIES,
    construct_probe_blocks,
    holm_adjust,
    normalized_order_entropy,
    paired_contrasts,
    randomized_first_position_analysis,
)


def _row(block, policy, minute, success, *, explicit=False, position=None):
    metadata = {}
    if explicit:
        metadata = {
            "block_id": block,
            "block_policy_count": 4,
            "policy_order": position,
            "randomized_order": True,
            "assignment_probability_first": 0.25,
            "block_seed": 17,
            "n_quoted": 5,
            "quoted_rank": {
                "pinned_cheapest": 0,
                "pinned_second": 1,
                "pinned_random": 4,
            }.get(policy),
        }
    provider = {
        "pinned_cheapest": "Cheap",
        "pinned_second": "Second",
        "pinned_random": "Random",
    }.get(policy)
    return {
        "source": "openrouter_generation",
        "event_id": f"{block}-{policy}",
        "observed_at": f"2026-07-14T00:00:{minute:02d}Z",
        "run_ts": "20260714T010000Z",
        "study_id": (
            "openrouter-routing-crossover-v2" if explicit else "openrouter-default-probes-v1"
        ),
        "model_id": "model/a",
        "policy": policy,
        "outcome": "succeeded" if success else "failed",
        "retry_reason": None if success else "http_429",
        "requested_provider": provider,
        "selected_provider": "Cheap" if policy == "openrouter_default" else provider,
        "cost_usd": 0.000004 if success else None,
        "latency_ms": 10.0,
        "metadata_json": json.dumps(metadata),
    }


def test_constructs_complete_legacy_block_and_exposes_fixed_order():
    rows = [
        _row("legacy", policy, i, policy == "openrouter_default")
        for i, policy in enumerate(POLICIES)
    ]
    blocks = construct_probe_blocks(pd.DataFrame(rows))
    assert blocks["block_id"].nunique() == 1
    assert blocks["policy_order"].tolist() == [0, 1, 2, 3]
    assert blocks["default_selected_quote_class"].unique().tolist() == ["cheapest"]
    assert normalized_order_entropy(blocks) == 0.0


def test_explicit_randomized_block_uses_published_assignment():
    order = ["openrouter_default", "pinned_second", "pinned_cheapest", "pinned_random"]
    rows = [
        _row("v2", policy, i, True, explicit=True, position=i) for i, policy in enumerate(order)
    ]
    blocks = construct_probe_blocks(pd.DataFrame(rows))
    assert blocks["block_source"].unique().tolist() == ["explicit_assignment"]
    first = blocks.loc[blocks["policy_order"].eq(0), "policy"].iloc[0]
    assert first == "openrouter_default"
    assert blocks["assignment_verified"].all()
    assert blocks["first_assignment_verified"].all()


def test_incomplete_explicit_block_retains_auditable_first_position_itt():
    first = _row(
        "interrupted",
        "openrouter_default",
        0,
        False,
        explicit=True,
        position=0,
    )
    blocks = construct_probe_blocks(pd.DataFrame([first]))
    assert len(blocks) == 1
    assert not bool(blocks["block_complete"].iloc[0])
    assert bool(blocks["assignment_verified"].iloc[0])
    assert bool(blocks["first_assignment_verified"].iloc[0])


def test_later_corruption_does_not_invalidate_preregistered_first_position():
    order = ["openrouter_default", "pinned_second", "pinned_cheapest", "pinned_random"]
    rows = [
        _row("corrupt-later", policy, i, True, explicit=True, position=i)
        for i, policy in enumerate(order)
    ]
    duplicate = _row(
        "corrupt-later", "pinned_random", 5, True, explicit=True, position=3
    )
    duplicate["event_id"] += "-duplicate"
    rows.append(duplicate)
    blocks = construct_probe_blocks(pd.DataFrame(rows))
    assert not blocks["assignment_verified"].any()
    assert blocks["first_assignment_verified"].all()
    assert not blocks["block_complete"].any()


def test_assignment_replay_preserves_unsigned_64_bit_seed_bits():
    seed = 16_232_024_600_027_900_149
    n_quoted = 17
    rng = random.Random(seed)
    random_rank = rng.choice(range(2, n_quoted))
    order = list(POLICIES)
    rng.shuffle(order)
    rows = []
    for position, policy in enumerate(order):
        row = _row("large-seed", policy, position, True, explicit=True, position=position)
        metadata = json.loads(row["metadata_json"])
        metadata["block_seed"] = seed
        metadata["n_quoted"] = n_quoted
        if policy == "pinned_random":
            metadata["quoted_rank"] = random_rank
        row["metadata_json"] = json.dumps(metadata)
        rows.append(row)
    blocks = construct_probe_blocks(pd.DataFrame(rows))
    assert blocks["assignment_verified"].all()


def test_paired_contrast_recovers_success_gap_and_break_even_value():
    rows = []
    for b in range(12):
        for i, policy in enumerate(POLICIES):
            success = policy == "openrouter_default" or (policy == "pinned_cheapest" and b < 6)
            row = _row(f"b{b}", policy, i, success, explicit=True, position=i)
            row["observed_at"] = f"2026-07-14T{b:02d}:{i:02d}:00Z"
            row["cost_usd"] = (
                0.000006 if policy == "openrouter_default" else (0.000002 if success else None)
            )
            rows.append(row)
    blocks = construct_probe_blocks(pd.DataFrame(rows))
    result = paired_contrasts(blocks, bootstrap=500)
    cheap = result[result["comparison"].str.endswith("pinned_cheapest")].iloc[0]
    assert cheap["success_difference"] == 0.5
    assert cheap["observed_spend_difference_usd"] > 0
    assert cheap["break_even_value_per_success_usd"] > 0


def test_holm_adjust_preserves_missing_values():
    adjusted = holm_adjust([0.01, float("nan"), 0.04, 0.03])
    assert adjusted[0] == 0.03
    assert pd.isna(adjusted[1])
    assert adjusted[2] == 0.06
    assert adjusted[3] == 0.06


def test_randomized_first_position_emits_ipw_model_panel_and_gate():
    rows = []
    for block_number in range(160):
        policy = POLICIES[block_number % len(POLICIES)]
        model_id = f"model/{block_number % 2}"
        rows.append(
            {
                "block_id": f"v2-{block_number}",
                "block_source": "explicit_assignment",
                "study_id": "openrouter-routing-crossover-v2",
                "assignment_verified": True,
                "policy_order": 0,
                "randomized_order": True,
                "policy": policy,
                "model_id": model_id,
                "success": policy == "openrouter_default",
                "rejected_429": policy != "openrouter_default",
                "observed_spend_usd": 0.000004,
                "assignment_probability_first": 0.25,
            }
        )
    panel, model_panel, contrasts, audit = randomized_first_position_analysis(
        pd.DataFrame(rows), simulations=2_000
    )
    assert panel.set_index("policy").loc["openrouter_default", "ht_success_mean"] == 1.0
    assert len(model_panel) == 4
    assert set(model_panel["model_id"]) == {"model/0", "model/1"}
    assert contrasts["success_difference_ht"].eq(1.0).all()
    assert contrasts["holm_p_greater"].notna().all()
    assert audit["assignment_replay_rate"] == 1.0
    assert audit["models_represented"] == 2
    assert audit["outcomes_released"] is True
    assert audit["confirmatory_prefix_blocks"] == 160
    assert audit["evidence_status"] == "randomized_first_position_ready"


def test_randomized_first_position_blinds_outcomes_before_gate():
    rows = []
    for block_number, policy in enumerate(POLICIES):
        rows.append(
            {
                "block_id": f"blind-{block_number}",
                "block_source": "explicit_assignment",
                "study_id": "openrouter-routing-crossover-v2",
                "assignment_verified": True,
                "policy_order": 0,
                "randomized_order": True,
                "policy": policy,
                "model_id": "model/a",
                "success": True,
                "rejected_429": False,
                "observed_spend_usd": 0.000004,
                "assignment_probability_first": 0.25,
            }
        )
    panel, _, contrasts, audit = randomized_first_position_analysis(
        pd.DataFrame(rows), simulations=100
    )
    assert audit["outcomes_released"] is False
    assert panel["success_rate"].isna().all()
    assert contrasts["randomization_p_greater"].isna().all()
