"""Public, block-pinned Bittensor metagraph capture for Chutes subnet 64.

This collector records public allocation/scoring state, not user requests,
inference routes, delivered workloads, prices, revenue, or provider costs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp
from .http import write_raw
from .observability import write_source_run

SOURCE = "bittensor_chutes"
DEFAULT_NETUID = 64
DEFAULT_MECHID = 0
DEFAULT_NETWORK = "finney"
SUBNET_NAME = "Chutes"
PUBLIC_ENDPOINT = "wss://entrypoint-finney.opentensor.ai:443"


def _scalar(value: Any) -> int:
    array = np.asarray(value)
    if array.size != 1:
        raise ValueError("expected scalar metagraph field")
    return int(array.reshape(-1)[0])


def _array(value: Any, *, length: int, name: str) -> list[Any]:
    values = np.asarray(value).reshape(-1).tolist()
    if len(values) != length:
        raise ValueError(f"{name} length {len(values)} != metagraph size {length}")
    return values


def metagraph_snapshot(
    metagraph: Any,
    *,
    block_hash: str,
    netuid: int,
    mechid: int,
    network: str,
) -> dict[str, Any]:
    """Convert the SDK object into JSON-safe complete public scoring state."""
    uids = np.asarray(metagraph.uids).reshape(-1)
    size = len(uids)
    hotkeys = list(metagraph.hotkeys)
    coldkeys = list(metagraph.coldkeys)
    if len(hotkeys) != size or len(coldkeys) != size:
        raise ValueError("metagraph identity arrays are incomplete")
    weights = np.asarray(metagraph.W, dtype=float)
    if weights.shape != (size, size):
        raise ValueError(f"weights shape {weights.shape} != {(size, size)}")
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("weights must be finite and non-negative")

    return {
        "network": network,
        "netuid": int(netuid),
        "mechid": int(mechid),
        "subnet_name": SUBNET_NAME if netuid == DEFAULT_NETUID else None,
        "block_number": _scalar(metagraph.block),
        "block_hash": block_hash,
        "n": size,
        "uids": uids.astype(int).tolist(),
        "hotkeys": hotkeys,
        "coldkeys": coldkeys,
        "active": _array(metagraph.active, length=size, name="active"),
        "validator_permit": _array(
            metagraph.validator_permit, length=size, name="validator_permit"
        ),
        "stake": _array(metagraph.stake, length=size, name="stake"),
        "alpha_stake": _array(metagraph.alpha_stake, length=size, name="alpha_stake"),
        "tao_stake": _array(metagraph.tao_stake, length=size, name="tao_stake"),
        "consensus": _array(metagraph.consensus, length=size, name="consensus"),
        "incentive": _array(metagraph.incentive, length=size, name="incentive"),
        "dividends": _array(metagraph.dividends, length=size, name="dividends"),
        "emission": _array(metagraph.emission, length=size, name="emission"),
        "validator_trust": _array(
            metagraph.validator_trust, length=size, name="validator_trust"
        ),
        "last_update": _array(metagraph.last_update, length=size, name="last_update"),
        "weights": weights.tolist(),
        "matrix_complete": True,
    }


def neuron_rows(snapshot: dict[str, Any], run_ts: str, dt: str) -> list[dict[str, Any]]:
    size = int(snapshot["n"])
    arrays = [
        "uids",
        "hotkeys",
        "coldkeys",
        "active",
        "validator_permit",
        "stake",
        "alpha_stake",
        "tao_stake",
        "consensus",
        "incentive",
        "dividends",
        "emission",
        "validator_trust",
        "last_update",
    ]
    if any(len(snapshot.get(name, [])) != size for name in arrays):
        raise ValueError("incomplete metagraph neuron arrays")
    output = []
    for index in range(size):
        output.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": SOURCE,
                "network": snapshot["network"],
                "netuid": snapshot["netuid"],
                "mechid": snapshot["mechid"],
                "subnet_name": snapshot.get("subnet_name"),
                "block_number": snapshot["block_number"],
                "block_hash": snapshot["block_hash"],
                "uid": int(snapshot["uids"][index]),
                "hotkey": snapshot["hotkeys"][index],
                "coldkey": snapshot["coldkeys"][index],
                "active": bool(snapshot["active"][index]),
                "validator_permit": bool(snapshot["validator_permit"][index]),
                "stake": float(snapshot["stake"][index]),
                "alpha_stake": float(snapshot["alpha_stake"][index]),
                "tao_stake": float(snapshot["tao_stake"][index]),
                "consensus": float(snapshot["consensus"][index]),
                "incentive": float(snapshot["incentive"][index]),
                "dividends": float(snapshot["dividends"][index]),
                "emission": float(snapshot["emission"][index]),
                "validator_trust": float(snapshot["validator_trust"][index]),
                "last_update_block": int(snapshot["last_update"][index]),
                "metric_definition": (
                    "block-pinned public Bittensor metagraph state for one subnet; reward and "
                    "scoring allocation, not a request route, workload, price, or delivered "
                    "inference observation"
                ),
            }
        )
    return output


def weight_rows(snapshot: dict[str, Any], run_ts: str, dt: str) -> list[dict[str, Any]]:
    """Store the complete matrix sparsely; absent pairs are known zeros."""
    weights = np.asarray(snapshot["weights"], dtype=float)
    size = int(snapshot["n"])
    if weights.shape != (size, size) or snapshot.get("matrix_complete") is not True:
        raise ValueError("weight matrix is not complete")
    uids = [int(value) for value in snapshot["uids"]]
    output = []
    for validator_index, miner_index in np.argwhere(weights > 0):
        output.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "source": SOURCE,
                "network": snapshot["network"],
                "netuid": snapshot["netuid"],
                "mechid": snapshot["mechid"],
                "subnet_name": snapshot.get("subnet_name"),
                "block_number": snapshot["block_number"],
                "block_hash": snapshot["block_hash"],
                "validator_uid": uids[int(validator_index)],
                "validator_hotkey": snapshot["hotkeys"][int(validator_index)],
                "miner_uid": uids[int(miner_index)],
                "miner_hotkey": snapshot["hotkeys"][int(miner_index)],
                "weight": float(weights[validator_index, miner_index]),
                "matrix_size": size,
                "matrix_complete_sparse_encoding": True,
                "metric_definition": (
                    "nonzero entry in a complete public validator-to-miner Bittensor weight "
                    "matrix; missing pairs in this block snapshot are exact zeros, not "
                    "unobserved routes"
                ),
            }
        )
    return output


def capture_bittensor(
    *,
    netuid: int = DEFAULT_NETUID,
    mechid: int = DEFAULT_MECHID,
    network: str = DEFAULT_NETWORK,
    raw_dir: Path = RAW_DIR,
    curated_dir: Path = CURATED_DIR,
) -> dict[str, Any]:
    """Query the official public network endpoint through the pinned SDK."""
    run_ts, dt = run_timestamp(), dt_partition()
    try:
        import bittensor as bt
    except ImportError as exc:  # pragma: no cover - exercised by base-only installs
        raise RuntimeError("install the bittensor optional dependency") from exc

    subtensor = bt.Subtensor(network=network)
    try:
        metagraph = subtensor.metagraph(netuid=netuid, mechid=mechid, lite=False)
        block_number = _scalar(metagraph.block)
        block_hash = subtensor.get_block_hash(block_number)
        snapshot = metagraph_snapshot(
            metagraph,
            block_hash=block_hash,
            netuid=netuid,
            mechid=mechid,
            network=network,
        )
    finally:
        subtensor.close()

    neurons = neuron_rows(snapshot, run_ts, dt)
    weights = weight_rows(snapshot, run_ts, dt)
    write_raw(
        [
            {
                "fetched_at": run_ts,
                "url": PUBLIC_ENDPOINT,
                "method": "Bittensor SDK full metagraph query",
                "status": 200,
                "body": snapshot,
            }
        ],
        SOURCE,
        raw_dir,
        run_ts,
        dt,
    )
    if neurons:
        write_partition(
            pa.Table.from_pylist(neurons), "bittensor_neurons", run_ts, dt, curated_dir
        )
    if weights:
        write_partition(
            pa.Table.from_pylist(weights), "bittensor_weights", run_ts, dt, curated_dir
        )
    complete = len(neurons) == int(snapshot["n"]) and snapshot["matrix_complete"] is True
    detail = {
        "network": network,
        "netuid": netuid,
        "mechid": mechid,
        "subnet_name": snapshot.get("subnet_name"),
        "block_number": snapshot["block_number"],
        "block_hash": snapshot["block_hash"],
        "neurons": len(neurons),
        "nonzero_weights": len(weights),
        "matrix_size": snapshot["n"],
        "matrix_complete": snapshot["matrix_complete"],
        "metric_boundary": (
            "public subnet scoring/reward state; not request-level routing, tokens served, "
            "price, workload success, cost, revenue, or user welfare"
        ),
    }
    write_source_run(
        SOURCE,
        status="success" if complete else "degraded",
        rows=len(neurons) + len(weights),
        watermark=str(snapshot["block_number"]),
        detail=detail,
        run_ts=run_ts,
        dt=dt,
        curated_dir=curated_dir,
    )
    return {
        "run_ts": run_ts,
        "dt": dt,
        "rows": len(neurons) + len(weights),
        "source_status": "success" if complete else "degraded",
        **detail,
    }


def main(
    *,
    netuid: int = DEFAULT_NETUID,
    mechid: int = DEFAULT_MECHID,
    network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = capture_bittensor(netuid=netuid, mechid=mechid, network=network)
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
