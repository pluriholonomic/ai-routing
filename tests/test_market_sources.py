import asyncio
import json

import httpx
import pytest
from pyarrow.parquet import ParquetFile

from orcap.capture_markets import (
    _block_time,
    _capture_uniswap_rpc_logs,
    _configured_url,
    _cow_usdc_weth_execution_fields,
    _ethereum_rpc_config,
    _log_block_times,
    _union_table,
    _uniswap_quoter_calldata,
    _write,
    akash_capacity_rows,
    akash_gpu_quote_rows,
    akash_lease_execution_rows,
    akash_live_gpu_provider_ids,
    akash_market_list_url,
    akash_market_snapshot_metadata,
    akash_open_bid_rows,
    akash_registry_summary,
    capture_akash_open_market,
    chutes_capacity_rows,
    cow_amm_preblock_quote_rows,
    cow_competition_rows,
    cow_execution_rows,
    cow_rpc_log_rows,
    cow_rpc_participant_rows,
    defillama_participant_rows,
    geckoterminal_quote_rows,
    golem_capacity_rows,
    instrument_map_rows,
    uniswap_pool_specs,
    uniswap_quoter_impact_capacity_rows,
    uniswap_quoter_quote_rows,
    uniswap_rows,
    uniswap_rpc_log_rows,
)
from orcap.http import Fetcher


def test_defillama_rows_preserve_source_identity():
    rows = defillama_participant_rows(
        [{"id": "uniswap", "name": "Uniswap", "category": "Dexes", "tvl": 12.5}],
        "20260709T000000Z",
        "2026-07-09",
    )
    assert rows[0]["participant_id"] == "uniswap"
    assert rows[0]["value"] == 12.5


def test_blank_actions_url_override_uses_public_default(monkeypatch):
    monkeypatch.setenv("ORCAP_AKASH_NETWORK_URL", "")
    assert _configured_url("ORCAP_AKASH_NETWORK_URL", "https://public.example") == (
        "https://public.example"
    )


def test_ethereum_rpc_config_prefers_operator_endpoint_over_public_bounded_fallback(monkeypatch):
    monkeypatch.delenv("ORCAP_ETHEREUM_RPC_URL", raising=False)
    monkeypatch.setenv("ORCAP_PUBLIC_ETHEREUM_RPC_URL", "https://public.example")
    assert _ethereum_rpc_config() == (
        "https://public.example",
        "public:dRPC-bounded-live",
        "public_bounded_live",
    )
    monkeypatch.setenv("ORCAP_ETHEREUM_RPC_URL", "https://operator.example/key")
    assert _ethereum_rpc_config() == (
        "https://operator.example/key",
        "configured:ORCAP_ETHEREUM_RPC_URL",
        "operator_configured",
    )


def test_log_block_timestamps_are_available_only_when_provider_explicitly_supplies_them():
    times = _log_block_times(
        [
            {"blockNumber": "0x10", "blockTimestamp": "0x6a5094f7"},
            {"blockNumber": "0x11"},
        ]
    )
    assert times == {16: "2026-07-10T06:45:11Z"}


def test_uniswap_quoter_rows_keep_fixed_notional_simulation_distinct_from_depth():
    pool_id = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    spec = uniswap_pool_specs()[pool_id]
    calldata = _uniswap_quoter_calldata(spec, 1_000_000)
    assert calldata.startswith("0xc6a5026a")
    assert len(calldata) == 2 + 8 + 64 * 5

    result = "0x" + "".join(f"{value:064x}" for value in (500_000_000_000_000, 1, 2, 3))
    rows = uniswap_quoter_quote_rows(
        [
            {
                "pool_id": pool_id,
                "spec": spec,
                "block_number": 25500656,
                "input_bucket_usdc": 1,
                "amount_in_raw": 1_000_000,
                "result": result,
            }
        ],
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["price_usd"] is None
    assert rows[0]["pool_id"] == pool_id
    assert rows[0]["price_usdc_per_weth"] == 2000.0
    assert rows[0]["depth_usd"] is None
    assert rows[0]["finalized"] is True
    assert "not a fill guarantee" in rows[0]["quality_tier"]


def test_uniswap_quoter_impact_capacity_is_a_discrete_lower_bound_not_depth():
    pool_id = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    spec = uniswap_pool_specs()[pool_id]

    def result(amount_out_raw: int) -> str:
        return "0x" + f"{amount_out_raw:064x}"

    rows = uniswap_quoter_impact_capacity_rows(
        [
            {
                "pool_id": pool_id,
                "spec": spec,
                "block_number": 25500656,
                "amount_in_raw": 100 * 10**6,
                "result": result(50_000_000_000_000_000),
            },
            {
                "pool_id": pool_id,
                "spec": spec,
                "block_number": 25500656,
                "amount_in_raw": 1_000 * 10**6,
                "result": result(500_000_000_000_000_000),
            },
            {
                "pool_id": pool_id,
                "spec": spec,
                "block_number": 25500656,
                "amount_in_raw": 10_000 * 10**6,
                "result": result(4_500_000_000_000_000_000),
            },
        ],
        "20260710T000000Z",
        "2026-07-10",
    )
    by_target = {row["impact_target_bps"]: row for row in rows}
    assert by_target[100]["impact_capacity_lower_bound_usdc"] == 1_000.0
    assert by_target[500]["impact_capacity_lower_bound_usdc"] == 1_000.0
    assert "lower bound" in by_target[100]["quality_tier"]
    assert "not total liquidity" in by_target[100]["metric_definition"]


def test_cow_amm_preblock_rows_keep_parent_block_counterfactual_distinct_from_fill():
    pool_id = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    spec = uniswap_pool_specs()[pool_id]
    result = "0x" + "00000000000000000000000000000000000000000000000000038d7ea4c68000"
    rows = cow_amm_preblock_quote_rows(
        [
            {
                "reference_execution_id": "cow:0xabc:1",
                "reference_event_block_number": 25500000,
                "state_block_number": 25499999,
                "pool_id": pool_id,
                "spec": spec,
                "amount_in_raw": 2_000_000_000,
                "result": result,
            }
        ],
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["reference_execution_id"] == "cow:0xabc:1"
    assert rows[0]["state_block_number"] == 25499999
    assert rows[0]["input_amount"] == 2_000.0
    assert rows[0]["quote_unit"] == "usdc_per_weth"
    assert "not an intra-block quote" in rows[0]["quality_tier"]


def test_golem_capacity_keeps_hardware_metadata():
    rows = golem_capacity_rows(
        {"providers": [{"node_id": "n1", "data": {"golem.inf.cpu.cores": 8}}]},
        "20260709T000000Z",
        "2026-07-09",
    )
    assert rows[0]["participant_id"] == "n1"
    assert rows[0]["cpu_cores"] == 8.0


def test_chutes_capacity_is_active_deployment_configuration_not_available_capacity():
    rows = chutes_capacity_rows(
        {"data": [{"id": "Qwen/Qwen3-32B-TEE", "chute_id": "chute-1"}]},
        [
            {
                "chute_id": "chute-1",
                "node_selector": {"gpu_count": 8, "supported_gpus": ["pro_6000"]},
                "instances": [
                    {"active": True, "verified": True},
                    {"active": True, "verified": False},
                    {"active": False, "verified": True},
                ],
                "concurrency": 192,
                "invocation_count": 1000,
                "current_estimated_price": {"usd": {"hour": 14.4}},
                "preemptible": True,
            }
        ],
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["resource_id"] == "Qwen/Qwen3-32B-TEE"
    assert rows[0]["active_instances"] == 2
    assert rows[0]["verified_active_instances"] == 1
    assert rows[0]["total"] == 16.0
    assert rows[0]["available"] is None
    assert rows[0]["used"] is None
    assert "not available capacity" in rows[0]["metric_definition"]


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


def test_cow_latest_competition_is_live_solver_metadata_not_trade_execution():
    participants, events = cow_competition_rows(
        {
            "auctionId": 123,
            "auctionStartBlock": 10,
            "auctionDeadlineBlock": 12,
            "transactionHashes": ["0xtx"],
            "auction": {"orders": ["order-uid-a", "order-uid-b"]},
            "solutions": [
                {
                    "solverAddress": "0xSolverA",
                    "score": "10",
                    "ranking": 1,
                    "isWinner": True,
                    "filteredOut": False,
                    "txHash": "0xtx",
                    "orders": [{"id": "order-uid-a"}],
                },
                {
                    "solverAddress": "0xSolverB",
                    "score": "9",
                    "ranking": 2,
                    "isWinner": False,
                    "filteredOut": False,
                    "orders": [{"id": "order-uid-b"}],
                },
            ],
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert events[0]["event_id"] == "cow:solver-competition:123"
    assert events[0]["event_type"] == "solver_competition_snapshot"
    assert events[0]["event_time"] is None
    assert "order-uid-a" not in events[0]["record_json"]
    assert participants[0]["participant_id"] == "0xsolvera"
    assert participants[0]["auction_id"] == "123"
    assert participants[0]["value"] is None
    assert participants[0]["competition_score"] == 10.0
    assert "not market-wide trades" in participants[0]["quality_tier"]


def test_market_union_table_keeps_later_source_specific_columns(tmp_path):
    table = _union_table(
        [
            {"source": "defillama", "participant_id": "protocol", "value": 1.0},
            {
                "source": "cow",
                "participant_id": "solver",
                "competition_score": 2.0,
                "is_winner": True,
            },
        ]
    )
    assert table.column_names == [
        "competition_score",
        "is_winner",
        "participant_id",
        "source",
        "value",
    ]
    _write(table.to_pylist(), "market_participants", "20260710T000000Z", "2026-07-10", tmp_path)
    row = ParquetFile(
        tmp_path / "market_participants" / "dt=2026-07-10" / "20260710T000000Z.parquet"
    ).read().to_pylist()[1]
    assert row["competition_score"] == 2.0
    assert row["is_winner"] is True


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
    assert executions[0]["finalized"] is False


def _abi_word(value: int, *, signed: bool = False) -> str:
    return value.to_bytes(32, byteorder="big", signed=signed).hex()


def test_uniswap_rpc_logs_normalize_finalized_swaps_and_liquidity_events():
    specs = uniswap_pool_specs()
    pool = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    sender = "0x" + "11" * 20
    recipient = "0x" + "22" * 20

    def pad(address: str) -> str:
        return "0x" + "00" * 12 + address.removeprefix("0x")

    logs = [
        {
            "address": pool,
            "transactionHash": "0xabc",
            "logIndex": "0x2",
            "blockNumber": "0x7b",
            "blockHash": "0xblock",
            "topics": [
                "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67",
                pad(sender),
                pad(recipient),
            ],
            "data": "0x"
            + _abi_word(2_000_000, signed=True)
            + _abi_word(-1_000_000_000_000_000_000, signed=True)
            + _abi_word(123)
            + _abi_word(456)
            + _abi_word(-5, signed=True),
        },
        {
            "address": pool,
            "transactionHash": "0xdef",
            "logIndex": "0x3",
            "blockNumber": "0x7b",
            "blockHash": "0xblock",
            "topics": [
                "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde",
                pad(sender),
            ],
            "data": "0x" + _abi_word(100) + _abi_word(2_000_000) + _abi_word(10**18),
        },
    ]
    executions, events = uniswap_rpc_log_rows(
        logs,
        {123: "2026-07-10T00:00:00Z"},
        "20260710T000000Z",
        "2026-07-10",
        pool_specs=specs,
    )
    assert len(executions) == 1
    execution = executions[0]
    assert execution["finalized"] is True
    assert execution["execution_id"] == "uniswap:0xabc:2"
    assert execution["side"] == "token0_to_token1"
    assert execution["requested_size"] == 2.0
    assert execution["filled_size"] == 1.0
    assert execution["native_price"] == 0.5
    assert execution["participant_id"] == sender
    assert {event["event_type"] for event in events} == {"swap", "liquidity_mint"}
    assert all(event["finalized"] is True for event in events)


def test_uniswap_rpc_capture_uses_a_bounded_finalized_window_and_redacts_url(monkeypatch):
    monkeypatch.setenv("ORCAP_ETHEREUM_FINALITY_BLOCKS", "64")
    monkeypatch.setenv("ORCAP_UNISWAP_LOG_WINDOW_BLOCKS", "3")
    requests = []

    async def run():
        async def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if payload["method"] == "eth_blockNumber":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x100"})
            assert payload["method"] == "eth_getLogs"
            query = payload["params"][0]
            assert query["fromBlock"] == "0xbe"
            assert query["toBlock"] == "0xc0"
            assert len(query["address"]) == 2
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = Fetcher(client)
            logs, block_times, detail = await _capture_uniswap_rpc_logs(
                fetcher, "https://rpc.example/secret-key"
            )
        return logs, block_times, detail, fetcher.records

    logs, block_times, detail, records = asyncio.run(run())
    assert len(requests) == 2
    assert logs == []
    assert block_times == {}
    assert detail["finalized_through_block"] == 192
    assert detail["from_block"] == 190
    assert detail["recent_bounded_only"] is False
    assert {record["url"] for record in records} == {"configured:ORCAP_ETHEREUM_RPC_URL"}


def test_cow_rpc_logs_match_solver_only_from_same_transaction_settlement_event():
    owner = "0x" + "11" * 20
    solver = "0x" + "22" * 20
    sell_token = "0x" + "aa" * 20
    buy_token = "0x" + "bb" * 20

    def pad(address: str) -> str:
        return "0x" + "00" * 12 + address.removeprefix("0x")

    order_uid = "01" * 56
    trade_data = (
        _abi_word(int(sell_token, 16))
        + _abi_word(int(buy_token, 16))
        + _abi_word(2_000_000)
        + _abi_word(10**18)
        + _abi_word(0)
        + _abi_word(192)
        + _abi_word(56)
        + order_uid.ljust(64 * 2, "0")
    )
    logs = [
        {
            "transactionHash": "0xtx",
            "logIndex": "0x1",
            "blockNumber": "0x7b",
            "blockHash": "0xblock",
            "topics": [
                "0xa07a543ab8a018198e99ca0184c93fe9050a79400a0a723441f84de1d972cc17",
                pad(owner),
            ],
            "data": "0x" + trade_data,
        },
        {
            "transactionHash": "0xtx",
            "logIndex": "0x2",
            "blockNumber": "0x7b",
            "blockHash": "0xblock",
            "topics": [
                "0x40338ce1a7c49204f0099533b1e9a7ee0a3d261f84974ab7af36105b8c4e9db4",
                pad(solver),
            ],
            "data": "0x",
        },
    ]
    executions, events = cow_rpc_log_rows(
        logs, {123: "2026-07-10T00:00:00Z"}, "20260710T000000Z", "2026-07-10"
    )
    assert len(executions) == 1
    execution = executions[0]
    assert execution["finalized"] is True
    assert execution["participant_id"] == owner
    assert execution["solver_id"] == solver
    assert execution["sell_amount_raw"] == "2000000"
    assert execution["buy_amount_raw"] == str(10**18)
    assert {event["event_type"] for event in events} == {"trade", "settlement"}
    participant_rows = cow_rpc_participant_rows(executions)
    assert participant_rows[0]["participant_id"] == solver


def test_cow_usdc_weth_cohort_uses_registered_decimals_and_never_labels_the_quote_usd():
    usdc_to_weth = _cow_usdc_weth_execution_fields(
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        2_000_000_000,
        10**18,
    )
    weth_to_usdc = _cow_usdc_weth_execution_fields(
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        10**18,
        1_900_000_000,
    )
    assert usdc_to_weth == {
        "instrument_id": "ethereum:USDC/WETH",
        "side": "usdc_to_weth",
        "requested_size": 2_000.0,
        "filled_size": 1.0,
        "native_price": 0.0005,
        "price_usdc_per_weth": 2_000.0,
        "price_unit": "usdc_per_weth",
        "metric_definition": usdc_to_weth["metric_definition"],
    }
    assert weth_to_usdc["side"] == "weth_to_usdc"
    assert weth_to_usdc["price_usdc_per_weth"] == 1_900.0
    assert "stablecoin-peg-adjusted USD price" in usdc_to_weth["metric_definition"]


def test_geckoterminal_rows_preserve_indexed_state_boundary():
    rows = geckoterminal_quote_rows(
        {
            "0xpool": {
                "data": {
                    "id": "eth_0xpool",
                    "attributes": {
                        "dex_id": "uniswap_v3",
                        "base_token_price_usd": "2000",
                        "quote_token_price_usd": "1",
                        "reserve_in_usd": "1200000",
                        "volume_usd": {"m5": "5", "h1": "60", "h24": "1440"},
                    },
                }
            }
        },
        "20260710T000000Z",
        "2026-07-10",
    )
    assert rows[0]["price_usd"] == 2000.0
    assert rows[0]["depth_usd"] == 1_200_000.0
    assert "not executable depth" in rows[0]["quality_tier"]


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


def test_akash_open_market_rows_keep_block_pinned_gpu_bids_distinct_from_execution():
    snapshot = akash_market_snapshot_metadata(
        {"block": {"header": {"height": "27652334", "time": "2026-07-10T09:51:37Z"}}}
    )
    assert snapshot == {"height": "27652334", "time": "2026-07-10T09:51:37Z"}
    bid_records = [
        {
            "bid": {
                "id": {
                    "owner": "tenant",
                    "dseq": "1",
                    "gseq": 2,
                    "oseq": 3,
                    "provider": "p",
                    "bseq": 0,
                },
                "state": "open",
                "price": {"denom": "uact", "amount": "4.5"},
                "resources_offer": [
                    {
                        "count": 2,
                        "resources": {
                            "gpu": {
                                "units": {"val": "1"},
                                "attributes": [
                                    {"key": "vendor/nvidia/model/h100", "value": "true"}
                                ],
                            },
                            "cpu": {"units": {"val": "16000"}},
                            "memory": {"quantity": {"val": "34359738368"}},
                        },
                    }
                ],
            }
        }
    ]
    bid = akash_open_bid_rows(bid_records, snapshot, "20260710T000000Z", "2026-07-10")[0]
    assert bid["gpu_units_total"] == 2.0
    assert bid["bid_id"] == "tenant/1/2/3/p/0"
    assert bid["snapshot_height"] == "27652334"
    assert bid["native_price_unit"] == "native_per_block"
    assert "not an executed lease" in bid["metric_definition"]


def test_akash_open_market_url_requires_known_book_side_and_encodes_page_cursor():
    url = akash_market_list_url(
        "bids",
        filters={"filters.state": "open", "filters.provider": "provider-a"},
        page_key="a+/=",
    )
    assert "filters.state=open" in url
    assert "filters.provider=provider-a" in url
    assert "pagination.key=a%2B%2F%3D" in url
    with pytest.raises(ValueError, match="bids or orders"):
        akash_market_list_url("leases", filters={"filters.state": "open"})
    with pytest.raises(ValueError, match="restrict state"):
        akash_market_list_url("bids", filters={"filters.state": "closed"})


def test_akash_live_gpu_provider_ids_follow_the_existing_live_capacity_filter():
    providers = akash_live_gpu_provider_ids(
        {
            "providers": [
                {
                    "owner": "live-gpu",
                    "isOnline": True,
                    "isValidVersion": True,
                    "stats": {"gpu": {"total": 2}},
                },
                {
                    "owner": "offline-gpu",
                    "isOnline": False,
                    "isValidVersion": True,
                    "stats": {"gpu": {"total": 2}},
                },
            ]
        }
    )
    assert providers == ["live-gpu"]


def test_akash_provider_filtered_bid_capture_pins_all_queries_to_one_block():
    class Fetcher:
        def __init__(self):
            self.calls = []

        async def get_json(self, url, headers=None):
            self.calls.append((url, headers))
            if "blocks/latest" in url:
                return {"block": {"header": {"height": "42", "time": "2026-07-10T00:00:00Z"}}}
            return {
                "bids": [
                    {
                        "bid": {
                            "id": {
                                "owner": "tenant",
                                "dseq": "1",
                                "gseq": 1,
                                "oseq": 1,
                                "provider": "provider-a",
                                "bseq": 0,
                            },
                            "state": "open",
                        }
                    }
                ],
                "pagination": {"next_key": None},
            }

    fetcher = Fetcher()
    bids, detail = asyncio.run(capture_akash_open_market(fetcher, ["provider-a"]))
    assert len(bids) == 1
    assert detail["coverage_complete"] is True
    assert detail["snapshot_height"] == "42"
    assert fetcher.calls[1][1] == {"x-cosmos-block-height": "42"}
    assert "filters.provider=provider-a" in fetcher.calls[1][0]


def test_akash_provider_bid_capture_discards_everything_when_one_provider_fails():
    class Fetcher:
        async def get_json(self, url, headers=None):
            if "blocks/latest" in url:
                return {"block": {"header": {"height": "42", "time": "2026-07-10T00:00:00Z"}}}
            return None if "provider-b" in url else {"bids": [], "pagination": {}}

    bids, detail = asyncio.run(capture_akash_open_market(Fetcher(), ["provider-a", "provider-b"]))
    assert bids == []
    assert detail["coverage_complete"] is False
    assert detail["reason"] == "provider_bid_pagination_incomplete"


def test_instrument_map_is_versioned_and_source_scoped():
    rows = instrument_map_rows("20260709T000000Z", "2026-07-09")
    assert {row["map_id"] for row in rows} >= {"uniswap_usdc_weth_5", "vast_h100_sxm"}
    assert all(row["mapping_version"] == "v1" for row in rows)
