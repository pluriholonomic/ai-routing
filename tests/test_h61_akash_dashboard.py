import pandas as pd

from orcap.analysis.h61_akash_dashboard import coverage_gate, latest_metrics, snapshot_panel


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T120000Z",
                "dt": "2026-07-10",
                "source_observed_at": "2026-07-10T12:00:00Z",
                "source_block_height": 101,
                "metric": "source_reported_active_lease_count",
                "source_reported_unit": "leases",
                "value": 10.0,
            },
            {
                "run_ts": "20260710T120000Z",
                "dt": "2026-07-10",
                "source_observed_at": "2026-07-10T12:00:00Z",
                "source_block_height": 101,
                "metric": "source_reported_dashboard_active_gpu_count",
                "source_reported_unit": "gpus",
                "value": 20.0,
            },
            {
                "run_ts": "20260710T120000Z",
                "dt": "2026-07-10",
                "source_observed_at": "2026-07-10T12:00:00Z",
                "source_block_height": 101,
                "metric": "source_reported_network_gpu_available",
                "source_reported_unit": "gpus",
                "value": 30.0,
            },
            {
                "run_ts": "20260710T120000Z",
                "dt": "2026-07-10",
                "source_observed_at": "2026-07-10T12:00:00Z",
                "source_block_height": 101,
                "metric": "source_reported_source_day_uusdc_spent",
                "source_reported_unit": "uusdc",
                "value": 40.0,
            },
            {
                "run_ts": "20260710T121000Z",
                "dt": "2026-07-10",
                "source_observed_at": "2026-07-10T12:00:00Z",
                "source_block_height": 101,
                "metric": "source_reported_active_lease_count",
                "source_reported_unit": "leases",
                "value": 11.0,
            },
        ]
    )


def test_h61_keeps_the_latest_capture_of_each_source_timestamp_metric():
    panel = snapshot_panel(_rows())

    assert len(panel) == 4
    leases = panel.loc[panel["metric"].eq("source_reported_active_lease_count")].iloc[0]
    assert leases["value"] == 11.0
    latest = latest_metrics(panel)
    assert latest["source_reported_network_gpu_available"]["value"] == 30.0
    assert latest["source_reported_network_gpu_available"]["unit"] == "gpus"


def test_h61_gates_a_single_source_snapshot_and_preserves_aggregate_boundary():
    gate = coverage_gate(snapshot_panel(_rows()))

    assert gate["status"] == "power_gated"
    assert gate["source_observation_days"] == 1
    assert gate["source_snapshots"] == 1
    assert gate["core_metrics_present"] == [
        "source_reported_active_lease_count",
        "source_reported_dashboard_active_gpu_count",
        "source_reported_network_gpu_available",
        "source_reported_source_day_uusdc_spent",
    ]
