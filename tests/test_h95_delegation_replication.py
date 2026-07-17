from __future__ import annotations

import itertools
import json
import math
import random
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

import orcap.analysis.h95_delegation_replication as h95
from orcap.capture_decomposition_probes import POLICIES
from orcap.capture_decomposition_replication import STUDY_ID, tasks_with_assigned_first


def _frames(triplets: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligibility: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    provider_order = ["cheap", "backup"]
    endpoints = [
        {"provider": "cheap", "price": 1.0, "input_price": 0.0},
        {"provider": "backup", "price": 2.0, "input_price": 0.0},
    ]
    for triplet_index in range(triplets):
        triplet_id = f"{STUDY_ID}|triplet-{triplet_index:03d}"
        observed_at = datetime(2026, 7, 17, 5, tzinfo=UTC) + timedelta(hours=triplet_index)
        shift = triplet_index % len(POLICIES)
        assigned_policies = (*POLICIES[shift:], *POLICIES[:shift])
        for position, policy in enumerate(assigned_policies):
            model_id = f"org/model-{(triplet_index + position) % 9}"
            block_id = f"{triplet_id}|{model_id}"
            block_seed = 10_000 + triplet_index * 3 + position
            eligibility.append(
                {
                    "run_id": f"triplet-{triplet_index:03d}",
                    "run_ts": observed_at.strftime("%Y%m%dT%H%M%SZ"),
                    "observed_at": observed_at.isoformat(),
                    "study_id": STUDY_ID,
                    "triplet_id": triplet_id,
                    "ranking_position": 7 + (triplet_index + position) % 24,
                    "model_id": model_id,
                    "hugging_face_id": model_id,
                    "eligible": True,
                    "selected_for_triplet": True,
                    "triplet_position": position,
                    "assigned_first_policy": policy,
                    "block_id": block_id,
                }
            )
            tasks = tasks_with_assigned_first(endpoints, policy, random.Random(block_seed))
            for policy_order, task in enumerate(tasks):
                metadata = {
                    "triplet_id": triplet_id,
                    "block_id": block_id,
                    "assigned_first_policy": policy,
                    "policy_order": policy_order,
                    "block_seed": block_seed,
                    "ranking_position": 7 + (triplet_index + position) % 24,
                    "hugging_face_id": model_id,
                    "public_provider_order": provider_order,
                    "public_provider_count": len(provider_order),
                    "requested_order_length": len(task["provider_order"] or []),
                    "provider_only_count": len(task["provider_only"] or []),
                    "allow_fallbacks": task["allow_fallbacks"],
                    "assignment_probability_first": 1 / 3,
                }
                attempts.append(
                    {
                        "source": "openrouter_generation",
                        "event_id": f"{block_id}|{policy_order}",
                        "run_ts": observed_at.strftime("%Y%m%dT%H%M%SZ"),
                        "observed_at": (observed_at + timedelta(seconds=policy_order)).isoformat(),
                        "study_id": STUDY_ID,
                        "model_id": model_id,
                        "policy": task["policy"],
                        "metadata_json": json.dumps(metadata),
                        "outcome": (
                            "succeeded"
                            if policy in {"delegated_default", "price_order_fallback"}
                            else "failed"
                        ),
                    }
                )
    return pd.DataFrame(eligibility), pd.DataFrame(attempts)


def test_gate_is_assignment_only_before_fixed_horizon() -> None:
    eligibility, attempts = _frames(4)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, audit, _, plans = h95.gate_summary(prepared, eligibility, simulations=200)

    assert summary["release_ready"] is False
    assert summary["outcome_access"] == "not_queried_by_fixed_horizon_gate"
    assert summary["planned_triplets"] == 4
    assert summary["planned_first_position_blocks"] == 12
    assert audit["complete_assignment"].all()
    assert audit["plan_compliance"].all()
    assert audit["replay_passes"].sum() == 12
    assert len(plans) == 12


def test_fixed_horizon_releases_exact_balance_and_blocked_contrasts() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, audit, _, plans = h95.gate_summary(prepared, eligibility, simulations=500)
    assert summary["release_ready"] is True
    assert len(plans) == 360
    assert audit["complete_assignment"].all()

    (
        panel,
        models,
        contrasts,
        lomo,
        position_panel,
        outcome_audit,
        released,
    ) = h95.analyze_released(attempts, plans, summary, simulations=500)

    assert panel.set_index("policy")["assigned_blocks"].to_dict() == {
        policy: 120 for policy in POLICIES
    }
    estimates = contrasts.set_index("estimand")["success_difference"].to_dict()
    assert estimates["fallback_option_value"] == 1.0
    assert estimates["hidden_selection_value"] == 0.0
    assert estimates["total_delegation_value"] == 1.0
    assert released["primary_missing_attempts"] == 0
    assert released["primary_assignment_compliance_rate"] == 1.0
    assert released["primary_treatment_metadata_audit_coverage"] == 1.0
    assert released["support"]["broad_multi_model_transport_ready"] is True
    assert models["model_id"].nunique() == 9
    assert not lomo.empty
    assert len(position_panel) == 9
    assert position_panel["assigned_blocks"].eq(40).all()
    assert len(outcome_audit) == 360

    zero_panel, zero_contrasts, zero_summary = h95._position_zero_sensitivity(outcome_audit)
    assert zero_summary["triplets"] == h95.TARGET_TRIPLETS
    assert zero_summary["policy_counts"] == {policy: 40 for policy in POLICIES}
    assert zero_panel["assigned_blocks"].eq(40).all()
    zero_estimates = zero_contrasts.set_index("estimand")["success_difference"].to_dict()
    assert zero_estimates["fallback_option_value"] == 1.0
    assert zero_estimates["hidden_selection_value"] == 0.0
    assert zero_contrasts.loc[zero_contrasts["primary"], "holm_p_greater"].notna().all()


def test_exact_randomization_matches_brute_force_for_two_triplets() -> None:
    outcomes = pd.DataFrame(
        [
            {
                "triplet_id": triplet,
                "model_id": f"model-{triplet}-{model}",
                "assigned_first_policy": policy,
                "primary_success": value,
            }
            for triplet, values in (("a", (1, 0, 1)), ("b", (0, 0, 1)))
            for model, (policy, value) in enumerate(zip(POLICIES, values, strict=True))
        ]
    )
    exact = h95._exact_blocked_randomization_pvalues(outcomes)
    wide = outcomes.pivot(
        index="triplet_id", columns="assigned_first_policy", values="primary_success"
    )
    for name, positive, negative, _ in h95.COMPARISONS:
        observed_differences = (wide[positive] - wide[negative]).to_numpy()
        observed = observed_differences.sum()
        null = [
            sum(
                sign * abs(difference)
                for sign, difference in zip(signs, observed_differences, strict=True)
            )
            for signs in itertools.product((-1, 1), repeat=2)
        ]
        greater = sum(value >= observed for value in null) / len(null)
        two_sided = sum(abs(value) >= abs(observed) for value in null) / len(null)
        assert exact[name][0] == pytest.approx(greater)
        assert exact[name][1] == pytest.approx(two_sided)


def test_design_interval_uses_two_contrast_family_radius() -> None:
    radius = h95._blocked_design_radius(h95.TARGET_TRIPLETS, family_size=2)
    expected = (2 * math.log(4 / h95.PRIMARY_FWER_ALPHA) / h95.TARGET_TRIPLETS) ** 0.5
    assert radius == pytest.approx(expected)

    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, _, _, plans = h95.gate_summary(prepared, eligibility, simulations=0)
    _, _, contrasts, _, _, _, _ = h95.analyze_released(attempts, plans, summary, simulations=0)
    primary = contrasts.loc[contrasts["primary"]]
    assert primary["design_hoeffding_radius"].eq(radius).all()
    assert primary["design_hoeffding_family_size"].eq(2).all()


def test_unknown_recorded_outcome_is_not_silently_coded_as_failure() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, _, _, plans = h95.gate_summary(prepared, eligibility, simulations=500)
    first_index = attempts.index[attempts["event_id"].str.endswith("|0")][0]
    attempts.loc[first_index, "outcome"] = "unknown"

    panel, _, contrasts, _, _, outcome_audit, released = h95.analyze_released(
        attempts, plans, summary, simulations=500
    )

    assert released["primary_measurement_missing_outcomes"] == 1
    assert released["point_inference_suppressed_for_measurement_missingness"] is True
    assert released["position_zero_sensitivity"]["complete_binary_outcomes"] is False
    assert contrasts["success_difference"].isna().all()
    assert contrasts["randomization_p_greater"].isna().all()
    assert contrasts["design_hoeffding_ci_low"].isna().all()
    assert contrasts["design_hoeffding_ci_high"].isna().all()
    assert int(outcome_audit["measurement_missing"].sum()) == 1
    affected_policy = outcome_audit.loc[
        outcome_audit["measurement_missing"], "assigned_first_policy"
    ].iloc[0]
    affected_arm = panel.set_index("policy").loc[affected_policy]
    assert (
        affected_arm["success_rate_measurement_upper_bound"]
        - affected_arm["success_rate_measurement_lower_bound"]
    ) == pytest.approx(1 / h95.TARGET_TRIPLETS)


def test_later_measurement_missingness_does_not_erase_position_zero_sensitivity() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, _, _, plans = h95.gate_summary(prepared, eligibility, simulations=0)
    later_block = eligibility.loc[eligibility["triplet_position"].eq(1), "block_id"].iloc[0]
    later_first = attempts.index[
        attempts["event_id"].str.startswith(f"{later_block}|")
        & attempts["event_id"].str.endswith("|0")
    ][0]
    attempts.loc[later_first, "outcome"] = "unknown"

    _, _, contrasts, _, _, outcome_audit, released = h95.analyze_released(
        attempts, plans, summary, simulations=0
    )
    _, zero_contrasts, zero_summary = h95._position_zero_sensitivity(outcome_audit)

    assert contrasts["success_difference"].isna().all()
    assert released["position_zero_sensitivity"]["complete_binary_outcomes"] is True
    assert zero_summary["complete_binary_outcomes"] is True
    assert zero_contrasts["success_difference"].notna().all()


def test_missing_and_noncompliant_first_requests_remain_structural_itt_zeros() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, _, _, plans = h95.gate_summary(prepared, eligibility, simulations=500)
    first_indices = attempts.index[attempts["event_id"].str.endswith("|0")].tolist()
    attempts = attempts.drop(index=first_indices[0]).copy()
    attempts.loc[first_indices[1], "policy"] = "not_the_assigned_policy"

    _, _, contrasts, _, _, outcome_audit, released = h95.analyze_released(
        attempts, plans, summary, simulations=500
    )

    assert released["primary_missing_attempts"] == 1
    assert released["primary_measurement_missing_outcomes"] == 0
    assert int(outcome_audit["structural_failure"].sum()) == 2
    assert outcome_audit.loc[outcome_audit["structural_failure"], "primary_success"].eq(0.0).all()
    assert contrasts["success_difference"].notna().all()


def test_production_monte_carlo_audit_passes_and_transport_is_reported() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, _, _, plans = h95.gate_summary(
        prepared, eligibility, simulations=h95.RANDOMIZATION_DRAWS
    )
    _, _, contrasts, lomo, _, _, released = h95.analyze_released(
        attempts,
        plans,
        summary,
        simulations=h95.RANDOMIZATION_DRAWS,
    )

    assert bool(contrasts["randomization_mc_audit_pass"].astype(bool).all())
    assert released["randomization_mc_audit_enforced"] is True
    assert released["support"]["max_six_hour_triplet_share"] <= 0.20
    assert released["support"]["lomo_primary_direction_stability_pass"] is True
    assert lomo["retained_triplets"].min() > 0


def test_corrupt_treatment_metadata_is_a_structural_zero() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, _, _, plans = h95.gate_summary(prepared, eligibility, simulations=500)
    first_index = attempts.index[attempts["event_id"].str.endswith("|0")][0]
    metadata = json.loads(attempts.loc[first_index, "metadata_json"])
    metadata["requested_order_length"] = 99
    attempts.loc[first_index, "metadata_json"] = json.dumps(metadata)

    _, _, _, _, _, outcome_audit, released = h95.analyze_released(
        attempts, plans, summary, simulations=500
    )

    corrupt = outcome_audit.loc[
        outcome_audit["treatment_metadata_auditable"]
        & ~outcome_audit["treatment_metadata_pass"].astype(bool)
    ]
    assert len(corrupt) == 1
    assert bool(corrupt["structural_failure"].iloc[0]) is True
    assert corrupt["primary_success"].iloc[0] == 0.0
    assert released["primary_treatment_metadata_pass_rate_among_auditable"] < 1.0


def test_production_randomization_audit_fails_closed_on_drift(monkeypatch) -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))
    summary, _, _, plans = h95.gate_summary(
        prepared, eligibility, simulations=h95.RANDOMIZATION_DRAWS
    )

    monkeypatch.setattr(
        h95,
        "_monte_carlo_randomization_pvalues",
        lambda *args, **kwargs: {name: (0.5, 0.5) for name, *_ in h95.COMPARISONS},
    )
    with pytest.raises(RuntimeError, match="randomization audit failed"):
        h95.analyze_released(
            attempts,
            plans,
            summary,
            simulations=h95.RANDOMIZATION_DRAWS,
        )


def test_six_hour_concentration_gate_uses_triplets_not_blocks() -> None:
    eligibility, attempts = _frames(h95.TARGET_TRIPLETS)
    eligibility["observed_at"] = "2026-07-17T05:00:00+00:00"
    eligibility["run_ts"] = "20260717T050000Z"
    prepared = h95.prepare_assignment_attempts(attempts.drop(columns=["outcome"]))

    summary, _, _, _ = h95.gate_summary(prepared, eligibility, simulations=0)

    assert summary["support"]["max_six_hour_triplets"] == h95.TARGET_TRIPLETS
    assert summary["support"]["max_six_hour_triplet_share"] == 1.0
    assert summary["support"]["structural_transport_gates_pass"] is False


def test_run_never_queries_outcomes_while_gate_is_closed(monkeypatch, tmp_path) -> None:
    eligibility, attempts = _frames(2)
    assignment = attempts.drop(columns=["outcome"])
    queries: list[str] = []

    class Relation:
        def __init__(self, frame):
            self.frame = frame

        def df(self):
            return self.frame.copy()

    def fake_q(sql: str):
        queries.append(sql)
        if "router_replication_eligibility" in sql:
            return Relation(eligibility)
        assert "outcome" not in sql.lower()
        assert "cost_usd" not in sql.lower()
        assert "selected_provider" not in sql.lower()
        return Relation(assignment)

    monkeypatch.setattr(h95.data, "q", fake_q)
    summary = h95.run(tmp_path, simulations=100)

    assert summary["outcomes_released"] is False
    assert len(queries) == 2
    assert all("outcome" not in query.lower() for query in queries)
