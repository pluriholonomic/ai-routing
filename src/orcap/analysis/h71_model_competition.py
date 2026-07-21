"""H71 — Model contestability and application-allocation explanatory screen.

The OpenRouter frontend exposes a short ranked list of apps for each model, but
does not document the counter's aggregation window.  H71 therefore separates
two jobs:

* a same-day descriptive ranking of *contestable* model markets, combining
  daily demand, supplier depth, and the shape of observed app allocation; and
* a strictly next-day, out-of-sample prediction screen asking whether the
  *shape* of an app's allocation adds information beyond model demand
  persistence.  Raw app-token totals are intentionally excluded from the
  headline test because their aggregation window is unknown and they may share
  accounting with the outcome.

The app data are top-N lists, not a complete application-by-model flow matrix.
All allocation measures are consequently labelled ``observed`` and must never
be interpreted as platform-wide app shares, causal routing effects, or realized
provider allocation.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.model_selection import GroupKFold

from . import data
from .common import DEFAULT_OUT, save, save_json
from .market_scope import paid_model_sql

log = logging.getLogger(__name__)

SHAPE_FEATURES = [
    "app_effective_n_observed",
    "app_portfolio_competition_observed",
]
BASE_FEATURES = ["log_lag_activity_tokens", "app_day_index"]


def _day(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def latest_complete_app_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep the most complete standard-model scrape for each calendar day.

    A failed/retried scrape can be later than the successful full scrape, so
    taking ``max(run_ts)`` alone silently turns a 300-model leader board into a
    two-model sample.  Completeness is the standard-model row count, then
    run timestamp breaks ties.
    """

    if frame.empty:
        return frame.copy()
    out = frame.copy()
    out["dt"] = out["dt"].map(_day)
    standard = out[(out["scope"] == "model") & (out["variant"] == "standard")].copy()
    coverage = (
        standard.groupby(["dt", "run_ts"], as_index=False)
        .size()
        .rename(columns={"size": "n_standard_app_rows"})
        .sort_values(["dt", "n_standard_app_rows", "run_ts"], ascending=[True, False, False])
    )
    winners = coverage.drop_duplicates("dt")[["dt", "run_ts"]]
    return standard.merge(winners, on=["dt", "run_ts"], how="inner")


def load_app_rows() -> pd.DataFrame:
    rows = data.q(
        f"""
        select dt, run_ts, model_permaslug, app_slug, app_title, rank,
               total_tokens, total_requests, scope, variant
        from {data.apps()}
        where scope = 'model' and variant = 'standard'
        """
    ).df()
    return latest_complete_app_rows(rows)


def allocation_metrics(app_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return observed app-to-model allocations and their model-level shape."""

    columns = [
        "dt",
        "model_permaslug",
        "app_slug",
        "app_title",
        "app_tokens_observed",
        "app_requests_observed",
        "model_app_share_observed",
        "app_model_share_observed",
        "app_portfolio_effective_models_observed",
        "app_portfolio_competition_component_observed",
    ]
    metric_columns = [
        "dt",
        "model_permaslug",
        "app_tokens_observed",
        "n_observed_apps",
        "top_app_share_observed",
        "app_hhi_observed",
        "app_effective_n_observed",
        "app_entropy_observed",
        "app_portfolio_competition_observed",
        "app_portfolio_effective_models_observed",
    ]
    if app_rows.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame(columns=metric_columns)

    a = app_rows.copy()
    a["dt"] = a["dt"].map(_day)
    a["total_tokens"] = pd.to_numeric(a["total_tokens"], errors="coerce")
    a["total_requests"] = pd.to_numeric(a["total_requests"], errors="coerce")
    a = a.dropna(subset=["model_permaslug", "app_slug", "total_tokens"])
    a = a[a["total_tokens"] > 0]
    # An app should occur once in a model's top-N list.  ``max`` is defensive
    # against source duplication and avoids counting the same counter twice.
    a = (
        a.groupby(["dt", "model_permaslug", "app_slug"], as_index=False)
        .agg(
            app_title=("app_title", "first"),
            app_tokens_observed=("total_tokens", "max"),
            app_requests_observed=("total_requests", "max"),
        )
        .copy()
    )
    a["model_observed_tokens"] = a.groupby(["dt", "model_permaslug"])[
        "app_tokens_observed"
    ].transform("sum")
    a["model_app_share_observed"] = a["app_tokens_observed"] / a["model_observed_tokens"]
    a["app_observed_tokens"] = a.groupby(["dt", "app_slug"])["app_tokens_observed"].transform(
        "sum"
    )
    a["app_model_share_observed"] = a["app_tokens_observed"] / a["app_observed_tokens"]
    a["app_portfolio_entropy"] = -a["app_model_share_observed"] * np.log(
        a["app_model_share_observed"].clip(lower=1e-15)
    )
    a["app_portfolio_effective_models_observed"] = np.exp(
        a.groupby(["dt", "app_slug"])["app_portfolio_entropy"].transform("sum")
    )
    # Higher means a model's observed apps also allocate material volume to
    # other observed models; it is a substitute-pressure proxy, not a flow share.
    a["app_portfolio_competition_component_observed"] = 1.0 - a["app_model_share_observed"]

    def _metrics(group: pd.DataFrame) -> pd.Series:
        shares = group["model_app_share_observed"].to_numpy(dtype=float)
        hhi = float(np.square(shares).sum())
        weights = shares
        return pd.Series(
            {
                "app_tokens_observed": float(group["app_tokens_observed"].sum()),
                "n_observed_apps": int(len(group)),
                "top_app_share_observed": float(shares.max()),
                "app_hhi_observed": hhi,
                "app_effective_n_observed": float(1.0 / hhi) if hhi > 0 else np.nan,
                "app_entropy_observed": float(-(shares * np.log(shares.clip(min=1e-15))).sum()),
                "app_portfolio_competition_observed": float(
                    np.average(
                        group["app_portfolio_competition_component_observed"], weights=weights
                    )
                ),
                "app_portfolio_effective_models_observed": float(
                    np.average(group["app_portfolio_effective_models_observed"], weights=weights)
                ),
            }
        )

    metrics = (
        a.groupby(["dt", "model_permaslug"], group_keys=False)
        .apply(_metrics, include_groups=False)
        .reset_index()
    )
    return a[columns], metrics[metric_columns]


def activity_panel() -> pd.DataFrame:
    frame = data.q(
        f"""
        select substr(cast(date as varchar), 1, 10) as activity_day,
               model_permaslug,
               sum(total_prompt_tokens + total_completion_tokens) as activity_tokens,
               sum(request_count) as activity_requests
        from {data.activity()}
        where variant = 'standard'
        group by 1, 2
        """
    ).df()
    frame["activity_day"] = frame["activity_day"].map(_day)
    return frame


def last_complete_activity_day(activity: pd.DataFrame) -> str:
    """The final chart day is intra-day at scrape time; retain the prior day."""

    days = sorted(activity["activity_day"].dropna().unique())
    if len(days) < 2:
        raise ValueError("need at least two activity days to exclude the partial terminal day")
    return str(days[-2])


def supply_panel(day: str) -> pd.DataFrame:
    """Supplier depth and listed-price dispersion from the final daily snapshot."""

    endpoints = data.q(
        f"""
        with chosen as (
          select max(run_ts) as run_ts
          from read_parquet('{data.table_glob("endpoints_snapshots")}')
          where dt = '{day}'
        )
        select e.model_id, e.provider_name, e.endpoint_fingerprint,
               e.price_completion
        from read_parquet('{data.table_glob("endpoints_snapshots")}') e
        join chosen using (run_ts)
        where e.dt = '{day}'
        """
    ).df()
    mapping = data.q(
        f"""
        select distinct id, canonical_slug
        from {data.models_snapshots()}
        where dt = '{day}' and {paid_model_sql("id")}
        """
    ).df()
    if endpoints.empty or mapping.empty:
        return pd.DataFrame(
            columns=[
                "model_permaslug",
                "n_providers",
                "n_endpoints",
                "min_completion_price",
                "completion_price_cv",
            ]
        )
    joined = endpoints.merge(mapping, left_on="model_id", right_on="id", how="inner")
    joined["price_completion"] = pd.to_numeric(joined["price_completion"], errors="coerce")

    def _supply(group: pd.DataFrame) -> pd.Series:
        prices = group.loc[group["price_completion"] > 0, "price_completion"]
        mean_price = prices.mean()
        return pd.Series(
            {
                "n_providers": int(group["provider_name"].nunique()),
                "n_endpoints": int(group["endpoint_fingerprint"].nunique()),
                "min_completion_price": float(prices.min()) if len(prices) else np.nan,
                "completion_price_cv": float(prices.std(ddof=0) / mean_price)
                if len(prices) > 1 and mean_price > 0
                else np.nan,
            }
        )

    return (
        joined.groupby("canonical_slug", group_keys=False)
        .apply(_supply, include_groups=False)
        .reset_index()
        .rename(columns={"canonical_slug": "model_permaslug"})
    )


def competition_ranking(
    metrics: pd.DataFrame, activity: pd.DataFrame, suppliers: pd.DataFrame, rank_day: str
) -> pd.DataFrame:
    """Equal-weight transparent rank: size, suppliers, app breadth, alternatives."""

    act = activity[activity["activity_day"] == rank_day].copy()
    app = metrics[metrics["dt"] == rank_day].copy()
    panel = app.merge(act, on="model_permaslug", how="inner").merge(
        suppliers, on="model_permaslug", how="left"
    )
    panel = panel.dropna(
        subset=[
            "activity_tokens",
            "n_providers",
            "app_effective_n_observed",
            "app_portfolio_competition_observed",
        ]
    ).copy()
    components = {
        "demand_percentile": np.log1p(panel["activity_tokens"]).rank(pct=True),
        "supplier_depth_percentile": panel["n_providers"].rank(pct=True),
        "app_breadth_percentile": panel["app_effective_n_observed"].rank(pct=True),
        "app_alternative_percentile": panel["app_portfolio_competition_observed"].rank(
            pct=True
        ),
    }
    for name, values in components.items():
        panel[name] = values
    component_names = list(components)
    panel["contestability_score"] = panel[component_names].mean(axis=1)
    panel["contestability_rank"] = panel["contestability_score"].rank(
        ascending=False, method="min"
    ).astype(int)
    panel["demand_rank"] = panel["activity_tokens"].rank(ascending=False, method="min").astype(int)
    return panel.sort_values(["contestability_rank", "model_permaslug"]).reset_index(drop=True)


def predictive_panel(metrics: pd.DataFrame, activity: pd.DataFrame) -> pd.DataFrame:
    """Model-day panel: app allocation at t, daily activity at t and t+1."""

    last_complete = last_complete_activity_day(activity)
    activity_lookup = activity.set_index(["activity_day", "model_permaslug"])["activity_tokens"]
    rows: list[pd.DataFrame] = []
    for app_day, frame in metrics.groupby("dt"):
        next_day = _day(pd.Timestamp(app_day) + pd.Timedelta(days=1))
        if next_day > last_complete:
            continue
        out = frame.copy()
        out["lag_activity_tokens"] = [
            activity_lookup.get((app_day, model), np.nan) for model in out["model_permaslug"]
        ]
        out["next_activity_tokens"] = [
            activity_lookup.get((next_day, model), np.nan) for model in out["model_permaslug"]
        ]
        out["next_activity_day"] = next_day
        rows.append(out)
    if not rows:
        return pd.DataFrame()
    panel = pd.concat(rows, ignore_index=True).dropna(
        subset=["lag_activity_tokens", "next_activity_tokens", *SHAPE_FEATURES]
    )
    panel = panel[(panel["lag_activity_tokens"] > 0) & (panel["next_activity_tokens"] > 0)].copy()
    panel["log_lag_activity_tokens"] = np.log(panel["lag_activity_tokens"])
    panel["log_next_activity_tokens"] = np.log(panel["next_activity_tokens"])
    day_codes = {day: code for code, day in enumerate(sorted(panel["dt"].unique()))}
    panel["app_day_index"] = panel["dt"].map(day_codes).astype(float)
    return panel


def _oof_predictions(panel: pd.DataFrame, features: list[str]) -> np.ndarray:
    if panel["model_permaslug"].nunique() < 10:
        raise ValueError("need at least 10 model clusters for an out-of-sample screen")
    x = panel[features].to_numpy(dtype=float)
    y = panel["log_next_activity_tokens"].to_numpy(dtype=float)
    groups = panel["model_permaslug"].to_numpy()
    pred = np.full(len(panel), np.nan)
    folds = min(5, len(np.unique(groups)))
    for train, test in GroupKFold(n_splits=folds).split(x, y, groups):
        pred[test] = LinearRegression().fit(x[train], y[train]).predict(x[test])
    return pred


def _bootstrap_delta(
    panel: pd.DataFrame,
    baseline_prediction: np.ndarray,
    allocation_prediction: np.ndarray,
    n: int = 1_000,
) -> dict[str, float]:
    """Cluster bootstrap of held-out loss differences (no in-sample refitting)."""

    y = panel["log_next_activity_tokens"].to_numpy(dtype=float)
    groups = panel["model_permaslug"].to_numpy()
    by_model = {model: np.flatnonzero(groups == model) for model in np.unique(groups)}
    model_ids = np.array(sorted(by_model))
    rng = np.random.default_rng(20260713)
    draws: list[float] = []
    for _ in range(n):
        picked = rng.choice(model_ids, size=len(model_ids), replace=True)
        idx = np.concatenate([by_model[model] for model in picked])
        denom = np.square(y[idx] - y[idx].mean()).sum()
        if denom <= 0:
            continue
        baseline_sse = np.square(y[idx] - baseline_prediction[idx]).sum()
        allocation_sse = np.square(y[idx] - allocation_prediction[idx]).sum()
        draws.append(
            float((baseline_sse - allocation_sse) / denom)
        )
    values = np.asarray(draws)
    return {
        "delta_oos_r2_ci95_low": float(np.quantile(values, 0.025)),
        "delta_oos_r2_ci95_high": float(np.quantile(values, 0.975)),
        "p_delta_oos_r2_positive": float((values > 0).mean()),
        "n_cluster_bootstrap": int(len(values)),
    }


def explanatory_value(panel: pd.DataFrame) -> dict:
    """Out-of-sample incremental value of allocation *shape* over persistence."""

    if panel.empty:
        return {"gated": "no complete next-day app-allocation/activity pairs"}
    baseline_prediction = _oof_predictions(panel, BASE_FEATURES)
    shape_prediction = _oof_predictions(panel, BASE_FEATURES + SHAPE_FEATURES)
    scale_prediction = _oof_predictions(
        panel, BASE_FEATURES + SHAPE_FEATURES + ["log_app_tokens_observed"]
    )
    y = panel["log_next_activity_tokens"].to_numpy(dtype=float)
    base_r2 = float(r2_score(y, baseline_prediction))
    shape_r2 = float(r2_score(y, shape_prediction))
    scale_r2 = float(r2_score(y, scale_prediction))
    result = {
        "n_model_days": int(len(panel)),
        "n_models": int(panel["model_permaslug"].nunique()),
        "transitions": sorted(
            f"{row.dt}->{row.next_activity_day}"
            for row in panel[["dt", "next_activity_day"]].drop_duplicates().itertuples(index=False)
        ),
        "baseline_persistence_oos_r2": base_r2,
        "allocation_shape_oos_r2": shape_r2,
        "allocation_shape_delta_oos_r2": shape_r2 - base_r2,
        **_bootstrap_delta(panel, baseline_prediction, shape_prediction),
        "scale_sensitive_extension_oos_r2": scale_r2,
        "scale_sensitive_extension_delta_oos_r2": scale_r2 - base_r2,
        "headline_features": SHAPE_FEATURES,
        "baseline_features": BASE_FEATURES,
        "read": (
            "The headline comparison uses only normalized top-N allocation shape, "
            "not app-token levels. The scale extension is retained as a diagnostic "
            "because its unknown counter window may overlap mechanically with model activity."
        ),
    }
    return result


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    app_rows = load_app_rows()
    allocations, metrics = allocation_metrics(app_rows)
    activity = activity_panel()
    rank_day = last_complete_activity_day(activity)
    suppliers = supply_panel(rank_day)
    ranking = competition_ranking(metrics, activity, suppliers, rank_day)
    predictive = predictive_panel(metrics, activity)
    if not predictive.empty:
        predictive["log_app_tokens_observed"] = np.log(
            predictive["app_tokens_observed"].clip(lower=1)
        )
    explanation = explanatory_value(predictive)

    save(allocations, out_dir, "h71_app_model_allocations")
    save(metrics, out_dir, "h71_app_allocation_metrics")
    save(ranking, out_dir, "h71_model_competition")
    save(predictive, out_dir, "h71_app_allocation_prediction_panel")
    results = {
        "rank_day": rank_day,
        "coverage": {
            "app_snapshot_days": sorted(app_rows["dt"].unique().tolist()),
            "n_models_ranked": int(len(ranking)),
            "n_models_with_observed_app_allocation_on_rank_day": int(
                metrics.loc[metrics["dt"] == rank_day, "model_permaslug"].nunique()
            ),
            "observed_apps_per_model_median": float(
                metrics.loc[metrics["dt"] == rank_day, "n_observed_apps"].median()
            ),
            "app_counter_window": "not disclosed by the frontend API",
        },
        "ranking_definition": (
            "Equal-weight percentile mean of daily token demand, distinct listed providers, "
            "observed effective app count, and app portfolio competition. It is a descriptive "
            "contestability screen, not a quality, welfare, or causal ranking."
        ),
        "top_contestable_models": ranking.head(25)[
            [
                "contestability_rank",
                "model_permaslug",
                "contestability_score",
                "demand_rank",
                "activity_tokens",
                "n_providers",
                "app_effective_n_observed",
                "top_app_share_observed",
                "app_portfolio_competition_observed",
            ]
        ].to_dict(orient="records"),
        "allocation_shape_predictive_screen": explanation,
        "claim_boundary": (
            "App rows are observed top-N lists and their counter window is undocumented. "
            "This does not identify complete app routing shares, provider selection, causal "
            "effects of app allocation, adverse selection, or front-running."
        ),
    }
    save_json(results, out_dir, "h71_summary")
    log.info("H71: %s", results)
    return results
