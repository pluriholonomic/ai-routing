import pandas as pd

from orcap.analysis import h69_experiment_readiness as h69
from orcap.analysis.h69_experiment_readiness import (
    _nonempty_count,
    quote_metrics,
    readiness_rows,
    telemetry_metrics,
)


def _gates():
    return {
        "quote_pulse": {
            "min_continuous_span_hours": 1,
            "min_independent_cut_episodes": 1,
        },
        "router_enforcement": {"min_derank_onsets": 1},
        "realized_routing": {
            "min_selected_attempts": 2,
            "min_quote_linked_attempts": 1,
            "min_stale_quote_episodes": 1,
        },
        "residual_flow": {"min_complete_days": 2, "min_repricing_episodes": 1},
        "preselection_access": {"min_events_per_randomized_arm": 1},
        "comparators": {"min_complete_days_per_venue": 1, "min_allocation_events_per_venue": 1},
    }


def test_h69_counts_contiguous_quote_cuts_and_reports_each_gate():
    rows = pd.DataFrame(
        [
            {
                "run_ts": "20260712T000000Z",
                "model_id": "m",
                "provider_name": "a",
                "scenario": "short_chat",
                "expected_quote_usd": 2.0,
                "simulated_route_share": 0.3,
                "surface_source": "synthetic",
            },
            {
                "run_ts": "20260712T000500Z",
                "model_id": "m",
                "provider_name": "a",
                "scenario": "short_chat",
                "expected_quote_usd": 1.0,
                "simulated_route_share": 0.6,
                "surface_source": "synthetic",
            },
            {
                "run_ts": "20260712T010000Z",
                "model_id": "m",
                "provider_name": "a",
                "scenario": "short_chat",
                "expected_quote_usd": 1.0,
                "simulated_route_share": 0.6,
                "surface_source": "synthetic",
            },
            {
                "run_ts": "20260712T000000Z",
                "model_id": "m",
                "provider_name": "b",
                "scenario": "short_chat",
                "expected_quote_usd": 1.0,
                "simulated_route_share": 0.7,
                "surface_source": "synthetic",
            },
            {
                "run_ts": "20260712T000500Z",
                "model_id": "m",
                "provider_name": "b",
                "scenario": "short_chat",
                "expected_quote_usd": 1.0,
                "simulated_route_share": 0.4,
                "surface_source": "synthetic",
            },
            {
                "run_ts": "20260712T010000Z",
                "model_id": "m",
                "provider_name": "b",
                "scenario": "short_chat",
                "expected_quote_usd": 1.0,
                "simulated_route_share": 0.4,
                "surface_source": "synthetic",
            },
        ]
    )
    gates = _gates()
    quote = quote_metrics(rows)
    assert quote["independent_cuts"] == 1
    assert quote["span_hours"] == 1.0
    ledger = readiness_rows(
        quote,
        enforcement_onsets=1,
        telemetry={
            "selected_attempts": 2,
            "quote_linked_attempts": 1,
            "decision_events": 3,
            "visible_arm_events": 1,
            "blinded_arm_events": 1,
            "decoy_arm_events": 1,
            "aggregate_days": 2,
            "repricing_episodes": 1,
        },
        comparator_complete_days=1,
        gates=gates,
    )
    assert set(ledger["status"]) == {"ready"}


def test_h69_nonempty_count_normalizes_nullable_integer_identifiers():
    rows = pd.DataFrame({"quote_snapshot_id": pd.Series([1, None, 2], dtype="Int32")})

    assert _nonempty_count(rows, "quote_snapshot_id") == 2


def test_h69_readiness_counts_exclude_gated_study_outcomes(monkeypatch):
    attempts = pd.DataFrame(
        [
            {
                "study_id": "openrouter-default-probes-v1",
                "selected_provider": "provider-a",
                "quote_snapshot_id": "quote-a",
            },
            {
                "study_id": "openrouter-enforcement-policy-v1",
                "selected_provider": "provider-b",
                "quote_snapshot_id": "quote-b",
            },
        ]
    )

    monkeypatch.setattr(
        h69,
        "_load_table",
        lambda table: attempts if table == "router_route_attempts" else pd.DataFrame(),
    )

    metrics = telemetry_metrics()

    assert metrics["selected_attempts"] == 1
    assert metrics["quote_linked_attempts"] == 1
