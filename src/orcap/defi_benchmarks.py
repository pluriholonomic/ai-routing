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
                      since 2024 -> cross-pool dispersion for the same pair
  btc_hashprice_daily BTC difficulty + block subsidy + BTC-USD -> $/TH/day
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
          WHERE block_timestamp >= '2024-01-01'
            AND address IN ('{POOL_USDC_WETH_5}', '{POOL_USDC_WETH_30}')
            AND topics[SAFE_OFFSET(0)] = '{UNIV3_SWAP_TOPIC}'
        )
        SELECT day, pool,
               POW(sqrt_price_x96 / POW(2, 96), 2) * 1e12 AS weth_per_usdc_scaled
        FROM swaps WHERE rn = 1 ORDER BY day, pool
    """,
    "btc_difficulty_daily": """
        SELECT DATE(timestamp) AS day,
               AVG(difficulty) AS difficulty,
               COUNT(*) AS n_blocks
        FROM `bigquery-public-data.crypto_bitcoin.blocks`
        WHERE timestamp >= '2020-01-01'
        GROUP BY 1 ORDER BY 1
    """,
}


def _cache_path(name: str) -> Path:
    return EXTERNAL_DIR / f"{name}.parquet"


def run_bigquery(name: str, force: bool = False) -> Path | None:
    cache = _cache_path(name)
    if cache.exists() and not force:
        log.info("%s: cached (%s)", name, cache)
        return cache
    from google.cloud import bigquery

    client = bigquery.Client()
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


def build_hashprice(force: bool = False) -> Path | None:
    """$/TH/day = (subsidy_btc_per_day * btc_usd) / network_TH."""
    diff_p, btc_p = _cache_path("btc_difficulty_daily"), _cache_path("btc_usd_daily")
    if not (diff_p.exists() and btc_p.exists()):
        log.warning("hashprice needs btc_difficulty_daily + btc_usd_daily first")
        return None
    cache = _cache_path("btc_hashprice_daily")
    if cache.exists() and not force:
        return cache
    d = pd.read_parquet(diff_p)
    b = pd.read_parquet(btc_p)
    d["day"] = pd.to_datetime(d["day"])
    b["day"] = pd.to_datetime(b["day"])
    m = d.merge(b, on="day")
    m["hashrate_ths"] = m["difficulty"] * 2**32 / 600 / 1e12
    m["day_dt"] = m["day"]
    halvings = [
        (pd.Timestamp("2020-05-11"), 6.25),
        (pd.Timestamp("2024-04-20"), 3.125),
        (pd.Timestamp("2028-01-01"), 1.5625),
    ]

    def subsidy(ts):
        s = 6.25
        for h, v in halvings:
            if ts >= h:
                s = v
        return s

    m["subsidy_btc_day"] = m["day_dt"].map(subsidy) * m["n_blocks"]
    m["hashprice_usd_per_th_day"] = m["subsidy_btc_day"] * m["btc_usd"] / m["hashrate_ths"]
    out = m[["day", "difficulty", "hashrate_ths", "btc_usd", "hashprice_usd_per_th_day"]]
    out.to_parquet(cache, index=False)
    return cache


def main(force: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = {}
    fetch_btc_usd_daily(force)
    results["btc_usd_daily"] = "ok"
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
