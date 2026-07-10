"""H53 — source-defined Chutes invocation growth and deployment configuration.

Chutes publishes a cumulative invocation counter per public chute. This module
first-differences only adjacent, plausibly hourly observations and keeps the
source's active configured-GPU field separate. It measures a public counter
change, not tokens, successful completions, unique users, revenue, capacity,
or GPU utilization.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

MAX_INTERVAL_HOURS = 3.0
MIN_DELTAS = 250
MIN_DAYS = 7
MIN_CHUTES = 5
PANEL_COLUMNS = [
    "run_ts",
    "dt",
    "participant_id",
    "resource_id",
    "previous_run_ts",
    "elapsed_hours",
    "cumulative_invocations",
    "delta_invocations",
    "invocation_rate_per_hour",
    "active_configured_gpus",
    "configured_concurrency",
    "estimated_deployment_usd_hour",
    "invocations_per_active_configured_gpu_hour",
]


def load_chutes_metrics() -> pd.DataFrame:
    """Load only the public fields required for a bounded counter panel."""
    glob = data.table_glob("market_capacity")
    required = {
        "run_ts",
        "dt",
        "source",
        "participant_id",
        "resource_id",
        "cumulative_invocations",
    }
    try:
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return pd.DataFrame(columns=PANEL_COLUMNS)
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(dt as varchar) as dt,
                   cast(participant_id as varchar) as participant_id,
                   cast(resource_id as varchar) as resource_id,
                   cumulative_invocations,
                   active_instances,
                   total as active_configured_gpus,
                   configured_concurrency,
                   estimated_deployment_usd_hour
            from read_parquet('{glob}', union_by_name=true)
            where source = 'chutes'
            """
        ).df()
    except Exception as exc:
        log.info("H53 Chutes metrics unavailable: %s", exc)
        return pd.DataFrame(columns=PANEL_COLUMNS)


def invocation_panel(rows: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Difference monotone adjacent counters without bridging snapshot gaps."""
    diagnostics = {"counter_resets": 0, "interval_rejections": 0}
    if rows.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS), diagnostics
    required = {
        "run_ts",
        "dt",
        "participant_id",
        "resource_id",
        "cumulative_invocations",
    }
    if not required.issubset(rows):
        return pd.DataFrame(columns=PANEL_COLUMNS), diagnostics
    panel = rows.copy()
    panel["observed_at"] = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    for column in (
        "cumulative_invocations",
        "active_configured_gpus",
        "configured_concurrency",
        "estimated_deployment_usd_hour",
    ):
        panel[column] = pd.to_numeric(panel.get(column), errors="coerce")
    panel = panel.dropna(
        subset=["observed_at", "participant_id", "resource_id", "cumulative_invocations"]
    )
    panel = panel[panel["cumulative_invocations"] >= 0]
    panel = panel.sort_values("observed_at").drop_duplicates(
        ["participant_id", "resource_id", "run_ts"], keep="last"
    )
    group_columns = ["participant_id", "resource_id"]
    panel["previous_run_ts"] = panel.groupby(group_columns)["run_ts"].shift()
    panel["previous_observed_at"] = panel.groupby(group_columns)["observed_at"].shift()
    panel["previous_cumulative_invocations"] = panel.groupby(group_columns)[
        "cumulative_invocations"
    ].shift()
    panel["elapsed_hours"] = (
        panel["observed_at"] - panel["previous_observed_at"]
    ).dt.total_seconds() / 3600
    panel["delta_invocations"] = (
        panel["cumulative_invocations"] - panel["previous_cumulative_invocations"]
    )
    has_predecessor = panel["previous_observed_at"].notna()
    diagnostics["counter_resets"] = int(
        (has_predecessor & (panel["delta_invocations"] < 0)).sum()
    )
    valid_interval = panel["elapsed_hours"].between(0, MAX_INTERVAL_HOURS, inclusive="both")
    diagnostics["interval_rejections"] = int((has_predecessor & ~valid_interval).sum())
    panel = panel[has_predecessor & valid_interval & (panel["delta_invocations"] >= 0)].copy()
    panel["invocation_rate_per_hour"] = panel["delta_invocations"] / panel["elapsed_hours"]
    panel["invocations_per_active_configured_gpu_hour"] = (
        panel["invocation_rate_per_hour"] / panel["active_configured_gpus"].where(
            panel["active_configured_gpus"] > 0
        )
    )
    return panel.loc[:, PANEL_COLUMNS].sort_values(
        ["run_ts", "participant_id", "resource_id"]
    ), diagnostics


def summarize(panel: pd.DataFrame, diagnostics: dict[str, int]) -> dict:
    if panel.empty:
        return {
            "evidence_status": "not_identified",
            "n_valid_deltas": 0,
            "diagnostics": diagnostics,
            "claim_boundary": _claim_boundary(),
        }
    n_deltas = int(len(panel))
    n_days = int(panel["dt"].nunique())
    n_chutes = int(panel["participant_id"].nunique())
    reasons = []
    if n_deltas < MIN_DELTAS:
        reasons.append(f"only {n_deltas}/{MIN_DELTAS} adjacent counter deltas")
    if n_days < MIN_DAYS:
        reasons.append(f"only {n_days}/{MIN_DAYS} days")
    if n_chutes < MIN_CHUTES:
        reasons.append(f"only {n_chutes}/{MIN_CHUTES} chutes")
    return {
        "evidence_status": "source_bounded_descriptive" if not reasons else "power_gated",
        "n_valid_deltas": n_deltas,
        "n_snapshot_runs": int(panel["run_ts"].nunique()),
        "n_days": n_days,
        "n_chutes": n_chutes,
        "median_invocation_rate_per_hour": _median(panel["invocation_rate_per_hour"]),
        "median_invocations_per_active_configured_gpu_hour": _median(
            panel["invocations_per_active_configured_gpu_hour"]
        ),
        "power_gate": {
            "min_adjacent_deltas": MIN_DELTAS,
            "min_days": MIN_DAYS,
            "min_chutes": MIN_CHUTES,
            "max_interval_hours": MAX_INTERVAL_HOURS,
        },
        "gate_reasons": reasons,
        "diagnostics": diagnostics,
        "claim_boundary": _claim_boundary(),
    }


def _median(values: pd.Series) -> float | None:
    value = values.median()
    return float(value) if pd.notna(value) else None


def _claim_boundary() -> str:
    return (
        "This panel first-differences Chutes's public, source-defined cumulative invocation "
        "counter over adjacent snapshots. It is not a count of successful completions, tokens, "
        "unique users, revenue, market-wide demand, GPU utilization, available capacity, or a "
        "causal demand/supply estimate. Active configured GPUs are a deployment-state denominator "
        "only, not observed GPU-hours consumed."
    )


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel, diagnostics = invocation_panel(load_chutes_metrics())
    save(panel, out_dir, "h53_chutes_invocation_panel")
    result = summarize(panel, diagnostics)
    save_json(result, out_dir, "h53_summary")
    return result
