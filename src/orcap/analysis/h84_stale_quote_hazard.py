"""H84/H85 — stale public quotes and next-snapshot capacity enforcement.

H84 is a retrospectively preregistered discovery analysis on the immutable H82
panel. H85 runs the identical construction on a disjoint future-only panel and
masks all case/control outcomes until sample-only release gates pass. See
``docs/h84-h85-stale-quote-adverse-selection-preregistration.md``.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.special import logsumexp
from statsmodels.discrete.conditional_models import ConditionalLogit

from .bm_common import completion_events, provider_cadence, temporal_training_cutoff
from .common import DEFAULT_OUT, save, save_json
from .h82_enforcement_substitution import (
    DISCOVERY_MAX_TS,
    HIGH_MIN_RATE_LIMITED,
    HIGH_MIN_SHARE,
    KEY_COLUMNS,
    MIN_ATTEMPT_PROXY,
    canonical_panel,
    daily_coverage,
    load_rows,
)

FUTURE_START = pd.Timestamp("2026-07-15T12:00:00Z")
MAX_CONTIGUOUS_MINUTES = 10.0
PRICE_ABS_TOLERANCE = 1e-12
PRICE_REL_TOLERANCE = 1e-9
BOOTSTRAP_DRAWS = 10_000
PERMUTATION_DRAWS = 10_000
RANDOM_SEED = 84_850_715

PRIMARY_FEATURE = "stale_cheap"
CONTRAST_METRICS = [
    PRIMARY_FEATURE,
    "log_quote_age",
    "cheapness",
    "log1p_success",
    "capacity_load",
    "endpoint_success_share",
    "prior_success_share_change",
    "stale_cheap_winsor",
]
SURFACE_FEATURES = ["cheapness", "log1p_capacity_ceiling_rpm"]
STALE_FEATURES = [
    *SURFACE_FEATURES,
    "log_quote_age",
    "stale_cheap",
    "spell_left_censored",
]
OPERATIONAL_FEATURES = [*STALE_FEATURES, "log1p_success", "capacity_load"]


def frozen_provider_cadence() -> pd.DataFrame:
    """Freeze provider cadence strictly inside the H84 discovery history."""
    try:
        events = completion_events()
    except Exception:
        return pd.DataFrame(columns=["provider_name", "cadence_class", "is_fast"])
    events = events[events["ts"].le(DISCOVERY_MAX_TS)].copy()
    cutoff = temporal_training_cutoff(events)
    training = events[events["ts"].le(cutoff)] if cutoff is not None else events
    cadence = provider_cadence(training)
    return cadence.loc[:, ["provider_name", "cadence_class", "is_fast"]]


def _price_changed(current: pd.Series, previous: pd.Series) -> pd.Series:
    current_values = pd.to_numeric(current, errors="coerce").to_numpy(dtype=float)
    previous_values = pd.to_numeric(previous, errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(current_values) & np.isfinite(previous_values)
    changed = np.zeros(len(current_values), dtype=bool)
    changed[finite] = ~np.isclose(
        current_values[finite],
        previous_values[finite],
        rtol=PRICE_REL_TOLERANCE,
        atol=PRICE_ABS_TOLERANCE,
    )
    changed[~finite] = True
    return pd.Series(changed, index=current.index, dtype=bool)


def _high_event(
    rate_limited: pd.Series,
    success: pd.Series,
    deranked: pd.Series,
) -> pd.Series:
    rate_limited = pd.to_numeric(rate_limited, errors="coerce")
    success = pd.to_numeric(success, errors="coerce")
    attempts = rate_limited + success
    share = rate_limited / attempts.where(attempts.gt(0))
    deranked_bool = deranked.map(
        lambda value: bool(value)
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().lower() in {"1", "true", "yes", "y"}
        if pd.notna(value)
        else False
    ).astype(bool)
    return (
        rate_limited.ge(HIGH_MIN_RATE_LIMITED)
        & share.ge(HIGH_MIN_SHARE)
        & attempts.ge(MIN_ATTEMPT_PROXY)
        & ~deranked_bool
    )


def quote_state_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Attach pre-onset quote spells and adjacent endpoint outcomes."""
    if panel.empty:
        return panel.copy()
    frame = panel.sort_values([*KEY_COLUMNS, "ts"]).copy().reset_index(drop=True)
    grouped = frame.groupby(KEY_COLUMNS, dropna=False, sort=False)
    previous_ts = grouped["ts"].shift()
    previous_price = grouped["price_completion"].shift()
    elapsed_previous = (frame["ts"] - previous_ts).dt.total_seconds() / 60
    contiguous_previous = elapsed_previous.gt(0) & elapsed_previous.le(
        MAX_CONTIGUOUS_MINUTES
    )
    observed_price_change = contiguous_previous & _price_changed(
        frame["price_completion"], previous_price
    )
    spell_break = previous_ts.isna() | ~contiguous_previous | observed_price_change
    frame["quote_spell"] = spell_break.groupby(
        [frame[column] for column in KEY_COLUMNS], dropna=False
    ).cumsum().astype(int)
    spell_keys = [*KEY_COLUMNS, "quote_spell"]
    spell_group = frame.groupby(spell_keys, dropna=False, sort=False)
    frame["quote_spell_start"] = spell_group["ts"].transform("min")
    frame["quote_age_hours"] = (
        frame["ts"] - frame["quote_spell_start"]
    ).dt.total_seconds() / 3600
    frame["spell_left_censored"] = ~spell_group.apply(
        lambda group: bool(observed_price_change.loc[group.index].iloc[0]),
        include_groups=False,
    ).reindex(pd.MultiIndex.from_frame(frame[spell_keys])).to_numpy(dtype=bool)

    # Adjacent outcomes are attached only after all spell covariates are fixed.
    grouped = frame.groupby(KEY_COLUMNS, dropna=False, sort=False)
    frame["next_ts"] = grouped["ts"].shift(-1)
    frame["previous_ts"] = grouped["ts"].shift(1)
    frame["next_elapsed_minutes"] = (
        frame["next_ts"] - frame["ts"]
    ).dt.total_seconds() / 60
    frame["previous_elapsed_minutes"] = (
        frame["ts"] - frame["previous_ts"]
    ).dt.total_seconds() / 60
    frame["next_contiguous"] = frame["next_elapsed_minutes"].gt(0) & frame[
        "next_elapsed_minutes"
    ].le(MAX_CONTIGUOUS_MINUTES)
    frame["previous_contiguous"] = frame["previous_elapsed_minutes"].gt(0) & frame[
        "previous_elapsed_minutes"
    ].le(MAX_CONTIGUOUS_MINUTES)

    adjacent_columns = [
        "success_5m",
        "rate_limited_5m",
        "is_deranked",
        "price_completion",
        "endpoint_success_share",
    ]
    for column in adjacent_columns:
        frame[f"next_{column}"] = grouped[column].shift(-1)
        frame[f"previous_{column}"] = grouped[column].shift(1)

    frame["next_high_event"] = frame["next_contiguous"] & _high_event(
        frame["next_rate_limited_5m"],
        frame["next_success_5m"],
        frame["next_is_deranked"],
    )
    frame["previous_high_event"] = frame["previous_contiguous"] & _high_event(
        frame["previous_rate_limited_5m"],
        frame["previous_success_5m"],
        frame["previous_is_deranked"],
    )
    frame["prior_success_share_change"] = np.where(
        frame["previous_contiguous"],
        frame["endpoint_success_share"] - frame["previous_endpoint_success_share"],
        np.nan,
    )
    current_price = pd.to_numeric(frame["price_completion"], errors="coerce")
    next_price = pd.to_numeric(frame["next_price_completion"], errors="coerce")
    frame["next_price_sticky"] = frame["next_contiguous"] & np.isclose(
        current_price,
        next_price,
        rtol=PRICE_REL_TOLERANCE,
        atol=PRICE_ABS_TOLERANCE,
        equal_nan=False,
    )
    return frame


def risk_rows(panel: pd.DataFrame, cadence: pd.DataFrame | None = None) -> pd.DataFrame:
    """Construct endpoint risk rows using only information available at t."""
    frame = quote_state_panel(panel)
    if frame.empty:
        return frame
    current_rate_limited = pd.to_numeric(frame["rate_limited_5m"], errors="coerce")
    current_success = pd.to_numeric(frame["success_5m"], errors="coerce")
    next_rate_limited = pd.to_numeric(frame["next_rate_limited_5m"], errors="coerce")
    next_success = pd.to_numeric(frame["next_success_5m"], errors="coerce")
    current_price = pd.to_numeric(frame["price_completion"], errors="coerce")
    at_risk = (
        current_rate_limited.fillna(0).le(0)
        & ~frame["is_deranked"].fillna(False).astype(bool)
        & current_price.gt(0)
        & current_success.notna()
        & frame["next_contiguous"].astype(bool)
        & next_rate_limited.notna()
        & next_success.notna()
    )
    risk = frame.loc[at_risk].copy()
    if risk.empty:
        return risk

    risk["log_price"] = np.log(pd.to_numeric(risk["price_completion"], errors="coerce"))
    model_snapshot = risk.groupby(["model_permaslug", "run_ts"], dropna=False)
    risk["relative_log_price"] = risk["log_price"] - model_snapshot["log_price"].transform(
        "median"
    )
    risk["cheapness"] = -risk["relative_log_price"]
    risk["log_quote_age"] = np.log1p(risk["quote_age_hours"].clip(lower=0))
    risk[PRIMARY_FEATURE] = risk["log_quote_age"] * risk["cheapness"]
    risk["log1p_success"] = np.log1p(
        pd.to_numeric(risk["success_5m"], errors="coerce").clip(lower=0)
    )
    ceiling = pd.to_numeric(risk["capacity_ceiling_rpm"], errors="coerce")
    peak = pd.to_numeric(risk["recent_peak_rpm"], errors="coerce")
    risk["capacity_load"] = np.where(ceiling.gt(0), peak / ceiling, np.nan)
    risk["log1p_capacity_ceiling_rpm"] = np.log1p(ceiling.clip(lower=0))
    risk["case_forward"] = risk["next_high_event"].astype(bool)
    risk["case_backward"] = risk["previous_high_event"].astype(bool)
    risk["choice_set_id"] = (
        risk["model_permaslug"].astype(str) + "|" + risk["run_ts"].astype(str)
    )
    risk["current_ts"] = risk["ts"]
    risk["cluster"] = (
        risk["model_permaslug"].astype(str)
        + "|"
        + risk["ts"].dt.strftime("%Y-%m-%d")
    )

    age_q = risk["quote_age_hours"].quantile([0.01, 0.99])
    cheap_q = risk["cheapness"].quantile([0.01, 0.99])
    age_winsor = risk["quote_age_hours"].clip(age_q.iloc[0], age_q.iloc[1])
    cheap_winsor = risk["cheapness"].clip(cheap_q.iloc[0], cheap_q.iloc[1])
    risk["stale_cheap_winsor"] = np.log1p(age_winsor.clip(lower=0)) * cheap_winsor

    cadence = cadence if cadence is not None else frozen_provider_cadence()
    if cadence.empty:
        risk["cadence_known"] = False
        risk["slow_or_unobserved"] = np.nan
        risk["cadence_class"] = pd.NA
    else:
        cadence_map = cadence.drop_duplicates("provider_name").set_index("provider_name")
        risk["cadence_class"] = risk["provider_name"].map(cadence_map["cadence_class"])
        risk["cadence_known"] = risk["cadence_class"].notna()
        risk["slow_or_unobserved"] = np.where(
            risk["cadence_known"], ~risk["provider_name"].map(cadence_map["is_fast"]).astype(
                "boolean"
            ), np.nan
        )
    return risk


def choice_rows(risk: pd.DataFrame, case_column: str) -> pd.DataFrame:
    """Retain same-model snapshots with one case and at least one control."""
    if risk.empty:
        return risk.copy()
    required = [PRIMARY_FEATURE, "log_quote_age", "cheapness", "price_completion"]
    eligible = risk.dropna(subset=required).copy()
    if eligible.empty:
        return eligible
    counts = eligible.groupby("choice_set_id", sort=False)[case_column].agg(
        alternatives="size", cases="sum"
    )
    valid = counts.index[(counts["alternatives"] >= 2) & counts["cases"].eq(1)]
    rows = eligible[eligible["choice_set_id"].isin(valid)].copy()
    rows["case"] = rows[case_column].astype(bool)
    rows["choice_direction"] = "forward" if case_column == "case_forward" else "backward"
    return rows


def choice_contrasts(rows: pd.DataFrame) -> pd.DataFrame:
    """Collapse choice sets to case-minus-mean-rival feature contrasts."""
    if rows.empty:
        columns = [
            "choice_set_id",
            "model_permaslug",
            "current_ts",
            "cluster",
            "case_provider",
            "alternatives",
            *[f"{metric}_case_minus_rival" for metric in CONTRAST_METRICS],
        ]
        return pd.DataFrame(columns=columns)
    records: list[dict[str, Any]] = []
    for choice_set_id, group in rows.groupby("choice_set_id", sort=False):
        case = group[group["case"]]
        controls = group[~group["case"]]
        if len(case) != 1 or controls.empty:
            continue
        focal = case.iloc[0]
        record: dict[str, Any] = {
            "choice_set_id": choice_set_id,
            "model_permaslug": focal["model_permaslug"],
            "current_ts": focal["current_ts"],
            "next_ts": focal.get("next_ts"),
            "cluster": focal["cluster"],
            "case_provider": focal["provider_name"],
            "alternatives": int(len(group)),
            "case_price_sticky": bool(focal.get("next_price_sticky", False)),
            "case_spell_left_censored": bool(focal["spell_left_censored"]),
            "case_cadence_known": bool(focal.get("cadence_known", False)),
            "case_slow_or_unobserved": (
                bool(focal["slow_or_unobserved"])
                if pd.notna(focal.get("slow_or_unobserved"))
                else np.nan
            ),
            "rival_known_cadence_share": float(controls["cadence_known"].mean()),
            "rival_slow_or_unobserved_share": float(
                controls.loc[controls["cadence_known"], "slow_or_unobserved"].mean()
            )
            if controls["cadence_known"].any()
            else np.nan,
        }
        for metric in CONTRAST_METRICS:
            case_value = pd.to_numeric(case[metric], errors="coerce").iloc[0]
            rival_value = pd.to_numeric(controls[metric], errors="coerce").mean()
            record[f"{metric}_case_minus_rival"] = (
                float(case_value - rival_value)
                if pd.notna(case_value) and pd.notna(rival_value)
                else np.nan
            )
        records.append(record)
    return pd.DataFrame(records)


def cluster_mean_interval(
    contrasts: pd.DataFrame,
    column: str,
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    sample = contrasts.loc[:, [column, "cluster"]].dropna()
    if sample.empty:
        return {"n_choice_sets": 0, "n_clusters": 0, "mean": None, "ci95": [None, None]}
    grouped = sample.groupby("cluster", sort=False)[column]
    sums = grouped.sum().to_numpy(dtype=float)
    counts = grouped.size().to_numpy(dtype=float)
    estimate = float(sample[column].mean())
    if len(sums) == 1:
        interval = [None, None]
    else:
        rng = np.random.default_rng(seed)
        indices = rng.integers(0, len(sums), size=(draws, len(sums)))
        values = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
        quantiles = np.quantile(values, [0.025, 0.975])
        interval = [float(quantiles[0]), float(quantiles[1])]
    return {
        "n_choice_sets": int(len(sample)),
        "n_clusters": int(len(sums)),
        "mean": estimate,
        "ci95": interval,
    }


def permutation_reference(
    rows: pd.DataFrame,
    *,
    feature: str = PRIMARY_FEATURE,
    draws: int = PERMUTATION_DRAWS,
    seed: int = RANDOM_SEED + 1,
) -> dict[str, Any]:
    if rows.empty:
        return {"draws": draws, "observed": None, "one_sided_p": None}
    observed_values: list[float] = []
    centered: list[np.ndarray] = []
    for _, group in rows.groupby("choice_set_id", sort=False):
        values = pd.to_numeric(group[feature], errors="coerce").to_numpy(dtype=float)
        cases = group["case"].to_numpy(dtype=bool)
        if len(values) < 2 or cases.sum() != 1 or not np.isfinite(values).all():
            continue
        scaled = len(values) / (len(values) - 1) * (values - values.mean())
        observed_values.append(float(scaled[np.flatnonzero(cases)[0]]))
        centered.append(scaled)
    if not centered:
        return {"draws": draws, "observed": None, "one_sided_p": None}
    observed = float(np.mean(observed_values))
    rng = np.random.default_rng(seed)
    simulated_sum = np.zeros(draws, dtype=float)
    for values in centered:
        simulated_sum += values[rng.integers(0, len(values), size=draws)]
    simulated = simulated_sum / len(centered)
    p_value = (1 + int((simulated >= observed).sum())) / (draws + 1)
    return {
        "draws": int(draws),
        "choice_sets": int(len(centered)),
        "observed": observed,
        "null_mean": float(simulated.mean()),
        "one_sided_p": float(p_value),
    }


def _valid_model_rows(rows: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    sample = rows.dropna(subset=features).copy()
    if sample.empty:
        return sample
    counts = sample.groupby("choice_set_id")["case"].agg(alternatives="size", cases="sum")
    valid = counts.index[(counts["alternatives"] >= 2) & counts["cases"].eq(1)]
    return sample[sample["choice_set_id"].isin(valid)].copy()


def _fit_and_score(
    sample: pd.DataFrame,
    features: list[str],
    *,
    label: str,
) -> dict[str, Any]:
    sets = (
        sample.loc[:, ["choice_set_id", "current_ts"]]
        .drop_duplicates()
        .sort_values(["current_ts", "choice_set_id"])
    )
    if len(sets) < 10:
        return {"model": label, "error": "fewer than 10 complete choice sets"}
    split = max(1, min(len(sets) - 1, int(len(sets) * 0.70)))
    train_ids = set(sets.iloc[:split]["choice_set_id"])
    test_ids = set(sets.iloc[split:]["choice_set_id"])
    train = sample[sample["choice_set_id"].isin(train_ids)].copy()
    test = sample[sample["choice_set_id"].isin(test_ids)].copy()
    means = train[features].mean()
    scales = train[features].std(ddof=0).replace(0, 1.0).fillna(1.0)
    train_x = (train[features] - means) / scales
    test_x = (test[features] - means) / scales
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ConditionalLogit(
                train["case"].astype(int),
                train_x,
                groups=train["choice_set_id"],
            ).fit(disp=False, maxiter=300)
    except Exception as exc:
        return {
            "model": label,
            "n_train_choice_sets": int(len(train_ids)),
            "n_test_choice_sets": int(len(test_ids)),
            "error": f"{type(exc).__name__}: {exc}",
        }
    params = pd.Series(np.asarray(fit.params, dtype=float), index=features)
    bse = pd.Series(np.asarray(fit.bse, dtype=float), index=features)
    scores = test_x.to_numpy(dtype=float) @ params.to_numpy(dtype=float)
    test = test.assign(_score=scores)
    losses: list[float] = []
    top_one: list[float] = []
    reciprocal_ranks: list[float] = []
    for _, group in test.groupby("choice_set_id", sort=False):
        case_index = np.flatnonzero(group["case"].to_numpy(dtype=bool))
        if len(case_index) != 1:
            continue
        group_scores = group["_score"].to_numpy(dtype=float)
        focal = int(case_index[0])
        losses.append(float(logsumexp(group_scores) - group_scores[focal]))
        top_one.append(float(focal == int(np.argmax(group_scores))))
        rank = 1 + int((group_scores > group_scores[focal]).sum())
        reciprocal_ranks.append(1.0 / rank)
    return {
        "model": label,
        "features": features,
        "n_train_choice_sets": int(len(train_ids)),
        "n_test_choice_sets": int(len(test_ids)),
        "temporal_split_ts": pd.Timestamp(sets.iloc[split - 1]["current_ts"]).isoformat(),
        "coefficients_standardized": {key: float(params[key]) for key in features},
        "standard_errors": {key: float(bse[key]) for key in features},
        "odds_ratios_per_training_sd": {key: float(np.exp(params[key])) for key in features},
        "heldout_log_loss": float(np.mean(losses)) if losses else None,
        "heldout_top_one_accuracy": float(np.mean(top_one)) if top_one else None,
        "heldout_mean_reciprocal_rank": (
            float(np.mean(reciprocal_ranks)) if reciprocal_ranks else None
        ),
    }


def conditional_models(rows: pd.DataFrame) -> dict[str, Any]:
    """Fit frozen temporal conditional-hazard model comparisons."""
    comparison_sample = _valid_model_rows(rows, STALE_FEATURES)
    baseline = _fit_and_score(comparison_sample, SURFACE_FEATURES, label="surface_baseline")
    stale = _fit_and_score(comparison_sample, STALE_FEATURES, label="stale_quote")
    operational_sample = _valid_model_rows(rows, OPERATIONAL_FEATURES)
    stale_operational_sample = _fit_and_score(
        operational_sample, STALE_FEATURES, label="stale_quote_operational_sample"
    )
    operational = _fit_and_score(
        operational_sample, OPERATIONAL_FEATURES, label="operational"
    )
    improvement = None
    if baseline.get("heldout_log_loss") is not None and stale.get("heldout_log_loss") is not None:
        improvement = float(baseline["heldout_log_loss"] - stale["heldout_log_loss"])
    return {
        "surface_baseline": baseline,
        "stale_quote": stale,
        "stale_quote_log_loss_improvement": improvement,
        "stale_quote_operational_sample": stale_operational_sample,
        "operational": operational,
    }


def _leave_one_out(
    contrasts: pd.DataFrame, column: str, group_column: str
) -> dict[str, Any]:
    estimates: list[float] = []
    for value in contrasts[group_column].dropna().unique():
        estimate = contrasts.loc[~contrasts[group_column].eq(value), column].mean()
        if pd.notna(estimate):
            estimates.append(float(estimate))
    return {
        "n_omissions": int(len(estimates)),
        "min": min(estimates) if estimates else None,
        "max": max(estimates) if estimates else None,
    }


def summarize_released(
    panel: pd.DataFrame,
    risk: pd.DataFrame,
    forward: pd.DataFrame,
    backward: pd.DataFrame,
    *,
    evidence_status: str,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    forward_contrasts = choice_contrasts(forward)
    backward_contrasts = choice_contrasts(backward)
    primary_column = f"{PRIMARY_FEATURE}_case_minus_rival"
    forward_primary = cluster_mean_interval(forward_contrasts, primary_column)
    backward_primary = cluster_mean_interval(
        backward_contrasts, primary_column, seed=RANDOM_SEED + 2
    )
    diagnostics = {
        metric: cluster_mean_interval(
            forward_contrasts,
            f"{metric}_case_minus_rival",
            seed=RANDOM_SEED + 10 + offset,
        )
        for offset, metric in enumerate(CONTRAST_METRICS)
    }
    no_left = forward_contrasts[~forward_contrasts["case_spell_left_censored"]]
    model_equal = (
        float(forward_contrasts.groupby("model_permaslug")[primary_column].mean().mean())
        if not forward_contrasts.empty
        else None
    )
    cadence_known = forward_contrasts[forward_contrasts["case_cadence_known"]]
    cadence_difference = (
        float(
            (
                cadence_known["case_slow_or_unobserved"].astype(float)
                - cadence_known["rival_slow_or_unobserved_share"]
            ).mean()
        )
        if not cadence_known.empty
        else None
    )
    result = {
        "evidence_status": evidence_status,
        "preregistration": "docs/h84-h85-stale-quote-adverse-selection-preregistration.md",
        "observed_span_days": (
            float((panel["ts"].max() - panel["ts"].min()).total_seconds() / 86400)
            if len(panel) > 1
            else 0.0
        ),
        "support": {
            "panel_rows": int(len(panel)),
            "at_risk_rows": int(len(risk)),
            "forward_choice_sets": int(forward["choice_set_id"].nunique()),
            "backward_placebo_sets": int(backward["choice_set_id"].nunique()),
            "models": int(forward.loc[forward["case"], "model_permaslug"].nunique())
            if not forward.empty
            else 0,
            "case_providers": int(forward.loc[forward["case"], "provider_name"].nunique())
            if not forward.empty
            else 0,
        },
        "primary_forward_contrast": forward_primary,
        "backward_temporal_placebo": backward_primary,
        "forward_exceeds_backward": bool(
            forward_primary["mean"] is not None
            and backward_primary["mean"] is not None
            and forward_primary["mean"] > backward_primary["mean"]
        ),
        "permutation_reference": permutation_reference(forward),
        "diagnostic_contrasts": diagnostics,
        "case_price_sticky_share": (
            float(forward_contrasts["case_price_sticky"].mean())
            if not forward_contrasts.empty
            else None
        ),
        "equal_model_weighted_primary": model_equal,
        "leave_one_provider_out": _leave_one_out(
            forward_contrasts, primary_column, "case_provider"
        ),
        "leave_one_model_out": _leave_one_out(
            forward_contrasts, primary_column, "model_permaslug"
        ),
        "non_left_censored_case_sensitivity": cluster_mean_interval(
            no_left, primary_column, seed=RANDOM_SEED + 30
        ),
        "winsorized_age_price_sensitivity": cluster_mean_interval(
            forward_contrasts,
            "stale_cheap_winsor_case_minus_rival",
            seed=RANDOM_SEED + 31,
        ),
        "cadence_bridge": {
            "known_case_sets": int(len(cadence_known)),
            "case_minus_rival_slow_or_unobserved_share": cadence_difference,
        },
        "conditional_models": conditional_models(forward),
        "claim_boundary": (
            "This is a one-step-ahead within-model predictive association. It does not "
            "identify strategic quote staleness, provider intent, front-running, a causal "
            "router effect, or welfare loss."
        ),
    }
    return result, forward_contrasts, backward_contrasts


def plot_released(
    result: dict[str, Any],
    forward_contrasts: pd.DataFrame,
    backward_contrasts: pd.DataFrame,
    out_dir: Path,
    *,
    prefix: str,
) -> None:
    if forward_contrasts.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    selected = [PRIMARY_FEATURE, "log_quote_age", "cheapness", "log1p_success"]
    estimates = [result["diagnostic_contrasts"][metric] for metric in selected]
    means = [estimate["mean"] for estimate in estimates]
    lows = [estimate["ci95"][0] for estimate in estimates]
    highs = [estimate["ci95"][1] for estimate in estimates]
    positions = np.arange(len(selected))
    lower_err = [
        mean - low if low is not None else 0
        for mean, low in zip(means, lows, strict=True)
    ]
    upper_err = [
        high - mean if high is not None else 0
        for mean, high in zip(means, highs, strict=True)
    ]
    axes[0, 0].errorbar(
        positions,
        means,
        yerr=np.vstack([lower_err, upper_err]),
        fmt="o",
        color="#B23A48",
        capsize=4,
    )
    axes[0, 0].axhline(0, color="black", lw=0.8)
    axes[0, 0].set_xticks(
        positions,
        ["stale×cheap", "log age", "cheapness", "log success"],
        rotation=20,
    )
    axes[0, 0].set_title("Case minus same-model rivals (95% cluster CI)")

    forward_primary = result["primary_forward_contrast"]["mean"]
    backward_primary = result["backward_temporal_placebo"]["mean"]
    axes[0, 1].bar(
        ["Forward next onset", "Backward placebo"],
        [forward_primary or 0, backward_primary or 0],
        color=["#3572A5", "#999999"],
    )
    axes[0, 1].axhline(0, color="black", lw=0.8)
    axes[0, 1].set_title("Directional stale×cheap contrast")

    models = result["conditional_models"]
    labels: list[str] = []
    losses: list[float] = []
    for key, label in [
        ("surface_baseline", "Surface"),
        ("stale_quote", "Stale quote"),
        ("operational", "Operational"),
    ]:
        value = models.get(key, {}).get("heldout_log_loss")
        if value is not None:
            labels.append(label)
            losses.append(float(value))
    axes[1, 0].bar(labels, losses, color=["#999999", "#3572A5", "#5B8C5A"][: len(labels)])
    axes[1, 0].set_title("Temporal held-out case log loss")
    axes[1, 0].set_ylabel("Lower is better")

    case_values = forward_contrasts[f"{PRIMARY_FEATURE}_case_minus_rival"].dropna()
    placebo_values = backward_contrasts[f"{PRIMARY_FEATURE}_case_minus_rival"].dropna()
    axes[1, 1].hist(case_values, bins=30, alpha=0.6, label="forward", color="#3572A5")
    if len(placebo_values):
        axes[1, 1].hist(placebo_values, bins=30, alpha=0.45, label="backward", color="#999999")
    axes[1, 1].axvline(0, color="black", lw=0.8)
    axes[1, 1].set_title("Choice-set stale×cheap contrasts")
    axes[1, 1].legend(frameon=False)
    for axis in axes.flat:
        axis.grid(alpha=0.18)
    fig.suptitle(f"{prefix.upper()} stale-quote capacity hazard")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{prefix}_stale_quote_hazard.png", dpi=180)
    fig.savefig(out_dir / f"{prefix}_stale_quote_hazard.pdf")
    plt.close(fig)


def analyze_discovery(
    rows: pd.DataFrame,
    out_dir: Path | None = None,
    *,
    cadence: pd.DataFrame | None = None,
) -> dict[str, Any]:
    panel = canonical_panel(rows)
    panel = panel[panel["ts"].le(DISCOVERY_MAX_TS)].copy() if not panel.empty else panel
    risk = risk_rows(panel, cadence)
    forward = choice_rows(risk, "case_forward")
    backward = choice_rows(risk, "case_backward")
    result, forward_contrasts, backward_contrasts = summarize_released(
        panel,
        risk,
        forward,
        backward,
        evidence_status="retrospectively_preregistered_discovery",
    )
    result["analysis_cutoff_utc"] = DISCOVERY_MAX_TS.isoformat()
    if out_dir is not None:
        save(risk, out_dir, "h84_stale_quote_risk_panel")
        save(forward, out_dir, "h84_forward_choice_rows")
        save(backward, out_dir, "h84_backward_placebo_rows")
        save(forward_contrasts, out_dir, "h84_forward_choice_contrasts")
        save(backward_contrasts, out_dir, "h84_backward_choice_contrasts")
        save_json(result, out_dir, "h84_summary")
        plot_released(result, forward_contrasts, backward_contrasts, out_dir, prefix="h84")
    return result


def _complete_day_times(panel: pd.DataFrame) -> list[pd.Timestamp]:
    completion_times: list[pd.Timestamp] = []
    if panel.empty:
        return completion_times
    for _, group in panel.groupby(panel["ts"].dt.strftime("%Y-%m-%d")):
        snapshots = pd.Series(group["ts"].dropna().unique()).sort_values().reset_index(drop=True)
        if len(snapshots) < 144:
            continue
        for position in range(143, len(snapshots)):
            if (snapshots.iloc[position] - snapshots.iloc[0]).total_seconds() >= 20 * 3600:
                completion_times.append(pd.Timestamp(snapshots.iloc[position]))
                break
    return completion_times


def future_support(
    panel: pd.DataFrame,
    risk: pd.DataFrame,
    forward: pd.DataFrame,
    backward: pd.DataFrame,
    *,
    cutoff: pd.Timestamp | None = None,
) -> dict[str, Any]:
    if cutoff is not None:
        panel = panel[panel["ts"].le(cutoff)]
        risk = risk[risk["current_ts"].le(cutoff)]
        forward = forward[
            forward["current_ts"].le(cutoff) & forward["next_ts"].le(cutoff)
        ]
        backward = backward[backward["current_ts"].le(cutoff)]
    cases = forward[forward["case"]] if not forward.empty else forward
    dominance = (
        float(cases["provider_name"].value_counts().iloc[0] / len(cases))
        if len(cases)
        else None
    )
    candidate_sets = (
        int((risk.groupby("choice_set_id")["case_forward"].sum() >= 1).sum())
        if not risk.empty
        else 0
    )
    capacity_coverage = (
        float(forward["capacity_load"].notna().mean()) if not forward.empty else 0.0
    )
    cadence_coverage = (
        float(cases["cadence_known"].mean()) if not cases.empty else 0.0
    )
    coverage = daily_coverage(panel)
    one_case_pass = bool(
        forward.empty or forward.groupby("choice_set_id")["case"].sum().eq(1).all()
    )
    return {
        "panel_rows": int(len(panel)),
        "latest_timestamp": panel["ts"].max().isoformat() if not panel.empty else None,
        "source_span_days": (
            float((panel["ts"].max() - panel["ts"].min()).total_seconds() / 86400)
            if len(panel) > 1
            else 0.0
        ),
        "at_risk_rows": int(len(risk)),
        "forward_candidate_sets": candidate_sets,
        "valid_forward_choice_sets": int(forward["choice_set_id"].nunique())
        if not forward.empty
        else 0,
        "valid_backward_placebo_sets": int(backward["choice_set_id"].nunique())
        if not backward.empty
        else 0,
        "complete_days": int(coverage["complete_day"].sum()) if not coverage.empty else 0,
        "models": int(cases["model_permaslug"].nunique()) if not cases.empty else 0,
        "case_providers": int(cases["provider_name"].nunique()) if not cases.empty else 0,
        "provider_dominance": dominance,
        "capacity_load_coverage": capacity_coverage,
        "case_cadence_coverage": cadence_coverage,
        "choice_set_size": {
            "min": int(forward.groupby("choice_set_id").size().min())
            if not forward.empty
            else 0,
            "median": float(forward.groupby("choice_set_id").size().median())
            if not forward.empty
            else 0.0,
            "max": int(forward.groupby("choice_set_id").size().max())
            if not forward.empty
            else 0,
        },
        "integrity": {
            "future_only": bool(panel.empty or panel["ts"].min() >= FUTURE_START),
            "exactly_one_case_per_forward_set": one_case_pass,
        },
    }


def _support_gates_pass(support: dict[str, Any]) -> bool:
    return bool(
        support["complete_days"] >= 28
        and support["valid_forward_choice_sets"] >= 500
        and support["models"] >= 20
        and support["case_providers"] >= 20
        and support["provider_dominance"] is not None
        and support["provider_dominance"] <= 0.20
        and support["valid_backward_placebo_sets"] >= 150
        and support["capacity_load_coverage"] >= 0.70
        and support["case_cadence_coverage"] >= 0.70
        and all(support["integrity"].values())
    )


def first_future_release_cutoff(
    panel: pd.DataFrame,
    risk: pd.DataFrame,
    forward: pd.DataFrame,
    backward: pd.DataFrame,
) -> pd.Timestamp | None:
    """Return the earliest prefix satisfying only H85 sample/support gates."""
    if panel.empty or forward.empty or backward.empty:
        return None
    candidates = set(_complete_day_times(panel))
    candidates.update(pd.to_datetime(forward["next_ts"].dropna(), utc=True).tolist())
    candidates.update(pd.to_datetime(backward["current_ts"].dropna(), utc=True).tolist())
    for cutoff in sorted(pd.Timestamp(value) for value in candidates):
        if _support_gates_pass(future_support(panel, risk, forward, backward, cutoff=cutoff)):
            return cutoff
    return None


def analyze_future(
    rows: pd.DataFrame,
    out_dir: Path | None = None,
    *,
    cadence: pd.DataFrame | None = None,
) -> dict[str, Any]:
    panel = canonical_panel(rows)
    panel = panel[panel["ts"].ge(FUTURE_START)].copy() if not panel.empty else panel
    risk = risk_rows(panel, cadence)
    forward = choice_rows(risk, "case_forward")
    backward = choice_rows(risk, "case_backward")
    cutoff = first_future_release_cutoff(panel, risk, forward, backward)
    support = future_support(panel, risk, forward, backward, cutoff=cutoff)
    result: dict[str, Any] = {
        "evidence_status": "future_holdout_power_gated" if cutoff is None else "released",
        "preregistration": "docs/h84-h85-stale-quote-adverse-selection-preregistration.md",
        "future_start": FUTURE_START.isoformat(),
        "outcomes_released": cutoff is not None,
        "release_cutoff": cutoff.isoformat() if cutoff is not None else None,
        "support": support,
        "sample_release_requirements": {
            "complete_days": 28,
            "valid_forward_choice_sets": 500,
            "models": 20,
            "case_providers": 20,
            "max_provider_dominance": 0.20,
            "valid_backward_placebo_sets": 150,
            "capacity_load_coverage": 0.70,
            "case_cadence_coverage": 0.70,
        },
        "claim_boundary": (
            "H85 is a future-only predictive stale-quote hazard test. Even after release, "
            "it does not identify provider intent, front-running, or welfare."
        ),
    }
    if cutoff is not None:
        released_panel = panel[panel["ts"].le(cutoff)].copy()
        released_risk = risk[risk["current_ts"].le(cutoff)].copy()
        released_forward = forward[
            forward["current_ts"].le(cutoff) & forward["next_ts"].le(cutoff)
        ].copy()
        released_backward = backward[backward["current_ts"].le(cutoff)].copy()
        released, forward_contrasts, backward_contrasts = summarize_released(
            released_panel,
            released_risk,
            released_forward,
            released_backward,
            evidence_status="future_holdout_released",
        )
        result["released_results"] = released
        if out_dir is not None:
            save(released_risk, out_dir, "h85_stale_quote_risk_panel")
            save(released_forward, out_dir, "h85_forward_choice_rows")
            save(released_backward, out_dir, "h85_backward_placebo_rows")
            save(forward_contrasts, out_dir, "h85_forward_choice_contrasts")
            save(backward_contrasts, out_dir, "h85_backward_choice_contrasts")
            plot_released(
                released,
                forward_contrasts,
                backward_contrasts,
                out_dir,
                prefix="h85",
            )
    if out_dir is not None:
        # Before release, this JSON contains counts and integrity only. No
        # case-labelled row, feature split, sign, coefficient, or plot is saved.
        save_json(result, out_dir, "h85_summary")
    return result


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    return analyze_discovery(load_rows(), out_dir)
