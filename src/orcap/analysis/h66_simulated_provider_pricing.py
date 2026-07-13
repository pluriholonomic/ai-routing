"""H66 — public-quote-implied inference-provider pricing scorecard.

This module deliberately analyzes the *simulated* provider allocation surface,
not customer orders.  A public endpoint quote and the documented inverse-square
price rule identify mechanical price sensitivity and a counterfactual share,
but they do not identify realized selection, provider costs, margins, or output
quality.  The report is therefore a pricing-position and repricing-event
scorecard with explicit coverage gates, rather than a profit or welfare study.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

MIN_SNAPSHOTS = 80
MIN_SPAN_HOURS = 23.0
MAX_CONTIGUOUS_GAP_MINUTES = 30.0
CHANGE_TOLERANCE = 1e-10

GROUP_COLUMNS = ["panel_id", "model_id", "scenario"]
ROW_KEY_COLUMNS = [*GROUP_COLUMNS, "run_ts", "provider_name"]
OPERATIONAL_COLUMNS = ["uptime_last_30m", "p90_latency_ms", "p90_throughput"]


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            *ROW_KEY_COLUMNS,
            "dt",
            "ts",
            "expected_quote_usd",
            "simulated_route_share",
            "provider_quote_rank",
            "n_eligible_providers",
            *OPERATIONAL_COLUMNS,
            "performance_join_status",
            "quote_markup_to_cheapest",
            "simulated_top_provider",
            "simulated_unique_leader",
            "mechanical_own_price_elasticity",
            "marginal_share_change_per_1pct_quote_increase",
            "simulated_quote_revenue_index",
            "operational_metrics_complete",
            "public_operationally_dominated",
        ]
    )


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "pricing_event_id",
            "pricing_shock_id",
            "panel_id",
            "model_id",
            "scenario",
            "provider_name",
            "previous_run_ts",
            "run_ts",
            "elapsed_minutes",
            "candidate_set_stable",
            "quote_before_usd",
            "quote_after_usd",
            "quote_change_pct",
            "share_before",
            "share_after",
            "simulated_share_change",
            "price_cut",
            "price_increase",
            "simulated_top_before",
            "simulated_top_after",
            "became_simulated_top",
            "left_simulated_top",
            "simulated_unique_leader_before",
            "simulated_unique_leader_after",
            "became_simulated_unique_leader",
            "left_simulated_unique_leader",
        ]
    )


def _empty_scorecard() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "provider_name",
            "n_observations",
            "n_models",
            "n_scenarios",
            "median_quote_markup_to_cheapest",
            "median_simulated_route_share",
            "lowest_public_quote_rate",
            "simulated_top_rate",
            "simulated_unique_leader_rate",
            "mean_mechanical_own_price_elasticity",
            "operational_metrics_complete_rate",
            "public_operationally_dominated_rate",
            "n_quote_events",
            "n_unique_pricing_shocks",
            "n_price_cuts",
            "n_price_increases",
            "n_became_simulated_top_events",
            "n_became_simulated_unique_leader_events",
            "median_simulated_share_change_on_cut",
            "median_simulated_share_change_on_increase",
        ]
    )


def load_simulations() -> pd.DataFrame:
    """Load the public simulation table with all operational fields optional."""
    try:
        rows = data.q(
            f"""
            select distinct run_ts, dt, panel_id, model_id, scenario, provider_name,
                   expected_quote_usd, simulated_route_share, provider_quote_rank,
                   n_eligible_providers, uptime_last_30m, latency_last_30m,
                   throughput_last_30m, p90_latency_ms, p90_throughput,
                   performance_join_status
            from read_parquet('{data.table_glob("routing_simulation")}', union_by_name = true)
            """
        ).df()
    except Exception:
        try:
            rows = data.q(
                f"""
                select distinct run_ts, dt, panel_id, model_id, scenario, provider_name,
                       expected_quote_usd, simulated_route_share, provider_quote_rank,
                       n_eligible_providers, uptime_last_30m, latency_last_30m,
                       throughput_last_30m
                from read_parquet('{data.table_glob("routing_simulation")}', union_by_name = true)
                """
            ).df()
        except Exception:
            return pd.DataFrame()
    return attach_public_performance(rows, *_load_public_performance())


def _load_public_performance() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the public model map and hot-model performance feed when available."""
    try:
        model_map = data.q(
            f"""
            select run_ts, id as model_id, canonical_slug
            from {data.models_snapshots()}
            where canonical_slug is not null
            """
        ).df()
        stats = data.q(
            f"""
            select run_ts, model_permaslug, provider_name, p90_latency_ms, p90_throughput
            from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name = true)
            """
        ).df()
    except Exception:
        return pd.DataFrame(), pd.DataFrame()
    return model_map, stats


def attach_public_performance(
    rows: pd.DataFrame, model_map: pd.DataFrame, stats: pd.DataFrame
) -> pd.DataFrame:
    """Fill missing performance fields through an exact historical public join.

    This lets existing snapshots use the already-captured frontend stats table.
    Both model mapping and provider stats must be one-to-one at the capture
    timestamp; ambiguous rows stay missing instead of being expanded or guessed.
    """
    frame = rows.copy()
    for column in ["p90_latency_ms", "p90_throughput"]:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "performance_join_status" not in frame:
        frame["performance_join_status"] = pd.NA
    required_map = {"run_ts", "model_id", "canonical_slug"}
    required_stats = {
        "run_ts",
        "model_permaslug",
        "provider_name",
        "p90_latency_ms",
        "p90_throughput",
    }
    if frame.empty or not required_map.issubset(model_map) or not required_stats.issubset(stats):
        return frame
    mapping = (
        model_map.loc[:, ["run_ts", "model_id", "canonical_slug"]]
        .dropna()
        .drop_duplicates()
        .copy()
    )
    mapping = mapping.loc[~mapping.duplicated(["run_ts", "model_id"], keep=False)]
    performance = stats.loc[
        :, ["run_ts", "model_permaslug", "provider_name", "p90_latency_ms", "p90_throughput"]
    ].drop_duplicates().copy()
    performance = performance.loc[
        ~performance.duplicated(["run_ts", "model_permaslug", "provider_name"], keep=False)
    ].rename(
        columns={
            "provider_name": "stats_provider_name",
            "p90_latency_ms": "stats_p90_latency_ms",
            "p90_throughput": "stats_p90_throughput",
        }
    )
    joined = frame.merge(mapping, on=["run_ts", "model_id"], how="left", validate="many_to_one")
    joined = joined.merge(
        performance,
        left_on=["run_ts", "canonical_slug", "provider_name"],
        right_on=["run_ts", "model_permaslug", "stats_provider_name"],
        how="left",
        validate="many_to_one",
    )
    matched = joined["stats_provider_name"].notna()
    for destination, source in [
        ("p90_latency_ms", "stats_p90_latency_ms"),
        ("p90_throughput", "stats_p90_throughput"),
    ]:
        joined[destination] = joined[destination].combine_first(joined[source])
    joined.loc[
        joined["performance_join_status"].isna() & matched,
        "performance_join_status",
    ] = "analysis_exact_canonical_model_provider"
    joined.loc[
        joined["performance_join_status"].isna() & ~matched,
        "performance_join_status",
    ] = "no_exact_public_provider_stats"
    return joined.drop(
        columns=[
            "canonical_slug",
            "model_permaslug",
            "stats_provider_name",
            "stats_p90_latency_ms",
            "stats_p90_throughput",
        ],
        errors="ignore",
    )


def _coerce(rows: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Validate public rows and return the duplicate count without hiding it."""
    if rows.empty:
        return pd.DataFrame(), 0
    frame = rows.copy()
    required = {
        "run_ts",
        "panel_id",
        "model_id",
        "scenario",
        "provider_name",
        "expected_quote_usd",
        "simulated_route_share",
    }
    if not required.issubset(frame.columns):
        return pd.DataFrame(), 0
    for column in [
        "expected_quote_usd",
        "simulated_route_share",
        "provider_quote_rank",
        "n_eligible_providers",
        *OPERATIONAL_COLUMNS,
    ]:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "dt" not in frame:
        frame["dt"] = pd.NA
    if "performance_join_status" not in frame:
        frame["performance_join_status"] = pd.NA
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame = frame.dropna(
        subset=[
            "ts",
            "panel_id",
            "model_id",
            "scenario",
            "provider_name",
            "expected_quote_usd",
            "simulated_route_share",
        ]
    ).copy()
    frame = frame[(frame["expected_quote_usd"] > 0) & (frame["simulated_route_share"] >= 0)]
    duplicate_count = int(frame.duplicated(ROW_KEY_COLUMNS, keep=False).sum())
    if duplicate_count:
        # An ambiguous public provider row must not be averaged into a score.
        frame = frame.loc[~frame.duplicated(ROW_KEY_COLUMNS, keep=False)].copy()
    return frame, duplicate_count


def _operational_dominance(group: pd.DataFrame) -> pd.Series:
    """Return a conservative public-observables dominance flag for one market.

    A provider is dominated only when another provider is no more expensive,
    at least as reliable/fast/high-throughput on every available required
    operational proxy, and strictly better on at least one.  Missing proxies
    produce an unknown value rather than an artificial frontier result.
    """
    result = pd.Series(pd.NA, index=group.index, dtype="boolean")
    complete = group[OPERATIONAL_COLUMNS].notna().all(axis=1)
    for index, row in group.loc[complete].iterrows():
        peers = group.loc[complete & (group.index != index)]
        if peers.empty:
            result.loc[index] = False
            continue
        no_worse = (
            (peers["expected_quote_usd"] <= row["expected_quote_usd"] + CHANGE_TOLERANCE)
            & (peers["uptime_last_30m"] >= row["uptime_last_30m"] - CHANGE_TOLERANCE)
            & (peers["p90_latency_ms"] <= row["p90_latency_ms"] + CHANGE_TOLERANCE)
            & (peers["p90_throughput"] >= row["p90_throughput"] - CHANGE_TOLERANCE)
        )
        strictly_better = (
            (peers["expected_quote_usd"] < row["expected_quote_usd"] - CHANGE_TOLERANCE)
            | (peers["uptime_last_30m"] > row["uptime_last_30m"] + CHANGE_TOLERANCE)
            | (peers["p90_latency_ms"] < row["p90_latency_ms"] - CHANGE_TOLERANCE)
            | (peers["p90_throughput"] > row["p90_throughput"] + CHANGE_TOLERANCE)
        )
        result.loc[index] = bool((no_worse & strictly_better).any())
    return result


def pricing_panel(rows: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Compute mechanical pricing-position quantities from simulated snapshots."""
    frame, duplicate_count = _coerce(rows)
    if frame.empty:
        return _empty_panel(), duplicate_count
    frame = frame.copy()
    grouped = frame.groupby([*GROUP_COLUMNS, "run_ts"], dropna=False)
    cheapest = grouped["expected_quote_usd"].transform("min")
    top_share = grouped["simulated_route_share"].transform("max")
    frame["quote_markup_to_cheapest"] = frame["expected_quote_usd"] / cheapest - 1.0
    frame["simulated_top_provider"] = np.isclose(
        frame["simulated_route_share"], top_share, rtol=0.0, atol=CHANGE_TOLERANCE
    )
    n_top_tier = grouped["simulated_top_provider"].transform("sum")
    frame["simulated_unique_leader"] = frame["simulated_top_provider"] & (n_top_tier == 1)
    # This is an analytical derivative of s_i proportional to q_i^-2.  It is
    # not estimated from customer behavior and must remain visibly labelled.
    frame["mechanical_own_price_elasticity"] = -2.0 * (1.0 - frame["simulated_route_share"])
    frame["marginal_share_change_per_1pct_quote_increase"] = (
        -0.02 * frame["simulated_route_share"] * (1.0 - frame["simulated_route_share"])
    )
    # Useful for a *fixed-unit-demand counterfactual* only.  It is not revenue.
    frame["simulated_quote_revenue_index"] = (
        frame["expected_quote_usd"] * frame["simulated_route_share"]
    )
    frame["operational_metrics_complete"] = frame[OPERATIONAL_COLUMNS].notna().all(axis=1)
    dominance = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    for _, market in grouped:
        dominance.loc[market.index] = _operational_dominance(market)
    frame["public_operationally_dominated"] = dominance
    return frame.loc[:, _empty_panel().columns], duplicate_count


def pricing_events(panel: pd.DataFrame) -> pd.DataFrame:
    """Describe contiguous public repricings without treating share shifts as data."""
    if panel.empty:
        return _empty_events()
    snapshots = (
        panel.groupby([*GROUP_COLUMNS, "run_ts"], dropna=False)
        .agg(
            snapshot_ts=("ts", "first"),
            providers=("provider_name", lambda values: "|".join(sorted(values.astype(str)))),
        )
        .reset_index()
    )
    work = panel.merge(snapshots, on=[*GROUP_COLUMNS, "run_ts"], how="left")
    work = work.sort_values([*GROUP_COLUMNS, "provider_name", "ts"]).copy()
    per_provider = work.groupby([*GROUP_COLUMNS, "provider_name"], dropna=False)
    for column in [
        "run_ts",
        "ts",
        "providers",
        "expected_quote_usd",
        "simulated_route_share",
        "simulated_top_provider",
        "simulated_unique_leader",
    ]:
        work[f"previous_{column}"] = per_provider[column].shift(1)
    work["elapsed_minutes"] = (work["ts"] - work["previous_ts"]).dt.total_seconds() / 60.0
    work["quote_change_pct"] = (
        work["expected_quote_usd"] / work["previous_expected_quote_usd"] - 1.0
    )
    changed = work[
        work["previous_run_ts"].notna()
        & (work["elapsed_minutes"] <= MAX_CONTIGUOUS_GAP_MINUTES)
        & (work["quote_change_pct"].abs() > CHANGE_TOLERANCE)
    ].copy()
    if changed.empty:
        return _empty_events()
    changed["candidate_set_stable"] = changed["providers"] == changed["previous_providers"]
    changed["simulated_share_change"] = (
        changed["simulated_route_share"] - changed["previous_simulated_route_share"]
    )
    changed["price_cut"] = changed["quote_change_pct"] < 0
    changed["price_increase"] = changed["quote_change_pct"] > 0
    changed["became_simulated_top"] = changed["simulated_top_provider"].astype(bool) & ~changed[
        "previous_simulated_top_provider"
    ].astype(bool)
    changed["left_simulated_top"] = ~changed["simulated_top_provider"].astype(bool) & changed[
        "previous_simulated_top_provider"
    ].astype(bool)
    changed["became_simulated_unique_leader"] = changed["simulated_unique_leader"].astype(
        bool
    ) & ~changed["previous_simulated_unique_leader"].astype(bool)
    changed["left_simulated_unique_leader"] = ~changed["simulated_unique_leader"].astype(
        bool
    ) & changed["previous_simulated_unique_leader"].astype(bool)
    changed["pricing_shock_id"] = (
        changed["panel_id"].astype(str)
        + "|"
        + changed["model_id"].astype(str)
        + "|"
        + changed["provider_name"].astype(str)
        + "|"
        + changed["previous_run_ts"].astype(str)
        + "|"
        + changed["run_ts"].astype(str)
    )
    changed["pricing_event_id"] = (
        changed["pricing_shock_id"] + "|" + changed["scenario"].astype(str)
    )
    renamed = changed.rename(
        columns={
            "previous_run_ts": "previous_run_ts",
            "expected_quote_usd": "quote_after_usd",
            "previous_expected_quote_usd": "quote_before_usd",
            "simulated_route_share": "share_after",
            "previous_simulated_route_share": "share_before",
            "simulated_top_provider": "simulated_top_after",
            "previous_simulated_top_provider": "simulated_top_before",
            "simulated_unique_leader": "simulated_unique_leader_after",
            "previous_simulated_unique_leader": "simulated_unique_leader_before",
        }
    )
    return renamed.loc[:, _empty_events().columns].reset_index(drop=True)


def provider_scorecard(panel: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a descriptive provider scorecard from public simulations."""
    if panel.empty:
        return _empty_scorecard()
    base = (
        panel.groupby("provider_name", dropna=False)
        .agg(
            n_observations=("provider_name", "size"),
            n_models=("model_id", "nunique"),
            n_scenarios=("scenario", "nunique"),
            median_quote_markup_to_cheapest=("quote_markup_to_cheapest", "median"),
            median_simulated_route_share=("simulated_route_share", "median"),
            lowest_public_quote_rate=(
                "quote_markup_to_cheapest",
                lambda values: float((values <= CHANGE_TOLERANCE).mean()),
            ),
            simulated_top_rate=("simulated_top_provider", "mean"),
            simulated_unique_leader_rate=("simulated_unique_leader", "mean"),
            mean_mechanical_own_price_elasticity=("mechanical_own_price_elasticity", "mean"),
            operational_metrics_complete_rate=("operational_metrics_complete", "mean"),
            public_operationally_dominated_rate=("public_operationally_dominated", "mean"),
        )
        .reset_index()
    )
    if events.empty:
        event_metrics = pd.DataFrame(
            columns=[
                "provider_name",
                "n_quote_events",
                "n_unique_pricing_shocks",
                "n_price_cuts",
                "n_price_increases",
                "n_became_simulated_top_events",
                "n_became_simulated_unique_leader_events",
                "median_simulated_share_change_on_cut",
                "median_simulated_share_change_on_increase",
            ]
        )
    else:
        event_metrics = (
            events.groupby("provider_name", dropna=False)
            .agg(
                n_quote_events=("pricing_event_id", "size"),
                n_unique_pricing_shocks=("pricing_shock_id", "nunique"),
                n_price_cuts=("price_cut", "sum"),
                n_price_increases=("price_increase", "sum"),
                n_became_simulated_top_events=("became_simulated_top", "sum"),
                n_became_simulated_unique_leader_events=(
                    "became_simulated_unique_leader",
                    "sum",
                ),
                median_simulated_share_change_on_cut=(
                    "simulated_share_change",
                    lambda values: values[events.loc[values.index, "price_cut"]].median(),
                ),
                median_simulated_share_change_on_increase=(
                    "simulated_share_change",
                    lambda values: values[events.loc[values.index, "price_increase"]].median(),
                ),
            )
            .reset_index()
        )
    scorecard = base.merge(event_metrics, on="provider_name", how="left")
    for column in [
        "n_quote_events",
        "n_unique_pricing_shocks",
        "n_price_cuts",
        "n_price_increases",
        "n_became_simulated_top_events",
        "n_became_simulated_unique_leader_events",
    ]:
        scorecard[column] = pd.to_numeric(scorecard[column], errors="coerce").fillna(0).astype(int)
    return (
        scorecard.loc[:, _empty_scorecard().columns]
        .sort_values(["simulated_top_rate", "median_simulated_route_share"], ascending=False)
        .reset_index(drop=True)
    )


def summarize(
    raw_rows: pd.DataFrame,
    panel: pd.DataFrame,
    events: pd.DataFrame,
    scorecard: pd.DataFrame,
    duplicate_count: int,
) -> dict:
    n_snapshots = int(panel["run_ts"].nunique()) if not panel.empty else 0
    span_hours = (
        float((panel["ts"].max() - panel["ts"].min()).total_seconds() / 3600.0)
        if n_snapshots >= 2
        else 0.0
    )
    temporal_gate = n_snapshots >= MIN_SNAPSHOTS and span_hours >= MIN_SPAN_HOURS
    stable_events = events[events["candidate_set_stable"]] if not events.empty else events
    if not temporal_gate:
        status = "insufficient_temporal_coverage"
    elif stable_events.empty:
        status = "covered_no_public_repricing_events"
    else:
        status = "descriptive_public_quote_pricing"
    operational_complete = (
        float(panel["operational_metrics_complete"].mean()) if not panel.empty else None
    )
    performance_join_counts = (
        {
            str(status): int(count)
            for status, count in panel["performance_join_status"].value_counts(dropna=False).items()
        }
        if not panel.empty
        else {}
    )
    return {
        "evidence_status": status,
        "claim_boundary": (
            "Quotes, shares, own-price elasticities, and revenue indices are outputs of the "
            "public inverse-square simulation. They identify public quote-implied competitive "
            "position and descriptive repricing effects only, not realized routing, output "
            "quality, provider costs, margins, profit maximization, intent, or causality."
        ),
        "temporal_coverage_gate": {
            "min_snapshots": MIN_SNAPSHOTS,
            "min_span_hours": MIN_SPAN_HOURS,
            "passed": temporal_gate,
        },
        "n_input_rows": int(len(raw_rows)),
        "n_valid_provider_observations": int(len(panel)),
        "n_ambiguous_duplicate_provider_observations_excluded": duplicate_count,
        "n_snapshots": n_snapshots,
        "observed_span_hours": span_hours,
        "n_model_scenario_paths": (
            int(panel.groupby(GROUP_COLUMNS).ngroups) if not panel.empty else 0
        ),
        "n_providers": int(panel["provider_name"].nunique()) if not panel.empty else 0,
        "operational_metrics_complete_rate": operational_complete,
        "operational_metric_coverage": {
            column: float(panel[column].notna().mean()) if not panel.empty else None
            for column in OPERATIONAL_COLUMNS
        },
        "public_performance_join_status_counts": performance_join_counts,
        "n_quote_events": int(len(events)),
        "n_unique_pricing_shocks": (
            int(events["pricing_shock_id"].nunique()) if not events.empty else 0
        ),
        "n_stable_candidate_set_quote_events": int(len(stable_events)),
        "n_candidate_set_change_quote_events": (
            int((~events["candidate_set_stable"]).sum()) if not events.empty else 0
        ),
        "n_simulated_leader_gains": (
            int(events["became_simulated_top"].sum()) if not events.empty else 0
        ),
        "n_simulated_top_tier_gains": (
            int(events["became_simulated_top"].sum()) if not events.empty else 0
        ),
        "n_simulated_unique_leader_gains": (
            int(events["became_simulated_unique_leader"].sum()) if not events.empty else 0
        ),
        "legacy_simulated_leader_gain_note": (
            "n_simulated_leader_gains is retained for backward compatibility and counts "
            "top-tier entries, including ties. Use n_simulated_unique_leader_gains for "
            "unique-winner transitions."
        ),
        "n_scorecard_providers": int(len(scorecard)),
        "next_data_quality_gates": [
            "Accumulate the 24-hour public-quote coverage gate before interpreting event rates.",
            (
                "Accumulate at least seven consecutive days before comparing provider repricing "
                "behavior."
            ),
            (
                "Require complete public uptime, latency, and throughput fields before "
                "interpreting the operational frontier."
            ),
            (
                "Validate simulated selection and quality-adjusted value with redacted owned "
                "route-attempt metadata before making realized-flow or welfare claims."
            ),
        ],
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_simulations()
    panel, duplicate_count = pricing_panel(rows)
    events = pricing_events(panel)
    scorecard = provider_scorecard(panel, events)
    save(panel.drop(columns="ts", errors="ignore"), out_dir, "h66_simulated_pricing_panel")
    save(events, out_dir, "h66_simulated_pricing_events")
    save(scorecard, out_dir, "h66_simulated_pricing_scorecard")
    result = summarize(rows, panel, events, scorecard, duplicate_count)
    save_json(result, out_dir, "h66_summary")
    return result
