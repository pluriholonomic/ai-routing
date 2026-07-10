"""H51 — aggregate Livepeer Gateway routing-adjustment control.

This is an external control for a decentralized Gateway with publicly observed
aggregate *routing adjustments*. It does not identify the selected
orchestrator, model, price, request value, delivered work, or an LLM-router
allocation. The pre-specified panel asks only whether the public rate of
Gateway swaps co-moves with a public in-flight reuse state, after region fixed
effects. That association is descriptive and power-gated.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

MIN_RUNS = 1_000
MIN_DAYS = 7
MIN_REGIONS = 2
PANEL_COLUMNS = [
    "run_ts",
    "capture_run_ts",
    "source_observed_at",
    "dt",
    "region",
    "rolling_window_minutes",
    "swap_events",
    "reuse_events",
    "inflight_reuse_events",
    "decision_events",
    "switch_share",
    "inflight_reuse_share",
]


def load_metrics() -> pd.DataFrame:
    glob = data.table_glob("livepeer_gateway_metrics")
    required = {
        "run_ts",
        "dt",
        "source",
        "region",
        "rolling_window_minutes",
        "swap_events",
        "reuse_events",
        "inflight_reuse_events",
    }
    try:
        schema = data.q(f"describe select * from read_parquet('{glob}', union_by_name=true)").df()
        if not required.issubset(set(schema["column_name"])):
            return pd.DataFrame(columns=PANEL_COLUMNS)
        observation_column = (
            "cast(source_observed_at as varchar)"
            if "source_observed_at" in set(schema["column_name"])
            else "cast(NULL as varchar)"
        )
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   {observation_column} as source_observed_at,
                   cast(dt as varchar) as dt,
                   cast(region as varchar) as region,
                   rolling_window_minutes, swap_events, reuse_events,
                   inflight_reuse_events
            from read_parquet('{glob}', union_by_name=true)
            where source = 'livepeer_gateway'
            """
        ).df()
    except Exception as exc:
        log.info("H51 Livepeer Gateway metrics unavailable: %s", exc)
        return pd.DataFrame(columns=PANEL_COLUMNS)


def decision_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Build a one-row-per-Gateway-region aggregate adjustment panel."""
    if rows.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    panel = rows.copy()
    panel["capture_run_ts"] = panel["run_ts"]
    source_observed = (
        pd.to_datetime(panel["source_observed_at"], utc=True, errors="coerce")
        if "source_observed_at" in panel
        else pd.Series(pd.NaT, index=panel.index, dtype="datetime64[ns, UTC]")
    )
    captured_at = pd.to_datetime(panel["run_ts"], utc=True, errors="coerce")
    effective_at = source_observed.fillna(captured_at)
    panel = panel.loc[effective_at.notna()].copy()
    effective_at = effective_at.loc[panel.index]
    panel["run_ts"] = effective_at.dt.strftime("%Y%m%dT%H%M%SZ")
    panel["source_observed_at"] = effective_at.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    panel["dt"] = effective_at.dt.strftime("%Y-%m-%d")
    for column in ("swap_events", "reuse_events", "inflight_reuse_events"):
        panel[column] = pd.to_numeric(panel[column], errors="coerce").fillna(0).clip(lower=0)
    panel["inflight_reuse_events"] = panel[["inflight_reuse_events", "reuse_events"]].min(axis=1)
    panel["decision_events"] = panel["swap_events"] + panel["reuse_events"]
    panel["switch_share"] = panel["swap_events"] / panel["decision_events"].where(
        panel["decision_events"] > 0
    )
    panel["inflight_reuse_share"] = panel["inflight_reuse_events"] / panel["reuse_events"].where(
        panel["reuse_events"] > 0
    )
    return (
        panel.sort_values(["run_ts", "capture_run_ts"])
        .drop_duplicates(["run_ts", "region"], keep="last")
        .loc[:, PANEL_COLUMNS]
    )


def switch_response(panel: pd.DataFrame) -> dict | None:
    """Estimate the pre-specified descriptive association with cluster-robust SEs."""
    fit_data = panel.dropna(subset=["switch_share", "inflight_reuse_share"]).copy()
    fit_data = fit_data[fit_data["decision_events"] > 0]
    if fit_data["run_ts"].nunique() < 5 or fit_data["region"].nunique() < 2:
        return None
    model = smf.wls(
        "switch_share ~ inflight_reuse_share + C(region)",
        data=fit_data,
        weights=fit_data["decision_events"],
    ).fit(cov_type="cluster", cov_kwds={"groups": fit_data["run_ts"]})
    return {
        "coefficient_on_inflight_reuse_share": float(model.params["inflight_reuse_share"]),
        "std_error": float(model.bse["inflight_reuse_share"]),
        "p_value": float(model.pvalues["inflight_reuse_share"]),
        "n_region_windows": int(len(fit_data)),
        "n_snapshot_clusters": int(fit_data["run_ts"].nunique()),
        "specification": (
            "weighted linear probability association: swap share on in-flight reuse share and "
            "Gateway-region fixed effects; weights are observed aggregate decision messages and "
            "standard errors cluster by snapshot"
        ),
    }


def summarize(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "evidence_status": "not_identified",
            "n_snapshot_runs": 0,
            "claim_boundary": _claim_boundary(),
        }
    n_runs = int(panel["run_ts"].nunique())
    n_days = int(panel["dt"].nunique())
    n_regions = int(panel["region"].nunique())
    reasons = []
    if n_runs < MIN_RUNS:
        reasons.append(f"only {n_runs}/{MIN_RUNS} aggregate snapshots")
    if n_days < MIN_DAYS:
        reasons.append(f"only {n_days}/{MIN_DAYS} days")
    if n_regions < MIN_REGIONS:
        reasons.append(f"only {n_regions}/{MIN_REGIONS} regions")
    response = switch_response(panel) if not reasons else None
    return {
        "evidence_status": "external_control_descriptive" if not reasons else "power_gated",
        "n_snapshot_runs": n_runs,
        "n_region_windows": int(len(panel)),
        "n_days": n_days,
        "n_regions": n_regions,
        "median_switch_share": _median(panel["switch_share"]),
        "median_inflight_reuse_share": _median(panel["inflight_reuse_share"]),
        "power_gate": {
            "min_snapshot_runs": MIN_RUNS,
            "min_days": MIN_DAYS,
            "min_regions": MIN_REGIONS,
        },
        "gate_reasons": reasons,
        "switch_response": response,
        "claim_boundary": _claim_boundary(),
    }


def _median(values: pd.Series) -> float | None:
    value = values.median()
    return float(value) if pd.notna(value) else None


def _claim_boundary() -> str:
    return (
        "The source exposes only aggregate public Gateway log messages about swapping or "
        "reusing an orchestrator. It does not identify an orchestrator, user, stream, model, "
        "price, route share, completion, capacity, cost, or causal policy effect; it is an "
        "external decentralized-routing control, not OpenRouter evidence."
    )


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = decision_panel(load_metrics())
    save(panel, out_dir, "h51_livepeer_gateway_panel")
    result = summarize(panel)
    save_json(result, out_dir, "h51_summary")
    return result
