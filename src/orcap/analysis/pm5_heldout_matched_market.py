"""Future-gated PM5 whole-market matched-menu validation.

The economic specification is frozen in
``manuscripts/pm5-heldout-matched-market-preregistration-2026-07-16.md``.
Before 30 quote dates exist, ``run`` reads only the date ledger and cannot load
prices or construct an outcome-bearing event table.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from . import data
from .common import DEFAULT_OUT, save, save_json
from .pm5_tie_microstructure import (
    REFERENCE_BOOTSTRAP_DRAWS,
    REFERENCE_MAX_GAP_MINUTES,
    _clustered_mean_inference,
    _hypergeometric_any_hit_probability,
    attach_global_price_menu_null,
    isolated_quote_change_events,
    quote_ticks,
)
from .vintage import observed_dates

TARGET_DATES = 30
TRAIN_DATES = 15
PRIMARY_MATCH_COUNT = 20
SENSITIVITY_MATCH_COUNTS = (10, 50)
MIN_DECOY_MARKETS = 5
BOOTSTRAP_DRAWS = REFERENCE_BOOTSTRAP_DRAWS
SEED = 20260718
SIGN_FLIP_EXACT_MAX_CLUSTERS = 22
SIGN_FLIP_MONTE_CARLO_DRAWS = 1_000_000
MIN_HOLDOUT_EVENTS = 100
MIN_HOLDOUT_CLUSTERS = 10
MAX_MODEL_EVENT_SHARE = 0.50
PREREGISTRATION_COMMIT = "7709446"

FEATURE_COLUMNS = (
    "log_endpoint_count",
    "log_median_price",
    "log1p_relative_iqr",
    "shared_endpoint_share",
    "tied_minimum",
)


def registered_split(values: list[Any]) -> dict[str, Any]:
    """Return the immutable earliest-30-date split without partial holdout dates."""
    dates = observed_dates(values)
    ready = len(dates) >= TARGET_DATES
    selected = dates[:TARGET_DATES] if ready else []
    return {
        "ready": ready,
        "observed_days": int(len(dates)),
        "target_days": TARGET_DATES,
        "remaining_days": int(max(0, TARGET_DATES - len(dates))),
        "selected_dates": selected,
        "training_dates": selected[:TRAIN_DATES],
        "holdout_dates": selected[TRAIN_DATES:],
        "training_start": selected[0] if ready else None,
        "training_end": selected[TRAIN_DATES - 1] if ready else None,
        "holdout_start": selected[TRAIN_DATES] if ready else None,
        "holdout_end": selected[-1] if ready else None,
    }


def _normalized_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    required = {"run_ts", "model_id", "provider_name", "price"}
    if quotes.empty or not required.issubset(quotes.columns):
        return pd.DataFrame(columns=sorted(required))
    frame = quotes[list(required)].copy()
    frame["run_ts"] = pd.to_datetime(frame["run_ts"], errors="coerce", utc=True)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["run_ts", "model_id", "provider_name", "price"])
    frame = frame[frame["price"].gt(0)]
    return (
        frame.groupby(["run_ts", "model_id", "provider_name"], as_index=False)["price"]
        .min()
        .sort_values(["run_ts", "model_id", "provider_name"], kind="mergesort")
        .reset_index(drop=True)
    )


def market_state_panel(quotes: pd.DataFrame) -> pd.DataFrame:
    """Construct the five preregistered pre-event whole-market features."""
    frame = _normalized_quotes(quotes)
    columns = ["run_ts", "model_id", "n_endpoints", *FEATURE_COLUMNS]
    rows: list[dict[str, Any]] = []
    for (timestamp, model_id), group in frame.groupby(
        ["run_ts", "model_id"], sort=True
    ):
        prices = group["price"].to_numpy(dtype=float)
        n = int(len(prices))
        median = float(np.median(prices))
        q25, q75 = np.quantile(prices, [0.25, 0.75])
        equal = np.isclose(
            prices[:, None], prices[None, :], rtol=1e-9, atol=1e-12
        )
        np.fill_diagonal(equal, False)
        minimum = float(prices.min())
        rows.append(
            {
                "run_ts": timestamp,
                "model_id": str(model_id),
                "n_endpoints": n,
                "log_endpoint_count": float(math.log(n)),
                "log_median_price": float(math.log(median)),
                "log1p_relative_iqr": float(math.log1p((q75 - q25) / median)),
                "shared_endpoint_share": float(equal.any(axis=1).mean()),
                "tied_minimum": float(
                    np.isclose(prices, minimum, rtol=1e-9, atol=1e-12).sum()
                    >= 2
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def fit_feature_scaler(
    states: pd.DataFrame,
    training_dates: list[str],
) -> dict[str, dict[str, float]]:
    """Fit feature location and scale using training market states only."""
    dates = pd.to_datetime(states["run_ts"], errors="coerce", utc=True).dt.strftime(
        "%Y-%m-%d"
    )
    training = states[dates.isin(training_dates)]
    if training.empty:
        raise ValueError("feature scaler requires training market states")
    means = training[list(FEATURE_COLUMNS)].mean()
    scales = training[list(FEATURE_COLUMNS)].std(ddof=0).replace(0, 1).fillna(1)
    return {
        "mean": {column: float(means[column]) for column in FEATURE_COLUMNS},
        "scale": {column: float(scales[column]) for column in FEATURE_COLUMNS},
        "n_training_market_states": int(len(training)),
    }


def attach_matched_market_probability(
    events: pd.DataFrame,
    quotes: pd.DataFrame,
    scaler: dict[str, dict[str, float]],
    *,
    match_count: int = PRIMARY_MATCH_COUNT,
    minimum_decoys: int = MIN_DECOY_MARKETS,
) -> pd.DataFrame:
    """Attach MM1 using nearest whole-market states at the exact prior timestamp."""
    out = events.copy()
    output_columns = {
        "matched_market_requested_decoys": pd.Series(dtype="Int64"),
        "matched_market_available_decoys": pd.Series(dtype="Int64"),
        "matched_market_used_decoys": pd.Series(dtype="Int64"),
        "matched_market_mean_distance": pd.Series(dtype=float),
        "matched_market_probability": pd.Series(dtype=float),
        "exact_minus_matched_market": pd.Series(dtype=float),
    }
    if out.empty:
        for column, values in output_columns.items():
            out[column] = values
        return out

    frame = _normalized_quotes(quotes)
    states = market_state_panel(frame)
    state_cache = {
        timestamp: group.set_index("model_id", drop=False)
        for timestamp, group in states.groupby("run_ts", sort=False)
    }
    quote_cache = {
        timestamp: group for timestamp, group in frame.groupby("run_ts", sort=False)
    }
    scale = np.array([scaler["scale"][column] for column in FEATURE_COLUMNS])

    available_counts: list[int] = []
    used_counts: list[int] = []
    distances: list[float] = []
    probabilities: list[float] = []
    for row in out.itertuples(index=False):
        timestamp = row.previous_run_ts
        snapshot_states = state_cache.get(timestamp)
        snapshot_quotes = quote_cache.get(timestamp)
        if (
            snapshot_states is None
            or snapshot_quotes is None
            or str(row.model_id) not in snapshot_states.index
        ):
            available_counts.append(0)
            used_counts.append(0)
            distances.append(math.nan)
            probabilities.append(math.nan)
            continue
        focal = snapshot_states.loc[str(row.model_id)]
        if isinstance(focal, pd.DataFrame):
            focal = focal.iloc[0]
        candidates = snapshot_states[
            snapshot_states["model_id"].astype(str).ne(str(row.model_id))
            & snapshot_states["n_endpoints"].ge(int(row.n_rival_quotes))
        ].copy().reset_index(drop=True)
        available_counts.append(int(len(candidates)))
        if len(candidates) < int(minimum_decoys):
            used_counts.append(0)
            distances.append(math.nan)
            probabilities.append(math.nan)
            continue
        focal_vector = focal[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
        candidate_values = candidates[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
        candidates["_distance"] = np.sqrt(
            np.square((candidate_values - focal_vector) / scale).sum(axis=1)
        )
        chosen = candidates.sort_values(
            ["_distance", "model_id"], kind="mergesort"
        ).head(int(match_count))
        decoy_probabilities = []
        for decoy in chosen.itertuples(index=False):
            decoy_prices = snapshot_quotes[
                snapshot_quotes["model_id"].astype(str).eq(str(decoy.model_id))
            ]["price"].to_numpy(dtype=float)
            hits = int(
                np.isclose(
                    decoy_prices,
                    float(row.new_price),
                    rtol=1e-9,
                    atol=1e-12,
                ).sum()
            )
            decoy_probabilities.append(
                _hypergeometric_any_hit_probability(
                    population=int(len(decoy_prices)),
                    hits=hits,
                    draws=int(row.n_rival_quotes),
                )
            )
        used_counts.append(int(len(chosen)))
        distances.append(float(chosen["_distance"].mean()))
        probabilities.append(float(np.mean(decoy_probabilities)))

    out["matched_market_requested_decoys"] = int(match_count)
    out["matched_market_available_decoys"] = available_counts
    out["matched_market_used_decoys"] = used_counts
    out["matched_market_mean_distance"] = distances
    out["matched_market_probability"] = probabilities
    out["exact_minus_matched_market"] = (
        out["exact_lagged_rival_match"] - out["matched_market_probability"]
    )
    return out


def fit_response_increment(panel: pd.DataFrame) -> dict[str, float | int]:
    """Fit the preregistered one-parameter persistent landing increment on training."""
    usable = panel.dropna(
        subset=["exact_lagged_rival_match", "matched_market_probability"]
    )
    if usable.empty:
        raise ValueError("response increment requires comparable training events")
    outcome = usable["exact_lagged_rival_match"].to_numpy(dtype=float)
    baseline = usable["matched_market_probability"].to_numpy(dtype=float)

    def log_likelihood(rho: float) -> float:
        probability = baseline + float(rho) * (1 - baseline)
        probability = np.clip(probability, 1e-12, 1 - 1e-12)
        return float(
            np.sum(
                outcome * np.log(probability)
                + (1 - outcome) * np.log1p(-probability)
            )
        )

    epsilon = 1e-9
    result = minimize_scalar(
        lambda rho: -log_likelihood(float(rho)),
        bounds=(0.0, 1.0 - epsilon),
        method="bounded",
        options={"xatol": 1e-12},
    )
    candidate = float(result.x)
    choices = [(0.0, log_likelihood(0.0)), (candidate, log_likelihood(candidate))]
    rho, fitted = max(choices, key=lambda item: item[1])
    return {
        "rho": float(rho),
        "n_training_events": int(len(usable)),
        "m0_log_likelihood": float(log_likelihood(0.0)),
        "m1_log_likelihood": float(fitted),
    }


def score_response_models(panel: pd.DataFrame, *, rho: float) -> pd.DataFrame:
    """Score frozen M0 and training-fitted M1 on an untouched event panel."""
    out = panel.copy()
    q0 = out["matched_market_probability"].to_numpy(dtype=float)
    q1 = q0 + float(rho) * (1 - q0)
    y = out["exact_lagged_rival_match"].to_numpy(dtype=float)
    p0 = np.clip(q0, 1e-12, 1 - 1e-12)
    p1 = np.clip(q1, 1e-12, 1 - 1e-12)
    out["m0_probability"] = q0
    out["m1_probability"] = q1
    out["m0_brier"] = np.square(y - q0)
    out["m1_brier"] = np.square(y - q1)
    out["m0_log_score"] = y * np.log(p0) + (1 - y) * np.log1p(-p0)
    out["m1_log_score"] = y * np.log(p1) + (1 - y) * np.log1p(-p1)
    out["m1_minus_m0_log_score"] = out["m1_log_score"] - out["m0_log_score"]
    return out


def cluster_sign_flip(
    panel: pd.DataFrame,
    *,
    value_column: str,
    cluster_column: str = "model_id",
    seed: int = SEED,
) -> dict[str, Any]:
    """Declared exact-or-fixed-Monte-Carlo cluster sign-flip robustness."""
    usable = panel.dropna(subset=[value_column, cluster_column])
    if usable.empty:
        return {
            "n_events": 0,
            "n_clusters": 0,
            "method": None,
            "one_sided_p": None,
            "two_sided_p": None,
        }
    sums = (
        usable.groupby(cluster_column, sort=True)[value_column]
        .sum()
        .to_numpy(dtype=np.longdouble)
    )
    n_clusters = int(len(sums))
    observed = np.sum(sums, dtype=np.longdouble)
    exact = n_clusters <= SIGN_FLIP_EXACT_MAX_CLUSTERS
    draws = (1 << n_clusters) if exact else SIGN_FLIP_MONTE_CARLO_DRAWS
    chunk_size = min(65_536, draws)
    tolerance = np.longdouble(32) * np.finfo(np.longdouble).eps * max(
        np.longdouble(1), np.sum(np.abs(sums), dtype=np.longdouble)
    )
    rng = np.random.default_rng(seed)
    one_sided = 0
    two_sided = 0
    bit_positions = np.arange(n_clusters, dtype=np.uint64)
    for start in range(0, draws, chunk_size):
        size = min(chunk_size, draws - start)
        if exact:
            assignments = np.arange(start, start + size, dtype=np.uint64)
            signs = (
                ((assignments[:, None] >> bit_positions[None, :]) & 1).astype(np.int8)
                * 2
                - 1
            )
        else:
            signs = rng.choice(np.array([-1, 1], dtype=np.int8), size=(size, n_clusters))
        totals = signs.astype(np.longdouble) @ sums
        one_sided += int(np.count_nonzero(totals >= observed - tolerance))
        two_sided += int(np.count_nonzero(np.abs(totals) >= abs(observed) - tolerance))
    one_p = float(one_sided / draws)
    return {
        "n_events": int(len(usable)),
        "n_clusters": n_clusters,
        "method": "exact_enumeration" if exact else "fixed_monte_carlo",
        "draws": int(draws),
        "observed_total": float(observed),
        "one_sided_p": one_p,
        "two_sided_p": float(two_sided / draws),
        "monte_carlo_standard_error": (
            None if exact else float(math.sqrt(one_p * (1 - one_p) / draws))
        ),
    }


def _probability_score_summary(
    panel: pd.DataFrame,
    *,
    probability_column: str,
    label: str,
) -> dict[str, Any]:
    usable = panel.dropna(
        subset=["exact_lagged_rival_match", probability_column]
    )
    if usable.empty:
        return {"label": label, "n_events": 0}
    y = usable["exact_lagged_rival_match"].to_numpy(dtype=float)
    q = usable[probability_column].to_numpy(dtype=float)
    clipped = np.clip(q, 1e-12, 1 - 1e-12)
    return {
        "label": label,
        "n_events": int(len(usable)),
        "mean_probability": float(q.mean()),
        "calibration_intercept": float(np.mean(y - q)),
        "brier_score": float(np.mean(np.square(y - q))),
        "log_score": float(
            np.mean(y * np.log(clipped) + (1 - y) * np.log1p(-clipped))
        ),
        "probability_p05": float(np.quantile(q, 0.05)),
        "probability_median": float(np.quantile(q, 0.5)),
        "probability_p95": float(np.quantile(q, 0.95)),
    }


def _positive_inference(inference: dict[str, Any]) -> bool:
    interval = inference.get("cluster_bootstrap_ci95") or [None, None]
    loo = inference.get("leave_one_cluster_out_range") or [None, None]
    return bool(
        interval[0] is not None
        and interval[0] > 0
        and loo[0] is not None
        and loo[0] > 0
    )


def heldout_experiment(
    quotes: pd.DataFrame,
    split: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Execute MM1/MR1 only after the external 30-date gate is satisfied."""
    if not split.get("ready"):
        raise ValueError("heldout experiment cannot run before 30 dates")
    selected = set(split["selected_dates"])
    frame = _normalized_quotes(quotes)
    dates = frame["run_ts"].dt.strftime("%Y-%m-%d")
    frame = frame[dates.isin(selected)].copy()
    states = market_state_panel(frame)
    scaler = fit_feature_scaler(states, list(split["training_dates"]))
    events = isolated_quote_change_events(
        frame,
        max_gap_minutes=REFERENCE_MAX_GAP_MINUTES,
    )
    events = attach_global_price_menu_null(events, frame)
    event_dates = pd.to_datetime(events["run_ts"], utc=True).dt.strftime("%Y-%m-%d")
    training_events = events[event_dates.isin(split["training_dates"])].copy()
    holdout_events = events[event_dates.isin(split["holdout_dates"])].copy()
    training = attach_matched_market_probability(
        training_events,
        frame,
        scaler,
        match_count=PRIMARY_MATCH_COUNT,
    ).dropna(subset=["matched_market_probability"])
    holdout = attach_matched_market_probability(
        holdout_events,
        frame,
        scaler,
        match_count=PRIMARY_MATCH_COUNT,
    ).dropna(subset=["matched_market_probability"])
    fitted = fit_response_increment(training)
    scored = score_response_models(holdout, rho=float(fitted["rho"]))

    residual_inference = _clustered_mean_inference(
        scored,
        value_column="exact_minus_matched_market",
        cluster_column="model_id",
        bootstrap_draws=BOOTSTRAP_DRAWS,
        seed=SEED,
    )
    gain_inference = _clustered_mean_inference(
        scored,
        value_column="m1_minus_m0_log_score",
        cluster_column="model_id",
        bootstrap_draws=BOOTSTRAP_DRAWS,
        seed=SEED,
    )
    residual_sign = cluster_sign_flip(
        scored, value_column="exact_minus_matched_market"
    )
    gain_sign = cluster_sign_flip(scored, value_column="m1_minus_m0_log_score")
    largest_model_share = (
        float(scored.groupby("model_id").size().max() / len(scored))
        if len(scored)
        else None
    )
    support_passes = bool(
        len(scored) >= MIN_HOLDOUT_EVENTS
        and scored["model_id"].nunique() >= MIN_HOLDOUT_CLUSTERS
        and largest_model_share is not None
        and largest_model_share <= MAX_MODEL_EVENT_SHARE
    )
    residual_sign_p = residual_sign.get("one_sided_p")
    gain_sign_p = gain_sign.get("one_sided_p")
    promotion = bool(
        support_passes
        and _positive_inference(residual_inference)
        and _positive_inference(gain_inference)
        and residual_sign_p is not None
        and residual_sign_p <= 0.05
        and gain_sign_p is not None
        and gain_sign_p <= 0.05
    )

    comparison_rows = [
        _probability_score_summary(
            scored,
            probability_column="matched_market_probability",
            label="MM1 whole-market matched menu",
        ),
        _probability_score_summary(
            scored,
            probability_column="global_menu_match_probability",
            label="factor-1.25 pooled global menu",
        ),
        _probability_score_summary(
            scored,
            probability_column="m1_probability",
            label="MR1 training-fitted persistent increment",
        ),
    ]
    sensitivities = {}
    for count in SENSITIVITY_MATCH_COUNTS:
        sensitivity = attach_matched_market_probability(
            holdout_events,
            frame,
            scaler,
            match_count=count,
        ).dropna(subset=["matched_market_probability"])
        sensitivities[str(count)] = {
            "match_count": int(count),
            "n_events": int(len(sensitivity)),
            "mean_probability": (
                float(sensitivity["matched_market_probability"].mean())
                if len(sensitivity)
                else None
            ),
            "mean_residual": (
                float(sensitivity["exact_minus_matched_market"].mean())
                if len(sensitivity)
                else None
            ),
        }

    summary = {
        "evidence_status": (
            "heldout_predictive_promotion"
            if promotion
            else "heldout_support_gate_failed"
            if not support_passes
            else "heldout_predictive_nonpromotion"
        ),
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "split": split,
        "scaler": scaler,
        "training_fit": fitted,
        "holdout_support": {
            "events": int(len(scored)),
            "models": int(scored["model_id"].nunique()),
            "providers": int(scored["provider_name"].nunique()),
            "largest_model_event_share": largest_model_share,
            "minimum_events": MIN_HOLDOUT_EVENTS,
            "minimum_model_clusters": MIN_HOLDOUT_CLUSTERS,
            "maximum_model_event_share": MAX_MODEL_EVENT_SHARE,
            "passes": support_passes,
        },
        "holdout_exact_landing_share": (
            float(scored["exact_lagged_rival_match"].mean()) if len(scored) else None
        ),
        "holdout_matched_market_probability": (
            float(scored["matched_market_probability"].mean()) if len(scored) else None
        ),
        "holdout_residual_inference": residual_inference,
        "holdout_log_score_gain_inference": gain_inference,
        "residual_cluster_sign_flip": residual_sign,
        "log_score_gain_cluster_sign_flip": gain_sign,
        "fixed_match_count_sensitivities": sensitivities,
        "predictive_promotion": promotion,
        "claim_boundary": (
            "Promotion rejects the declared whole-market exchangeability benchmark in "
            "favor of a persistent same-model landing increment. It does not identify "
            "strategic response, intent, front-running, collusion, profit, or welfare."
        ),
    }
    return scored, pd.DataFrame(comparison_rows), summary


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    """Execute only the outcome-free readiness path until the 30-date gate matures."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with data.pinned_analysis_source() as source_snapshot:
        date_frame = data.q(
            f"""
            select distinct cast(dt as varchar) as dt
            from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
            order by 1
            """
        ).df()
        split = registered_split(date_frame["dt"].tolist())
        if not split["ready"]:
            summary = {
                "evidence_status": "future_30_date_gate_not_ready",
                "preregistration_commit": PREREGISTRATION_COMMIT,
                "source_snapshot": source_snapshot,
                "split": split,
                "outcomes_loaded": False,
                "outcome_tables_emitted": False,
                "claim_boundary": (
                    "Only outcome-free date support was read. Quote prices, PM5 events, "
                    "holdout outcomes, and H80 outcomes were not loaded."
                ),
            }
            save_json(summary, out_dir, "pm5_heldout_matched_market_summary")
            return summary

        quotes = quote_ticks()
        panel, comparison, result = heldout_experiment(quotes, split)
        save(panel, out_dir, "pm5_heldout_matched_market_panel")
        save(comparison, out_dir, "pm5_heldout_matched_market_calibration")
        summary = {
            **result,
            "source_snapshot": source_snapshot,
            "outcomes_loaded": True,
            "outcome_tables_emitted": True,
        }
        save_json(summary, out_dir, "pm5_heldout_matched_market_summary")
        return summary
