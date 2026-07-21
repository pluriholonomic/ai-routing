"""DuckDB access layer for analysis modules.

Reads from the HF dataset repo by default (authoritative store; the local
data/ staging dir is transient), or from a local data dir for tests via
ORCAP_ANALYSIS_SOURCE=local.
"""

import functools
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from ..config import DATA_DIR, HF_DATASET_REPO


def _hf_base() -> str:
    revision = os.environ.get("ORCAP_HF_REVISION", "").strip()
    suffix = f"@{revision}" if revision else ""
    return f"hf://datasets/{HF_DATASET_REPO}{suffix}"


@contextmanager
def pinned_analysis_source() -> Iterator[dict[str, str | None]]:
    """Freeze a multi-query release run to one immutable input revision.

    Ordinary live analyses intentionally read the dataset head. Manuscript
    releases instead use this context so a concurrent capture upload or late
    backfill cannot mix two dataset states or silently mutate a dated vintage.
    """
    source = os.environ.get("ORCAP_ANALYSIS_SOURCE", "hf")
    if source == "local":
        revision = os.environ.get("ORCAP_HF_REVISION", "").strip() or None
        yield {
            "source": "huggingface_local_snapshot" if revision else "local",
            "repo_id": HF_DATASET_REPO if revision else None,
            "revision": revision,
            "path": str(Path(DATA_DIR).resolve()),
            "resolution": "caller_managed_local_snapshot",
        }
        return

    previous = os.environ.get("ORCAP_HF_REVISION")
    revision = (previous or "").strip()
    resolution = "environment"
    if not revision:
        from huggingface_hub import HfApi

        revision = str(HfApi().dataset_info(HF_DATASET_REPO).sha or "").strip()
        resolution = "dataset_head_at_run_start"
    if not revision:
        raise RuntimeError("could not resolve an immutable Hugging Face dataset revision")

    os.environ["ORCAP_HF_REVISION"] = revision
    reset_connection()
    try:
        yield {
            "source": "huggingface",
            "repo_id": HF_DATASET_REPO,
            "revision": revision,
            "path": _hf_base(),
            "resolution": resolution,
        }
    finally:
        reset_connection()
        if previous is None:
            os.environ.pop("ORCAP_HF_REVISION", None)
        else:
            os.environ["ORCAP_HF_REVISION"] = previous


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
