from orcap.capture_markets import (
    akash_capacity_rows,
    cow_execution_rows,
    defillama_participant_rows,
    golem_capacity_rows,
    instrument_map_rows,
    uniswap_rows,
)


def test_defillama_rows_preserve_source_identity():
    rows = defillama_participant_rows(
        [{"id": "uniswap", "name": "Uniswap", "category": "Dexes", "tvl": 12.5}],
        "20260709T000000Z",
        "2026-07-09",
    )
    assert rows[0]["participant_id"] == "uniswap"
    assert rows[0]["value"] == 12.5


def test_golem_capacity_keeps_hardware_metadata():
    rows = golem_capacity_rows(
        {"providers": [{"node_id": "n1", "data": {"golem.inf.cpu.cores": 8}}]},
        "20260709T000000Z",
        "2026-07-09",
    )
    assert rows[0]["participant_id"] == "n1"
    assert rows[0]["cpu_cores"] == 8.0


def test_cow_execution_uses_immutable_trade_identity():
    rows = cow_execution_rows(
        [
            {
                "uid": "trade1",
                "sellToken": "a",
                "buyToken": "b",
                "sellAmount": "2",
                "buyAmount": "6",
            }
        ],
        "20260709T000000Z",
        "2026-07-09",
    )
    assert rows[0]["execution_id"] == "trade1"
    assert rows[0]["native_price"] == 3.0


def test_uniswap_rows_keep_quote_and_execution_separate():
    quotes, executions, events = uniswap_rows(
        {
            "data": {
                "pools": [
                    {
                        "id": "pool",
                        "token0": {"id": "a"},
                        "token1": {"id": "b"},
                        "token1Price": "2",
                        "totalValueLockedUSD": "4",
                    }
                ],
                "swaps": [
                    {
                        "id": "swap",
                        "pool": {"id": "pool"},
                        "amount0": "1",
                        "amount1": "2",
                        "amountUSD": "3",
                    }
                ],
            }
        },
        "20260709T000000Z",
        "2026-07-09",
    )
    assert quotes[0]["quote_id"] == "pool"
    assert executions[0]["execution_id"] == "swap"
    assert events[0]["event_type"] == "swap"


def test_akash_rows_keep_provider_as_participant():
    rows = akash_capacity_rows(
        {"providers": [{"owner": "akash1x", "attributes": {"region": "us"}, "capacity": 4}]},
        "20260709T000000Z",
        "2026-07-09",
    )
    assert rows[0]["participant_id"] == "akash1x"
    assert rows[0]["available"] == 4.0


def test_instrument_map_is_versioned_and_source_scoped():
    rows = instrument_map_rows("20260709T000000Z", "2026-07-09")
    assert {row["map_id"] for row in rows} >= {"uniswap_usdc_weth_5", "vast_h100_sxm"}
    assert all(row["mapping_version"] == "v1" for row in rows)
