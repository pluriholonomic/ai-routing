from datetime import UTC, datetime

from orcap.price_events import build_wave_plan, detect_price_events, wave_status


def quote(provider, prompt, completion, *, tag=None):
    return {
        "model_id": "author/model",
        "provider_name": provider,
        "endpoint_tag": tag or f"tag-{provider}",
        "prompt_price_per_token": prompt,
        "completion_price_per_token": completion,
    }


def test_detects_cut_raise_and_pure_rank_crossing():
    previous = [quote("a", 1, 1), quote("b", 2, 2), quote("c", 3, 3)]
    current = [quote("a", 0.8, 0.8), quote("b", 4.0, 4.0), quote("c", 1.9, 4.1)]
    events = detect_price_events(previous, current, detected_at="2026-07-19T00:00:00Z")
    by_provider = {row["provider_name"]: row for row in events}
    assert by_provider["a"]["event_type"] == "price_cut"
    assert by_provider["b"]["event_type"] == "price_raise"
    assert by_provider["c"]["event_type"] == "rank_crossing"
    assert len({row["event_id"] for row in events}) == len(events)


def test_source_health_failure_sends_no_events():
    previous = [quote("a", 1, 1), quote("b", 2, 2)]
    current = [quote("a", 0.5, 0.5), quote("b", 2, 2)]
    assert not detect_price_events(
        previous,
        current,
        detected_at="2026-07-19T00:00:00Z",
        source_healthy=False,
    )


def test_wave_plan_is_deterministic_balanced_and_time_bounded():
    event = {
        "event_id": "event-1",
        "detected_at": "2026-07-19T00:00:00Z",
        "model_id": "author/model",
        "provider_name": "provider-a",
    }
    first = build_wave_plan(event, seed=9)
    assert first == build_wave_plan(event, seed=9)
    assert len(first) == 30
    assert len({row["task_id"] for row in first}) == 30
    for wave_id in {row["wave_id"] for row in first}:
        arms = [row["arm"] for row in first if row["wave_id"] == wave_id]
        assert arms.count("default_fresh") == 4
        assert arms.count("sort_price") == 1
        assert arms.count("moving_provider_pin") == 1


def test_wave_status_never_backfills_missed_wave():
    row = {"target_at": "2026-07-19T00:00:00Z", "latest_at": "2026-07-19T00:10:00Z"}
    assert wave_status(row, now=datetime(2026, 7, 18, 23, 59, tzinfo=UTC)) == "pending"
    assert wave_status(row, now=datetime(2026, 7, 19, 0, 5, tzinfo=UTC)) == "due"
    assert wave_status(row, now=datetime(2026, 7, 19, 0, 11, tzinfo=UTC)) == "missed"
