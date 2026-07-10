"""H62 — source-bounded Akash GPU-provider lease-activity history.

The panel uses only the public Console's aggregate active-lease graph for
providers that are in the collector's *current* live-GPU universe. It is a
provider-activity control, not a historical GPU-capacity census or workload
execution record.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

HISTORY_METRIC = "source_reported_provider_active_lease_count_history"
MIN_DAYS = 30
MIN_PROVIDERS = 10
MIN_PROVIDER_DAYS = 20
HISTORY_COLUMNS = [
    "provider_id",
    "source_bucket_at",
    "active_leases",
    "latest_run_ts",
    "n_revisions",
]
DAILY_COLUMNS = [
    "source_day",
    "providers_observed",
    "total_source_reported_active_leases",
    "top_provider_lease_share",
    "provider_lease_hhi",
]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def load_provider_aggregates() -> pd.DataFrame:
    """Load only the aggregate provider-history source table."""
    required = {
        "run_ts",
        "source",
        "provider_id",
        "observation_type",
        "source_bucket_at",
        "metric",
        "value",
    }
    try:
        glob = data.table_glob("akash_provider_aggregates")
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return _empty(HISTORY_COLUMNS)
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(provider_id as varchar) as provider_id,
                   cast(observation_type as varchar) as observation_type,
                   cast(source_bucket_at as varchar) as source_bucket_at,
                   cast(metric as varchar) as metric,
                   value
            from read_parquet('{glob}', union_by_name=true)
            where source = 'akash_provider_aggregates'
            """
        ).df()
    except Exception:
        return _empty(HISTORY_COLUMNS)


def latest_provider_history(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest retained source revision for each provider/timestamp."""
    required = {
        "run_ts",
        "provider_id",
        "observation_type",
        "source_bucket_at",
        "metric",
        "value",
    }
    if rows.empty or not required.issubset(rows.columns):
        return _empty(HISTORY_COLUMNS)
    panel = rows.loc[
        rows["observation_type"].eq("source_reported_provider_history")
        & rows["metric"].eq(HISTORY_METRIC)
    ].copy()
    panel["captured_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    panel["source_bucket_at"] = pd.to_datetime(panel["source_bucket_at"], utc=True, errors="coerce")
    panel["value"] = pd.to_numeric(panel["value"], errors="coerce")
    panel = panel.dropna(subset=["captured_at", "provider_id", "source_bucket_at", "value"])
    panel = panel.loc[panel["value"] >= 0].copy()
    if panel.empty:
        return _empty(HISTORY_COLUMNS)
    keys = ["provider_id", "source_bucket_at"]
    revisions = panel.groupby(keys).size().rename("n_revisions").reset_index()
    latest = panel.sort_values("captured_at").drop_duplicates(keys, keep="last")
    latest = latest.merge(revisions, on=keys, how="inner", validate="one_to_one")
    latest = latest.rename(columns={"value": "active_leases", "run_ts": "latest_run_ts"})
    return latest.loc[:, HISTORY_COLUMNS].sort_values(["provider_id", "source_bucket_at"])


def daily_provider_panel(history: pd.DataFrame) -> pd.DataFrame:
    """Aggregate one latest source history point per provider and UTC day."""
    if history.empty or not set(HISTORY_COLUMNS).issubset(history.columns):
        return _empty(DAILY_COLUMNS)
    panel = history.copy()
    panel["source_bucket_at"] = pd.to_datetime(panel["source_bucket_at"], utc=True, errors="coerce")
    panel["active_leases"] = pd.to_numeric(panel["active_leases"], errors="coerce")
    panel = panel.dropna(subset=["provider_id", "source_bucket_at", "active_leases"])
    panel = panel.loc[panel["active_leases"] >= 0].copy()
    if panel.empty:
        return _empty(DAILY_COLUMNS)
    panel["source_day"] = panel["source_bucket_at"].dt.date.astype(str)
    panel = panel.sort_values("source_bucket_at").drop_duplicates(
        ["provider_id", "source_day"], keep="last"
    )
    rows = []
    for source_day, group in panel.groupby("source_day", sort=True):
        total = float(group["active_leases"].sum())
        shares = group["active_leases"] / total if total > 0 else pd.Series(dtype="float64")
        rows.append(
            {
                "source_day": source_day,
                "providers_observed": int(group["provider_id"].nunique()),
                "total_source_reported_active_leases": total,
                "top_provider_lease_share": float(shares.max()) if not shares.empty else None,
                "provider_lease_hhi": float((shares**2).sum()) if not shares.empty else None,
            }
        )
    return pd.DataFrame(rows, columns=DAILY_COLUMNS).sort_values("source_day")


def coverage_gate(history: pd.DataFrame, daily: pd.DataFrame) -> dict:
    if history.empty or daily.empty:
        return {
            "status": "not_identified",
            "source_history_days": 0,
            "providers_observed": 0,
            "providers_with_minimum_days": 0,
            "minimum_days": MIN_DAYS,
            "minimum_providers": MIN_PROVIDERS,
            "minimum_provider_days": MIN_PROVIDER_DAYS,
        }
    provider_days = history.copy()
    provider_days["source_bucket_at"] = pd.to_datetime(
        provider_days["source_bucket_at"], utc=True, errors="coerce"
    )
    provider_days["source_day"] = provider_days["source_bucket_at"].dt.date
    counts = provider_days.groupby("provider_id")["source_day"].nunique()
    days = int(len(daily))
    providers = int(history["provider_id"].nunique())
    eligible = int((counts >= MIN_PROVIDER_DAYS).sum())
    reasons = []
    if days < MIN_DAYS:
        reasons.append(f"only {days}/{MIN_DAYS} source-history days")
    if providers < MIN_PROVIDERS:
        reasons.append(f"only {providers}/{MIN_PROVIDERS} providers")
    if eligible < MIN_PROVIDERS:
        reasons.append(
            f"only {eligible}/{MIN_PROVIDERS} providers with {MIN_PROVIDER_DAYS} "
            "source-history days"
        )
    return {
        "status": "source_bounded_provider_history_ready" if not reasons else "power_gated",
        "source_history_days": days,
        "providers_observed": providers,
        "providers_with_minimum_days": eligible,
        "minimum_days": MIN_DAYS,
        "minimum_providers": MIN_PROVIDERS,
        "minimum_provider_days": MIN_PROVIDER_DAYS,
        "gate_reasons": reasons,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_provider_aggregates()
    history = latest_provider_history(rows)
    daily = daily_provider_panel(history)
    result = {
        "provider_aggregate_rows": int(len(rows)),
        "coverage_gate": coverage_gate(history, daily),
        "claim_boundary": (
            "H62 reports only public Akash Console source-defined active-lease history for the "
            "collector's current live-GPU-provider universe. It does not identify historical GPU "
            "capacity, tenant/workload activity, completed jobs, GPU-hours, utilization, price, "
            "provider profit, routing allocation, welfare, or causal demand."
        ),
    }
    save(history, out_dir, "h62_akash_provider_lease_history")
    save(daily, out_dir, "h62_akash_provider_daily")
    save_json(result, out_dir, "h62_summary")
    return result
