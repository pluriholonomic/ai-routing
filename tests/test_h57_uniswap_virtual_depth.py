from decimal import Decimal

import pandas as pd

from orcap.analysis.h57_uniswap_virtual_depth import (
    Q96,
    gross_usdc_for_post_spot_impact,
    post_sqrt_after_usdc_input,
    quoter_validation_panel,
    validation_gate,
    virtual_depth_panel,
)

POOL = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"


def _records() -> list[dict]:
    return [
        {
            "tick": -100,
            "tick_spacing": 10,
            "current_tick": 0,
            "sqrt_price_x96": int(Q96),
            "active_liquidity_raw": 1_000_000,
            "liquidity_net_raw": 0,
        },
        {
            "tick": -1000,
            "tick_spacing": 10,
            "current_tick": 0,
            "sqrt_price_x96": int(Q96),
            "active_liquidity_raw": 1_000_000,
            "liquidity_net_raw": 0,
        },
    ]


def _ticks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "pool_id": POOL,
                "pool_map_id": "uniswap_usdc_weth_5",
                "block_number": 10,
                "liquidity_gross_raw": "1000000",
                **record,
            }
            for record in _records()
        ]
    )


def test_h57_zero_for_one_state_traversal_applies_fee_before_virtual_liquidity():
    records = _records()
    gross = Decimal(1000)
    estimated = post_sqrt_after_usdc_input(list(reversed(records)), 500, gross)
    expected = Decimal(1_000_000) / (Decimal(1_000_000) + Decimal("999.5")) * Q96
    assert estimated is not None
    assert abs(estimated / expected - Decimal(1)) < Decimal("1e-25")

    capacity = gross_usdc_for_post_spot_impact(list(reversed(records)), 500, 100)
    assert capacity is not None
    achieved = post_sqrt_after_usdc_input(records, 500, capacity)
    assert achieved is not None
    impact_bps = ((Q96 / achieved) ** 2 - Decimal(1)) * Decimal(10_000)
    assert abs(impact_bps - Decimal(100)) < Decimal("1e-20")


def test_h57_requires_complete_manifest_rows_and_checks_same_block_quoter_sqrt_price():
    ticks = _ticks()
    manifests = {("20260710T000000Z", "2026-07-10"): 2}
    depth = virtual_depth_panel(ticks, manifests)
    assert set(depth["impact_target_bps"]) == {100, 500}
    assert set(depth["state_status"]) == {"model_implied_pending_quoter_validation"}

    actual = post_sqrt_after_usdc_input(_records(), 500, 1_000)
    quotes = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "pool_id": POOL,
                "block_number": 10,
                "quote_side": "usdc_to_weth_exact_input_simulation",
                "input_amount_raw": "1000",
                "sqrt_price_x96_after": str(int(actual)),
            }
        ]
    )
    validation = quoter_validation_panel(ticks, quotes, manifests)
    assert validation["absolute_sqrt_price_error_bps"].iloc[0] < 1e-20
    assert validation_gate(validation)["status"] == "same_block_quoter_consistent"

    assert virtual_depth_panel(ticks, {("20260710T000000Z", "2026-07-10"): 3}).empty
