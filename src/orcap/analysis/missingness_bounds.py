"""Distribution-free mean bounds for partially observed secondary outcomes."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def bounded_mean(
    values: pd.Series,
    *,
    lower: float = 0.0,
    upper: float | pd.Series | None = None,
) -> dict[str, Any]:
    """Bound a mean by assigning missing rows to prespecified support limits.

    If an upper support value is unavailable for any missing row, the upper
    mean bound is unidentified and returned as ``None``. Observed values that
    violate their recorded upper support also invalidate the upper bound.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    n = len(numeric)
    missing = numeric.isna()
    observed = numeric[~missing]
    if not n:
        return {
            "n": 0,
            "observed": 0,
            "missing": 0,
            "observed_mean": None,
            "mean_lower_bound": None,
            "mean_upper_bound": None,
            "upper_support_complete_for_missing": False,
            "observed_upper_support_violations": 0,
        }

    lower_mean = float((observed.sum() + missing.sum() * lower) / n)
    if upper is None:
        upper_values = pd.Series(np.nan, index=numeric.index, dtype=float)
    elif np.isscalar(upper):
        upper_values = pd.Series(float(upper), index=numeric.index, dtype=float)
    else:
        upper_values = pd.to_numeric(upper, errors="coerce").reindex(numeric.index)

    upper_support_complete = bool(not missing.any() or upper_values[missing].notna().all())
    observed_violations = int(
        (
            observed
            > upper_values.loc[observed.index].where(
                upper_values.loc[observed.index].notna(), np.inf
            )
        ).sum()
    )
    if not missing.any():
        upper_mean = float(observed.mean())
    elif upper_support_complete and not observed_violations:
        upper_mean = float((observed.sum() + upper_values[missing].sum()) / n)
    else:
        upper_mean = None
    return {
        "n": n,
        "observed": int((~missing).sum()),
        "missing": int(missing.sum()),
        "observed_mean": float(observed.mean()) if len(observed) else None,
        "mean_lower_bound": lower_mean,
        "mean_upper_bound": upper_mean,
        "upper_support_complete_for_missing": upper_support_complete,
        "observed_upper_support_violations": observed_violations,
    }


def difference_bounds(
    positive: dict[str, Any], negative: dict[str, Any]
) -> tuple[float | None, float | None]:
    """Return sharp rectangular bounds for a difference of bounded means."""
    pos_low = positive.get("mean_lower_bound")
    pos_high = positive.get("mean_upper_bound")
    neg_low = negative.get("mean_lower_bound")
    neg_high = negative.get("mean_upper_bound")
    lower = float(pos_low - neg_high) if pos_low is not None and neg_high is not None else None
    upper = float(pos_high - neg_low) if pos_high is not None and neg_low is not None else None
    return lower, upper
