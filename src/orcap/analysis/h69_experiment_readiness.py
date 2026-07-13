"""H69 — auditable readiness ledger for the routing-mechanism experiments.

The ledger separates public quote coverage, realized owned-routing telemetry,
router aggregate flow, private ordering logs, and external comparators.  It is
not a hypothesis test: it makes a missing data requirement visible before an
analysis can be run or a claim can be promoted.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h67_quote_pulse import (
    annotate_surface,
    attach_reversion_paths,
    build_episode_events,
    build_paths,
    load_config,
    load_quote_surface,
)
from .h68_router_enforcement import derank_events, enforcement_panel, load_enforcement_rows

GATE_FILE = Path("config/experiment_gates.toml")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "experiment",
            "evidence_layer",
            "metric",
            "observed",
            "required",
            "status",
            "data_requirement",
            "permitted_claim_if_ready",
        ]
    )


def load_gates(path: Path = GATE_FILE) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load(sql: str) -> pd.DataFrame:
    try:
        return data.q(sql).df()
    except Exception:
        return pd.DataFrame()


def quote_metrics(rows: pd.DataFrame) -> dict:
    """Use H67's primary-scenario episode definition, not raw endpoint ticks."""
    if rows.empty:
        return {"span_hours": 0.0, "independent_cuts": 0, "snapshot_count": 0}
    config = load_config()
    surface = annotate_surface(rows)
    if surface.empty:
        return {"span_hours": 0.0, "independent_cuts": 0, "snapshot_count": 0}
    paths = attach_reversion_paths(build_paths(surface, config), config)
    events = build_episode_events(paths, config)
    snapshot_times = surface["ts"].drop_duplicates().sort_values()
    span = (
        (snapshot_times.max() - snapshot_times.min()).total_seconds() / 3600
        if len(snapshot_times) > 1
        else 0.0
    )
    return {
        "span_hours": float(span),
        "independent_cuts": int(len(events)),
        "snapshot_count": int(len(snapshot_times)),
    }


def telemetry_metrics() -> dict:
    attempts = _load_table("router_route_attempts")
    decisions = _load_table("router_decision_events")
    aggregates = _load_table("router_flow_aggregates")
    selected = _nonempty_count(attempts, "selected_provider")
    quote_linked = _nonempty_count(attempts, "quote_snapshot_id")
    aggregate_days = 0
    repricing_episodes = 0
    if not aggregates.empty:
        interval_start = pd.to_datetime(aggregates.get("interval_start"), utc=True, errors="coerce")
        aggregate_days = int(interval_start.dt.date.nunique())
        repricing_episodes = _nonempty_count(aggregates, "quote_or_capacity_action_at")
    arm_counts = (
        decisions.get("experiment_arm", pd.Series(dtype="object")).value_counts().to_dict()
        if not decisions.empty
        else {}
    )
    return {
        "selected_attempts": selected,
        "quote_linked_attempts": quote_linked,
        "decision_events": int(len(decisions)),
        "visible_arm_events": int(arm_counts.get("provider_visible", 0)),
        "blinded_arm_events": int(arm_counts.get("provider_blinded", 0)),
        "decoy_arm_events": int(arm_counts.get("decoy_signal", 0)),
        "aggregate_days": aggregate_days,
        "repricing_episodes": repricing_episodes,
    }


def _load_table(table: str) -> pd.DataFrame:
    table_glob = data.table_glob(table)
    return _load(
        f"""
        select distinct *
        from read_parquet('{table_glob}', union_by_name = true)
        """
    )


def _nonempty_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame:
        return 0
    return int(frame[column].fillna("").astype(str).str.len().gt(0).sum())


def comparator_days() -> int:
    tables = ("akash_market_open_bids", "chutes_invocations", "livepeer_gateway_metrics")
    counts = []
    for table in tables:
        table_glob = data.table_glob(table)
        rows = _load(f"select distinct dt from read_parquet('{table_glob}', union_by_name = true)")
        if not rows.empty:
            counts.append(int(rows["dt"].nunique()))
    return min(counts) if counts else 0


def _status(observed: float, required: float) -> str:
    if observed <= 0:
        return "not_collected"
    return "ready" if observed >= required else "power_gated"


def _spec(
    experiment: str,
    evidence_layer: str,
    metric: str,
    observed: float,
    required: float,
    data_requirement: str,
    permitted_claim_if_ready: str,
) -> dict:
    return {
        "experiment": experiment,
        "evidence_layer": evidence_layer,
        "metric": metric,
        "observed": observed,
        "required": required,
        "status": _status(observed, required),
        "data_requirement": data_requirement,
        "permitted_claim_if_ready": permitted_claim_if_ready,
    }


def readiness_rows(
    quote: dict,
    enforcement_onsets: int,
    telemetry: dict,
    comparator_complete_days: int,
    gates: dict,
) -> pd.DataFrame:
    q = gates["quote_pulse"]
    realized = gates["realized_routing"]
    residual = gates["residual_flow"]
    access = gates["preselection_access"]
    comparators = gates["comparators"]
    return pd.DataFrame(
        [
            _spec(
                "H67 quote pulse",
                "public",
                "continuous quote-surface hours",
                quote["span_hours"],
                q["min_continuous_span_hours"],
                "five-minute endpoint quotes",
                "public quote-pulse/fade screen",
            ),
            _spec(
                "H67 quote pulse",
                "public",
                "independent >=5% contiguous cuts",
                quote["independent_cuts"],
                q["min_independent_cut_episodes"],
                "contiguous endpoint quote paths",
                "public quote-pulse/fade screen",
            ),
            _spec(
                "H68 enforcement",
                "public",
                "observed contiguous derank onsets",
                enforcement_onsets,
                gates["router_enforcement"]["min_derank_onsets"],
                "frontend enforcement states",
                "descriptive rate-limit/derank hazard",
            ),
            _spec(
                "H43 calibration",
                "owned realized",
                "attempts with selected provider",
                telemetry["selected_attempts"],
                realized["min_selected_attempts"],
                "payload-free owned route telemetry",
                "simulation-versus-owned-selection calibration",
            ),
            _spec(
                "H14 phantom liquidity",
                "owned realized",
                "quote-linked selected attempts",
                telemetry["quote_linked_attempts"],
                realized["min_quote_linked_attempts"],
                "owned attempts joined to quote snapshots",
                "owned fallback/admission contrast",
            ),
            _spec(
                "H42 stale quote",
                "owned realized",
                "quote-linked event opportunities",
                telemetry["quote_linked_attempts"],
                realized["min_stale_quote_episodes"],
                "matched quote episodes plus owned attempts",
                "owned stale-quote selection screen",
            ),
            _spec(
                "Residual-flow anticipation",
                "router aggregate",
                "complete flow days",
                telemetry["aggregate_days"],
                residual["min_complete_days"],
                "fixed-interval provider/model selected-flow aggregates",
                "out-of-sample residual-flow event study",
            ),
            _spec(
                "Residual-flow anticipation",
                "router aggregate",
                "repricing episodes with aggregates",
                telemetry["repricing_episodes"],
                residual["min_repricing_episodes"],
                "aggregate flow plus timestamped quote/capacity actions",
                "out-of-sample residual-flow event study",
            ),
            _spec(
                "Pre-selection access",
                "private signal experiment",
                "provider-visible assignments",
                telemetry["visible_arm_events"],
                access["min_events_per_randomized_arm"],
                "timestamped router decision export",
                "eligible pre-selection signal contrast after manifest audit",
            ),
            _spec(
                "Pre-selection access",
                "private signal experiment",
                "provider-blinded assignments",
                telemetry["blinded_arm_events"],
                access["min_events_per_randomized_arm"],
                "timestamped router decision export",
                "eligible pre-selection signal contrast after manifest audit",
            ),
            _spec(
                "Pre-selection access",
                "private signal experiment",
                "decoy-signal assignments",
                telemetry["decoy_arm_events"],
                access["min_events_per_randomized_arm"],
                "timestamped router decision export",
                "eligible pre-selection signal contrast after manifest audit",
            ),
            _spec(
                "Observable comparators",
                "external control",
                "common complete days",
                comparator_complete_days,
                comparators["min_complete_days_per_venue"],
                "source-specific finalized or aggregate control panels",
                "cross-venue methodological control only",
            ),
        ]
    )


def summarize(ledger: pd.DataFrame, quote: dict, telemetry: dict) -> dict:
    ready = int((ledger["status"] == "ready").sum()) if not ledger.empty else 0
    power_gated = int((ledger["status"] == "power_gated").sum()) if not ledger.empty else 0
    not_collected = int((ledger["status"] == "not_collected").sum()) if not ledger.empty else 0
    return {
        "n_ready_gates": ready,
        "n_power_gated_gates": power_gated,
        "n_not_collected_gates": not_collected,
        "quote_surface": quote,
        "private_telemetry": telemetry,
        "claim_boundary": (
            "Readiness is a data-coverage result, not evidence for any routing mechanism. "
            "Public quote, enforcement, or comparator gates cannot identify selected provider, "
            "private order flow, provider profit, or literal front-running."
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    gates = load_gates()
    quote = quote_metrics(load_quote_surface())
    enforcement = enforcement_panel(load_enforcement_rows())
    onsets = int(len(derank_events(enforcement).query("event_type == 'derank_onset'")))
    telemetry = telemetry_metrics()
    ledger = readiness_rows(quote, onsets, telemetry, comparator_days(), gates)
    save(ledger if not ledger.empty else _empty(), out_dir, "h69_experiment_readiness")
    summary = summarize(ledger, quote, telemetry)
    save_json(summary, out_dir, "h69_summary")
    return summary
