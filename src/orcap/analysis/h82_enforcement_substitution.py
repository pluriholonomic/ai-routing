"""H82 — high-frequency capacity enforcement and within-model substitution.

The public endpoint feed exposes rolling five-minute success and rate-limit
counts.  H82 asks whether an isolated, endpoint-specific rate-limit onset is
followed by successful volume moving to other endpoints or providers while the
posted price remains fixed.  The design is frozen in
``docs/h82-enforcement-substitution-preregistration.md``.

The study is observational.  Rate limits respond endogenously to load, and the
feed does not expose request ordering, customer identity, private eligibility,
or the router score.  Consequently the analysis reports a substitution event
study and refuses causal or front-running language until its explicit coverage
and falsification gates pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h68_router_enforcement import KEY_COLUMNS, SOURCE_TABLES, enforcement_panel

HIGH_MIN_RATE_LIMITED = 5
HIGH_MIN_SHARE = 0.20
LOW_MAX_SHARE = 0.05
MIN_ATTEMPT_PROXY = 10
ISOLATION_MINUTES = 60.0
EVENT_GRID = np.arange(-30, 65, 5, dtype=int)
PRIMARY_PRE = (-30, -5)
PRIMARY_POST = (5, 30)
EARLY_PRE = (-30, -20)
LATE_PRE = (-15, -5)
MIN_PRE_CELLS = 4
MIN_POST_CELLS = 4
BOOTSTRAP_DRAWS = 2_000
BOOTSTRAP_SEED = 82_071_526

PRIMARY_METRICS = [
    "endpoint_success_share",
    "provider_success_share",
    "log1p_other_provider_success",
]

OUTCOME_METRICS = [
    *PRIMARY_METRICS,
    "endpoint_attempt_share",
    "log1p_endpoint_success",
    "log1p_same_provider_other_success",
    "log1p_model_success",
    "log_price_completion",
    "log1p_capacity_ceiling_rpm",
]

RAW_ACCOUNTING_METRICS = [
    "success_5m",
    "same_provider_other_success_5m",
    "other_provider_success_5m",
    "model_success_5m",
]


def load_rows() -> pd.DataFrame:
    """Load the two public enforcement sources with enough fields for H82."""
    frames: list[pd.DataFrame] = []
    for table in SOURCE_TABLES:
        try:
            frame = data.q(
                f"""
                select run_ts, dt, model_permaslug, endpoint_uuid, provider_name,
                       price_completion, success_5m, rate_limited_5m,
                       derankable_error_30m, request_count_30m,
                       capacity_ceiling_rpm, recent_peak_rpm, is_deranked
                from read_parquet('{data.table_glob(table)}', union_by_name=true)
                """
            ).df()
        except Exception:
            continue
        if not frame.empty:
            frame["source"] = table
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def canonical_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate public rows and attach within-model flow accounting."""
    if rows.empty:
        return pd.DataFrame()
    frame = rows.copy()
    for column in ["run_ts", "dt", *KEY_COLUMNS]:
        if column not in frame:
            frame[column] = pd.NA
    if "source" not in frame:
        frame["source"] = "congestion_intraday"
    numeric = [
        "price_completion",
        "success_5m",
        "rate_limited_5m",
        "derankable_error_30m",
        "request_count_30m",
        "capacity_ceiling_rpm",
        "recent_peak_rpm",
    ]
    for column in numeric:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "is_deranked" not in frame:
        frame["is_deranked"] = False

    frame["source_priority"] = frame["source"].eq("event_bursts_congestion").astype(int)
    frame = (
        frame.sort_values("source_priority")
        .drop_duplicates(["run_ts", *KEY_COLUMNS], keep="last")
        .drop(columns="source_priority")
        .reset_index(drop=True)
    )
    public = enforcement_panel(frame)
    if public.empty:
        return pd.DataFrame()
    extra = frame.loc[
        :,
        ["run_ts", *KEY_COLUMNS, "price_completion"],
    ].drop_duplicates(["run_ts", *KEY_COLUMNS], keep="last")
    panel = public.merge(extra, on=["run_ts", *KEY_COLUMNS], how="left", validate="one_to_one")

    model_keys = ["run_ts", "model_permaslug"]
    provider_keys = [*model_keys, "provider_name"]
    panel["model_success_5m"] = panel.groupby(model_keys, dropna=False)["success_5m"].transform(
        lambda values: values.sum(min_count=1)
    )
    panel["model_attempt_5m"] = panel.groupby(model_keys, dropna=False)[
        "attempt_proxy_5m"
    ].transform(lambda values: values.sum(min_count=1))
    panel["provider_success_5m"] = panel.groupby(provider_keys, dropna=False)[
        "success_5m"
    ].transform(lambda values: values.sum(min_count=1))
    panel["same_provider_other_success_5m"] = (
        panel["provider_success_5m"] - panel["success_5m"]
    )
    panel["other_provider_success_5m"] = (
        panel["model_success_5m"] - panel["provider_success_5m"]
    )
    panel["endpoint_success_share"] = np.where(
        panel["model_success_5m"] > 0,
        panel["success_5m"] / panel["model_success_5m"],
        np.nan,
    )
    panel["provider_success_share"] = np.where(
        panel["model_success_5m"] > 0,
        panel["provider_success_5m"] / panel["model_success_5m"],
        np.nan,
    )
    panel["endpoint_attempt_share"] = np.where(
        panel["model_attempt_5m"] > 0,
        panel["attempt_proxy_5m"] / panel["model_attempt_5m"],
        np.nan,
    )
    panel["log1p_endpoint_success"] = np.log1p(panel["success_5m"].clip(lower=0))
    panel["log1p_same_provider_other_success"] = np.log1p(
        panel["same_provider_other_success_5m"].clip(lower=0)
    )
    panel["log1p_other_provider_success"] = np.log1p(
        panel["other_provider_success_5m"].clip(lower=0)
    )
    panel["log1p_model_success"] = np.log1p(panel["model_success_5m"].clip(lower=0))
    panel["log_price_completion"] = np.where(
        panel["price_completion"] > 0, np.log(panel["price_completion"]), np.nan
    )
    panel["log1p_capacity_ceiling_rpm"] = np.log1p(
        panel["capacity_ceiling_rpm"].clip(lower=0)
    )
    panel["accounting_residual"] = panel["model_success_5m"] - (
        panel["success_5m"]
        + panel["same_provider_other_success_5m"]
        + panel["other_provider_success_5m"]
    )
    return panel


def _minutes_to_nearest(timestamp: pd.Timestamp, candidates: np.ndarray) -> float:
    if not len(candidates):
        return np.inf
    value = int(timestamp.value)
    position = int(np.searchsorted(candidates, value))
    distances: list[int] = []
    if position < len(candidates):
        distances.append(abs(int(candidates[position]) - value))
    if position:
        distances.append(abs(int(candidates[position - 1]) - value))
    return min(distances) / 60_000_000_000 if distances else np.inf


def event_registry(panel: pd.DataFrame) -> pd.DataFrame:
    """Classify high and low onsets without consulting post-event outcomes."""
    if panel.empty:
        return pd.DataFrame()
    base = panel[
        panel["rate_limit_onset"]
        & panel["attempt_proxy_5m"].ge(MIN_ATTEMPT_PROXY)
        & ~panel["is_deranked"]
    ].copy()
    high = base[
        base["rate_limited_5m"].ge(HIGH_MIN_RATE_LIMITED)
        & base["rate_limit_share_5m"].ge(HIGH_MIN_SHARE)
    ].copy()
    low = base[
        base["rate_limited_5m"].gt(0)
        & base["rate_limit_share_5m"].le(LOW_MAX_SHARE)
    ].copy()
    if high.empty and low.empty:
        return pd.DataFrame()

    high = high.sort_values(["model_permaslug", "ts", "endpoint_uuid"])
    high["simultaneous_high_onsets"] = high.groupby(
        ["run_ts", "model_permaslug"], dropna=False
    )["endpoint_uuid"].transform("size")
    grouped = high.groupby("model_permaslug", dropna=False, sort=False)
    high["minutes_since_previous_high"] = (
        high["ts"] - grouped["ts"].shift()
    ).dt.total_seconds() / 60
    high["minutes_until_next_high"] = (
        grouped["ts"].shift(-1) - high["ts"]
    ).dt.total_seconds() / 60
    high["analysis_eligible"] = (
        high["simultaneous_high_onsets"].eq(1)
        & high["minutes_since_previous_high"].fillna(np.inf).gt(ISOLATION_MINUTES)
        & high["minutes_until_next_high"].fillna(np.inf).gt(ISOLATION_MINUTES)
    )
    high["exclusion_reason"] = np.select(
        [
            high["simultaneous_high_onsets"].gt(1),
            high["minutes_since_previous_high"].fillna(np.inf).le(ISOLATION_MINUTES),
            high["minutes_until_next_high"].fillna(np.inf).le(ISOLATION_MINUTES),
        ],
        ["simultaneous_high", "previous_high_within_60m", "next_high_within_60m"],
        default="eligible",
    )
    high["event_class"] = "high"

    high_times: dict[str, np.ndarray] = {
        str(model): np.sort(group["ts"].astype("int64").to_numpy())
        for model, group in high.groupby("model_permaslug", dropna=False)
    }
    low = low.sort_values(["model_permaslug", "ts", "endpoint_uuid"]).copy()
    low["minutes_to_nearest_high"] = [
        _minutes_to_nearest(row.ts, high_times.get(str(row.model_permaslug), np.array([])))
        for row in low.itertuples(index=False)
    ]
    low["analysis_eligible"] = low["minutes_to_nearest_high"].gt(ISOLATION_MINUTES)
    low["exclusion_reason"] = np.where(
        low["analysis_eligible"], "eligible_before_thinning", "high_within_60m"
    )
    # Deterministic greedy thinning uses time and model only, never outcomes.
    for _, indices in low.groupby("model_permaslug", dropna=False, sort=False).groups.items():
        last: pd.Timestamp | None = None
        for index in sorted(indices, key=lambda idx: low.at[idx, "ts"]):
            if not bool(low.at[index, "analysis_eligible"]):
                continue
            current = low.at[index, "ts"]
            if last is None or (current - last).total_seconds() / 60 > ISOLATION_MINUTES:
                last = current
            else:
                low.at[index, "analysis_eligible"] = False
                low.at[index, "exclusion_reason"] = "greedy_low_thinning_60m"
    low["event_class"] = "low"
    low["simultaneous_high_onsets"] = 0
    low["minutes_since_previous_high"] = np.nan
    low["minutes_until_next_high"] = np.nan

    events = pd.concat([high, low], ignore_index=True, sort=False)
    events["event_id"] = (
        events["event_class"].astype(str)
        + "|"
        + events["run_ts"].astype(str)
        + "|"
        + events["model_permaslug"].astype(str)
        + "|"
        + events["endpoint_uuid"].astype(str)
    )
    columns = [
        "event_id",
        "event_class",
        "event_ts",
        "run_ts",
        "dt",
        *KEY_COLUMNS,
        "rate_limited_5m",
        "success_5m",
        "attempt_proxy_5m",
        "rate_limit_share_5m",
        "simultaneous_high_onsets",
        "minutes_since_previous_high",
        "minutes_until_next_high",
        "minutes_to_nearest_high",
        "analysis_eligible",
        "exclusion_reason",
    ]
    events["event_ts"] = events["ts"]
    for column in columns:
        if column not in events:
            events[column] = np.nan
    return events.loc[:, columns].sort_values(["event_ts", "event_class", "event_id"])


def build_event_time_panel(panel: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Select the nearest public snapshot for each frozen five-minute cell."""
    if panel.empty or events.empty:
        return pd.DataFrame()
    eligible = events[events["analysis_eligible"].astype(bool)].copy()
    if eligible.empty:
        return pd.DataFrame()
    groups = {
        tuple(key if isinstance(key, tuple) else (key,)): group.sort_values("ts")
        for key, group in panel.groupby(KEY_COLUMNS, dropna=False, sort=False)
    }
    records: list[pd.DataFrame] = []
    keep = [
        "run_ts",
        "ts",
        "success_5m",
        "attempt_proxy_5m",
        "rate_limited_5m",
        "rate_limit_share_5m",
        "endpoint_success_share",
        "provider_success_share",
        "endpoint_attempt_share",
        "same_provider_other_success_5m",
        "other_provider_success_5m",
        "model_success_5m",
        "model_attempt_5m",
        "log1p_endpoint_success",
        "log1p_same_provider_other_success",
        "log1p_other_provider_success",
        "log1p_model_success",
        "price_completion",
        "log_price_completion",
        "capacity_ceiling_rpm",
        "log1p_capacity_ceiling_rpm",
        "accounting_residual",
    ]
    for event in eligible.itertuples(index=False):
        key = (event.model_permaslug, event.endpoint_uuid, event.provider_name)
        path = groups.get(key)
        if path is None or path.empty:
            continue
        relative = (path["ts"] - event.event_ts).dt.total_seconds() / 60
        window = path[relative.between(EVENT_GRID.min() - 2.5, EVENT_GRID.max() + 2.5)].copy()
        if window.empty:
            continue
        window["relative_minutes_exact"] = relative.loc[window.index]
        window["relative_minutes"] = (
            np.floor((window["relative_minutes_exact"] + 2.5) / 5) * 5
        ).astype(int)
        window["cell_error_minutes"] = (
            window["relative_minutes_exact"] - window["relative_minutes"]
        ).abs()
        window = window[
            window["relative_minutes"].isin(EVENT_GRID)
            & window["cell_error_minutes"].le(2.5 + 1e-12)
        ]
        if window.empty:
            continue
        window = (
            window.sort_values(["relative_minutes", "cell_error_minutes", "ts"])
            .drop_duplicates("relative_minutes", keep="first")
            .copy()
        )
        selected = window.loc[
            :,
            keep + ["relative_minutes_exact", "relative_minutes", "cell_error_minutes"],
        ]
        selected.insert(0, "event_id", event.event_id)
        selected.insert(1, "event_class", event.event_class)
        selected.insert(2, "event_ts", event.event_ts)
        selected.insert(3, "model_permaslug", event.model_permaslug)
        selected.insert(4, "endpoint_uuid", event.endpoint_uuid)
        selected.insert(5, "provider_name", event.provider_name)
        records.append(selected)
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


def _window_mean(group: pd.DataFrame, metric: str, bounds: tuple[int, int]) -> float:
    values = group.loc[group["relative_minutes"].between(*bounds), metric]
    mean = values.mean()
    return float(mean) if pd.notna(mean) else np.nan


def event_effects(event_time: pd.DataFrame) -> pd.DataFrame:
    """Collapse event paths to pre/post and placebo contrasts."""
    if event_time.empty:
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for event_id, group in event_time.groupby("event_id", sort=False):
        first = group.iloc[0]
        pre_rows = group[group["relative_minutes"].between(*PRIMARY_PRE)]
        post_rows = group[group["relative_minutes"].between(*PRIMARY_POST)]
        record: dict[str, Any] = {
            "event_id": event_id,
            "event_class": first["event_class"],
            "event_ts": first["event_ts"],
            "model_permaslug": first["model_permaslug"],
            "endpoint_uuid": first["endpoint_uuid"],
            "provider_name": first["provider_name"],
            "pre_cells": int(pre_rows["relative_minutes"].nunique()),
            "post_cells": int(post_rows["relative_minutes"].nunique()),
        }
        record["complete_event"] = bool(
            record["pre_cells"] >= MIN_PRE_CELLS
            and record["post_cells"] >= MIN_POST_CELLS
            and pre_rows["endpoint_success_share"].notna().sum() >= MIN_PRE_CELLS
            and post_rows["endpoint_success_share"].notna().sum() >= MIN_POST_CELLS
        )
        event_ts = pd.Timestamp(first["event_ts"])
        record["event_date"] = str(event_ts.date())
        record["event_hour_utc"] = int(event_ts.hour)
        record["cluster"] = f"{first['model_permaslug']}|{event_ts.date()}"
        record["pre_log1p_model_attempt"] = float(np.log1p(pre_rows["model_attempt_5m"].mean()))
        record["accounting_residual_max"] = float(group["accounting_residual"].abs().max())
        prices = group.loc[
            group["relative_minutes"].between(PRIMARY_PRE[0], PRIMARY_POST[1]),
            "price_completion",
        ].dropna()
        if len(prices) >= 2:
            tolerance = max(1e-12, abs(float(prices.mean())) * 1e-9)
            record["price_sticky"] = bool(float(prices.max() - prices.min()) <= tolerance)
        else:
            record["price_sticky"] = np.nan
        for metric in OUTCOME_METRICS + RAW_ACCOUNTING_METRICS:
            pre = _window_mean(group, metric, PRIMARY_PRE)
            post = _window_mean(group, metric, PRIMARY_POST)
            early = _window_mean(group, metric, EARLY_PRE)
            late = _window_mean(group, metric, LATE_PRE)
            record[f"{metric}_pre"] = pre
            record[f"{metric}_post"] = post
            record[f"{metric}_delta"] = (
                post - pre if np.isfinite(pre) and np.isfinite(post) else np.nan
            )
            record[f"{metric}_placebo"] = (
                late - early if np.isfinite(early) and np.isfinite(late) else np.nan
            )
        records.append(record)
    return pd.DataFrame(records)


def match_negative_controls(effects: pd.DataFrame) -> pd.DataFrame:
    """Match high to low onsets within model using pre-treatment covariates only."""
    columns = [
        "high_event_id",
        "low_event_id",
        "model_permaslug",
        "match_score",
        *[f"{metric}_high_minus_low" for metric in PRIMARY_METRICS],
    ]
    complete = effects[effects["complete_event"].astype(bool)].copy()
    high = complete[complete["event_class"].eq("high")].sort_values("event_ts")
    low = complete[complete["event_class"].eq("low")].copy()
    if high.empty or low.empty:
        return pd.DataFrame(columns=columns)
    used: set[str] = set()
    rows: list[dict[str, Any]] = []
    for focal in high.itertuples(index=False):
        candidates = low[
            low["model_permaslug"].eq(focal.model_permaslug)
            & ~low["event_id"].isin(used)
        ].copy()
        if candidates.empty:
            continue
        day_distance = (
            pd.to_datetime(candidates["event_ts"], utc=True) - pd.Timestamp(focal.event_ts)
        ).abs().dt.total_seconds() / 86_400
        hour_distance = (candidates["event_hour_utc"] - focal.event_hour_utc).abs()
        hour_distance = np.minimum(hour_distance, 24 - hour_distance)
        candidates["match_score"] = (
            (candidates["pre_log1p_model_attempt"] - focal.pre_log1p_model_attempt).abs()
            + hour_distance / 12
            + day_distance / 7
        )
        chosen = candidates.sort_values(["match_score", "event_ts", "event_id"]).iloc[0]
        used.add(str(chosen["event_id"]))
        record: dict[str, Any] = {
            "high_event_id": focal.event_id,
            "low_event_id": chosen["event_id"],
            "model_permaslug": focal.model_permaslug,
            "match_score": float(chosen["match_score"]),
            "cluster": focal.cluster,
        }
        for metric in PRIMARY_METRICS:
            record[f"{metric}_high_minus_low"] = float(
                getattr(focal, f"{metric}_delta") - chosen[f"{metric}_delta"]
            )
        rows.append(record)
    frame = pd.DataFrame(rows)
    for column in columns:
        if column not in frame:
            frame[column] = np.nan
    return frame


def cluster_mean_interval(
    frame: pd.DataFrame,
    column: str,
    *,
    cluster_column: str = "cluster",
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Cluster bootstrap a mean with deterministic resampling."""
    sample = frame.loc[:, [column, cluster_column]].dropna()
    if sample.empty:
        return {
            "n_events": 0,
            "n_clusters": 0,
            "mean": None,
            "ci95": [None, None],
            "bootstrap_sign_p": None,
        }
    grouped = sample.groupby(cluster_column, sort=False)[column]
    sums = grouped.sum().to_numpy(dtype=float)
    counts = grouped.size().to_numpy(dtype=float)
    estimate = float(sample[column].mean())
    if len(sums) == 1 or draws <= 0:
        return {
            "n_events": int(len(sample)),
            "n_clusters": int(len(sums)),
            "mean": estimate,
            "ci95": [None, None],
            "bootstrap_sign_p": None,
        }
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(sums), size=(draws, len(sums)))
    sampled = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    ci = np.quantile(sampled, [0.025, 0.975])
    sign_p = min(1.0, 2 * min(float((sampled <= 0).mean()), float((sampled >= 0).mean())))
    return {
        "n_events": int(len(sample)),
        "n_clusters": int(len(sums)),
        "mean": estimate,
        "ci95": [float(ci[0]), float(ci[1])],
        "bootstrap_sign_p": float(sign_p),
    }


def daily_coverage(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame(
            columns=["dt", "snapshots", "rows", "endpoints", "span_hours", "complete_day"]
        )
    frame = panel.copy()
    frame["date"] = frame["ts"].dt.strftime("%Y-%m-%d")
    daily = (
        frame.groupby("date", as_index=False)
        .agg(
            snapshots=("run_ts", "nunique"),
            rows=("run_ts", "size"),
            endpoints=("endpoint_uuid", "nunique"),
            min_ts=("ts", "min"),
            max_ts=("ts", "max"),
        )
        .rename(columns={"date": "dt"})
    )
    daily["span_hours"] = (daily["max_ts"] - daily["min_ts"]).dt.total_seconds() / 3600
    daily["complete_day"] = daily["span_hours"].ge(20) & daily["snapshots"].ge(144)
    return daily.loc[:, ["dt", "snapshots", "rows", "endpoints", "span_hours", "complete_day"]]


def _model_equal_mean(frame: pd.DataFrame, column: str) -> float | None:
    sample = frame.loc[:, ["model_permaslug", column]].dropna()
    if sample.empty:
        return None
    return float(sample.groupby("model_permaslug")[column].mean().mean())


def _leave_one_provider_out(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    values = []
    for provider in frame["provider_name"].dropna().unique():
        estimate = frame.loc[~frame["provider_name"].eq(provider), column].mean()
        if pd.notna(estimate):
            values.append(float(estimate))
    return {
        "n_omissions": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def summarize(
    panel: pd.DataFrame,
    events: pd.DataFrame,
    event_time: pd.DataFrame,
    effects: pd.DataFrame,
    matches: pd.DataFrame,
    coverage: pd.DataFrame,
) -> dict[str, Any]:
    if panel.empty:
        return {
            "evidence_status": "no_public_enforcement_rows",
            "claim_boundary": "No public enforcement observations were available.",
        }
    complete = effects[effects["complete_event"].astype(bool)] if not effects.empty else effects
    high = complete[complete["event_class"].eq("high")].copy() if not complete.empty else complete
    low = complete[complete["event_class"].eq("low")].copy() if not complete.empty else complete

    primary: dict[str, Any] = {}
    placebo_passes: dict[str, bool] = {}
    matched_sign_passes: dict[str, bool] = {}
    for offset, metric in enumerate(PRIMARY_METRICS):
        delta = cluster_mean_interval(high, f"{metric}_delta", seed=BOOTSTRAP_SEED + offset)
        placebo = cluster_mean_interval(
            high, f"{metric}_placebo", seed=BOOTSTRAP_SEED + 100 + offset
        )
        matched = cluster_mean_interval(
            matches,
            f"{metric}_high_minus_low",
            seed=BOOTSTRAP_SEED + 200 + offset,
        )
        ci = placebo["ci95"]
        interval_contains_zero = bool(
            ci[0] is not None and ci[0] <= 0 <= ci[1]
        )
        ratio = (
            abs(float(placebo["mean"])) / abs(float(delta["mean"]))
            if delta["mean"] not in (None, 0) and placebo["mean"] is not None
            else None
        )
        placebo_passes[metric] = bool(
            interval_contains_zero and ratio is not None and ratio < 0.20
        )
        matched_sign_passes[metric] = bool(
            delta["mean"] is not None
            and matched["mean"] is not None
            and np.sign(delta["mean"]) == np.sign(matched["mean"])
        )
        primary[metric] = {
            "high_event_delta": delta,
            "early_vs_late_pre_placebo": placebo,
            "placebo_to_effect_abs_ratio": ratio,
            "model_equal_weighted_delta": _model_equal_mean(high, f"{metric}_delta"),
            "matched_high_minus_low_delta": matched,
            "leave_one_provider_out": _leave_one_provider_out(high, f"{metric}_delta")
            if not high.empty
            else {"n_omissions": 0, "min": None, "max": None},
        }

    accounting: dict[str, Any] = {}
    for metric in RAW_ACCOUNTING_METRICS:
        column = f"{metric}_delta"
        values = high[column].dropna() if not high.empty else pd.Series(dtype=float)
        if len(values):
            low_q, high_q = values.quantile([0.01, 0.99])
            winsorized = float(values.clip(low_q, high_q).mean())
        else:
            winsorized = None
        accounting[metric] = {
            "mean_delta": float(values.mean()) if len(values) else None,
            "winsorized_mean_delta": winsorized,
        }
    flow_identity_delta = None
    if all(accounting[metric]["mean_delta"] is not None for metric in RAW_ACCOUNTING_METRICS):
        flow_identity_delta = float(
            accounting["model_success_5m"]["mean_delta"]
            - accounting["success_5m"]["mean_delta"]
            - accounting["same_provider_other_success_5m"]["mean_delta"]
            - accounting["other_provider_success_5m"]["mean_delta"]
        )
    focal_change = accounting.get("success_5m", {}).get("mean_delta")
    rival_change = accounting.get("other_provider_success_5m", {}).get("mean_delta")
    diversion_ratio = (
        float(rival_change / -focal_change)
        if focal_change is not None and rival_change is not None and focal_change < 0
        else None
    )

    event_counts = (
        high["provider_name"].value_counts() if not high.empty else pd.Series(dtype=int)
    )
    provider_dominance = float(event_counts.iloc[0] / len(high)) if len(high) else None
    accounting_max = (
        float(event_time["accounting_residual"].abs().max())
        if not event_time.empty
        else None
    )
    span_days = (panel["ts"].max() - panel["ts"].min()).total_seconds() / 86_400
    gate = {
        "min_complete_high_events": {"required": 100, "observed": int(len(high))},
        "min_complete_days": {
            "required": 28,
            "observed": int(coverage["complete_day"].sum()) if not coverage.empty else 0,
        },
        "min_models": {
            "required": 20,
            "observed": int(high["model_permaslug"].nunique()) if not high.empty else 0,
        },
        "min_providers": {
            "required": 20,
            "observed": int(high["provider_name"].nunique()) if not high.empty else 0,
        },
        "max_provider_dominance": {"required": 0.20, "observed": provider_dominance},
        "primary_placebo_passes": placebo_passes,
        "matched_sign_passes": matched_sign_passes,
        "accounting_residual_max": {"required": 1e-9, "observed": accounting_max},
    }
    gate_pass = bool(
        len(high) >= 100
        and (int(coverage["complete_day"].sum()) if not coverage.empty else 0) >= 28
        and (high["model_permaslug"].nunique() if not high.empty else 0) >= 20
        and (high["provider_name"].nunique() if not high.empty else 0) >= 20
        and provider_dominance is not None
        and provider_dominance <= 0.20
        and all(placebo_passes.values())
        and all(matched_sign_passes.values())
        and accounting_max is not None
        and accounting_max <= 1e-9
    )
    price_sticky_share = (
        float(high["price_sticky"].dropna().mean())
        if not high.empty and high["price_sticky"].notna().any()
        else None
    )
    return {
        "evidence_status": (
            "confirmatory_event_study_gate_passed"
            if gate_pass
            else "descriptive_enforcement_substitution_power_gated"
        ),
        "preregistration": "docs/h82-enforcement-substitution-preregistration.md",
        "observed_span_days": float(span_days),
        "n_panel_rows": int(len(panel)),
        "n_candidate_high_onsets": int(events["event_class"].eq("high").sum())
        if not events.empty
        else 0,
        "n_eligible_high_onsets": int(
            (events["event_class"].eq("high") & events["analysis_eligible"].astype(bool)).sum()
        )
        if not events.empty
        else 0,
        "n_complete_high_events": int(len(high)),
        "n_complete_low_events": int(len(low)),
        "n_matched_high_low_pairs": int(len(matches)),
        "high_event_models": int(high["model_permaslug"].nunique()) if not high.empty else 0,
        "high_event_providers": int(high["provider_name"].nunique()) if not high.empty else 0,
        "provider_event_dominance": provider_dominance,
        "price_sticky_share": price_sticky_share,
        "primary_results": primary,
        "flow_accounting": {
            **accounting,
            "mean_identity_residual": flow_identity_delta,
            "maximum_snapshot_identity_residual": accounting_max,
            "other_provider_diversion_ratio_when_focal_declines": diversion_ratio,
        },
        "release_gate": {**gate, "all_pass": gate_pass},
        "claim_boundary": (
            "H82 is an observational event study of public rolling aggregates. Rate-limit "
            "onsets are endogenous to load and may share latent causes with routing volume. "
            "The data do not reveal request ordering, customer identity, private eligibility, "
            "router intent, front-running, or the welfare effect of capacity certification."
        ),
    }


def plot_event_paths(event_time: pd.DataFrame, out_dir: Path) -> None:
    if event_time.empty:
        return
    metrics = [
        ("endpoint_success_share", "Focal endpoint success share"),
        ("provider_success_share", "Focal provider success share"),
        ("log1p_other_provider_success", "log1p other-provider successes"),
        ("log_price_completion", "Log completion price"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for axis, (metric, title) in zip(axes.flat, metrics, strict=True):
        for event_class, color in [("high", "#B23A48"), ("low", "#3572A5")]:
            subset = event_time[event_time["event_class"].eq(event_class)]
            path = subset.groupby("relative_minutes")[metric].agg(["mean", "std", "count"])
            if path.empty:
                continue
            se = path["std"] / np.sqrt(path["count"].clip(lower=1))
            axis.plot(path.index, path["mean"], marker="o", ms=3, label=event_class, color=color)
            axis.fill_between(
                path.index.to_numpy(dtype=float),
                (path["mean"] - 1.96 * se).to_numpy(dtype=float),
                (path["mean"] + 1.96 * se).to_numpy(dtype=float),
                color=color,
                alpha=0.13,
            )
        axis.axvline(0, color="black", lw=1, ls="--")
        axis.axvspan(PRIMARY_POST[0], PRIMARY_POST[1], color="#999999", alpha=0.08)
        axis.set_title(title)
        axis.grid(alpha=0.2)
    axes[1, 0].set_xlabel("Minutes from rate-limit onset")
    axes[1, 1].set_xlabel("Minutes from rate-limit onset")
    axes[0, 0].legend(frameon=False)
    fig.suptitle("H82 public enforcement event paths (descriptive 95% event-level SE bands)")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h82_enforcement_substitution.png", dpi=180)
    fig.savefig(out_dir / "h82_enforcement_substitution.pdf")
    plt.close(fig)


def analyze(rows: pd.DataFrame, out_dir: Path | None = None) -> dict[str, Any]:
    panel = canonical_panel(rows)
    events = event_registry(panel)
    event_time = build_event_time_panel(panel, events)
    effects = event_effects(event_time)
    matches = match_negative_controls(effects)
    coverage = daily_coverage(panel)
    result = summarize(panel, events, event_time, effects, matches, coverage)
    if out_dir is not None:
        save(events, out_dir, "h82_enforcement_event_registry")
        save(event_time, out_dir, "h82_enforcement_event_time")
        save(effects, out_dir, "h82_enforcement_event_effects")
        save(matches, out_dir, "h82_enforcement_negative_control_matches")
        save(coverage, out_dir, "h82_enforcement_daily_coverage")
        save_json(result, out_dir, "h82_summary")
        plot_event_paths(event_time, out_dir)
    return result


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    return analyze(load_rows(), out_dir)
