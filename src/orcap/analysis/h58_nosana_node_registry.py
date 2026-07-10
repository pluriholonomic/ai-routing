"""H58 — source-verified Nosana declared NodeAccount registry snapshots.

The public Solana program exposes a small registration header for NodeAccounts.
H58 only reports that source-bounded declared registry state after the source
ledger confirms the account count and parser count match. Registration is not
evidence that a node is live, accepting jobs, offering a particular GPU model,
or delivering capacity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h56_uniswap_tick_book import snapshot_key

PANEL_COLUMNS = ["run_ts", "dt", "snapshot_slot", "metric", "value", "n_nodes"]
MIN_SNAPSHOT_DAYS = 7
MIN_SNAPSHOTS = 20


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=PANEL_COLUMNS)


def _load(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def complete_registry_snapshot_manifests(source_runs: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Return source-run keys whose raw and parsed NodeAccount counts agree."""
    required = {"run_ts", "dt", "source", "status", "detail_json"}
    if source_runs.empty or not required.issubset(source_runs.columns):
        return {}
    manifests = {}
    candidates = source_runs[
        source_runs["source"].eq("nosana") & source_runs["status"].eq("success")
    ]
    for row in candidates.itertuples(index=False):
        try:
            detail = json.loads(row.detail_json)
            expected = int(detail["account_records_fetched"])
            written = int(detail["rows_written"]["nosana_node_registry"])
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            detail.get("query_succeeded") is not True
            or detail.get("registry_complete") is not True
            or expected <= 0
            or written != expected
        ):
            continue
        run_ts, dt = getattr(row, "run_ts", None), getattr(row, "dt", None)
        if run_ts is not None and dt is not None:
            manifests[snapshot_key(run_ts, dt)] = expected
    return manifests


def registry_panel(
    nodes: pd.DataFrame,
    manifests: dict[tuple[str, str], int],
) -> pd.DataFrame:
    """Summarize complete declared-profile snapshots without capacity claims."""
    required = {"run_ts", "dt", "participant_id"}
    if nodes.empty or not required.issubset(nodes.columns) or not manifests:
        return _empty()
    frame = nodes.copy()
    frame["_snapshot_key"] = [
        snapshot_key(run_ts, dt) for run_ts, dt in zip(frame["run_ts"], frame["dt"], strict=True)
    ]
    frame = frame.loc[frame["_snapshot_key"].isin(manifests)].copy()
    if frame.empty:
        return _empty()
    count = frame.groupby("_snapshot_key").size().to_dict()
    distinct = frame.groupby("_snapshot_key")["participant_id"].nunique().to_dict()
    complete_keys = {
        key
        for key, expected in manifests.items()
        if count.get(key) == expected == distinct.get(key)
    }
    frame = frame.loc[frame["_snapshot_key"].isin(complete_keys)].copy()
    if frame.empty:
        return _empty()
    for column in (
        "audited",
        "architecture_type",
        "country_code",
        "declared_cpu_cores",
        "declared_gpu_value",
        "declared_memory_gb",
        "declared_iops",
        "declared_storage_gb",
        "snapshot_slot",
    ):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    rows = []
    for key, group in frame.groupby(["run_ts", "dt", "snapshot_slot"], dropna=False):
        run_ts, dt, slot = key
        n_nodes = int(len(group))
        audited = group["audited"].dropna()

        def emit(
            metric: str,
            value: float | int | None,
            *,
            run_ts=run_ts,
            dt=dt,
            slot=slot,
            n_nodes=n_nodes,
        ) -> None:
            snapshot_slot = int(slot) if pd.notna(slot) else None
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "snapshot_slot": snapshot_slot,
                    "metric": metric,
                    "value": value,
                    "n_nodes": n_nodes,
                }
            )

        emit("registered_node_count", n_nodes)
        emit("audited_node_count", int((audited == 1).sum()) if not audited.empty else None)
        emit("audited_node_share", float((audited == 1).mean()) if not audited.empty else None)
        for column, metric, aggregation in (
            ("architecture_type", "distinct_declared_architecture_types", "nunique"),
            ("country_code", "distinct_declared_country_codes", "nunique"),
            ("declared_gpu_value", "distinct_declared_gpu_values", "nunique"),
            ("declared_cpu_cores", "sum_declared_cpu_cores", "sum"),
            ("declared_memory_gb", "sum_declared_memory_gb", "sum"),
            ("declared_storage_gb", "sum_declared_storage_gb", "sum"),
            ("declared_iops", "median_declared_iops", "median"),
        ):
            values = group[column].dropna()
            if values.empty:
                emit(metric, None)
            elif aggregation == "nunique":
                emit(metric, int(values.nunique()))
            elif aggregation == "sum":
                emit(metric, float(values.sum()))
            else:
                emit(metric, float(values.median()))
    return pd.DataFrame(rows, columns=PANEL_COLUMNS) if rows else _empty()


def coverage_gate(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "status": "not_identified",
            "snapshot_days": 0,
            "snapshots": 0,
            "minimum_snapshot_days": MIN_SNAPSHOT_DAYS,
            "minimum_snapshots": MIN_SNAPSHOTS,
        }
    snapshots = panel.loc[:, ["run_ts", "dt", "snapshot_slot"]].drop_duplicates()
    dates = sorted(str(value) for value in snapshots["dt"].dropna().unique())
    status = (
        "source_bounded_dynamic_panel_ready"
        if len(dates) >= MIN_SNAPSHOT_DAYS and len(snapshots) >= MIN_SNAPSHOTS
        else "power_gated"
    )
    return {
        "status": status,
        "snapshot_days": len(dates),
        "snapshots": int(len(snapshots)),
        "minimum_snapshot_days": MIN_SNAPSHOT_DAYS,
        "minimum_snapshots": MIN_SNAPSHOTS,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    nodes = _load("nosana_node_registry")
    source_runs = _load("source_runs")
    manifests = complete_registry_snapshot_manifests(source_runs)
    panel = registry_panel(nodes, manifests)
    gate = coverage_gate(panel)
    save(panel, out_dir, "h58_nosana_node_registry")
    summary = {
        "node_registry_rows": int(len(nodes)),
        "verified_complete_source_runs": len(manifests),
        "coverage_gate": gate,
        "claim_boundary": (
            "H58 reports only source-ledger-verified, on-chain declared Nosana NodeAccount "
            "profile fields. A registration is not node liveness, current availability, GPU "
            "model or count, utilization, a posted price, a job, delivered compute, or an "
            "LLM-routing allocation. Declared fields are not harmonized to other venues."
        ),
    }
    save_json(summary, out_dir, "h58_summary")
    return summary
