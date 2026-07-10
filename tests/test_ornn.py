import json

import pandas as pd

from orcap.analysis.h7_passthrough import align_ornn_h100
from orcap.capture_gpu import (
    LAMBDA_GPU_PRICING_URL,
    RUNPOD_GPU_PRICING_URL,
    _lambda_gpu_price_rows,
    _ornn_index_rows,
    _runpod_gpu_price_rows,
)
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
    runpod = source_spec("runpod_gpu_pricing")
    assert runpod.required is False
    assert runpod.min_rows == 10


def test_lambda_rows_require_labeled_tabular_gpu_prices():
    body = """
    <button role="tab" aria-controls="one">1x</button>
    <div role="tabpanel" id="one"><table><thead><tr>
      <th>Plan</th><th>VRAM/GPU</th><th>vCPUs</th><th>RAM</th><th>STORAGE</th><th>PRICE/GPU/HR*</th>
    </tr></thead><tbody><tr>
      <th>NVIDIA H100 SXM</th><td>80 GB</td><td>26</td><td>225 GiB</td>
      <td>2.75 TiB SSD</td><td>$4.29</td>
    </tr></tbody></table></div>
    """
    rows = _lambda_gpu_price_rows(body, "20260710T000000Z", "2026-07-10")
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "lambda"
    assert row["gpu_class"] == "NVIDIA H100 SXM"
    assert row["instance_gpu_count"] == 1
    assert row["gpu_vram_gb"] == 80.0
    assert row["usd_per_gpu_hour"] == 4.29
    assert row["source_url"] == LAMBDA_GPU_PRICING_URL
    assert json.loads(row["record_json"])["price_per_gpu_hour"] == "$4.29"


def test_lambda_rows_reject_unlabeled_price_or_changed_headers():
    assert _lambda_gpu_price_rows("<html></html>", "20260710T000000Z", "2026-07-10") == []


def test_runpod_rows_keep_only_labeled_public_pods_gpu_cards():
    body = """
    <div role="listitem" class="gpu_collection-item w-dyn-item">
      <div class="gpu_table-row">
        <div class="gpu_name-wrapper"><p class="gpu_name is-pricing-page">H100 SXM</p></div>
        <div class="gpu_table-tags">80 GB VRAM 125 GB RAM 20 vCPUs</div>
        <div class="gpu_table-pricing">$2.99/hr</div>
      </div>
    </div>
    <div role="listitem" class="clusters_list-item">
      <div>H100 SXM</div><div class="clusters_item-price">$4.31/hr</div>
    </div>
    """

    rows = _runpod_gpu_price_rows(body, "20260710T000000Z", "2026-07-10")

    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "runpod"
    assert row["gpu_class"] == "H100 SXM"
    assert row["gpu_vram_gb"] == 80.0
    assert row["usd_per_gpu_hour"] == 2.99
    assert row["quote_type"] == "published_pods_gpu_list_price"
    assert row["source_url"] == RUNPOD_GPU_PRICING_URL
    assert json.loads(row["record_json"])["product"] == "pods"


def test_runpod_rows_fail_closed_on_ambiguous_price_or_missing_vram():
    ambiguous = """
    <div role="listitem" class="gpu_collection-item"><div class="gpu_table-row">
      <p class="gpu_name is-pricing-page">H100 SXM</p>
      <div class="gpu_table-tags">80 GB VRAM</div>
      <div class="gpu_table-pricing">from $2.99/hr</div>
    </div></div>
    """
    missing_vram = """
    <div role="listitem" class="gpu_collection-item"><div class="gpu_table-row">
      <p class="gpu_name is-pricing-page">H100 SXM</p>
      <div class="gpu_table-tags">high memory</div>
      <div class="gpu_table-pricing">$2.99/hr</div>
    </div></div>
    """

    assert _runpod_gpu_price_rows(ambiguous, "20260710T000000Z", "2026-07-10") == []
    assert _runpod_gpu_price_rows(missing_vram, "20260710T000000Z", "2026-07-10") == []
