import pyarrow as pa
import pyarrow.parquet as pq

from orcap.analysis import data
from orcap.analysis import pm2_sufficient_stats as pm2


def test_pm2_clips_changes_and_endpoint_days_to_registered_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCAP_ANALYSIS_SOURCE", "local")
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    data.reset_connection()

    change_rows = [
            {
                "dt": "2026-07-07",
                "changed_at_run_ts": "20260707T000000Z",
                "model_id": "m/a",
                "provider_name": "P",
                "endpoint_fingerprint": "one",
                "old_value": "1.0",
                "new_value": "2.0",
                "field": "price_completion",
            },
            {
                "dt": "2026-07-08",
                "changed_at_run_ts": "20260708T000000Z",
                "model_id": "m/a",
                "provider_name": "P",
                "endpoint_fingerprint": "one",
                "old_value": "2.0",
                "new_value": "3.0",
                "field": "price_completion",
            },
    ]
    for row in change_rows:
        changes_dir = tmp_path / "derived" / "pricing_changes" / f"dt={row['dt']}"
        changes_dir.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist([row]), changes_dir / "part.parquet")

    endpoint_rows = [
            {
                "dt": "2026-07-07",
                "model_id": "m/a",
                "provider_name": "P",
                "price_completion": 1.0,
            },
            {
                "dt": "2026-07-08",
                "model_id": "m/a",
                "provider_name": "P",
                "price_completion": 1.0,
            },
    ]
    for row in endpoint_rows:
        endpoints_dir = tmp_path / "curated" / "endpoints_snapshots" / f"dt={row['dt']}"
        endpoints_dir.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist([row]), endpoints_dir / "part.parquet")

    clipped = pm2.changes(start_date="2026-07-08", end_date="2026-07-08")

    assert clipped["dt"].tolist() == ["2026-07-08"]
    assert pm2.endpoint_days(start_date="2026-07-08", end_date="2026-07-08") == 1.0
    data.reset_connection()
