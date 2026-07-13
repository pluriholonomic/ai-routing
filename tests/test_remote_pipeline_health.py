from datetime import UTC, datetime, timedelta

from orcap.remote_health import evaluate_workflow

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _run(*, minutes_ago, status="completed", conclusion="success"):
    return {
        "id": 1,
        "created_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "status": status,
        "conclusion": conclusion,
        "html_url": "https://github.example/run/1",
    }


def test_remote_health_accepts_recent_success_or_active_run():
    success = evaluate_workflow("capture.yml", [_run(minutes_ago=60)], now=NOW, max_age_minutes=150)
    active = evaluate_workflow(
        "capture.yml",
        [_run(minutes_ago=20, status="in_progress", conclusion=None)],
        now=NOW,
        max_age_minutes=150,
    )
    assert success["healthy"] is True
    assert active["healthy"] is True


def test_remote_health_rejects_latest_failure_even_if_previous_run_succeeded():
    result = evaluate_workflow(
        "capture.yml",
        [_run(minutes_ago=80), _run(minutes_ago=20, conclusion="failure")],
        now=NOW,
        max_age_minutes=150,
    )
    assert result["healthy"] is False
    assert "failure" in result["reason"]


def test_remote_health_rejects_stale_success():
    result = evaluate_workflow(
        "capture.yml", [_run(minutes_ago=151)], now=NOW, max_age_minutes=150
    )
    assert result["healthy"] is False
    assert "stale" in result["reason"]
