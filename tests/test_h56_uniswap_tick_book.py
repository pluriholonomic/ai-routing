import pandas as pd

from orcap.analysis.h56_uniswap_tick_book import (
    complete_snapshot_keys,
    complete_snapshot_manifests,
    coverage_gate,
    tick_book_panel,
)


def test_h56_requires_a_complete_source_run_and_keeps_virtual_tick_state_distinct():
    source_runs = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "source": "uniswap_tick_book",
                "status": "success",
                "detail_json": (
                    '{"coverage_complete":true,"initialized_tick_rows":2,'
                    '"pool_details":{"pool-a":{"complete":true,"initialized_tick_rows":1},'
                    '"pool-b":{"complete":true,"initialized_tick_rows":1}}}'
                ),
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "source": "uniswap_tick_book",
                "status": "degraded",
                "detail_json": (
                    '{"coverage_complete":false,"initialized_tick_rows":1,'
                    '"pool_details":{"pool-a":{"complete":true,"initialized_tick_rows":1}}}'
                ),
            },
        ]
    )
    complete = complete_snapshot_keys(source_runs)
    assert complete == {("20260710T000000Z", "2026-07-10")}
    assert complete_snapshot_manifests(source_runs) == {
        ("20260710T000000Z", "2026-07-10"): 2
    }
    ticks = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "pool_id": "pool-a",
                "pool_map_id": "usdc-weth",
                "block_number": 10,
                "tick": -10,
                "current_tick": 0,
                "active_liquidity_raw": "100",
                "liquidity_net_raw": "5",
            },
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "pool_id": "pool-a",
                "pool_map_id": "usdc-weth",
                "block_number": 10,
                "tick": 10,
                "current_tick": 0,
                "active_liquidity_raw": "100",
                "liquidity_net_raw": "-5",
            },
            {
                "run_ts": "20260710T010000Z",
                "dt": "2026-07-10",
                "pool_id": "pool-a",
                "pool_map_id": "usdc-weth",
                "block_number": 11,
                "tick": 20,
                "current_tick": 1,
                "active_liquidity_raw": "90",
                "liquidity_net_raw": "3",
            },
        ]
    )
    panel = tick_book_panel(ticks, complete)
    assert set(panel["metric"]) == {
        "initialized_tick_count",
        "minimum_initialized_tick",
        "maximum_initialized_tick",
        "positive_net_liquidity_tick_count",
        "negative_net_liquidity_tick_count",
        "signed_liquidity_net_sums_to_zero",
    }
    assert set(panel["block_number"]) == {10}
    assert panel.loc[
        panel["metric"].eq("signed_liquidity_net_sums_to_zero"), "value"
    ].iloc[0] == 1
    assert coverage_gate(panel)["status"] == "power_gated"


def test_h56_does_not_promote_unverified_tick_rows_to_a_panel():
    ticks = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "pool_id": "pool-a",
                "block_number": 10,
                "tick": 0,
            }
        ]
    )
    panel = tick_book_panel(ticks, set())
    assert panel.empty
    assert coverage_gate(panel)["status"] == "not_identified"


def test_h56_normalizes_parquet_date_values_before_joining_the_source_ledger():
    source_runs = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": pd.Timestamp("2026-07-10"),
                "source": "uniswap_tick_book",
                "status": "success",
                "detail_json": (
                    '{"coverage_complete":true,"initialized_tick_rows":1,'
                    '"pool_details":{"pool-a":{"complete":true,"initialized_tick_rows":1}}}'
                ),
            }
        ]
    )
    ticks = pd.DataFrame(
        [
            {
                "run_ts": "20260710T000000Z",
                "dt": pd.Timestamp("2026-07-10"),
                "pool_id": "pool-a",
                "block_number": 10,
                "tick": 0,
                "liquidity_net_raw": "0",
            }
        ]
    )
    manifests = complete_snapshot_manifests(source_runs)
    assert manifests == {("20260710T000000Z", "2026-07-10"): 1}
    assert not tick_book_panel(ticks, set(manifests), manifests).empty
