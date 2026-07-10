import pyarrow as pa
import pyarrow.parquet as pq

from orcap.capture_api import canonical_slug_map, diff_models, endpoint_snapshot_price_map


def test_diff_detects_change_and_skips_variants():
    prev = {
        ("m/a", "P", "t", "f1"): 1.0,
        ("m/b", "P", "t", "f1"): 2.0,
        ("m/a:free", "P", "t", "f1"): 0.0,
    }
    cur = {
        ("m/a", "P", "t", "f1"): 1.5,  # changed
        ("m/b", "P", "t", "f1"): 2.0,  # unchanged
        ("m/a:free", "P", "t", "f1"): 9.9,  # variant — ignored
        ("m/c", "P", "t", "f1"): 3.0,  # new endpoint — not a price change
    }
    assert diff_models(prev, cur) == {"m/a"}
    assert diff_models({}, cur) == set()


def test_canonical_slug_map_uses_versioned_stats_identifier(tmp_path):
    path = tmp_path / "models.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"id": "vendor/model", "canonical_slug": "vendor/model-20260709"},
                {"id": "other/model", "canonical_slug": "other/model-20260709"},
            ]
        ),
        path,
    )
    assert canonical_slug_map(path, {"vendor/model", "missing/model"}) == {
        "vendor/model": "vendor/model-20260709"
    }


def test_endpoint_snapshot_price_map_uses_the_latest_retained_quote_as_a_baseline(tmp_path):
    path = tmp_path / "endpoints.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "run_ts": "20260710T000000Z",
                    "model_id": "vendor/model",
                    "provider_name": "provider",
                    "tag": "default",
                    "endpoint_fingerprint": "endpoint-a",
                    "price_completion": 1.0,
                },
                {
                    "run_ts": "20260710T000500Z",
                    "model_id": "vendor/model",
                    "provider_name": "provider",
                    "tag": "default",
                    "endpoint_fingerprint": "endpoint-a",
                    "price_completion": 1.5,
                },
                {
                    "run_ts": "20260710T000500Z",
                    "model_id": "vendor/other",
                    "provider_name": "provider",
                    "tag": "default",
                    "endpoint_fingerprint": "endpoint-b",
                    "price_completion": None,
                },
            ]
        ),
        path,
    )

    prices = endpoint_snapshot_price_map(path)

    assert prices == {("vendor/model", "provider", "default", "endpoint-a"): 1.5}
