import pandas as pd

from orcap.analysis.h59_nosana_job_activity import (
    coverage_gate,
    latest_bucket_panel,
    running_market_panel,
)


def _rows():
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_completed_job_count_bucket",
                "value": 10,
                "observation_type": "rolling_bucket",
                "source_bucket_unix_ms": 1_783_678_200_000,
                "source_total": 10,
                "requested_period_seconds": 86_400,
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_completed_job_count_bucket",
                "value": 12,
                "observation_type": "rolling_bucket",
                "source_bucket_unix_ms": 1_783_678_200_000,
                "source_total": 12,
                "requested_period_seconds": 86_400,
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_job_duration_hours_bucket",
                "value": 4.5,
                "observation_type": "rolling_bucket",
                "source_bucket_unix_ms": 1_783_678_200_000,
                "source_total": 4.5,
                "requested_period_seconds": 86_400,
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_running_jobs_by_market",
                "value": 3,
                "observation_type": "market_snapshot",
                "market_id": "market-a",
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_running_jobs_by_market",
                "value": 1,
                "observation_type": "market_snapshot",
                "market_id": "market-b",
            },
        ]
    )


def test_h59_keeps_only_latest_revision_of_each_public_source_bucket():
    panel = latest_bucket_panel(_rows())
    jobs = panel.loc[panel["metric"].eq("source_reported_completed_job_count_bucket")]
    assert len(jobs) == 1
    assert jobs["value"].iat[0] == 12
    assert jobs["n_revisions"].iat[0] == 2
    assert coverage_gate(panel)["status"] == "power_gated"


def test_h59_running_market_panel_is_a_public_activity_concentration_not_capacity():
    panel = running_market_panel(_rows())
    assert panel["running_jobs"].iat[0] == 4
    assert panel["n_markets"].iat[0] == 2
    assert panel["top_market_running_share"].iat[0] == 0.75
    assert panel["running_job_hhi"].iat[0] == 0.625
