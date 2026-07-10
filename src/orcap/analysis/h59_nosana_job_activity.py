"""H59 — source-bounded Nosana aggregate job-activity monitoring.

Nosana Explore's public aggregate API reports state counts and rolling job
count/duration buckets. The API is an indexer view, so H59 keeps the latest
revision of each source bucket and reports only source-defined job activity.
It does not infer LLM traffic, GPU utilization, cleared capacity, or routing.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

BUCKET_METRICS = {
    "source_reported_completed_job_count_bucket",
    "source_reported_job_duration_hours_bucket",
}
BUCKET_COLUMNS = [
    "metric",
    "bucket_start_unix_ms",
    "bucket_start",
    "value",
    "source_total",
    "requested_period_seconds",
    "latest_run_ts",
    "n_revisions",
]
RUNNING_COLUMNS = [
    "run_ts",
    "dt",
    "running_jobs",
    "n_markets",
    "top_market_running_share",
    "running_job_hhi",
]
MIN_DAYS = 7
MIN_BUCKETS_PER_METRIC = 100


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def load_activity() -> pd.DataFrame:
    """Load only the aggregate, privacy-preserving Nosana activity table."""
    glob = data.table_glob("nosana_job_activity")
    required = {
        "run_ts",
        "dt",
        "source",
        "metric",
        "value",
        "observation_type",
    }
    try:
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return pd.DataFrame()
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(dt as varchar) as dt,
                   cast(metric as varchar) as metric,
                   value,
                   cast(observation_type as varchar) as observation_type,
                   cast(market_id as varchar) as market_id,
                   source_bucket_unix_ms,
                   source_total,
                   requested_period_seconds
            from read_parquet('{glob}', union_by_name=true)
            where source = 'nosana_jobs_api'
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def latest_bucket_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest captured revision of each aggregate source bucket."""
    required = {
        "run_ts",
        "metric",
        "value",
        "observation_type",
        "source_bucket_unix_ms",
    }
    if rows.empty or not required.issubset(rows.columns):
        return _empty(BUCKET_COLUMNS)
    panel = rows.loc[
        rows["observation_type"].eq("rolling_bucket")
        & rows["metric"].isin(BUCKET_METRICS)
    ].copy()
    if panel.empty:
        return _empty(BUCKET_COLUMNS)
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    panel["bucket_start_unix_ms"] = pd.to_numeric(
        panel["source_bucket_unix_ms"], errors="coerce"
    )
    panel["value"] = pd.to_numeric(panel["value"], errors="coerce")
    panel["source_total"] = pd.to_numeric(panel.get("source_total"), errors="coerce")
    panel["requested_period_seconds"] = pd.to_numeric(
        panel.get("requested_period_seconds"), errors="coerce"
    )
    panel = panel.dropna(subset=["captured_at", "bucket_start_unix_ms", "value"])
    panel = panel.loc[(panel["bucket_start_unix_ms"] > 0) & (panel["value"] >= 0)].copy()
    if panel.empty:
        return _empty(BUCKET_COLUMNS)
    keys = ["metric", "bucket_start_unix_ms"]
    revisions = panel.groupby(keys).size().rename("n_revisions").reset_index()
    latest = panel.sort_values("captured_at").drop_duplicates(keys, keep="last")
    latest = latest.merge(revisions, on=keys, how="inner", validate="one_to_one")
    latest["bucket_start"] = pd.to_datetime(
        latest["bucket_start_unix_ms"], unit="ms", utc=True
    )
    latest = latest.rename(columns={"run_ts": "latest_run_ts"})
    return latest.loc[:, BUCKET_COLUMNS].sort_values(["metric", "bucket_start_unix_ms"])


def running_market_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Summarize public market-level running counts at each collector snapshot."""
    required = {"run_ts", "dt", "metric", "value", "observation_type", "market_id"}
    if rows.empty or not required.issubset(rows.columns):
        return _empty(RUNNING_COLUMNS)
    panel = rows.loc[
        rows["observation_type"].eq("market_snapshot")
        & rows["metric"].eq("source_reported_running_jobs_by_market")
    ].copy()
    panel["value"] = pd.to_numeric(panel.get("value"), errors="coerce")
    panel = panel.dropna(subset=["run_ts", "dt", "market_id", "value"])
    panel = panel.loc[panel["value"] >= 0]
    if panel.empty:
        return _empty(RUNNING_COLUMNS)
    rows_out = []
    for (run_ts, dt), group in panel.groupby(["run_ts", "dt"], dropna=False):
        running = float(group["value"].sum())
        shares = group["value"] / running if running > 0 else pd.Series(dtype="float64")
        rows_out.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "running_jobs": running,
                "n_markets": int(group["market_id"].nunique()),
                "top_market_running_share": float(shares.max()) if not shares.empty else None,
                "running_job_hhi": float((shares**2).sum()) if not shares.empty else None,
            }
        )
    return pd.DataFrame(rows_out, columns=RUNNING_COLUMNS).sort_values("run_ts")


def coverage_gate(bucket_panel: pd.DataFrame) -> dict:
    if bucket_panel.empty:
        return {
            "status": "not_identified",
            "source_bucket_days": 0,
            "completed_job_buckets": 0,
            "duration_hour_buckets": 0,
            "minimum_days": MIN_DAYS,
            "minimum_buckets_per_metric": MIN_BUCKETS_PER_METRIC,
        }
    dates = pd.to_datetime(bucket_panel["bucket_start"], utc=True, errors="coerce").dt.date
    counts = bucket_panel.groupby("metric").size().to_dict()
    job_buckets = int(counts.get("source_reported_completed_job_count_bucket", 0))
    hour_buckets = int(counts.get("source_reported_job_duration_hours_bucket", 0))
    status = (
        "source_bounded_dynamic_panel_ready"
        if dates.nunique() >= MIN_DAYS
        and job_buckets >= MIN_BUCKETS_PER_METRIC
        and hour_buckets >= MIN_BUCKETS_PER_METRIC
        else "power_gated"
    )
    return {
        "status": status,
        "source_bucket_days": int(dates.nunique()),
        "completed_job_buckets": job_buckets,
        "duration_hour_buckets": hour_buckets,
        "minimum_days": MIN_DAYS,
        "minimum_buckets_per_metric": MIN_BUCKETS_PER_METRIC,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_activity()
    buckets = latest_bucket_panel(rows)
    running = running_market_panel(rows)
    gate = coverage_gate(buckets)
    save(buckets, out_dir, "h59_nosana_job_activity_buckets")
    save(running, out_dir, "h59_nosana_running_market")
    summary = {
        "activity_rows": int(len(rows)),
        "coverage_gate": gate,
        "running_market_snapshots": int(len(running)),
        "claim_boundary": (
            "H59 reports only public, source-defined Nosana Explore aggregate job-state counts, "
            "market-level running counts, and rolling count/duration buckets. It does not identify "
            "LLM requests or routing, tokens, unique users, verified GPU-hours, capacity, "
            "utilization, job usefulness, realized payment, revenue, profit, or causal demand."
        ),
    }
    save_json(summary, out_dir, "h59_summary")
    return summary
