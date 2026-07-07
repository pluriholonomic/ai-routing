import pyarrow as pa

from orcap.compact import TRACKED_PRICE_FIELDS, fold_pricing_changes


def _row(run_ts, model="m/x", provider="P", tag="p/fp8", prompt=1e-7, completion=4e-7, fp="abc123"):
    row = {
        "run_ts": run_ts,
        "model_id": model,
        "provider_name": provider,
        "tag": tag,
        "endpoint_fingerprint": fp,
        **{f: None for f in TRACKED_PRICE_FIELDS},
    }
    row["price_prompt"] = prompt
    row["price_completion"] = completion
    return row


def test_new_endpoint_emits_added_event():
    day = pa.Table.from_pylist([_row("20260101T000000Z")])
    events, state = fold_pricing_changes(day, {})
    assert [e["field"] for e in events] == ["__endpoint_added__"]
    assert len(state) == 1


def test_price_change_emits_field_event():
    day = pa.Table.from_pylist(
        [
            _row("20260101T000000Z", prompt=1e-7),
            _row("20260101T001500Z", prompt=2e-7),
            _row("20260101T003000Z", prompt=2e-7),  # no further change
        ]
    )
    events, state = fold_pricing_changes(day, {})
    changes = [e for e in events if e["field"] == "price_prompt"]
    assert len(changes) == 1
    assert changes[0]["old_value"] == "1e-07"
    assert changes[0]["new_value"] == "2e-07"
    assert state[next(iter(state))]["price_prompt"] == 2e-7


def test_state_carries_across_days_without_spurious_events():
    day1 = pa.Table.from_pylist([_row("20260101T000000Z")])
    _, state = fold_pricing_changes(day1, {})
    day2 = pa.Table.from_pylist([_row("20260102T000000Z")])
    events, state = fold_pricing_changes(day2, state)
    assert events == []


def test_removed_endpoint_emits_removed_event():
    day = pa.Table.from_pylist(
        [
            _row("20260101T000000Z", tag="a/fp8"),
            _row("20260101T000000Z", tag="b/fp8"),
            _row("20260101T001500Z", tag="a/fp8"),  # b/fp8 gone in final run
        ]
    )
    events, state = fold_pricing_changes(day, {})
    removed = [e for e in events if e["field"] == "__endpoint_removed__"]
    assert len(removed) == 1
    assert removed[0]["tag"] == "b/fp8"
    assert len(state) == 1
