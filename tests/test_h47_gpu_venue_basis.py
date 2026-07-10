import pandas as pd

from orcap.analysis.h47_gpu_venue_basis import (
    coverage_diagnostic,
    match_venue_quotes,
    source_read_status,
    summarize,
)


def test_h47_matches_only_versioned_explicit_gpu_cohorts():
    akash = pd.DataFrame(
        [
            {
                "run_ts": "20260710T010000Z",
                "quote_id": "nvidia:rtx4090:24Gi:PCIe",
                "price_usd": 0.4,
                "available_units": 5,
            }
        ]
    )
    vast = pd.DataFrame(
        [
            {
                "run_ts": "20260710T005500Z",
                "gpu_class": "RTX 4090",
                "offer_type": "on-demand",
                "dph_total": 0.5,
                "rented": True,
            },
            {
                "run_ts": "20260710T005500Z",
                "gpu_class": "RTX 4090",
                "offer_type": "on-demand",
                "dph_total": 0.5,
                "rented": False,
            },
            {
                "run_ts": "20260710T005500Z",
                "gpu_class": "H100 SXM",
                "offer_type": "on-demand",
                "dph_total": 3.0,
                "rented": False,
            },
        ]
    )
    mapping = pd.DataFrame(
        [
            {
                "cohort": "rtx4090_pcie_24g",
                "akash_quote_id": "nvidia:rtx4090:24Gi:PCIe",
                "vast_gpu_class": "RTX 4090",
            }
        ]
    )
    panel = match_venue_quotes(akash, vast, mapping)
    assert len(panel) == 1
    assert panel.iloc[0]["vast_over_akash_basis_pct"] == 25.0
    assert panel.iloc[0]["vast_rented_share"] == 0.5


def test_h47_is_gated_without_sufficient_time_and_cohort_coverage():
    panel = pd.DataFrame(
        [
            {
                "cohort": "rtx4090_pcie_24g",
                "akash_run_ts": "20260710T010000Z",
                "vast_over_akash_basis_pct": 25.0,
            }
        ]
    )
    result = summarize(panel)
    assert result["gate"]["passed"] is False
    assert result["verdict"] == "insufficient_quote_history"


def test_h47_coverage_diagnostic_separates_clock_mismatch_from_missing_cohort():
    akash = pd.DataFrame(
        [
            {
                "run_ts": "20260710T120000Z",
                "quote_id": "nvidia:rtx4090:24Gi:PCIe",
                "price_usd": 0.4,
                "available_units": 5,
            }
        ]
    )
    vast = pd.DataFrame(
        [
            {
                "run_ts": "20260710T070000Z",
                "gpu_class": "RTX 4090",
                "offer_type": "on-demand",
                "dph_total": 0.5,
                "rented": False,
            }
        ]
    )
    mapping = pd.DataFrame(
        [
            {
                "cohort": "rtx4090_pcie_24g",
                "akash_quote_id": "nvidia:rtx4090:24Gi:PCIe",
                "vast_gpu_class": "RTX 4090",
            }
        ]
    )

    result = coverage_diagnostic(akash, vast, mapping)

    assert result["valid_akash_quote_rows"] == 1
    assert result["vast_on_demand_snapshot_rows"] == 1
    cohort = result["cohorts"][0]
    assert cohort["akash_quote_snapshots"] == 1
    assert cohort["vast_on_demand_snapshots"] == 1
    assert cohort["nearest_elapsed_minutes"] == 300.0
    assert cohort["akash_snapshots_within_match_window"] == 0


def test_h47_source_status_does_not_conflate_empty_data_with_query_failure():
    empty = pd.DataFrame()

    assert source_read_status(empty, query_succeeded=True) == {
        "status": "query_succeeded",
        "rows": 0,
    }
    assert source_read_status(empty, query_succeeded=False) == {
        "status": "query_failed",
        "rows": 0,
    }
