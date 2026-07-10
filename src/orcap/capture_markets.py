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
DEFAULT_UNISWAP_LOG_WINDOW_BLOCKS = 128
GPV2_SETTLEMENT_ADDRESS = "0x9008d19f58aabd9ed0d60971565aa8510560ab41"
GPV2_TRADE_TOPIC = "0xa07a543ab8a018198e99ca0184c93fe9050a79400a0a723441f84de1d972cc17"
GPV2_SETTLEMENT_TOPIC = "0x40338ce1a7c49204f0099533b1e9a7ee0a3d261f84974ab7af36105b8c4e9db4"


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _configured_url(name: str, default: str) -> str:
    """Use the public default when Actions injects an empty optional variable."""
    return os.environ.get(name) or default


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


def uniswap_pool_specs() -> dict[str, dict[str, Any]]:
    """Load the checked-in, exact-token metadata for registered V3 pools."""
    with INSTRUMENTS_PATH.open("rb") as handle:
        instruments = tomllib.load(handle)["instruments"]
    result: dict[str, dict[str, Any]] = {}
    required = ("source_id", "canonical_instrument", "quality_tier")
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
        address = str(raw["source_id"]).lower()
        result[address] = {
            "map_id": map_id,
            "canonical_instrument": str(raw["canonical_instrument"]),
            "quality_tier": str(raw["quality_tier"]),
            "token0_symbol": str(raw.get("token0_symbol") or "token0"),
            "token0_decimals": decimals[0],
            "token1_symbol": str(raw.get("token1_symbol") or "token1"),
            "token1_decimals": decimals[1],
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
        record_json = _json({"log": log_row, "parsed": parsed})
        executions.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": "cow",
                "venue": "cow-protocol",
                "execution_id": event_id,
                "instrument_id": f"ethereum:{sell_token}/{buy_token}",
                "executed_at": block_times.get(block_number),
                "event_block_number": block_number,
                "finalized": True,
                "side": "sell_token_to_buy_token",
                # Token decimal metadata is not present in GPv2 Trade. Preserve
                # exact raw values rather than manufacture normalized amounts.
                "requested_size": None,
                "filled_size": None,
                "sell_amount_raw": str(sell_amount),
                "buy_amount_raw": str(buy_amount),
                "gross_price_usd": None,
                "native_price": None,
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
                    "One finalized GPv2 Trade event per executed order. Amounts are raw token "
                    "units; no USD price, gas-inclusive execution cost, surplus, or solver is "
                    "imputed."
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
    fetcher: Fetcher, url: str, method: str, params: list[Any]
) -> tuple[Any | None, str | None]:
    """Make one JSON-RPC call while retaining only a redacted endpoint label."""
    body = await fetcher.post_json(
        url,
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        record_url="configured:ORCAP_ETHEREUM_RPC_URL",
    )
    if not isinstance(body, dict):
        return None, "no JSON-RPC response"
    if isinstance(body.get("error"), dict):
        return None, str(body["error"].get("message") or "JSON-RPC error")
    if "result" not in body:
        return None, "JSON-RPC response has no result"
    return body["result"], None


async def _ethereum_rpc_batch(
    fetcher: Fetcher, url: str, calls: list[tuple[int, str, list[Any]]]
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
        record_url="configured:ORCAP_ETHEREUM_RPC_URL",
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
    fetcher: Fetcher, url: str
) -> tuple[list[dict[str, Any]], dict[int, str | None], dict[str, Any]]:
    """Fetch a bounded, finalized log window for registered Uniswap V3 pools."""
    latest_raw, latest_error = await _ethereum_rpc(fetcher, url, "eth_blockNumber", [])
    latest_block = _hex_int(latest_raw)
    if latest_block is None:
        return [], {}, {"rpc_configured": True, "error": latest_error or "invalid latest block"}
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
    )
    logs = [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []
    detail: dict[str, Any] = {
        "rpc_configured": True,
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
    )
    block_times = {
        block_number: _ethereum_block_time(responses.get(index))
        for index, block_number in enumerate(block_numbers, start=1)
    }
    detail["block_timestamp_rows"] = sum(value is not None for value in block_times.values())
    if errors:
        detail["block_timestamp_errors"] = len(errors)
    return logs, block_times, detail


async def _capture_cow_rpc_logs(
    fetcher: Fetcher, url: str
) -> tuple[list[dict[str, Any]], dict[int, str | None], dict[str, Any]]:
    """Fetch a bounded, finalized GPv2Settlement event window."""
    latest_raw, latest_error = await _ethereum_rpc(fetcher, url, "eth_blockNumber", [])
    latest_block = _hex_int(latest_raw)
    if latest_block is None:
        return [], {}, {"rpc_configured": True, "error": latest_error or "invalid latest block"}
    finality_blocks = _bounded_int_env(
        "ORCAP_ETHEREUM_FINALITY_BLOCKS",
        DEFAULT_ETHEREUM_FINALITY_BLOCKS,
        minimum=1,
        maximum=10_000,
    )
    window_blocks = _bounded_int_env(
        "ORCAP_COW_LOG_WINDOW_BLOCKS",
        DEFAULT_UNISWAP_LOG_WINDOW_BLOCKS,
        minimum=1,
        maximum=10_000,
    )
    finalized_through = latest_block - finality_blocks
    if finalized_through < 0:
        return [], {}, {
            "rpc_configured": True,
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
    )
    logs = [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []
    detail: dict[str, Any] = {
        "rpc_configured": True,
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
    )
    block_times = {
        block_number: _ethereum_block_time(responses.get(index))
        for index, block_number in enumerate(block_numbers, start=1)
    }
    detail["block_timestamp_rows"] = sum(value is not None for value in block_times.values())
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
        cow_url = os.environ.get("ORCAP_COW_TRADES_URL")
        cow_competition_url = _configured_url(
            "ORCAP_COW_SOLVER_COMPETITION_URL", COW_SOLVER_COMPETITION_LATEST_URL
        )
        defillama, golem, cow_competition = await asyncio.gather(
            fetcher.get_json(DEFILLAMA_PROTOCOLS_URL),
            fetcher.get_json(_configured_url("ORCAP_GOLEM_STATS_URL", GOLEM_ONLINE_URL)),
            fetcher.get_json(cow_competition_url),
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
            "rpc_configured": bool(os.environ.get("ORCAP_ETHEREUM_RPC_URL"))
        }

        uniswap = None
        uniswap_rpc_logs: list[dict[str, Any]] = []
        uniswap_block_times: dict[int, str | None] = {}
        uniswap_rpc_detail: dict[str, Any] = {
            "rpc_configured": bool(os.environ.get("ORCAP_ETHEREUM_RPC_URL"))
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
        ethereum_rpc_url = os.environ.get("ORCAP_ETHEREUM_RPC_URL")
        if with_uniswap and ethereum_rpc_url:
            uniswap_rpc_logs, uniswap_block_times, uniswap_rpc_detail = (
                await _capture_uniswap_rpc_logs(fetcher, ethereum_rpc_url)
            )
        if ethereum_rpc_url:
            cow_rpc_logs, cow_block_times, cow_rpc_detail = await _capture_cow_rpc_logs(
                fetcher, ethereum_rpc_url
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
    uni_quotes, graph_uni_executions, graph_uni_events = uniswap_rows(uniswap, run_ts, dt)
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
    _write(golem_capacity + akash_capacity, "market_capacity", run_ts, dt, curated_dir)
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
                "graph_quote_rows": len(uni_quotes),
                "graph_execution_rows_ignored_for_finalized_path": (
                    len(graph_uni_executions) if uniswap_rpc_detail["rpc_configured"] else 0
                ),
                "finalized_execution_rows": len(rpc_uni_executions),
                "finalized_liquidity_event_rows": sum(
                    event["event_type"] in {"liquidity_mint", "liquidity_burn"}
                    for event in rpc_uni_events
                ),
                **uniswap_rpc_detail,
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
        "geckoterminal_quotes": len(geckoterminal_quotes),
        "uniswap_quotes": len(uni_quotes),
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
