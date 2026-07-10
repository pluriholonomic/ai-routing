"""H61 — source-bounded Akash public aggregate dashboard panel.

The Console Network Data API reports aggregate lease, resource, and spend
metrics. This module makes their availability and coverage visible without
turning an aggregate count into model-level capacity, utilization, price, or
routing flow.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

MIN_DAYS = 7
MIN_SNAPSHOTS = 20
SNAPSHOT_COLUMNS = [
    "run_ts",
    "dt",
    "source_observed_at",
    "source_block_height",
    "metric",
    "source_reported_unit",
    "value",
]
CORE_METRICS = {
    "source_reported_active_lease_count",
    "source_reported_dashboard_active_gpu_count",
    "source_reported_network_gpu_available",
    "source_reported_source_day_uusdc_spent",
}


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def load_dashboard() -> pd.DataFrame:
    """Load the aggregate-only Akash dashboard table when it is available."""
    required = {
        "run_ts",
        "dt",
        "source",
        "source_observed_at",
        "source_block_height",
        "metric",
        "source_reported_unit",
        "value",
    }
    try:
        glob = data.table_glob("akash_dashboard")
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return _empty()
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(dt as varchar) as dt,
                   cast(source_observed_at as varchar) as source_observed_at,
                   source_block_height,
                   cast(metric as varchar) as metric,
                   cast(source_reported_unit as varchar) as source_reported_unit,
                   value
            from read_parquet('{glob}', union_by_name=true)
            where source = 'akash_dashboard'
            """
        ).df()
    except Exception:
        return _empty()


def snapshot_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep one latest revision for each source timestamp and metric."""
    if rows.empty or not set(SNAPSHOT_COLUMNS).issubset(rows.columns):
        return _empty()
    panel = rows.loc[rows["metric"].isin(CORE_METRICS)].copy()
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    panel["source_observed_at"] = pd.to_datetime(
        panel["source_observed_at"], utc=True, errors="coerce"
    )
    panel["source_block_height"] = pd.to_numeric(panel["source_block_height"], errors="coerce")
    panel["value"] = pd.to_numeric(panel["value"], errors="coerce")
    panel = panel.dropna(
        subset=["captured_at", "source_observed_at", "source_block_height", "metric", "value"]
    )
    panel = panel.loc[(panel["source_block_height"] > 0) & (panel["value"] >= 0)].copy()
    if panel.empty:
        return _empty()
    panel = panel.sort_values("captured_at").drop_duplicates(
        ["source_observed_at", "metric"], keep="last"
    )
    return panel.loc[:, SNAPSHOT_COLUMNS].sort_values(["source_observed_at", "metric"])


def coverage_gate(panel: pd.DataFrame) -> dict:
    """Gate aggregate monitoring before a descriptive time-series result."""
    if panel.empty:
        return {
            "status": "not_identified",
            "source_observation_days": 0,
            "source_snapshots": 0,
            "core_metrics_present": [],
            "minimum_days": MIN_DAYS,
            "minimum_snapshots": MIN_SNAPSHOTS,
        }
    snapshot_times = pd.to_datetime(panel["source_observed_at"], utc=True, errors="coerce")
    snapshot_keys = panel[["source_observed_at", "source_block_height"]].drop_duplicates()
    days = int(snapshot_times.dt.date.nunique())
    snapshots = int(len(snapshot_keys))
    metrics = sorted(panel["metric"].unique())
    reasons = []
    if days < MIN_DAYS:
        reasons.append(f"only {days}/{MIN_DAYS} source observation days")
    if snapshots < MIN_SNAPSHOTS:
        reasons.append(f"only {snapshots}/{MIN_SNAPSHOTS} source snapshots")
    missing = sorted(CORE_METRICS.difference(metrics))
    if missing:
        reasons.append(f"missing core metrics: {', '.join(missing)}")
    return {
        "status": "source_bounded_descriptive" if not reasons else "power_gated",
        "source_observation_days": days,
        "source_snapshots": snapshots,
        "core_metrics_present": metrics,
        "minimum_days": MIN_DAYS,
        "minimum_snapshots": MIN_SNAPSHOTS,
        "gate_reasons": reasons,
    }


def latest_metrics(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {}
    latest_at = panel["source_observed_at"].max()
    latest = panel.loc[panel["source_observed_at"].eq(latest_at)]
    return {
        row.metric: {
            "value": float(row.value),
            "unit": row.source_reported_unit,
            "source_observed_at": str(row.source_observed_at),
            "source_block_height": int(row.source_block_height),
        }
        for row in latest.itertuples(index=False)
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_dashboard()
    panel = snapshot_panel(rows)
    result = {
        "dashboard_rows": int(len(rows)),
        "coverage_gate": coverage_gate(panel),
        "latest_metrics": latest_metrics(panel),
        "claim_boundary": (
            "H61 reports only source-defined public Akash aggregate lease, GPU-state, and "
            "spend metrics. It does not identify workload completion, GPU-hours, model-specific "
            "capacity, physical-GPU inventory, utilization, a clearing price, provider revenue, "
            "routing allocation, welfare, or causal demand."
        ),
    }
    save(panel, out_dir, "h61_akash_dashboard")
    save_json(result, out_dir, "h61_summary")
    return result
