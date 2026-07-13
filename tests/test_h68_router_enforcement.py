"""Synthetic coverage for public router-enforcement event construction."""

import pandas as pd

from orcap.analysis.h68_router_enforcement import (
    derank_events,
    derank_hazard,
    enforcement_panel,
    rate_limit_events,
    summarize,
)


def _row(run_ts, deranked, rate_limited, success):
    return {
        "run_ts": run_ts,
        "dt": "2026-07-10",
        "model_permaslug": "model-v1",
        "endpoint_uuid": "endpoint-a",
        "provider_name": "provider-a",
        "source": "congestion_intraday",
        "success_5m": success,
        "rate_limited_5m": rate_limited,
        "derankable_error_30m": 0,
        "request_count_30m": success + rate_limited,
        "capacity_ceiling_rpm": 100,
        "recent_peak_rpm": 50,
        "is_deranked": deranked,
    }


def test_h68_detects_contiguous_derank_and_rate_limit_transitions():
    rows = pd.DataFrame(
        [
            _row("20260710T000000Z", False, 0, 10),
            _row("20260710T000500Z", True, 4, 6),
            _row("20260710T001000Z", True, 2, 8),
            _row("20260710T001500Z", False, 0, 10),
        ]
    )
    panel = enforcement_panel(rows)

    onset = panel.iloc[1]
    assert onset["derank_onset"]
    assert onset["rate_limit_onset"]
    assert onset["rate_limit_share_5m"] == 0.4
    assert panel.iloc[3]["derank_release"]

    events = derank_events(panel)
    assert set(events["event_type"]) == {"derank_onset", "derank_release"}
    assert len(rate_limit_events(panel)) == 1


def test_h68_keeps_hazard_unidentified_without_a_derank_transition():
    rows = pd.DataFrame(
        [
            _row("20260710T000000Z", False, 0, 10),
            _row("20260710T000500Z", False, 1, 9),
            _row("20260710T001000Z", False, 0, 10),
        ]
    )
    panel = enforcement_panel(rows)
    hazard = derank_hazard(panel)
    summary = summarize(panel, hazard)

    assert len(rate_limit_events(panel)) == 1
    assert derank_events(panel).empty
    assert summary["evidence_status"] == "descriptive_incidence_no_observed_derank_transition"
    assert summary["n_derank_onsets"] == 0
    assert "not identified" in summary["hazard_interpretation"]
