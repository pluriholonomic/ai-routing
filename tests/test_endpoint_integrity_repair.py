import hashlib
import runpy
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from orcap.compact import TRACKED_PRICE_FIELDS

build_repair_bundle = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "repair_endpoint_integrity.py")
)["build_repair_bundle"]


def _row(dt: str, run_ts: str, *, prompt: float, status: int, raw: str) -> dict:
    row = {
        "dt": dt,
        "run_ts": run_ts,
        "model_id": "m/x",
        "provider_name": "P",
        "tag": "p/fp8",
        "endpoint_fingerprint": "abc123",
        "record_json": raw,
        "status": status,
        **{field: None for field in TRACKED_PRICE_FIELDS},
    }
    row["price_prompt"] = prompt
    return row


def test_repair_bundle_deduplicates_and_rebuilds_chronological_events(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    day1 = source / "curated" / "endpoints_snapshots" / "dt=2026-07-07"
    day2 = source / "curated" / "endpoints_snapshots" / "dt=2026-07-08"
    day1.mkdir(parents=True)
    day2.mkdir(parents=True)

    first = _row(
        "2026-07-07",
        "20260707T235500Z",
        prompt=1e-7,
        status=0,
        raw='{"prompt":"0.0000001","status":0}',
    )
    availability_variant = first | {
        "status": -2,
        "record_json": '{"prompt":"0.0000001","status":-2}',
    }
    changed = _row(
        "2026-07-08",
        "20260708T000500Z",
        prompt=2e-7,
        status=0,
        raw='{"prompt":"0.0000002","status":0}',
    )
    pq.write_table(pa.Table.from_pylist([first, first, availability_variant]), day1 / "a.parquet")
    pq.write_table(pa.Table.from_pylist([changed, changed]), day2 / "b.parquet")

    manifest = build_repair_bundle(
        source,
        output,
        dates=["2026-07-07", "2026-07-08"],
        input_revision="frozen-revision",
    )

    assert manifest["totals"] == {
        "physical_rows": 5,
        "distinct_source_records": 3,
        "duplicate_rows_removed": 2,
        "listing_keys": 2,
        "same_listing_raw_variants": 1,
        "pricing_events": 2,
        "price_field_changes": 1,
    }
    assert manifest["event_fields"] == {"__endpoint_added__": 1, "price_prompt": 1}
    repaired_day1 = pq.ParquetFile(
        output / "curated" / "endpoints_snapshots" / "dt=2026-07-07" / "part-0.parquet"
    ).read()
    assert repaired_day1.num_rows == 2
    changes_day2 = pq.ParquetFile(
        output / "derived" / "pricing_changes" / "dt=2026-07-08" / "part-0.parquet"
    ).read().to_pylist()
    assert [row["field"] for row in changes_day2] == ["price_prompt"]

    for relative, metadata in manifest["output_files"].items():
        payload = (output / relative).read_bytes()
        assert metadata["sha256"] == hashlib.sha256(payload).hexdigest()
