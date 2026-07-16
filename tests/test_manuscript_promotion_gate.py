import pandas as pd

from orcap.analysis.manuscript_promotion_gate import build_promotion_status


def _h80(counts, *, ready=False):
    return {
        "first_position_counts": counts,
        "target_per_policy": 500,
        "outcomes_released": ready,
        "assignment_replay_rate": 1.0,
        "confirmatory_cutoff": "cutoff" if ready else None,
        "outcome_access": (
            "released_confirmatory_prefix" if ready else "masked_by_500_per_arm_gate"
        ),
        "accrual_projection": {"forecast_boundary": "assignment only"},
    }


def test_promotion_status_keeps_incomplete_gates_closed():
    dates = pd.date_range("2026-07-07", periods=10, freq="D")
    status = build_promotion_status(
        dates,
        _h80(
            {
                "openrouter_default": 15,
                "pinned_cheapest": 20,
                "pinned_second": 19,
                "pinned_random": 22,
            }
        ),
    )

    assert status["evidence_status"] == "accruing"
    assert status["all_promotion_gates_ready"] is False
    assert status["quote_panel_gate"]["observed_distinct_days"] == 10
    assert status["quote_panel_gate"]["remaining_distinct_days"] == 20
    assert status["quote_panel_gate"]["frozen_vintage"]["days"] == [
        f"2026-07-{day:02d}" for day in range(7, 16)
    ]
    assert status["quote_panel_gate"]["confirmatory_vintage"]["days"] == []
    assert status["h80_first_position_gate"]["min_count"] == 15
    assert status["h80_first_position_gate"]["remaining_by_policy"][
        "openrouter_default"
    ] == 485


def test_promotion_status_freezes_earliest_30_day_prefix():
    dates = pd.date_range("2026-07-07", periods=35, freq="D")
    counts = {
        "openrouter_default": 503,
        "pinned_cheapest": 501,
        "pinned_second": 500,
        "pinned_random": 506,
    }
    status = build_promotion_status(dates, _h80(counts, ready=True))

    assert status["evidence_status"] == "confirmatory_release_ready"
    assert status["all_promotion_gates_ready"] is True
    assert len(status["quote_panel_gate"]["confirmatory_vintage"]["days"]) == 30
    assert status["quote_panel_gate"]["confirmatory_vintage"]["end"] == "2026-08-05"
    assert status["h80_first_position_gate"]["confirmatory_cutoff"] == "cutoff"
