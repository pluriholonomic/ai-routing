import pandas as pd

from orcap.analysis.h7_passthrough import align_ornn_h100
from orcap.capture_gpu import _ornn_index_rows
from orcap.observability import source_spec


def test_ornn_history_rows_keep_source_defined_index_value():
    body = {
        "success": True,
        "gpu_type": "H100 SXM",
        "data": [
            {"timestamp": "2026-04-10T20:00:00.000Z", "index_value": 1.76},
            {"timestamp": "2026-04-11T20:00:00.000Z", "index_value": "1.77"},
            {"timestamp": "2026-04-12T20:00:00.000Z", "index_value": None},
        ],
    }
    rows = _ornn_index_rows(body, "H100 SXM", "20260710T000000Z", "2026-07-10")
    assert len(rows) == 2
    assert rows[0]["gpu_class"] == "H100 SXM"
    assert rows[0]["index_value"] == 1.76
    assert rows[0]["source"] == "ornn"
    assert rows[0]["source_unit"] == "ornn_compute_index"


def test_ornn_monthly_alignment_deduplicates_latest_capture():
    token_idx = pd.DataFrame(
        {
            "month_start": pd.to_datetime(["2026-04-01", "2026-05-01", "2026-06-01"]),
            "index": [50.0, 48.0, 46.0],
        }
    )
    history = pd.DataFrame(
        {
            "run_ts": [
                "20260709T000000Z",
                "20260709T000000Z",
                "20260709T000000Z",
                "20260710T000000Z",
            ],
            "gpu_class": ["H100 SXM"] * 4,
            "observed_at": [
                "2026-04-10T20:00:00.000Z",
                "2026-05-10T20:00:00.000Z",
                "2026-06-10T20:00:00.000Z",
                "2026-05-10T20:00:00.000Z",
            ],
            "index_value": [1.8, 2.0, 2.4, 2.2],
            "source_unit": ["ornn_compute_index"] * 4,
        }
    )
    aligned = align_ornn_h100(token_idx, history)
    assert aligned["segment"].unique().tolist() == ["ornn_h100_sxm_index"]
    assert aligned["period_start"].dt.strftime("%Y-%m").tolist() == [
        "2026-04",
        "2026-05",
        "2026-06",
    ]
    assert aligned["gpu_usd_hr"].tolist() == [1.8, 2.2, 2.4]
    assert aligned["series_unit"].unique().tolist() == ["ornn_compute_index"]


def test_ornn_is_required_for_gpu_source_health():
    spec = source_spec("ornn")
    assert spec.required is True
    assert spec.min_rows == 5
