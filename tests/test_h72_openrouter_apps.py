import pandas as pd

from orcap.analysis.h72_openrouter_apps import coverage_gate, daily_panel, latest_revisions


def _rows(days=1, apps=3):
    rows = []
    for day in pd.date_range("2026-01-01", periods=days, freq="D"):
        for rank in range(1, apps + 1):
            rows.append(
                {
                    "run_ts": "20260702T030000Z",
                    "source_date": day.strftime("%Y-%m-%d"),
                    "app_id": str(rank),
                    "app_name": f"App {rank}",
                    "rank": rank,
                    "total_requests": 100 // rank,
                    "total_tokens": 1000 // rank,
                    "ranking_sort": "popular",
                    "category": None,
                    "subcategory": None,
                    "is_public_attributed_only": True,
                    "is_top_n_censored": True,
                }
            )
    return pd.DataFrame(rows)


def test_h72_keeps_latest_revision_and_reports_visible_concentration():
    rows = _rows()
    revision = rows.iloc[0].copy()
    revision["run_ts"] = "20260703T030000Z"
    revision["total_requests"] = 120
    revision["total_tokens"] = 1200
    rows = pd.concat([rows, pd.DataFrame([revision])], ignore_index=True)

    latest = latest_revisions(rows)
    daily = daily_panel(latest)

    assert len(latest) == 3
    assert latest.loc[latest["app_id"].eq("1"), "n_revisions"].iloc[0] == 2
    assert daily.iloc[0]["visible_apps"] == 3
    assert daily.iloc[0]["visible_total_requests"] == 120 + 50 + 33
    assert 0 < daily.iloc[0]["request_hhi_visible"] < 1
    assert bool(daily.iloc[0]["is_top_n_censored"])


def test_h72_requires_ninety_consecutive_well_covered_days():
    short = coverage_gate(daily_panel(latest_revisions(_rows(days=2, apps=50))))
    assert short["status"] == "power_gated"
    assert "only 2/90 public-app source days" in short["gate_reasons"]

    ready = coverage_gate(daily_panel(latest_revisions(_rows(days=90, apps=50))))
    assert ready["status"] == "public_app_panel_ready"
    assert ready["complete_source_days"] == 90
