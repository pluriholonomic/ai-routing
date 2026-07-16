"""BM4 — out-of-sample reaction-rule horse race."""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from .bm_common import (
    completion_events,
    load_gates,
    provider_cadence,
    quote_exposure_by_provider,
    temporal_training_cutoff,
)
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes
from .vintage import clip_date_range, date_support

PAIRED_BOOTSTRAP_DRAWS = 5_000
PAIRED_BOOTSTRAP_SEED = 20260716


def link_reactions(
    events: pd.DataFrame,
    cadence: pd.DataFrame,
    *,
    lookback_hours: float = 72,
) -> pd.DataFrame:
    """Attach repricing to a unique, strictly earlier rival move.

    Capture timestamps interval-censor quote updates. Events first observed in
    the same snapshot are never ordered. If several rivals share the most
    recent prior timestamp, the putative stimulus is ambiguous and the
    current event is excluded from this reaction panel.
    """
    columns = [
        "ts",
        "model_id",
        "provider_name",
        "own_dlog",
        "rival_provider",
        "rival_dlog",
        "lag_hours",
        "gap_to_rival_new",
        "is_fast",
        "fast_x_rival_dlog",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    fast = cadence.set_index("provider_name")["is_fast"].to_dict()
    rows = []
    horizon = pd.to_timedelta(float(lookback_hours) * 3600, unit="s")
    for _, group in events.groupby("model_id", sort=True):
        ordered = group.sort_values(["ts", "provider_name"], kind="mergesort")
        history: list[pd.Series] = []
        for _, batch in ordered.groupby("ts", sort=True):
            batch = batch.sort_values("provider_name", kind="mergesort")
            for _, event in batch.iterrows():
                candidates = [
                    prior
                    for prior in history
                    if prior["provider_name"] != event["provider_name"]
                    and event["ts"] - prior["ts"] <= horizon
                ]
                if not candidates:
                    continue
                latest_ts = max(prior["ts"] for prior in candidates)
                latest = [prior for prior in candidates if prior["ts"] == latest_ts]
                if len(latest) != 1:
                    continue
                rival = latest[0]
                is_fast = int(bool(fast.get(event["provider_name"], False)))
                rows.append(
                    {
                        "ts": event["ts"],
                        "model_id": event["model_id"],
                        "provider_name": event["provider_name"],
                        "own_dlog": event["dlog_price"],
                        "rival_provider": rival["provider_name"],
                        "rival_dlog": rival["dlog_price"],
                        "lag_hours": (event["ts"] - rival["ts"]).total_seconds() / 3600,
                        "gap_to_rival_new": np.log(event["old_price"] / rival["new_price"]),
                        "is_fast": is_fast,
                        "fast_x_rival_dlog": is_fast * rival["dlog_price"],
                    }
                )
            history.extend(row for _, row in batch.iterrows())
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(["ts", "model_id", "provider_name"], kind="mergesort")
        .reset_index(drop=True)
    )


def _score(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]) -> dict:
    from sklearn.linear_model import HuberRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    if len(train) < max(20, len(columns) * 4) or len(test) < 5:
        return {
            "error": "insufficient temporal holdout",
            "n_train": len(train),
            "n_test": len(test),
        }
    model = HuberRegressor(max_iter=500).fit(train[columns], train["own_dlog"])
    predicted = model.predict(test[columns])
    return {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "mae": float(mean_absolute_error(test["own_dlog"], predicted)),
        "rmse": float(mean_squared_error(test["own_dlog"], predicted) ** 0.5),
        "coefficients": {
            key: float(value) for key, value in zip(columns, model.coef_, strict=True)
        },
        "intercept": float(model.intercept_),
    }


def paired_predictive_test(
    train: pd.DataFrame,
    test: pd.DataFrame,
    base_columns: list[str],
    brown_mackay_columns: list[str],
    *,
    draws: int = PAIRED_BOOTSTRAP_DRAWS,
) -> dict:
    """Model-cluster bootstrap of paired temporal-holdout loss differences."""
    from sklearn.linear_model import HuberRegressor

    minimum_train = max(20, len(brown_mackay_columns) * 4)
    if len(train) < minimum_train or len(test) < 5:
        return {
            "error": "insufficient temporal holdout",
            "n_train": int(len(train)),
            "n_test": int(len(test)),
        }
    base = HuberRegressor(max_iter=500).fit(train[base_columns], train["own_dlog"])
    brown = HuberRegressor(max_iter=500).fit(
        train[brown_mackay_columns], train["own_dlog"]
    )
    observed = test["own_dlog"].to_numpy(float)
    base_error = observed - base.predict(test[base_columns])
    brown_error = observed - brown.predict(test[brown_mackay_columns])
    squared_gain = base_error**2 - brown_error**2
    absolute_gain = np.abs(base_error) - np.abs(brown_error)
    cluster_values = [
        squared_gain[test["model_id"].to_numpy() == model]
        for model in sorted(test["model_id"].unique())
    ]
    cluster_values = [values for values in cluster_values if len(values)]
    cluster_means = np.asarray([float(values.mean()) for values in cluster_values])
    bootstrap = []
    if cluster_values and draws > 0:
        rng = np.random.default_rng(PAIRED_BOOTSTRAP_SEED)
        for _ in range(draws):
            selected = rng.integers(0, len(cluster_values), size=len(cluster_values))
            sample = np.concatenate([cluster_values[index] for index in selected])
            bootstrap.append(float(sample.mean()))
    ci95 = (
        [float(value) for value in np.percentile(bootstrap, [2.5, 97.5])]
        if bootstrap
        else None
    )
    exact_sign_flip_p = None
    equal_weight_gain = float(cluster_means.mean()) if len(cluster_means) else None
    if 0 < len(cluster_means) <= 20:
        null = np.asarray(
            [
                float(np.mean(cluster_means * np.asarray(signs)))
                for signs in itertools.product((-1.0, 1.0), repeat=len(cluster_means))
            ]
        )
        exact_sign_flip_p = float(
            np.mean(null >= float(equal_weight_gain) - np.finfo(float).eps)
        )
    if ci95 is None:
        verdict = "power_gated"
    elif ci95[0] > 0 and exact_sign_flip_p is not None and exact_sign_flip_p <= 0.05:
        verdict = "brown_mackay_predictive_gain"
    elif ci95[1] < 0:
        verdict = "state_only_predictive_advantage"
    else:
        verdict = "predictively_indistinguishable"
    return {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "n_model_clusters": len(cluster_values),
        "mse_improvement": float(squared_gain.mean()),
        "cluster_equal_weight_mse_improvement": equal_weight_gain,
        "mae_improvement": float(absolute_gain.mean()),
        "model_cluster_bootstrap_ci95": ci95,
        "bootstrap_draws": int(draws),
        "probability_positive_gain": (
            float(np.mean(np.asarray(bootstrap) > 0)) if bootstrap else None
        ),
        "exact_sign_flip_p_positive": exact_sign_flip_p,
        "verdict": verdict,
    }


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    events: pd.DataFrame | None = None,
    quotes: pd.DataFrame | None = None,
) -> dict:
    events = (
        completion_events(start_date=start_date, end_date=end_date)
        if events is None
        else clip_date_range(events, start_date=start_date, end_date=end_date)
    )
    quotes = (
        clip_date_range(daily_quotes(), start_date=start_date, end_date=end_date)
        if quotes is None
        else clip_date_range(quotes, start_date=start_date, end_date=end_date)
    )
    cutoff = temporal_training_cutoff(events)
    training_events = events[events["ts"] <= cutoff] if cutoff is not None else events
    training_quotes = (
        clip_date_range(quotes, end_date=cutoff.strftime("%Y-%m-%d"))
        if cutoff is not None
        else quotes
    )
    cadence = provider_cadence(
        training_events,
        set(quotes["provider_name"].dropna()),
        exposure_days=quote_exposure_by_provider(training_quotes),
    )
    panel = link_reactions(events, cadence)
    save(panel, out_dir, "bm4_reaction_rules")
    if cutoff is None:
        train, test = panel.iloc[:0], panel
    else:
        train = panel[panel["ts"] <= cutoff]
        test = panel[panel["ts"] > cutoff]
    base_columns = ["gap_to_rival_new"]
    bm_columns = [
        "gap_to_rival_new",
        "rival_dlog",
        "lag_hours",
        "is_fast",
        "fast_x_rival_dlog",
    ]
    baseline = _score(train, test, base_columns)
    brown_mackay = _score(train, test, bm_columns)
    paired = paired_predictive_test(train, test, base_columns, bm_columns)
    slopes = []
    min_events = load_gates()["brown_mackay"]["min_active_events_per_provider"]
    for provider, group in panel.groupby("provider_name"):
        if len(group) < min_events or group["rival_dlog"].std() == 0:
            continue
        design = np.column_stack([np.ones(len(group)), group["rival_dlog"]])
        coef = np.linalg.lstsq(design, group["own_dlog"], rcond=None)[0]
        slopes.append(
            {
                "provider_name": provider,
                "n_linked_events": int(len(group)),
                "rival_reaction_slope": float(coef[1]),
            }
        )
    save(pd.DataFrame(slopes), out_dir, "bm4_provider_slopes")
    min_linked = load_gates()["brown_mackay"]["min_linked_reactions"]
    summary = {
        "evidence_status": (
            "provisional_descriptive" if len(panel) >= min_linked else "power_gated"
        ),
        "n_linked_reactions": int(len(panel)),
        "min_linked_reactions": min_linked,
        "state_only_holdout": baseline,
        "brown_mackay_holdout": brown_mackay,
        "paired_predictive_test": paired,
        "predictive_verdict": paired.get("verdict", "power_gated"),
        "n_provider_specific_slopes": len(slopes),
        "cadence_training_cutoff": cutoff.isoformat() if cutoff is not None else None,
        "cadence_training_fraction": 0.7,
        "cadence_training_events": int(len(training_events)),
        "cadence_training_exposure_days": int(training_quotes["dt"].nunique()),
        "analysis_vintage": date_support(quotes),
        "claim_boundary": (
            "Cadence classes are frozen on the first 70% of events before the temporal holdout. "
            "Same-snapshot changes have no invented order and ambiguous most-recent rival moves "
            "are excluded. A Brown-MacKay predictive gain would not prove strategic observation; "
            "both models omit latent common shocks and costs."
        ),
    }
    save_json(summary, out_dir, "bm4_summary")
    return summary
