import pandas as pd

from orcap.analysis import wcv4_policy_evaluation as wcv4


def test_wcv4_excludes_power_gated_study_outcomes(monkeypatch, tmp_path):
    frame = pd.DataFrame(
        [
            {
                "source": "openrouter_generation",
                "event_id": "legacy",
                "run_ts": "20260715T000000Z",
                "study_id": "openrouter-default-probes-v1",
                "policy": "legacy_policy",
                "outcome": "succeeded",
                "selected_provider": "Provider",
                "cost_usd": 0.01,
                "latency_ms": 100,
                "fallback_triggered": False,
            },
            {
                "source": "openrouter_generation",
                "event_id": "h80",
                "run_ts": "20260715T010000Z",
                "study_id": "openrouter-routing-crossover-v2",
                "policy": "pinned_cheapest",
                "outcome": "failed",
                "selected_provider": None,
                "cost_usd": None,
                "latency_ms": None,
                "fallback_triggered": False,
            },
            {
                "source": "openrouter_generation",
                "event_id": "h81",
                "run_ts": "20260715T020000Z",
                "study_id": "openrouter-fallback-selection-decomposition-v1",
                "policy": "delegated_default",
                "outcome": "succeeded",
                "selected_provider": "Provider",
                "cost_usd": 0.02,
                "latency_ms": 200,
                "fallback_triggered": False,
            },
            {
                "source": "openrouter_generation",
                "event_id": "h87",
                "run_ts": "20260715T030000Z",
                "study_id": "openrouter-capacity-policy-v1",
                "policy": "capacity_safe",
                "outcome": "succeeded",
                "selected_provider": "Provider",
                "cost_usd": 0.03,
                "latency_ms": 300,
                "fallback_triggered": False,
            },
            {
                "source": "openrouter_generation",
                "event_id": "h88",
                "run_ts": "20260715T040000Z",
                "study_id": "openrouter-enforcement-policy-v1",
                "policy": "enforcement_safe",
                "outcome": "failed",
                "selected_provider": None,
                "cost_usd": None,
                "latency_ms": None,
                "fallback_triggered": False,
            },
        ]
    )
    monkeypatch.setattr(wcv4, "load_attempts", lambda: frame)

    summary = wcv4.run(tmp_path)

    assert summary["attempts"] == 1
    assert summary["outcome_blinded_attempts_excluded"] == 4
    assert summary["policies_observed"] == 1
    assert [row["policy"] for row in summary["policy_panel"]] == ["legacy_policy"]
