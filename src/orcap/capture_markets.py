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
AKASH_CONSOLE_PROVIDERS_URL = "https://console-api.akash.network/v1/providers"
AKASH_GPU_PRICES_URL = "https://console-api.akash.network/v1/gpu-prices"
AKASH_LEASES_URL = (
    "https://console-api.akash.network/akash/market/v1beta5/leases/list"
    "?pagination.limit=50&pagination.reverse=true"
)
AKASH_RPC_URL = "https://rpc.akashnet.net:443"
GRAPH_GATEWAY = "https://gateway.thegraph.com/api/{key}/subgraphs/id/{subgraph_id}"
INSTRUMENTS_PATH = Path(__file__).resolve().parents[2] / "config" / "instruments.toml"


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


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
                "quality_tier": "onchain-finalized-pending",
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
                    "record_json": _json(swap),
                }
            )
    return quotes, executions, events


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


def _write(rows: list[dict[str, Any]], table: str, run_ts: str, dt: str, curated_dir: Path) -> None:
    if rows:
        write_partition(pa.Table.from_pylist(rows), table, run_ts, dt, curated_dir)


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
        defillama, golem = await asyncio.gather(
            fetcher.get_json(DEFILLAMA_PROTOCOLS_URL),
            fetcher.get_json(os.environ.get("ORCAP_GOLEM_STATS_URL", GOLEM_ONLINE_URL)),
        )
        cow = await fetcher.get_json(cow_url) if cow_url else None

        uniswap = None
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
                GRAPH_GATEWAY.format(key=graph_key, subgraph_id=subgraph_id), query
            )

        akash = None
        akash_gpu_prices = None
        akash_leases = None
        akash_block_times: dict[int, str | None] = {}
        akash_url = os.environ.get("ORCAP_AKASH_NETWORK_URL", AKASH_CONSOLE_PROVIDERS_URL)
        if with_akash:
            headers = (
                {"x-api-key": os.environ["AKASH_API_KEY"]}
                if os.environ.get("AKASH_API_KEY")
                else None
            )
            akash = await fetcher.get_json(akash_url, headers=headers)
            akash_gpu_prices = await fetcher.get_json(
                os.environ.get("ORCAP_AKASH_GPU_PRICES_URL", AKASH_GPU_PRICES_URL)
            )
            akash_leases = await fetcher.get_json(
                os.environ.get("ORCAP_AKASH_LEASES_URL", AKASH_LEASES_URL)
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
            rpc_url = os.environ.get("ORCAP_AKASH_RPC_URL", AKASH_RPC_URL).rstrip("/")
            block_bodies = await asyncio.gather(
                *(fetcher.get_json(f"{rpc_url}/header?height={height}") for height in heights)
            )
            akash_block_times = {
                height: _block_time(body)
                for height, body in zip(heights, block_bodies, strict=True)
            }
        write_raw(fetcher.records, "market_sources", raw_dir, run_ts, dt)

    participants = defillama_participant_rows(defillama, run_ts, dt)
    cow_executions = cow_execution_rows(cow, run_ts, dt)
    golem_capacity = golem_capacity_rows(golem, run_ts, dt)
    uni_quotes, uni_executions, uni_events = uniswap_rows(uniswap, run_ts, dt)
    akash_capacity = akash_capacity_rows(akash, run_ts, dt)
    akash_coverage = akash_registry_summary(akash)
    akash_quotes = akash_gpu_quote_rows(akash_gpu_prices, run_ts, dt)
    akash_leases_rows = akash_lease_execution_rows(akash_leases, akash_block_times, run_ts, dt)
    instrument_map = instrument_map_rows(run_ts, dt)
    _write(participants, "market_participants", run_ts, dt, curated_dir)
    _write(
        cow_executions + uni_executions + akash_leases_rows,
        "market_executions",
        run_ts,
        dt,
        curated_dir,
    )
    _write(uni_quotes + akash_quotes, "market_quotes", run_ts, dt, curated_dir)
    _write(golem_capacity + akash_capacity, "market_capacity", run_ts, dt, curated_dir)
    _write(
        execution_events(cow_executions, "trade")
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
    if cow_url:
        _run_status("cow", len(cow_executions), run_ts, dt, {"url": cow_url}, curated_dir)
    else:
        write_source_run(
            "cow",
            status="skipped",
            run_ts=run_ts,
            dt=dt,
            detail={"reason": "set ORCAP_COW_TRADES_URL to a scoped official feed"},
            curated_dir=curated_dir,
        )
    _run_status(
        "golem",
        len(golem_capacity),
        run_ts,
        dt,
        {"url": os.environ.get("ORCAP_GOLEM_STATS_URL", GOLEM_ONLINE_URL)},
        curated_dir,
    )
    if with_uniswap:
        _run_status(
            "uniswap",
            len(uni_quotes) + len(uni_executions),
            run_ts,
            dt,
            {"configured": bool(graph_key and subgraph_id and pool_ids)},
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
        "golem_capacity": len(golem_capacity),
        "uniswap_quotes": len(uni_quotes),
        "uniswap_executions": len(uni_executions),
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
