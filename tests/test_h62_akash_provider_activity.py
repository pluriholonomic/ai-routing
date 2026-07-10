import pandas as pd

from orcap.analysis.h62_akash_provider_activity import (
    coverage_gate,
    daily_provider_panel,
    latest_provider_history,
)


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T010000Z",
                "provider_id": "provider-a",
                "observation_type": "source_reported_provider_history",
                "source_bucket_at": "2026-07-09T00:00:00Z",
                "metric": "source_reported_provider_active_lease_count_history",
                "value": 2,
            },
            {
                "run_ts": "20260710T020000Z",
                "provider_id": "provider-a",
                "observation_type": "source_reported_provider_history",
                "source_bucket_at": "2026-07-09T00:00:00Z",
                "metric": "source_reported_provider_active_lease_count_history",
                "value": 3,
            },
            {
                "run_ts": "20260710T020000Z",
                "provider_id": "provider-b",
                "observation_type": "source_reported_provider_history",
                "source_bucket_at": "2026-07-09T12:00:00Z",
                "metric": "source_reported_provider_active_lease_count_history",
                "value": 1,
            },
            {
                "run_ts": "20260710T020000Z",
                "provider_id": "provider-a",
                "observation_type": "source_reported_provider_snapshot",
                "source_bucket_at": None,
                "metric": "source_reported_provider_current_active_gpu_count",
                "value": 4,
            },
        ]
    )


def test_h62_keeps_latest_provider_history_revision_and_uses_one_point_per_day():
    history = latest_provider_history(_rows())
    daily = daily_provider_panel(history)

    assert len(history) == 2
    assert history.loc[history["provider_id"].eq("provider-a"), "active_leases"].iat[0] == 3
    assert history.loc[history["provider_id"].eq("provider-a"), "n_revisions"].iat[0] == 2
    assert len(daily) == 1
    assert daily["providers_observed"].iat[0] == 2
    assert daily["total_source_reported_active_leases"].iat[0] == 4.0
    assert daily["top_provider_lease_share"].iat[0] == 0.75
    assert daily["provider_lease_hhi"].iat[0] == 0.625


def test_h62_gates_short_history_without_claiming_provider_activity_is_demand():
    history = latest_provider_history(_rows())
    gate = coverage_gate(history, daily_provider_panel(history))

    assert gate["status"] == "power_gated"
    assert gate["source_history_days"] == 1
    assert gate["providers_observed"] == 2
