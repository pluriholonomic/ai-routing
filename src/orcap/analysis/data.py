"""DuckDB access layer for analysis modules.

Reads from the HF dataset repo by default (authoritative store; the local
data/ staging dir is transient), or from a local data dir for tests via
ORCAP_ANALYSIS_SOURCE=local.
"""

import functools
import os

import duckdb

from ..config import DATA_DIR, HF_DATASET_REPO


def _hf_base() -> str:
    return f"hf://datasets/{HF_DATASET_REPO}"


@functools.lru_cache(maxsize=1)
def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    source = os.environ.get("ORCAP_ANALYSIS_SOURCE", "hf")
    if source == "hf":
        from huggingface_hub import get_token

        token = os.environ.get("HF_TOKEN") or get_token()
        con.sql(f"CREATE SECRET hf (TYPE huggingface, TOKEN '{token}')")
    return con


def reset_connection() -> None:
    """Close and discard the process-wide analytical connection, if any."""
    if connect.cache_info().currsize:
        connection = connect()
        try:
            connection.close()
        finally:
            connect.cache_clear()


def table_glob(name: str, layer: str = "curated") -> str:
    source = os.environ.get("ORCAP_ANALYSIS_SOURCE", "hf")
    base = str(DATA_DIR) if source == "local" else _hf_base()
    return f"{base}/{layer}/{name}/*/*.parquet"


def q(sql: str) -> duckdb.DuckDBPyRelation:
    try:
        return connect().sql(sql)
    except duckdb.TransactionException as exc:
        # An optional query can fail inside an explicit DuckDB transaction and
        # be handled by its hypothesis module, leaving the shared connection in
        # an aborted state. Heal that state once; preserve the retried query's
        # real exception if the SQL or input itself is invalid.
        if "transaction is aborted" not in str(exc).lower():
            raise
        reset_connection()
        return connect().sql(sql)


def latest_endpoints() -> str:
    """Subquery: most recent full endpoints snapshot."""
    g = table_glob("endpoints_snapshots")
    return f"""(
      with latest as (select max(run_ts) m from read_parquet('{g}'))
      select * from read_parquet('{g}'), latest where run_ts = latest.m
    )"""


def wayback_models() -> str:
    source = os.environ.get("ORCAP_ANALYSIS_SOURCE", "hf")
    base = str(DATA_DIR) if source == "local" else _hf_base()
    return f"read_parquet('{base}/backfill/models_snapshots_wayback/*/*.parquet')"


def effective_pricing() -> str:
    return f"read_parquet('{table_glob('effective_pricing_daily')}')"


def apps() -> str:
    return f"read_parquet('{table_glob('apps_leaderboards')}')"


def activity() -> str:
    return f"read_parquet('{table_glob('model_activity_daily')}')"


def gpu_offers() -> str:
    return f"read_parquet('{table_glob('gpu_offers_snapshots')}')"


def models_snapshots() -> str:
    return f"read_parquet('{table_glob('models_snapshots')}')"


def external(name: str) -> str:
    source = os.environ.get("ORCAP_ANALYSIS_SOURCE", "hf")
    base = str(DATA_DIR) if source == "local" else _hf_base()
    return f"read_parquet('{base}/external/{name}.parquet')"
