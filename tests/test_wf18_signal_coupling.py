from __future__ import annotations

import numpy as np
import pandas as pd

from orcap.analysis import data
from orcap.analysis import wf18_signal_coupling as wf18


def _price_events(days: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    author = []
    signal = np.sin(np.arange(days) * 1.7) * 0.08
    for day, value in zip(pd.date_range("2026-01-01", periods=days, tz="UTC"), signal, strict=True):
        author.append(
            {
                "model_id": "author/model",
                "dt": day.normalize(),
                "author_price": 1.0,
                "author_log_change": 0.0,
            }
        )
        for provider in ("A", "B"):
            rows.append(
                {
                    "ts": pd.Timestamp(day) + pd.Timedelta(12, unit="h"),
                    "model_id": "author/model",
                    "provider_name": provider,
                    "old_price": 1.0,
                    "new_price": float(np.exp(value)),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(author)


def test_chronological_split_is_disjoint_and_forward_only():
    timestamps = pd.Series(pd.date_range("2026-01-01", periods=20, tz="UTC"))
    split = wf18.chronological_split(timestamps, calibration_fraction=0.25, mechanism_fraction=0.50)
    assert len(split["calibration_dates"]) == 5
    assert len(split["mechanism_dates"]) == 10
    assert len(split["outcome_dates"]) == 5
    assert max(split["calibration_dates"]) < min(split["mechanism_dates"])
    assert max(split["mechanism_dates"]) < min(split["outcome_dates"])


def test_calibration_only_residualization_and_coupling_recovery():
    changes, author = _price_events()
    split = wf18.chronological_split(changes.ts, calibration_fraction=0.25, mechanism_fraction=0.50)
    innovations, diagnostics = wf18.prepare_quote_innovations(changes, author, split, ridge=1e-6)
    assert diagnostics["n_calibration_events"] == 30
    assert abs(innovations[innovations.period == "calibration"].residual_innovation.mean()) < 1e-8
    mechanism = innovations[innovations.period == "mechanism"].reset_index(drop=True)
    null, inference = wf18.circular_sequence_inference(
        mechanism, window_hours=1, permutations=199, seed=17
    )
    assert len(null) == 199
    assert inference["observed_minus_null_mean"] > 0
    assert inference["one_sided_p_excess_coupling"] <= 0.05


def test_pair_products_never_pair_provider_with_itself_or_duplicate_order():
    changes, author = _price_events(days=10)
    split = wf18.chronological_split(changes.ts, calibration_fraction=0.2, mechanism_fraction=0.5)
    innovations, _ = wf18.prepare_quote_innovations(changes, author, split, ridge=1e-6)
    products = wf18.pair_products(innovations, window_hours=1)
    assert (products.provider_a < products.provider_b).all()
    assert (products.provider_a != products.provider_b).all()
    assert not products.duplicated(["event_a", "event_b"]).any()


def _owned_tables(tasks: int = 120):
    candidates = []
    assignments = []
    attempts = []
    rng = np.random.default_rng(9)
    for task in range(tasks):
        task_id = f"task-{task}"
        block_id = f"block-{task}"
        price_a = float(np.exp(rng.normal(-0.1, 0.25)))
        price_b = float(np.exp(rng.normal(0.1, 0.25)))
        probability_a = 1 / (1 + np.exp(4 * np.log(price_a / price_b)))
        selected = "A" if rng.random() < probability_a else "B"
        for provider, price in (("A", price_a), ("B", price_b)):
            candidates.append(
                {
                    "run_id": "run",
                    "block_id": block_id,
                    "model_id": "author/model",
                    "provider_name": provider,
                    "expected_quote_usd": price,
                    "conservative_quote_usd": price,
                    "compatible": True,
                }
            )
        assignments.append(
            {
                "run_id": "run",
                "task_id": task_id,
                "block_id": block_id,
                "model_id": "author/model",
                "policy": "default_broad",
            }
        )
        attempts.append(
            {
                "task_id": task_id,
                "observed_at": (
                    pd.Timestamp("2026-02-01", tz="UTC") + pd.Timedelta(int(task), unit="h")
                ).isoformat(),
                "run_ts": "",
                "selected_provider": selected,
                "outcome": "succeeded",
                "fallback_triggered": False,
                "cost_usd": 0.001,
                "latency_ms": 100.0,
            }
        )
    return pd.DataFrame(candidates), pd.DataFrame(assignments), pd.DataFrame(attempts)


def test_owned_risk_set_excludes_nondelegated_policies_and_expands_menu():
    candidates, assignments, attempts = _owned_tables(tasks=10)
    assignments.loc[0, "policy"] = "pinned_a"
    risk = wf18.build_owned_choice_risk_set(candidates, assignments, attempts)
    assert risk.task_id.nunique() == 9
    assert len(risk) == 18
    assert risk.groupby("task_id").selected.sum().eq(1).all()
    assert set(risk.policy) == {"default_broad"}


def test_snr_and_elasticity_wedge_return_explicit_support_status():
    candidates, assignments, attempts = _owned_tables(tasks=240)
    risk = wf18.build_owned_choice_risk_set(candidates, assignments, attempts)
    snr = wf18.estimate_preperiod_snr(
        risk,
        preperiod_end=risk.dt.max(),
        minimum_choices=20,
    )
    assert set(snr.status) == {"leave_date_out_estimated"}
    assert (snr.routing_snr > 0).all()
    wedge, summary = wf18.elasticity_wedge_panel(risk, minimum_choices=200)
    assert len(wedge) == 1
    assert summary["status"] == "estimated"
    assert np.isfinite(wedge.iloc[0].elasticity_wedge)


def test_claim_promotion_is_impossible_without_support_gate():
    claims = wf18.claim_level(
        {
            "one_sided_p_excess_coupling": 0.001,
            "observed_minus_null_mean": 1.0,
        },
        {"snr_gradient_95ci": [0.1, 0.2]},
        {"status": "estimated", "estimated_clusters": 10},
        {"coupling_difference_premium_minus_other": 1.0},
        release_ready=False,
        alpha=0.05,
    )
    assert claims["level"] == "no_promoted_confirmatory_claim"
    assert claims["collusion_identified"] is False
    assert claims["provider_algorithm_identified"] is False
    assert claims["communication_identified"] is False


def test_holm_family_refuses_partial_chain():
    family = wf18.holm_family(
        {"one_sided_p_excess_coupling": 0.001},
        {"one_sided_bootstrap_sign_p": None},
        {"one_sided_bootstrap_sign_p": 0.01},
        {"one_sided_label_randomization_p": 0.01},
        alpha=0.05,
    )
    assert family["family_complete"] is False
    assert family["promotion_allowed"] is False
    assert not any(family["rejected_at_alpha"].values())


def test_local_hf_snapshot_preserves_immutable_revision_metadata(monkeypatch):
    revision = "b" * 40
    monkeypatch.setenv("ORCAP_ANALYSIS_SOURCE", "local")
    monkeypatch.setenv("ORCAP_HF_REVISION", revision)
    with data.pinned_analysis_source() as source:
        assert source["source"] == "huggingface_local_snapshot"
        assert source["repo_id"] == data.HF_DATASET_REPO
        assert source["revision"] == revision
        assert source["resolution"] == "caller_managed_local_snapshot"


def test_robustness_suite_emits_registered_negative_controls():
    changes, author = _price_events(days=60)
    split = wf18.chronological_split(changes.ts, calibration_fraction=0.25, mechanism_fraction=0.5)
    innovations, _ = wf18.prepare_quote_innovations(changes, author, split, ridge=1e-6)
    mechanism = innovations[innovations.period == "mechanism"].reset_index(drop=True)
    checks, summary = wf18.robustness_suite(
        mechanism,
        unanchored_innovations=mechanism,
        enforcement_windows=pd.DataFrame(),
        primary_window_hours=1,
        secondary_windows=[6, 24],
        permutations=19,
        seed=5,
    )
    names = set(checks["check"])
    assert "different_model_negative_control" in names
    assert "provider_a_leads" in names
    assert "fixed_daily_frequency" in names
    assert summary["provider_identity_shuffle_draws"] == 19
