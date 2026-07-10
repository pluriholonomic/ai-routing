import pandas as pd

from orcap.analysis.h64_openrouter_usage import coverage_gate, daily_panel, latest_revisions


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_ts": "20260703T000000Z",
                "source_date": "2026-07-01",
                "model_permaslug": "model/a",
                "total_tokens": 100,
                "is_other_aggregate": False,
            },
            {
                "run_ts": "20260704T000000Z",
                "source_date": "2026-07-01",
                "model_permaslug": "model/a",
                "total_tokens": 120,
                "is_other_aggregate": False,
            },
            {
                "run_ts": "20260703T000000Z",
                "source_date": "2026-07-01",
                "model_permaslug": "model/b",
                "total_tokens": 30,
                "is_other_aggregate": False,
            },
            {
                "run_ts": "20260703T000000Z",
                "source_date": "2026-07-01",
                "model_permaslug": "other",
                "total_tokens": 50,
                "is_other_aggregate": True,
            },
            {
                "run_ts": "20260703T000000Z",
                "source_date": "2026-07-02",
                "model_permaslug": "model/a",
                "total_tokens": 40,
                "is_other_aggregate": False,
            },
            {
                "run_ts": "20260703T000000Z",
                "source_date": "2026-07-02",
                "model_permaslug": "other",
                "total_tokens": 60,
                "is_other_aggregate": True,
            },
        ]
    )


def test_h64_retains_latest_revision_and_reports_source_defined_shares():
    revisions = latest_revisions(_rows())
    daily = daily_panel(revisions)

    assert len(revisions) == 5
    model_a = revisions.loc[
        revisions["source_date"].eq("2026-07-01") & revisions["model_permaslug"].eq("model/a")
    ].iloc[0]
    assert model_a["total_tokens"] == 120
    assert model_a["n_revisions"] == 2

    day_one = daily.loc[daily["source_date"].eq("2026-07-01")].iloc[0]
    assert day_one["total_tokens"] == 200
    assert day_one["source_reported_top50_model_tokens"] == 150
    assert day_one["source_reported_other_tokens"] == 50
    assert day_one["source_reported_top50_token_share"] == 0.75
    assert day_one["top1_model_token_share_total"] == 0.6
    assert bool(day_one["has_source_reported_other"])


def test_h64_gates_short_and_incomplete_history():
    gate = coverage_gate(daily_panel(latest_revisions(_rows())))

    assert gate["status"] == "power_gated"
    assert gate["source_days"] == 2
    assert gate["complete_source_days"] == 0
    assert "only 2/30 source days" in gate["gate_reasons"]


def test_h64_accepts_30_consecutive_complete_source_days():
    panel = pd.DataFrame(
        {
            "source_date": pd.date_range("2026-06-01", periods=30, freq="D").strftime("%Y-%m-%d"),
            "total_tokens": [100] * 30,
            "source_reported_top50_model_tokens": [80] * 30,
            "source_reported_other_tokens": [20] * 30,
            "source_reported_top50_token_share": [0.8] * 30,
            "source_reported_other_token_share": [0.2] * 30,
            "top1_model_token_share_total": [0.1] * 30,
            "top50_observed_models": [50] * 30,
            "has_source_reported_other": [True] * 30,
        }
    )

    gate = coverage_gate(panel)

    assert gate["status"] == "aggregate_demand_panel_ready"
    assert gate["complete_source_days"] == 30
