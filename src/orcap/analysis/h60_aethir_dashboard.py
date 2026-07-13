"""H60 — source-bounded Aethir public-dashboard aggregate panel.

The public dashboard exposes aggregate supply, demand, and earnings series,
not a host-level book or a routing log. H60 preserves the latest revision of
each source-reported monthly point and keeps all interpretations at that
aggregate boundary.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

MONTHLY_METRICS = {
    "source_reported_monthly_cloud_host_rewards_ath",
    "source_reported_monthly_cloud_host_service_fee_ath",
    "source_reported_monthly_network_revenue_usd",
}
MONTHLY_COLUMNS = [
    "metric",
    "source_reported_unit",
    "source_bucket_label",
    "source_bucket_unix_ms",
    "source_bucket_time",
    "value",
    "latest_run_ts",
    "n_revisions",
]
SNAPSHOT_COLUMNS = ["run_ts", "dt", "metric", "source_reported_unit", "value"]
MIN_MONTHLY_POINTS_PER_METRIC = 12
MIN_MONTHS = 6


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def load_dashboard() -> pd.DataFrame:
    """Load only the public aggregate dashboard table, never market tables."""
    required = {
        "run_ts",
        "dt",
        "source",
        "metric",
        "value",
        "observation_type",
        "source_reported_unit",
    }
    try:
        glob = data.table_glob("aethir_dashboard")
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return pd.DataFrame()
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(dt as varchar) as dt,
                   cast(metric as varchar) as metric,
                   cast(source_reported_unit as varchar) as source_reported_unit,
                   value,
                   cast(observation_type as varchar) as observation_type,
                   cast(source_bucket_period as varchar) as source_bucket_period,
                   cast(source_bucket_label as varchar) as source_bucket_label,
                   source_bucket_unix_ms
            from read_parquet('{glob}', union_by_name=true)
            where source = 'aethir_dashboard'
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def latest_monthly_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest capture for each literal Aethir monthly source bucket."""
    required = {
        "run_ts",
        "metric",
        "source_reported_unit",
        "value",
        "observation_type",
        "source_bucket_period",
        "source_bucket_label",
    }
    if rows.empty or not required.issubset(rows.columns):
        return _empty(MONTHLY_COLUMNS)
    panel = rows.loc[
        rows["observation_type"].eq("source_reported_time_bucket")
        & rows["source_bucket_period"].eq("monthly")
        & rows["metric"].isin(MONTHLY_METRICS)
    ].copy()
    if panel.empty:
        return _empty(MONTHLY_COLUMNS)
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    panel["value"] = pd.to_numeric(panel["value"], errors="coerce")
    panel["source_bucket_unix_ms"] = pd.to_numeric(
        panel.get("source_bucket_unix_ms"), errors="coerce"
    )
    panel = panel.dropna(subset=["captured_at", "metric", "source_bucket_label", "value"])
    panel = panel.loc[panel["value"] >= 0].copy()
    if panel.empty:
        return _empty(MONTHLY_COLUMNS)
    keys = ["metric", "source_bucket_label"]
    revisions = panel.groupby(keys).size().rename("n_revisions").reset_index()
    latest = panel.sort_values("captured_at").drop_duplicates(keys, keep="last")
    latest = latest.merge(revisions, on=keys, how="inner", validate="one_to_one")
    label_time = pd.to_datetime(
        latest["source_bucket_label"], format="%B, %Y", utc=True, errors="coerce"
    )
    unix_time = pd.to_datetime(latest["source_bucket_unix_ms"], unit="ms", utc=True)
    latest["source_bucket_time"] = unix_time.where(unix_time.notna(), label_time)
    latest = latest.rename(columns={"run_ts": "latest_run_ts"})
    return latest.loc[:, MONTHLY_COLUMNS].sort_values(
        ["metric", "source_bucket_time", "source_bucket_label"], na_position="last"
    )


def snapshot_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Return literal aggregate dashboard snapshots, not normalized market capacity."""
    required = {"run_ts", "dt", "metric", "source_reported_unit", "value", "observation_type"}
    if rows.empty or not required.issubset(rows.columns):
        return _empty(SNAPSHOT_COLUMNS)
    panel = rows.loc[rows["observation_type"].eq("aggregate_snapshot")].copy()
    panel["value"] = pd.to_numeric(panel.get("value"), errors="coerce")
    panel = panel.dropna(subset=["run_ts", "dt", "metric", "source_reported_unit", "value"])
    panel = panel.loc[panel["value"] >= 0]
    return panel.loc[:, SNAPSHOT_COLUMNS].sort_values(["run_ts", "metric"])


def coverage_gate(monthly: pd.DataFrame) -> dict:
    if monthly.empty:
        return {
            "status": "not_identified",
            "monthly_points_by_metric": {},
            "distinct_months": 0,
            "minimum_monthly_points_per_metric": MIN_MONTHLY_POINTS_PER_METRIC,
            "minimum_months": MIN_MONTHS,
        }
    counts = monthly.groupby("metric").size().to_dict()
    dates = pd.to_datetime(monthly["source_bucket_time"], utc=True, errors="coerce")
    month_count = int(dates.dt.tz_localize(None).dt.to_period("M").nunique())
    status = (
        "source_bounded_monthly_history_ready"
        if all(counts.get(metric, 0) >= MIN_MONTHLY_POINTS_PER_METRIC for metric in MONTHLY_METRICS)
        and month_count >= MIN_MONTHS
        else "power_gated"
    )
    return {
        "status": status,
        "monthly_points_by_metric": {metric: int(count) for metric, count in counts.items()},
        "distinct_months": month_count,
        "minimum_monthly_points_per_metric": MIN_MONTHLY_POINTS_PER_METRIC,
        "minimum_months": MIN_MONTHS,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_dashboard()
    monthly = latest_monthly_panel(rows)
    snapshots = snapshot_panel(rows)
    gate = coverage_gate(monthly)
    save(monthly, out_dir, "h60_aethir_monthly")
    save(snapshots, out_dir, "h60_aethir_snapshots")
    summary = {
        "dashboard_rows": int(len(rows)),
        "aggregate_snapshots": int(len(snapshots)),
        "coverage_gate": gate,
        "claim_boundary": (
            "H60 reports only Aethir public-dashboard, source-defined aggregate cards and "
            "monthly series. It does not identify physical GPU count, available capacity, "
            "offer-level price, individual cloud-host or buyer behavior, route allocation, "
            "LLM requests/tokens, verified GPU-hours, independent utilization, audited "
            "revenue, provider profit, welfare, or causal demand."
        ),
    }
    save_json(summary, out_dir, "h60_summary")
    return summary
