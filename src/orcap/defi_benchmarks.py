"""DeFi comparator series from BigQuery public data (+ BTC price from Coinbase).

Every series is cached to external/{name}.parquet (pushed to the HF dataset)
so BigQuery is hit exactly once per series. Auth: application-default
credentials (`gcloud auth application-default login`).

Series:
  basefee_hourly      EIP-1559 base fee (gwei), hourly, since London
  cow_solver_monthly  CoW Protocol settlements per solver per month
                      (solver = tx sender to GPv2Settlement; approximation —
                      some solvers rotate submission EOAs)
  univ3_pool_daily    daily last sqrtPrice for USDC/WETH 5bps & 30bps pools
                      since 2026 -> cross-pool dispersion for the same pair
  btc_hashprice_daily blockchain.info hashrate + subsidy + BTC-USD -> $/TH/day
"""

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from .config import DATA_DIR

log = logging.getLogger(__name__)

EXTERNAL_DIR = DATA_DIR / "external"

GPV2_SETTLEMENT = "0x9008d19f58aabd9ed0d60971565aa8510560ab41"
UNIV3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
POOL_USDC_WETH_5 = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
POOL_USDC_WETH_30 = "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8"

MAX_BYTES_BILLED = 400 * 1024**3  # hard cap per query (~$2.5 at on-demand rates)

QUERIES: dict[str, str] = {
    "basefee_hourly": """
        SELECT TIMESTAMP_TRUNC(timestamp, HOUR) AS hour,
               AVG(base_fee_per_gas) / 1e9 AS avg_base_fee_gwei,
               MIN(base_fee_per_gas) / 1e9 AS min_base_fee_gwei,
               MAX(base_fee_per_gas) / 1e9 AS max_base_fee_gwei,
               COUNT(*) AS n_blocks
        FROM `bigquery-public-data.crypto_ethereum.blocks`
        WHERE timestamp >= '2021-08-05' AND base_fee_per_gas IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """,
    "cow_solver_monthly": f"""
        SELECT DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
               from_address AS solver,
               COUNT(*) AS settlements
        FROM `bigquery-public-data.crypto_ethereum.transactions`
        WHERE to_address = '{GPV2_SETTLEMENT}'
          AND receipt_status = 1
          AND block_timestamp >= '2021-03-01'
        GROUP BY 1, 2 ORDER BY 1, 3 DESC
    """,
    # sqrtPriceX96 is the 3rd 32-byte word of Swap event data; float64 precision
    # is ample for dispersion in log-price space
    "univ3_pool_daily": f"""
        CREATE TEMP FUNCTION hexToFloat(h STRING) RETURNS FLOAT64
        LANGUAGE js AS '''
          let x = 0.0;
          for (let i = 0; i < h.length; i++) x = x * 16 + parseInt(h[i], 16);
          return x;
        ''';
        WITH swaps AS (
          SELECT DATE(block_timestamp) AS day, address AS pool,
                 hexToFloat(SUBSTR(data, 3 + 2 * 64, 64)) AS sqrt_price_x96,
                 ROW_NUMBER() OVER (
                   PARTITION BY DATE(block_timestamp), address
                   ORDER BY block_number DESC, log_index DESC
                 ) AS rn
          FROM `bigquery-public-data.crypto_ethereum.logs`
          -- logs' data column is fat; 6 months keeps the scan under the cost cap
          WHERE block_timestamp >= '2026-01-01'
            AND address IN ('{POOL_USDC_WETH_5}', '{POOL_USDC_WETH_30}')
            AND topics[SAFE_OFFSET(0)] = '{UNIV3_SWAP_TOPIC}'
        )
        SELECT day, pool,
               POW(sqrt_price_x96 / POW(2, 96), 2) * 1e12 AS weth_per_usdc_scaled
        FROM swaps WHERE rn = 1 ORDER BY day, pool
    """,
}


def _cache_path(name: str) -> Path:
    return EXTERNAL_DIR / f"{name}.parquet"


def _bq_project() -> str | None:
    """Billing project: env var, else the ADC quota project."""
    import os

    if p := os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return p
    adc = Path.home() / ".config/gcloud/application_default_credentials.json"
    if adc.exists():
        return json.loads(adc.read_text()).get("quota_project_id")
    return None


def run_bigquery(name: str, force: bool = False) -> Path | None:
    cache = _cache_path(name)
    if cache.exists() and not force:
        log.info("%s: cached (%s)", name, cache)
        return cache
    from google.cloud import bigquery

    client = bigquery.Client(project=_bq_project())
    sql = QUERIES[name]
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    gb = dry.total_bytes_processed / 1024**3
    log.info("%s: dry run scans %.1f GiB", name, gb)
    if dry.total_bytes_processed > MAX_BYTES_BILLED:
        raise RuntimeError(f"{name} would scan {gb:.0f} GiB > cap; narrow the query")
    job = client.query(
        sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    )
    df = job.result().to_dataframe()
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    log.info("%s: %d rows -> %s", name, len(df), cache)
    return cache


def fetch_btc_usd_daily(force: bool = False) -> Path:
    """Daily BTC-USD closes from Coinbase Exchange public candles (no auth)."""
    cache = _cache_path("btc_usd_daily")
    if cache.exists() and not force:
        return cache
    rows = []
    end = datetime.now(UTC)
    start_target = datetime(2020, 1, 1, tzinfo=UTC)
    with httpx.Client(timeout=30) as client:
        while end > start_target:
            start = max(start_target, end - pd.Timedelta(days=299))
            r = client.get(
                "https://api.exchange.coinbase.com/products/BTC-USD/candles",
                params={
                    "granularity": 86400,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                },
                headers={"User-Agent": "orcap/0.1"},
            )
            r.raise_for_status()
            for t, _lo, _hi, _op, close, _vol in r.json():
                rows.append({"day": datetime.fromtimestamp(t, UTC).date(), "btc_usd": close})
            end = start
            time.sleep(0.4)
    df = pd.DataFrame(rows).drop_duplicates("day").sort_values("day")
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return cache


def fetch_perp_funding(force: bool = False, instrument: str = "BTC-PERPETUAL") -> Path:
    """Perp funding-rate history (hourly, with 8h rate) from Deribit's public
    API — the H12 comparator: a market-set basis on a continuously-quoted
    instrument. (Binance's endpoint is geo-blocked from the US.)"""
    cache = _cache_path(f"funding_{instrument.lower().replace('-', '_')}")
    if cache.exists() and not force:
        return cache
    rows: list[dict] = []
    start = pd.Timestamp("2020-01-01", tz="UTC")
    now = pd.Timestamp.now(tz="UTC")
    with httpx.Client(timeout=30) as client:
        while start < now:
            end = min(start + pd.Timedelta(days=30), now)
            r = client.get(
                "https://www.deribit.com/api/v2/public/get_funding_rate_history",
                params={
                    "instrument_name": instrument,
                    "start_timestamp": int(start.timestamp() * 1000),
                    "end_timestamp": int(end.timestamp() * 1000),
                },
                headers={"User-Agent": "orcap/0.1"},
            )
            r.raise_for_status()
            for b in r.json().get("result") or []:
                rows.append(
                    {
                        "funding_time": datetime.fromtimestamp(b["timestamp"] / 1000, UTC),
                        "funding_8h": float(b["interest_8h"]),
                        "index_price": float(b["index_price"]),
                    }
                )
            start = end
            time.sleep(0.25)
    df = pd.DataFrame(rows).drop_duplicates("funding_time").sort_values("funding_time")
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return cache


def fetch_btc_hashrate_daily(force: bool = False) -> Path:
    """Daily network hashrate (TH/s) from blockchain.info's public chart API."""
    cache = _cache_path("btc_hashrate_daily")
    if cache.exists() and not force:
        return cache
    with httpx.Client(timeout=60) as client:
        r = client.get(
            "https://api.blockchain.info/charts/hash-rate",
            params={"timespan": "7years", "format": "json", "sampled": "false"},
            headers={"User-Agent": "orcap/0.1"},
        )
        r.raise_for_status()
        values = r.json()["values"]
    df = pd.DataFrame(
        [
            {"day": datetime.fromtimestamp(v["x"], UTC).date(), "hashrate_ths": v["y"]}
            for v in values
        ]
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return cache


def build_hashprice(force: bool = False) -> Path | None:
    """$/TH/day = (subsidy_btc_per_day * btc_usd) / network_TH; assumes 144 blocks/day
    (fees excluded — subsidy-only hashprice, the standard cost-anchor series)."""
    hr_p, btc_p = _cache_path("btc_hashrate_daily"), _cache_path("btc_usd_daily")
    if not (hr_p.exists() and btc_p.exists()):
        log.warning("hashprice needs btc_hashrate_daily + btc_usd_daily first")
        return None
    cache = _cache_path("btc_hashprice_daily")
    if cache.exists() and not force:
        return cache
    h = pd.read_parquet(hr_p)
    b = pd.read_parquet(btc_p)
    h["day"] = pd.to_datetime(h["day"])
    b["day"] = pd.to_datetime(b["day"])
    m = h.merge(b, on="day")
    halvings = [
        (pd.Timestamp("2020-05-11"), 6.25),
        (pd.Timestamp("2024-04-20"), 3.125),
    ]

    def subsidy(ts):
        s = 12.5
        for hv, v in halvings:
            if ts >= hv:
                s = v
        return s

    m["hashprice_usd_per_th_day"] = m["day"].map(subsidy) * 144 * m["btc_usd"] / m["hashrate_ths"]
    out = m[["day", "hashrate_ths", "btc_usd", "hashprice_usd_per_th_day"]]
    out.to_parquet(cache, index=False)
    return cache


def main(force: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = {}
    fetch_btc_usd_daily(force)
    results["btc_usd_daily"] = "ok"
    fetch_btc_hashrate_daily(force)
    results["btc_hashrate_daily"] = "ok"
    try:
        fetch_perp_funding(force)
        results["funding_btc_perpetual"] = "ok"
    except Exception as exc:  # non-fatal comparator
        log.warning("perp funding fetch failed: %s", exc)
        results["funding_btc_perpetual"] = f"failed: {exc}"
    for name in QUERIES:
        try:
            run_bigquery(name, force)
            results[name] = "ok"
        except Exception as exc:
            log.error("%s failed: %s", name, exc)
            results[name] = f"failed: {exc}"
    if build_hashprice(force):
        results["btc_hashprice_daily"] = "ok"
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
