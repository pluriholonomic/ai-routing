import pandas as pd
import pytest

from orcap.analysis.h53_chutes_invocations import invocation_panel, summarize


def _rows():
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "participant_id": "a",
                "resource_id": "model-a",
                "cumulative_invocations": 100,
                "active_configured_gpus": 2,
                "configured_concurrency": 8,
                "estimated_deployment_usd_hour": 3,
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "participant_id": "a",
                "resource_id": "model-a",
                "cumulative_invocations": 130,
                "active_configured_gpus": 2,
                "configured_concurrency": 8,
                "estimated_deployment_usd_hour": 3,
            },
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "participant_id": "b",
                "resource_id": "model-b",
                "cumulative_invocations": 50,
                "active_configured_gpus": 1,
                "configured_concurrency": 4,
                "estimated_deployment_usd_hour": 2,
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "participant_id": "b",
                "resource_id": "model-b",
                "cumulative_invocations": 70,
                "active_configured_gpus": 1,
                "configured_concurrency": 4,
                "estimated_deployment_usd_hour": 2,
            },
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "participant_id": "reset",
                "resource_id": "model-reset",
                "cumulative_invocations": 10,
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "participant_id": "reset",
                "resource_id": "model-reset",
                "cumulative_invocations": 2,
            },
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "participant_id": "gap",
                "resource_id": "model-gap",
                "cumulative_invocations": 10,
            },
            {
                "run_ts": "20260710T060000Z",
                "dt": "2026-07-10",
                "participant_id": "gap",
                "resource_id": "model-gap",
                "cumulative_invocations": 70,
            },
        ]
    )


def test_h53_differences_only_adjacent_monotone_counters():
    panel, diagnostics = invocation_panel(_rows())
    assert set(panel["participant_id"]) == {"a", "b"}
    assert panel.loc[panel["participant_id"] == "a", "delta_invocations"].iat[0] == 30
    assert panel.loc[
        panel["participant_id"] == "a", "invocations_per_active_configured_gpu_hour"
    ].iat[0] == pytest.approx(15)
    assert diagnostics == {"counter_resets": 1, "interval_rejections": 1}


def test_h53_short_panel_is_power_gated_and_preserves_consumption_boundary():
    panel, diagnostics = invocation_panel(_rows())
    result = summarize(panel, diagnostics)
    assert result["evidence_status"] == "power_gated"
    assert result["n_valid_deltas"] == 2
    assert "not a count of successful completions" in result["claim_boundary"]
