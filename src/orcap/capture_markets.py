"""Capture the source-backed DeFi and decentralized-compute comparison layer.

Public sources are collected immediately; source-specific credentials only
unlock the canonical Uniswap Graph query and an operator-selected Akash
network-data endpoint.  Missing credentials are written as ``skipped`` source
runs, never mistaken for a quiet market.
"""

import asyncio
import json
import logging
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
AKASH_RPC_URL = "https://rpc.akashnet.net:443"
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
GPV2_SETTLEMENT_ADDRESS = "0x9008d19f58aabd9ed0d60971565aa8510560ab41"
GPV2_TRADE_TOPIC = "0xa07a543ab8a018198e99ca0184c93fe9050a79400a0a723441f84de1d972cc17"
GPV2_SETTLEMENT_TOPIC = "0x40338ce1a7c49204f0099533b1e9a7ee0a3d261f84974ab7af36105b8c4e9db4"
PUBLIC_ETHEREUM_RPC_URL = "https://eth.drpc.org"
USDC_ADDRESS = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
UNISWAP_V3_QUOTER_V2_ADDRESS = "0x61ffe014ba17989e743c5f6cb21bf9697530b21e"
UNISWAP_V3_QUOTE_EXACT_INPUT_SINGLE_SELECTOR = "c6a5026a"
UNISWAP_USDC_QUOTE_BUCKETS = (100, 1_000, 10_000, 100_000)


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
        result[block_number] = datetime.fromtimestamp(timestamp, UTC).isoformat().replace(
            "+00:00", "Z"
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
            detail.get("node_selector")
            if isinstance(detail.get("node_selector"), dict)
            else {}
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
    return "0x" + UNISWAP_V3_QUOTE_EXACT_INPUT_SINGLE_SELECTOR + "".join(
        (
            _abi_address(spec["token0_address"]),
            _abi_address(spec["token1_address"]),
            _abi_uint(amount_in_raw),
            _abi_uint(int(spec["fee"]), bits=24),
            _abi_uint(0, bits=160),
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
            amount0_raw, amount1_raw = _signed_word(log_row.get("data"), 0), _signed_word(
                log_row.get("data"), 1
            )
            sqrt_price_x96 = _word(log_row.get("data"), 2)
            liquidity_after = _word(log_row.get("data"), 3)
            tick = _signed_word(log_row.get("data"), 4)
            if amount0_raw is None or amount1_raw is None or not (
                (amount0_raw > 0 and amount1_raw < 0) or (amount1_raw > 0 and amount0_raw < 0)
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
        sell_token, buy_token = _address_word(log_row.get("data"), 0), _address_word(
            log_row.get("data"), 1
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
        normalized = _cow_usdc_weth_execution_fields(
            sell_token, buy_token, sell_amount, buy_amount
        )
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
            event_base
            | {"event_type": "trade", "solver_id": solver, "record_json": record_json}
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
        available = _first_number(
            gpu.get("available"), item.get("available"), item.get("capacity")
        )
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
    body: Any, block_times: dict[int, str | None], run_ts: str, dt: str
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
        return [], {}, {
            "rpc_configured": True,
            "rpc_mode": rpc_mode,
            "error": latest_error or "invalid latest block",
        }
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
        return [], {}, {
            "rpc_configured": True,
            "rpc_mode": rpc_mode,
            "latest_block": latest_block,
            "finality_blocks": finality_blocks,
            "error": "chain height is below requested finality depth",
        }
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
        block_number not in {
            key for key, value in header_block_times.items() if value is not None
        }
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
        return [], {}, {
            "rpc_configured": True,
            "rpc_mode": rpc_mode,
            "error": latest_error or "invalid latest block",
        }
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
        return [], {}, {
            "rpc_configured": True,
            "rpc_mode": rpc_mode,
            "latest_block": latest_block,
            "finality_blocks": finality_blocks,
            "error": "chain height is below requested finality depth",
        }
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
        block_number not in {
            key for key, value in header_block_times.items() if value is not None
        }
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
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    run_ts, dt = run_timestamp(), dt_partition()
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
        cow_rpc_detail: dict[str, Any] = {
            "rpc_configured": True,
            "rpc_mode": ethereum_rpc_mode,
        }

        uniswap = None
        uniswap_rpc_logs: list[dict[str, Any]] = []
        uniswap_block_times: dict[int, str | None] = {}
        uniswap_quoter_records: list[dict[str, Any]] = []
        uniswap_quoter_detail: dict[str, Any] = {}
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
            uniswap_rpc_logs, uniswap_block_times, uniswap_rpc_detail = (
                await _capture_uniswap_rpc_logs(
                    fetcher,
                    ethereum_rpc_url,
                    record_url=ethereum_rpc_record_url,
                    rpc_mode=ethereum_rpc_mode,
                )
            )
            uniswap_quoter_records, uniswap_quoter_detail = await _capture_uniswap_quoter_quotes(
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

        akash = None
        akash_gpu_prices = None
        akash_leases = None
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
            lease_records = _as_list(akash_leases, "leases", "data")
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
        write_raw(fetcher.records, "market_sources", raw_dir, run_ts, dt)

    participants = defillama_participant_rows(defillama, run_ts, dt)
    geckoterminal_quotes = geckoterminal_quote_rows(
        dict(zip(GECKOTERMINAL_POOLS, geckoterminal_bodies, strict=True)), run_ts, dt
    )
    configured_cow_executions = cow_execution_rows(cow, run_ts, dt)
    cow_rpc_executions, cow_rpc_events = cow_rpc_log_rows(
        cow_rpc_logs, cow_block_times, run_ts, dt
    )
    cow_executions = (
        cow_rpc_executions if cow_rpc_detail["rpc_configured"] else configured_cow_executions
    )
    cow_rpc_participants = cow_rpc_participant_rows(cow_rpc_executions)
    cow_participants, cow_competition_events = cow_competition_rows(
        cow_competition, run_ts, dt
    )
    golem_capacity = golem_capacity_rows(golem, run_ts, dt)
    chutes_capacity = chutes_capacity_rows(chutes_models, chutes_details, run_ts, dt)
    graph_uni_quotes, graph_uni_executions, graph_uni_events = uniswap_rows(
        uniswap, run_ts, dt
    )
    quoter_uni_quotes = uniswap_quoter_quote_rows(uniswap_quoter_records, run_ts, dt)
    uni_quotes = graph_uni_quotes + quoter_uni_quotes
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
    akash_leases_rows = akash_lease_execution_rows(akash_leases, akash_block_times, run_ts, dt)
    instrument_map = instrument_map_rows(run_ts, dt)
    _write(
        participants + cow_participants + cow_rpc_participants,
        "market_participants",
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
        golem_capacity + akash_capacity + chutes_capacity,
        "market_capacity",
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
                "finalized_liquidity_event_rows": sum(
                    event["event_type"] in {"liquidity_mint", "liquidity_burn"}
                    for event in rpc_uni_events
                ),
                **uniswap_rpc_detail,
                **uniswap_quoter_detail,
            },
            curated_dir,
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
    if with_akash:
        _run_status(
            "akash",
            len(akash_capacity) + len(akash_quotes) + len(akash_leases_rows),
            run_ts,
            dt,
            {
                "configured": bool(akash_url),
                "gpu_quote_rows": len(akash_quotes),
                "lease_lifecycle_rows": len(akash_leases_rows),
                "lease_blocks_timestamped": sum(
                    row["executed_at"] is not None for row in akash_leases_rows
                ),
                **akash_coverage,
            },
            curated_dir,
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

    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "defillama_participants": len(participants),
        "cow_executions": len(cow_executions),
        "cow_finalized_executions": len(cow_rpc_executions),
        "cow_finalized_solver_identified_executions": len(cow_rpc_participants),
        "cow_competition_participants": len(cow_participants),
        "cow_competition_events": len(cow_competition_events),
        "golem_capacity": len(golem_capacity),
        "chutes_capacity": len(chutes_capacity),
        "geckoterminal_quotes": len(geckoterminal_quotes),
        "uniswap_quotes": len(uni_quotes),
        "uniswap_finalized_quote_curve_points": len(quoter_uni_quotes),
        "uniswap_executions": len(uni_executions),
        "uniswap_finalized_executions": len(rpc_uni_executions),
        "uniswap_finalized_liquidity_events": sum(
            event["event_type"] in {"liquidity_mint", "liquidity_burn"} for event in rpc_uni_events
        ),
        "akash_capacity": len(akash_capacity),
        "akash_gpu_quotes": len(akash_quotes),
        "akash_coverage": akash_coverage,
        "akash_lease_lifecycle_rows": len(akash_leases_rows),
    }
    log.info("market-source capture complete: %s", summary)
    return summary


def main(with_uniswap: bool = False, with_akash: bool = False) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(capture_markets(with_uniswap=with_uniswap, with_akash=with_akash))
    print(json.dumps(result, indent=2))
    return result
