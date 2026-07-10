from orcap.capture_markets import (
    _block_time,
    akash_capacity_rows,
    akash_gpu_quote_rows,
    akash_lease_execution_rows,
    akash_registry_summary,
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


def test_akash_console_provider_rows_use_public_gpu_stats():
    rows = akash_capacity_rows(
        [
            {
                "owner": "akash1x",
                "hostUri": "https://provider.example",
                "ipRegion": "us-east",
                "isOnline": True,
                "isValidVersion": True,
                "gpuModels": [{"vendor": "nvidia", "model": "h100", "ram": "80Gi"}],
                "stats": {
                    "gpu": {"active": 2, "available": 6, "total": 8},
                    "cpu": {"total": 64},
                    "memory": {"total": 512},
                },
                "attributes": [{"key": "datacenter", "value": "example"}],
            }
        ],
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["available"] == 6.0
    assert rows[0]["used"] == 2.0
    assert rows[0]["total"] == 8.0
    # Akash's current Console field is not documented as cores, so it remains
    # in raw provenance rather than being relabeled as a physical CPU count.
    assert rows[0]["cpu_cores"] is None
    assert rows[0]["region"] == "us-east"
    assert rows[0]["resource_kind"] == "gpu"
    assert rows[0]["resource_class"] == "nvidia:h100:80Gi"


def test_akash_registry_entries_without_live_gpu_capacity_are_excluded():
    body = [
        {
            "owner": "offline",
            "isOnline": False,
            "isValidVersion": True,
            "stats": {"gpu": {"total": 8}},
        },
        {
            "owner": "no-gpu",
            "isOnline": True,
            "isValidVersion": True,
            "stats": {"gpu": {"total": 0}},
        },
    ]
    assert akash_capacity_rows(body, "20260710T000000Z", "2026-07-10") == []
    assert akash_registry_summary(body) == {
        "registry_providers": 2,
        "online_providers": 1,
        "online_version_valid_providers": 1,
        "online_gpu_capacity_providers": 0,
    }


def test_akash_lease_lifecycle_preserves_native_rate_without_claiming_workload_success():
    rows = akash_lease_execution_rows(
        {
            "leases": [
                {
                    "lease": {
                        "id": {
                            "owner": "owner",
                            "dseq": "1",
                            "gseq": 2,
                            "oseq": 3,
                            "provider": "provider",
                            "bseq": 4,
                        },
                        "state": "closed",
                        "closed_on": "99",
                        "price": {"denom": "uakt", "amount": "12.5"},
                    },
                    "escrow_payment": {
                        "state": {"withdrawn": {"denom": "uakt", "amount": "20"}}
                    },
                }
            ]
        },
        {99: "2026-07-10T00:00:00Z"},
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["execution_id"] == "owner/1/2/3/provider/4"
    assert rows[0]["executed_at"] == "2026-07-10T00:00:00Z"
    assert rows[0]["rate_denom"] == "uakt"
    assert rows[0]["rate_amount_native"] == 12.5
    assert rows[0]["success"] is None
    assert _block_time({"result": {"header": {"time": "2026-07-10T00:00:00Z"}}}) == (
        "2026-07-10T00:00:00Z"
    )


def test_akash_gpu_quotes_preserve_exact_model_and_hourly_quote_unit():
    rows = akash_gpu_quote_rows(
        {
            "models": [
                {
                    "vendor": "nvidia",
                    "model": "h100",
                    "ram": "80Gi",
                    "interface": "SXM5",
                    "availability": {"total": 8, "available": 2},
                    "providerAvailability": {"total": 3, "available": 2},
                    "price": {"currency": "USD", "weightedAverage": 2.4, "med": 2.5},
                    "priceUakt": {"currency": "uakt", "weightedAverage": 4_000_000},
                }
            ]
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["instrument_id"] == "gpu:nvidia:h100:80Gi:SXM5"
    assert rows[0]["price_usd"] == 2.4
    assert rows[0]["quote_unit"] == "usd_per_gpu_hour"
    assert rows[0]["available_units"] == 2.0


def test_instrument_map_is_versioned_and_source_scoped():
    rows = instrument_map_rows("20260709T000000Z", "2026-07-09")
    assert {row["map_id"] for row in rows} >= {"uniswap_usdc_weth_5", "vast_h100_sxm"}
    assert all(row["mapping_version"] == "v1" for row in rows)
