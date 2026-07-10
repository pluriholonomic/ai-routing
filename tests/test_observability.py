from datetime import UTC, datetime, timedelta

from orcap.observability import write_source_run
from orcap.quality import check


def test_required_missing_source_is_red(tmp_path):
    result = check("core", curated_dir=tmp_path, now=datetime(2026, 7, 9, tzinfo=UTC))
    assert result["overall"] == "red"


def test_optional_degradation_is_visible_but_not_red(tmp_path):
    now = datetime(2026, 7, 9, tzinfo=UTC)
    for source in ("openrouter_api", "openrouter_frontend", "vast", "defillama"):
        write_source_run(
            source,
            status="success",
            rows=1,
            run_ts="20260709T000000Z",
            dt="2026-07-09",
            curated_dir=tmp_path,
        )
    write_source_run(
        "cow",
        status="skipped",
        run_ts="20260709T000000Z",
        dt="2026-07-09",
        curated_dir=tmp_path,
    )
    result = check("comparison", curated_dir=tmp_path, now=now)
    assert result["overall"] == "yellow"
    assert next(x for x in result["sources"] if x["source"] == "cow")["state"] == "yellow"


def test_stale_required_source_is_red(tmp_path):
    now = datetime(2026, 7, 9, tzinfo=UTC)
    for source in ("openrouter_api", "openrouter_frontend", "vast"):
        write_source_run(
            source,
            status="success",
            rows=1,
            run_ts="20260701T000000Z",
            dt="2026-07-01",
            curated_dir=tmp_path,
        )
    result = check("core", curated_dir=tmp_path, now=now + timedelta(days=1))
    assert result["overall"] == "red"
