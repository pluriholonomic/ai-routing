"""H68 — descriptive router-enforcement telemetry from public endpoint stats.

OpenRouter's public frontend stats expose rolling rate-limit counts, a
derank-state flag, and capacity-related fields per endpoint.  Those fields are
router-side enforcement *aggregates*, not a request tape: they do not reveal a
request's owner, ordering, selected-provider fill, enforcement reason, or
provider intent.  H68 makes the free evidence auditable without promoting an
incidence or state transition into a front-running claim.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

MAX_CONTIGUOUS_GAP_MINUTES = 10.0
KEY_COLUMNS = ["model_permaslug", "endpoint_uuid", "provider_name"]
SOURCE_TABLES = ("congestion_intraday", "event_bursts_congestion")


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "run_ts",
            "dt",
            *KEY_COLUMNS,
            "ts",
            "source",
            "success_5m",
            "rate_limited_5m",
            "derankable_error_30m",
            "request_count_30m",
            "capacity_ceiling_rpm",
            "recent_peak_rpm",
            "is_deranked",
            "previous_run_ts",
            "elapsed_minutes",
            "contiguous",
            "previous_is_deranked",
            "previous_rate_limited_5m",
            "attempt_proxy_5m",
            "rate_limit_share_5m",
            "capacity_load_ratio",
            "rate_limit_incidence",
            "rate_limit_onset",
            "at_risk_derank",
            "derank_onset",
            "derank_release",
        ]
    )


def _empty_derank_events() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "event_type",
            "run_ts",
            "dt",
            *KEY_COLUMNS,
            "elapsed_minutes",
            "previous_is_deranked",
            "is_deranked",
            "previous_rate_limited_5m",
            "rate_limited_5m",
            "success_5m",
            "rate_limit_share_5m",
            "capacity_load_ratio",
        ]
    )


def _empty_rate_limit_events() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "run_ts",
            "dt",
            *KEY_COLUMNS,
            "elapsed_minutes",
            "previous_rate_limited_5m",
            "rate_limited_5m",
            "success_5m",
            "rate_limit_share_5m",
            "is_deranked",
            "capacity_load_ratio",
        ]
    )


def _as_bool(values: pd.Series) -> pd.Series:
    """Normalize nullable public JSON booleans without treating strings as truthy."""
    truthy = {"1", "true", "yes", "y"}
    return values.map(
        lambda value: bool(value)
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().lower() in truthy
        if pd.notna(value)
        else False
    ).astype(bool)


def load_enforcement_rows() -> pd.DataFrame:
    """Load public enforcement rows, preferring targeted burst samples on ties."""
    frames: list[pd.DataFrame] = []
    for table in SOURCE_TABLES:
        try:
            frame = data.q(
                f"""
                select distinct run_ts, dt, model_permaslug, endpoint_uuid, provider_name,
                       success_5m, rate_limited_5m, derankable_error_30m,
                       request_count_30m, capacity_ceiling_rpm, recent_peak_rpm,
                       is_deranked
                from read_parquet('{data.table_glob(table)}', union_by_name = true)
                """
            ).df()
        except Exception:
            continue
        if not frame.empty:
            frame["source"] = table
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    rows = pd.concat(frames, ignore_index=True)
    rows["source_priority"] = (rows["source"] == "event_bursts_congestion").astype(int)
    return (
        rows.sort_values("source_priority")
        .drop_duplicates(["run_ts", *KEY_COLUMNS], keep="last")
        .drop(columns="source_priority")
        .reset_index(drop=True)
    )


def enforcement_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Create contiguous endpoint paths and explicit public enforcement events."""
    if rows.empty:
        return _empty_panel()
    frame = rows.copy()
    for column in ["run_ts", "dt", *KEY_COLUMNS]:
        if column not in frame:
            frame[column] = pd.NA
    for column in [
        "success_5m",
        "rate_limited_5m",
        "derankable_error_30m",
        "request_count_30m",
        "capacity_ceiling_rpm",
        "recent_peak_rpm",
    ]:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "is_deranked" not in frame:
        frame["is_deranked"] = False
    frame["is_deranked"] = _as_bool(frame["is_deranked"])
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame = frame.dropna(subset=["ts", *KEY_COLUMNS]).copy()
    if frame.empty:
        return _empty_panel()
    frame = (
        frame.sort_values([*KEY_COLUMNS, "ts"])
        .drop_duplicates(["run_ts", *KEY_COLUMNS], keep="last")
        .reset_index(drop=True)
    )
    grouped = frame.groupby(KEY_COLUMNS, dropna=False, sort=False)
    frame["previous_run_ts"] = grouped["run_ts"].shift()
    previous_ts = grouped["ts"].shift()
    frame["elapsed_minutes"] = (frame["ts"] - previous_ts).dt.total_seconds() / 60
    frame["contiguous"] = frame["elapsed_minutes"].between(
        0.0, MAX_CONTIGUOUS_GAP_MINUTES, inclusive="both"
    )
    frame["previous_is_deranked"] = _as_bool(grouped["is_deranked"].shift())
    frame["previous_rate_limited_5m"] = grouped["rate_limited_5m"].shift()
    frame["attempt_proxy_5m"] = frame["success_5m"].fillna(0) + frame[
        "rate_limited_5m"
    ].fillna(0)
    frame["rate_limit_share_5m"] = np.where(
        frame["attempt_proxy_5m"] > 0,
        frame["rate_limited_5m"].fillna(0) / frame["attempt_proxy_5m"],
        np.nan,
    )
    frame["capacity_load_ratio"] = np.where(
        frame["capacity_ceiling_rpm"] > 0,
        frame["recent_peak_rpm"] / frame["capacity_ceiling_rpm"],
        np.nan,
    )
    frame["rate_limit_incidence"] = frame["rate_limited_5m"].fillna(0) > 0
    frame["rate_limit_onset"] = (
        frame["contiguous"]
        & frame["previous_rate_limited_5m"].fillna(0).le(0)
        & frame["rate_limited_5m"].fillna(0).gt(0)
    )
    frame["at_risk_derank"] = frame["contiguous"] & ~frame["previous_is_deranked"]
    frame["derank_onset"] = frame["at_risk_derank"] & frame["is_deranked"]
    frame["derank_release"] = (
        frame["contiguous"] & frame["previous_is_deranked"] & ~frame["is_deranked"]
    )
    return frame.loc[:, _empty_panel().columns]


def derank_events(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return _empty_derank_events()
    events = panel[panel["derank_onset"] | panel["derank_release"]].copy()
    if events.empty:
        return _empty_derank_events()
    events["event_type"] = np.where(events["derank_onset"], "derank_onset", "derank_release")
    return events.loc[:, _empty_derank_events().columns]


def rate_limit_events(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return _empty_rate_limit_events()
    events = panel[panel["rate_limit_onset"]].copy()
    if events.empty:
        return _empty_rate_limit_events()
    return events.loc[:, _empty_rate_limit_events().columns]


def derank_hazard(panel: pd.DataFrame) -> pd.DataFrame:
    """Describe transition incidence by the prior public rate-limit state."""
    columns = ["prior_rate_limit_positive", "at_risk_observations", "derank_onsets", "hazard"]
    at_risk = panel[panel["at_risk_derank"]].copy() if not panel.empty else pd.DataFrame()
    if at_risk.empty:
        return pd.DataFrame(columns=columns)
    at_risk["prior_rate_limit_positive"] = at_risk["previous_rate_limited_5m"].fillna(0).gt(0)
    result = (
        at_risk.groupby("prior_rate_limit_positive", as_index=False)
        .agg(
            at_risk_observations=("derank_onset", "size"),
            derank_onsets=("derank_onset", "sum"),
        )
        .sort_values("prior_rate_limit_positive")
    )
    result["derank_onsets"] = result["derank_onsets"].astype(int)
    result["hazard"] = result["derank_onsets"] / result["at_risk_observations"]
    return result.loc[:, columns]


def summarize(panel: pd.DataFrame, hazard: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "evidence_status": "no_public_enforcement_rows",
            "claim_boundary": "No public enforcement observations were available.",
        }
    span_hours = (panel["ts"].max() - panel["ts"].min()).total_seconds() / 3600
    onsets = int(panel["derank_onset"].sum())
    status = (
        "descriptive_router_enforcement"
        if onsets
        else "descriptive_incidence_no_observed_derank_transition"
    )
    return {
        "evidence_status": status,
        "claim_boundary": (
            "Public rate-limit counts and derank state describe router-side aggregate "
            "enforcement only. They do not identify request ordering, customer identity, "
            "selected-provider fills, enforcement reasons, provider intent, front-running, "
            "or customer harm."
        ),
        "n_rows": int(len(panel)),
        "n_snapshots": int(panel["run_ts"].nunique()),
        "observed_span_hours": float(span_hours),
        "n_endpoints": int(panel[KEY_COLUMNS].drop_duplicates().shape[0]),
        "n_rate_limit_positive_rows": int(panel["rate_limit_incidence"].sum()),
        "n_rate_limit_onsets": int(panel["rate_limit_onset"].sum()),
        "n_deranked_state_rows": int(panel["is_deranked"].sum()),
        "n_derank_onsets": onsets,
        "n_derank_releases": int(panel["derank_release"].sum()),
        "n_at_risk_derank_transitions": int(panel["at_risk_derank"].sum()),
        "derank_hazard": hazard.to_dict("records"),
        "hazard_interpretation": (
            "No derank-state transition was observed in contiguous public snapshots; "
            "a derank hazard or relation to prior rate limits is not identified."
            if onsets == 0
            else "Descriptive transition incidence only; no causal enforcement claim."
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = enforcement_panel(load_enforcement_rows())
    events = derank_events(panel)
    rate_events = rate_limit_events(panel)
    hazard = derank_hazard(panel)
    save(panel, out_dir, "h68_router_enforcement_panel")
    save(events, out_dir, "h68_derank_events")
    save(rate_events, out_dir, "h68_rate_limit_events")
    save(hazard, out_dir, "h68_derank_hazard")
    result = summarize(panel, hazard)
    save_json(result, out_dir, "h68_summary")
    return result
