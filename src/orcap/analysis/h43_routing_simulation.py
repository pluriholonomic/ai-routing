"""H43 — Does the public quote surface imply changing router allocations?

H43 is a zero-spend, pre-execution test.  It compares the simulated provider
shares produced from consecutive public endpoint snapshots.  A non-zero
change means that the documented price-based routing rule would have allocated
the fixed workload to providers differently, conditional on public quotes.
It does *not* show actual routed flow or the router's private health state.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

MIN_SNAPSHOTS_FOR_24H_READ = 80
MIN_SPAN_HOURS_FOR_24H_READ = 23.0
MIN_TRANSITIONS_FOR_24H_READ = 48
CHANGE_TOLERANCE = 1e-10


def _empty_changes() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "panel_id",
            "model_id",
            "scenario",
            "previous_run_ts",
            "run_ts",
            "elapsed_minutes",
            "n_previous_providers",
            "n_current_providers",
            "eligible_set_changed",
            "quote_changed",
            "total_variation_distance",
            "simulated_share_changed",
            "top_provider_before",
            "top_provider_after",
            "top_provider_changed",
        ]
    )


def load_simulations() -> pd.DataFrame:
    try:
        rows = data.q(
            f"""
            select run_ts, dt, panel_id, model_id, scenario, provider_name,
                   expected_quote_usd, simulated_route_share
            from read_parquet('{data.table_glob("routing_simulation")}')
            """
        ).df()
    except Exception:
        return pd.DataFrame()
    if rows.empty:
        return rows
    rows["ts"] = pd.to_datetime(rows["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    rows["expected_quote_usd"] = pd.to_numeric(rows["expected_quote_usd"], errors="coerce")
    rows["simulated_route_share"] = pd.to_numeric(
        rows["simulated_route_share"], errors="coerce"
    )
    return rows.dropna(subset=["ts", "provider_name", "simulated_route_share"]).copy()


def transition_panel(rows: pd.DataFrame, max_gap_minutes: int = 30) -> pd.DataFrame:
    """Compute route-surface changes from each contiguous panel transition."""
    if rows.empty:
        return _empty_changes()
    records: list[dict] = []
    group_cols = ["panel_id", "model_id", "scenario"]
    for group, frame in rows.groupby(group_cols, dropna=False, sort=False):
        snapshots = {
            ts: snapshot.set_index("provider_name")
            for ts, snapshot in frame.groupby("ts", sort=True)
        }
        ordered = sorted(snapshots)
        for before_ts, after_ts in zip(ordered, ordered[1:], strict=False):
            elapsed_minutes = (after_ts - before_ts).total_seconds() / 60
            if elapsed_minutes > max_gap_minutes:
                continue
            before, after = snapshots[before_ts], snapshots[after_ts]
            providers = before.index.union(after.index)
            before_share = before["simulated_route_share"].reindex(providers, fill_value=0.0)
            after_share = after["simulated_route_share"].reindex(providers, fill_value=0.0)
            before_quote = before["expected_quote_usd"].reindex(providers)
            after_quote = after["expected_quote_usd"].reindex(providers)
            tvd = 0.5 * float(np.abs(after_share - before_share).sum())
            provider_set_changed = set(before.index) != set(after.index)
            quotes_changed = provider_set_changed or bool(
                (np.abs(after_quote - before_quote) > CHANGE_TOLERANCE).fillna(True).any()
            )
            top_before = before_share.sort_values(ascending=False).index[0]
            top_after = after_share.sort_values(ascending=False).index[0]
            panel_id, model_id, scenario = group
            records.append(
                {
                    "panel_id": panel_id,
                    "model_id": model_id,
                    "scenario": scenario,
                    "previous_run_ts": before_ts.strftime("%Y%m%dT%H%M%SZ"),
                    "run_ts": after_ts.strftime("%Y%m%dT%H%M%SZ"),
                    "elapsed_minutes": elapsed_minutes,
                    "n_previous_providers": len(before.index),
                    "n_current_providers": len(after.index),
                    "eligible_set_changed": provider_set_changed,
                    "quote_changed": quotes_changed,
                    "total_variation_distance": tvd,
                    "simulated_share_changed": tvd > CHANGE_TOLERANCE,
                    "top_provider_before": top_before,
                    "top_provider_after": top_after,
                    "top_provider_changed": top_before != top_after,
                }
            )
    return pd.DataFrame(records) if records else _empty_changes()


def summarize(rows: pd.DataFrame, changes: pd.DataFrame) -> dict:
    n_snapshots = int(rows["run_ts"].nunique()) if not rows.empty else 0
    n_paths = int(rows.groupby(["model_id", "scenario"]).ngroups) if not rows.empty else 0
    n_transitions = int(len(changes))
    n_changed = int(changes["simulated_share_changed"].sum()) if not changes.empty else 0
    n_top_changed = int(changes["top_provider_changed"].sum()) if not changes.empty else 0
    span_hours = (
        (rows["ts"].max() - rows["ts"].min()).total_seconds() / 3600 if n_snapshots >= 2 else 0.0
    )
    enough = (
        n_snapshots >= MIN_SNAPSHOTS_FOR_24H_READ
        and span_hours >= MIN_SPAN_HOURS_FOR_24H_READ
        and n_transitions >= MIN_TRANSITIONS_FOR_24H_READ
    )
    if not enough:
        verdict = "insufficient_24h_coverage"
    elif n_changed:
        verdict = "public_quote_surface_changes_simulated_route"
    else:
        verdict = "no_public_quote_induced_route_change_observed"
    return {
        "verdict": verdict,
        "claim_boundary": (
            "A positive result means public quote/capability changes alter the documented "
            "inverse-square allocation proxy. It does not identify realized routing, exact "
            "live eligibility, failed attempts, or market-wide provider flow."
        ),
        "coverage_gate": {
            "min_snapshots_for_24h_read": MIN_SNAPSHOTS_FOR_24H_READ,
            "min_span_hours_for_24h_read": MIN_SPAN_HOURS_FOR_24H_READ,
            "min_transitions_for_24h_read": MIN_TRANSITIONS_FOR_24H_READ,
            "passed": enough,
        },
        "n_snapshots": n_snapshots,
        "observed_span_hours": span_hours,
        "n_model_scenario_paths": n_paths,
        "n_contiguous_transitions": n_transitions,
        "n_simulated_share_changes": n_changed,
        "share_of_transitions_changed": n_changed / n_transitions if n_transitions else None,
        "n_top_provider_changes": n_top_changed,
        "median_total_variation_distance": (
            float(changes["total_variation_distance"].median()) if n_transitions else None
        ),
        "p95_total_variation_distance": (
            float(changes["total_variation_distance"].quantile(0.95)) if n_transitions else None
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_simulations()
    changes = transition_panel(rows)
    save(rows.drop(columns="ts", errors="ignore"), out_dir, "h43_routing_simulation_panel")
    save(changes, out_dir, "h43_routing_simulation_changes")
    result = summarize(rows, changes)
    save_json(result, out_dir, "h43_routing_simulation_summary")
    return result
