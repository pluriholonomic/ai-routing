import asyncio
from contextlib import asynccontextmanager

import orcap.capture_openrouter_datasets as datasets
from orcap.capture_openrouter_datasets import (
    app_rankings_page_rows,
    capture_openrouter_app_rankings_daily,
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
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

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


def _app_body(*, rows=2, source_date="2026-07-01", start_rank=1):
    return {
        "data": [
            {
                "app_id": index,
                "app_name": f"App {index}",
                "rank": index,
                "total_requests": 1000 - index,
                "total_tokens": str(10_000 - index),
            }
            for index in range(start_rank, start_rank + rows)
        ],
        "meta": {
            "start_date": source_date,
            "end_date": source_date,
            "as_of": "2026-07-02T02:00:00Z",
            "version": "v1",
        },
    }


def test_app_rankings_rows_preserve_public_top_n_and_scope_boundaries():
    rows, detail = app_rankings_page_rows(
        _app_body(),
        "20260702T030000Z",
        "2026-07-02",
        requested_date="2026-07-01",
        sort="popular",
        category=None,
        subcategory=None,
        offset=0,
    )

    assert detail["coverage_complete"] is True
    assert len(rows) == 2
    assert rows[0]["source"] == "openrouter_app_rankings_daily"
    assert rows[0]["source_date"] == "2026-07-01"
    assert rows[0]["app_id"] == "1"
    assert rows[0]["total_tokens"] == 9999
    assert rows[0]["is_public_attributed_only"] is True
    assert rows[0]["is_top_n_censored"] is True
    assert "not an app-by-model" in rows[0]["metric_definition"]


def test_app_rankings_rows_fail_closed_on_date_or_page_rank_mismatch():
    rows, detail = app_rankings_page_rows(
        _app_body(source_date="2026-07-02"),
        "run",
        "dt",
        requested_date="2026-07-01",
        sort="popular",
        category=None,
        subcategory=None,
        offset=0,
    )
    assert rows == []
    assert detail["reason"] == "resolved_date_mismatch"

    rows, detail = app_rankings_page_rows(
        _app_body(start_rank=1),
        "run",
        "dt",
        requested_date="2026-07-01",
        sort="popular",
        category=None,
        subcategory=None,
        offset=100,
    )
    assert rows == []
    assert detail["reason"] == "rank_outside_page"


def test_app_rankings_capture_skips_without_credential(monkeypatch, tmp_path):
    monkeypatch.delenv("ORCAP_OPENROUTER_DATASET_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = asyncio.run(
        capture_openrouter_app_rankings_daily(
            start_date="2026-07-01",
            end_date="2026-07-01",
            raw_dir=tmp_path / "raw",
            curated_dir=tmp_path / "curated",
        )
    )

    assert result["source_status"] == "skipped"
    assert result["rows"] == 0
    assert not (tmp_path / "raw").exists()
    assert list((tmp_path / "curated" / "source_runs").rglob("*.parquet"))


def test_app_rankings_capture_retains_completed_days_before_degraded_page(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-token")

    @asynccontextmanager
    async def fake_client():
        yield object()

    class FakeFetcher:
        def __init__(self, client, rps):
            assert rps == datasets.APP_REQUESTS_PER_SECOND
            self.records = []
            self.responses = [_app_body(source_date="2026-07-01"), None, None, None]

        async def get_json(self, url, headers=None):
            return self.responses.pop(0)

    monkeypatch.setattr(datasets, "make_client", fake_client)
    monkeypatch.setattr(datasets, "Fetcher", FakeFetcher)

    result = asyncio.run(
        capture_openrouter_app_rankings_daily(
            start_date="2026-07-01",
            end_date="2026-07-02",
            raw_dir=tmp_path / "raw",
            curated_dir=tmp_path / "curated",
        )
    )

    assert result["source_status"] == "degraded"
    assert result["rows"] == 2
    assert result["complete_source_days"] == 1
    assert result["failed_detail"]["source_date"] == "2026-07-02"
    assert list(
        (tmp_path / "curated" / "openrouter_app_rankings_daily").rglob("*.parquet")
    )


def test_app_rankings_capture_retries_transient_invalid_page(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-token")

    @asynccontextmanager
    async def fake_client():
        yield object()

    class FakeFetcher:
        def __init__(self, client, rps):
            assert rps == datasets.APP_REQUESTS_PER_SECOND
            self.records = []
            self.responses = [None, _app_body()]

        async def get_json(self, url, headers=None):
            return self.responses.pop(0)

    monkeypatch.setattr(datasets, "make_client", fake_client)
    monkeypatch.setattr(datasets, "Fetcher", FakeFetcher)

    result = asyncio.run(
        capture_openrouter_app_rankings_daily(
            start_date="2026-07-01",
            end_date="2026-07-01",
            raw_dir=tmp_path / "raw",
            curated_dir=tmp_path / "curated",
        )
    )

    assert result["source_status"] == "success"
    assert result["rows"] == 2
    assert result["complete_source_days"] == 1
    assert result["page_requests"] == 2


def test_app_rankings_capture_does_not_count_partial_two_page_day(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-token")

    @asynccontextmanager
    async def fake_client():
        yield object()

    class FakeFetcher:
        def __init__(self, client, rps):
            assert rps == datasets.APP_REQUESTS_PER_SECOND
            self.records = []
            self.responses = [_app_body(rows=100), None, None, None]

        async def get_json(self, url, headers=None):
            return self.responses.pop(0)

    monkeypatch.setattr(datasets, "make_client", fake_client)
    monkeypatch.setattr(datasets, "Fetcher", FakeFetcher)

    result = asyncio.run(
        capture_openrouter_app_rankings_daily(
            start_date="2026-07-01",
            end_date="2026-07-01",
            raw_dir=tmp_path / "raw",
            curated_dir=tmp_path / "curated",
        )
    )

    assert result["source_status"] == "degraded"
    assert result["rows"] == 100
    assert result["complete_source_days"] == 0
    assert result["failed_detail"]["page_offset"] == 100
    assert result["failed_detail"]["attempts"] == datasets.APP_PAGE_ATTEMPTS
