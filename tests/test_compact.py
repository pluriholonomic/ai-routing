import pyarrow as pa
import pytest

from orcap.compact import (
    TRACKED_PRICE_FIELDS,
    _shard_tables,
    bundle_curated_partitions,
    fold_pricing_changes,
)


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


def test_consolidate_merges_int64_double_schema_flap(tmp_path):
    # per-sample schema inference can type a stat column int64 in one file and
    # double in another; consolidation must unify instead of raising
    import pyarrow.parquet as pq

    from orcap.capture_api import consolidate_local

    day = tmp_path / "endpoints_stats" / "dt=2026-07-10"
    day.mkdir(parents=True)
    pq.write_table(
        pa.table({"run_ts": ["a"], "p50_throughput": pa.array([45], pa.int64())}),
        day / "s1.parquet",
    )
    pq.write_table(
        pa.table({"run_ts": ["b"], "p50_throughput": pa.array([45.3], pa.float64())}),
        day / "s2.parquet",
    )
    assert consolidate_local(tmp_path) == 2
    merged = pq.ParquetFile(day / "s2.parquet").read()
    assert merged.num_rows == 2
    assert merged.schema.field("p50_throughput").type == pa.float64()


def test_table_shards_are_deterministic_disjoint_and_complete():
    names = ["source_runs", "endpoints_snapshots", "market_quotes", "source_runs"]
    shard0 = _shard_tables(names, shard_index=0, shard_count=2)
    shard1 = _shard_tables(names, shard_index=1, shard_count=2)

    assert set(shard0).isdisjoint(shard1)
    assert sorted(shard0 + shard1) == sorted(set(names))
    assert shard0 == _shard_tables(list(reversed(names)), shard_index=0, shard_count=2)


def test_table_shards_validate_paired_bounds():
    with pytest.raises(ValueError):
        _shard_tables(["a"], shard_index=0, shard_count=None)
    with pytest.raises(ValueError):
        _shard_tables(["a"], shard_index=2, shard_count=2)


def test_bundle_curated_partitions_uses_stable_name_and_migration_guard(tmp_path):
    import pyarrow.parquet as pq

    old = tmp_path / "curated" / "source_runs" / "dt=2026-07-13"
    new = tmp_path / "curated" / "source_runs" / "dt=2026-07-14"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    pq.write_table(pa.table({"run_ts": ["old-a"]}), old / "a.parquet")
    pq.write_table(pa.table({"run_ts": ["old-b"]}), old / "b.parquet")
    pq.write_table(pa.table({"run_ts": ["new-a"]}), new / "a.parquet")
    pq.write_table(pa.table({"run_ts": ["new-b"]}), new / "b.parquet")

    result = bundle_curated_partitions(tmp_path, min_dt="2026-07-14")

    assert sorted(path.name for path in old.glob("*.parquet")) == ["a.parquet", "b.parquet"]
    assert [path.name for path in new.glob("*.parquet")] == ["buffered-part.parquet"]
    assert pq.read_table(new / "buffered-part.parquet").num_rows == 2
    assert result["source_files_removed"] == 2

    # A later assembly replaces the same future remote object and incorporates
    # its existing rows instead of creating a second bundle path.
    pq.write_table(pa.table({"run_ts": ["new-c"]}), new / "c.parquet")
    rerun = bundle_curated_partitions(tmp_path, min_dt="2026-07-14")
    assert [path.name for path in new.glob("*.parquet")] == ["buffered-part.parquet"]
    assert pq.read_table(new / "buffered-part.parquet").num_rows == 3
    assert rerun["source_files_removed"] == 1


def test_bundle_curated_partitions_rejects_non_filename_bundle_name(tmp_path):
    with pytest.raises(ValueError):
        bundle_curated_partitions(tmp_path, bundle_name="nested/part.parquet")
