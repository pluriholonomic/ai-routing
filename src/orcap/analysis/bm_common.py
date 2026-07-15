"""Shared data preparation for the Brown-MacKay inference-market tests."""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from . import data

GATE_FILE = Path("config/welfare_conjecture_gates.toml")


def load_gates(path: Path = GATE_FILE) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def completion_events() -> pd.DataFrame:
    """Return deduplicated positive completion-price changes with UTC timestamps."""
    glob = data.table_glob("pricing_changes", layer="derived")
    frame = data.q(
        f"""
        select distinct changed_at_run_ts, cast(dt as varchar) as dt,
               model_id, provider_name,
               try_cast(old_value as double) as old_price,
               try_cast(new_value as double) as new_price
        from read_parquet('{glob}', union_by_name=true)
        where field = 'price_completion' and model_id not like '%:%'
          and try_cast(old_value as double) > 0
          and try_cast(new_value as double) > 0
          and try_cast(old_value as double) != try_cast(new_value as double)
        """
    ).df()
    if frame.empty:
        return frame
    frame["ts"] = pd.to_datetime(
        frame["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame = frame.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    frame["dlog_price"] = np.log(frame["new_price"] / frame["old_price"])
    frame["direction"] = np.sign(frame["dlog_price"]).astype(int)
    return frame


def panel_span_days(events: pd.DataFrame) -> float:
    if len(events) < 2:
        return 0.0
    return float((events["ts"].max() - events["ts"].min()).total_seconds() / 86400)


def classify_cadence(
    n_changes: int,
    changes_per_day: float,
    median_gap_hours: float | None,
) -> str:
    """Pre-registered cadence ladder; callable directly in recovery tests."""
    gap = float(median_gap_hours) if median_gap_hours is not None else np.inf
    if np.isnan(gap):
        gap = np.inf
    if n_changes <= 0:
        return "inactive"
    if gap <= 6 or changes_per_day >= 2:
        return "intraday"
    if gap <= 36 or changes_per_day >= 0.5:
        return "daily"
    if gap <= 9 * 24 or changes_per_day >= 0.1:
        return "weekly"
    return "episodic"


def provider_cadence(
    events: pd.DataFrame, providers: set[str] | list[str] | None = None
) -> pd.DataFrame:
    """Estimate each provider's observable update technology."""
    columns = [
        "provider_name",
        "n_changes",
        "active_models",
        "changes_per_day",
        "median_gap_hours",
        "clock_hour_concentration",
        "clock_hour_entropy",
        "cadence_class",
        "is_fast",
    ]
    provider_universe = set(providers or [])
    if events.empty:
        rows = [
            {
                "provider_name": provider,
                "n_changes": 0,
                "active_models": 0,
                "changes_per_day": 0.0,
                "median_gap_hours": np.nan,
                "clock_hour_concentration": np.nan,
                "clock_hour_entropy": np.nan,
                "cadence_class": "inactive",
                "is_fast": False,
            }
            for provider in sorted(provider_universe)
        ]
        return pd.DataFrame(rows, columns=columns)
    span = max(panel_span_days(events), 1.0)
    rows = []
    for provider, group in events.groupby("provider_name"):
        ordered = group.sort_values("ts")
        gaps = ordered["ts"].diff().dt.total_seconds().div(3600).dropna()
        counts = ordered["ts"].dt.hour.value_counts()
        probs = counts / counts.sum()
        entropy = float(-(probs * np.log(probs)).sum() / np.log(24)) if len(probs) > 1 else 0.0
        rate = len(ordered) / span
        median_gap = float(gaps.median()) if len(gaps) else np.nan
        cadence = classify_cadence(len(ordered), rate, median_gap)
        rows.append(
            {
                "provider_name": provider,
                "n_changes": int(len(ordered)),
                "active_models": int(ordered["model_id"].nunique()),
                "changes_per_day": float(rate),
                "median_gap_hours": median_gap,
                "clock_hour_concentration": float(probs.max()),
                "clock_hour_entropy": entropy,
                "cadence_class": cadence,
                "is_fast": cadence in {"intraday", "daily"},
            }
        )
    observed = set(events["provider_name"])
    for provider in sorted(provider_universe - observed):
        rows.append(
            {
                "provider_name": provider,
                "n_changes": 0,
                "active_models": 0,
                "changes_per_day": 0.0,
                "median_gap_hours": np.nan,
                "clock_hour_concentration": np.nan,
                "clock_hour_entropy": np.nan,
                "cadence_class": "inactive",
                "is_fast": False,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["changes_per_day", "n_changes"], ascending=False
    )


def independent_waves(events: pd.DataFrame, window_hours: float = 6) -> pd.DataFrame:
    """Thin clusters to initiating model-level waves separated by ``window_hours``."""
    if events.empty:
        return events.copy()
    keep: list[int] = []
    gap = pd.to_timedelta(float(window_hours) * 3600, unit="s")
    for _, group in events.sort_values("ts").groupby("model_id", sort=False):
        last = None
        for idx, row in group.iterrows():
            if last is None or row["ts"] - last >= gap:
                keep.append(idx)
                last = row["ts"]
    return events.loc[keep].sort_values("ts").reset_index(drop=True)


def evidence_status(observed: float, required: float, *, positive: bool = True) -> str:
    if not positive or observed <= 0:
        return "not_collected"
    return "provisional_descriptive" if observed >= required else "power_gated"
