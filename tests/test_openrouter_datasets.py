import asyncio

from orcap.capture_openrouter_datasets import (
    capture_openrouter_rankings_daily,
    rankings_daily_rows,
)


def _body():
    return {
        "data": [
            {"date": "2026-07-01", "model_permaslug": "model/a", "total_tokens": 100},
            {"date": "2026-07-01", "model_permaslug": "model/b", "total_tokens": "40"},
            {"date": "2026-07-01", "model_permaslug": "other", "total_tokens": 60},
            {"date": "2026-07-02", "model_permaslug": "model/a", "total_tokens": 120},
            {"date": "2026-07-02", "model_permaslug": "other", "total_tokens": 80},
        ],
        "meta": {
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
            "as_of": "2026-07-03T00:00:00Z",
            "version": "v1",
        },
    }


def test_rankings_daily_rows_preserves_aggregate_contract_and_provenance():
    rows, detail = rankings_daily_rows(
        _body(),
        "20260703T000000Z",
        "2026-07-03",
        requested_start_date="2026-07-01",
        requested_end_date="2026-07-02",
    )

    assert detail["coverage_complete"] is True
    assert detail["source_dates"] == 2
    assert detail["other_rows"] == 2
    assert len(rows) == 5
    assert rows[0]["source"] == "openrouter_rankings_daily"
    assert rows[0]["requested_start_date"] == "2026-07-01"
    assert rows[0]["api_version"] == "v1"
    assert rows[2]["is_other_aggregate"] is True
    assert "not provider allocation" in rows[0]["metric_definition"]


def test_rankings_daily_rows_fail_closed_for_invalid_or_incomplete_source_days():
    duplicate = _body()
    duplicate["data"].append(
        {"date": "2026-07-01", "model_permaslug": "model/a", "total_tokens": 1}
    )
    rows, detail = rankings_daily_rows(duplicate, "20260703T000000Z", "2026-07-03")
    assert rows == []
    assert detail["reason"] == "duplicate_model_day"

    no_other = _body()
    no_other["data"] = [row for row in no_other["data"] if row["model_permaslug"] != "other"]
    rows, detail = rankings_daily_rows(no_other, "20260703T000000Z", "2026-07-03")
    assert rows == []
    assert detail["reason"] == "missing_or_duplicate_other_row"


def test_rankings_daily_capture_skips_without_a_configured_credential(monkeypatch, tmp_path):
    monkeypatch.delenv("ORCAP_OPENROUTER_DATASET_API_KEY", raising=False)

    result = asyncio.run(
        capture_openrouter_rankings_daily(
            raw_dir=tmp_path / "raw",
            curated_dir=tmp_path / "curated",
        )
    )

    assert result["source_status"] == "skipped"
    assert result["rows"] == 0
    assert not (tmp_path / "raw").exists()
    assert list((tmp_path / "curated" / "source_runs").rglob("*.parquet"))
