"""Capture the source-backed DeFi and decentralized-compute comparison layer.

Public sources are collected immediately; source-specific credentials only
unlock the canonical Uniswap Graph query and an operator-selected Akash
network-data endpoint.  Missing credentials are written as ``skipped`` source
runs, never mistaken for a quiet market.
"""

import asyncio
import base64
import json
import logging
import os
import re
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import Fetcher, make_client, write_raw
from .observability import write_source_run

log = logging.getLogger(__name__)

DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"
GOLEM_ONLINE_URL = "https://api.stats.golem.network/v1/network/online"
COW_SOLVER_COMPETITION_LATEST_URL = "https://api.cow.fi/mainnet/api/v2/solver_competition/latest"
AKASH_CONSOLE_PROVIDERS_URL = "https://console-api.akash.network/v1/providers"
AKASH_GPU_PRICES_URL = "https://console-api.akash.network/v1/gpu-prices"
AKASH_LEASES_URL = (
    "https://console-api.akash.network/akash/market/v1beta5/leases/list"
    "?pagination.limit=50&pagination.reverse=true"
)
AKASH_DASHBOARD_URL = "https://console-api.akash.network/v1/dashboard-data"
AKASH_NETWORK_CAPACITY_URL = "https://console-api.akash.network/v1/network-capacity"
AKASH_PROVIDER_ACTIVE_LEASES_GRAPH_URL = (
    "https://console-api.akash.network/v1/providers/{provider}/active-leases-graph-data"
)
AKASH_PROVIDER_DASHBOARD_URL = "https://console-api.akash.network/v1/provider-dashboard/{provider}"
DEFAULT_AKASH_PROVIDER_HISTORY_DAYS = 8
AKASH_RPC_URL = "https://rpc.akashnet.net:443"
AKASH_MARKET_API_URL = "https://api.akashnet.net/akash/market/v1beta5"
AKASH_LATEST_BLOCK_URL = "https://api.akashnet.net/cosmos/base/tendermint/v1beta1/blocks/latest"
NOSANA_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
NOSANA_NODES_PROGRAM_ID = "nosNeZR64wiEhQc5j251bsP4WqDabT6hmz4PHyoHLGD"
NOSANA_EXPLORE_API_URL = "https://dashboard.k8s.prd.nos.ci/api"
NOSANA_JOB_ACTIVITY_PERIOD_SECONDS = 86_400
AETHIR_SUPPLY_DASHBOARD_URL = "https://dashboard.aethir.com/protocol/supply-metric"
AETHIR_DEMAND_DASHBOARD_URL = "https://dashboard.aethir.com/protocol/demand-metric"
# The documented Anchor discriminator for Nosana's NodeAccount. The base58
# form is required by Solana's public ``getProgramAccounts`` memcmp filter.
NOSANA_NODE_ACCOUNT_DISCRIMINATOR = bytes.fromhex("7da61292c37f56dc")
NOSANA_NODE_ACCOUNT_DISCRIMINATOR_BASE58 = "N1x6kpVdXxo"
AKASH_MARKET_PAGE_SIZE = max(1, int(os.environ.get("ORCAP_AKASH_MARKET_PAGE_SIZE", "1000")))
AKASH_MARKET_MAX_PAGES = max(1, int(os.environ.get("ORCAP_AKASH_MARKET_MAX_PAGES", "25")))
AKASH_CHOICE_MAX_ORDERS = max(
    1, int(os.environ.get("ORCAP_AKASH_CHOICE_MAX_ORDERS", "25"))
)
AKASH_BID_EVENT_LOOKBACK_BLOCKS = max(
    100, int(os.environ.get("ORCAP_AKASH_BID_EVENT_LOOKBACK_BLOCKS", "1000"))
)
AKASH_CLOSE_EVENT_LOOKBACK_BLOCKS = max(
    100, int(os.environ.get("ORCAP_AKASH_CLOSE_EVENT_LOOKBACK_BLOCKS", "1000"))
)
AKASH_BID_EVENT_PAGE_SIZE = 100
AKASH_BID_EVENT_MAX_PAGES = 10
GECKOTERMINAL_POOL_URL = "https://api.geckoterminal.com/api/v2/networks/eth/pools/{pool_id}"
CHUTES_MODELS_URL = "https://llm.chutes.ai/v1/models"
CHUTES_DETAIL_URL = "https://api.chutes.ai/chutes/{chute_id}"
GECKOTERMINAL_POOLS = (
    "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
    "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8",
)
GRAPH_GATEWAY = "https://gateway.thegraph.com/api/{key}/subgraphs/id/{subgraph_id}"
INSTRUMENTS_PATH = Path(__file__).resolve().parents[2] / "config" / "instruments.toml"
UNISWAP_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
UNISWAP_V3_MINT_TOPIC = "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"
UNISWAP_V3_BURN_TOPIC = "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c"
DEFAULT_ETHEREUM_FINALITY_BLOCKS = 64
# The market workflow runs hourly. Ethereum has recently advanced ~400 blocks
# per hour, so this must materially overlap adjacent runs rather than merely
# sample a recent slice. 1024 blocks is roughly 2--2.5 hours at observed
# cadence and remains within the validated public dRPC response envelope.
DEFAULT_UNISWAP_LOG_WINDOW_BLOCKS = 1024
DEFAULT_COW_LOG_WINDOW_BLOCKS = 1024
DEFAULT_COW_AMM_COUNTERFACTUAL_BATCH_SIZE = 100
GPV2_SETTLEMENT_ADDRESS = "0x9008d19f58aabd9ed0d60971565aa8510560ab41"
GPV2_TRADE_TOPIC = "0xa07a543ab8a018198e99ca0184c93fe9050a79400a0a723441f84de1d972cc17"
GPV2_SETTLEMENT_TOPIC = "0x40338ce1a7c49204f0099533b1e9a7ee0a3d261f84974ab7af36105b8c4e9db4"
PUBLIC_ETHEREUM_RPC_URL = "https://eth.drpc.org"
USDC_ADDRESS = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
UNISWAP_V3_QUOTER_V2_ADDRESS = "0x61ffe014ba17989e743c5f6cb21bf9697530b21e"
UNISWAP_V3_QUOTE_EXACT_INPUT_SINGLE_SELECTOR = "c6a5026a"
UNISWAP_V3_MULTICALL2_ADDRESS = "0x5ba1e12693dc8f9c48aad8770482f4739beed696"
UNISWAP_V3_TICK_LENS_ADDRESS = "0xbfd8137f7d1516d3ea5ca83523914859ec47f573"
UNISWAP_V3_MULTICALL2_AGGREGATE_SELECTOR = "252dba42"
UNISWAP_V3_TICK_LENS_SELECTOR = "351fb478"
UNISWAP_V3_TICK_SPACING_SELECTOR = "d0c93a7c"
UNISWAP_V3_SLOT0_SELECTOR = "3850c7bd"
UNISWAP_V3_LIQUIDITY_SELECTOR = "1a686502"
UNISWAP_V3_MIN_TICK = -887272
UNISWAP_V3_MAX_TICK = 887272
DEFAULT_UNISWAP_TICK_BOOK_BATCH_WORDS = 25
DEFAULT_UNISWAP_TICK_BOOK_MAX_ROWS_PER_POOL = 100_000
# These are deliberately a sparse, bounded ladder.  A derived capacity point
# is a lower bound at a declared all-in price-deterioration threshold, not a
# claim to have reconstructed the full V3 tick book or a firm fillable quote.
UNISWAP_USDC_QUOTE_BUCKETS = (100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000)
UNISWAP_USDC_IMPACT_TARGET_BPS = (100, 500)


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _configured_url(name: str, default: str) -> str:
    """Use the public default when Actions injects an empty optional variable."""
    return os.environ.get(name) or default


def _ethereum_rpc_config() -> tuple[str, str, str]:
    """Choose an operator RPC when present, otherwise a bounded public feed.

    The public endpoint is deliberately only a recent-window monitor. It must
    never be used as an archive/backfill source, and its raw provenance remains
    distinct from a configured provider URL that may include credentials.
    """
    configured = os.environ.get("ORCAP_ETHEREUM_RPC_URL")
    if configured:
        return configured, "configured:ORCAP_ETHEREUM_RPC_URL", "operator_configured"
    public = os.environ.get("ORCAP_PUBLIC_ETHEREUM_RPC_URL") or PUBLIC_ETHEREUM_RPC_URL
    return public, "public:dRPC-bounded-live", "public_bounded_live"


def _bounded_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    """Read a bounded integer environment setting without accepting nonsense."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _hex_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value, 16) if value.startswith("0x") else int(value)
    except ValueError:
        return None


def _hex_quantity(value: int) -> str:
    return hex(value)


def _abi_address(value: str) -> str:
    normalized = value.lower().removeprefix("0x")
    if len(normalized) != 40:
        raise ValueError("Ethereum address must have 20 bytes")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError("Ethereum address must be hexadecimal") from exc
    return normalized.rjust(64, "0")


def _abi_uint(value: int, *, bits: int = 256) -> str:
    if not isinstance(value, int) or not 0 <= value < 2**bits:
        raise ValueError(f"unsigned {bits}-bit ABI value is out of range")
    return f"{value:064x}"


def _abi_int(value: int, *, bits: int = 256) -> str:
    """Encode one bounded signed ABI integer with a full 32-byte word."""
    if not isinstance(value, int) or not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
        raise ValueError(f"signed {bits}-bit ABI value is out of range")
    return f"{value % 2**256:064x}"


def _word(data: Any, index: int) -> int | None:
    """Decode a 32-byte ABI word from a hexadecimal event-data string."""
    if not isinstance(data, str):
        return None
    value = data.removeprefix("0x")
    start, end = index * 64, (index + 1) * 64
    if len(value) < end:
        return None
    try:
        return int(value[start:end], 16)
    except ValueError:
        return None


def _signed_word(data: Any, index: int) -> int | None:
    value = _word(data, index)
    if value is None:
        return None
    return value - (1 << 256) if value >= (1 << 255) else value


def _address_word(data: Any, index: int) -> str | None:
    value = _word(data, index)
    return f"0x{value:040x}" if value is not None else None


def _dynamic_bytes(data: Any, offset_index: int) -> str | None:
    """Decode a dynamic ABI bytes value while retaining its literal hex form."""
    offset = _word(data, offset_index)
    if offset is None or offset % 32:
        return None
    length = _word(data, offset // 32)
    if length is None:
        return None
    value = str(data).removeprefix("0x")
    start, end = (offset + 32) * 2, (offset + 32 + length) * 2
    if len(value) < end:
        return None
    return "0x" + value[start:end]


def _uniswap_tick_lens_calldata(pool_id: str, word_position: int) -> str:
    """Encode TickLens's one-word populated-tick view call."""
    return (
        "0x"
        + UNISWAP_V3_TICK_LENS_SELECTOR
        + _abi_address(pool_id)
        + _abi_int(word_position, bits=16)
    )


def _multicall2_aggregate_calldata(calls: list[tuple[str, str]]) -> str:
    """Encode Multicall2 aggregate((address,bytes)[]) without a web3 dependency."""
    if not calls:
        raise ValueError("Multicall2 aggregate requires at least one call")
    encoded_calls = []
    for target, calldata in calls:
        data = calldata.removeprefix("0x")
        if len(data) % 2:
            raise ValueError("Multicall calldata must contain complete bytes")
        try:
            int(data or "0", 16)
        except ValueError as exc:
            raise ValueError("Multicall calldata must be hexadecimal") from exc
        padded = data.ljust(((len(data) + 63) // 64) * 64, "0")
        encoded_calls.append(
            _abi_address(target) + _abi_uint(64) + _abi_uint(len(data) // 2) + padded
        )
    offsets, position = [], 32 * len(encoded_calls)
    for encoded in encoded_calls:
        offsets.append(_abi_uint(position))
        position += len(encoded) // 2
    # The top-level function argument is one dynamic array. Within that array,
    # offsets to each dynamic tuple are relative to the array payload after its
    # length word, as specified by the ABI's tuple encoding rule.
    return (
        "0x"
        + UNISWAP_V3_MULTICALL2_AGGREGATE_SELECTOR
        + _abi_uint(32)
        + _abi_uint(len(encoded_calls))
        + "".join(offsets)
        + "".join(encoded_calls)
    )


def _multicall2_aggregate_result(data: Any) -> tuple[int, list[str]] | None:
    """Decode Multicall2's ``(uint256 blockNumber, bytes[] returnData)`` result."""
    block_number, array_offset = _word(data, 0), _word(data, 1)
    if block_number is None or array_offset is None or array_offset % 32:
        return None
    array_word = array_offset // 32
    count = _word(data, array_word)
    if count is None or count > 10_000:
        return None
    head_start = array_offset + 32
    values = []
    for index in range(count):
        relative_offset = _word(data, array_word + 1 + index)
        if relative_offset is None or relative_offset % 32:
            return None
        item_start = head_start + relative_offset
        item_word = item_start // 32
        length = _word(data, item_word)
        if length is None:
            return None
        raw = str(data).removeprefix("0x")
        start, end = (item_start + 32) * 2, (item_start + 32 + length) * 2
        if len(raw) < end:
            return None
        values.append("0x" + raw[start:end])
    return block_number, values


def _tick_lens_populated_ticks(data: Any) -> list[dict[str, int]] | None:
    """Decode TickLens's dynamic ``PopulatedTick[]`` output for one bitmap word."""
    offset = _word(data, 0)
    if offset is None or offset % 32:
        return None
    start_word = offset // 32
    count = _word(data, start_word)
    # A bitmap word has exactly 256 positions, so more records is malformed.
    if count is None or count > 256:
        return None
    result = []
    for index in range(count):
        tick = _signed_word(data, start_word + 1 + 3 * index)
        liquidity_net = _signed_word(data, start_word + 2 + 3 * index)
        liquidity_gross = _word(data, start_word + 3 + 3 * index)
        if tick is None or liquidity_net is None or liquidity_gross is None:
            return None
        result.append(
            {
                "tick": tick,
                "liquidity_net_raw": liquidity_net,
                "liquidity_gross_raw": liquidity_gross,
            }
        )
    return result


def _topic_address(topics: Any, index: int) -> str | None:
    if not isinstance(topics, list) or len(topics) <= index or not isinstance(topics[index], str):
        return None
    value = topics[index].removeprefix("0x")
    if len(value) != 64:
        return None
    return "0x" + value[-40:].lower()


def _ethereum_block_time(body: Any) -> str | None:
    """Read an EVM block timestamp without pretending a missing one is zero."""
    if not isinstance(body, dict):
        return None
    timestamp = _hex_int(body.get("timestamp"))
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _log_block_times(logs: list[dict[str, Any]]) -> dict[int, str]:
    """Read explicit provider-supplied block timestamps from log records.

    Standard Ethereum logs do not carry a timestamp, but some public RPCs add
    ``blockTimestamp``. It is used only as a fallback when a canonical
    ``eth_getBlockByNumber`` lookup is unavailable; logs with no explicit
    timestamp remain time-unidentified.
    """
    result = {}
    for log_row in logs:
        block_number = _hex_int(log_row.get("blockNumber"))
        timestamp = _hex_int(log_row.get("blockTimestamp"))
        if block_number is None or timestamp is None:
            continue
        result[block_number] = (
            datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")
        )
    return result


def uniswap_pool_specs() -> dict[str, dict[str, Any]]:
    """Load the checked-in, exact-token metadata for registered V3 pools."""
    with INSTRUMENTS_PATH.open("rb") as handle:
        instruments = tomllib.load(handle)["instruments"]
    result: dict[str, dict[str, Any]] = {}
    required = (
        "source_id",
        "canonical_instrument",
        "quality_tier",
        "token0_address",
        "token1_address",
        "fee",
    )
    for map_id, raw in instruments.items():
        if raw.get("source") != "uniswap":
            continue
        missing = [field for field in required if not raw.get(field)]
        if missing:
            raise ValueError(f"Uniswap instrument {map_id} missing: {', '.join(missing)}")
        try:
            decimals = (int(raw["token0_decimals"]), int(raw["token1_decimals"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Uniswap instrument {map_id} needs token decimals") from exc
        if any(value < 0 or value > 36 for value in decimals):
            raise ValueError(f"Uniswap instrument {map_id} has invalid token decimals")
        try:
            fee = int(raw["fee"])
            if not 0 < fee < 2**24:
                raise ValueError
            token0_address = "0x" + _abi_address(str(raw["token0_address"]))[-40:]
            token1_address = "0x" + _abi_address(str(raw["token1_address"]))[-40:]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Uniswap instrument {map_id} has invalid token addresses or fee"
            ) from exc
        address = str(raw["source_id"]).lower()
        result[address] = {
            "map_id": map_id,
            "canonical_instrument": str(raw["canonical_instrument"]),
            "quality_tier": str(raw["quality_tier"]),
            "token0_symbol": str(raw.get("token0_symbol") or "token0"),
            "token0_decimals": decimals[0],
            "token0_address": token0_address,
            "token1_symbol": str(raw.get("token1_symbol") or "token1"),
            "token1_decimals": decimals[1],
            "token1_address": token1_address,
            "fee": fee,
        }
    return result


def _as_list(value: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if not isinstance(value, dict):
        return []
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, list):
            return [x for x in candidate if isinstance(x, dict)]
        if isinstance(candidate, dict):
            return [x for x in candidate.values() if isinstance(x, dict)]
    return []


def defillama_participant_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    for item in _as_list(body, "protocols", "data"):
        source_id = str(item.get("id") or item.get("slug") or item.get("name") or "")
        if not source_id:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "defillama",
                "venue": item.get("category") or "protocol",
                "participant_id": source_id,
                "participant_name": item.get("name"),
                "instrument_id": item.get("chain") or "all",
                "metric": "tvl_usd",
                "value": _float(item.get("tvl")),
                "quality_tier": "aggregate",
                "record_json": _json(item),
            }
        )
    return rows


def golem_capacity_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    records = _as_list(body, "providers", "data", "online")
    if not records and isinstance(body, dict):
        records = [
            value
            for value in body.values()
            if isinstance(value, dict) and ("node_id" in value or "data" in value)
        ]
    rows = []
    for item in records:
        attrs = item.get("data") if isinstance(item.get("data"), dict) else item
        participant = item.get("node_id") or attrs.get("id")
        if not participant:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "golem",
                "venue": "golem-network",
                "participant_id": participant,
                "resource_id": attrs.get("golem.runtime.name") or "compute",
                "available": 1.0,
                "total": 1.0,
                "used": None,
                "cpu_cores": _float(attrs.get("golem.inf.cpu.cores")),
                "gpu_count": _float(attrs.get("golem.inf.gpu.count")),
                "memory_gib": _float(attrs.get("golem.inf.mem.gib")),
                "region": attrs.get("golem.inf.location.country"),
                "quality_tier": "provider-reported",
                "record_json": _json(item),
            }
        )
    return rows


def nosana_node_registry_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize Nosana's public on-chain NodeAccount registry state.

    Registration is a declared hardware profile, not a liveness check, current
    workload, free capacity, job completion, GPU model, or price. Preserve
    those distinctions by retaining the declared values in a dedicated table
    instead of treating a registered node as immediately rentable supply.
    """
    accounts = body.get("result") if isinstance(body, dict) else None
    if not isinstance(accounts, list):
        return []
    rows = []
    for item in accounts:
        if not isinstance(item, dict):
            continue
        account = item.get("account") if isinstance(item.get("account"), dict) else {}
        encoded = account.get("data") if isinstance(account.get("data"), list) else []
        if not encoded or not isinstance(encoded[0], str):
            continue
        try:
            raw = base64.b64decode(encoded[0], validate=True)
        except (ValueError, TypeError):
            continue
        # The documented fixed header ends at storage; variable strings follow.
        if len(raw) < 54 or raw[:8] != NOSANA_NODE_ACCOUNT_DISCRIMINATOR:
            continue
        audited_raw = raw[40]
        if audited_raw not in (0, 1):
            continue
        participant_id = str(item.get("pubkey") or "")
        if not participant_id:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "nosana",
                "venue": "nosana-node-registry",
                "participant_id": participant_id,
                "audited": bool(audited_raw),
                "architecture_type": raw[41],
                "country_code": int.from_bytes(raw[42:44], "little"),
                "declared_cpu_cores": int.from_bytes(raw[44:46], "little"),
                "declared_gpu_value": int.from_bytes(raw[46:48], "little"),
                "declared_memory_gb": int.from_bytes(raw[48:50], "little"),
                "declared_iops": int.from_bytes(raw[50:52], "little"),
                "declared_storage_gb": int.from_bytes(raw[52:54], "little"),
                "snapshot_slot": body.get("context", {}).get("slot")
                if isinstance(body.get("context"), dict)
                else None,
                "quality_tier": "onchain-node-registry; declared hardware profile",
                "metric_definition": (
                    "Nosana NodeAccount fields declared at registration. They do not identify "
                    "node liveness, available GPUs, GPU model, utilization, posted price, "
                    "executed jobs, or delivered compute."
                ),
                "record_json": _json(item),
            }
        )
    return rows


async def capture_nosana_node_registry(
    fetcher: Fetcher,
    *,
    url: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Fetch a bounded public Solana NodeAccount registry snapshot.

    ``getProgramAccounts`` is block-pinned by the returned context slot. The
    request asks only for the fixed 54-byte header; it deliberately excludes
    variable endpoint strings and does not touch the authenticated Nosana API.
    """
    rpc_url = _configured_url("ORCAP_NOSANA_SOLANA_RPC_URL", url or NOSANA_SOLANA_RPC_URL)
    body = await fetcher.post_json(
        rpc_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getProgramAccounts",
            "params": [
                NOSANA_NODES_PROGRAM_ID,
                {
                    "encoding": "base64",
                    "withContext": True,
                    "dataSlice": {"offset": 0, "length": 54},
                    "filters": [
                        {
                            "memcmp": {
                                "offset": 0,
                                "bytes": NOSANA_NODE_ACCOUNT_DISCRIMINATOR_BASE58,
                            }
                        }
                    ],
                },
            ],
        },
        record_url="public:solana-mainnet-nosana-node-registry",
    )
    if not isinstance(body, dict):
        return body, {"query_succeeded": False, "error": "no JSON-RPC response"}
    if isinstance(body.get("error"), dict):
        return body, {
            "query_succeeded": False,
            "error": str(body["error"].get("message") or "JSON-RPC error"),
        }
    result = body.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("value"), list):
        return body, {"query_succeeded": False, "error": "malformed getProgramAccounts result"}
    normalized = {"context": result.get("context"), "result": result["value"]}
    return normalized, {
        "query_succeeded": True,
        "snapshot_slot": (
            result.get("context", {}).get("slot")
            if isinstance(result.get("context"), dict)
            else None
        ),
        "account_records_fetched": len(result["value"]),
        "program_id": NOSANA_NODES_PROGRAM_ID,
        "account_discriminator": NOSANA_NODE_ACCOUNT_DISCRIMINATOR.hex(),
        "data_slice_bytes": 54,
        "metric_boundary": (
            "registered declared node hardware only; not online availability, GPU model, "
            "price, utilization, jobs, or delivered capacity"
        ),
    }


def _nosana_activity_points(body: Any) -> list[dict[str, int | float]]:
    """Retain only public aggregate time buckets with numeric coordinates."""
    if not isinstance(body, dict) or _float(body.get("total")) is None:
        return []
    points = body.get("data")
    if not isinstance(points, list):
        return []
    rows = []
    for point in points:
        if not isinstance(point, dict):
            continue
        bucket_ms, value = _integer(point.get("x")), _float(point.get("y"))
        if bucket_ms is None or bucket_ms <= 0 or value is None or value < 0:
            continue
        rows.append({"x": bucket_ms, "y": value})
    return rows


def nosana_job_activity_rows(
    body: Any,
    run_ts: str,
    dt: str,
) -> list[dict[str, Any]]:
    """Normalize Nosana's public aggregate job monitor without job metadata.

    The Explore API's individual-job endpoint includes public job definitions
    and participant addresses. This collector intentionally never calls that
    endpoint. It retains only aggregate state counts, public market-level
    running totals, and source-reported rolling aggregate buckets.
    """
    if not isinstance(body, dict):
        return []
    stats = body.get("stats") if isinstance(body.get("stats"), dict) else {}
    counts = body.get("counts") if isinstance(body.get("counts"), dict) else {}
    by_state = counts.get("byState") if isinstance(counts.get("byState"), dict) else {}
    running = body.get("running") if isinstance(body.get("running"), dict) else {}
    period = _integer(body.get("period_seconds"))
    retrieved = _integer(stats.get("retrieved"))
    rows = []
    common = {
        "run_ts": run_ts,
        "dt": dt,
        "source": "nosana_jobs_api",
        "venue": "nosana-explore-aggregate-api",
        "requested_period_seconds": period,
        "retrieved_unix_seconds": retrieved,
        "quality_tier": "public aggregate indexer; source-defined job activity",
    }

    def emit(
        metric: str,
        value: Any,
        *,
        observation_type: str,
        market_id: str | None = None,
        bucket_unix_ms: int | None = None,
        source_total: float | None = None,
        definition: str,
        record: Any,
    ) -> None:
        number = _float(value)
        if number is None or number < 0:
            return
        rows.append(
            common
            | {
                "metric": metric,
                "value": number,
                "observation_type": observation_type,
                "market_id": market_id,
                "source_bucket_unix_ms": bucket_unix_ms,
                "source_total": source_total,
                "metric_definition": definition,
                "record_json": _json(record),
            }
        )

    for field, metric, definition in (
        (
            "completed",
            "source_reported_indexer_completed_jobs",
            "Nosana Explore aggregate indexer completed-job count; not LLM requests or tokens.",
        ),
        (
            "duration",
            "source_reported_indexer_job_duration_seconds",
            "Nosana Explore aggregate indexer job duration in seconds; not independently "
            "verified GPU-hours, delivered compute, or utilization.",
        ),
        (
            "price",
            "source_reported_indexer_price_value",
            "Nosana Explore aggregate indexer price field in its source-defined units; not a "
            "USD clearing price, realized revenue, or a comparable GPU-hour rate.",
        ),
        (
            "usdReward",
            "source_reported_indexer_usd_reward",
            "Nosana Explore indexer-derived USD reward field; not independently verified "
            "revenue, payment, profit, or a cross-market clearing price.",
        ),
    ):
        emit(
            metric,
            stats.get(field),
            observation_type="aggregate_snapshot",
            definition=definition,
            record={"endpoint": "/jobs/stats", "field": field, "value": stats.get(field)},
        )
    emit(
        "source_reported_indexer_total_jobs",
        counts.get("total"),
        observation_type="aggregate_snapshot",
        definition=(
            "Nosana Explore aggregate indexer job-account count; not active demand or fills."
        ),
        record={"endpoint": "/jobs/count", "field": "total", "value": counts.get("total")},
    )
    for state in ("QUEUED", "RUNNING", "COMPLETED", "STOPPED"):
        emit(
            f"source_reported_indexer_{state.lower()}_jobs",
            by_state.get(state),
            observation_type="aggregate_snapshot",
            definition=(
                "Nosana Explore aggregate indexer count by its job state; a state count is not "
                "LLM routing flow, completed useful work, tokens, or capacity utilization."
            ),
            record={"endpoint": "/jobs/count", "state": state, "value": by_state.get(state)},
        )
    for market_id, item in running.items():
        value = item.get("running") if isinstance(item, dict) else None
        emit(
            "source_reported_running_jobs_by_market",
            value,
            observation_type="market_snapshot",
            market_id=str(market_id),
            definition=(
                "Nosana Explore aggregate running-job count for a public market identifier; not "
                "a GPU count, job completion, available capacity, price, or routing share."
            ),
            record={"endpoint": "/jobs/running", "market": market_id, "value": value},
        )
    for endpoint, metric, definition in (
        (
            "/jobs/stats/timestamps",
            "source_reported_completed_job_count_bucket",
            "Nosana Explore rolling source-reported completed-job count bucket; not LLM requests, "
            "tokens, unique users, or a causal demand estimate.",
        ),
        (
            "/jobs/stats/timestamps-hours",
            "source_reported_job_duration_hours_bucket",
            "Nosana Explore rolling source-reported job-duration-hours bucket (shown by its UI as "
            "GPU Compute Hours); not independently verified GPU-hours, delivered compute, "
            "utilization, or revenue.",
        ),
    ):
        series = body.get(endpoint)
        total = _float(series.get("total")) if isinstance(series, dict) else None
        for point in _nosana_activity_points(series):
            emit(
                metric,
                point["y"],
                observation_type="rolling_bucket",
                bucket_unix_ms=int(point["x"]),
                source_total=total,
                definition=definition,
                record={"endpoint": endpoint, "point": point, "period_seconds": period},
            )
    return rows


_AETHIR_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def _aethir_literal(body: Any) -> str:
    """Normalize Next.js's JSON-escaped server stream without evaluating it."""
    return body.replace('\\"', '"') if isinstance(body, str) else ""


def _aethir_number(body: Any, name: str) -> float | None:
    """Extract one numeric field from Aethir's server-rendered public page."""
    match = re.search(rf'"{re.escape(name)}":({_AETHIR_NUMBER})', _aethir_literal(body))
    return _float(match.group(1)) if match else None


def _aethir_array(body: Any, name: str) -> list[dict[str, Any]]:
    """Decode an embedded, public dashboard array without executing page code."""
    body = _aethir_literal(body)
    marker = f'"{name}":'
    start = body.find(marker)
    if start < 0:
        return []
    try:
        value, _ = json.JSONDecoder().raw_decode(body[start + len(marker) :])
    except (json.JSONDecodeError, TypeError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _aethir_series_count(body: Any, *names: str) -> dict[str, int]:
    return {name: len(_aethir_array(body, name)) for name in names}


def aethir_dashboard_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize only public Aethir dashboard aggregates and dated source series.

    This source has no publicly documented machine-readable API.  The dashboard
    server-renders its aggregate cards and arrays, so the collector stores the
    raw public pages and parses literal fields only.  It deliberately excludes
    individual cloud-host, workload, buyer, or routing data.
    """
    if not isinstance(body, dict):
        return []
    supply = body.get("supply")
    demand = body.get("demand")
    if not isinstance(supply, str) or not isinstance(demand, str):
        return []
    rows: list[dict[str, Any]] = []
    common = {
        "run_ts": run_ts,
        "dt": dt,
        "source": "aethir_dashboard",
        "venue": "aethir-public-gpu-dashboard",
        "quality_tier": "public dashboard aggregate; source-defined network metric",
    }

    def emit(
        metric: str,
        value: Any,
        *,
        definition: str,
        unit: str,
        observation_type: str = "aggregate_snapshot",
        bucket_period: str | None = None,
        bucket_label: str | None = None,
        bucket_unix_ms: int | None = None,
        record: Any,
    ) -> None:
        number = _float(value)
        if number is None or number < 0:
            return
        rows.append(
            common
            | {
                "metric": metric,
                "value": number,
                "source_reported_unit": unit,
                "observation_type": observation_type,
                "source_bucket_period": bucket_period,
                "source_bucket_label": bucket_label,
                "source_bucket_unix_ms": bucket_unix_ms,
                "metric_definition": definition,
                "record_json": _json(record),
            }
        )

    for field, metric, unit, definition in (
        (
            "nodes",
            "source_reported_total_gpu_containers",
            "containers",
            "Aethir dashboard Total GPUs (Containers); a source-defined container count, not "
            "verified physical GPUs, free capacity, an offer book, or delivered compute.",
        ),
        (
            "locations",
            "source_reported_gpu_countries",
            "countries",
            "Aethir dashboard GPUs Countries count; not region-specific available capacity or "
            "a geographic demand measure.",
        ),
        (
            "totalComputePower",
            "source_reported_total_compute_power_tflops",
            "tflops",
            "Aethir dashboard Total Compute Power (Total TFlops); a source aggregate, not "
            "model-specific throughput, capacity allocation, or a delivered FLOP measure.",
        ),
        (
            "totalMonthlyCapacity",
            "source_reported_monthly_player_capacity",
            "source_defined_player_capacity",
            "Aethir dashboard Total Monthly Capacity of Players in the source's own units; not "
            "an observed customer count, a fill count, or a route allocation.",
        ),
        (
            "idcStaked",
            "source_reported_cloud_host_locked_ath",
            "ath",
            "Aethir dashboard Total Locked ATH by Cloud Hosts; collateral/token state, not "
            "physical capacity, delivered service, or provider profit.",
        ),
        (
            "totalOnlineHours",
            "source_reported_compute_hours",
            "hours",
            "Aethir dashboard Compute Hours aggregate; source-defined hours, not independently "
            "verified GPU-hours, LLM demand, utilization, or a routing-flow measure.",
        ),
        (
            "totalRewards",
            "source_reported_cloud_host_total_rewards_ath",
            "ath",
            "Aethir dashboard Proof of Capacity plus Proof of Delivery rewards; source-reported "
            "ATH rewards, not USD revenue, realized price, or profit.",
        ),
        (
            "totalServiceFee",
            "source_reported_cloud_host_total_service_fee_ath",
            "ath",
            "Aethir dashboard Total Service Fee in its cloud-host earnings display; source-"
            "reported ATH, not independently verified revenue, price, or profit.",
        ),
        (
            "totalLockedRewards",
            "source_reported_cloud_host_total_locked_rewards_ath",
            "ath",
            "Aethir dashboard source-reported locked cloud-host reward amount; not free "
            "capacity, delivered compute, or provider profit.",
        ),
    ):
        emit(
            metric,
            _aethir_number(supply, field),
            unit=unit,
            definition=definition,
            record={"page": "supply-metric", "field": field},
        )
    for field, metric, unit, definition in (
        (
            "arr",
            "source_reported_annual_recurring_revenue_usd",
            "usd",
            "Aethir dashboard Annual Recurring Revenue (ARR); source-reported USD, not an "
            "audited revenue series, realized routing price, or welfare measure.",
        ),
        (
            "onChainComputePurchases",
            "source_reported_onchain_compute_purchases_ath",
            "ath",
            "Aethir dashboard Onchain Compute Purchases; source-reported ATH aggregate, not "
            "individual purchases, tokenized GPU-hours, or a route-flow census.",
        ),
        (
            "totalNetworkRevenue",
            "source_reported_total_network_revenue_usd",
            "usd",
            "Aethir dashboard Total Network Revenue Since June 2024; source-reported USD, not "
            "audited cash revenue, provider profit, or a comparable clearing-price series.",
        ),
        (
            "totalComputeHoursDelivered",
            "source_reported_total_compute_hours_delivered",
            "hours",
            "Aethir dashboard Total Compute Hours Delivered; source-defined aggregate, not "
            "independently verified GPU-hours, LLM requests, tokens, or routing allocation.",
        ),
        (
            "totalComputeHoursDeliveredLastWeek",
            "source_reported_compute_hours_delivered_last_week",
            "hours",
            "Aethir dashboard Total Compute Hours Delivered Last Week; source-defined aggregate, "
            "not independently verified GPU-hours, LLM requests, tokens, or routing allocation.",
        ),
    ):
        emit(
            metric,
            _aethir_number(demand, field),
            unit=unit,
            definition=definition,
            record={"page": "demand-metric", "field": field},
        )

    for series_name, label_field, value_fields, period, page, definition in (
        (
            "weeklyData",
            "week",
            (
                ("reward", "source_reported_weekly_cloud_host_rewards_ath", "ath"),
                ("service", "source_reported_weekly_cloud_host_service_fee_ath", "ath"),
            ),
            "weekly",
            "supply-metric",
            "Aethir dashboard cloud-host earnings component in the source-defined weekly "
            "series; no year is supplied in the label, so it is retained as a label rather "
            "than inferred as a dated causal observation.",
        ),
        (
            "dailyData",
            "day",
            (
                ("reward", "source_reported_daily_cloud_host_rewards_ath", "ath"),
                ("service", "source_reported_daily_cloud_host_service_fee_ath", "ath"),
            ),
            "daily",
            "supply-metric",
            "Aethir dashboard cloud-host earnings component in the source-defined daily "
            "series; no year is supplied in the label, so it is retained as a label rather "
            "than inferred as a dated causal observation.",
        ),
        (
            "monthlyData",
            "month",
            (
                ("reward", "source_reported_monthly_cloud_host_rewards_ath", "ath"),
                ("service", "source_reported_monthly_cloud_host_service_fee_ath", "ath"),
            ),
            "monthly",
            "supply-metric",
            "Aethir dashboard cloud-host earnings component in its dated monthly source "
            "series; source-reported ATH, not audited revenue, provider profit, or price.",
        ),
    ):
        for point in _aethir_array(supply, series_name):
            label = str(point.get(label_field) or "") or None
            bucket_ms = _integer(point.get("unixTimestamp"))
            for field, metric, unit in value_fields:
                emit(
                    metric,
                    point.get(field),
                    unit=unit,
                    observation_type="source_reported_time_bucket",
                    bucket_period=period,
                    bucket_label=label,
                    bucket_unix_ms=bucket_ms,
                    definition=definition,
                    record={"page": page, "series": series_name, "point": point},
                )

    for series_name, label_field, value_field, metric, unit, period, definition in (
        (
            "weeklyNetworkRevenue",
            "startDate",
            "amount",
            "source_reported_weekly_network_revenue_usd",
            "usd",
            "weekly",
            "Aethir dashboard Weekly Network Revenue; source-reported USD series whose labels "
            "omit a year, retained as labels rather than inferred dates or causal observations.",
        ),
        (
            "monthlyNetworkRevenue",
            "month",
            "earning",
            "source_reported_monthly_network_revenue_usd",
            "usd",
            "monthly",
            "Aethir dashboard dated Monthly Network Revenue; source-reported USD, not audited "
            "revenue, comparable clearing price, or provider profit.",
        ),
        (
            "weeklyComputeHoursDelivered",
            "startDate",
            "amount",
            "source_reported_weekly_compute_hours_delivered",
            "hours",
            "weekly",
            "Aethir dashboard Weekly Compute Hours Delivered via its tenant portal; source-"
            "defined hours, not independently verified GPU-hours, LLM routing, or utilization.",
        ),
    ):
        for point in _aethir_array(demand, series_name):
            label = str(point.get(label_field) or "") or None
            emit(
                metric,
                point.get(value_field),
                unit=unit,
                observation_type="source_reported_time_bucket",
                bucket_period=period,
                bucket_label=label,
                bucket_unix_ms=_integer(point.get("unixTimestamp")),
                definition=definition,
                record={"page": "demand-metric", "series": series_name, "point": point},
            )
    return rows


async def capture_aethir_dashboard(
    fetcher: Fetcher,
    *,
    supply_url: str | None = None,
    demand_url: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Capture Aethir's public, server-rendered aggregate dashboard pages only."""
    supply_url = _configured_url(
        "ORCAP_AETHIR_SUPPLY_DASHBOARD_URL", supply_url or AETHIR_SUPPLY_DASHBOARD_URL
    )
    demand_url = _configured_url(
        "ORCAP_AETHIR_DEMAND_DASHBOARD_URL", demand_url or AETHIR_DEMAND_DASHBOARD_URL
    )
    supply, demand = await asyncio.gather(
        fetcher.get_text(supply_url), fetcher.get_text(demand_url)
    )
    supply_scalars = {
        field: _aethir_number(supply, field)
        for field in (
            "nodes",
            "locations",
            "totalComputePower",
            "totalMonthlyCapacity",
            "idcStaked",
            "totalOnlineHours",
            "totalRewards",
            "totalServiceFee",
            "totalLockedRewards",
        )
    }
    demand_scalars = {
        field: _aethir_number(demand, field)
        for field in (
            "arr",
            "onChainComputePurchases",
            "totalNetworkRevenue",
            "totalComputeHoursDelivered",
            "totalComputeHoursDeliveredLastWeek",
        )
    }
    supply_series = _aethir_series_count(supply, "weeklyData", "dailyData", "monthlyData")
    demand_series = _aethir_series_count(
        demand, "weeklyNetworkRevenue", "monthlyNetworkRevenue", "weeklyComputeHoursDelivered"
    )
    query_succeeded = (
        all(value is not None and value >= 0 for value in supply_scalars.values())
        and all(value is not None and value >= 0 for value in demand_scalars.values())
        and all(count > 0 for count in supply_series.values())
        and all(count > 0 for count in demand_series.values())
    )
    return {"supply": supply, "demand": demand}, {
        "query_succeeded": query_succeeded,
        "supply_url": supply_url,
        "demand_url": demand_url,
        "supply_scalar_fields": len(supply_scalars),
        "demand_scalar_fields": len(demand_scalars),
        "supply_series_records": supply_series,
        "demand_series_records": demand_series,
        "metric_boundary": (
            "public Aethir dashboard aggregates and source-reported time buckets only; no "
            "cloud-host, buyer, workload, individual transaction, LLM request, token, route, "
            "verified GPU-hour, independently measured utilization, or causal welfare data"
        ),
    }


async def capture_nosana_job_activity(
    fetcher: Fetcher,
    *,
    url: str | None = None,
    period_seconds: int = NOSANA_JOB_ACTIVITY_PERIOD_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch only public Nosana Explore aggregates, never individual job records."""
    configured_url = _configured_url("ORCAP_NOSANA_EXPLORE_API_URL", url or NOSANA_EXPLORE_API_URL)
    base_url = configured_url.rstrip("/")
    if period_seconds <= 0:
        raise ValueError("period_seconds must be positive")
    paths = {
        "stats": "/jobs/stats",
        "counts": "/jobs/count",
        "running": "/jobs/running",
        "/jobs/stats/timestamps": f"/jobs/stats/timestamps?period={period_seconds}",
        "/jobs/stats/timestamps-hours": f"/jobs/stats/timestamps-hours?period={period_seconds}",
    }
    values = await asyncio.gather(*(fetcher.get_json(base_url + path) for path in paths.values()))
    body = dict(zip(paths, values, strict=True)) | {"period_seconds": period_seconds}
    stats = body["stats"]
    counts = body["counts"]
    running = body["running"]
    bucket_counts = _nosana_activity_points(body["/jobs/stats/timestamps"])
    bucket_hours = _nosana_activity_points(body["/jobs/stats/timestamps-hours"])
    stats_valid = isinstance(stats, dict) and all(
        _float(stats.get(field)) is not None
        for field in ("completed", "duration", "price", "usdReward", "retrieved")
    )
    counts_valid = (
        isinstance(counts, dict)
        and _integer(counts.get("total")) is not None
        and isinstance(counts.get("byState"), dict)
        and all(
            _integer(counts["byState"].get(state)) is not None
            for state in ("QUEUED", "RUNNING", "COMPLETED", "STOPPED")
        )
    )
    running_values = (
        [item.get("running") for item in running.values() if isinstance(item, dict)]
        if isinstance(running, dict)
        else []
    )
    running_valid = isinstance(running, dict) and all(
        _integer(value) is not None for value in running_values
    )
    reported_running = _integer(counts.get("byState", {}).get("RUNNING")) if counts_valid else None
    running_sum = sum(_integer(value) or 0 for value in running_values) if running_valid else None
    running_count_consistent = (
        reported_running is not None and running_sum is not None and reported_running == running_sum
    )
    query_succeeded = (
        stats_valid
        and counts_valid
        and running_valid
        and bool(bucket_counts)
        and bool(bucket_hours)
        and running_count_consistent
    )
    return body, {
        "query_succeeded": query_succeeded,
        "base_url": base_url,
        "period_seconds": period_seconds,
        "aggregate_endpoint_count": len(paths),
        "completed_job_bucket_records": len(bucket_counts),
        "job_duration_hour_bucket_records": len(bucket_hours),
        "running_market_records": len(running_values),
        "reported_running_jobs": reported_running,
        "running_jobs_sum_across_markets": running_sum,
        "running_count_consistent": running_count_consistent,
        "metric_boundary": (
            "public source-defined aggregate job counts and duration buckets only; no individual "
            "job definitions, payer IDs, LLM requests, tokens, verified GPU-hours, delivered "
            "compute, utilization, revenue, or routing allocation"
        ),
    }


def chutes_capacity_rows(
    models_body: Any, detail_bodies: list[Any], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize public Chutes deployment configuration as a supply proxy.

    Chutes reports active deployment instances and each chute's requested GPU
    selector. Their product is a count of active configured GPUs—not open
    capacity, throughput, token demand, or utilization. Keep those fields
    separate so H41 cannot convert it into a false clearing-capacity claim.
    """
    models = _as_list(models_body, "data")
    model_by_chute_id = {
        str(model["chute_id"]): model
        for model in models
        if model.get("chute_id") and isinstance(model, dict)
    }
    rows = []
    for detail in detail_bodies:
        if not isinstance(detail, dict):
            continue
        chute_id = detail.get("chute_id")
        if not chute_id:
            continue
        model = model_by_chute_id.get(str(chute_id), {})
        selector = (
            detail.get("node_selector") if isinstance(detail.get("node_selector"), dict) else {}
        )
        instances = detail.get("instances") if isinstance(detail.get("instances"), list) else []
        active_instances = sum(
            isinstance(instance, dict) and instance.get("active") is True for instance in instances
        )
        verified_instances = sum(
            isinstance(instance, dict)
            and instance.get("active") is True
            and instance.get("verified") is True
            for instance in instances
        )
        configured_gpus_per_instance = _float(selector.get("gpu_count"))
        active_configured_gpus = (
            active_instances * configured_gpus_per_instance
            if configured_gpus_per_instance is not None
            else None
        )
        estimated_price = detail.get("current_estimated_price")
        hourly_price = (
            ((estimated_price.get("usd") or {}).get("hour"))
            if isinstance(estimated_price, dict)
            else None
        )
        gpu_types = selector.get("supported_gpus") or detail.get("supported_gpus") or []
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "chutes",
                "venue": "chutes-public-inference",
                "participant_id": str(chute_id),
                "resource_id": model.get("id") or detail.get("name") or str(chute_id),
                "resource_kind": "active_configured_gpu",
                "available": None,
                "total": active_configured_gpus,
                "used": None,
                "active_instances": active_instances,
                "verified_active_instances": verified_instances,
                "configured_gpus_per_instance": configured_gpus_per_instance,
                "configured_concurrency": _float(detail.get("concurrency")),
                "gpu_types": [str(gpu) for gpu in gpu_types],
                "cumulative_invocations": _float(detail.get("invocation_count")),
                "estimated_deployment_usd_hour": _float(hourly_price),
                "preemptible": detail.get("preemptible"),
                "quality_tier": "public-active-deployment-configuration-proxy",
                "metric_definition": (
                    "Active Chutes instances times the chute NodeSelector's configured GPU count. "
                    "This is an active deployment configuration proxy, not available capacity, "
                    "throughput, token demand, utilization, or realized routing allocation."
                ),
                "record_json": _json(detail),
            }
        )
    return rows


def cow_execution_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    for item in _as_list(body, "trades", "data"):
        execution_id = item.get("uid") or item.get("orderUid") or item.get("txHash")
        if not execution_id:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "cow",
                "venue": "cow-protocol",
                "execution_id": execution_id,
                "instrument_id": (
                    f"{item.get('sellToken', 'unknown')}/{item.get('buyToken', 'unknown')}"
                ),
                "executed_at": item.get("executed") or item.get("creationDate"),
                "side": item.get("kind"),
                "requested_size": _float(item.get("sellAmount")),
                "filled_size": _float(item.get("executedSellAmount") or item.get("sellAmount")),
                "gross_price_usd": None,
                "native_price": _ratio(item.get("buyAmount"), item.get("sellAmount")),
                "fee_native": _float(item.get("feeAmount")),
                "gas_native": None,
                "success": True,
                "participant_id": item.get("owner"),
                "record_json": _json(item),
            }
        )
    return rows


def cow_competition_rows(
    body: Any, run_ts: str, dt: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize the public *latest* CoW solver competition as a live snapshot.

    This endpoint exposes one current/recent batch and candidate solutions. It
    is not paginated market-wide trade history, does not identify all failed
    orders, and must not be used as a settlement/execution panel. The raw
    response is retained separately; normalized rows deliberately keep only
    aggregate auction properties and solver-proposal metadata.
    """
    if not isinstance(body, dict) or body.get("auctionId") is None:
        return [], []
    auction_id = str(body["auctionId"])
    auction = body.get("auction") if isinstance(body.get("auction"), dict) else {}
    orders = auction.get("orders") if isinstance(auction.get("orders"), list) else []
    solutions = _as_list(body, "solutions")
    auction_start_block = _integer(body.get("auctionStartBlock"))
    auction_deadline_block = _integer(body.get("auctionDeadlineBlock"))
    winner_count = sum(solution.get("isWinner") is True for solution in solutions)
    event_summary = {
        "auction_id": auction_id,
        "auction_start_block": auction_start_block,
        "auction_deadline_block": auction_deadline_block,
        "candidate_order_count": len(orders),
        "solver_solution_count": len(solutions),
        "winner_count": winner_count,
        "settlement_transaction_count": len(body.get("transactionHashes") or []),
        "schema": "cow_solver_competition_latest_v1",
    }
    event = {
        "run_ts": run_ts,
        "dt": dt,
        "source": "cow",
        "event_id": f"cow:solver-competition:{auction_id}",
        "event_type": "solver_competition_snapshot",
        # The endpoint has blocks but no auction timestamp. ``run_ts`` is an
        # observation time, so it must not be substituted as event time.
        "event_time": None,
        "instrument_id": "multi-asset-batch",
        "auction_start_block": auction_start_block,
        "auction_deadline_block": auction_deadline_block,
        "record_json": _json(event_summary),
    }
    participants = []
    for solution in solutions:
        solver = solution.get("solverAddress")
        if not solver:
            continue
        solution_orders = solution.get("orders")
        solution_summary = {
            **event_summary,
            "solver_address": str(solver).lower(),
            "ranking": _integer(solution.get("ranking")),
            "is_winner": solution.get("isWinner") is True,
            "filtered_out": solution.get("filteredOut") is True,
            "candidate_order_count_in_solution": (
                len(solution_orders) if isinstance(solution_orders, list) else 0
            ),
            "has_settlement_transaction": bool(solution.get("txHash")),
        }
        participants.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "cow",
                "venue": "cow-protocol",
                "participant_id": str(solver).lower(),
                "participant_name": None,
                "instrument_id": "multi-asset-batch",
                "metric": "solver_competition_candidate",
                "auction_id": auction_id,
                "auction_start_block": auction_start_block,
                "auction_deadline_block": auction_deadline_block,
                # Score units are protocol-objective units, not a comparable
                # price, volume, or liquidity measure. Preserve it separately.
                "value": None,
                "competition_score": _float(solution.get("score")),
                "ranking": _integer(solution.get("ranking")),
                "is_winner": solution.get("isWinner") is True,
                "quality_tier": (
                    "official-live-solver-competition; snapshot only, not market-wide "
                    "trades, fills, or execution outcomes"
                ),
                "record_json": _json(solution_summary),
            }
        )
    return participants, [event]


def uniswap_rows(
    body: Any, run_ts: str, dt: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    data = (body or {}).get("data") if isinstance(body, dict) else {}
    quotes, executions, events = [], [], []
    for pool in _as_list(data, "pools"):
        quotes.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "uniswap",
                "venue": "uniswap-v3",
                "instrument_id": (
                    f"{(pool.get('token0') or {}).get('id', 'unknown')}/"
                    f"{(pool.get('token1') or {}).get('id', 'unknown')}"
                ),
                "quote_id": pool.get("id"),
                "quote_side": "marginal",
                "price_usd": None,
                "native_price": _float(pool.get("token1Price")),
                "depth_usd": _float(pool.get("totalValueLockedUSD")),
                "quality_tier": "subgraph-indexed-state; not finalized logs",
                "finalized": False,
                "record_json": _json(pool),
            }
        )
    for swap in _as_list(data, "swaps"):
        execution_id = swap.get("id")
        executions.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "uniswap",
                "venue": "uniswap-v3",
                "execution_id": execution_id,
                "instrument_id": (swap.get("pool") or {}).get("id"),
                "executed_at": swap.get("timestamp"),
                "side": None,
                "requested_size": _float(swap.get("amount0")),
                "filled_size": _float(swap.get("amount1")),
                "gross_price_usd": _float(swap.get("amountUSD")),
                "native_price": None,
                "fee_native": None,
                "gas_native": None,
                "success": True,
                "finalized": False,
                "participant_id": swap.get("origin"),
                "record_json": _json(swap),
            }
        )
        if execution_id:
            events.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "source": "uniswap",
                    "event_id": f"uniswap:{execution_id}",
                    "event_type": "swap",
                    "event_time": swap.get("timestamp"),
                    "instrument_id": (swap.get("pool") or {}).get("id"),
                    "finalized": False,
                    "record_json": _json(swap),
                }
            )
    return quotes, executions, events


def _uniswap_quoter_calldata(spec: dict[str, Any], amount_in_raw: int) -> str:
    """Encode QuoterV2's one-tuple exact-input quote without a web3 dependency."""
    return (
        "0x"
        + UNISWAP_V3_QUOTE_EXACT_INPUT_SINGLE_SELECTOR
        + "".join(
            (
                _abi_address(spec["token0_address"]),
                _abi_address(spec["token1_address"]),
                _abi_uint(amount_in_raw),
                _abi_uint(int(spec["fee"]), bits=24),
                _abi_uint(0, bits=160),
            )
        )
    )


def uniswap_quoter_quote_rows(
    quote_records: list[dict[str, Any]], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize finalized-block QuoterV2 simulations as a price-impact curve.

    A QuoterV2 response is an exact-input state simulation at a fixed block,
    not a trade, firm RFQ, or total executable market depth. It is still a
    substantially stronger fixed-notional price-impact object than indexed
    TVL, so retain the raw simulation and block identity separately.
    """
    rows = []
    for record in quote_records:
        spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
        result = record.get("result")
        amount_out_raw = _word(result, 0)
        if amount_out_raw is None:
            continue
        try:
            amount_in_raw = int(record["amount_in_raw"])
            input_amount = amount_in_raw / 10 ** int(spec["token0_decimals"])
            output_amount = amount_out_raw / 10 ** int(spec["token1_decimals"])
            block_number = int(record["block_number"])
        except (KeyError, TypeError, ValueError):
            continue
        if input_amount <= 0 or output_amount <= 0:
            continue
        sqrt_after = _word(result, 1)
        ticks_crossed = _word(result, 2)
        gas_estimate = _word(result, 3)
        pool_id = str(record.get("pool_id") or "").lower()
        bucket = record.get("input_bucket_usdc")
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "uniswap",
                "venue": "uniswap-v3",
                "instrument_id": spec.get("canonical_instrument"),
                "pool_id": pool_id,
                "quote_id": f"{pool_id}:quoter-v2:{block_number}:{amount_in_raw}",
                "quote_side": "usdc_to_weth_exact_input_simulation",
                "quote_unit": "usdc_per_weth",
                "price_usd": None,
                "price_usdc_per_weth": input_amount / output_amount,
                "native_price": output_amount / input_amount,
                "depth_usd": None,
                "input_amount": input_amount,
                "input_amount_raw": str(amount_in_raw),
                "output_amount": output_amount,
                "output_amount_raw": str(amount_out_raw),
                "input_bucket_usdc": bucket,
                "block_number": block_number,
                "sqrt_price_x96_after": str(sqrt_after) if sqrt_after is not None else None,
                "initialized_ticks_crossed": ticks_crossed,
                "gas_estimate": gas_estimate,
                "finalized": True,
                "quality_tier": (
                    "onchain-quoter-v2 simulation at finality-buffered block; fixed-notional "
                    "price-impact point, not a fill guarantee or market-wide executable depth"
                ),
                "record_json": _json(record),
            }
        )
    return rows


def uniswap_quoter_impact_capacity_rows(
    quote_records: list[dict[str, Any]], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Derive discrete all-in price-impact capacity lower bounds from QuoterV2.

    Within a pool/block, the smallest successful USDC probe is the explicit
    all-in reference price.  For each declared deterioration threshold, this
    reports the largest successful input-ladder point whose simulated price is
    still within the threshold.  It is a repeatable state-derived lower bound:
    a sparse ladder cannot locate the exact threshold crossing, and QuoterV2
    does not guarantee a subsequently executable fill.
    """
    points: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in quote_records:
        spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
        amount_out_raw = _word(record.get("result"), 0)
        try:
            amount_in_raw = int(record["amount_in_raw"])
            block_number = int(record["block_number"])
            input_amount = amount_in_raw / 10 ** int(spec["token0_decimals"])
            output_amount = amount_out_raw / 10 ** int(spec["token1_decimals"])
        except (KeyError, TypeError, ValueError):
            continue
        pool_id = str(record.get("pool_id") or "").lower()
        if not pool_id or amount_out_raw is None or input_amount <= 0 or output_amount <= 0:
            continue
        points.setdefault((pool_id, block_number), []).append(
            {
                "input_amount": input_amount,
                "price_usdc_per_weth": input_amount / output_amount,
                "record": record,
                "spec": spec,
            }
        )

    rows = []
    for (pool_id, block_number), candidates in sorted(points.items()):
        candidates.sort(key=lambda item: item["input_amount"])
        reference = candidates[0]
        reference_price = reference["price_usdc_per_weth"]
        if reference_price <= 0:
            continue
        for target_bps in UNISWAP_USDC_IMPACT_TARGET_BPS:
            threshold = reference_price * (1 + target_bps / 10_000)
            eligible = [item for item in candidates if item["price_usdc_per_weth"] <= threshold]
            if not eligible:
                continue
            lower_bound = max(eligible, key=lambda item: item["input_amount"])
            spec = lower_bound["spec"]
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "source": "uniswap",
                    "venue": "uniswap-v3",
                    "instrument_id": spec.get("canonical_instrument"),
                    "pool_id": pool_id,
                    "quote_id": (
                        f"{pool_id}:quoter-v2-impact-capacity:{block_number}:{target_bps}bps"
                    ),
                    "quote_side": "usdc_to_weth_all_in_impact_capacity_lower_bound",
                    "quote_unit": "usdc",
                    "impact_target_bps": target_bps,
                    "impact_capacity_lower_bound_usdc": lower_bound["input_amount"],
                    "reference_input_amount_usdc": reference["input_amount"],
                    "reference_price_usdc_per_weth": reference_price,
                    "price_usdc_per_weth": lower_bound["price_usdc_per_weth"],
                    "block_number": block_number,
                    "finalized": True,
                    "quality_tier": (
                        "onchain-quoter-v2 finality-buffered state simulation; sparse-ladder "
                        "all-in price-impact capacity lower bound, not tick-book depth or a "
                        "fill guarantee"
                    ),
                    "metric_definition": (
                        "Largest successful declared USDC input ladder point whose all-in "
                        "simulated USDC/WETH price is within impact_target_bps of the smallest "
                        "successful "
                        "same-block probe. It is a discrete lower bound, not total liquidity, "
                        "market-wide depth, or a firm executable quote."
                    ),
                    "record_json": _json(
                        {
                            "reference": reference["record"],
                            "eligible_ladder_points": [
                                {
                                    "input_amount_usdc": item["input_amount"],
                                    "price_usdc_per_weth": item["price_usdc_per_weth"],
                                }
                                for item in eligible
                            ],
                        }
                    ),
                }
            )
    return rows


def uniswap_tick_book_rows(
    tick_records: list[dict[str, Any]], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize a complete, block-pinned V3 initialized-tick snapshot.

    This is exact virtual-liquidity state for a registered pool across its
    usable tick range, but it is deliberately not converted into USD depth or
    a firm executable quote. Those claims require an explicit swap traversal,
    fee accounting, and a stated trade direction/notional.
    """
    rows = []
    for record in tick_records:
        spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
        try:
            pool_id = str(record["pool_id"]).lower()
            block_number = int(record["block_number"])
            tick = int(record["tick"])
            tick_spacing = int(record["tick_spacing"])
            word_position = int(record["word_position"])
            current_tick = int(record["current_tick"])
            sqrt_price_x96 = int(record["sqrt_price_x96"])
            active_liquidity_raw = int(record["active_liquidity_raw"])
            liquidity_net_raw = int(record["liquidity_net_raw"])
            liquidity_gross_raw = int(record["liquidity_gross_raw"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not pool_id
            or tick_spacing <= 0
            or tick % tick_spacing
            or (tick // tick_spacing) // 256 != word_position
            or not UNISWAP_V3_MIN_TICK <= tick <= UNISWAP_V3_MAX_TICK
        ):
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "uniswap",
                "venue": "uniswap-v3",
                "instrument_id": spec.get("canonical_instrument"),
                "pool_id": pool_id,
                "pool_map_id": spec.get("map_id"),
                "block_number": block_number,
                "tick": tick,
                "word_position": word_position,
                "tick_spacing": tick_spacing,
                "current_tick": current_tick,
                "sqrt_price_x96": str(sqrt_price_x96),
                "active_liquidity_raw": str(active_liquidity_raw),
                "liquidity_net_raw": str(liquidity_net_raw),
                "liquidity_gross_raw": str(liquidity_gross_raw),
                "finalized": True,
                "quality_tier": (
                    "onchain TickLens state at finality-buffered block; complete initialized "
                    "tick book for one registered pool, not USD executable depth or a "
                    "fill guarantee"
                ),
                "metric_definition": (
                    "An initialized Uniswap V3 tick's virtual-liquidity gross and signed net "
                    "values, returned by TickLens after scanning every usable tick-bitmap word "
                    "at one finality-buffered block. It is not a swap traversal, dollar depth, "
                    "market-wide book, or firm quote."
                ),
                "record_json": _json(record),
            }
        )
    return rows


def cow_amm_preblock_quote_rows(
    quote_records: list[dict[str, Any]], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize parent-block AMM simulations matched to exact CoW USDC sells.

    The parent block is the most recent universally reproducible EVM state
    before the CoW settlement block. It cannot reconstruct intra-block ordering
    or a contemporaneous firm quote, so these rows are a pre-block gross-price
    counterfactual rather than an adverse-selection, surplus, or best-execution
    measurement.
    """
    rows = []
    for record in quote_records:
        spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
        amount_out_raw = _word(record.get("result"), 0)
        if amount_out_raw is None:
            continue
        try:
            amount_in_raw = int(record["amount_in_raw"])
            input_amount = amount_in_raw / 10 ** int(spec["token0_decimals"])
            output_amount = amount_out_raw / 10 ** int(spec["token1_decimals"])
            state_block = int(record["state_block_number"])
            event_block = int(record["reference_event_block_number"])
        except (KeyError, TypeError, ValueError):
            continue
        if input_amount <= 0 or output_amount <= 0 or state_block < 0 or event_block <= state_block:
            continue
        pool_id = str(record.get("pool_id") or "").lower()
        execution_id = str(record.get("reference_execution_id") or "")
        if not pool_id or not execution_id:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "uniswap",
                "venue": "uniswap-v3",
                "quote_id": f"{execution_id}:{pool_id}:parent-block:{state_block}",
                "reference_source": "cow",
                "reference_execution_id": execution_id,
                "reference_event_block_number": event_block,
                "state_block_number": state_block,
                "instrument_id": spec.get("canonical_instrument"),
                "pool_id": pool_id,
                "quote_side": "usdc_to_weth_preblock_exact_input_counterfactual",
                "quote_unit": "usdc_per_weth",
                "input_amount": input_amount,
                "input_amount_raw": str(amount_in_raw),
                "output_amount": output_amount,
                "output_amount_raw": str(amount_out_raw),
                "price_usdc_per_weth": input_amount / output_amount,
                "native_price": output_amount / input_amount,
                "finalized": True,
                "quality_tier": (
                    "onchain-quoter-v2 parent-block state simulation matched to one finalized "
                    "CoW USDC-to-WETH Trade; not an intra-block quote, fill guarantee, or depth"
                ),
                "metric_definition": (
                    "Pre-block gross AMM counterfactual for the exact CoW sell amount. It excludes "
                    "CoW fee, gas, surplus, intra-block ordering, and subsequent price movement."
                ),
                "record_json": _json(record),
            }
        )
    return rows


def uniswap_rpc_log_rows(
    logs: Any,
    block_times: dict[int, str | None],
    run_ts: str,
    dt: str,
    *,
    pool_specs: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize finalized, registered-pool Uniswap V3 logs.

    The routine deliberately measures swap execution and liquidity-event
    incidence, not dollar executable depth.  V3's virtual liquidity and a
    single swap price do not identify depth at a notional-size bucket, so that
    higher bar remains visible in H41.
    """
    specs = pool_specs if pool_specs is not None else uniswap_pool_specs()
    executions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for log_row in logs if isinstance(logs, list) else []:
        if not isinstance(log_row, dict):
            continue
        pool = str(log_row.get("address") or "").lower()
        spec = specs.get(pool)
        topics = log_row.get("topics")
        topic0 = topics[0].lower() if isinstance(topics, list) and topics else None
        tx_hash = str(log_row.get("transactionHash") or "").lower()
        log_index = _hex_int(log_row.get("logIndex"))
        block_number = _hex_int(log_row.get("blockNumber"))
        if spec is None or not topic0 or not tx_hash or log_index is None or block_number is None:
            continue
        event_id = f"uniswap:{tx_hash}:{log_index}"
        base = {
            "run_ts": run_ts,
            "dt": dt,
            "source": "uniswap",
            "event_id": event_id,
            "event_time": block_times.get(block_number),
            "instrument_id": spec["canonical_instrument"],
            "pool_id": pool,
            "pool_map_id": spec["map_id"],
            "block_number": block_number,
            "block_hash": log_row.get("blockHash"),
            "transaction_hash": tx_hash,
            "log_index": log_index,
            "finalized": True,
        }
        if topic0 == UNISWAP_V3_SWAP_TOPIC:
            amount0_raw, amount1_raw = (
                _signed_word(log_row.get("data"), 0),
                _signed_word(log_row.get("data"), 1),
            )
            sqrt_price_x96 = _word(log_row.get("data"), 2)
            liquidity_after = _word(log_row.get("data"), 3)
            tick = _signed_word(log_row.get("data"), 4)
            if (
                amount0_raw is None
                or amount1_raw is None
                or not (
                    (amount0_raw > 0 and amount1_raw < 0) or (amount1_raw > 0 and amount0_raw < 0)
                )
            ):
                continue
            amount0 = amount0_raw / 10 ** spec["token0_decimals"]
            amount1 = amount1_raw / 10 ** spec["token1_decimals"]
            zero_for_one = amount0_raw > 0
            input_amount = amount0 if zero_for_one else amount1
            output_amount = -amount1 if zero_for_one else -amount0
            side = "token0_to_token1" if zero_for_one else "token1_to_token0"
            parsed = {
                "event_kind": "swap",
                "amount0_raw": str(amount0_raw),
                "amount1_raw": str(amount1_raw),
                "amount0": amount0,
                "amount1": amount1,
                "sqrt_price_x96": str(sqrt_price_x96) if sqrt_price_x96 is not None else None,
                "liquidity_after": str(liquidity_after) if liquidity_after is not None else None,
                "tick": tick,
                "sender": _topic_address(topics, 1),
                "recipient": _topic_address(topics, 2),
                "token0_symbol": spec["token0_symbol"],
                "token1_symbol": spec["token1_symbol"],
            }
            record_json = _json({"log": log_row, "parsed": parsed})
            executions.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "source": "uniswap",
                    "venue": "uniswap-v3",
                    "execution_id": event_id,
                    "instrument_id": spec["canonical_instrument"],
                    "executed_at": block_times.get(block_number),
                    "event_block_number": block_number,
                    "finalized": True,
                    "side": side,
                    "requested_size": input_amount,
                    "filled_size": output_amount,
                    "gross_price_usd": None,
                    "native_price": output_amount / input_amount if input_amount else None,
                    "fee_native": None,
                    "gas_native": None,
                    "success": True,
                    "participant_id": parsed["sender"],
                    "quality_tier": f"onchain-finalized-rpc;{spec['quality_tier']}",
                    "metric_definition": (
                        "Finalized Uniswap V3 Swap event. Requested and filled sizes are "
                        "pool-balance deltas, normalized by configured token decimals; they "
                        "are not USD notional, gas-inclusive price, or depth."
                    ),
                    "record_json": record_json,
                }
            )
            events.append(base | {"event_type": "swap", "record_json": record_json})
        elif topic0 in {UNISWAP_V3_MINT_TOPIC, UNISWAP_V3_BURN_TOPIC}:
            liquidity_delta = _word(log_row.get("data"), 0)
            amount0_raw, amount1_raw = _word(log_row.get("data"), 1), _word(log_row.get("data"), 2)
            if liquidity_delta is None or amount0_raw is None or amount1_raw is None:
                continue
            kind = "liquidity_mint" if topic0 == UNISWAP_V3_MINT_TOPIC else "liquidity_burn"
            parsed = {
                "event_kind": kind,
                "owner": _topic_address(topics, 1),
                "liquidity_delta": str(liquidity_delta),
                "amount0_raw": str(amount0_raw),
                "amount1_raw": str(amount1_raw),
                "amount0": amount0_raw / 10 ** spec["token0_decimals"],
                "amount1": amount1_raw / 10 ** spec["token1_decimals"],
                "token0_symbol": spec["token0_symbol"],
                "token1_symbol": spec["token1_symbol"],
            }
            events.append(
                base
                | {
                    "event_type": kind,
                    "record_json": _json({"log": log_row, "parsed": parsed}),
                }
            )
    return executions, events


def _cow_usdc_weth_execution_fields(
    sell_token: str, buy_token: str, sell_amount: int, buy_amount: int
) -> dict[str, Any] | None:
    """Normalize the one exact CoW cohort with checked token-decimal metadata.

    Most GPv2 Trade records only expose raw token amounts. For USDC/WETH both
    mainnet token addresses and decimals are explicitly registered, allowing a
    comparable per-fill price without pretending that every CoW asset has a
    complete token/FX map. USDC is retained as the quote unit, never silently
    converted into a USD execution claim.
    """
    if {sell_token, buy_token} != {USDC_ADDRESS, WETH_ADDRESS}:
        return None
    sell_amount_normalized = sell_amount / (10**6 if sell_token == USDC_ADDRESS else 10**18)
    buy_amount_normalized = buy_amount / (10**6 if buy_token == USDC_ADDRESS else 10**18)
    if sell_amount_normalized <= 0 or buy_amount_normalized <= 0:
        return None
    if sell_token == USDC_ADDRESS:
        price_usdc_per_weth = sell_amount_normalized / buy_amount_normalized
        side = "usdc_to_weth"
    else:
        price_usdc_per_weth = buy_amount_normalized / sell_amount_normalized
        side = "weth_to_usdc"
    return {
        "instrument_id": "ethereum:USDC/WETH",
        "side": side,
        "requested_size": sell_amount_normalized,
        "filled_size": buy_amount_normalized,
        "native_price": buy_amount_normalized / sell_amount_normalized,
        "price_usdc_per_weth": price_usdc_per_weth,
        "price_unit": "usdc_per_weth",
        "metric_definition": (
            "Finalized GPv2 Trade for the exact USDC/WETH pair, normalized using registered "
            "mainnet token decimals. price_usdc_per_weth is a USDC quote-unit execution price, "
            "not a stablecoin-peg-adjusted USD price, gas-inclusive cost, or surplus estimate."
        ),
    }


def cow_rpc_log_rows(
    logs: Any, block_times: dict[int, str | None], run_ts: str, dt: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize finalized GPv2 settlement events without a solver proxy.

    ``Trade`` records the owner and raw token amounts, while ``Settlement``
    records the authorized solver. They are joined only by immutable
    transaction hash, so a missing Settlement event stays missing rather than
    being filled from the transaction sender.
    """
    rows = [item for item in logs if isinstance(item, dict)] if isinstance(logs, list) else []
    solvers = {
        str(item.get("transactionHash") or "").lower(): _topic_address(item.get("topics"), 1)
        for item in rows
        if isinstance(item.get("topics"), list)
        and item["topics"]
        and str(item["topics"][0]).lower() == GPV2_SETTLEMENT_TOPIC
    }
    executions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for log_row in rows:
        topics = log_row.get("topics")
        topic0 = topics[0].lower() if isinstance(topics, list) and topics else None
        tx_hash = str(log_row.get("transactionHash") or "").lower()
        log_index = _hex_int(log_row.get("logIndex"))
        block_number = _hex_int(log_row.get("blockNumber"))
        if not topic0 or not tx_hash or log_index is None or block_number is None:
            continue
        event_id = f"cow:{tx_hash}:{log_index}"
        event_base = {
            "run_ts": run_ts,
            "dt": dt,
            "source": "cow",
            "event_id": event_id,
            "event_time": block_times.get(block_number),
            "instrument_id": "multi-asset-batch",
            "block_number": block_number,
            "block_hash": log_row.get("blockHash"),
            "transaction_hash": tx_hash,
            "log_index": log_index,
            "finalized": True,
        }
        if topic0 == GPV2_SETTLEMENT_TOPIC:
            solver = _topic_address(topics, 1)
            events.append(
                event_base
                | {
                    "event_type": "settlement",
                    "solver_id": solver,
                    "record_json": _json({"log": log_row, "solver": solver}),
                }
            )
            continue
        if topic0 != GPV2_TRADE_TOPIC:
            continue
        sell_token, buy_token = (
            _address_word(log_row.get("data"), 0),
            _address_word(log_row.get("data"), 1),
        )
        sell_amount, buy_amount, fee_amount = (
            _word(log_row.get("data"), 2),
            _word(log_row.get("data"), 3),
            _word(log_row.get("data"), 4),
        )
        order_uid = _dynamic_bytes(log_row.get("data"), 5)
        owner = _topic_address(topics, 1)
        if None in (sell_token, buy_token, sell_amount, buy_amount, fee_amount, order_uid, owner):
            continue
        solver = solvers.get(tx_hash)
        parsed = {
            "owner": owner,
            "solver": solver,
            "sell_token": sell_token,
            "buy_token": buy_token,
            "sell_amount_raw": str(sell_amount),
            "buy_amount_raw": str(buy_amount),
            "fee_amount_raw": str(fee_amount),
            "order_uid": order_uid,
        }
        normalized = _cow_usdc_weth_execution_fields(sell_token, buy_token, sell_amount, buy_amount)
        record_json = _json({"log": log_row, "parsed": parsed})
        executions.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "cow",
                "venue": "cow-protocol",
                "execution_id": event_id,
                "instrument_id": (
                    normalized["instrument_id"]
                    if normalized is not None
                    else f"ethereum:{sell_token}/{buy_token}"
                ),
                "executed_at": block_times.get(block_number),
                "event_block_number": block_number,
                "finalized": True,
                "side": normalized["side"] if normalized is not None else "sell_token_to_buy_token",
                # Generic GPv2 trades preserve raw amounts. Only the explicit
                # USDC/WETH cohort below has independently registered decimals.
                "requested_size": normalized["requested_size"] if normalized is not None else None,
                "filled_size": normalized["filled_size"] if normalized is not None else None,
                "sell_amount_raw": str(sell_amount),
                "buy_amount_raw": str(buy_amount),
                "gross_price_usd": None,
                "native_price": normalized["native_price"] if normalized is not None else None,
                "price_usdc_per_weth": (
                    normalized["price_usdc_per_weth"] if normalized is not None else None
                ),
                "price_unit": normalized["price_unit"] if normalized is not None else None,
                "fee_native": None,
                "fee_amount_raw": str(fee_amount),
                "gas_native": None,
                "success": True,
                "participant_id": owner,
                "solver_id": solver,
                "quality_tier": (
                    "onchain-finalized-rpc; GPv2Settlement Trade event; solver only when "
                    "matched to same-transaction Settlement event"
                ),
                "metric_definition": (
                    normalized["metric_definition"]
                    if normalized is not None
                    else (
                        "One finalized GPv2 Trade event per executed order. Amounts are raw token "
                        "units; no USD price, gas-inclusive execution cost, surplus, or solver is "
                        "imputed."
                    )
                ),
                "record_json": record_json,
            }
        )
        events.append(
            event_base | {"event_type": "trade", "solver_id": solver, "record_json": record_json}
        )
    return executions, events


def cow_rpc_participant_rows(executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose solver participation only where the Settlement event identifies it."""
    return [
        {
            "run_ts": row["run_ts"],
            "dt": row["dt"],
            "source": "cow",
            "venue": "cow-protocol",
            "participant_id": row["solver_id"],
            "participant_name": None,
            "instrument_id": row["instrument_id"],
            "metric": "solver_finalized_trade",
            "value": None,
            "execution_id": row["execution_id"],
            "quality_tier": "solver from same-transaction finalized Settlement event",
            "record_json": row["record_json"],
        }
        for row in executions
        if row.get("solver_id")
    ]


def geckoterminal_quote_rows(
    body_by_pool: dict[str, Any], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize third-party indexed pool state without calling it execution data."""
    rows = []
    for pool_id, body in body_by_pool.items():
        data = body.get("data") if isinstance(body, dict) else None
        attrs = data.get("attributes") if isinstance(data, dict) else None
        if not isinstance(attrs, dict):
            continue
        base_usd = _float(attrs.get("base_token_price_usd"))
        quote_usd = _float(attrs.get("quote_token_price_usd"))
        reserve_usd = _float(attrs.get("reserve_in_usd"))
        if base_usd is None and reserve_usd is None:
            continue
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "geckoterminal",
                "venue": attrs.get("dex_id") or "indexed-dex-pool",
                "instrument_id": pool_id.lower(),
                "quote_id": (data or {}).get("id") or pool_id.lower(),
                "quote_side": "indexed_pool_state",
                "price_usd": base_usd,
                "native_price": base_usd / quote_usd if quote_usd not in (None, 0) else None,
                "depth_usd": reserve_usd,
                "volume_usd_m5": _float((attrs.get("volume_usd") or {}).get("m5")),
                "volume_usd_h1": _float((attrs.get("volume_usd") or {}).get("h1")),
                "volume_usd_h24": _float((attrs.get("volume_usd") or {}).get("h24")),
                "quality_tier": (
                    "third-party-indexed-pool-state; reserve proxy, not executable depth or fills"
                ),
                "record_json": _json(data),
            }
        )
    return rows


def akash_market_snapshot_metadata(body: Any) -> dict[str, str] | None:
    """Extract the immutable height and time used to pin an Akash book query."""
    if not isinstance(body, dict):
        return None
    block = body.get("block") or {}
    header = block.get("header") if isinstance(block, dict) else None
    height = header.get("height") if isinstance(header, dict) else None
    timestamp = header.get("time") if isinstance(header, dict) else None
    if height is None or timestamp is None:
        return None
    try:
        if int(height) < 0:
            return None
    except (TypeError, ValueError):
        return None
    return {"height": str(height), "time": str(timestamp)}


def akash_market_list_url(
    kind: str, *, filters: dict[str, str], page_key: str | None = None
) -> str:
    """Return a state-filtered public Akash market-list URL.

    The block height is passed as a request header, because Cosmos' REST API
    treats it as a query-state selector rather than a URL parameter.
    """
    if kind not in {"bids", "orders"}:
        raise ValueError("Akash market list kind must be bids or orders")
    if filters.get("filters.state") != "open":
        raise ValueError("Akash market list filters must restrict state to open")
    params = {**filters, "pagination.limit": str(AKASH_MARKET_PAGE_SIZE)}
    if page_key:
        params["pagination.key"] = page_key
    return f"{AKASH_MARKET_API_URL}/{kind}/list?{urlencode(params)}"


def akash_order_bid_list_url(identifier: dict[str, Any], page_key: str | None = None) -> str:
    """Query all currently retained bid states for one immutable Akash order."""
    required = ("owner", "dseq", "gseq", "oseq")
    if any(identifier.get(field) is None for field in required):
        raise ValueError("Akash order identifier is incomplete")
    params = {
        f"filters.{field}": str(identifier[field])
        for field in required
    } | {"pagination.limit": str(AKASH_MARKET_PAGE_SIZE)}
    if page_key:
        params["pagination.key"] = page_key
    return f"{AKASH_MARKET_API_URL}/bids/list?{urlencode(params)}"


async def capture_akash_lease_choice_sets(
    fetcher: Fetcher,
    lease_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Retrospectively query every retained bid for recent accepted leases.

    This is stronger than an open-book snapshot because the selected bid is
    public.  It is still a post-selection chain-state query: losing bids that
    the chain has already pruned cannot be recovered and are never imputed.
    """
    latest = await fetcher.get_json(AKASH_LATEST_BLOCK_URL)
    snapshot = akash_market_snapshot_metadata(latest)
    if snapshot is None:
        return [], {
            "coverage_complete": False,
            "reason": "latest_block_metadata_unavailable",
            "snapshot_height": None,
            "snapshot_time": None,
        }
    orders: dict[str, dict[str, Any]] = {}
    selected_bid_ids: dict[str, set[str]] = {}
    for item in lease_records:
        lease = (
            item.get("lease")
            if isinstance(item, dict) and isinstance(item.get("lease"), dict)
            else item
        )
        if not isinstance(lease, dict):
            continue
        identifier = lease.get("id")
        order_id = _akash_order_id(identifier)
        bid_id = _lease_id(lease)
        if order_id is None or bid_id is None or not isinstance(identifier, dict):
            continue
        orders[order_id] = {
            field: identifier.get(field) for field in ("owner", "dseq", "gseq", "oseq")
        }
        selected_bid_ids.setdefault(order_id, set()).add(bid_id)
    selected_orders = sorted(orders)[:AKASH_CHOICE_MAX_ORDERS]
    headers = {"x-cosmos-block-height": snapshot["height"]}

    async def capture_order(order_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_key: str | None = None
        for page in range(1, AKASH_MARKET_MAX_PAGES + 1):
            body = await fetcher.get_json(
                akash_order_bid_list_url(orders[order_id], page_key=page_key),
                headers=headers,
            )
            records = body.get("bids") if isinstance(body, dict) else None
            if not isinstance(records, list) or not all(
                isinstance(record, dict) for record in records
            ):
                return [], {
                    "order_id": order_id,
                    "complete": False,
                    "reason": "invalid_page_response",
                    "pages_fetched": page,
                    "records_fetched": len(rows),
                }
            rows.extend(records)
            pagination = body.get("pagination") or {}
            next_key = pagination.get("next_key") if isinstance(pagination, dict) else None
            if not next_key:
                return rows, {
                    "order_id": order_id,
                    "complete": True,
                    "reason": None,
                    "pages_fetched": page,
                    "records_fetched": len(rows),
                    "selected_bid_ids": sorted(selected_bid_ids[order_id]),
                }
            page_key = str(next_key)
        return [], {
            "order_id": order_id,
            "complete": False,
            "reason": "pagination_cap_exceeded",
            "pages_fetched": AKASH_MARKET_MAX_PAGES,
            "records_fetched": len(rows),
        }

    if not selected_orders:
        return [], {
            "coverage_complete": False,
            "reason": "no_recent_leases_with_complete_ids",
            "snapshot_height": snapshot["height"],
            "snapshot_time": snapshot["time"],
        }
    results = await asyncio.gather(*(capture_order(order_id) for order_id in selected_orders))
    complete_results = [result for result in results if result[1]["complete"]]
    incomplete = [detail for _, detail in results if not detail["complete"]]
    payloads = [
        {
            "order_id": detail["order_id"],
            "selected_bid_ids": detail["selected_bid_ids"],
            "records": records,
        }
        for records, detail in complete_results
    ]
    return payloads, {
        "coverage_complete": not incomplete and len(complete_results) == len(selected_orders),
        "reason": "order_bid_query_incomplete" if incomplete else None,
        "snapshot_height": snapshot["height"],
        "snapshot_time": snapshot["time"],
        "lease_orders_available": len(orders),
        "orders_requested": len(selected_orders),
        "orders_complete": len(complete_results),
        "orders_capped": len(orders) > AKASH_CHOICE_MAX_ORDERS,
        "max_orders_per_run": AKASH_CHOICE_MAX_ORDERS,
        "bid_records_fetched": sum(detail["records_fetched"] for _, detail in complete_results),
        "incomplete_order_details": incomplete,
        "post_selection_query": True,
        "retention_boundary": (
            "complete pagination of bid records retained by current chain state for each "
            "queried recent lease order; bids already pruned before capture are not observable"
        ),
    }


def akash_bid_event_search_url(start_height: int, end_height: int, page: int) -> str:
    if start_height < 0 or end_height < start_height or page < 1:
        raise ValueError("invalid Akash bid-event search window")
    query = (
        "message.action='/akash.market.v1beta5.MsgCreateBid' "
        f"AND tx.height>{start_height} AND tx.height<={end_height}"
    )
    params = {
        "query": json.dumps(query),
        "page": json.dumps(str(page)),
        "per_page": json.dumps(str(AKASH_BID_EVENT_PAGE_SIZE)),
        "order_by": json.dumps("asc"),
    }
    return f"{AKASH_RPC_URL}/tx_search?{urlencode(params)}"


async def capture_akash_bid_events(
    fetcher: Fetcher, end_height: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Capture a complete bounded window of indexed public bid-create events."""
    start_height = max(0, end_height - AKASH_BID_EVENT_LOOKBACK_BLOCKS)
    pages: list[dict[str, Any]] = []
    total_count: int | None = None
    for page in range(1, AKASH_BID_EVENT_MAX_PAGES + 1):
        body = await fetcher.get_json(akash_bid_event_search_url(start_height, end_height, page))
        result = body.get("result") if isinstance(body, dict) else None
        txs = result.get("txs") if isinstance(result, dict) else None
        try:
            source_total = int(result.get("total_count")) if isinstance(result, dict) else None
        except (TypeError, ValueError):
            source_total = None
        if not isinstance(txs, list) or source_total is None or source_total < 0:
            return [], {
                "coverage_complete": False,
                "reason": "invalid_tx_search_page",
                "start_height_exclusive": start_height,
                "end_height_inclusive": end_height,
                "failed_page": page,
            }
        if total_count is None:
            total_count = source_total
        elif source_total != total_count:
            return [], {
                "coverage_complete": False,
                "reason": "tx_search_total_changed_during_pagination",
                "start_height_exclusive": start_height,
                "end_height_inclusive": end_height,
                "failed_page": page,
            }
        pages.append(body)
        if len(txs) < AKASH_BID_EVENT_PAGE_SIZE or page * AKASH_BID_EVENT_PAGE_SIZE >= total_count:
            return pages, {
                "coverage_complete": True,
                "reason": None,
                "start_height_exclusive": start_height,
                "end_height_inclusive": end_height,
                "pages_fetched": page,
                "transactions_fetched": sum(len(p["result"]["txs"]) for p in pages),
                "source_total_count": total_count,
            }
    return [], {
        "coverage_complete": False,
        "reason": "tx_search_pagination_cap_exceeded",
        "start_height_exclusive": start_height,
        "end_height_inclusive": end_height,
        "pages_fetched": AKASH_BID_EVENT_MAX_PAGES,
        "source_total_count": total_count,
    }


def _akash_closed_lease_blocks(
    lease_records: list[dict[str, Any]], start_height: int, end_height: int
) -> tuple[dict[int, set[str]], int]:
    """Return exact recent close blocks and lease IDs from the source lease list."""
    by_block: dict[int, set[str]] = {}
    closed_records = 0
    for item in lease_records:
        lease = (
            item.get("lease")
            if isinstance(item, dict) and isinstance(item.get("lease"), dict)
            else item
        )
        if not isinstance(lease, dict) or lease.get("state") != "closed":
            continue
        closed_records += 1
        lease_id = _lease_id(lease)
        block = _lease_block(lease)
        if lease_id is None or block is None or not start_height < block <= end_height:
            continue
        by_block.setdefault(block, set()).add(lease_id)
    return by_block, closed_records


async def capture_akash_lease_close_events(
    fetcher: Fetcher,
    lease_records: list[dict[str, Any]],
    end_height: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch exact block results for recent closed leases in a bounded window.

    The source lease list gives the immutable close height but not the actor or
    close reason. CometBFT block results contain the source-defined
    ``EventLeaseClosed`` reason. Every requested block must return a matching
    height and a well-formed result; otherwise the canonical event set fails
    closed for the run.
    """
    start_height = max(0, end_height - AKASH_CLOSE_EVENT_LOOKBACK_BLOCKS)
    expected, closed_records = _akash_closed_lease_blocks(
        lease_records, start_height, end_height
    )
    if not expected:
        return [], {
            "coverage_complete": True,
            "reason": None,
            "start_height_exclusive": start_height,
            "end_height_inclusive": end_height,
            "closed_lease_records_seen": closed_records,
            "expected_recent_closed_leases": 0,
            "close_blocks_requested": 0,
        }

    async def fetch_block(height: int) -> tuple[int, Any]:
        rpc_url = _configured_url("ORCAP_AKASH_RPC_URL", AKASH_RPC_URL).rstrip("/")
        return height, await fetcher.get_json(f"{rpc_url}/block_results?height={height}")

    results = await asyncio.gather(*(fetch_block(height) for height in sorted(expected)))
    malformed = []
    payloads = []
    for height, body in results:
        result = body.get("result") if isinstance(body, dict) else None
        try:
            returned_height = int(result.get("height")) if isinstance(result, dict) else None
        except (TypeError, ValueError):
            returned_height = None
        txs = result.get("txs_results") if isinstance(result, dict) else None
        if returned_height != height or (txs is not None and not isinstance(txs, list)):
            malformed.append(height)
            continue
        payloads.append(
            {
                "block_height": height,
                "expected_lease_ids": sorted(expected[height]),
                "body": body,
            }
        )
    if malformed:
        return [], {
            "coverage_complete": False,
            "reason": "malformed_close_block_results",
            "start_height_exclusive": start_height,
            "end_height_inclusive": end_height,
            "closed_lease_records_seen": closed_records,
            "expected_recent_closed_leases": sum(len(ids) for ids in expected.values()),
            "close_blocks_requested": len(expected),
            "malformed_block_heights": malformed,
        }
    return payloads, {
        "coverage_complete": True,
        "reason": None,
        "start_height_exclusive": start_height,
        "end_height_inclusive": end_height,
        "closed_lease_records_seen": closed_records,
        "expected_recent_closed_leases": sum(len(ids) for ids in expected.values()),
        "close_blocks_requested": len(expected),
        "close_blocks_fetched": len(payloads),
    }


async def capture_akash_open_market(
    fetcher: Fetcher, provider_ids: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch complete open bids for the live GPU-provider universe.

    The global open lists exceed a safe recurring raw-capture budget. Instead,
    the coverage universe is the current Console registry's online,
    version-valid GPU providers. The public LCD supports a height selector, so
    every provider query is pinned to one block. If any provider's pagination
    fails or exceeds the cap, no canonical bid rows are returned.
    """
    latest = await fetcher.get_json(AKASH_LATEST_BLOCK_URL)
    snapshot = akash_market_snapshot_metadata(latest)
    if snapshot is None:
        return [], {
            "coverage_complete": False,
            "reason": "latest_block_metadata_unavailable",
            "snapshot_height": None,
            "snapshot_time": None,
        }
    headers = {"x-cosmos-block-height": snapshot["height"]}

    async def capture_provider(provider: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_key: str | None = None
        for page in range(1, AKASH_MARKET_MAX_PAGES + 1):
            body = await fetcher.get_json(
                akash_market_list_url(
                    "bids",
                    filters={"filters.state": "open", "filters.provider": provider},
                    page_key=page_key,
                ),
                headers=headers,
            )
            records = body.get("bids") if isinstance(body, dict) else None
            if not isinstance(records, list) or not all(
                isinstance(record, dict) for record in records
            ):
                return [], {
                    "provider": provider,
                    "complete": False,
                    "pages_fetched": page,
                    "records_fetched": len(rows),
                    "reason": "invalid_page_response",
                }
            rows.extend(records)
            pagination = body.get("pagination") or {}
            next_key = pagination.get("next_key") if isinstance(pagination, dict) else None
            if not next_key:
                return rows, {
                    "provider": provider,
                    "complete": True,
                    "pages_fetched": page,
                    "records_fetched": len(rows),
                    "reason": None,
                }
            page_key = str(next_key)
        return [], {
            "provider": provider,
            "complete": False,
            "pages_fetched": AKASH_MARKET_MAX_PAGES,
            "records_fetched": len(rows),
            "reason": "pagination_cap_exceeded",
        }

    providers = sorted(set(provider_ids))
    if not providers:
        return [], {
            "coverage_complete": False,
            "reason": "no_live_gpu_providers",
            "snapshot_height": snapshot["height"],
            "snapshot_time": snapshot["time"],
        }
    results = await asyncio.gather(*(capture_provider(provider) for provider in providers))
    incomplete = [detail for _, detail in results if not detail["complete"]]
    if incomplete:
        return [], {
            "coverage_complete": False,
            "reason": "provider_bid_pagination_incomplete",
            "snapshot_height": snapshot["height"],
            "snapshot_time": snapshot["time"],
            "provider_count": len(providers),
            "incomplete_provider_count": len(incomplete),
            "incomplete_provider_details": incomplete,
            "pagination_page_size": AKASH_MARKET_PAGE_SIZE,
            "pagination_max_pages": AKASH_MARKET_MAX_PAGES,
        }
    bids_by_id: dict[str, dict[str, Any]] = {}
    for records, _ in results:
        for record in records:
            bid = record.get("bid") if isinstance(record.get("bid"), dict) else record
            bid_id = _akash_bid_id(bid.get("id") if isinstance(bid, dict) else None)
            if bid_id is not None:
                bids_by_id[bid_id] = record
    return list(bids_by_id.values()), {
        "coverage_complete": True,
        "snapshot_height": snapshot["height"],
        "snapshot_time": snapshot["time"],
        "provider_count": len(providers),
        "provider_queries_complete": len(results),
        "bid_records_fetched": sum(detail["records_fetched"] for _, detail in results),
        "bid_records_deduplicated": len(bids_by_id),
        "pagination_page_size": AKASH_MARKET_PAGE_SIZE,
        "pagination_max_pages": AKASH_MARKET_MAX_PAGES,
    }


def _akash_provider_graph_url(provider: str) -> str:
    return AKASH_PROVIDER_ACTIVE_LEASES_GRAPH_URL.format(provider=quote(provider, safe=""))


def _akash_provider_dashboard_url(provider: str) -> str:
    return AKASH_PROVIDER_DASHBOARD_URL.format(provider=quote(provider, safe=""))


async def capture_akash_provider_aggregates(
    fetcher: Fetcher,
    provider_ids: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch aggregate-only provider history for the current GPU-provider universe.

    The Console endpoints expose source-defined active-lease histories and
    provider aggregate cards. They do not require tenant, deployment, or
    workload records. All providers must return both documented aggregate
    payloads; otherwise the collector writes no partial canonical panel.
    """
    providers = sorted(set(provider_ids))
    if not providers:
        return [], {
            "coverage_complete": False,
            "reason": "no_live_gpu_providers",
            "provider_count": 0,
        }

    async def capture_provider(provider: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        graph, dashboard = await asyncio.gather(
            fetcher.get_json(_akash_provider_graph_url(provider)),
            fetcher.get_json(_akash_provider_dashboard_url(provider)),
        )
        snapshots = graph.get("snapshots") if isinstance(graph, dict) else None
        current = dashboard.get("current") if isinstance(dashboard, dict) else None
        if not isinstance(snapshots, list) or not all(
            isinstance(point, dict) for point in snapshots
        ):
            return None, {
                "provider": provider,
                "complete": False,
                "reason": "active_leases_graph_unavailable",
            }
        if (
            not isinstance(current, dict)
            or not current.get("date")
            or current.get("height") is None
        ):
            return None, {
                "provider": provider,
                "complete": False,
                "reason": "provider_dashboard_unavailable",
            }
        return {
            "provider_id": provider,
            "active_leases_graph": graph,
            "provider_dashboard": dashboard,
        }, {
            "provider": provider,
            "complete": True,
            "source_history_points": len(snapshots),
        }

    results = await asyncio.gather(*(capture_provider(provider) for provider in providers))
    incomplete = [detail for _, detail in results if not detail["complete"]]
    if incomplete:
        return [], {
            "coverage_complete": False,
            "reason": "provider_aggregate_response_incomplete",
            "provider_count": len(providers),
            "incomplete_provider_count": len(incomplete),
            "incomplete_provider_details": incomplete,
        }
    payloads = [payload for payload, _ in results if payload is not None]
    return payloads, {
        "coverage_complete": True,
        "provider_count": len(providers),
        "provider_queries_complete": len(payloads),
        "source_history_points_fetched": sum(
            detail["source_history_points"] for _, detail in results
        ),
    }


def _akash_source_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def akash_provider_aggregate_rows(
    payloads: list[dict[str, Any]],
    run_ts: str,
    dt: str,
    *,
    history_days: int = DEFAULT_AKASH_PROVIDER_HISTORY_DAYS,
) -> list[dict[str, Any]]:
    """Normalize recent provider aggregates without claiming demand or utilization.

    The public graph can contain a long source history. Retaining only the
    recent rolling window prevents hourly re-publication of an unchanged full
    back-history while preserving revisions around the dynamic panel's edge.
    """
    if not isinstance(history_days, int) or not 1 <= history_days <= 30:
        raise ValueError("history_days must be an integer between 1 and 30")
    cutoff = datetime.now(UTC) - timedelta(days=history_days)
    rows: list[dict[str, Any]] = []

    for payload in payloads:
        provider = payload.get("provider_id") if isinstance(payload, dict) else None
        graph = payload.get("active_leases_graph") if isinstance(payload, dict) else None
        dashboard = payload.get("provider_dashboard") if isinstance(payload, dict) else None
        snapshots = graph.get("snapshots") if isinstance(graph, dict) else None
        current = dashboard.get("current") if isinstance(dashboard, dict) else None
        if not isinstance(provider, str) or not provider or not isinstance(current, dict):
            continue
        observed_at = _akash_source_time(current.get("date"))
        height = _integer(current.get("height"))
        if observed_at is None or height is None or height <= 0:
            continue
        common = {
            "run_ts": run_ts,
            "dt": dt,
            "source": "akash_provider_aggregates",
            "venue": "akash-console-network-data",
            "provider_id": provider,
            "source_observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "source_block_height": height,
            "quality_tier": "public indexed provider aggregate; source-defined metric",
        }

        if isinstance(snapshots, list):
            for point in snapshots:
                if not isinstance(point, dict):
                    continue
                bucket_at = _akash_source_time(point.get("date"))
                value = _float(point.get("value"))
                if bucket_at is None or bucket_at < cutoff or value is None or value < 0:
                    continue
                rows.append(
                    common
                    | {
                        "observation_type": "source_reported_provider_history",
                        "source_bucket_at": bucket_at.isoformat().replace("+00:00", "Z"),
                        "metric": "source_reported_provider_active_lease_count_history",
                        "value": value,
                        "source_reported_unit": "leases",
                        "metric_definition": (
                            "Akash Console source-defined provider active-lease history for a "
                            "provider in the current live-GPU universe; not completed workloads, "
                            "GPU-hours, demand, utilization, price, or delivery."
                        ),
                        "record_json": _json(
                            {
                                "endpoint": _akash_provider_graph_url(provider),
                                "point": point,
                            }
                        ),
                    }
                )

        for field, metric, unit, definition in (
            (
                "activeLeaseCount",
                "source_reported_provider_current_active_lease_count",
                "leases",
                "Akash Console current provider active-lease count; not completed workloads "
                "or demand.",
            ),
            (
                "activeGPU",
                "source_reported_provider_current_active_gpu_count",
                "gpus",
                "Akash Console current provider active GPU count; source-indexed state, not "
                "utilization.",
            ),
        ):
            value = _float(current.get(field))
            if value is None or value < 0:
                continue
            rows.append(
                common
                | {
                    "observation_type": "source_reported_provider_snapshot",
                    "source_bucket_at": None,
                    "metric": metric,
                    "value": value,
                    "source_reported_unit": unit,
                    "metric_definition": definition,
                    "record_json": _json(
                        {"endpoint": _akash_provider_dashboard_url(provider), "field": field}
                    ),
                }
            )
        for denom in ("UAkt", "UAct", "UUsdc", "UUsd"):
            for prefix, horizon in (("total", "cumulative"), ("daily", "source_day")):
                field = f"{prefix}{denom}Earned"
                value = _float(current.get(field))
                if value is None or value < 0:
                    continue
                rows.append(
                    common
                    | {
                        "observation_type": "source_reported_provider_snapshot",
                        "source_bucket_at": None,
                        "metric": f"source_reported_provider_{horizon}_{denom.lower()}_earned",
                        "value": value,
                        "source_reported_unit": denom.lower(),
                        "metric_definition": (
                            f"Akash Console provider {horizon} {denom} earned aggregate in the "
                            "literal source unit; not audited revenue, provider profit, a "
                            "GPU-hour price, or welfare."
                        ),
                        "record_json": _json(
                            {"endpoint": _akash_provider_dashboard_url(provider), "field": field}
                        ),
                    }
                )
    return rows


def _akash_order_id(identifier: Any) -> str | None:
    if not isinstance(identifier, dict):
        return None
    values = [identifier.get(field) for field in ("owner", "dseq", "gseq", "oseq")]
    if any(value is None for value in values):
        return None
    return "/".join(str(value) for value in values)


def _akash_bid_id(identifier: Any) -> str | None:
    order_id = _akash_order_id(identifier)
    if order_id is None or not isinstance(identifier, dict):
        return None
    provider, bseq = identifier.get("provider"), identifier.get("bseq")
    if provider is None or bseq is None:
        return None
    return f"{order_id}/{provider}/{bseq}"


def _akash_resource_fields(resource: Any, count: Any) -> dict[str, Any] | None:
    if not isinstance(resource, dict):
        return None
    instances = _float(count)
    if instances is None or instances <= 0:
        return None
    gpu = resource.get("gpu") or {}
    gpu_units = _float((gpu.get("units") or {}).get("val"))
    if gpu_units is None or gpu_units <= 0:
        return None
    cpu = resource.get("cpu") or {}
    memory = resource.get("memory") or {}
    return {
        "resource_count": instances,
        "gpu_units_per_resource": gpu_units,
        "gpu_units_total": gpu_units * instances,
        "gpu_attributes_json": _json(gpu.get("attributes") or []),
        "cpu_units_per_resource": _float((cpu.get("units") or {}).get("val")),
        "memory_bytes_per_resource": _float((memory.get("quantity") or {}).get("val")),
    }


def _akash_market_row(
    *,
    run_ts: str,
    dt: str,
    snapshot: dict[str, Any],
    order_id: str,
    bid_id: str | None,
    owner: Any,
    provider: Any,
    state: Any,
    resource_index: int,
    resource: Any,
    count: Any,
    price: Any,
    record: dict[str, Any],
    book_side: str,
) -> dict[str, Any] | None:
    fields = _akash_resource_fields(resource, count)
    if fields is None:
        return None
    price = price if isinstance(price, dict) else {}
    return {
        "run_ts": run_ts,
        "dt": dt,
        "source": "akash",
        "venue": "akash-network",
        "snapshot_height": snapshot.get("snapshot_height") or snapshot.get("height"),
        "snapshot_time": snapshot.get("snapshot_time") or snapshot.get("time"),
        "book_side": book_side,
        "order_id": order_id,
        "bid_id": bid_id,
        "owner": owner,
        "provider": provider,
        "state": state,
        "resource_index": resource_index,
        "resource_id": f"{order_id}:resource:{resource_index}",
        "native_price_amount": _float(price.get("amount")),
        "native_price_denom": price.get("denom"),
        "native_price_unit": "native_per_block",
        "metric_definition": (
            "Block-pinned open Akash GPU market record with its raw native price field; "
            "not an executed lease, USD price, GPU-hour rate, capacity observation, or utilization."
        ),
        "record_json": _json(record),
        **fields,
    }


def akash_open_bid_rows(
    records: list[dict[str, Any]], snapshot: dict[str, Any], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize only GPU-bearing open provider bids from a pinned book."""
    rows = []
    for record in records:
        bid = record.get("bid") if isinstance(record.get("bid"), dict) else record
        if not isinstance(bid, dict) or bid.get("state") != "open":
            continue
        identifier = bid.get("id")
        order_id, bid_id = _akash_order_id(identifier), _akash_bid_id(identifier)
        if order_id is None or bid_id is None:
            continue
        for index, offer in enumerate(bid.get("resources_offer") or []):
            if not isinstance(offer, dict):
                continue
            row = _akash_market_row(
                run_ts=run_ts,
                dt=dt,
                snapshot=snapshot,
                order_id=order_id,
                bid_id=bid_id,
                owner=(identifier or {}).get("owner"),
                provider=(identifier or {}).get("provider"),
                state=bid.get("state"),
                resource_index=index,
                resource=offer.get("resources"),
                count=offer.get("count"),
                price=bid.get("price"),
                record=record,
                book_side="provider_open_bid",
            )
            if row is not None:
                rows.append(row)
    return rows


def akash_lease_choice_bid_rows(
    payloads: list[dict[str, Any]], snapshot: dict[str, Any], run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize post-selection bid sets and mark the publicly accepted contract."""
    rows = []
    for payload in payloads:
        order_id = payload.get("order_id") if isinstance(payload, dict) else None
        records = payload.get("records") if isinstance(payload, dict) else None
        selected = (
            set(payload.get("selected_bid_ids") or []) if isinstance(payload, dict) else set()
        )
        if not isinstance(order_id, str) or not isinstance(records, list) or not selected:
            continue
        for record in records:
            bid = (
                record.get("bid")
                if isinstance(record, dict) and isinstance(record.get("bid"), dict)
                else record
            )
            if not isinstance(bid, dict):
                continue
            identifier = bid.get("id")
            bid_id = _akash_bid_id(identifier)
            if bid_id is None or _akash_order_id(identifier) != order_id:
                continue
            for index, offer in enumerate(bid.get("resources_offer") or []):
                if not isinstance(offer, dict):
                    continue
                row = _akash_market_row(
                    run_ts=run_ts,
                    dt=dt,
                    snapshot=snapshot,
                    order_id=order_id,
                    bid_id=bid_id,
                    owner=(identifier or {}).get("owner"),
                    provider=(identifier or {}).get("provider"),
                    state=bid.get("state"),
                    resource_index=index,
                    resource=offer.get("resources"),
                    count=offer.get("count"),
                    price=bid.get("price"),
                    record=record,
                    book_side="retained_post_selection_bid",
                )
                if row is None:
                    continue
                row.update(
                    {
                        "choice_set_id": f"{order_id}@{snapshot.get('snapshot_height')}",
                        "selected_contract": bid_id in selected,
                        "selected_bid_ids_json": _json(sorted(selected)),
                        "choice_set_pagination_complete": True,
                        "post_selection_query": True,
                        "metric_definition": (
                            "Complete paginated bid records still retained by public Akash "
                            "chain state for a recent lease order, with the accepted contract "
                            "marked from the public lease ID. This is post-selection state: "
                            "already-pruned losing bids, workload delivery, and user routing "
                            "are not observed."
                        ),
                    }
                )
                rows.append(row)
    return rows


def akash_bid_event_rows(
    pages: list[dict[str, Any]],
    detail: dict[str, Any],
    selected_bid_ids: set[str],
    gpu_order_ids: set[str],
    run_ts: str,
    dt: str,
) -> list[dict[str, Any]]:
    """Normalize indexed bid-create events for recent selected GPU orders."""
    if detail.get("coverage_complete") is not True:
        return []
    rows = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        result = page.get("result") if isinstance(page, dict) else None
        for tx in result.get("txs", []) if isinstance(result, dict) else []:
            tx_result = tx.get("tx_result") if isinstance(tx, dict) else None
            if not isinstance(tx_result, dict) or int(tx_result.get("code") or 0) != 0:
                continue
            for event in tx_result.get("events") or []:
                if (
                    not isinstance(event, dict)
                    or event.get("type") != "akash.market.v1.EventBidCreated"
                ):
                    continue
                attributes = {
                    item.get("key"): item.get("value")
                    for item in event.get("attributes") or []
                    if isinstance(item, dict)
                }
                try:
                    identifier = json.loads(attributes.get("id"))
                    price = json.loads(attributes.get("price"))
                except (TypeError, json.JSONDecodeError):
                    continue
                order_id = _akash_order_id(identifier)
                bid_id = _akash_bid_id(identifier)
                amount = _float(price.get("amount")) if isinstance(price, dict) else None
                denom = price.get("denom") if isinstance(price, dict) else None
                if (
                    order_id not in gpu_order_ids
                    or bid_id is None
                    or amount is None
                    or amount < 0
                    or not isinstance(denom, str)
                    or not denom
                ):
                    continue
                identity = (str(tx.get("hash")), bid_id)
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(
                    {
                        "run_ts": run_ts,
                        "dt": dt,
                        "source": "akash",
                        "venue": "akash-network",
                        "choice_set_source": "indexed_bid_create_events",
                        "choice_set_id": (
                            f"{order_id}@events:{detail.get('start_height_exclusive')}:"
                            f"{detail.get('end_height_inclusive')}"
                        ),
                        "order_id": order_id,
                        "bid_id": bid_id,
                        "provider": identifier.get("provider"),
                        "bid_created_block": int(tx.get("height")),
                        "transaction_hash": tx.get("hash"),
                        "transaction_index": _integer(tx.get("index")),
                        "native_price_amount": amount,
                        "native_price_denom": denom,
                        "native_price_unit": "native_per_block",
                        "selected_contract": bid_id in selected_bid_ids,
                        "event_window_start_height_exclusive": detail.get(
                            "start_height_exclusive"
                        ),
                        "event_window_end_height_inclusive": detail.get(
                            "end_height_inclusive"
                        ),
                        "event_window_complete": True,
                        "metric_definition": (
                            "Public indexed Akash bid-create transaction for a recent GPU lease "
                            "order; the complete bounded event window restores bids that may no "
                            "longer appear in current state. It does not observe workload "
                            "delivery, utilization, user routing, cost, profit, or welfare."
                        ),
                        "record_json": _json(event),
                    }
                )
    return rows


def _akash_event_value(value: Any) -> Any:
    """Decode CometBFT event values that may themselves be JSON strings."""
    current = value
    for _ in range(2):
        if not isinstance(current, str):
            break
        try:
            current = json.loads(current)
        except json.JSONDecodeError:
            break
    return current


def _akash_close_actor(reason: str) -> str:
    normalized = reason.lower()
    if "provider" in normalized:
        return "provider"
    if "owner" in normalized or "tenant" in normalized:
        return "owner"
    if "insufficient" in normalized or "escrow" in normalized:
        return "escrow"
    return "other"


def akash_lease_close_event_rows(
    payloads: list[dict[str, Any]],
    detail: dict[str, Any],
    run_ts: str,
    dt: str,
) -> list[dict[str, Any]]:
    """Normalize exact source-defined close reasons for expected public leases."""
    if detail.get("coverage_complete") is not True:
        return []
    rows = []
    seen: set[tuple[int, str]] = set()
    raw_payload_source = str(detail.get("raw_payload_source") or "market_sources")
    raw_payload_path = f"raw/{raw_payload_source}/dt={dt}/{run_ts}.jsonl.gz"
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        expected = set(payload.get("expected_lease_ids") or [])
        body = payload.get("body")
        result = body.get("result") if isinstance(body, dict) else None
        height = _integer(result.get("height")) if isinstance(result, dict) else None
        txs = result.get("txs_results") if isinstance(result, dict) else None
        if height is None or (txs is not None and not isinstance(txs, list)):
            continue
        event_groups: list[tuple[str, int | None, list[Any]]] = []
        for tx_index, tx in enumerate(txs or []):
            if isinstance(tx, dict) and int(tx.get("code") or 0) == 0:
                event_groups.append(("transaction", tx_index, tx.get("events") or []))
        for field in ("finalize_block_events", "end_block_events", "begin_block_events"):
            events = result.get(field) if isinstance(result, dict) else None
            if isinstance(events, list):
                event_groups.append((field, None, events))
        for event_scope, tx_index, events in event_groups:
            for event in events:
                if (
                    not isinstance(event, dict)
                    or event.get("type") != "akash.market.v1.EventLeaseClosed"
                ):
                    continue
                attributes = {
                    item.get("key"): item.get("value")
                    for item in event.get("attributes") or []
                    if isinstance(item, dict)
                }
                identifier = _akash_event_value(attributes.get("id"))
                reason = _akash_event_value(attributes.get("reason"))
                lease_id = (
                    _lease_id({"id": identifier}) if isinstance(identifier, dict) else None
                )
                if lease_id is None or lease_id not in expected or not isinstance(reason, str):
                    continue
                identity = (height, lease_id)
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(
                    {
                        "run_ts": run_ts,
                        "dt": dt,
                        "source": "akash",
                        "venue": "akash-network",
                        "execution_id": lease_id,
                        "close_block_height": height,
                        "transaction_index": tx_index,
                        "event_scope": event_scope,
                        "message_index": _integer(attributes.get("msg_index")),
                        "close_reason": reason,
                        "close_actor_class": _akash_close_actor(reason),
                        "owner": identifier.get("owner"),
                        "provider": identifier.get("provider"),
                        "dseq": str(identifier.get("dseq")),
                        "gseq": _integer(identifier.get("gseq")),
                        "oseq": _integer(identifier.get("oseq")),
                        "bseq": _integer(identifier.get("bseq")),
                        "event_window_start_height_exclusive": detail.get(
                            "start_height_exclusive"
                        ),
                        "event_window_end_height_inclusive": detail.get(
                            "end_height_inclusive"
                        ),
                        "event_window_complete": True,
                        "raw_payload_path": raw_payload_path,
                        "raw_block_height": height,
                        "metric_definition": (
                            "Exact public Akash EventLeaseClosed reason for a lease returned "
                            "by the source lease list in the bounded close-block window. It "
                            "identifies the on-chain termination path, not workload delivery, "
                            "failure, default, "
                            "or actor intent."
                        ),
                        "record_json": _json(event),
                    }
                )
    return rows


def akash_capacity_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Return live, version-valid *GPU* capacity observations from Akash.

    ``/v1/providers`` is a registry as well as a capacity view.  Most registry
    records are offline and report all-zero stats, which must not become a
    zero-supply market observation.  The endpoint reports provider-level GPU
    totals but does not allocate those totals across a provider's listed GPU
    models, so model mix is retained as metadata rather than manufactured as
    per-model capacity.
    """
    records = _as_list(body, "providers", "data", "items")
    rows = []
    for item in records:
        participant = item.get("owner") or item.get("address") or item.get("id")
        if not participant:
            continue
        attrs_raw = item.get("attributes") or {}
        attrs = (
            {str(a.get("key")): a.get("value") for a in attrs_raw if isinstance(a, dict)}
            if isinstance(attrs_raw, list)
            else attrs_raw
        )
        stats = item.get("stats") or {}
        gpu = stats.get("gpu") or {}
        total = _first_number(gpu.get("total"), item.get("total"), item.get("capacity"))
        available = _first_number(gpu.get("available"), item.get("available"), item.get("capacity"))
        used = _first_number(gpu.get("active"), item.get("used"))
        # Missing boolean flags occur in lightweight test fixtures and older
        # responses.  Explicit false is a meaningful exclusion; missing is
        # left eligible only if a positive GPU total is actually reported.
        if item.get("isOnline") is False or item.get("isValidVersion") is False:
            continue
        if total is None or total <= 0:
            continue
        gpu_models = item.get("gpuModels") or item.get("hardwareGpuModels") or []
        model_labels = []
        for model in gpu_models:
            if isinstance(model, dict):
                label = ":".join(
                    str(part)
                    for part in (model.get("vendor"), model.get("model"), model.get("ram"))
                    if part
                )
            else:
                label = str(model)
            if label:
                model_labels.append(label)
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "akash",
                "venue": "akash-network",
                "participant_id": participant,
                "resource_id": f"{item.get('hostUri') or participant}#gpu",
                "resource_kind": "gpu",
                "resource_unit": "gpus",
                "resource_class": ",".join(sorted(set(model_labels))) or None,
                "available": available,
                "total": total,
                "used": used,
                "cpu_cores": None,
                "gpu_count": total,
                "memory_gib": None,
                "region": (
                    attrs.get("region")
                    or attrs.get("location-region")
                    or item.get("ipRegion")
                    or item.get("region")
                    or item.get("country")
                ),
                "is_online": item.get("isOnline"),
                "is_valid_version": item.get("isValidVersion"),
                "is_audited": item.get("isAudited"),
                "uptime_1d": _float(item.get("uptime1d")),
                "uptime_7d": _float(item.get("uptime7d")),
                "uptime_30d": _float(item.get("uptime30d")),
                "quality_tier": "live-version-valid-provider-aggregate-gpu",
                "record_json": _json(item),
            }
        )
    return rows


def akash_registry_summary(body: Any) -> dict[str, int]:
    """Coverage ledger for the registry-to-capacity filtering decision."""
    records = _as_list(body, "providers", "data", "items")
    online = [row for row in records if row.get("isOnline") is True]
    valid = [row for row in online if row.get("isValidVersion") is not False]
    with_gpu = [
        row
        for row in valid
        if _float(((row.get("stats") or {}).get("gpu") or {}).get("total")) not in (None, 0.0)
    ]
    return {
        "registry_providers": len(records),
        "online_providers": len(online),
        "online_version_valid_providers": len(valid),
        "online_gpu_capacity_providers": len(with_gpu),
    }


def akash_live_gpu_provider_ids(body: Any) -> list[str]:
    """Return the transparent GPU-provider coverage universe for open bids."""
    return sorted(
        {
            str(row["participant_id"])
            for row in akash_capacity_rows(body, "", "")
            if row.get("participant_id")
        }
    )


def akash_gpu_quote_rows(body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Normalize public aggregate Akash GPU quotes without fabricating fills.

    The Console response aggregates provider offers by exact GPU model/RAM/
    interface and already reports USD-per-hour price statistics.  Availability
    is retained on the quote row because the source does not map aggregate
    model units back to individual provider capacity rows.
    """
    models = _as_list(body, "models", "data")
    rows = []
    for model in models:
        price = model.get("price") or {}
        weighted = _float(price.get("weightedAverage"))
        median = _float(price.get("med"))
        if weighted is None and median is None:
            continue
        vendor = model.get("vendor") or "unknown"
        name = model.get("model") or "unknown"
        ram = model.get("ram") or "unknown"
        interface = model.get("interface") or "unknown"
        availability = model.get("availability") or {}
        provider_availability = model.get("providerAvailability") or {}
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "akash",
                "venue": "akash-network",
                "instrument_id": f"gpu:{vendor}:{name}:{ram}:{interface}",
                "quote_id": f"{vendor}:{name}:{ram}:{interface}",
                "quote_side": "aggregate_weighted_provider_quote",
                "quote_unit": "usd_per_gpu_hour",
                "price_usd": weighted if weighted is not None else median,
                "native_price": _float((model.get("priceUakt") or {}).get("weightedAverage")),
                "price_min_usd_hr": _float(price.get("min")),
                "price_max_usd_hr": _float(price.get("max")),
                "price_avg_usd_hr": _float(price.get("avg")),
                "price_weighted_avg_usd_hr": weighted,
                "price_median_usd_hr": median,
                "available_units": _float(availability.get("available")),
                "total_units": _float(availability.get("total")),
                "provider_available_count": _float(provider_availability.get("available")),
                "provider_total_count": _float(provider_availability.get("total")),
                "depth_usd": None,
                "quality_tier": "public-aggregate-gpu-quote",
                "record_json": _json(model),
            }
        )
    return rows


def _lease_id(lease: dict[str, Any]) -> str | None:
    identifier = lease.get("id") or {}
    fields = ("owner", "dseq", "gseq", "oseq", "provider", "bseq")
    values = [identifier.get(field) for field in fields]
    if not all(value is not None for value in values):
        return None
    return "/".join(str(value) for value in values)


def _block_time(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    result = body.get("result") or {}
    # CometBFT ``/header`` is sufficient for a timestamp and avoids storing
    # every unrelated transaction in the raw capture of a lease lifecycle.
    header = result.get("header") or ((result.get("block") or {}).get("header") or {})
    return header.get("time")


def _lease_block(lease: dict[str, Any]) -> int | None:
    value = lease.get("closed_on") if lease.get("state") == "closed" else lease.get("created_at")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def akash_lease_execution_rows(
    body: Any,
    block_times: dict[int, str | None],
    run_ts: str,
    dt: str,
    *,
    snapshot_height: int | str | None = None,
    snapshot_time: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize on-chain lease lifecycle events without calling them workloads.

    A lease is a capacity-market contract.  Its close state does not reveal
    task success, GPU-hours consumed, or a USD clearing price; those are
    deliberately left null.  Payment rates remain in native denomination.
    """
    rows = []
    for item in _as_list(body, "leases", "data"):
        lease = item.get("lease") if isinstance(item.get("lease"), dict) else item
        if not isinstance(lease, dict):
            continue
        execution_id = _lease_id(lease)
        if not execution_id:
            continue
        created_at_block = _integer(lease.get("created_at"))
        closed_on_block = _integer(lease.get("closed_on"))
        block_height = _lease_block(lease)
        payment = item.get("escrow_payment") or {}
        payment_state = payment.get("state") or {}
        rate = payment_state.get("rate") or lease.get("price") or {}
        withdrawn = payment_state.get("withdrawn") or {}
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "akash",
                "venue": "akash-network",
                "execution_id": execution_id,
                "instrument_id": "akash:lease-contract",
                "snapshot_height": _integer(snapshot_height),
                "snapshot_time": snapshot_time,
                "created_at_block": created_at_block,
                "closed_on_block": closed_on_block,
                "executed_at": block_times.get(block_height),
                "event_block_height": block_height,
                "lease_state": lease.get("state"),
                "side": "capacity_lease",
                "requested_size": None,
                "filled_size": None,
                "gross_price_usd": None,
                "native_price": None,
                "rate_denom": rate.get("denom"),
                "rate_amount_native": _float(rate.get("amount")),
                "fee_native": None,
                "gas_native": None,
                "settled_denom": withdrawn.get("denom"),
                "settled_amount_native": _float(withdrawn.get("amount")),
                "success": None,
                "participant_id": (lease.get("id") or {}).get("provider"),
                "metric_definition": (
                    "On-chain Akash lease lifecycle contract; state and native payment rate, "
                    "not workload success, GPU-hours consumed, or USD execution price"
                ),
                "record_json": _json(item),
            }
        )
    return rows


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def akash_dashboard_rows(
    dashboard: Any, network_capacity: Any, run_ts: str, dt: str
) -> list[dict[str, Any]]:
    """Normalize public Akash network aggregates without inferring unit economics.

    The Console dashboard is a source-indexed aggregate view. It complements,
    but cannot be joined one-to-one with, the provider/GPU and lease panels.
    In particular, its spend fields are kept in their literal source units and
    are never divided by GPU or lease counts to manufacture prices or usage.
    """
    if not isinstance(dashboard, dict) or not isinstance(network_capacity, dict):
        return []
    now = dashboard.get("now")
    if not isinstance(now, dict):
        return []
    observed_at = now.get("date")
    block_height = _integer(now.get("height"))
    if (
        not isinstance(observed_at, str)
        or not observed_at
        or block_height is None
        or block_height <= 0
    ):
        return []
    compare = dashboard.get("compare") if isinstance(dashboard.get("compare"), dict) else {}
    common = {
        "run_ts": run_ts,
        "dt": dt,
        "source": "akash_dashboard",
        "venue": "akash-console-network-data",
        "source_observed_at": observed_at,
        "source_block_height": block_height,
        "source_compare_at": compare.get("date"),
        "source_compare_block_height": _integer(compare.get("height")),
        "quality_tier": "public indexed network aggregate; source-defined metric",
    }
    rows: list[dict[str, Any]] = []

    def emit(
        *,
        metric: str,
        value: Any,
        unit: str,
        endpoint: str,
        path: str,
        definition: str,
    ) -> None:
        numeric = _float(value)
        if numeric is None or numeric < 0:
            return
        rows.append(
            common
            | {
                "metric": metric,
                "value": numeric,
                "source_reported_unit": unit,
                "metric_definition": definition,
                "record_json": _json({"endpoint": endpoint, "path": path}),
            }
        )

    for field, metric, unit, definition in (
        (
            "activeLeaseCount",
            "source_reported_active_lease_count",
            "leases",
            "Akash dashboard active lease-contract count; not completed workloads or demand.",
        ),
        (
            "totalLeaseCount",
            "source_reported_total_lease_count",
            "leases",
            "Akash dashboard cumulative lease-contract count; not delivered compute.",
        ),
        (
            "dailyLeaseCount",
            "source_reported_daily_lease_count",
            "leases",
            "Akash dashboard source-defined daily lease count; not successful workloads.",
        ),
        (
            "activeGPU",
            "source_reported_dashboard_active_gpu_count",
            "gpus",
            "Akash dashboard active GPU count; source-indexed state, not utilization or "
            "audited GPUs.",
        ),
    ):
        emit(
            metric=metric,
            value=now.get(field),
            unit=unit,
            endpoint=AKASH_DASHBOARD_URL,
            path=f"now.{field}",
            definition=definition,
        )
    for denom in ("UAkt", "UAct", "UUsdc", "UUsd"):
        for prefix, horizon in (("total", "cumulative"), ("daily", "source_day")):
            field = f"{prefix}{denom}Spent"
            emit(
                metric=f"source_reported_{horizon}_{denom.lower()}_spent",
                value=now.get(field),
                unit=denom.lower(),
                endpoint=AKASH_DASHBOARD_URL,
                path=f"now.{field}",
                definition=(
                    f"Akash dashboard {horizon} {denom} spend in the literal source unit; "
                    "aggregate protocol spend, not provider revenue, a GPU-hour price, or welfare."
                ),
            )

    resources = network_capacity.get("resources")
    gpu = resources.get("gpu") if isinstance(resources, dict) else None
    if isinstance(gpu, dict):
        for state in ("active", "pending", "available", "total"):
            emit(
                metric=f"source_reported_network_gpu_{state}",
                value=gpu.get(state),
                unit="gpus",
                endpoint=AKASH_NETWORK_CAPACITY_URL,
                path=f"resources.gpu.{state}",
                definition=(
                    f"Akash network-capacity GPU {state} count; source-indexed aggregate, not "
                    "model-specific capacity, a physical-GPU audit, or utilization."
                ),
            )
    emit(
        metric="source_reported_network_active_provider_count",
        value=network_capacity.get("activeProviderCount"),
        unit="providers",
        endpoint=AKASH_NETWORK_CAPACITY_URL,
        path="activeProviderCount",
        definition=(
            "Akash network-capacity active-provider count; source-indexed aggregate, not an "
            "individual provider quality or capacity observation."
        ),
    )
    return rows


def _ratio(numerator: Any, denominator: Any) -> float | None:
    n, d = _float(numerator), _float(denominator)
    return n / d if n is not None and d not in (None, 0) else None


def _first_number(*values: Any) -> float | None:
    """Return the first parseable number while preserving zero as a value."""
    for value in values:
        number = _float(value)
        if number is not None:
            return number
    return None


def _union_table(rows: list[dict[str, Any]]) -> pa.Table:
    """Build a table from all observed keys, not just the first source row.

    Market tables intentionally combine heterogeneous source adapters. PyArrow
    infers ``from_pylist`` fields from the first row, which would drop fields
    unique to a later source (for example CoW solver metadata after
    DefiLlama participants). Building column arrays across the whole batch
    retains those fields while preserving nulls for sources that lack them.
    """
    fields = sorted({field for row in rows for field in row})
    return pa.Table.from_pydict({field: [row.get(field) for row in rows] for field in fields})


def _write(rows: list[dict[str, Any]], table: str, run_ts: str, dt: str, curated_dir: Path) -> None:
    if rows:
        write_partition(_union_table(rows), table, run_ts, dt, curated_dir)


def instrument_map_rows(run_ts: str, dt: str) -> list[dict[str, Any]]:
    with INSTRUMENTS_PATH.open("rb") as f:
        instruments = tomllib.load(f)["instruments"]
    return [
        {
            "run_ts": run_ts,
            "dt": dt,
            "map_id": name,
            "source": raw["source"],
            "source_id": raw["source_id"],
            "canonical_instrument": raw["canonical_instrument"],
            "venue": raw["venue"],
            "quality_tier": raw["quality_tier"],
            "mapping_version": "v1",
            "record_json": _json(raw),
        }
        for name, raw in instruments.items()
    ]


def execution_events(rows: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [
        {
            "run_ts": row["run_ts"],
            "dt": row["dt"],
            "source": row["source"],
            "event_id": f"{row['source']}:{row['execution_id']}",
            "event_type": event_type,
            "event_time": row["executed_at"],
            "instrument_id": row["instrument_id"],
            "record_json": row["record_json"],
        }
        for row in rows
        if row.get("execution_id")
    ]


async def _ethereum_rpc(
    fetcher: Fetcher,
    url: str,
    method: str,
    params: list[Any],
    *,
    record_url: str = "configured:ORCAP_ETHEREUM_RPC_URL",
) -> tuple[Any | None, str | None]:
    """Make one JSON-RPC call while retaining only a redacted endpoint label."""
    body = await fetcher.post_json(
        url,
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        record_url=record_url,
    )
    if not isinstance(body, dict):
        return None, "no JSON-RPC response"
    if isinstance(body.get("error"), dict):
        return None, str(body["error"].get("message") or "JSON-RPC error")
    if "result" not in body:
        return None, "JSON-RPC response has no result"
    return body["result"], None


async def _ethereum_rpc_batch(
    fetcher: Fetcher,
    url: str,
    calls: list[tuple[int, str, list[Any]]],
    *,
    record_url: str = "configured:ORCAP_ETHEREUM_RPC_URL",
) -> tuple[dict[int, Any], list[str]]:
    """Fetch block headers in one standard JSON-RPC batch request."""
    if not calls:
        return {}, []
    body = await fetcher.post_json(
        url,
        [
            {"jsonrpc": "2.0", "id": call_id, "method": method, "params": params}
            for call_id, method, params in calls
        ],
        record_url=record_url,
    )
    if not isinstance(body, list):
        return {}, ["no JSON-RPC batch response"]
    results, errors = {}, []
    for item in body:
        if not isinstance(item, dict):
            continue
        call_id = item.get("id")
        if not isinstance(call_id, int):
            continue
        if isinstance(item.get("error"), dict):
            errors.append(str(item["error"].get("message") or "JSON-RPC batch error"))
            continue
        if "result" in item:
            results[call_id] = item["result"]
    return results, errors


async def _capture_uniswap_rpc_logs(
    fetcher: Fetcher,
    url: str,
    *,
    record_url: str = "configured:ORCAP_ETHEREUM_RPC_URL",
    rpc_mode: str = "operator_configured",
) -> tuple[list[dict[str, Any]], dict[int, str | None], dict[str, Any]]:
    """Fetch a bounded, finalized log window for registered Uniswap V3 pools."""
    latest_raw, latest_error = await _ethereum_rpc(
        fetcher, url, "eth_blockNumber", [], record_url=record_url
    )
    latest_block = _hex_int(latest_raw)
    if latest_block is None:
        return (
            [],
            {},
            {
                "rpc_configured": True,
                "rpc_mode": rpc_mode,
                "error": latest_error or "invalid latest block",
            },
        )
    finality_blocks = _bounded_int_env(
        "ORCAP_ETHEREUM_FINALITY_BLOCKS",
        DEFAULT_ETHEREUM_FINALITY_BLOCKS,
        minimum=1,
        maximum=10_000,
    )
    window_blocks = _bounded_int_env(
        "ORCAP_UNISWAP_LOG_WINDOW_BLOCKS",
        DEFAULT_UNISWAP_LOG_WINDOW_BLOCKS,
        minimum=1,
        maximum=10_000,
    )
    finalized_through = latest_block - finality_blocks
    if finalized_through < 0:
        return (
            [],
            {},
            {
                "rpc_configured": True,
                "rpc_mode": rpc_mode,
                "latest_block": latest_block,
                "finality_blocks": finality_blocks,
                "error": "chain height is below requested finality depth",
            },
        )
    from_block = max(0, finalized_through - window_blocks + 1)
    result, logs_error = await _ethereum_rpc(
        fetcher,
        url,
        "eth_getLogs",
        [
            {
                "fromBlock": _hex_quantity(from_block),
                "toBlock": _hex_quantity(finalized_through),
                "address": sorted(uniswap_pool_specs()),
                "topics": [[UNISWAP_V3_SWAP_TOPIC, UNISWAP_V3_MINT_TOPIC, UNISWAP_V3_BURN_TOPIC]],
            }
        ],
        record_url=record_url,
    )
    logs = [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []
    detail: dict[str, Any] = {
        "rpc_configured": True,
        "rpc_mode": rpc_mode,
        "recent_bounded_only": rpc_mode == "public_bounded_live",
        "latest_block": latest_block,
        "finality_blocks": finality_blocks,
        "finalized_through_block": finalized_through,
        "from_block": from_block,
        "to_block": finalized_through,
        "log_window_blocks": window_blocks,
        "log_rows": len(logs),
    }
    if logs_error:
        detail["error"] = logs_error
        return [], {}, detail
    # An empty result is still a successful observation of every block in the
    # requested range. Record that distinction so H41 can measure continuity
    # without confusing a failed JSON-RPC call for an event-free interval.
    detail["log_query_succeeded"] = True
    block_numbers = sorted(
        {block for item in logs if (block := _hex_int(item.get("blockNumber"))) is not None}
    )
    responses, errors = await _ethereum_rpc_batch(
        fetcher,
        url,
        [
            (index, "eth_getBlockByNumber", [_hex_quantity(block_number), False])
            for index, block_number in enumerate(block_numbers, start=1)
        ],
        record_url=record_url,
    )
    header_block_times = {
        block_number: _ethereum_block_time(responses.get(index))
        for index, block_number in enumerate(block_numbers, start=1)
    }
    metadata_block_times = _log_block_times(logs)
    block_times = {
        block_number: header_block_times.get(block_number) or metadata_block_times.get(block_number)
        for block_number in block_numbers
    }
    detail["block_timestamp_rows"] = sum(value is not None for value in block_times.values())
    detail["log_metadata_timestamp_rows"] = sum(
        block_number not in {key for key, value in header_block_times.items() if value is not None}
        and value is not None
        for block_number, value in block_times.items()
    )
    if errors:
        detail["block_timestamp_errors"] = len(errors)
    return logs, block_times, detail


async def _capture_uniswap_quoter_quotes(
    fetcher: Fetcher,
    url: str,
    finalized_block: int | None,
    *,
    record_url: str = "configured:ORCAP_ETHEREUM_RPC_URL",
    rpc_mode: str = "operator_configured",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Query official QuoterV2 at a finality-buffered block for fixed USDC sizes."""
    if finalized_block is None or finalized_block < 0:
        return [], {"error": "no finalized block available for QuoterV2 simulation"}
    records = []
    errors = 0
    for pool_id, spec in sorted(uniswap_pool_specs().items()):
        if spec["token0_symbol"] != "USDC" or spec["token1_symbol"] != "WETH":
            continue
        for bucket in UNISWAP_USDC_QUOTE_BUCKETS:
            amount_in_raw = bucket * 10 ** int(spec["token0_decimals"])
            result, error = await _ethereum_rpc(
                fetcher,
                url,
                "eth_call",
                [
                    {
                        "to": UNISWAP_V3_QUOTER_V2_ADDRESS,
                        "data": _uniswap_quoter_calldata(spec, amount_in_raw),
                    },
                    _hex_quantity(finalized_block),
                ],
                record_url=record_url,
            )
            if error:
                errors += 1
                continue
            records.append(
                {
                    "pool_id": pool_id,
                    "spec": spec,
                    "block_number": finalized_block,
                    "input_bucket_usdc": bucket,
                    "amount_in_raw": amount_in_raw,
                    "result": result,
                }
            )
    detail = {
        "quoter_v2_address": UNISWAP_V3_QUOTER_V2_ADDRESS,
        "rpc_mode": rpc_mode,
        "recent_bounded_only": rpc_mode == "public_bounded_live",
        "finalized_block": finalized_block,
        "input_buckets_usdc": list(UNISWAP_USDC_QUOTE_BUCKETS),
        "quoter_quote_rows": len(records),
        "quoter_quote_errors": errors,
    }
    return records, detail


def _uniswap_tick_book_word_positions(tick_spacing: int) -> list[int]:
    """Return every usable V3 bitmap word for a positive pool tick spacing."""
    if not isinstance(tick_spacing, int) or tick_spacing <= 0:
        raise ValueError("Uniswap V3 tick spacing must be positive")
    minimum_tick = -((abs(UNISWAP_V3_MIN_TICK) // tick_spacing) * tick_spacing)
    maximum_tick = (UNISWAP_V3_MAX_TICK // tick_spacing) * tick_spacing
    minimum_word = (minimum_tick // tick_spacing) // 256
    maximum_word = (maximum_tick // tick_spacing) // 256
    if not -(2**15) <= minimum_word <= maximum_word < 2**15:
        raise ValueError("Uniswap V3 bitmap words exceed int16 range")
    return list(range(minimum_word, maximum_word + 1))


async def _capture_uniswap_tick_book(
    fetcher: Fetcher,
    url: str,
    finalized_block: int | None,
    *,
    record_url: str = "configured:ORCAP_ETHEREUM_RPC_URL",
    rpc_mode: str = "operator_configured",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Capture a fail-closed, complete initialized-tick book for each registered pool.

    TickLens retrieves all populated ticks in one bitmap word. Multicall2
    batches those word calls in a single EVM ``eth_call`` so this stays bounded
    on a public RPC without accepting a partial word range as a full book.
    """
    if finalized_block is None or finalized_block < 0:
        return [], {
            "coverage_complete": False,
            "error": "no finalized block available for Uniswap tick-book capture",
        }
    batch_words = _bounded_int_env(
        "ORCAP_UNISWAP_TICK_BOOK_BATCH_WORDS",
        DEFAULT_UNISWAP_TICK_BOOK_BATCH_WORDS,
        minimum=1,
        maximum=64,
    )
    max_rows_per_pool = _bounded_int_env(
        "ORCAP_UNISWAP_TICK_BOOK_MAX_ROWS_PER_POOL",
        DEFAULT_UNISWAP_TICK_BOOK_MAX_ROWS_PER_POOL,
        minimum=1,
        maximum=2_000_000,
    )
    all_records, pool_details = [], {}
    for pool_id, spec in sorted(uniswap_pool_specs().items()):
        tick_spacing_data, spacing_error = await _ethereum_rpc(
            fetcher,
            url,
            "eth_call",
            [
                {"to": pool_id, "data": "0x" + UNISWAP_V3_TICK_SPACING_SELECTOR},
                _hex_quantity(finalized_block),
            ],
            record_url=record_url,
        )
        slot0_data, slot0_error = await _ethereum_rpc(
            fetcher,
            url,
            "eth_call",
            [
                {"to": pool_id, "data": "0x" + UNISWAP_V3_SLOT0_SELECTOR},
                _hex_quantity(finalized_block),
            ],
            record_url=record_url,
        )
        liquidity_data, liquidity_error = await _ethereum_rpc(
            fetcher,
            url,
            "eth_call",
            [
                {"to": pool_id, "data": "0x" + UNISWAP_V3_LIQUIDITY_SELECTOR},
                _hex_quantity(finalized_block),
            ],
            record_url=record_url,
        )
        tick_spacing = _signed_word(tick_spacing_data, 0)
        sqrt_price_x96, current_tick = _word(slot0_data, 0), _signed_word(slot0_data, 1)
        active_liquidity_raw = _word(liquidity_data, 0)
        state_errors = [
            error for error in (spacing_error, slot0_error, liquidity_error) if error is not None
        ]
        if (
            state_errors
            or tick_spacing is None
            or tick_spacing <= 0
            or sqrt_price_x96 is None
            or current_tick is None
            or active_liquidity_raw is None
        ):
            pool_details[pool_id] = {
                "complete": False,
                "error": "; ".join(state_errors) or "invalid pool state response",
            }
            continue
        try:
            word_positions = _uniswap_tick_book_word_positions(tick_spacing)
        except ValueError as exc:
            pool_details[pool_id] = {"complete": False, "error": str(exc)}
            continue

        pool_records, seen_ticks, error, multicall_requests = [], set(), None, 0
        for start in range(0, len(word_positions), batch_words):
            batch = word_positions[start : start + batch_words]
            result, rpc_error = await _ethereum_rpc(
                fetcher,
                url,
                "eth_call",
                [
                    {
                        "to": UNISWAP_V3_MULTICALL2_ADDRESS,
                        "data": _multicall2_aggregate_calldata(
                            [
                                (
                                    UNISWAP_V3_TICK_LENS_ADDRESS,
                                    _uniswap_tick_lens_calldata(pool_id, word_position),
                                )
                                for word_position in batch
                            ]
                        ),
                    },
                    _hex_quantity(finalized_block),
                ],
                record_url=record_url,
            )
            multicall_requests += 1
            decoded = _multicall2_aggregate_result(result)
            if rpc_error or decoded is None:
                error = rpc_error or "malformed Multicall2 aggregate response"
                break
            returned_block, return_data = decoded
            if returned_block != finalized_block:
                error = (
                    "Multicall2 block number does not match requested finalized block "
                    f"({returned_block} != {finalized_block})"
                )
                break
            if len(return_data) != len(batch):
                error = "Multicall2 returned an incomplete TickLens word batch"
                break
            for word_position, word_data in zip(batch, return_data, strict=True):
                populated_ticks = _tick_lens_populated_ticks(word_data)
                if populated_ticks is None:
                    error = f"malformed TickLens response for bitmap word {word_position}"
                    break
                for tick_data in populated_ticks:
                    tick = tick_data["tick"]
                    if (
                        tick in seen_ticks
                        or tick % tick_spacing
                        or not UNISWAP_V3_MIN_TICK <= tick <= UNISWAP_V3_MAX_TICK
                        or (tick // tick_spacing) // 256 != word_position
                    ):
                        error = (
                            f"invalid or duplicate initialized tick in bitmap word {word_position}"
                        )
                        break
                    seen_ticks.add(tick)
                    pool_records.append(
                        {
                            "pool_id": pool_id,
                            "spec": spec,
                            "block_number": finalized_block,
                            "word_position": word_position,
                            "tick_spacing": tick_spacing,
                            "sqrt_price_x96": sqrt_price_x96,
                            "current_tick": current_tick,
                            "active_liquidity_raw": active_liquidity_raw,
                            **tick_data,
                        }
                    )
                    if len(pool_records) > max_rows_per_pool:
                        error = (
                            "initialized-tick row cap exceeded; refusing a partial pool snapshot "
                            f"({max_rows_per_pool})"
                        )
                        break
                if error:
                    break
            if error:
                break
        pool_details[pool_id] = {
            "complete": error is None,
            "tick_spacing": tick_spacing,
            "usable_bitmap_words": len(word_positions),
            "multicall_requests": multicall_requests,
            "initialized_tick_rows": len(pool_records) if error is None else 0,
            "error": error,
        }
        # A failed last word must never appear as an apparently complete pool.
        if error is None:
            all_records.extend(pool_records)

    coverage_complete = bool(pool_details) and all(
        detail["complete"] for detail in pool_details.values()
    )
    return all_records, {
        "coverage_complete": coverage_complete,
        "rpc_mode": rpc_mode,
        "recent_bounded_only": rpc_mode == "public_bounded_live",
        "finalized_block": finalized_block,
        "tick_lens_address": UNISWAP_V3_TICK_LENS_ADDRESS,
        "multicall2_address": UNISWAP_V3_MULTICALL2_ADDRESS,
        "batch_words": batch_words,
        "max_rows_per_pool": max_rows_per_pool,
        "pool_details": pool_details,
        "completed_pool_count": sum(detail["complete"] for detail in pool_details.values()),
        "initialized_tick_rows": len(all_records),
    }


async def _capture_cow_amm_preblock_quotes(
    fetcher: Fetcher,
    url: str,
    cow_executions: list[dict[str, Any]],
    *,
    record_url: str = "configured:ORCAP_ETHEREUM_RPC_URL",
    rpc_mode: str = "operator_configured",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Quote each exact CoW USDC sell against registered pools at its parent block."""
    candidates = []
    for execution in cow_executions:
        if execution.get("side") != "usdc_to_weth":
            continue
        try:
            amount_in_raw = int(execution["sell_amount_raw"])
            event_block = int(execution["event_block_number"])
        except (KeyError, TypeError, ValueError):
            continue
        if amount_in_raw <= 0 or event_block <= 0 or not execution.get("execution_id"):
            continue
        candidates.append(
            {
                "reference_execution_id": str(execution["execution_id"]),
                "reference_event_block_number": event_block,
                "state_block_number": event_block - 1,
                "amount_in_raw": amount_in_raw,
            }
        )
    tasks = [
        candidate | {"pool_id": pool_id, "spec": spec}
        for candidate in sorted(candidates, key=lambda item: item["reference_execution_id"])
        for pool_id, spec in sorted(uniswap_pool_specs().items())
        if spec["token0_address"] == USDC_ADDRESS and spec["token1_address"] == WETH_ADDRESS
    ]
    batch_size = _bounded_int_env(
        "ORCAP_COW_AMM_COUNTERFACTUAL_BATCH_SIZE",
        DEFAULT_COW_AMM_COUNTERFACTUAL_BATCH_SIZE,
        minimum=1,
        maximum=500,
    )
    # dRPC's public endpoint serves ordinary historical ``eth_call`` but
    # rejects JSON-RPC batches. Keep the bounded batch-size configuration as a
    # provenance field for an operator endpoint, while issue public calls one
    # at a time so a failed batch never becomes a false zero-counterfactual.
    records, errors = [], []
    for start in range(0, len(tasks), batch_size):
        batch = tasks[start : start + batch_size]
        for task in batch:
            result, error = await _ethereum_rpc(
                fetcher,
                url,
                "eth_call",
                [
                    {
                        "to": UNISWAP_V3_QUOTER_V2_ADDRESS,
                        "data": _uniswap_quoter_calldata(task["spec"], task["amount_in_raw"]),
                    },
                    _hex_quantity(task["state_block_number"]),
                ],
                record_url=record_url,
            )
            if error or result is None:
                errors.append(error or "eth_call returned an empty result")
            else:
                records.append(task | {"result": result})
    detail = {
        "counterfactual_state_basis": "parent_block",
        "counterfactual_rpc_mode": rpc_mode,
        "counterfactual_candidate_executions": len(candidates),
        "counterfactual_requested_quotes": len(tasks),
        "counterfactual_quote_rows": len(records),
        "counterfactual_quote_errors": len(errors),
        "counterfactual_batch_size": batch_size,
    }
    return records, detail


async def _capture_cow_rpc_logs(
    fetcher: Fetcher,
    url: str,
    *,
    record_url: str = "configured:ORCAP_ETHEREUM_RPC_URL",
    rpc_mode: str = "operator_configured",
) -> tuple[list[dict[str, Any]], dict[int, str | None], dict[str, Any]]:
    """Fetch a bounded, finalized GPv2Settlement event window."""
    latest_raw, latest_error = await _ethereum_rpc(
        fetcher, url, "eth_blockNumber", [], record_url=record_url
    )
    latest_block = _hex_int(latest_raw)
    if latest_block is None:
        return (
            [],
            {},
            {
                "rpc_configured": True,
                "rpc_mode": rpc_mode,
                "error": latest_error or "invalid latest block",
            },
        )
    finality_blocks = _bounded_int_env(
        "ORCAP_ETHEREUM_FINALITY_BLOCKS",
        DEFAULT_ETHEREUM_FINALITY_BLOCKS,
        minimum=1,
        maximum=10_000,
    )
    window_blocks = _bounded_int_env(
        "ORCAP_COW_LOG_WINDOW_BLOCKS",
        DEFAULT_COW_LOG_WINDOW_BLOCKS,
        minimum=1,
        maximum=10_000,
    )
    finalized_through = latest_block - finality_blocks
    if finalized_through < 0:
        return (
            [],
            {},
            {
                "rpc_configured": True,
                "rpc_mode": rpc_mode,
                "latest_block": latest_block,
                "finality_blocks": finality_blocks,
                "error": "chain height is below requested finality depth",
            },
        )
    from_block = max(0, finalized_through - window_blocks + 1)
    result, logs_error = await _ethereum_rpc(
        fetcher,
        url,
        "eth_getLogs",
        [
            {
                "fromBlock": _hex_quantity(from_block),
                "toBlock": _hex_quantity(finalized_through),
                "address": GPV2_SETTLEMENT_ADDRESS,
                "topics": [[GPV2_TRADE_TOPIC, GPV2_SETTLEMENT_TOPIC]],
            }
        ],
        record_url=record_url,
    )
    logs = [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []
    detail: dict[str, Any] = {
        "rpc_configured": True,
        "rpc_mode": rpc_mode,
        "recent_bounded_only": rpc_mode == "public_bounded_live",
        "latest_block": latest_block,
        "finality_blocks": finality_blocks,
        "finalized_through_block": finalized_through,
        "from_block": from_block,
        "to_block": finalized_through,
        "log_window_blocks": window_blocks,
        "log_rows": len(logs),
    }
    if logs_error:
        detail["error"] = logs_error
        return [], {}, detail
    detail["log_query_succeeded"] = True
    block_numbers = sorted(
        {block for item in logs if (block := _hex_int(item.get("blockNumber"))) is not None}
    )
    responses, errors = await _ethereum_rpc_batch(
        fetcher,
        url,
        [
            (index, "eth_getBlockByNumber", [_hex_quantity(block_number), False])
            for index, block_number in enumerate(block_numbers, start=1)
        ],
        record_url=record_url,
    )
    header_block_times = {
        block_number: _ethereum_block_time(responses.get(index))
        for index, block_number in enumerate(block_numbers, start=1)
    }
    metadata_block_times = _log_block_times(logs)
    block_times = {
        block_number: header_block_times.get(block_number) or metadata_block_times.get(block_number)
        for block_number in block_numbers
    }
    detail["block_timestamp_rows"] = sum(value is not None for value in block_times.values())
    detail["log_metadata_timestamp_rows"] = sum(
        block_number not in {key for key, value in header_block_times.items() if value is not None}
        and value is not None
        for block_number, value in block_times.items()
    )
    if errors:
        detail["block_timestamp_errors"] = len(errors)
    return logs, block_times, detail


def _run_status(
    source: str,
    rows: int,
    run_ts: str,
    dt: str,
    detail: dict[str, Any],
    curated_dir: Path,
) -> None:
    write_source_run(
        source,
        status="success" if rows else "degraded",
        rows=rows,
        run_ts=run_ts,
        dt=dt,
        detail=detail,
        curated_dir=curated_dir,
    )


async def capture_markets(
    *,
    with_uniswap: bool = False,
    with_akash: bool = False,
    with_akash_open_book: bool = False,
    with_akash_provider_aggregates: bool = False,
    with_nosana: bool = False,
    with_aethir: bool = False,
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    run_ts, dt = run_timestamp(), dt_partition()
    if with_akash_provider_aggregates and not with_akash:
        raise ValueError("with_akash_provider_aggregates requires with_akash")
    if with_akash_open_book and not with_akash:
        raise ValueError("with_akash_open_book requires with_akash")
    async with make_client() as client:
        fetcher = Fetcher(client, rps=1.0)
        ethereum_rpc_url, ethereum_rpc_record_url, ethereum_rpc_mode = _ethereum_rpc_config()
        cow_url = os.environ.get("ORCAP_COW_TRADES_URL")
        cow_competition_url = _configured_url(
            "ORCAP_COW_SOLVER_COMPETITION_URL", COW_SOLVER_COMPETITION_LATEST_URL
        )
        defillama, golem, cow_competition = await asyncio.gather(
            fetcher.get_json(DEFILLAMA_PROTOCOLS_URL),
            fetcher.get_json(_configured_url("ORCAP_GOLEM_STATS_URL", GOLEM_ONLINE_URL)),
            fetcher.get_json(cow_competition_url),
        )
        chutes_models = await fetcher.get_json(CHUTES_MODELS_URL)
        chute_ids = [
            str(model["chute_id"])
            for model in _as_list(chutes_models, "data")
            if model.get("chute_id")
        ]
        chutes_details = await asyncio.gather(
            *(
                fetcher.get_json(CHUTES_DETAIL_URL.format(chute_id=chute_id))
                for chute_id in chute_ids
            )
        )
        geckoterminal_bodies = await asyncio.gather(
            *(
                fetcher.get_json(GECKOTERMINAL_POOL_URL.format(pool_id=pool))
                for pool in GECKOTERMINAL_POOLS
            )
        )
        cow = await fetcher.get_json(cow_url) if cow_url else None
        cow_rpc_logs: list[dict[str, Any]] = []
        cow_block_times: dict[int, str | None] = {}
        cow_rpc_executions: list[dict[str, Any]] = []
        cow_rpc_events: list[dict[str, Any]] = []
        cow_amm_counterfactual_records: list[dict[str, Any]] = []
        cow_amm_counterfactual_detail: dict[str, Any] = {
            "counterfactual_state_basis": "not_collected",
            "counterfactual_candidate_executions": 0,
            "counterfactual_requested_quotes": 0,
            "counterfactual_quote_rows": 0,
        }
        cow_rpc_detail: dict[str, Any] = {
            "rpc_configured": True,
            "rpc_mode": ethereum_rpc_mode,
        }

        uniswap = None
        uniswap_rpc_logs: list[dict[str, Any]] = []
        uniswap_block_times: dict[int, str | None] = {}
        uniswap_quoter_records: list[dict[str, Any]] = []
        uniswap_quoter_detail: dict[str, Any] = {}
        uniswap_tick_records: list[dict[str, Any]] = []
        uniswap_tick_detail: dict[str, Any] = {"coverage_complete": False}
        uniswap_rpc_detail: dict[str, Any] = {
            "rpc_configured": True,
            "rpc_mode": ethereum_rpc_mode,
        }
        graph_key, subgraph_id = (
            os.environ.get("GRAPH_API_KEY"),
            os.environ.get("ORCAP_UNISWAP_SUBGRAPH_ID"),
        )
        pool_ids = [
            item.strip().lower()
            for item in os.environ.get("ORCAP_UNISWAP_POOLS", "").split(",")
            if item.strip()
        ]
        if with_uniswap and graph_key and subgraph_id and pool_ids:
            query = {
                "query": """
                  query Pools($poolIds: [String!]) {
                    pools(where: {id_in: $poolIds}) {
                      id token0 { id symbol decimals } token1 { id symbol decimals }
                      token1Price totalValueLockedUSD liquidity
                    }
                    swaps(first: 100, orderBy: timestamp, orderDirection: desc,
                          where: {pool_in: $poolIds}) {
                      id timestamp amount0 amount1 amountUSD origin pool { id }
                    }
                  }
                """,
                "variables": {"poolIds": pool_ids},
            }
            uniswap = await fetcher.post_json(
                GRAPH_GATEWAY.format(key=graph_key, subgraph_id=subgraph_id),
                query,
                record_url=(
                    "https://gateway.thegraph.com/api/[redacted]/subgraphs/id/" + subgraph_id
                ),
            )
        if with_uniswap:
            (
                uniswap_rpc_logs,
                uniswap_block_times,
                uniswap_rpc_detail,
            ) = await _capture_uniswap_rpc_logs(
                fetcher,
                ethereum_rpc_url,
                record_url=ethereum_rpc_record_url,
                rpc_mode=ethereum_rpc_mode,
            )
            uniswap_quoter_records, uniswap_quoter_detail = await _capture_uniswap_quoter_quotes(
                fetcher,
                ethereum_rpc_url,
                uniswap_rpc_detail.get("finalized_through_block"),
                record_url=ethereum_rpc_record_url,
                rpc_mode=ethereum_rpc_mode,
            )
            uniswap_tick_records, uniswap_tick_detail = await _capture_uniswap_tick_book(
                fetcher,
                ethereum_rpc_url,
                uniswap_rpc_detail.get("finalized_through_block"),
                record_url=ethereum_rpc_record_url,
                rpc_mode=ethereum_rpc_mode,
            )
        cow_rpc_logs, cow_block_times, cow_rpc_detail = await _capture_cow_rpc_logs(
            fetcher,
            ethereum_rpc_url,
            record_url=ethereum_rpc_record_url,
            rpc_mode=ethereum_rpc_mode,
        )
        cow_rpc_executions, cow_rpc_events = cow_rpc_log_rows(
            cow_rpc_logs, cow_block_times, run_ts, dt
        )
        if with_uniswap and cow_rpc_detail.get("log_query_succeeded") is True:
            (
                cow_amm_counterfactual_records,
                cow_amm_counterfactual_detail,
            ) = await _capture_cow_amm_preblock_quotes(
                fetcher,
                ethereum_rpc_url,
                cow_rpc_executions,
                record_url=ethereum_rpc_record_url,
                rpc_mode=ethereum_rpc_mode,
            )

        akash = None
        akash_gpu_prices = None
        akash_leases = None
        akash_dashboard_body = None
        akash_network_capacity_body = None
        akash_provider_aggregate_payloads: list[dict[str, Any]] = []
        akash_provider_aggregate_detail: dict[str, Any] = {
            "coverage_complete": False,
            "reason": "flag_not_set",
        }
        akash_open_bids: list[dict[str, Any]] = []
        akash_choice_payloads: list[dict[str, Any]] = []
        akash_bid_event_pages: list[dict[str, Any]] = []
        akash_close_event_payloads: list[dict[str, Any]] = []
        akash_market_detail: dict[str, Any] = {
            "coverage_complete": False,
            "reason": "flag_not_set",
            "snapshot_height": None,
            "snapshot_time": None,
        }
        akash_choice_detail: dict[str, Any] = {
            "coverage_complete": False,
            "reason": "flag_not_set",
            "snapshot_height": None,
            "snapshot_time": None,
        }
        akash_bid_event_detail: dict[str, Any] = {
            "coverage_complete": False,
            "reason": "flag_not_set",
        }
        akash_close_event_detail: dict[str, Any] = {
            "coverage_complete": False,
            "reason": "flag_not_set",
        }
        akash_block_times: dict[int, str | None] = {}
        akash_url = _configured_url("ORCAP_AKASH_NETWORK_URL", AKASH_CONSOLE_PROVIDERS_URL)
        if with_akash:
            headers = (
                {"x-api-key": os.environ["AKASH_API_KEY"]}
                if os.environ.get("AKASH_API_KEY")
                else None
            )
            akash = await fetcher.get_json(akash_url, headers=headers)
            akash_gpu_prices = await fetcher.get_json(
                _configured_url("ORCAP_AKASH_GPU_PRICES_URL", AKASH_GPU_PRICES_URL)
            )
            akash_leases = await fetcher.get_json(
                _configured_url("ORCAP_AKASH_LEASES_URL", AKASH_LEASES_URL)
            )
            akash_dashboard_body, akash_network_capacity_body = await asyncio.gather(
                fetcher.get_json(_configured_url("ORCAP_AKASH_DASHBOARD_URL", AKASH_DASHBOARD_URL)),
                fetcher.get_json(
                    _configured_url("ORCAP_AKASH_NETWORK_CAPACITY_URL", AKASH_NETWORK_CAPACITY_URL)
                ),
            )
            live_gpu_providers = akash_live_gpu_provider_ids(akash)
            if with_akash_open_book:
                akash_open_bids, akash_market_detail = await capture_akash_open_market(
                    fetcher, live_gpu_providers
                )
            else:
                akash_market_detail = {
                    "coverage_complete": False,
                    "reason": "provider_wide_diagnostic_not_requested",
                    "snapshot_height": None,
                    "snapshot_time": None,
                    "provider_count": len(live_gpu_providers),
                }
            if with_akash_provider_aggregates:
                history_days = _bounded_int_env(
                    "ORCAP_AKASH_PROVIDER_HISTORY_DAYS",
                    DEFAULT_AKASH_PROVIDER_HISTORY_DAYS,
                    minimum=1,
                    maximum=30,
                )
                (
                    akash_provider_aggregate_payloads,
                    akash_provider_aggregate_detail,
                ) = await capture_akash_provider_aggregates(fetcher, live_gpu_providers)
                akash_provider_aggregate_detail["history_days"] = history_days
            lease_records = _as_list(akash_leases, "leases", "data")
            akash_choice_payloads, akash_choice_detail = await capture_akash_lease_choice_sets(
                fetcher, lease_records
            )
            choice_snapshot_height = _integer(akash_choice_detail.get("snapshot_height"))
            if choice_snapshot_height is not None:
                akash_bid_event_pages, akash_bid_event_detail = await capture_akash_bid_events(
                    fetcher, choice_snapshot_height
                )
                (
                    akash_close_event_payloads,
                    akash_close_event_detail,
                ) = await capture_akash_lease_close_events(
                    fetcher, lease_records, choice_snapshot_height
                )
                akash_close_event_detail["raw_payload_source"] = "market_sources"
            heights = sorted(
                {
                    block
                    for item in lease_records
                    if isinstance(item, dict)
                    for block in [_lease_block(item.get("lease") or item)]
                    if block is not None
                }
            )
            rpc_url = _configured_url("ORCAP_AKASH_RPC_URL", AKASH_RPC_URL).rstrip("/")
            block_bodies = await asyncio.gather(
                *(fetcher.get_json(f"{rpc_url}/header?height={height}") for height in heights)
            )
            akash_block_times = {
                height: _block_time(body)
                for height, body in zip(heights, block_bodies, strict=True)
            }
        nosana_body = None
        nosana_detail: dict[str, Any] = {"query_succeeded": False, "reason": "flag_not_set"}
        nosana_jobs_body: dict[str, Any] | None = None
        nosana_jobs_detail: dict[str, Any] = {
            "query_succeeded": False,
            "reason": "flag_not_set",
        }
        if with_nosana:
            nosana_body, nosana_detail = await capture_nosana_node_registry(fetcher)
            nosana_jobs_body, nosana_jobs_detail = await capture_nosana_job_activity(fetcher)
        aethir_body: dict[str, Any] | None = None
        aethir_detail: dict[str, Any] = {"query_succeeded": False, "reason": "flag_not_set"}
        if with_aethir:
            aethir_body, aethir_detail = await capture_aethir_dashboard(fetcher)
        write_raw(fetcher.records, "market_sources", raw_dir, run_ts, dt)

    participants = defillama_participant_rows(defillama, run_ts, dt)
    geckoterminal_quotes = geckoterminal_quote_rows(
        dict(zip(GECKOTERMINAL_POOLS, geckoterminal_bodies, strict=True)), run_ts, dt
    )
    configured_cow_executions = cow_execution_rows(cow, run_ts, dt)
    cow_executions = (
        cow_rpc_executions if cow_rpc_detail["rpc_configured"] else configured_cow_executions
    )
    cow_rpc_participants = cow_rpc_participant_rows(cow_rpc_executions)
    cow_participants, cow_competition_events = cow_competition_rows(cow_competition, run_ts, dt)
    golem_capacity = golem_capacity_rows(golem, run_ts, dt)
    chutes_capacity = chutes_capacity_rows(chutes_models, chutes_details, run_ts, dt)
    graph_uni_quotes, graph_uni_executions, graph_uni_events = uniswap_rows(uniswap, run_ts, dt)
    quoter_uni_quotes = uniswap_quoter_quote_rows(uniswap_quoter_records, run_ts, dt)
    quoter_uni_impact_capacity = uniswap_quoter_impact_capacity_rows(
        uniswap_quoter_records, run_ts, dt
    )
    uni_tick_book = uniswap_tick_book_rows(uniswap_tick_records, run_ts, dt)
    cow_amm_counterfactual_quotes = cow_amm_preblock_quote_rows(
        cow_amm_counterfactual_records, run_ts, dt
    )
    uni_quotes = graph_uni_quotes + quoter_uni_quotes + quoter_uni_impact_capacity
    rpc_uni_executions, rpc_uni_events = uniswap_rpc_log_rows(
        uniswap_rpc_logs, uniswap_block_times, run_ts, dt
    )
    # Graph swaps are useful indexed observations, but never substitutes for
    # the configured finalized log path. Prefer the latter whenever it was
    # explicitly enabled, including when its bounded window legitimately has
    # no rows.
    uni_executions = (
        rpc_uni_executions if uniswap_rpc_detail["rpc_configured"] else graph_uni_executions
    )
    uni_events = rpc_uni_events if uniswap_rpc_detail["rpc_configured"] else graph_uni_events
    akash_capacity = akash_capacity_rows(akash, run_ts, dt)
    akash_coverage = akash_registry_summary(akash)
    akash_quotes = akash_gpu_quote_rows(akash_gpu_prices, run_ts, dt)
    akash_leases_rows = akash_lease_execution_rows(
        akash_leases,
        akash_block_times,
        run_ts,
        dt,
        snapshot_height=akash_choice_detail.get("snapshot_height"),
        snapshot_time=akash_choice_detail.get("snapshot_time"),
    )
    akash_close_events = akash_lease_close_event_rows(
        akash_close_event_payloads,
        akash_close_event_detail,
        run_ts,
        dt,
    )
    expected_recent_closes = int(
        akash_close_event_detail.get("expected_recent_closed_leases") or 0
    )
    akash_close_event_detail["close_event_rows"] = len(akash_close_events)
    akash_close_event_detail["exact_event_match_rate"] = (
        len(akash_close_events) / expected_recent_closes if expected_recent_closes else 1.0
    )
    akash_dashboard = akash_dashboard_rows(
        akash_dashboard_body, akash_network_capacity_body, run_ts, dt
    )
    akash_provider_aggregates = akash_provider_aggregate_rows(
        akash_provider_aggregate_payloads,
        run_ts,
        dt,
        history_days=int(
            akash_provider_aggregate_detail.get("history_days", DEFAULT_AKASH_PROVIDER_HISTORY_DAYS)
        ),
    )
    akash_open_bid_book = akash_open_bid_rows(akash_open_bids, akash_market_detail, run_ts, dt)
    akash_choice_bids = akash_lease_choice_bid_rows(
        akash_choice_payloads, akash_choice_detail, run_ts, dt
    )
    selected_lease_bid_ids = {
        lease_id
        for item in _as_list(akash_leases, "leases", "data")
        if isinstance(item, dict)
        for lease in [item.get("lease") if isinstance(item.get("lease"), dict) else item]
        for lease_id in [_lease_id(lease)]
        if lease_id is not None
    }
    gpu_choice_order_ids = {row["order_id"] for row in akash_choice_bids}
    akash_bid_events = akash_bid_event_rows(
        akash_bid_event_pages,
        akash_bid_event_detail,
        selected_lease_bid_ids,
        gpu_choice_order_ids,
        run_ts,
        dt,
    )
    nosana_nodes = nosana_node_registry_rows(nosana_body, run_ts, dt)
    nosana_job_activity = nosana_job_activity_rows(nosana_jobs_body, run_ts, dt)
    aethir_dashboard = (
        aethir_dashboard_rows(aethir_body, run_ts, dt)
        if aethir_detail.get("query_succeeded") is True
        else []
    )
    instrument_map = instrument_map_rows(run_ts, dt)
    _write(
        participants + cow_participants + cow_rpc_participants,
        "market_participants",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        cow_amm_counterfactual_quotes,
        "market_counterfactual_quotes",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        cow_executions + uni_executions + akash_leases_rows,
        "market_executions",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        uni_quotes + akash_quotes + geckoterminal_quotes,
        "market_quotes",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        uni_tick_book,
        "uniswap_tick_book",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        golem_capacity + akash_capacity + chutes_capacity,
        "market_capacity",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        akash_dashboard,
        "akash_dashboard",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        akash_provider_aggregates,
        "akash_provider_aggregates",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        akash_open_bid_book,
        "akash_market_open_bids",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        akash_choice_bids,
        "akash_market_choice_bids",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        akash_bid_events,
        "akash_market_bid_events",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        akash_close_events,
        "akash_market_lease_close_events",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        nosana_nodes,
        "nosana_node_registry",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        nosana_job_activity,
        "nosana_job_activity",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        aethir_dashboard,
        "aethir_dashboard",
        run_ts,
        dt,
        curated_dir,
    )
    _write(
        (
            cow_rpc_events
            if cow_rpc_detail["rpc_configured"]
            else execution_events(cow_executions, "trade")
        )
        + cow_competition_events
        + execution_events(akash_leases_rows, "lease_lifecycle")
        + uni_events,
        "market_events",
        run_ts,
        dt,
        curated_dir,
    )
    _write(instrument_map, "instrument_map", run_ts, dt, curated_dir)

    _run_status(
        "defillama",
        len(participants),
        run_ts,
        dt,
        {"url": DEFILLAMA_PROTOCOLS_URL},
        curated_dir,
    )
    _run_status(
        "cow",
        len(cow_executions) + len(cow_participants) + len(cow_competition_events),
        run_ts,
        dt,
        {
            "competition_url": cow_competition_url,
            "competition_auction_id": (
                cow_competition.get("auctionId") if isinstance(cow_competition, dict) else None
            ),
            "competition_snapshot_rows": len(cow_participants) + len(cow_competition_events),
            "trade_feed_configured": bool(cow_url),
            "trade_feed_rows": len(configured_cow_executions),
            "finalized_trade_rows": len(cow_rpc_executions),
            "finalized_solver_identified_trade_rows": len(cow_rpc_participants),
            **cow_rpc_detail,
            **cow_amm_counterfactual_detail,
        },
        curated_dir,
    )
    _run_status(
        "chutes",
        len(chutes_capacity),
        run_ts,
        dt,
        {
            "models_url": CHUTES_MODELS_URL,
            "catalog_models": len(chute_ids),
            "detail_responses": sum(isinstance(body, dict) for body in chutes_details),
            "active_instances": sum(row["active_instances"] for row in chutes_capacity),
            "active_configured_gpus": sum(
                row["total"] for row in chutes_capacity if row["total"] is not None
            ),
            "metric_boundary": (
                "active deployment configuration proxy; not availability or utilization"
            ),
        },
        curated_dir,
    )
    _run_status(
        "golem",
        len(golem_capacity),
        run_ts,
        dt,
        {"url": _configured_url("ORCAP_GOLEM_STATS_URL", GOLEM_ONLINE_URL)},
        curated_dir,
    )
    _run_status(
        "geckoterminal",
        len(geckoterminal_quotes),
        run_ts,
        dt,
        {"network": "eth", "pools": list(GECKOTERMINAL_POOLS)},
        curated_dir,
    )
    if with_uniswap:
        _run_status(
            "uniswap",
            len(uni_quotes) + len(uni_executions),
            run_ts,
            dt,
            {
                "graph_configured": bool(graph_key and subgraph_id and pool_ids),
                "graph_quote_rows": len(graph_uni_quotes),
                "graph_execution_rows_ignored_for_finalized_path": (
                    len(graph_uni_executions) if uniswap_rpc_detail["rpc_configured"] else 0
                ),
                "finalized_execution_rows": len(rpc_uni_executions),
                "finalized_impact_capacity_rows": len(quoter_uni_impact_capacity),
                "finalized_tick_book_rows": len(uni_tick_book),
                "finalized_tick_book_coverage_complete": uniswap_tick_detail.get(
                    "coverage_complete"
                ),
                "finalized_liquidity_event_rows": sum(
                    event["event_type"] in {"liquidity_mint", "liquidity_burn"}
                    for event in rpc_uni_events
                ),
                **uniswap_rpc_detail,
                **uniswap_quoter_detail,
            },
            curated_dir,
        )
        write_source_run(
            "uniswap_tick_book",
            status="success" if uniswap_tick_detail.get("coverage_complete") else "degraded",
            rows=len(uni_tick_book),
            run_ts=run_ts,
            dt=dt,
            detail={
                "resource_scope": (
                    "initialized virtual-liquidity ticks for the registered pools only; not "
                    "USD depth, all-market liquidity, or a fill census"
                ),
                **uniswap_tick_detail,
            },
            curated_dir=curated_dir,
        )
    else:
        write_source_run(
            "uniswap",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
        write_source_run(
            "uniswap_tick_book",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
    if with_akash:
        _run_status(
            "akash",
            len(akash_capacity)
            + len(akash_quotes)
            + len(akash_leases_rows)
            + len(akash_open_bid_book),
            run_ts,
            dt,
            {
                "configured": bool(akash_url),
                "gpu_quote_rows": len(akash_quotes),
                "lease_lifecycle_rows": len(akash_leases_rows),
                "lease_blocks_timestamped": sum(
                    row["executed_at"] is not None for row in akash_leases_rows
                ),
                "open_gpu_bid_rows": len(akash_open_bid_book),
                "market_book": akash_market_detail,
                **akash_coverage,
            },
            curated_dir,
        )
        dashboard_now = (
            akash_dashboard_body.get("now") if isinstance(akash_dashboard_body, dict) else None
        )
        _run_status(
            "akash_dashboard",
            len(akash_dashboard),
            run_ts,
            dt,
            {
                "dashboard_url": _configured_url("ORCAP_AKASH_DASHBOARD_URL", AKASH_DASHBOARD_URL),
                "network_capacity_url": _configured_url(
                    "ORCAP_AKASH_NETWORK_CAPACITY_URL", AKASH_NETWORK_CAPACITY_URL
                ),
                "dashboard_now_timestamp": (
                    dashboard_now.get("date") if isinstance(dashboard_now, dict) else None
                ),
                "dashboard_now_height": (
                    dashboard_now.get("height") if isinstance(dashboard_now, dict) else None
                ),
                "metric_boundary": (
                    "public aggregate lease, resource, and spend fields; not workload delivery, "
                    "GPU-hour price, provider revenue, utilization, or welfare"
                ),
            },
            curated_dir,
        )
        if with_akash_provider_aggregates:
            provider_aggregate_complete = (
                akash_provider_aggregate_detail.get("coverage_complete") is True
                and len(akash_provider_aggregates) > 0
            )
            write_source_run(
                "akash_provider_aggregates",
                status="success" if provider_aggregate_complete else "degraded",
                rows=len(akash_provider_aggregates),
                run_ts=run_ts,
                dt=dt,
                detail={
                    "active_leases_graph_url": AKASH_PROVIDER_ACTIVE_LEASES_GRAPH_URL,
                    "provider_dashboard_url": AKASH_PROVIDER_DASHBOARD_URL,
                    "rows_written": {"akash_provider_aggregates": len(akash_provider_aggregates)},
                    "metric_boundary": (
                        "public provider aggregate lease history and cards for the current "
                        "live-GPU universe only; not tenant/workload activity, GPU-hours, "
                        "utilization, price, delivery, audited revenue, profit, or welfare"
                    ),
                    **akash_provider_aggregate_detail,
                },
                curated_dir=curated_dir,
            )
        market_rows = int(akash_market_detail.get("bid_records_fetched") or 0)
        write_source_run(
            "akash_market_book",
            status=(
                "success"
                if akash_market_detail.get("coverage_complete")
                else "degraded"
                if with_akash_open_book
                else "skipped"
            ),
            rows=market_rows,
            run_ts=run_ts,
            dt=dt,
            detail={
                "url": AKASH_MARKET_API_URL,
                "query_state": "open",
                "resource_scope": "GPU-bearing resources only in curated book tables",
                "rows_written": {
                    "open_gpu_bids": len(akash_open_bid_book),
                },
                **akash_market_detail,
            },
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_choice_sets",
            status=(
                "success"
                if akash_choice_detail.get("coverage_complete") and len(akash_choice_bids) > 0
                else "degraded"
            ),
            rows=len(akash_choice_bids),
            watermark=str(akash_choice_detail.get("snapshot_height") or run_ts),
            run_ts=run_ts,
            dt=dt,
            detail={
                "url": AKASH_MARKET_API_URL,
                "query_scope": "all bid states retained for recent public lease orders",
                "gpu_choice_bid_rows": len(akash_choice_bids),
                "selected_gpu_bid_rows": sum(
                    bool(row["selected_contract"]) for row in akash_choice_bids
                ),
                "metric_boundary": (
                    "post-selection public chain state for recent lease orders; already-pruned "
                    "bids, workload delivery, LLM routing, cost, and welfare are not observed"
                ),
                **akash_choice_detail,
            },
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_bid_events",
            status=(
                "success"
                if akash_bid_event_detail.get("coverage_complete")
                and len(akash_bid_events) > 0
                else "degraded"
            ),
            rows=len(akash_bid_events),
            watermark=str(akash_bid_event_detail.get("end_height_inclusive") or run_ts),
            run_ts=run_ts,
            dt=dt,
            detail={
                "url": f"{AKASH_RPC_URL}/tx_search",
                "gpu_order_count": len(gpu_choice_order_ids),
                "bid_event_rows": len(akash_bid_events),
                "selected_bid_event_rows": sum(
                    bool(row["selected_contract"]) for row in akash_bid_events
                ),
                "metric_boundary": (
                    "complete bounded indexed bid-create event window for recent public GPU "
                    "lease orders; not workload delivery, utilization, user routing, cost, "
                    "profit, or welfare"
                ),
                **akash_bid_event_detail,
            },
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_lease_close_events",
            status=(
                "success"
                if akash_close_event_detail.get("coverage_complete")
                and akash_close_event_detail.get("exact_event_match_rate") == 1.0
                else "degraded"
            ),
            rows=len(akash_close_events),
            watermark=str(akash_close_event_detail.get("end_height_inclusive") or run_ts),
            run_ts=run_ts,
            dt=dt,
            detail={
                "url": f"{AKASH_RPC_URL}/block_results",
                "metric_boundary": (
                    "exact public lease-close reason for source-returned recent leases; actor "
                    "class identifies the on-chain termination path, not workload delivery, "
                    "failure, default, or intent"
                ),
                **akash_close_event_detail,
            },
            curated_dir=curated_dir,
        )

    else:
        write_source_run(
            "akash",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_market_book",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_choice_sets",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_bid_events",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_lease_close_events",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
        write_source_run(
            "akash_dashboard",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )

    if with_nosana:
        expected_nosana_accounts = nosana_detail.get("account_records_fetched")
        registry_complete = (
            nosana_detail.get("query_succeeded") is True
            and isinstance(expected_nosana_accounts, int)
            and expected_nosana_accounts > 0
            and len(nosana_nodes) == expected_nosana_accounts
        )
        write_source_run(
            "nosana",
            status="success" if registry_complete else "degraded",
            rows=len(nosana_nodes),
            run_ts=run_ts,
            dt=dt,
            detail={
                "rows_written": {"nosana_node_registry": len(nosana_nodes)},
                "registry_complete": registry_complete,
                **nosana_detail,
            },
            curated_dir=curated_dir,
        )
        jobs_complete = (
            nosana_jobs_detail.get("query_succeeded") is True and len(nosana_job_activity) > 0
        )
        write_source_run(
            "nosana_jobs_api",
            status="success" if jobs_complete else "degraded",
            rows=len(nosana_job_activity),
            run_ts=run_ts,
            dt=dt,
            detail={
                "rows_written": {"nosana_job_activity": len(nosana_job_activity)},
                "aggregate_response_complete": jobs_complete,
                **nosana_jobs_detail,
            },
            curated_dir=curated_dir,
        )
    else:
        write_source_run(
            "nosana",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )
        write_source_run(
            "nosana_jobs_api",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )

    if with_aethir:
        dashboard_complete = (
            aethir_detail.get("query_succeeded") is True and len(aethir_dashboard) > 0
        )
        write_source_run(
            "aethir_dashboard",
            status="success" if dashboard_complete else "degraded",
            rows=len(aethir_dashboard),
            run_ts=run_ts,
            dt=dt,
            detail={
                "rows_written": {"aethir_dashboard": len(aethir_dashboard)},
                "aggregate_response_complete": dashboard_complete,
                **aethir_detail,
            },
            curated_dir=curated_dir,
        )
    else:
        write_source_run(
            "aethir_dashboard",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "flag not set"},
            curated_dir=curated_dir,
        )

    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "defillama_participants": len(participants),
        "cow_executions": len(cow_executions),
        "cow_finalized_executions": len(cow_rpc_executions),
        "cow_finalized_solver_identified_executions": len(cow_rpc_participants),
        "cow_amm_preblock_counterfactual_quotes": len(cow_amm_counterfactual_quotes),
        "cow_competition_participants": len(cow_participants),
        "cow_competition_events": len(cow_competition_events),
        "golem_capacity": len(golem_capacity),
        "chutes_capacity": len(chutes_capacity),
        "geckoterminal_quotes": len(geckoterminal_quotes),
        "uniswap_quotes": len(uni_quotes),
        "uniswap_finalized_quote_curve_points": len(quoter_uni_quotes),
        "uniswap_finalized_impact_capacity_points": len(quoter_uni_impact_capacity),
        "uniswap_finalized_tick_book_rows": len(uni_tick_book),
        "uniswap_tick_book_coverage_complete": uniswap_tick_detail.get("coverage_complete"),
        "uniswap_executions": len(uni_executions),
        "uniswap_finalized_executions": len(rpc_uni_executions),
        "uniswap_finalized_liquidity_events": sum(
            event["event_type"] in {"liquidity_mint", "liquidity_burn"} for event in rpc_uni_events
        ),
        "akash_capacity": len(akash_capacity),
        "akash_gpu_quotes": len(akash_quotes),
        "akash_coverage": akash_coverage,
        "akash_lease_lifecycle_rows": len(akash_leases_rows),
        "akash_dashboard_rows": len(akash_dashboard),
        "akash_provider_aggregate_rows": len(akash_provider_aggregates),
        "akash_provider_aggregates": akash_provider_aggregate_detail,
        "akash_open_gpu_bid_rows": len(akash_open_bid_book),
        "akash_market_book": akash_market_detail,
        "akash_choice_bid_rows": len(akash_choice_bids),
        "akash_choice_sets": akash_choice_detail,
        "akash_bid_event_rows": len(akash_bid_events),
        "akash_bid_events": akash_bid_event_detail,
        "akash_lease_close_event_rows": len(akash_close_events),
        "akash_lease_close_events": akash_close_event_detail,
        "nosana_node_registry_rows": len(nosana_nodes),
        "nosana_node_registry": nosana_detail,
        "nosana_job_activity_rows": len(nosana_job_activity),
        "nosana_job_activity": nosana_jobs_detail,
        "aethir_dashboard_rows": len(aethir_dashboard),
        "aethir_dashboard": aethir_detail,
    }
    log.info("market-source capture complete: %s", summary)
    return summary


def main(
    with_uniswap: bool = False,
    with_akash: bool = False,
    with_akash_open_book: bool = False,
    with_akash_provider_aggregates: bool = False,
    with_nosana: bool = False,
    with_aethir: bool = False,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(
        capture_markets(
            with_uniswap=with_uniswap,
            with_akash=with_akash,
            with_akash_open_book=with_akash_open_book,
            with_akash_provider_aggregates=with_akash_provider_aggregates,
            with_nosana=with_nosana,
            with_aethir=with_aethir,
        )
    )
    print(json.dumps(result, indent=2))
    return result
