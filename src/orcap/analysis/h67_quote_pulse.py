"""H67 — tie-aware public quote-pulse and fade screen.

H67 reconstructs the public inverse-square route surface at the finest retained
five-minute endpoint cadence.  It detects a pre-registered public signature:
an eligible quote cut, an entry into the simulated top tier, and a later return
toward the pre-cut quote.  The share response is mechanically implied by the
simulation, so it is never presented as realized routing or provider intent.

The module is deliberately a *screen*.  A pulse candidate becomes a measured
allocation-capture claim only after an owned, privacy-preserving route-attempt
panel supplies selected-provider and outcome telemetry.
"""

# The generated standalone dashboard contains compact embedded HTML and JavaScript.
# ruff: noqa: E501

from __future__ import annotations

import html
import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..routing_simulation import panel_models, simulate_snapshot
from . import data
from .common import DEFAULT_OUT, save, save_json

CONFIG_PATH = Path("config/quote_pulse.toml")
TIE_TOLERANCE = 1e-10
MARKET_COLUMNS = ["run_ts", "model_id", "scenario"]
PATH_COLUMNS = ["model_id", "scenario", "provider_name"]
EPISODE_COLUMNS = ["model_id", "provider_name", "previous_run_ts", "run_ts"]


@dataclass(frozen=True)
class QuotePulseConfig:
    primary_scenario: str = "short_chat"
    cut_threshold_pct: float = -0.05
    reversion_tolerance_pct: float = 0.02
    max_contiguous_gap_minutes: float = 10.0
    fade_horizons_minutes: tuple[int, ...] = (30, 60, 120, 240, 360, 1440)
    min_span_days: int = 7
    min_independent_cut_episodes: int = 80


def _false_for_missing(values: pd.Series) -> pd.Series:
    """Return a non-null boolean series without pandas object downcast warnings."""
    return values.astype("boolean").fillna(False).astype(bool)


def load_config(path: Path = CONFIG_PATH) -> QuotePulseConfig:
    """Load the fixed public-screen thresholds without changing their defaults."""
    if not path.exists():
        return QuotePulseConfig()
    with path.open("rb") as handle:
        raw = tomllib.load(handle).get("quote_pulse", {})
    return QuotePulseConfig(
        primary_scenario=str(raw.get("primary_scenario", "short_chat")),
        cut_threshold_pct=float(raw.get("cut_threshold_pct", -0.05)),
        reversion_tolerance_pct=float(raw.get("reversion_tolerance_pct", 0.02)),
        max_contiguous_gap_minutes=float(raw.get("max_contiguous_gap_minutes", 10.0)),
        fade_horizons_minutes=tuple(
            int(value) for value in raw.get("fade_horizons_minutes", (30, 60, 120, 240, 360, 1440))
        ),
        min_span_days=int(raw.get("min_span_days", 7)),
        min_independent_cut_episodes=int(raw.get("min_independent_cut_episodes", 80)),
    )


def _quoted_models() -> str:
    return ", ".join("'" + model.replace("'", "''") + "'" for model in panel_models())


def load_endpoint_rows() -> pd.DataFrame:
    """Load the retained five-minute endpoint rows for the fixed route panel."""
    try:
        return data.q(
            f"""
            select distinct run_ts, dt, endpoint_fingerprint, model_id, model_name,
                   provider_name, tag, context_length, max_completion_tokens,
                   max_prompt_tokens, status, uptime_last_5m, uptime_last_30m,
                   latency_last_30m, throughput_last_30m, supported_parameters,
                   price_prompt, price_completion, price_request
            from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name = true)
            where model_id in ({_quoted_models()})
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def derive_five_minute_surface(endpoint_rows: pd.DataFrame) -> pd.DataFrame:
    """Replay the public route simulator at every retained endpoint timestamp."""
    if endpoint_rows.empty:
        return pd.DataFrame()
    records: list[dict] = []
    for (run_ts, dt), frame in endpoint_rows.groupby(["run_ts", "dt"], sort=True):
        # DuckDB/Pandas represent absent numeric API fields as NaN, whereas the
        # simulator's optional-price contract expects ``None``.  In particular,
        # a missing per-request price is a zero surcharge, not a NaN quote.
        rows = frame.astype(object).where(pd.notna(frame), None).copy()
        rows["supported_parameters"] = rows["supported_parameters"].map(
            lambda value: value.tolist() if isinstance(value, np.ndarray) else value
        )
        simulated, _ = simulate_snapshot(
            rows.to_dict("records"), run_ts=str(run_ts), dt=str(dt), models=panel_models()
        )
        records.extend(simulated)
    if not records:
        return pd.DataFrame()
    output = pd.DataFrame(records)
    output["surface_source"] = "derived_endpoint_snapshots_5m"
    return output


def load_precomputed_surface() -> pd.DataFrame:
    """Fall back to the 15-minute saved surface when endpoint history is absent."""
    try:
        rows = data.q(
            f"""
            select run_ts, dt, panel_id, model_id, model_name, scenario,
                   input_tokens, output_tokens, required_parameters, provider_name,
                   tag, endpoint_fingerprint, n_compatible_endpoint_variants,
                   n_eligible_endpoints, n_eligible_providers, provider_quote_rank,
                   is_lowest_public_quote, expected_quote_usd, price_prompt,
                   price_completion, price_request, inverse_square_weight,
                   simulated_route_share, public_status, uptime_last_5m,
                   uptime_last_30m, latency_last_30m, throughput_last_30m
            from read_parquet('{data.table_glob("routing_simulation")}', union_by_name = true)
            """
        ).df()
    except Exception:
        return pd.DataFrame()
    if not rows.empty:
        rows["surface_source"] = "saved_routing_simulation_15m"
    return rows


def load_quote_surface() -> pd.DataFrame:
    """Prefer replayed five-minute quotes; disclose a coarser fallback explicitly."""
    derived = derive_five_minute_surface(load_endpoint_rows())
    return derived if not derived.empty else load_precomputed_surface()


def annotate_surface(rows: pd.DataFrame) -> pd.DataFrame:
    """Attach tie-aware top-tier and candidate-set states to every quote row."""
    required = set(
        MARKET_COLUMNS + ["provider_name", "expected_quote_usd", "simulated_route_share"]
    )
    if rows.empty or not required.issubset(rows):
        return pd.DataFrame()
    frame = rows.copy()
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame["expected_quote_usd"] = pd.to_numeric(frame["expected_quote_usd"], errors="coerce")
    frame["simulated_route_share"] = pd.to_numeric(frame["simulated_route_share"], errors="coerce")
    frame = frame.dropna(
        subset=[
            "ts",
            "model_id",
            "scenario",
            "provider_name",
            "expected_quote_usd",
            "simulated_route_share",
        ]
    ).copy()
    frame = frame[(frame["expected_quote_usd"] > 0) & (frame["simulated_route_share"] >= 0)]
    if frame.empty:
        return frame
    top_share = frame.groupby(MARKET_COLUMNS, dropna=False)["simulated_route_share"].transform(
        "max"
    )
    frame["is_top_tier"] = np.isclose(
        frame["simulated_route_share"], top_share, rtol=0.0, atol=TIE_TOLERANCE
    )
    state = (
        frame.groupby(MARKET_COLUMNS, dropna=False)
        .agg(
            candidate_set=("provider_name", lambda values: "|".join(sorted(values.astype(str)))),
            n_candidates=("provider_name", "nunique"),
            n_top_tier=("is_top_tier", "sum"),
        )
        .reset_index()
    )
    tiers = (
        frame.loc[frame["is_top_tier"]]
        .groupby(MARKET_COLUMNS, dropna=False)["provider_name"]
        .agg(lambda values: "|".join(sorted(values.astype(str))))
        .rename("top_tier")
        .reset_index()
    )
    state = state.merge(tiers, on=MARKET_COLUMNS, how="left", validate="one_to_one")
    frame = frame.merge(state, on=MARKET_COLUMNS, how="left", validate="many_to_one")
    frame["is_unique_leader"] = frame["is_top_tier"] & (frame["n_top_tier"] == 1)
    frame["unique_leader"] = np.where(frame["is_unique_leader"], frame["provider_name"], pd.NA)
    return frame.sort_values(["model_id", "scenario", "provider_name", "ts"]).reset_index(drop=True)


def build_paths(surface: pd.DataFrame, config: QuotePulseConfig) -> pd.DataFrame:
    """Construct one scenario-level contiguous quote transition per provider."""
    if surface.empty:
        return pd.DataFrame()
    work = surface.sort_values(PATH_COLUMNS + ["ts"]).copy()
    grouped = work.groupby(PATH_COLUMNS, dropna=False)
    for column in [
        "run_ts",
        "ts",
        "expected_quote_usd",
        "simulated_route_share",
        "candidate_set",
        "top_tier",
        "is_top_tier",
        "is_unique_leader",
        "unique_leader",
    ]:
        work[f"previous_{column}"] = grouped[column].shift(1)
    work["elapsed_minutes"] = (work["ts"] - work["previous_ts"]).dt.total_seconds() / 60.0
    work["quote_change_pct"] = (
        work["expected_quote_usd"] / work["previous_expected_quote_usd"] - 1.0
    )
    work["simulated_share_change"] = (
        work["simulated_route_share"] - work["previous_simulated_route_share"]
    )
    work["contiguous"] = work["previous_run_ts"].notna() & (
        work["elapsed_minutes"] <= config.max_contiguous_gap_minutes
    )
    work["candidate_set_stable"] = work["candidate_set"] == work["previous_candidate_set"]
    work["is_quote_cut"] = work["contiguous"] & (
        work["quote_change_pct"] <= config.cut_threshold_pct
    )
    work["is_quote_increase"] = work["contiguous"] & (
        work["quote_change_pct"] >= -config.cut_threshold_pct
    )
    work["entered_top_tier"] = work["is_top_tier"] & ~_false_for_missing(
        work["previous_is_top_tier"]
    )
    work["entered_unique_leader"] = work["is_unique_leader"] & ~work[
        "previous_is_unique_leader"
    ].pipe(_false_for_missing)
    work["is_primary_scenario"] = work["scenario"] == config.primary_scenario
    work["pulse_path_id"] = (
        work["model_id"].astype(str)
        + "|"
        + work["scenario"].astype(str)
        + "|"
        + work["provider_name"].astype(str)
        + "|"
        + work["previous_run_ts"].astype(str)
        + "|"
        + work["run_ts"].astype(str)
    )
    return work.reset_index(drop=True)


def attach_reversion_paths(paths: pd.DataFrame, config: QuotePulseConfig) -> pd.DataFrame:
    """Attach right-censored fade outcomes without treating a missing future as no fade."""
    if paths.empty:
        return paths.copy()
    result = paths.copy()
    for horizon in config.fade_horizons_minutes:
        result[f"followup_complete_{horizon}m"] = pd.NA
        result[f"quote_reverted_{horizon}m"] = pd.NA
        result[f"first_reversion_minutes_{horizon}m"] = np.nan
    eligible = result.index[result["is_quote_cut"] & result["contiguous"]]
    groups = {
        key: frame.sort_values("ts")
        for key, frame in result.groupby(PATH_COLUMNS, dropna=False, sort=False)
    }
    for index in eligible:
        row = result.loc[index]
        group = groups[(row["model_id"], row["scenario"], row["provider_name"])]
        event_ts = pd.Timestamp(row["ts"])
        previous_quote = float(row["previous_expected_quote_usd"])
        for horizon in config.fade_horizons_minutes:
            deadline = event_ts + pd.to_timedelta(int(horizon), unit="m")
            window = group[(group["ts"] >= event_ts) & (group["ts"] <= deadline)].copy()
            complete = False
            if not window.empty and window["ts"].max() >= deadline:
                gaps = window["ts"].diff().dropna().dt.total_seconds() / 60.0
                complete = bool((gaps <= config.max_contiguous_gap_minutes).all())
            future = window[window["ts"] > event_ts]
            reverted = future.loc[
                np.isclose(
                    future["expected_quote_usd"] / previous_quote,
                    1.0,
                    rtol=config.reversion_tolerance_pct,
                    atol=0.0,
                )
            ]
            result.loc[index, f"followup_complete_{horizon}m"] = complete
            result.loc[index, f"quote_reverted_{horizon}m"] = bool(not reverted.empty)
            if not reverted.empty:
                first = reverted.iloc[0]
                result.loc[index, f"first_reversion_minutes_{horizon}m"] = (
                    first["ts"] - event_ts
                ).total_seconds() / 60.0
    return result


def build_episode_events(paths: pd.DataFrame, config: QuotePulseConfig) -> pd.DataFrame:
    """Deduplicate the four workload-shape views into primary-scenario episodes."""
    if paths.empty:
        return pd.DataFrame()
    cuts = paths.loc[paths["is_quote_cut"] & paths["contiguous"]].copy()
    primary = cuts.loc[cuts["is_primary_scenario"]].copy()
    if primary.empty:
        return pd.DataFrame()
    aggregate = (
        cuts.groupby(EPISODE_COLUMNS, dropna=False)
        .agg(
            n_scenario_cuts=("scenario", "nunique"),
            scenario_cut_list=("scenario", lambda values: "|".join(sorted(values.astype(str)))),
            median_quote_cut_pct=("quote_change_pct", "median"),
            median_simulated_share_change=("simulated_share_change", "median"),
        )
        .reset_index()
    )
    fields = [
        *EPISODE_COLUMNS,
        "pulse_path_id",
        "elapsed_minutes",
        "candidate_set_stable",
        "previous_candidate_set",
        "candidate_set",
        "previous_top_tier",
        "top_tier",
        "previous_unique_leader",
        "unique_leader",
        "entered_top_tier",
        "entered_unique_leader",
        "quote_change_pct",
        "simulated_share_change",
        "surface_source",
    ]
    for horizon in config.fade_horizons_minutes:
        fields.extend(
            [
                f"followup_complete_{horizon}m",
                f"quote_reverted_{horizon}m",
                f"first_reversion_minutes_{horizon}m",
            ]
        )
    events = primary.loc[:, fields].merge(
        aggregate, on=EPISODE_COLUMNS, how="left", validate="one_to_one"
    )
    events = events.rename(
        columns={
            "pulse_path_id": "event_id",
            "quote_change_pct": "primary_quote_cut_pct",
            "simulated_share_change": "primary_simulated_share_change",
            "candidate_set": "candidate_set_after",
            "top_tier": "top_tier_after",
            "unique_leader": "unique_leader_after",
        }
    )
    events["quote_pulse_candidate"] = _false_for_missing(
        events["candidate_set_stable"]
    ) & _false_for_missing(events["entered_top_tier"])
    for horizon in config.fade_horizons_minutes:
        events[f"pulse_and_fade_{horizon}m"] = (
            events["quote_pulse_candidate"]
            & _false_for_missing(events[f"followup_complete_{horizon}m"])
            & _false_for_missing(events[f"quote_reverted_{horizon}m"])
        )
    return events.sort_values(["run_ts", "model_id", "provider_name"]).reset_index(drop=True)


def event_quality(events: pd.DataFrame, config: QuotePulseConfig) -> pd.DataFrame:
    """Keep inclusion and right-censoring explicit for every primary cut episode."""
    if events.empty:
        return pd.DataFrame()
    longest = max(config.fade_horizons_minutes)
    quality = events.loc[
        :,
        [
            "event_id",
            "model_id",
            "provider_name",
            "previous_run_ts",
            "run_ts",
            "elapsed_minutes",
            "candidate_set_stable",
            "entered_top_tier",
            "entered_unique_leader",
            "quote_pulse_candidate",
            f"followup_complete_{longest}m",
            f"quote_reverted_{longest}m",
        ],
    ].copy()
    quality["status"] = np.select(
        [
            ~_false_for_missing(quality["candidate_set_stable"]),
            ~_false_for_missing(quality["entered_top_tier"]),
            ~_false_for_missing(quality[f"followup_complete_{longest}m"]),
        ],
        ["candidate_set_changed", "cut_without_top_tier_entry", f"right_censored_{longest}m"],
        default="eligible_quote_pulse_followup",
    )
    return quality


def provider_scorecard(events: pd.DataFrame, config: QuotePulseConfig) -> pd.DataFrame:
    """Aggregate candidate pulse and fade rates without pretending scenarios are independent."""
    if events.empty:
        return pd.DataFrame(
            columns=[
                "provider_name",
                "n_primary_cut_episodes",
                "n_quote_pulse_candidates",
                "median_primary_quote_cut_pct",
                "median_primary_simulated_share_change",
            ]
        )
    aggregations: dict[str, tuple[str, str]] = {
        "n_primary_cut_episodes": ("event_id", "size"),
        "n_models": ("model_id", "nunique"),
        "n_quote_pulse_candidates": ("quote_pulse_candidate", "sum"),
        "median_primary_quote_cut_pct": ("primary_quote_cut_pct", "median"),
        "median_primary_simulated_share_change": ("primary_simulated_share_change", "median"),
    }
    for horizon in config.fade_horizons_minutes:
        aggregations[f"n_followup_complete_{horizon}m"] = (f"followup_complete_{horizon}m", "sum")
        aggregations[f"n_quote_reverted_{horizon}m"] = (f"quote_reverted_{horizon}m", "sum")
        aggregations[f"n_pulse_and_fade_{horizon}m"] = (f"pulse_and_fade_{horizon}m", "sum")
    scorecard = events.groupby("provider_name", dropna=False).agg(**aggregations).reset_index()
    count_columns = ["n_primary_cut_episodes", "n_models", "n_quote_pulse_candidates"]
    for horizon in config.fade_horizons_minutes:
        count_columns.extend(
            [
                f"n_followup_complete_{horizon}m",
                f"n_quote_reverted_{horizon}m",
                f"n_pulse_and_fade_{horizon}m",
            ]
        )
    for column in count_columns:
        scorecard[column] = pd.to_numeric(scorecard[column], errors="coerce").fillna(0).astype(int)
    return scorecard.sort_values(
        ["n_quote_pulse_candidates", "n_primary_cut_episodes"], ascending=False
    ).reset_index(drop=True)


def summarize(surface: pd.DataFrame, events: pd.DataFrame, config: QuotePulseConfig) -> dict:
    """Return a public-screen verdict with hard coverage and identification boundaries."""
    if surface.empty:
        return {
            "evidence_status": "not_available",
            "claim_boundary": _claim_boundary(),
            "reason": "No eligible public routing surface was available.",
            "config": asdict(config),
        }
    n_snapshots = int(surface["run_ts"].nunique())
    span_days = (
        (surface["ts"].max() - surface["ts"].min()).total_seconds() / 86_400
        if n_snapshots >= 2
        else 0.0
    )
    longest = max(config.fade_horizons_minutes)
    n_events = int(len(events))
    n_candidates = int(events["quote_pulse_candidate"].sum()) if not events.empty else 0
    n_complete = (
        int(_false_for_missing(events[f"followup_complete_{longest}m"]).sum())
        if not events.empty
        else 0
    )
    n_fades = int(events[f"pulse_and_fade_{longest}m"].sum()) if not events.empty else 0
    coverage_passed = (
        span_days >= config.min_span_days and n_events >= config.min_independent_cut_episodes
    )
    if span_days < config.min_span_days:
        evidence_status = "insufficient_temporal_coverage"
    elif n_events < config.min_independent_cut_episodes:
        evidence_status = "power_gated"
    elif n_fades == 0:
        evidence_status = "no_public_quote_pulse_and_fade_observed"
    else:
        evidence_status = "public_quote_pulse_candidates_observed"
    return {
        "evidence_status": evidence_status,
        "claim_boundary": _claim_boundary(),
        "surface_source": str(surface["surface_source"].iloc[0]),
        "n_snapshots": n_snapshots,
        "observed_span_days": span_days,
        "n_models": int(surface["model_id"].nunique()),
        "n_scenarios": int(surface["scenario"].nunique()),
        "n_primary_cut_episodes": n_events,
        "n_quote_pulse_candidates": n_candidates,
        f"n_complete_{longest}m_followups": n_complete,
        f"n_quote_pulse_and_fade_{longest}m": n_fades,
        "coverage_gate": {
            "min_span_days": config.min_span_days,
            "min_independent_cut_episodes": config.min_independent_cut_episodes,
            "passed": coverage_passed,
        },
        "config": asdict(config),
    }


def _claim_boundary() -> str:
    return (
        "This is a public quote-dynamics screen. Simulated share movements are generated "
        "by the documented inverse-square price rule and do not identify selected provider, "
        "routed volume, intent, provider profit, MEV, front-running, or customer harm. A "
        "pulse-and-fade candidate requires separate owned route-attempt telemetry for an "
        "allocation-capture claim."
    )


def write_dashboard(
    summary: dict, scorecard: pd.DataFrame, events: pd.DataFrame, out_dir: Path
) -> Path:
    """Write a compact local dashboard with a provider filter and event ledger."""
    rows = (
        events.loc[
            :,
            [
                "run_ts",
                "model_id",
                "provider_name",
                "primary_quote_cut_pct",
                "primary_simulated_share_change",
                "quote_pulse_candidate",
            ],
        ].copy()
        if not events.empty
        else pd.DataFrame()
    )
    records = rows.tail(100).to_dict("records") if not rows.empty else []
    provider_options = (
        "".join(
            f'<option value="{html.escape(str(provider))}">{html.escape(str(provider))}</option>'
            for provider in sorted(events["provider_name"].dropna().unique())
        )
        if not events.empty
        else ""
    )
    score_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.provider_name))}</td>"
        f"<td>{int(row.n_primary_cut_episodes)}</td>"
        f"<td>{int(row.n_quote_pulse_candidates)}</td>"
        f"<td>{float(row.median_primary_quote_cut_pct):.1%}</td>"
        "</tr>"
        for row in scorecard.head(12).itertuples(index=False)
    )
    page = f"""<!doctype html>
<meta charset=\"utf-8\">
<title>H67 quote-pulse monitor</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#18212f;background:#fff}}main{{max-width:1100px;margin:auto}}table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{border-bottom:1px solid #d8dee8;padding:8px;text-align:left}}th{{background:#f5f7fa}}.stats{{display:flex;gap:24px;flex-wrap:wrap}}.stats strong{{display:block;font-size:1.4rem}}.muted{{color:#596579}}label{{font-weight:600}}select{{margin-left:8px;padding:4px}}code{{font-size:.9em}}
</style>
<main><h1>Public quote-pulse monitor</h1>
<p class=\"muted\">{html.escape(summary.get("claim_boundary", ""))}</p>
<div class=\"stats\"><div><strong>{summary.get("n_primary_cut_episodes", 0)}</strong>primary cut episodes</div><div><strong>{summary.get("n_quote_pulse_candidates", 0)}</strong>top-tier pulse candidates</div><div><strong>{summary.get("evidence_status", "—")}</strong>evidence status</div></div>
<h2>Provider ledger</h2><table><thead><tr><th>Provider</th><th>Cuts</th><th>Pulse candidates</th><th>Median cut</th></tr></thead><tbody>{score_rows}</tbody></table>
<h2>Recent primary-scenario events</h2><label for=\"provider\">Provider</label><select id=\"provider\"><option value=\"\">All</option>{provider_options}</select>
<table><thead><tr><th>UTC</th><th>Model</th><th>Provider</th><th>Quote cut</th><th>Simulated share change</th><th>Top-tier candidate</th></tr></thead><tbody id=\"events\"></tbody></table>
</main><script>
const rows={json.dumps(records, default=str)};const body=document.getElementById('events');const select=document.getElementById('provider');
function render(){{const selected=select.value;body.innerHTML=rows.filter(r=>!selected||r.provider_name===selected).map(r=>`<tr><td>${{r.run_ts}}</td><td>${{r.model_id}}</td><td>${{r.provider_name}}</td><td>${{(100*r.primary_quote_cut_pct).toFixed(1)}}%</td><td>${{(100*r.primary_simulated_share_change).toFixed(1)}}pp</td><td>${{r.quote_pulse_candidate?'yes':'no'}}</td></tr>`).join('');}}select.addEventListener('change',render);render();
</script>"""
    path = out_dir / "h67_quote_pulse_dashboard.html"
    path.write_text(page, encoding="utf-8")
    return path


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    config = load_config()
    surface = annotate_surface(load_quote_surface())
    paths = attach_reversion_paths(build_paths(surface, config), config)
    events = build_episode_events(paths, config)
    quality = event_quality(events, config)
    scorecard = provider_scorecard(events, config)
    summary = summarize(surface, events, config)
    summary["dashboard"] = "h67_quote_pulse_dashboard.html"
    save(surface, out_dir, "h67_quote_pulse_surface")
    save(paths, out_dir, "h67_quote_pulse_paths")
    save(events, out_dir, "h67_quote_pulse_events")
    save(quality, out_dir, "h67_quote_pulse_quality")
    save(scorecard, out_dir, "h67_quote_pulse_scorecard")
    write_dashboard(summary, scorecard, events, out_dir)
    save_json(summary, out_dir, "h67_summary")
    return summary
