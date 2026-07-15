"""H86b — post-support-audit canonical model identifier bridge.

H86 remains the frozen exact-key analysis and has zero support. H86b connects
OpenRouter's exact API model ``id`` to its official ``canonical_slug`` using
pre-request model snapshots. Provider identity remains exact. See the H86b
section of ``docs/h86-h87-capacity-state-execution-preregistration.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h82_enforcement_substitution import load_rows
from .h86_capacity_execution_bridge import (
    attach_public_state,
    legacy_pinned_attempts,
    plot_results,
    public_provider_states,
    risk_pairs,
    summarize,
)

MAX_MODEL_MAP_AGE_DAYS = 7


def canonicalize_attempt_models(
    attempts: pd.DataFrame, model_snapshots: pd.DataFrame
) -> pd.DataFrame:
    """Attach a pre-request, exact official id-to-canonical-slug mapping."""
    out = attempts.copy()
    out["route_model_id"] = out.get("model_id")
    out["model_mapping_status"] = "no_official_model_snapshot"
    out["model_mapping_snapshot_ts"] = pd.Series(
        pd.NaT, index=out.index, dtype="datetime64[ns, UTC]"
    )
    if out.empty or model_snapshots.empty:
        return out

    snapshots = model_snapshots.copy()
    snapshots["snapshot_ts"] = pd.to_datetime(
        snapshots.get("run_ts"), utc=True, errors="coerce"
    )
    snapshots = snapshots.dropna(subset=["id", "canonical_slug", "snapshot_ts"])
    lookup = {
        str(model_id): group.sort_values("snapshot_ts")
        for model_id, group in snapshots.groupby("id", sort=False)
    }
    observed = pd.to_datetime(out.get("observed_at"), utc=True, errors="coerce")
    out["_model_map_observed_ts"] = observed
    for index, row in out.iterrows():
        model_id = str(row.get("route_model_id"))
        current = row.get("_model_map_observed_ts")
        if pd.isna(current):
            out.at[index, "model_mapping_status"] = "invalid_attempt_time"
            continue
        candidates = lookup.get(model_id)
        if candidates is None:
            continue
        lower = current - pd.Timedelta(f"{MAX_MODEL_MAP_AGE_DAYS} days")
        window = candidates[
            candidates["snapshot_ts"].le(current) & candidates["snapshot_ts"].ge(lower)
        ]
        if window.empty:
            out.at[index, "model_mapping_status"] = "no_recent_prior_model_snapshot"
            continue
        canonical = window["canonical_slug"].dropna().astype(str).unique()
        if len(canonical) != 1:
            out.at[index, "model_mapping_status"] = "conflicting_recent_canonical_slug"
            continue
        latest = window.iloc[-1]
        out.at[index, "model_id"] = canonical[0]
        out.at[index, "model_mapping_status"] = "mapped_exact_official_snapshot"
        out.at[index, "model_mapping_snapshot_ts"] = latest["snapshot_ts"]
    return out.drop(columns="_model_map_observed_ts")


def analyze(
    attempts: pd.DataFrame,
    public_rows: pd.DataFrame,
    model_snapshots: pd.DataFrame,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    mapped = canonicalize_attempt_models(attempts, model_snapshots)
    pinned = legacy_pinned_attempts(mapped)
    states = public_provider_states(public_rows)
    joined = attach_public_state(pinned, states)
    pairs = risk_pairs(joined)
    summary = summarize(joined, pairs)
    mapping_counts = pinned["model_mapping_status"].value_counts(dropna=False).to_dict()
    summary["evidence_status"] = "post_support_audit_canonical_id_bridge"
    summary["study"] = "H86b"
    summary["support"]["model_mapping_status_counts"] = {
        str(key): int(value) for key, value in mapping_counts.items()
    }
    summary["support"]["mapped_legacy_pinned_attempts"] = int(
        pinned["model_mapping_status"].eq("mapped_exact_official_snapshot").sum()
    )
    summary["claim_boundary"] = (
        "H86b is a retrospective sensitivity introduced after H86's schema-support "
        "failure. It uses only exact official pre-request model mappings and exact "
        "provider names. It is not confirmatory and does not identify the causal effect "
        "of capacity, provider intent, front-running, other-user routing, or welfare."
    )
    if out_dir is not None:
        save(states, out_dir, "h86b_public_provider_states")
        save(joined, out_dir, "h86b_legacy_probe_state_join")
        save(pairs, out_dir, "h86b_capacity_risk_pairs")
        save_json(summary, out_dir, "h86b_summary")
        plot_results(
            pairs,
            summary,
            out_dir,
            prefix="h86b",
            title="H86b official-ID capacity state and pinned execution",
        )
    return summary


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    attempts = data.q(
        f"""
        select *
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        """
    ).df()
    models = data.q(
        f"""
        select run_ts, id, canonical_slug
        from {data.models_snapshots()}
        """
    ).df()
    return analyze(attempts, load_rows(), models, out_dir)
