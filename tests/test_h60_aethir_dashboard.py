import pandas as pd

from orcap.analysis.h60_aethir_dashboard import coverage_gate, latest_monthly_panel, snapshot_panel


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_monthly_network_revenue_usd",
                "source_reported_unit": "usd",
                "value": 10.0,
                "observation_type": "source_reported_time_bucket",
                "source_bucket_period": "monthly",
                "source_bucket_label": "June, 2026",
                "source_bucket_unix_ms": None,
            },
            {
                "run_ts": "20260710T020000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_monthly_network_revenue_usd",
                "source_reported_unit": "usd",
                "value": 11.0,
                "observation_type": "source_reported_time_bucket",
                "source_bucket_period": "monthly",
                "source_bucket_label": "June, 2026",
                "source_bucket_unix_ms": None,
            },
            {
                "run_ts": "20260710T020000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_monthly_cloud_host_rewards_ath",
                "source_reported_unit": "ath",
                "value": 4.0,
                "observation_type": "source_reported_time_bucket",
                "source_bucket_period": "monthly",
                "source_bucket_label": "June, 2026",
                "source_bucket_unix_ms": 1_780_272_000_000,
            },
            {
                "run_ts": "20260710T020000Z",
                "dt": "2026-07-10",
                "metric": "source_reported_total_gpu_containers",
                "source_reported_unit": "containers",
                "value": 435_114.0,
                "observation_type": "aggregate_snapshot",
                "source_bucket_period": None,
                "source_bucket_label": None,
                "source_bucket_unix_ms": None,
            },
        ]
    )


def test_h60_keeps_latest_source_revision_and_uses_literal_month_labels():
    panel = latest_monthly_panel(_rows())

    revenue = panel.loc[
        panel["metric"].eq("source_reported_monthly_network_revenue_usd")
    ].iloc[0]
    assert revenue["value"] == 11.0
    assert revenue["n_revisions"] == 2
    assert revenue["source_bucket_label"] == "June, 2026"
    assert str(revenue["source_bucket_time"].date()) == "2026-06-01"


def test_h60_snapshot_panel_remains_an_aggregate_dashboard_panel():
    panel = snapshot_panel(_rows())

    assert len(panel) == 1
    assert panel.iloc[0]["metric"] == "source_reported_total_gpu_containers"
    assert panel.iloc[0]["source_reported_unit"] == "containers"


def test_h60_power_gates_partial_source_history():
    gate = coverage_gate(latest_monthly_panel(_rows()))

    assert gate["status"] == "power_gated"
    assert gate["monthly_points_by_metric"]["source_reported_monthly_network_revenue_usd"] == 1
