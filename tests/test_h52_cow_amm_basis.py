import pandas as pd
import pytest

from orcap.analysis.h52_cow_amm_basis import basis_panel, summarize


def _executions():
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "source": "cow",
                "execution_id": "cow-a",
                "executed_at": "2026-07-10T00:00:00Z",
                "event_block_number": 100,
                "side": "usdc_to_weth",
                "price_unit": "usdc_per_weth",
                "price_usdc_per_weth": 2_020.0,
                "requested_size": 2_000.0,
                "fee_amount_raw": "10000000",
            },
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "source": "cow",
                "execution_id": "cow-opposite",
                "side": "weth_to_usdc",
                "price_unit": "usdc_per_weth",
                "price_usdc_per_weth": 2_020.0,
                "requested_size": 1.0,
                "fee_amount_raw": "0",
            },
        ]
    )


def _quotes():
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "reference_source": "cow",
                "reference_execution_id": "cow-a",
                "quote_side": "usdc_to_weth_preblock_exact_input_counterfactual",
                "quote_unit": "usdc_per_weth",
                "state_block_number": 99,
                "pool_id": "pool-5",
                "input_amount": 2_000.0,
                "price_usdc_per_weth": 2_000.0,
            },
            {
                "run_ts": "20260710T000000Z",
                "reference_source": "cow",
                "reference_execution_id": "cow-a",
                "quote_side": "usdc_to_weth_preblock_exact_input_counterfactual",
                "quote_unit": "usdc_per_weth",
                "state_block_number": 99,
                "pool_id": "pool-30",
                "input_amount": 2_000.0,
                "price_usdc_per_weth": 2_010.0,
            },
        ]
    )


def test_h52_matches_only_same_execution_and_computes_gross_basis_per_pool():
    panel = basis_panel(_executions(), _quotes()).set_index("pool_id")
    assert set(panel.index) == {"pool-5", "pool-30"}
    assert panel.loc["pool-5", "state_block_number"] == 99
    assert panel.loc["pool-5", "cow_over_amm_gross_basis_pct"] == pytest.approx(1.0)
    assert panel.loc["pool-30", "cow_over_amm_gross_basis_pct"] == pytest.approx(
        (2_020 / 2_010 - 1) * 100
    )
    assert panel.loc["pool-5", "cow_reported_fee_usdc"] == 10.0
    assert panel.loc["pool-5", "cow_reported_fee_bps"] == 50.0
    assert panel.loc["pool-5", "cow_fee_adjusted_price_usdc_per_weth"] == pytest.approx(2_030.1)
    assert panel.loc["pool-5", "cow_fee_adjusted_over_amm_stated_input_basis_pct"] == pytest.approx(
        (2_030.1 / 2_000 - 1) * 100
    )


def test_h52_short_panel_is_power_gated_and_rejects_adverse_selection_claim():
    summary = summarize(basis_panel(_executions(), _quotes()))
    assert summary["evidence_status"] == "power_gated"
    assert summary["n_fee_observed_fills"] == 1
    assert summary["median_cow_reported_fee_bps"] == 50.0
    assert "not same-all-in-notional best execution" in summary["claim_boundary"]
