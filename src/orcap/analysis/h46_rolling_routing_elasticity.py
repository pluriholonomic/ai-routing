"""H46 — rolling within-market routing share-price elasticity.

H4's pooled daily panel establishes an average association. H46 fixes a
14-day trailing window and re-estimates the same within-(day, model, variant)
specification at each window end. It makes changes in observed routing-price
sensitivity visible without treating daily aggregates as individual requests
or price changes as exogenous shocks.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .common import DEFAULT_OUT, save, save_json
from .h4_routing import load_shares, within_demean

log = logging.getLogger(__name__)

WINDOW_DAYS = 14
MIN_WINDOW_OBSERVATIONS = 100
MIN_WINDOW_GROUPS = 30
MIN_WINDOWS = 4
PANEL_COLUMNS = [
    "window_start",
    "window_end",
    "n_days",
    "n_observations",
    "n_groups",
    "share_price_elasticity",
    "std_error",
    "ci95_low",
    "ci95_high",
    "p_value",
    "distance_to_inverse_square",
]


def rolling_elasticity(
    rows: pd.DataFrame,
    *,
    window_days: int = WINDOW_DAYS,
    min_observations: int = MIN_WINDOW_OBSERVATIONS,
    min_groups: int = MIN_WINDOW_GROUPS,
) -> pd.DataFrame:
    """Fit the H4 within-market specification on fixed trailing daily windows."""
    if rows.empty or window_days < 2:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    required = {"dt", "group", "share", "effective_output_price", "cache_hit_rate"}
    if not required.issubset(rows):
        return pd.DataFrame(columns=PANEL_COLUMNS)
    data = rows.copy()
    data["day"] = pd.to_datetime(data["dt"], utc=True, errors="coerce").dt.normalize()
    data["share"] = pd.to_numeric(data["share"], errors="coerce")
    data["effective_output_price"] = pd.to_numeric(
        data["effective_output_price"], errors="coerce"
    )
    data["cache_hit_rate"] = pd.to_numeric(data["cache_hit_rate"], errors="coerce")
    data = data.dropna(subset=["day", "group", "share", "effective_output_price"])
    data = data[(data["share"] > 0) & (data["effective_output_price"] > 0)]
    if data.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    rows_out = []
    for window_end_text in sorted(data["day"].dt.strftime("%Y-%m-%d").unique()):
        window_end = pd.Timestamp(window_end_text, tz="UTC")
        window_start = window_end - timedelta(days=int(window_days) - 1)
        window = data[(data["day"] >= window_start) & (data["day"] <= window_end)].copy()
        if window["day"].nunique() < window_days:
            continue
        fit = _fit_window(window, min_observations=min_observations, min_groups=min_groups)
        if fit is None:
            continue
        rows_out.append(
            {
                "window_start": str(window_start.date()),
                "window_end": str(window_end.date()),
                "n_days": int(window["day"].nunique()),
                **fit,
            }
        )
    return pd.DataFrame(rows_out, columns=PANEL_COLUMNS)


def _fit_window(
    rows: pd.DataFrame, *, min_observations: int, min_groups: int
) -> dict[str, float | int] | None:
    """Return a group-clustered H4 coefficient for one already fixed window."""
    data = rows.copy()
    data["log_share"] = np.log(data["share"])
    data["log_price"] = np.log(data["effective_output_price"])
    data["cache"] = data["cache_hit_rate"].fillna(0)
    data = within_demean(data, ["log_share", "log_price", "cache"])
    data = data.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["log_share_dm", "log_price_dm", "cache_dm", "group"]
    )
    n_groups = int(data["group"].nunique())
    if len(data) < min_observations or n_groups < min_groups:
        return None
    if data["log_price_dm"].abs().sum() == 0:
        return None
    try:
        fitted = smf.ols("log_share_dm ~ log_price_dm + cache_dm - 1", data=data).fit(
            cov_type="cluster", cov_kwds={"groups": data["group"]}
        )
    except (ValueError, np.linalg.LinAlgError) as exc:
        log.info("H46 window fit unavailable: %s", exc)
        return None
    elasticity = float(fitted.params["log_price_dm"])
    standard_error = float(fitted.bse["log_price_dm"])
    return {
        "n_observations": int(fitted.nobs),
        "n_groups": n_groups,
        "share_price_elasticity": elasticity,
        "std_error": standard_error,
        "ci95_low": elasticity - 1.96 * standard_error,
        "ci95_high": elasticity + 1.96 * standard_error,
        "p_value": float(fitted.pvalues["log_price_dm"]),
        "distance_to_inverse_square": elasticity + 2.0,
    }


def summarize(panel: pd.DataFrame, input_rows: pd.DataFrame | None = None) -> dict:
    coverage = _input_coverage(input_rows)
    if panel.empty:
        input_days = coverage["n_input_days"]
        return {
            "evidence_status": "power_gated" if input_days else "not_identified",
            "n_windows": 0,
            "input_coverage": coverage,
            "gate_reasons": (
                [f"only {input_days}/{WINDOW_DAYS} daily effective-pricing observations"]
                if input_days
                else ["no eligible daily multi-provider effective-pricing groups"]
            ),
            "claim_boundary": _claim_boundary(),
        }
    latest = panel.iloc[-1]
    reasons = []
    if len(panel) < MIN_WINDOWS:
        reasons.append(f"only {len(panel)}/{MIN_WINDOWS} full rolling windows")
    if int(latest["n_groups"]) < MIN_WINDOW_GROUPS:
        reasons.append(
            f"latest window has only {int(latest['n_groups'])}/{MIN_WINDOW_GROUPS} groups"
        )
    return {
        "evidence_status": "rolling_descriptive_association" if not reasons else "power_gated",
        "n_windows": int(len(panel)),
        "first_window_end": str(panel["window_end"].iloc[0]),
        "latest_window_end": str(latest["window_end"]),
        "latest_elasticity": float(latest["share_price_elasticity"]),
        "latest_std_error": float(latest["std_error"]),
        "latest_ci95": [float(latest["ci95_low"]), float(latest["ci95_high"])],
        "elasticity_range": [
            float(panel["share_price_elasticity"].min()),
            float(panel["share_price_elasticity"].max()),
        ],
        "input_coverage": coverage,
        "power_gate": {
            "window_days": WINDOW_DAYS,
            "min_observations_per_window": MIN_WINDOW_OBSERVATIONS,
            "min_groups_per_window": MIN_WINDOW_GROUPS,
            "min_full_windows": MIN_WINDOWS,
        },
        "gate_reasons": reasons,
        "claim_boundary": _claim_boundary(),
    }


def _input_coverage(rows: pd.DataFrame | None) -> dict[str, int]:
    if rows is None or rows.empty or "dt" not in rows:
        return {"n_input_observations": 0, "n_input_days": 0, "n_input_groups": 0}
    days = pd.to_datetime(rows["dt"], utc=True, errors="coerce")
    return {
        "n_input_observations": int(len(rows)),
        "n_input_days": int(days.dt.strftime("%Y-%m-%d").nunique()),
        "n_input_groups": int(rows["group"].nunique()) if "group" in rows else 0,
    }


def _claim_boundary() -> str:
    return (
        "Each point is the H4 within-(day, model, variant) association between daily "
        "effective output price and token share in a fixed trailing window, with cache-hit "
        "rate control and group-clustered standard errors. It is not an individual-request "
        "routing rule, a causal price elasticity, evidence that all users accept the router "
        "default, or a DeFi best-execution estimate."
    )


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_shares()
    panel = rolling_elasticity(rows)
    save(panel, out_dir, "h46_rolling_routing_elasticity")
    result = summarize(panel, rows)
    save_json(result, out_dir, "h46_summary")
    return result
