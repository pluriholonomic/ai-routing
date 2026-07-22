import pyarrow as pa
import pytest

from orcap.compact import (
    TRACKED_PRICE_FIELDS,
    _shard_tables,
    build_source_runs_baseline,
    bundle_curated_partitions,
    canonicalize_pricing_endpoints,
    compact_local,
    consolidate_table_day,
    deduplicate_endpoint_records,
    deduplicate_exact_records,
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


def test_endpoint_source_record_dedup_preserves_distinct_raw_variants():
    first = _row("20260101T000000Z") | {"record_json": '{"status":0}', "status": 0}
    second = first | {"record_json": '{"status":-2}', "status": -2}
    table = pa.Table.from_pylist([first, first, second])

    result, audit = deduplicate_endpoint_records(table)

    assert result.num_rows == 2
    assert result["status"].to_pylist() == [0, -2]
    assert audit == {
        "physical_rows": 3,
        "distinct_source_records": 2,
        "duplicate_rows_removed": 1,
    }


def test_endpoint_source_record_dedup_rejects_normalization_conflict():
    first = _row("20260101T000000Z") | {"record_json": '{"status":0}', "status": 0}
    conflicting = first | {"price_prompt": 9e-7}

    with pytest.raises(RuntimeError, match="conflicting normalized fields"):
        deduplicate_endpoint_records(pa.Table.from_pylist([first, conflicting]))


def test_exact_record_dedup_removes_only_identical_checkpoint_rows():
    first = {"study_id": "s", "task_id": "a", "tags": ["x", "y"], "cost": 0.1}
    conflicting = first | {"cost": 0.2}

    result, audit = deduplicate_exact_records(
        pa.Table.from_pylist([first, first, conflicting])
    )

    assert result.to_pylist() == [first, conflicting]
    assert audit == {"physical_rows": 3, "duplicate_rows_removed": 1}


def test_pricing_fold_collapses_availability_variants_with_identical_quote():
    first = _row("20260101T000000Z") | {"status": 0}
    second = first | {"status": -2}

    canonical = canonicalize_pricing_endpoints(pa.Table.from_pylist([first, second]))
    events, state = fold_pricing_changes(pa.Table.from_pylist([first, second]), {})

    assert canonical.num_rows == 1
    assert [event["field"] for event in events] == ["__endpoint_added__"]
    assert len(state) == 1


def test_pricing_fold_rejects_same_listing_time_with_conflicting_quote():
    first = _row("20260101T000000Z", prompt=1e-7)
    second = _row("20260101T000000Z", prompt=2e-7)

    with pytest.raises(RuntimeError, match="conflicting prices"):
        fold_pricing_changes(pa.Table.from_pylist([first, second]), {})


def test_endpoint_consolidation_is_idempotent_under_buffer_overlap(tmp_path):
    import pyarrow.parquet as pq

    day = tmp_path / "curated" / "endpoints_snapshots" / "dt=2026-07-16"
    day.mkdir(parents=True)
    first = _row("20260716T000000Z") | {"record_json": '{"status":0}', "status": 0}
    second = _row("20260716T000000Z", provider="Q") | {
        "record_json": '{"status":0,"provider":"Q"}',
        "status": 0,
    }
    pq.write_table(pa.Table.from_pylist([first, second]), day / "part-0.parquet")
    pq.write_table(pa.Table.from_pylist([first, second]), day / "buffered-part.parquet")

    out, inputs = consolidate_table_day(day)

    assert out == day / "part-0.parquet"
    assert inputs == [day / "buffered-part.parquet"]
    assert pq.ParquetFile(out).read().num_rows == 2

    # The caller removes folded inputs; adding the same buffer again must still
    # leave exactly one copy of each source record.
    for path in inputs:
        path.unlink()
    pq.write_table(pa.Table.from_pylist([first, second]), day / "buffered-part.parquet")
    out, _ = consolidate_table_day(day)
    assert pq.ParquetFile(out).read().num_rows == 2


def test_generic_consolidation_is_idempotent_under_artifact_overlap(tmp_path):
    import pyarrow.parquet as pq

    day = tmp_path / "curated" / "paid_spend_ledger" / "dt=2026-07-16"
    day.mkdir(parents=True)
    row = {"study_id": "s", "task_id": "a", "cost_usd": 0.001}
    pq.write_table(pa.Table.from_pylist([row]), day / "part-0.parquet")
    pq.write_table(pa.Table.from_pylist([row]), day / "buffered-part.parquet")

    out, _ = consolidate_table_day(day)

    assert pq.ParquetFile(out).read().to_pylist() == [row]


def test_compaction_requires_prior_state_when_history_exists(tmp_path):
    import pyarrow.parquet as pq

    day = tmp_path / "curated" / "endpoints_snapshots" / "dt=2026-07-08"
    day.mkdir(parents=True)
    row = _row("20260708T000000Z") | {"record_json": '{"status":0}', "status": 0}
    pq.write_table(pa.Table.from_pylist([row]), day / "capture.parquet")

    with pytest.raises(RuntimeError, match="no immutable prior-day pricing state"):
        compact_local(
            "2026-07-08",
            data_dir=tmp_path,
            tables={"endpoints_snapshots"},
            require_prior_state=True,
        )


def test_pricing_day_is_reproducible_from_immutable_prior_state(tmp_path):
    import pyarrow.parquet as pq

    first_day = tmp_path / "curated" / "endpoints_snapshots" / "dt=2026-07-07"
    first_day.mkdir(parents=True)
    initial = _row("20260707T235500Z", prompt=1e-7) | {
        "record_json": '{"prompt":"0.0000001"}',
        "status": 0,
    }
    pq.write_table(pa.Table.from_pylist([initial]), first_day / "capture.parquet")
    compact_local("2026-07-07", data_dir=tmp_path, tables={"endpoints_snapshots"})
    prior = tmp_path / "derived" / "pricing_state" / "dt=2026-07-07" / "part-0.parquet"

    second_day = tmp_path / "curated" / "endpoints_snapshots" / "dt=2026-07-08"
    second_day.mkdir(parents=True)
    changed = _row("20260708T000500Z", prompt=2e-7) | {
        "record_json": '{"prompt":"0.0000002"}',
        "status": 0,
    }
    pq.write_table(pa.Table.from_pylist([changed]), second_day / "capture.parquet")
    compact_local(
        "2026-07-08",
        data_dir=tmp_path,
        tables={"endpoints_snapshots"},
        prior_state_path=prior,
        require_prior_state=True,
    )
    changes_path = (
        tmp_path / "derived" / "pricing_changes" / "dt=2026-07-08" / "part-0.parquet"
    )
    expected = pq.ParquetFile(changes_path).read().to_pylist()
    assert [row["field"] for row in expected] == ["price_prompt"]

    # Reintroducing the same source buffer re-runs the day from the prior state,
    # replacing the derived partition with the identical event set.
    pq.write_table(pa.Table.from_pylist([changed]), second_day / "buffered-part.parquet")
    compact_local(
        "2026-07-08",
        data_dir=tmp_path,
        tables={"endpoints_snapshots"},
        prior_state_path=prior,
        require_prior_state=True,
    )
    assert pq.ParquetFile(changes_path).read().to_pylist() == expected


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


def test_build_source_runs_baseline_preserves_all_legacy_rows(tmp_path):
    import pyarrow.parquet as pq

    source_runs = tmp_path / "curated" / "source_runs"
    for dt, run_ts in (("2026-07-10", "a"), ("2026-07-11", "b")):
        partition = source_runs / f"dt={dt}"
        partition.mkdir(parents=True)
        pq.write_table(pa.table({"run_ts": [run_ts], "dt": [dt]}), partition / "part.parquet")
    ignored = source_runs / "dt=2026-07-14"
    ignored.mkdir(parents=True)
    pq.write_table(
        pa.table({"run_ts": ["future"], "dt": ["2026-07-14"]}),
        ignored / "buffered-part.parquet",
    )

    output = tmp_path / "baseline" / "source-runs.parquet"
    summary = build_source_runs_baseline(
        tmp_path,
        ("2026-07-10", "2026-07-11"),
        output,
    )

    assert summary["source_files"] == 2
    assert summary["rows"] == 2
    assert pq.ParquetFile(output).read().to_pydict() == {
        "run_ts": ["a", "b"],
        "dt": ["2026-07-10", "2026-07-11"],
    }


def test_build_source_runs_baseline_requires_hydrated_inputs(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_source_runs_baseline(tmp_path, ("2026-07-10",), tmp_path / "out.parquet")
