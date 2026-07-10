import pandas as pd
import pytest

from orcap.analysis.h51_livepeer_gateway import decision_panel, summarize, switch_response


def _rows():
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "region": "fra",
                "rolling_window_minutes": 5,
                "swap_events": 2,
                "reuse_events": 8,
                "inflight_reuse_events": 7,
            },
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "region": "nyc",
                "rolling_window_minutes": 5,
                "swap_events": 4,
                "reuse_events": 6,
                "inflight_reuse_events": 99,
            },
            {
                "run_ts": "20260710T000500Z",
                "dt": "2026-07-10",
                "region": "fra",
                "rolling_window_minutes": 5,
                "swap_events": 3,
                "reuse_events": 7,
                "inflight_reuse_events": 2,
            },
            {
                "run_ts": "20260710T000500Z",
                "dt": "2026-07-10",
                "region": "nyc",
                "rolling_window_minutes": 5,
                "swap_events": 5,
                "reuse_events": 5,
                "inflight_reuse_events": 1,
            },
        ]
    )


def test_h51_decision_panel_bounds_inflight_count_and_builds_shares():
    panel = decision_panel(_rows()).set_index(["run_ts", "region"])
    assert panel.loc[("20260710T000000Z", "fra"), "switch_share"] == pytest.approx(0.2)
    assert panel.loc[("20260710T000000Z", "nyc"), "inflight_reuse_share"] == 1.0


def test_h51_short_panel_is_power_gated_and_not_openrouter_evidence():
    summary = summarize(decision_panel(_rows()))
    assert summary["evidence_status"] == "power_gated"
    assert "OpenRouter evidence" in summary["claim_boundary"]


def test_h51_response_uses_snapshot_clustered_external_control_specification():
    response = switch_response(decision_panel(_rows()))
    assert response is None
    repeated = pd.concat([_rows()] * 3, ignore_index=True)
    repeated["run_ts"] = [
        f"20260710T{i:06d}Z" for i in range(len(repeated))
    ]
    response = switch_response(decision_panel(repeated))
    assert response is not None
    assert response["n_snapshot_clusters"] == len(repeated)
