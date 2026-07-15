"""BM3 — Brown-MacKay cadence premium, with public quality adjustment."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .bm_common import completion_events, load_gates, panel_span_days, provider_cadence
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes


def quote_quality_panel(out_dir: Path) -> pd.DataFrame:
    """Join daily prices to the same delivered-quality panel used by H11."""
    path = out_dir / "h11_endpoint_quality.parquet"
    if path.exists():
        quality = pd.read_parquet(path)
    else:
        from .h11_quality import load_quality

        quality = load_quality()
    collapsed = (
        quality.groupby(["model_permaslug", "provider_name"], as_index=False)
        .agg(
            throughput=("tok_s", "median"),
            latency=("latency", "median"),
            tool_err=("tool_err", "mean"),
            struct_err=("struct_err", "mean"),
        )
    )
    # canonical slug is the key used by effective-pricing and performance panels.
    quotes = daily_quotes()
    collapsed = collapsed.rename(columns={"model_permaslug": "model_id"})
    return quotes.merge(collapsed, on=["model_id", "provider_name"], how="left")


def fit_within(panel: pd.DataFrame, quality_adjusted: bool) -> dict:
    """Within-model-day OLS with model-clustered uncertainty."""
    import statsmodels.api as sm

    work = panel.copy()
    work["log_price"] = np.log(work["price"])
    regressors = ["is_fast"]
    if quality_adjusted:
        work["log_throughput"] = np.log1p(pd.to_numeric(work["throughput"], errors="coerce"))
        work["log_latency"] = np.log1p(pd.to_numeric(work["latency"], errors="coerce"))
        work["tool_err"] = pd.to_numeric(work["tool_err"], errors="coerce")
        work["struct_err"] = pd.to_numeric(work["struct_err"], errors="coerce")
        regressors += ["log_throughput", "log_latency", "tool_err", "struct_err"]
    group = work.groupby(["model_id", "dt"])
    for column in ["log_price", *regressors]:
        work[f"{column}_dm"] = work[column] - group[column].transform("mean")
    y = work["log_price_dm"]
    xcols = [f"{column}_dm" for column in regressors]
    valid = work[xcols].notna().all(axis=1) & y.notna()
    work = work[valid]
    if len(work) < 20 or work["is_fast"].nunique() < 2:
        return {
            "n_obs": int(len(work)),
            "n_cadence_classes": int(work["is_fast"].nunique()),
            "error": "complete delivered-quality sample lacks mixed-cadence overlap",
        }
    fit = sm.OLS(work["log_price_dm"], work[xcols], hasconst=False).fit(
        cov_type="cluster", cov_kwds={"groups": work["model_id"]}
    )
    coef = float(fit.params["is_fast_dm"])
    se = float(fit.bse["is_fast_dm"])
    return {
        "n_obs": int(len(work)),
        "n_models": int(work["model_id"].nunique()),
        "beta_fast": coef,
        "se": se,
        "ci95": [coef - 1.96 * se, coef + 1.96 * se],
        "slow_over_fast_premium_pct": 100 * (np.exp(-coef) - 1),
        "r2_within": float(fit.rsquared),
        "all_coefficients": {str(key): float(value) for key, value in fit.params.items()},
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    events = completion_events()
    prices_and_quality = quote_quality_panel(out_dir)
    cadence_path = out_dir / "bm1_provider_cadence.parquet"
    cadence = (
        pd.read_parquet(cadence_path)
        if cadence_path.exists()
        else provider_cadence(events, set(prices_and_quality["provider_name"].dropna()))
    )
    panel = prices_and_quality.merge(
        cadence[["provider_name", "cadence_class", "is_fast"]],
        on="provider_name",
        how="inner",
    )
    group = panel.groupby(["model_id", "dt"])
    panel = panel[
        group["provider_name"].transform("size").ge(2)
        & group["is_fast"].transform("nunique").gt(1)
    ].copy()
    basic = fit_within(panel, False)
    adjusted = fit_within(panel, True)
    rows = []
    for specification, result in (("cadence_only", basic), ("quality_adjusted", adjusted)):
        if "beta_fast" in result:
            rows.append(
                {
                    "specification": specification,
                    "beta_fast": result["beta_fast"],
                    "se": result["se"],
                    "ci95_low": result["ci95"][0],
                    "ci95_high": result["ci95"][1],
                    "slow_over_fast_premium_pct": result["slow_over_fast_premium_pct"],
                    "n_obs": result["n_obs"],
                    "n_models": result["n_models"],
                }
            )
    save(pd.DataFrame(rows), out_dir, "bm3_premium_coefficients")
    span = panel_span_days(events)
    min_days = load_gates()["brown_mackay"]["min_panel_days"]
    summary = {
        "evidence_status": "provisional_descriptive" if span >= min_days else "power_gated",
        "panel_span_days": round(span, 2),
        "cadence_only": basic,
        "quality_adjusted": adjusted,
        "claim_boundary": (
            "The regression absorbs model-day price levels and public delivered latency, "
            "throughput, tool-call error, and structured-output error. It does not observe all "
            "endpoint fidelity, private discounts, costs, or "
            "endogenous "
            "adoption of fast repricing, so the coefficient is not a causal technology effect."
        ),
    }
    save_json(summary, out_dir, "bm3_summary")
    return summary
