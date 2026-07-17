"""Fail-closed temporal validation for the PM1 repricing-hazard ladder.

The descriptive PM1 ladder is fitted and scored in sample.  This companion
protocol answers the narrower predictive question without pretending that an
in-sample likelihood-ratio test is temporal evidence:

* wait for 30 *completed* UTC quote dates;
* use the first 15 dates for estimation and the next 15 for one fixed holdout;
* construct every state, congestion, and rival-move feature from information
  available by the prior UTC close;
* estimate provider activity from the training prefix only; and
* compare adjacent ladder rungs with date-clustered paired log-loss tests.

Before the calendar gate matures, :func:`run` queries calendar support only and
publishes no fitted coefficient, prediction, loss, or repricing-event count.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .pm1_hazard_baseline import AGE_BINS, build_panel
from .vintage import canonical_date, observed_dates

TRAIN_DAYS = 15
TEST_DAYS = 15
TARGET_DAYS = TRAIN_DAYS + TEST_DAYS
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_SEED = 81_503
EPSILON = 1e-8
RIDGE_C = 1.0
MIN_TRAIN_OUTCOMES_PER_PRIMARY_PARAMETER = 10
MIN_TEST_EVENTS = 50
MIN_EVENT_DATES = 10
MIN_TEST_MODELS = 10

CONTRASTS = (
    ("L2_vs_L1", 1, 2, "duration_calendar"),
    ("L3_vs_L2", 2, 3, "lagged_state"),
    ("L4_vs_L3", 3, 4, "lagged_congestion"),
    ("L5_vs_L4", 4, 5, "lagged_rival_moves"),
)
PRIMARY_CONTRAST = "L3_vs_L2"


def registered_temporal_split(
    values: list[Any] | pd.Series | pd.Index,
    *,
    as_of_date: Any | None = None,
) -> dict[str, Any]:
    """Return the immutable 15/15 split, excluding the open UTC date.

    ``as_of_date`` is injectable for deterministic tests and historical audits.
    A represented date is complete only when it is strictly earlier than the
    UTC as-of date.
    """

    dates = observed_dates(values)
    as_of = canonical_date(as_of_date) or datetime.now(UTC).strftime("%Y-%m-%d")
    completed = [day for day in dates if day < as_of]
    ready = len(completed) >= TARGET_DAYS
    selected = completed[:TARGET_DAYS] if ready else []
    train = selected[:TRAIN_DAYS]
    test = selected[TRAIN_DAYS:]
    return {
        "ready": ready,
        "as_of_utc_date": as_of,
        "represented_dates": len(dates),
        "completed_dates": len(completed),
        "remaining_completed_dates": max(0, TARGET_DAYS - len(completed)),
        "excluded_open_or_future_dates": [day for day in dates if day >= as_of],
        "target_days": TARGET_DAYS,
        "train_target_days": TRAIN_DAYS,
        "test_target_days": TEST_DAYS,
        "selected_dates": selected,
        "train_dates": train,
        "test_dates": test,
        "train_start": train[0] if train else None,
        "train_end": train[-1] if train else None,
        "test_start": test[0] if test else None,
        "test_end": test[-1] if test else None,
    }


def _previous_calendar_day_merge(
    panel: pd.DataFrame,
    values: pd.DataFrame,
    *,
    keys: list[str],
    value_columns: list[str],
) -> pd.DataFrame:
    previous = values.copy()
    previous["d"] = pd.to_datetime(previous["d"], utc=True) + pd.Timedelta(1, unit="D")
    return panel.merge(previous[keys + ["d", *value_columns]], on=[*keys, "d"], how="left")


def prepare_ex_ante_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Replace contemporaneous PM1 covariates with prior-close information."""

    required = {
        "dt",
        "d",
        "model_id",
        "provider_name",
        "price",
        "event",
        "any_raise",
        "age",
        "age_censored",
        "dow",
        "gpu_dlog",
        "util",
        "rl",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"PM1 temporal panel is missing columns: {missing}")

    p = panel.copy()
    p["d"] = pd.to_datetime(p["d"], errors="coerce", utc=True)
    p = p.dropna(subset=["d", "model_id", "provider_name"]).sort_values(
        ["model_id", "provider_name", "d"], kind="mergesort"
    )
    pair = ["model_id", "provider_name"]
    if p.duplicated([*pair, "d"]).any():
        raise ValueError("PM1 temporal panel must contain one row per provider-model-day")

    # The price used to form the relative gap is the previous observed daily
    # quote for the same provider-model pair, never the event day's median.
    p["price_lag1"] = p.groupby(pair, sort=False)["price"].shift(1)
    rival_median = p.groupby(["model_id", "d"], sort=False)["price_lag1"].transform(
        "median"
    )
    rival_count = p.groupby(["model_id", "d"], sort=False)["price_lag1"].transform(
        "count"
    )
    valid_gap = (
        (rival_count >= 2)
        & (pd.to_numeric(p["price_lag1"], errors="coerce") > 0)
        & (pd.to_numeric(rival_median, errors="coerce") > 0)
    )
    p["gap_lag1"] = np.where(
        valid_gap,
        np.log(pd.to_numeric(p["price_lag1"], errors="coerce"))
        - np.log(pd.to_numeric(rival_median, errors="coerce")),
        np.nan,
    )

    # GPU and congestion inputs are lagged one calendar day.  Calendar-day
    # joins deliberately do not carry stale values across missing dates.
    gpu_daily = (
        p[["d", "gpu_dlog"]]
        .groupby("d", as_index=False, sort=True)["gpu_dlog"]
        .median()
        .rename(columns={"gpu_dlog": "gpu_dlog_lag1"})
    )
    p = _previous_calendar_day_merge(
        p, gpu_daily, keys=[], value_columns=["gpu_dlog_lag1"]
    )
    congestion_daily = (
        p.groupby([*pair, "d"], as_index=False, sort=True)
        .agg(util_lag1=("util", "mean"), rl_lag1=("rl", "mean"))
    )
    p = _previous_calendar_day_merge(
        p,
        congestion_daily,
        keys=pair,
        value_columns=["util_lag1", "rl_lag1"],
    )

    # Recompute prior-day rival moves exactly.  The old descriptive feature is
    # a model-day total and can include the provider's own move.
    event = p["event"].astype(bool).astype(int)
    raised = p["any_raise"].fillna(0).astype(float).gt(0).astype(int) * event
    p["_event_int"] = event
    p["_raise_int"] = raised
    model_day = (
        p.groupby(["model_id", "d"], as_index=False, sort=True)
        .agg(total_moves_prev=("_event_int", "sum"), total_raises_prev=("_raise_int", "sum"))
    )
    own_day = p[[*pair, "d", "_event_int", "_raise_int"]].rename(
        columns={"_event_int": "own_move_prev", "_raise_int": "own_raise_prev"}
    )
    p = _previous_calendar_day_merge(
        p,
        model_day,
        keys=["model_id"],
        value_columns=["total_moves_prev", "total_raises_prev"],
    )
    p = _previous_calendar_day_merge(
        p,
        own_day,
        keys=pair,
        value_columns=["own_move_prev", "own_raise_prev"],
    )
    p["rival_moves_lag1"] = (
        p["total_moves_prev"].fillna(0) - p["own_move_prev"].fillna(0)
    ).clip(lower=0)
    p["rival_raises_lag1"] = (
        p["total_raises_prev"].fillna(0) - p["own_raise_prev"].fillna(0)
    ).clip(lower=0)
    p["dt"] = p["d"].dt.strftime("%Y-%m-%d")
    return p.drop(
        columns=[
            "_event_int",
            "_raise_int",
            "total_moves_prev",
            "total_raises_prev",
            "own_move_prev",
            "own_raise_prev",
        ]
    ).reset_index(drop=True)


def assign_training_provider_rates(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate the provider activity control without test-outcome leakage."""

    tr = train.copy()
    te = test.copy()
    y = tr["event"].astype(bool).astype(float)
    global_rate = float(y.mean()) if len(y) else 0.0
    grouped = tr.assign(_y=y).groupby("provider_name")["_y"].agg(["sum", "count"])
    sums = tr["provider_name"].map(grouped["sum"]).astype(float)
    counts = tr["provider_name"].map(grouped["count"]).astype(float)
    tr["provider_rate_train"] = np.where(
        counts > 1,
        (sums - y) / (counts - 1),
        global_rate,
    )
    provider_rates = (grouped["sum"] / grouped["count"]).to_dict()
    te["provider_rate_train"] = te["provider_name"].map(provider_rates).fillna(global_rate)
    tr["provider_rate_train"] = tr["provider_rate_train"].clip(0, 0.5)
    te["provider_rate_train"] = te["provider_rate_train"].clip(0, 0.5)
    return tr, te


def temporal_design(panel: pd.DataFrame, rung: int) -> tuple[np.ndarray, list[str]]:
    """Fixed, leakage-free design matrix for one PM1 ladder rung."""

    cols: list[np.ndarray] = [np.ones(len(panel))]
    names = ["const"]
    if rung >= 2:
        for lo, hi in AGE_BINS[1:]:
            cols.append(
                ((panel["age"] >= lo) & (panel["age"] <= hi)).astype(float).to_numpy()
            )
            names.append(f"age_{lo}_{hi}")
        cols.append(panel["age_censored"].astype(float).to_numpy())
        names.append("age_censored")
        for day in range(1, 7):
            cols.append((panel["dow"] == day).astype(float).to_numpy())
            names.append(f"dow{day}")
        cols.append(panel["provider_rate_train"].astype(float).to_numpy())
        names.append("provider_rate_train")
    if rung >= 3:
        gap = pd.to_numeric(panel["gap_lag1"], errors="coerce")
        gpu = pd.to_numeric(panel["gpu_dlog_lag1"], errors="coerce")
        cols.extend(
            [
                gap.abs().fillna(0).to_numpy(),
                gap.gt(0).fillna(False).astype(float).to_numpy(),
                gap.isna().astype(float).to_numpy(),
                gpu.abs().fillna(0).to_numpy(),
                gpu.isna().astype(float).to_numpy(),
            ]
        )
        names.extend(
            [
                "abs_gap_lag1",
                "gap_positive_lag1",
                "gap_missing_lag1",
                "abs_gpu_dlog_lag1",
                "gpu_missing_lag1",
            ]
        )
    if rung >= 4:
        util = pd.to_numeric(panel["util_lag1"], errors="coerce")
        rate_limit = pd.to_numeric(panel["rl_lag1"], errors="coerce")
        cols.extend(
            [
                util.fillna(0).to_numpy(),
                rate_limit.fillna(0).to_numpy(),
                (util.isna() | rate_limit.isna()).astype(float).to_numpy(),
            ]
        )
        names.extend(["util_lag1", "rl_lag1", "congestion_missing_lag1"])
    if rung >= 5:
        cols.extend(
            [
                panel["rival_moves_lag1"].astype(float).to_numpy(),
                panel["rival_raises_lag1"].astype(float).to_numpy(),
            ]
        )
        names.extend(["rival_moves_lag1", "rival_raises_lag1"])
    return np.column_stack(cols), names


def _ridge_logit_predict(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    names: list[str],
) -> tuple[np.ndarray, list[dict[str, float | str]]]:
    """Fit one fixed, training-standardized ridge logit without holdout tuning."""
    if names[0] != "const" or x_train.shape[1] != len(names):
        raise ValueError("PM1 temporal design must begin with one intercept column")
    y = np.asarray(y_train, dtype=float)
    if len(np.unique(y)) != 2:
        raise ValueError("ridge logit requires both training outcomes")

    features_train = np.asarray(x_train[:, 1:], dtype=float)
    features_test = np.asarray(x_test[:, 1:], dtype=float)
    means = features_train.mean(axis=0) if features_train.shape[1] else np.array([])
    scales = features_train.std(axis=0) if features_train.shape[1] else np.array([])
    scales = np.where(scales > 0, scales, 1.0)
    standardized_train = (features_train - means) / scales
    standardized_test = (features_test - means) / scales

    if standardized_train.shape[1]:
        from sklearn.linear_model import LogisticRegression

        fit = LogisticRegression(
            C=RIDGE_C,
            l1_ratio=0.0,
            solver="lbfgs",
            fit_intercept=True,
            max_iter=2_000,
            random_state=BOOTSTRAP_SEED,
        ).fit(standardized_train, y)
        probability = fit.predict_proba(standardized_test)[:, 1]
        coefficient_values = [float(fit.intercept_[0]), *fit.coef_[0].astype(float).tolist()]
    else:
        mean = float(np.clip(y.mean(), EPSILON, 1 - EPSILON))
        probability = np.full(len(x_test), mean, dtype=float)
        coefficient_values = [float(np.log(mean / (1 - mean)))]

    coefficients: list[dict[str, float | str]] = [
        {
            "term": "const",
            "coefficient": coefficient_values[0],
            "scale": "intercept",
            "training_mean": 0.0,
            "training_sd": 1.0,
        }
    ]
    coefficients.extend(
        {
            "term": name,
            "coefficient": float(coefficient),
            "scale": "training_z_score",
            "training_mean": float(mean),
            "training_sd": float(scale),
        }
        for name, coefficient, mean, scale in zip(
            names[1:], coefficient_values[1:], means, scales, strict=True
        )
    )
    return np.asarray(probability, dtype=float), coefficients


def _log_loss(y: np.ndarray, probability: np.ndarray) -> np.ndarray:
    probability = np.clip(np.asarray(probability, dtype=float), EPSILON, 1 - EPSILON)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(probability) + (1 - y) * np.log(1 - probability))


def _exact_sign_flip_p(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values) or len(values) > 20:
        return None
    observed = float(values.mean())
    signs = np.asarray(list(itertools.product((-1.0, 1.0), repeat=len(values))))
    null_means = (signs * values).mean(axis=1)
    return float(np.mean(null_means >= observed - 1e-15))


def _cluster_bootstrap_ci(
    values: pd.Series,
    clusters: pd.Series,
    *,
    reps: int = BOOTSTRAP_REPS,
    seed: int = BOOTSTRAP_SEED,
) -> list[float] | None:
    frame = pd.DataFrame({"value": values, "cluster": clusters}).dropna()
    means = frame.groupby("cluster", sort=True)["value"].mean().to_numpy(dtype=float)
    if len(means) < 2:
        return None
    rng = np.random.default_rng(seed)
    draws = means[rng.integers(0, len(means), size=(reps, len(means)))].mean(axis=1)
    return [float(value) for value in np.quantile(draws, [0.025, 0.975])]


def _holm_adjust(p_values: dict[str, float | None]) -> dict[str, float | None]:
    valid = sorted(
        ((name, float(value)) for name, value in p_values.items() if value is not None),
        key=lambda item: item[1],
    )
    adjusted: dict[str, float | None] = {name: None for name in p_values}
    running = 0.0
    total = len(valid)
    for rank, (name, value) in enumerate(valid):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted[name] = running
    return adjusted


def evaluate_temporal_panel(
    panel: pd.DataFrame, split: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fit on the registered prefix and score the untouched holdout."""

    if not split.get("ready"):
        raise ValueError("temporal evaluation is forbidden before the 30-date gate")
    p = prepare_ex_ante_panel(panel)
    selected = set(split["selected_dates"])
    p = p[p["dt"].isin(selected)].copy()
    train = p[p["dt"].isin(split["train_dates"])].copy()
    test = p[p["dt"].isin(split["test_dates"])].copy()
    train, test = assign_training_provider_rates(train, test)
    y_train = train["event"].astype(bool).astype(float).to_numpy()
    y_test = test["event"].astype(bool).astype(float).to_numpy()
    _, primary_names = temporal_design(train, 3)
    primary_parameter_count = len(primary_names)
    train_events = int(y_train.sum())
    train_nonevents = int(len(y_train) - train_events)
    test_events = int(y_test.sum())
    test_nonevents = int(len(y_test) - test_events)

    support = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_events": train_events,
        "train_nonevents": train_nonevents,
        "test_events": test_events,
        "test_nonevents": test_nonevents,
        "train_event_dates": int(train.loc[train["event"].astype(bool), "dt"].nunique()),
        "test_event_dates": int(test.loc[test["event"].astype(bool), "dt"].nunique()),
        "test_models": int(test["model_id"].nunique()),
        "test_providers": int(test["provider_name"].nunique()),
        "primary_train_parameters_including_intercept": primary_parameter_count,
        "train_events_per_primary_parameter": (
            float(train_events / primary_parameter_count) if primary_parameter_count else None
        ),
        "train_nonevents_per_primary_parameter": (
            float(train_nonevents / primary_parameter_count) if primary_parameter_count else None
        ),
    }
    support["minimum_identification_gate"] = bool(
        train_events
        >= MIN_TRAIN_OUTCOMES_PER_PRIMARY_PARAMETER * primary_parameter_count
        and train_nonevents
        >= MIN_TRAIN_OUTCOMES_PER_PRIMARY_PARAMETER * primary_parameter_count
        and test_events >= MIN_TEST_EVENTS
        and test_nonevents >= MIN_TEST_EVENTS
        and support["train_event_dates"] >= MIN_EVENT_DATES
        and support["test_event_dates"] >= MIN_EVENT_DATES
        and support["test_models"] >= MIN_TEST_MODELS
        and len(np.unique(y_train)) == 2
        and len(np.unique(y_test)) == 2
    )
    support["minimum_identification_gate_rule"] = {
        "train_events_per_primary_parameter": MIN_TRAIN_OUTCOMES_PER_PRIMARY_PARAMETER,
        "train_nonevents_per_primary_parameter": MIN_TRAIN_OUTCOMES_PER_PRIMARY_PARAMETER,
        "test_events": MIN_TEST_EVENTS,
        "test_nonevents": MIN_TEST_EVENTS,
        "train_event_dates": MIN_EVENT_DATES,
        "test_event_dates": MIN_EVENT_DATES,
        "test_models": MIN_TEST_MODELS,
    }

    predictions = test[["dt", "model_id", "provider_name", "event"]].copy()
    coefficients: list[dict[str, Any]] = []
    rung_metrics: dict[str, Any] = {}
    fit_errors: dict[str, str] = {}
    for rung in range(1, 6):
        x_train, names = temporal_design(train, rung)
        x_test, test_names = temporal_design(test, rung)
        if names != test_names:
            raise AssertionError("train/test PM1 design columns differ")
        try:
            probability, rung_coefficients = _ridge_logit_predict(
                x_train, y_train, x_test, names
            )
            if not np.isfinite(probability).all():
                raise ValueError("non-finite holdout predictions")
        except Exception as exc:
            fit_errors[f"L{rung}"] = f"{type(exc).__name__}: {exc}"
            continue
        loss = _log_loss(y_test, probability)
        predictions[f"p_L{rung}"] = probability
        predictions[f"log_loss_L{rung}"] = loss
        auc = None
        if len(np.unique(y_test)) == 2:
            from sklearn.metrics import roc_auc_score

            auc = float(roc_auc_score(y_test, probability))
        rung_metrics[f"L{rung}"] = {
            "test_log_loss_row_weighted": float(loss.mean()),
            "test_log_loss_date_weighted": float(
                pd.Series(loss, index=test.index).groupby(test["dt"]).mean().mean()
            ),
            "test_brier": float(np.mean((y_test - probability) ** 2)),
            "test_auc": auc,
        }
        coefficients.extend(
            {
                "rung": rung,
                **row,
            }
            for row in rung_coefficients
        )

    contrast_rows: list[dict[str, Any]] = []
    raw_p: dict[str, float | None] = {}
    for name, previous, current, interpretation in CONTRASTS:
        previous_col = f"log_loss_L{previous}"
        current_col = f"log_loss_L{current}"
        if previous_col not in predictions or current_col not in predictions:
            raw_p[name] = None
            continue
        improvement = predictions[previous_col] - predictions[current_col]
        daily = improvement.groupby(predictions["dt"]).mean()
        model = improvement.groupby(predictions["model_id"]).mean()
        leave_one_model_out = [
            float(improvement.loc[predictions["model_id"] != held_out].mean())
            for held_out in sorted(predictions["model_id"].unique())
        ]
        raw_p[name] = _exact_sign_flip_p(daily.to_numpy())
        contrast_rows.append(
            {
                "contrast": name,
                "previous_rung": previous,
                "current_rung": current,
                "interpretation": interpretation,
                "mean_log_loss_improvement_date_weighted": float(daily.mean()),
                "mean_log_loss_improvement_row_weighted": float(improvement.mean()),
                "date_cluster_bootstrap_ci95": _cluster_bootstrap_ci(
                    improvement, predictions["dt"], seed=BOOTSTRAP_SEED + current
                ),
                "model_cluster_bootstrap_ci95": _cluster_bootstrap_ci(
                    improvement, predictions["model_id"], seed=BOOTSTRAP_SEED + 100 + current
                ),
                "date_exact_sign_flip_p_one_sided": raw_p[name],
                "n_test_dates": int(len(daily)),
                "n_test_models": int(len(model)),
                "leave_one_model_out_range": (
                    leave_one_model_out
                    if len(model) > 1
                    else []
                ),
            }
        )

    adjusted = _holm_adjust(raw_p)
    for row in contrast_rows:
        row["holm_p_one_sided_four_adjacent_contrasts"] = adjusted[row["contrast"]]
        loo = row["leave_one_model_out_range"]
        row["leave_one_model_out_range"] = (
            [float(np.nanmin(loo)), float(np.nanmax(loo))] if loo else None
        )
    contrasts = pd.DataFrame(contrast_rows)
    primary = next(
        (row for row in contrast_rows if row["contrast"] == PRIMARY_CONTRAST), None
    )
    verdict = "insufficient_identifying_support"
    if support["minimum_identification_gate"] and primary is not None:
        effect = primary["mean_log_loss_improvement_date_weighted"]
        p_holm = primary["holm_p_one_sided_four_adjacent_contrasts"]
        date_ci = primary["date_cluster_bootstrap_ci95"]
        model_ci = primary["model_cluster_bootstrap_ci95"]
        if (
            effect > 0
            and p_holm is not None
            and p_holm <= 0.05
            and date_ci is not None
            and model_ci is not None
            and date_ci[0] > 0
            and model_ci[0] > 0
        ):
            verdict = "lagged_state_dependence_predicts_holdout_repricing"
        elif effect <= 0 and date_ci is not None and date_ci[1] < 0:
            verdict = "lagged_state_dependence_rejected_predictively"
        else:
            verdict = "lagged_state_dependence_predictively_indistinguishable"

    summary = {
        "evidence_status": "temporal_holdout_released",
        "verdict": verdict,
        "primary_contrast": PRIMARY_CONTRAST,
        "estimator": {
            "model": "training-standardized L2-penalized logistic regression",
            "ridge_c": RIDGE_C,
            "holdout_tuning": False,
            "coefficient_scale": "training z score except intercept",
        },
        "split": split,
        "support": support,
        "rung_metrics": rung_metrics,
        "contrasts": {row["contrast"]: row for row in contrast_rows},
        "fit_errors": fit_errors,
        "coefficient_rows": coefficients,
        "claim_boundary": (
            "This is a fixed 15-day-to-15-day predictive validation using prior-close "
            "public covariates. It does not identify causal pricing responses, private order "
            "flow, provider costs, or welfare effects."
        ),
    }
    return predictions, contrasts, summary


def _empty_predictions() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["dt", "model_id", "provider_name", "event", *[f"p_L{i}" for i in range(1, 6)]]
    )


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    endpoint_dates: list[Any] | None = None,
    panel: pd.DataFrame | None = None,
    as_of_date: Any | None = None,
) -> dict[str, Any]:
    """Publish readiness only before 30 completed dates; otherwise run once."""

    out_dir.mkdir(parents=True, exist_ok=True)
    with data.pinned_analysis_source() as source_snapshot:
        dates = endpoint_dates
        if dates is None:
            dates = data.q(
                f"""
                select distinct cast(dt as varchar) as dt
                from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
                order by 1
                """
            ).df()["dt"].tolist()
        split = registered_temporal_split(dates, as_of_date=as_of_date)
        if not split["ready"]:
            save(_empty_predictions(), out_dir, "pm1_temporal_validation_predictions")
            save(pd.DataFrame(), out_dir, "pm1_temporal_validation_contrasts")
            summary = {
                "evidence_status": "not_run_before_30_completed_date_gate",
                "verdict": "calendar_power_gated",
                "source_snapshot": source_snapshot,
                "split": split,
                "pricing_events_queried": False,
                "protocol": {
                    "training": "first 15 completed UTC quote dates",
                    "holdout": "next 15 completed UTC quote dates",
                    "features": "prior-close only",
                    "provider_activity": "training-prefix only",
                    "estimator": (
                        "training-standardized L2 logistic, C=1 fixed before holdout, "
                        "no holdout tuning"
                    ),
                    "primary_contrast": PRIMARY_CONTRAST,
                    "primary_loss": "date-weighted paired Bernoulli log loss",
                    "multiplicity": "Holm across four adjacent ladder contrasts",
                    "minimum_identification_gate": (
                        "10 train events and 10 train nonevents per L3 parameter; "
                        "50 test events and nonevents; 10 train/test event dates; "
                        "10 test models"
                    ),
                },
                "claim_boundary": (
                    "No PM1 temporal coefficient, prediction, loss, AUC, or repricing-event "
                    "count is computed before the 30-completed-date gate."
                ),
            }
            save_json(summary, out_dir, "pm1_temporal_validation_summary")
            return summary

        selected = split["selected_dates"]
        analytical_panel = panel
        if analytical_panel is None:
            analytical_panel = build_panel(start_date=selected[0], end_date=selected[-1])
        predictions, contrasts, summary = evaluate_temporal_panel(analytical_panel, split)
        summary["source_snapshot"] = source_snapshot
        summary["pricing_events_queried"] = True
        save(predictions, out_dir, "pm1_temporal_validation_predictions")
        save(contrasts, out_dir, "pm1_temporal_validation_contrasts")
        save_json(summary, out_dir, "pm1_temporal_validation_summary")
        return summary
