"""Deterministic date-vintage helpers for confirmatory analyses."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd


def canonical_date(value: Any | None) -> str | None:
    """Return an ISO calendar date, rejecting unparseable bounds."""
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="raise", utc=True)
    return parsed.strftime("%Y-%m-%d")


def observed_dates(values: Iterable[Any]) -> list[str]:
    """Sorted unique ISO dates represented by ``values``."""
    parsed = pd.to_datetime(pd.Series(list(values)), errors="coerce", utc=True).dropna()
    return sorted(parsed.dt.strftime("%Y-%m-%d").unique().tolist())


def clip_date_range(
    frame: pd.DataFrame,
    *,
    date_col: str = "dt",
    start_date: Any | None = None,
    end_date: Any | None = None,
) -> pd.DataFrame:
    """Copy and clip a frame to inclusive ISO calendar-date bounds."""
    if frame.empty or (start_date is None and end_date is None):
        return frame.copy()
    if date_col not in frame:
        raise KeyError(f"date column {date_col!r} is absent")
    start = canonical_date(start_date)
    end = canonical_date(end_date)
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must not follow end_date")
    dates = pd.to_datetime(frame[date_col], errors="coerce", utc=True).dt.strftime(
        "%Y-%m-%d"
    )
    keep = dates.notna()
    if start is not None:
        keep &= dates >= start
    if end is not None:
        keep &= dates <= end
    clipped = frame.loc[keep].copy()
    clipped[date_col] = dates.loc[keep]
    return clipped.reset_index(drop=True)


def date_support(frame: pd.DataFrame, *, date_col: str = "dt") -> dict[str, Any]:
    """Outcome-free calendar support metadata for one analytical frame."""
    dates = observed_dates(frame[date_col]) if date_col in frame else []
    return {
        "observed_dates": dates,
        "n_observed_dates": len(dates),
        "start_date": dates[0] if dates else None,
        "end_date": dates[-1] if dates else None,
    }
