"""WF-18: prospective HMP-style signal-coupling property tests.

The module measures residual public-price coupling, preperiod owned-routing
signal-to-noise, a researcher-estimated omitted-rival-price wedge, and forward
economic outcomes.  It never infers provider algorithms, communication, intent,
or literal collusion.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
import json
import logging
import tomllib
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from . import data
from .common import DEFAULT_OUT, save, save_json
from .market_scope import paid_model_sql
from .wf16_provider_type_validation import load_daily_quotes, load_price_changes

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "hmp_signal_coupling_v1.toml"
DEFAULT_STUDY_DIR = DEFAULT_OUT / "hmp-signal-coupling-v1"
DELEGATED_DEFAULT_POLICIES = {
    "default_budgeted_iid",
    "default_broad",
    "openrouter_default",
}


def load_protocol(path: Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    return tomllib.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def _provider_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def chronological_split(
    timestamps: pd.Series,
    *,
    calibration_fraction: float,
    mechanism_fraction: float,
) -> dict[str, Any]:
    """Freeze calibration, mechanism, and outcome dates without reading values."""
    dates = sorted(
        pd.to_datetime(timestamps, utc=True, errors="coerce").dropna().dt.normalize().unique()
    )
    if len(dates) < 3:
        raise ValueError("WF18 requires at least three complete UTC dates")
    n = len(dates)
    calibration_end_index = min(max(int(np.floor(n * calibration_fraction)), 1), n - 2)
    mechanism_end_index = min(
        max(
            int(np.floor(n * (calibration_fraction + mechanism_fraction))),
            calibration_end_index + 1,
        ),
        n - 1,
    )
    calibration_dates = dates[:calibration_end_index]
    mechanism_dates = dates[calibration_end_index:mechanism_end_index]
    outcome_dates = dates[mechanism_end_index:]
    return {
        "all_dates": dates,
        "calibration_dates": calibration_dates,
        "mechanism_dates": mechanism_dates,
        "outcome_dates": outcome_dates,
        "calibration_end": pd.Timestamp(calibration_dates[-1]),
        "mechanism_start": pd.Timestamp(mechanism_dates[0]),
        "mechanism_end": pd.Timestamp(mechanism_dates[-1]),
        "outcome_start": pd.Timestamp(outcome_dates[0]),
    }


def author_daily_prices(daily_quotes: pd.DataFrame) -> pd.DataFrame:
    """Extract the public model-author benchmark with a conservative name rule."""
    from .pm9_author_anchor import is_author_provider

    if daily_quotes.empty:
        return pd.DataFrame(columns=["model_id", "dt", "author_price", "author_log_change"])
    frame = daily_quotes.copy()
    frame["is_author"] = [
        is_author_provider(model, provider)
        for model, provider in zip(frame["model_id"], frame["provider_name"], strict=True)
    ]
    frame = frame[frame["is_author"] & (frame["price_completion"] > 0)].copy()
    daily = (
        frame.groupby(["model_id", "dt"], as_index=False)["price_completion"]
        .min()
        .rename(columns={"price_completion": "author_price"})
        .sort_values(["model_id", "dt"])
    )
    daily["author_log_change"] = daily.groupby("model_id")["author_price"].transform(
        lambda values: np.log(values).diff()
    )
    daily["author_log_change"] = daily["author_log_change"].fillna(0.0)
    return daily


def prepare_quote_innovations(
    changes: pd.DataFrame,
    author_prices: pd.DataFrame,
    split: dict[str, Any],
    *,
    ridge: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit calibration-only nuisance expectations and return residual changes."""
    columns = [
        "event_id",
        "ts",
        "dt",
        "period",
        "model_id",
        "provider_name",
        "provider_key",
        "old_price",
        "new_price",
        "raw_innovation",
        "author_log_change",
        "nuisance_fit",
        "residual_innovation",
    ]
    if changes.empty:
        return pd.DataFrame(columns=columns), {"status": "power_gated", "gate": "no price changes"}
    frame = changes.copy()
    frame = frame[(frame["old_price"] > 0) & (frame["new_price"] > 0)].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    frame["dt"] = frame["ts"].dt.normalize()
    frame["provider_key"] = frame["provider_name"].map(_provider_key)
    frame["raw_innovation"] = np.log(frame["new_price"] / frame["old_price"])
    author = author_prices[["model_id", "dt", "author_log_change"]].copy()
    author["dt"] = pd.to_datetime(author["dt"], utc=True, errors="coerce")
    frame = frame.merge(author, on=["model_id", "dt"], how="left")
    frame["author_log_change"] = frame["author_log_change"].fillna(0.0)
    frame["model_day_activity"] = frame.groupby(["model_id", "dt"])["provider_name"].transform(
        "size"
    )
    frame["hour_sin"] = np.sin(2 * np.pi * frame["ts"].dt.hour / 24.0)
    frame["hour_cos"] = np.cos(2 * np.pi * frame["ts"].dt.hour / 24.0)
    frame["dow_sin"] = np.sin(2 * np.pi * frame["ts"].dt.dayofweek / 7.0)
    frame["dow_cos"] = np.cos(2 * np.pi * frame["ts"].dt.dayofweek / 7.0)
    calibration_mask = frame["dt"].isin(split["calibration_dates"])
    calibration_days = max(len(split["calibration_dates"]), 1)
    cadence = (
        frame[calibration_mask]
        .groupby(["model_id", "provider_key"])
        .size()
        .div(calibration_days)
        .rename("calibration_cadence")
        .reset_index()
    )
    frame = frame.merge(cadence, on=["model_id", "provider_key"], how="left")
    frame["calibration_cadence"] = frame["calibration_cadence"].fillna(0.0)
    numeric = [
        "author_log_change",
        "model_day_activity",
        "calibration_cadence",
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
    ]
    fixed = pd.get_dummies(
        frame[["model_id", "provider_key"]].astype(str),
        columns=["model_id", "provider_key"],
        drop_first=True,
        dtype=float,
    )
    design = pd.concat(
        [pd.Series(1.0, index=frame.index, name="intercept"), frame[numeric].astype(float), fixed],
        axis=1,
    )
    train = calibration_mask.to_numpy()
    if int(train.sum()) < 3:
        frame["nuisance_fit"] = float(frame.loc[calibration_mask, "raw_innovation"].mean() or 0.0)
        fit_status = "thin_calibration_global_mean"
        rank = 1
    else:
        x_train = design.loc[train].to_numpy(dtype=float)
        y_train = frame.loc[train, "raw_innovation"].to_numpy(dtype=float)
        penalty = np.eye(x_train.shape[1]) * float(ridge)
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(x_train.T @ x_train + penalty, x_train.T @ y_train)
        frame["nuisance_fit"] = design.to_numpy(dtype=float) @ beta
        fit_status = "calibration_only_ridge"
        rank = int(np.linalg.matrix_rank(x_train))
    frame["residual_innovation"] = frame["raw_innovation"] - frame["nuisance_fit"]
    frame["period"] = np.select(
        [
            frame["dt"].isin(split["calibration_dates"]),
            frame["dt"].isin(split["mechanism_dates"]),
            frame["dt"].isin(split["outcome_dates"]),
        ],
        ["calibration", "mechanism", "outcome"],
        default="outside",
    )
    frame["event_id"] = [f"wf18-price-{index:08d}" for index in range(len(frame))]
    summary = {
        "status": fit_status,
        "n_events": int(len(frame)),
        "n_calibration_events": int(train.sum()),
        "design_columns": int(design.shape[1]),
        "calibration_rank": rank,
        "calibration_residual_mean": float(
            frame.loc[calibration_mask, "residual_innovation"].mean()
        )
        if calibration_mask.any()
        else None,
    }
    return frame[columns], summary


def pair_products(innovations: pd.DataFrame, *, window_hours: float) -> pd.DataFrame:
    """Create unique same-model cross-provider event pairs inside a time window."""
    columns = [
        "model_id",
        "provider_a",
        "provider_b",
        "pair_id",
        "event_a",
        "event_b",
        "lag_hours",
        "product",
        "same_direction",
    ]
    if innovations.empty:
        return pd.DataFrame(columns=columns)
    left = innovations.rename(
        columns={
            "provider_key": "provider_a",
            "event_id": "event_a",
            "ts": "ts_a",
            "residual_innovation": "residual_a",
        }
    )[["model_id", "provider_a", "event_a", "ts_a", "residual_a"]]
    right = innovations.rename(
        columns={
            "provider_key": "provider_b",
            "event_id": "event_b",
            "ts": "ts_b",
            "residual_innovation": "residual_b",
        }
    )[["model_id", "provider_b", "event_b", "ts_b", "residual_b"]]
    joined = left.merge(right, on="model_id", how="inner")
    joined = joined[
        (joined["provider_a"] < joined["provider_b"]) & (joined["event_a"] != joined["event_b"])
    ].copy()
    joined["lag_hours"] = (joined["ts_b"] - joined["ts_a"]).dt.total_seconds() / 3600.0
    joined = joined[joined["lag_hours"].abs() <= float(window_hours)].copy()
    if joined.empty:
        return pd.DataFrame(columns=columns)
    joined["pair_id"] = joined["provider_a"] + "||" + joined["provider_b"]
    joined["product"] = joined["residual_a"] * joined["residual_b"]
    joined["same_direction"] = np.sign(joined["residual_a"]) == np.sign(joined["residual_b"])
    return joined[columns].sort_values(["model_id", "pair_id", "event_a", "event_b"])


def aggregate_pair_coupling(products: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "model_id",
        "provider_a",
        "provider_b",
        "pair_id",
        "event_pairs",
        "residual_covariance",
        "same_direction_rate",
        "mean_abs_lag_hours",
    ]
    if products.empty:
        return pd.DataFrame(columns=columns)
    return (
        products.groupby(["model_id", "provider_a", "provider_b", "pair_id"], as_index=False)
        .agg(
            event_pairs=("product", "size"),
            residual_covariance=("product", "mean"),
            same_direction_rate=("same_direction", "mean"),
            mean_abs_lag_hours=("lag_hours", lambda values: float(np.mean(np.abs(values)))),
        )
        .sort_values(["model_id", "pair_id"])
        .reset_index(drop=True)
    )


def circular_sequence_inference(
    innovations: pd.DataFrame,
    *,
    window_hours: float,
    permutations: int,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Circularly shift residual sequences while preserving event clocks and marginals."""
    observed_products = pair_products(innovations, window_hours=window_hours)
    observed_pairs = aggregate_pair_coupling(observed_products)
    if observed_pairs.empty:
        return pd.DataFrame(columns=["draw", "mean_pair_covariance"]), {
            "status": "power_gated",
            "gate": "no same-model cross-provider event pairs",
            "observed_mean_pair_covariance": None,
        }
    observed = float(observed_pairs["residual_covariance"].mean())
    rng = np.random.default_rng(seed)
    null_values: list[float] = []
    groups = list(innovations.groupby(["model_id", "provider_key"], sort=True).groups.values())
    residual = innovations["residual_innovation"].to_numpy(copy=True)
    for _ in range(int(permutations)):
        shifted = residual.copy()
        for positions in groups:
            indices = np.asarray(list(positions), dtype=int)
            if len(indices) > 1:
                offset = int(rng.integers(1, len(indices)))
                shifted[indices] = np.roll(residual[indices], offset)
        permuted = innovations.copy()
        permuted["residual_innovation"] = shifted
        pair_summary = aggregate_pair_coupling(pair_products(permuted, window_hours=window_hours))
        null_values.append(
            float(pair_summary["residual_covariance"].mean()) if not pair_summary.empty else 0.0
        )
    null = np.asarray(null_values, dtype=float)
    p_value = float((1 + np.sum(null >= observed)) / (1 + len(null)))
    summary = {
        "status": "circular_sequence_randomization",
        "observed_mean_pair_covariance": observed,
        "pair_model_clusters": int(len(observed_pairs)),
        "event_pairs": int(observed_pairs["event_pairs"].sum()),
        "null_mean": float(np.mean(null)),
        "null_95_interval": [float(value) for value in np.quantile(null, [0.025, 0.975])],
        "observed_minus_null_mean": float(observed - np.mean(null)),
        "one_sided_p_excess_coupling": p_value,
        "claim_boundary": (
            "Residual covariance above a clock-preserving sequence null is excess quote "
            "synchronization, not evidence of communication, intent, or deployed algorithm type."
        ),
    }
    return pd.DataFrame({"draw": np.arange(len(null)), "mean_pair_covariance": null}), summary


def _coupling_value(innovations: pd.DataFrame, *, window_hours: float) -> tuple[float | None, int]:
    pairs = aggregate_pair_coupling(pair_products(innovations, window_hours=window_hours))
    if pairs.empty:
        return None, 0
    return float(pairs["residual_covariance"].mean()), int(len(pairs))


def _different_model_coupling(
    innovations: pd.DataFrame, *, window_hours: float
) -> tuple[float | None, int]:
    """Negative control using different-model cross-provider event pairs."""
    if innovations.empty:
        return None, 0
    columns = ["model_id", "provider_key", "ts", "residual_innovation"]
    left = innovations[columns].rename(
        columns={
            "model_id": "model_a",
            "provider_key": "provider_a",
            "ts": "ts_a",
            "residual_innovation": "residual_a",
        }
    )
    right = innovations[columns].rename(
        columns={
            "model_id": "model_b",
            "provider_key": "provider_b",
            "ts": "ts_b",
            "residual_innovation": "residual_b",
        }
    )
    joined = left.merge(right, how="cross")
    joined = joined[
        (joined["model_a"] < joined["model_b"]) & (joined["provider_a"] < joined["provider_b"])
    ].copy()
    lag = (joined["ts_b"] - joined["ts_a"]).dt.total_seconds().abs() / 3600.0
    joined = joined[lag <= float(window_hours)].copy()
    if joined.empty:
        return None, 0
    joined["product"] = joined["residual_a"] * joined["residual_b"]
    clusters = joined.groupby(["model_a", "model_b", "provider_a", "provider_b"], as_index=False)[
        "product"
    ].mean()
    return float(clusters["product"].mean()), int(len(clusters))


def load_enforcement_windows() -> pd.DataFrame:
    """Load public rate-limit/derank timestamps with a model-id mapping when available."""
    rows = _optional_query(
        f"""
        select run_ts, model_permaslug, provider_name,
               try_cast(rate_limited_5m as double) as rate_limited_5m,
               try_cast(is_deranked as boolean) as is_deranked
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        where coalesce(try_cast(rate_limited_5m as double), 0) > 0
           or coalesce(try_cast(is_deranked as boolean), false)
        """
    )
    if rows.empty:
        return pd.DataFrame(columns=["ts", "model_id", "provider_key"])
    slug_map = _optional_query(
        f"""
        select canonical_slug, min(id) as model_id
        from read_parquet('{data.table_glob("models_snapshots")}', union_by_name=true)
        where canonical_slug is not null and {paid_model_sql("id")}
        group by 1
        """
    )
    rows = rows.merge(slug_map, left_on="model_permaslug", right_on="canonical_slug", how="left")
    rows["ts"] = pd.to_datetime(rows["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce")
    rows["provider_key"] = rows["provider_name"].map(_provider_key)
    return rows.dropna(subset=["ts", "model_id"])[["ts", "model_id", "provider_key"]]


def robustness_suite(
    innovations: pd.DataFrame,
    *,
    unanchored_innovations: pd.DataFrame,
    enforcement_windows: pd.DataFrame,
    primary_window_hours: float,
    secondary_windows: list[float],
    permutations: int,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the frozen specification, negative-control, and influence diagnostics."""
    rows: list[dict[str, Any]] = []

    def record(name: str, frame: pd.DataFrame, window: float = primary_window_hours) -> None:
        value, clusters = _coupling_value(frame, window_hours=window)
        rows.append(
            {
                "check": name,
                "window_hours": float(window),
                "statistic": "mean_pair_covariance",
                "value": value,
                "clusters": clusters,
                "status": "estimated" if value is not None else "power_gated",
            }
        )

    record("primary", innovations)
    for window in secondary_windows:
        record(f"secondary_window_{window:g}h", innovations, float(window))
    record("author_anchor_excluded", unanchored_innovations)
    record("price_increases_only", innovations[innovations["raw_innovation"] > 0])
    record("price_decreases_only", innovations[innovations["raw_innovation"] < 0])
    record("author_move_windows_removed", innovations[innovations["author_log_change"] == 0])
    daily = (
        innovations.sort_values("ts")
        .drop_duplicates(["model_id", "provider_key", "dt"], keep="first")
        .reset_index(drop=True)
    )
    record("fixed_daily_frequency", daily)
    if enforcement_windows.empty:
        rows.append(
            {
                "check": "enforcement_windows_removed",
                "window_hours": float(primary_window_hours),
                "statistic": "mean_pair_covariance",
                "value": None,
                "clusters": 0,
                "status": "source_unavailable",
            }
        )
    else:
        event_index: dict[tuple[str, str], np.ndarray] = {}
        for key, group in enforcement_windows.groupby(["model_id", "provider_key"]):
            event_index[(str(key[0]), str(key[1]))] = (
                pd.to_datetime(group["ts"], utc=True).astype("int64").to_numpy()
            )
        keep = []
        for event in innovations.itertuples(index=False):
            timestamps = event_index.get((str(event.model_id), str(event.provider_key)))
            event_ns = pd.Timestamp(event.ts).value
            affected = bool(
                timestamps is not None
                and np.any(
                    np.abs(timestamps - event_ns) <= primary_window_hours * 3600 * 1_000_000_000
                )
            )
            keep.append(not affected)
        record("enforcement_windows_removed", innovations[np.asarray(keep, dtype=bool)])
    products = pair_products(innovations, window_hours=primary_window_hours)
    for name, subset in (
        ("provider_a_leads", products[products["lag_hours"] > 0]),
        ("provider_b_leads", products[products["lag_hours"] < 0]),
    ):
        pairs = aggregate_pair_coupling(subset)
        rows.append(
            {
                "check": name,
                "window_hours": float(primary_window_hours),
                "statistic": "mean_pair_covariance",
                "value": float(pairs["residual_covariance"].mean()) if not pairs.empty else None,
                "clusters": int(len(pairs)),
                "status": "estimated" if not pairs.empty else "power_gated",
            }
        )
    different_value, different_clusters = _different_model_coupling(
        innovations, window_hours=primary_window_hours
    )
    rows.append(
        {
            "check": "different_model_negative_control",
            "window_hours": float(primary_window_hours),
            "statistic": "mean_pair_covariance",
            "value": different_value,
            "clusters": different_clusters,
            "status": "estimated" if different_value is not None else "power_gated",
        }
    )
    rng = np.random.default_rng(seed)
    identity_null = []
    for _ in range(int(permutations)):
        shuffled = innovations.copy()
        shuffled["provider_key"] = shuffled.groupby("model_id")["provider_key"].transform(
            lambda values: rng.permutation(values.to_numpy())
        )
        value, _ = _coupling_value(shuffled, window_hours=primary_window_hours)
        if value is not None:
            identity_null.append(value)
    observed, _ = _coupling_value(innovations, window_hours=primary_window_hours)
    identity_p = (
        float((1 + np.sum(np.asarray(identity_null) >= observed)) / (1 + len(identity_null)))
        if observed is not None and identity_null
        else None
    )
    pair_summary = aggregate_pair_coupling(products)
    leave_out = []
    for provider in sorted(innovations["provider_key"].unique()):
        value, _ = _coupling_value(
            innovations[innovations["provider_key"] != provider],
            window_hours=primary_window_hours,
        )
        if value is not None:
            leave_out.append(value)
    for model in sorted(innovations["model_id"].unique()):
        value, _ = _coupling_value(
            innovations[innovations["model_id"] != model],
            window_hours=primary_window_hours,
        )
        if value is not None:
            leave_out.append(value)
    leader_share = (
        float(pair_summary["event_pairs"].max() / pair_summary["event_pairs"].sum())
        if not pair_summary.empty and pair_summary["event_pairs"].sum() > 0
        else None
    )
    summary = {
        "status": "complete" if rows else "power_gated",
        "checks": int(len(rows)),
        "provider_identity_shuffle_p": identity_p,
        "provider_identity_shuffle_draws": int(len(identity_null)),
        "provider_identity_shuffle_null_mean": float(np.mean(identity_null))
        if identity_null
        else None,
        "provider_identity_shuffle_null_95_interval": [
            float(value) for value in np.quantile(identity_null, [0.025, 0.975])
        ]
        if identity_null
        else None,
        "leave_one_unit_range": [float(min(leave_out)), float(max(leave_out))]
        if leave_out
        else None,
        "maximum_pair_event_share": leader_share,
        "all_required_sources_available": not enforcement_windows.empty,
        "claim_boundary": (
            "These diagnostics probe sensitivity and negative controls; none identifies intent "
            "or communication."
        ),
    }
    return pd.DataFrame(rows), summary


def _optional_query(sql: str) -> pd.DataFrame:
    try:
        return data.q(sql).df()
    except Exception as exc:
        data.reset_connection()
        log.warning("WF18 optional table unavailable: %s", exc)
        return pd.DataFrame()


def load_owned_routing_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load public candidate menus, frozen assignments, and redacted attempts."""
    candidate_frames = []
    assignment_frames = []
    for candidate_table, assignment_table in (
        ("router_calibration_candidates", "router_calibration_assignments"),
        ("market_measurement_candidates", "market_measurement_assignments"),
    ):
        candidates = _optional_query(
            f"""
            select run_id, block_id, model_id, provider_name,
                   try_cast(expected_quote_usd as double) as expected_quote_usd,
                   try_cast(conservative_quote_usd as double) as conservative_quote_usd,
                   try_cast(compatible as boolean) as compatible
            from read_parquet('{data.table_glob(candidate_table)}', union_by_name=true)
            """
        )
        assignments = _optional_query(
            f"""
            select run_id, task_id, block_id, model_id, policy
            from read_parquet('{data.table_glob(assignment_table)}', union_by_name=true)
            """
        )
        if not candidates.empty:
            candidates["source_table"] = candidate_table
            candidate_frames.append(candidates)
        if not assignments.empty:
            assignments["source_table"] = assignment_table
            assignment_frames.append(assignments)
    attempts = _optional_query(
        f"""
        select coalesce(json_extract_string(metadata_json, '$.task_id'), event_id) as task_id,
               observed_at, run_ts, study_id, model_id, policy, selected_provider,
               outcome, fallback_triggered,
               try_cast(cost_usd as double) as cost_usd,
               try_cast(latency_ms as double) as latency_ms
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        where study_id in ('openrouter-route-calibration-v1', 'openrouter-market-measurement-v1')
        """
    )
    candidates = (
        pd.concat(candidate_frames, ignore_index=True) if candidate_frames else pd.DataFrame()
    )
    assignments = (
        pd.concat(assignment_frames, ignore_index=True) if assignment_frames else pd.DataFrame()
    )
    return candidates, assignments, attempts


def build_owned_choice_risk_set(
    candidates: pd.DataFrame,
    assignments: pd.DataFrame,
    attempts: pd.DataFrame,
    *,
    delegated_policies: set[str] | None = None,
) -> pd.DataFrame:
    """Expand delegated choices to eligible alternatives without using payload data."""
    columns = [
        "task_id",
        "ts",
        "dt",
        "run_id",
        "block_id",
        "model_id",
        "policy",
        "provider_name",
        "provider_key",
        "selected_provider",
        "selected",
        "quote_usd",
        "log_quote",
        "log_relative_quote",
        "outcome",
        "fallback_triggered",
        "cost_usd",
        "latency_ms",
    ]
    policies = delegated_policies or DELEGATED_DEFAULT_POLICIES
    if candidates.empty or assignments.empty or attempts.empty:
        return pd.DataFrame(columns=columns)
    a = assignments[assignments["policy"].astype(str).isin(policies)].drop_duplicates("task_id")
    t = attempts.drop_duplicates("task_id", keep="last").copy()
    t["ts"] = pd.to_datetime(t["observed_at"], utc=True, errors="coerce").fillna(
        pd.to_datetime(t["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce")
    )
    joined = a.merge(
        t[
            [
                "task_id",
                "ts",
                "selected_provider",
                "outcome",
                "fallback_triggered",
                "cost_usd",
                "latency_ms",
            ]
        ],
        on="task_id",
        how="inner",
        validate="one_to_one",
    )
    joined = joined.dropna(subset=["ts", "selected_provider"])
    c = candidates[candidates["compatible"].fillna(False)].copy()
    c["quote_usd"] = pd.to_numeric(c["expected_quote_usd"], errors="coerce").fillna(
        pd.to_numeric(c["conservative_quote_usd"], errors="coerce")
    )
    c = c[c["quote_usd"] > 0].drop_duplicates(["block_id", "provider_name"])
    risk = joined.merge(c[["block_id", "provider_name", "quote_usd"]], on="block_id", how="inner")
    if risk.empty:
        return pd.DataFrame(columns=columns)
    risk["provider_key"] = risk["provider_name"].map(_provider_key)
    risk["selected_key"] = risk["selected_provider"].map(_provider_key)
    risk["selected"] = risk["provider_key"] == risk["selected_key"]
    risk["log_quote"] = np.log(risk["quote_usd"])
    risk["log_relative_quote"] = risk["log_quote"] - risk.groupby("task_id")["log_quote"].transform(
        "mean"
    )
    risk["dt"] = risk["ts"].dt.normalize()
    return risk[columns]


def estimate_preperiod_snr(
    risk_set: pd.DataFrame,
    *,
    preperiod_end: pd.Timestamp,
    minimum_choices: int,
) -> pd.DataFrame:
    """Estimate leave-date-out routing information by provider/model in the preperiod."""
    columns = [
        "model_id",
        "provider_key",
        "choices",
        "selection_rate",
        "relative_price_beta",
        "signal_sd",
        "residual_sd",
        "routing_snr",
        "status",
    ]
    if risk_set.empty:
        return pd.DataFrame(columns=columns)
    frame = risk_set[risk_set["dt"] <= pd.Timestamp(preperiod_end)].copy()
    rows = []
    for (model, provider), group in frame.groupby(["model_id", "provider_key"], sort=True):
        row: dict[str, Any] = {
            "model_id": model,
            "provider_key": provider,
            "choices": int(len(group)),
            "selection_rate": float(group["selected"].mean()),
        }
        group = group.sort_values(["dt", "task_id"]).reset_index(drop=True)
        x = group["log_relative_quote"].to_numpy(dtype=float)
        y = group["selected"].astype(float).to_numpy()
        dates = group["dt"].to_numpy()
        if (
            len(group) < minimum_choices
            or group["dt"].nunique() < 3
            or np.std(x) <= 1e-12
            or len(np.unique(y)) < 2
        ):
            row.update(
                {
                    "relative_price_beta": np.nan,
                    "signal_sd": np.nan,
                    "residual_sd": np.nan,
                    "routing_snr": np.nan,
                    "status": "power_gated",
                }
            )
        else:
            prediction = np.full(len(group), np.nan, dtype=float)
            slopes: list[float] = []
            minimum_training = max(10, minimum_choices // 2)
            for held_out_date in group["dt"].drop_duplicates():
                test = dates == held_out_date
                train = ~test
                if (
                    int(train.sum()) < minimum_training
                    or np.std(x[train]) <= 1e-12
                    or len(np.unique(y[train])) < 2
                ):
                    continue
                design = np.column_stack([np.ones(int(train.sum())), x[train]])
                beta = np.linalg.lstsq(design, y[train], rcond=None)[0]
                prediction[test] = beta[0] + beta[1] * x[test]
                slopes.append(float(beta[1]))
            valid = np.isfinite(prediction)
            if int(valid.sum()) < minimum_choices or not slopes:
                row.update(
                    {
                        "relative_price_beta": np.nan,
                        "signal_sd": np.nan,
                        "residual_sd": np.nan,
                        "routing_snr": np.nan,
                        "status": "power_gated",
                    }
                )
            else:
                signal_sd = float(np.std(prediction[valid], ddof=1))
                residual_sd = float(np.std(y[valid] - prediction[valid], ddof=1))
                row.update(
                    {
                        "relative_price_beta": float(np.mean(slopes)),
                        "signal_sd": signal_sd,
                        "residual_sd": residual_sd,
                        "routing_snr": signal_sd / residual_sd if residual_sd > 0 else np.nan,
                        "status": "leave_date_out_estimated",
                    }
                )
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def snr_coupling_test(
    pair_coupling: pd.DataFrame,
    snr: pd.DataFrame,
    *,
    bootstrap_draws: int,
    seed: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = list(pair_coupling.columns) + ["snr_a", "snr_b", "pair_snr"]
    if pair_coupling.empty or snr.empty:
        return pd.DataFrame(columns=columns), {
            "status": "power_gated",
            "gate": "missing coupling or SNR",
        }
    index = snr.set_index(["model_id", "provider_key"])["routing_snr"]
    panel = pair_coupling.copy()
    panel["snr_a"] = [
        index.get((m, p), np.nan) for m, p in zip(panel.model_id, panel.provider_a, strict=True)
    ]
    panel["snr_b"] = [
        index.get((m, p), np.nan) for m, p in zip(panel.model_id, panel.provider_b, strict=True)
    ]
    panel["pair_snr"] = panel[["snr_a", "snr_b"]].mean(axis=1)
    fitted = panel.dropna(subset=["pair_snr", "residual_covariance"]).copy()
    if len(fitted) < 3 or fitted["pair_snr"].nunique() < 2:
        return panel[columns], {
            "status": "power_gated",
            "gate": "fewer than three pair clusters with varying preperiod SNR",
            "covered_pairs": int(len(fitted)),
        }
    x = fitted["pair_snr"].to_numpy(dtype=float)
    y = fitted["residual_covariance"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    beta = np.linalg.lstsq(design, y, rcond=None)[0]
    rng = np.random.default_rng(seed)
    models = np.array(sorted(fitted["model_id"].unique()))
    boot = []
    if len(models) >= 2:
        for _ in range(int(bootstrap_draws)):
            sampled = rng.choice(models, len(models), replace=True)
            chunks = [fitted[fitted["model_id"] == model] for model in sampled]
            draw = pd.concat(chunks, ignore_index=True)
            dx = draw["pair_snr"].to_numpy(dtype=float)
            dy = draw["residual_covariance"].to_numpy(dtype=float)
            if np.std(dx) > 1e-12:
                boot.append(
                    float(
                        np.linalg.lstsq(np.column_stack([np.ones(len(dx)), dx]), dy, rcond=None)[0][
                            1
                        ]
                    )
                )
    interval = [float(value) for value in np.quantile(boot, [0.025, 0.975])] if boot else None
    sign_p = float((1 + np.sum(np.asarray(boot) <= 0)) / (1 + len(boot))) if boot else None
    return panel[columns], {
        "status": "model_cluster_bootstrap" if interval else "estimated_without_cluster_interval",
        "covered_pairs": int(len(fitted)),
        "models": int(fitted["model_id"].nunique()),
        "snr_gradient": float(beta[1]),
        "snr_gradient_95ci": interval,
        "one_sided_bootstrap_sign_p": sign_p,
        "positive_interval": bool(interval and interval[0] > 0),
        "claim_boundary": (
            "An SNR gradient is an HMP comparative-static consistency test, "
            "not provider algorithm identification."
        ),
    }


def pairwise_choice_rows(risk_set: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for task_id, group in risk_set.groupby("task_id", sort=False):
        selected = group[group["selected"]]
        if len(selected) != 1:
            continue
        selected_key = str(selected.iloc[0]["provider_key"])
        records = (
            group.drop_duplicates("provider_key").sort_values("provider_key").to_dict("records")
        )
        for a, b in itertools.combinations(records, 2):
            if selected_key not in {str(a["provider_key"]), str(b["provider_key"])}:
                continue
            rows.append(
                {
                    "task_id": task_id,
                    "dt": a["dt"],
                    "model_id": a["model_id"],
                    "provider_a": a["provider_key"],
                    "provider_b": b["provider_key"],
                    "pair_id": f"{a['provider_key']}||{b['provider_key']}",
                    "choose_a": int(selected_key == str(a["provider_key"])),
                    "log_price_a": float(a["log_quote"]),
                    "log_relative_price": float(a["log_quote"] - b["log_quote"]),
                }
            )
    return pd.DataFrame(rows)


def _logit_coefficient(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(y) < 2 or len(np.unique(y)) < 2 or np.std(x) <= 1e-12:
        return None
    model = LogisticRegression(C=1000.0, solver="lbfgs", max_iter=2000)
    model.fit(x.reshape(-1, 1), y)
    return float(model.coef_[0, 0])


def elasticity_wedge_panel(
    risk_set: pd.DataFrame,
    *,
    minimum_choices: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    pairs = pairwise_choice_rows(risk_set)
    columns = [
        "model_id",
        "provider_a",
        "provider_b",
        "pair_id",
        "choices",
        "omitted_beta",
        "relative_beta",
        "elasticity_wedge",
        "status",
    ]
    if pairs.empty:
        return pd.DataFrame(columns=columns), {
            "status": "power_gated",
            "gate": "no covered pairwise choices",
        }
    rows = []
    for keys, group in pairs.groupby(
        ["model_id", "provider_a", "provider_b", "pair_id"], sort=True
    ):
        omitted = _logit_coefficient(
            group["log_price_a"].to_numpy(float), group["choose_a"].to_numpy(int)
        )
        relative = _logit_coefficient(
            group["log_relative_price"].to_numpy(float), group["choose_a"].to_numpy(int)
        )
        ready = len(group) >= minimum_choices and omitted is not None and relative is not None
        rows.append(
            {
                "model_id": keys[0],
                "provider_a": keys[1],
                "provider_b": keys[2],
                "pair_id": keys[3],
                "choices": int(len(group)),
                "omitted_beta": omitted,
                "relative_beta": relative,
                "elasticity_wedge": omitted - relative if ready else np.nan,
                "status": "estimated" if ready else "power_gated",
            }
        )
    panel = pd.DataFrame(rows, columns=columns)
    estimated = panel[panel["status"] == "estimated"]
    return panel, {
        "status": "estimated" if not estimated.empty else "power_gated",
        "pair_model_clusters": int(len(panel)),
        "estimated_clusters": int(len(estimated)),
        "mean_elasticity_wedge": float(estimated["elasticity_wedge"].mean())
        if not estimated.empty
        else None,
        "claim_boundary": (
            "The wedge is a researcher specification diagnostic, not a provider belief estimate."
        ),
    }


def wedge_coupling_test(
    pair_coupling: pd.DataFrame,
    wedge: pd.DataFrame,
    *,
    bootstrap_draws: int,
    seed: int,
) -> dict[str, Any]:
    """Test whether stronger quote coupling predicts a larger wedge magnitude."""
    if pair_coupling.empty or wedge.empty:
        return {"status": "power_gated", "gate": "missing coupling or elasticity wedge"}
    panel = pair_coupling[["model_id", "provider_a", "provider_b", "residual_covariance"]].merge(
        wedge[["model_id", "provider_a", "provider_b", "elasticity_wedge", "status"]],
        on=["model_id", "provider_a", "provider_b"],
        how="inner",
    )
    panel = panel[panel["status"] == "estimated"].dropna(
        subset=["residual_covariance", "elasticity_wedge"]
    )
    if len(panel) < 3 or panel["residual_covariance"].nunique() < 2:
        return {
            "status": "power_gated",
            "gate": "fewer than three coupled pair-model elasticity cohorts",
            "covered_pairs": int(len(panel)),
        }
    x = panel["residual_covariance"].to_numpy(float)
    y = panel["elasticity_wedge"].abs().to_numpy(float)
    gradient = float(np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y, rcond=None)[0][1])
    rng = np.random.default_rng(seed)
    models = np.array(sorted(panel["model_id"].unique()))
    boot: list[float] = []
    if len(models) >= 2:
        for _ in range(int(bootstrap_draws)):
            sampled = rng.choice(models, len(models), replace=True)
            draw = pd.concat(
                [panel[panel["model_id"] == model] for model in sampled], ignore_index=True
            )
            dx = draw["residual_covariance"].to_numpy(float)
            dy = draw["elasticity_wedge"].abs().to_numpy(float)
            if np.std(dx) > 1e-12:
                boot.append(
                    float(
                        np.linalg.lstsq(np.column_stack([np.ones(len(dx)), dx]), dy, rcond=None)[0][
                            1
                        ]
                    )
                )
    interval = [float(value) for value in np.quantile(boot, [0.025, 0.975])] if boot else None
    sign_p = float((1 + np.sum(np.asarray(boot) <= 0)) / (1 + len(boot))) if boot else None
    return {
        "status": "model_cluster_bootstrap" if boot else "estimated_without_cluster_interval",
        "covered_pairs": int(len(panel)),
        "models": int(panel["model_id"].nunique()),
        "coupling_wedge_gradient": gradient,
        "coupling_wedge_gradient_95ci": interval,
        "one_sided_bootstrap_sign_p": sign_p,
        "claim_boundary": (
            "This tests a researcher-specification wedge magnitude, not provider beliefs."
        ),
    }


def forward_transition_panel(
    pair_coupling: pd.DataFrame,
    transitions: pd.DataFrame,
    *,
    permutations: int = 0,
    seed: int = 0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = [
        "model_id",
        "provider_name",
        "provider_key",
        "incident_coupling",
        "training_type",
        "outcome_type",
        "transitioned_to_premium",
    ]
    if pair_coupling.empty or transitions.empty:
        return pd.DataFrame(columns=columns), {
            "status": "power_gated",
            "gate": "missing pair coupling or frozen transitions",
        }
    incident = (
        pd.concat(
            [
                pair_coupling[["model_id", "provider_a", "residual_covariance"]].rename(
                    columns={"provider_a": "provider_key"}
                ),
                pair_coupling[["model_id", "provider_b", "residual_covariance"]].rename(
                    columns={"provider_b": "provider_key"}
                ),
            ],
            ignore_index=True,
        )
        .groupby(["model_id", "provider_key"], as_index=False)["residual_covariance"]
        .mean()
        .rename(columns={"residual_covariance": "incident_coupling"})
    )
    tr = transitions.copy()
    tr["provider_key"] = tr["provider_name"].map(_provider_key)
    outcome_column = next(
        (name for name in ("holdout_provider_type", "holdout_type", "outcome_type") if name in tr),
        None,
    )
    if outcome_column is None:
        return pd.DataFrame(columns=columns), {
            "status": "power_gated",
            "gate": "transition outcome column unavailable",
        }
    training_column = "provider_type" if "provider_type" in tr else "training_type"
    panel = incident.merge(
        tr[["model_id", "provider_name", "provider_key", training_column, outcome_column]],
        on=["model_id", "provider_key"],
        how="inner",
    )
    panel = panel.rename(columns={training_column: "training_type", outcome_column: "outcome_type"})
    panel["transitioned_to_premium"] = panel["outcome_type"] == "premium_differentiated"
    premium = panel[panel["transitioned_to_premium"]]["incident_coupling"]
    other = panel[~panel["transitioned_to_premium"]]["incident_coupling"]
    difference = float(premium.mean() - other.mean()) if len(premium) and len(other) else None
    randomization_p = None
    if difference is not None and permutations > 0:
        rng = np.random.default_rng(seed)
        values = panel["incident_coupling"].to_numpy(float)
        labels = panel["transitioned_to_premium"].to_numpy(bool)
        null = []
        for _ in range(int(permutations)):
            shuffled = rng.permutation(labels)
            if shuffled.any() and (~shuffled).any():
                null.append(float(values[shuffled].mean() - values[~shuffled].mean()))
        if null:
            randomization_p = float((1 + np.sum(np.asarray(null) >= difference)) / (1 + len(null)))
    return panel[columns], {
        "status": "descriptive_forward_transition" if difference is not None else "power_gated",
        "covered_provider_models": int(len(panel)),
        "premium_transitions": int(panel["transitioned_to_premium"].sum()),
        "coupling_difference_premium_minus_other": difference,
        "one_sided_label_randomization_p": randomization_p,
        "claim_boundary": (
            "Forward state association is observational and the author benchmark is not "
            "marginal cost."
        ),
    }


def holm_family(
    coupling: dict[str, Any],
    snr: dict[str, Any],
    wedge: dict[str, Any],
    transition: dict[str, Any],
    *,
    alpha: float,
) -> dict[str, Any]:
    """Apply Holm correction only when the frozen SC1--SC4 family is complete."""
    raw = {
        "sc1": coupling.get("one_sided_p_excess_coupling"),
        "sc2": snr.get("one_sided_bootstrap_sign_p"),
        "sc3": wedge.get("one_sided_bootstrap_sign_p"),
        "sc4": transition.get("one_sided_label_randomization_p"),
    }
    complete = all(value is not None and np.isfinite(value) for value in raw.values())
    adjusted = {name: None for name in raw}
    rejected = {name: False for name in raw}
    if complete:
        ordered = sorted(raw, key=lambda name: float(raw[name]))
        running = 0.0
        m = len(ordered)
        for rank, name in enumerate(ordered):
            running = max(running, (m - rank) * float(raw[name]))
            adjusted[name] = min(running, 1.0)
            rejected[name] = bool(adjusted[name] <= alpha)
    return {
        "family_complete": complete,
        "raw_one_sided_p": raw,
        "holm_adjusted_p": adjusted,
        "rejected_at_alpha": rejected,
        "alpha": alpha,
        "promotion_allowed": bool(complete),
    }


def support_gate(
    innovations: pd.DataFrame,
    pair_coupling: pd.DataFrame,
    risk_set: pd.DataFrame,
    wedge: pd.DataFrame,
    split: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    required = protocol["support"]
    counts = {
        "mechanism_days": len(split["mechanism_dates"]),
        "models": int(innovations[innovations["period"] == "mechanism"]["model_id"].nunique()),
        "price_experiments": int((innovations["period"] == "mechanism").sum()),
        "pair_model_clusters": int(len(pair_coupling)),
        "default_choices": int(risk_set["task_id"].nunique()) if not risk_set.empty else 0,
        "price_changing_pairs": int((wedge["choices"] > 0).sum()) if not wedge.empty else 0,
    }
    pair_share = (
        float(pair_coupling["event_pairs"].max() / pair_coupling["event_pairs"].sum())
        if not pair_coupling.empty and pair_coupling["event_pairs"].sum() > 0
        else 1.0
    )
    checks = {
        "mechanism_days": counts["mechanism_days"]
        >= int(protocol["split"]["minimum_mechanism_days"]),
        "models": counts["models"] >= int(required["minimum_models"]),
        "price_experiments": counts["price_experiments"]
        >= int(required["minimum_price_experiments"]),
        "pair_model_clusters": counts["pair_model_clusters"]
        >= int(required["minimum_pair_model_clusters"]),
        "default_choices": counts["default_choices"] >= int(required["minimum_default_choices"]),
        "price_changing_pairs": counts["price_changing_pairs"]
        >= int(required["minimum_price_changing_pairs"]),
        "pair_concentration": pair_share <= float(required["maximum_pair_share"]),
    }
    return {
        "release_ready": bool(all(checks.values())),
        "counts": counts,
        "checks": checks,
        "maximum_pair_share": pair_share,
        "failed_gates": [name for name, passed in checks.items() if not passed],
    }


def claim_level(
    coupling: dict[str, Any],
    snr: dict[str, Any],
    wedge: dict[str, Any],
    transition: dict[str, Any],
    *,
    release_ready: bool,
    alpha: float,
    family: dict[str, Any] | None = None,
) -> dict[str, Any]:
    family = family or holm_family(coupling, snr, wedge, transition, alpha=alpha)
    rejected = family["rejected_at_alpha"]
    sc1 = bool(
        release_ready
        and family["family_complete"]
        and rejected["sc1"]
        and coupling.get("one_sided_p_excess_coupling") is not None
        and coupling.get("observed_minus_null_mean", 0) > 0
    )
    sc2 = bool(sc1 and rejected["sc2"] and snr.get("snr_gradient", 0) > 0)
    sc3 = bool(sc2 and rejected["sc3"] and wedge.get("coupling_wedge_gradient", 0) > 0)
    sc4 = bool(
        sc3
        and rejected["sc4"]
        and transition.get("coupling_difference_premium_minus_other") is not None
        and transition["coupling_difference_premium_minus_other"] > 0
    )
    if sc4:
        level = "hmp_consistent_chain_with_forward_premium_association"
    elif sc3:
        level = "hmp_consistent_coupling_and_researcher_elasticity_distortion"
    elif sc2:
        level = "hmp_consistent_snr_comparative_static"
    elif sc1:
        level = "excess_residual_quote_synchronization"
    else:
        level = "no_promoted_confirmatory_claim"
    return {
        "level": level,
        "sc1": sc1,
        "sc2": sc2,
        "sc3": sc3,
        "sc4": sc4,
        "holm_family_complete": bool(family["family_complete"]),
        "collusion_identified": False,
        "provider_algorithm_identified": False,
        "communication_identified": False,
    }


def _render(
    out_dir: Path,
    pair_coupling: pd.DataFrame,
    null: pd.DataFrame,
    coupling_summary: dict[str, Any],
    snr_panel: pd.DataFrame,
    wedge: pd.DataFrame,
    transition: pd.DataFrame,
    gate: dict[str, Any],
) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(13.2, 7.4), constrained_layout=True)
    if not null.empty:
        axes[0, 0].hist(null["mean_pair_covariance"], bins=30, color="#9cb8cc", edgecolor="white")
        observed = coupling_summary.get("observed_mean_pair_covariance")
        if observed is not None:
            axes[0, 0].axvline(observed, color="#8b1e3f", lw=2, label="observed")
            axes[0, 0].legend(frameon=False)
    axes[0, 0].set_title("A. Residual-coupling randomization null")
    axes[0, 0].set_xlabel("mean pair covariance")
    if not pair_coupling.empty:
        shown = pair_coupling.sort_values("residual_covariance")
        axes[0, 1].scatter(
            shown["event_pairs"], shown["residual_covariance"], s=22, alpha=0.75, color="#22577a"
        )
        axes[0, 1].axhline(0, color="black", lw=0.8)
    axes[0, 1].set_title("B. Pair coupling and support")
    axes[0, 1].set_xlabel("paired quote events")
    axes[0, 1].set_ylabel("residual covariance")
    covered = (
        snr_panel.dropna(subset=["pair_snr", "residual_covariance"])
        if not snr_panel.empty
        else pd.DataFrame()
    )
    if not covered.empty:
        axes[0, 2].scatter(
            covered["pair_snr"], covered["residual_covariance"], s=25, alpha=0.75, color="#2a9d8f"
        )
    axes[0, 2].set_title("C. Preperiod routing SNR")
    axes[0, 2].set_xlabel("pair SNR")
    axes[0, 2].set_ylabel("later residual covariance")
    estimated = wedge.dropna(subset=["elasticity_wedge"]) if not wedge.empty else pd.DataFrame()
    if not estimated.empty:
        axes[1, 0].scatter(
            estimated["choices"], estimated["elasticity_wedge"], s=25, alpha=0.75, color="#e76f51"
        )
        axes[1, 0].axhline(0, color="black", lw=0.8)
    axes[1, 0].set_title("D. Omitted-rival elasticity wedge")
    axes[1, 0].set_xlabel("owned pairwise choices")
    axes[1, 0].set_ylabel("omitted minus relative coefficient")
    if not transition.empty:
        grouped = transition.groupby("transitioned_to_premium")["incident_coupling"].mean()
        axes[1, 1].bar(
            ["other", "premium"],
            [grouped.get(False, np.nan), grouped.get(True, np.nan)],
            color=["#9cb8cc", "#8b1e3f"],
        )
    axes[1, 1].set_title("E. Future pricing state")
    axes[1, 1].set_ylabel("mean incident coupling")
    checks = gate["checks"]
    names = list(checks)
    axes[1, 2].barh(
        range(len(names)),
        [1 if checks[name] else 0 for name in names],
        color=["#2a9d8f" if checks[name] else "#d9d9d9" for name in names],
    )
    axes[1, 2].set_yticks(range(len(names)), labels=[name.replace("_", " ") for name in names])
    axes[1, 2].set_xlim(0, 1)
    axes[1, 2].set_title("F. Confirmatory support gates")
    fig.suptitle("WF-18 HMP-style signal coupling: monitoring, not intent inference", fontsize=14)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "wf18_signal_coupling.png", dpi=180)
    fig.savefig(out_dir / "wf18_signal_coupling.pdf")
    plt.close(fig)
    encoded = base64.b64encode((out_dir / "wf18_signal_coupling.png").read_bytes()).decode("ascii")
    dashboard = (
        "<!doctype html><meta charset='utf-8'><title>WF-18 signal coupling</title>"
        "<style>body{font:15px system-ui;max-width:1180px;margin:32px auto;color:#17202a}"
        "img{max-width:100%;height:auto}.boundary{border-left:4px solid #b7791f;padding:12px;"
        "background:#fff8e6}</style><h1>WF-18 HMP-style signal coupling</h1>"
        f"<p><b>Release ready:</b> {str(gate['release_ready']).lower()}</p>"
        f"<img alt='WF-18 six-panel diagnostic' src='data:image/png;base64,{encoded}'>"
        "<p class='boundary'>Residual coupling, SNR gradients, and elasticity wedges do not "
        "identify communication, intent, provider algorithms, or literal collusion.</p>"
    )
    (out_dir / "wf18_signal_coupling.html").write_text(dashboard, encoding="utf-8")


def _load_transitions(out_dir: Path) -> pd.DataFrame:
    path = out_dir / "wf16_holdout_transitions.parquet"
    return pd.read_parquet(path) if path.is_file() else pd.DataFrame()


def run(out_dir: Path = DEFAULT_STUDY_DIR, *, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    protocol, protocol_sha = load_protocol(config_path)
    with data.pinned_analysis_source() as source:
        changes = load_price_changes()
        daily = load_daily_quotes()
        candidates, assignments, attempts = load_owned_routing_tables()
        enforcement_windows = load_enforcement_windows()
    if changes.empty:
        raise ValueError("WF18 requires public completion-price changes")
    split = chronological_split(
        changes["ts"],
        calibration_fraction=float(protocol["split"]["calibration_fraction"]),
        mechanism_fraction=float(protocol["split"]["mechanism_fraction"]),
    )
    innovations, residual_summary = prepare_quote_innovations(
        changes,
        author_daily_prices(daily),
        split,
        ridge=float(protocol["residualization"]["ridge"]),
    )
    unanchored_author = author_daily_prices(daily)
    unanchored_author["author_log_change"] = 0.0
    unanchored_innovations, _ = prepare_quote_innovations(
        changes,
        unanchored_author,
        split,
        ridge=float(protocol["residualization"]["ridge"]),
    )
    mechanism = innovations[innovations["period"] == "mechanism"].reset_index(drop=True)
    unanchored_mechanism = unanchored_innovations[
        unanchored_innovations["period"] == "mechanism"
    ].reset_index(drop=True)
    pair_coupling = aggregate_pair_coupling(
        pair_products(
            mechanism, window_hours=float(protocol["residualization"]["primary_window_hours"])
        )
    )
    null, coupling_summary = circular_sequence_inference(
        mechanism,
        window_hours=float(protocol["residualization"]["primary_window_hours"]),
        permutations=int(protocol["inference"]["permutations"]),
        seed=int(protocol["inference"]["seed"]),
    )
    robustness, robustness_summary = robustness_suite(
        mechanism,
        unanchored_innovations=unanchored_mechanism,
        enforcement_windows=enforcement_windows,
        primary_window_hours=float(protocol["residualization"]["primary_window_hours"]),
        secondary_windows=[
            float(value) for value in protocol["residualization"]["secondary_window_hours"]
        ],
        permutations=int(protocol["inference"]["diagnostic_permutations"]),
        seed=int(protocol["inference"]["seed"]) + 4,
    )
    risk_set = build_owned_choice_risk_set(
        candidates,
        assignments,
        attempts,
        delegated_policies=set(protocol["owned_routing"]["delegated_policies"]),
    )
    snr = estimate_preperiod_snr(
        risk_set,
        preperiod_end=split["calibration_end"],
        minimum_choices=int(protocol["owned_routing"]["minimum_choices_per_provider_model"]),
    )
    snr_panel, snr_summary = snr_coupling_test(
        pair_coupling,
        snr,
        bootstrap_draws=int(protocol["inference"]["bootstrap_draws"]),
        seed=int(protocol["inference"]["seed"]) + 1,
    )
    wedge, wedge_level_summary = elasticity_wedge_panel(
        risk_set,
        minimum_choices=int(protocol["support"]["minimum_choices_per_elasticity_cohort"]),
    )
    wedge_relation_summary = wedge_coupling_test(
        pair_coupling,
        wedge,
        bootstrap_draws=int(protocol["inference"]["bootstrap_draws"]),
        seed=int(protocol["inference"]["seed"]) + 2,
    )
    wedge_summary = {**wedge_level_summary, **wedge_relation_summary}
    transitions = _load_transitions(out_dir)
    transition_panel, transition_summary = forward_transition_panel(
        pair_coupling,
        transitions,
        permutations=int(protocol["inference"]["bootstrap_draws"]),
        seed=int(protocol["inference"]["seed"]) + 3,
    )
    gate = support_gate(innovations, pair_coupling, risk_set, wedge, split, protocol)
    family = holm_family(
        coupling_summary,
        snr_summary,
        wedge_summary,
        transition_summary,
        alpha=float(protocol["inference"]["alpha"]),
    )
    claims = claim_level(
        coupling_summary,
        snr_summary,
        wedge_summary,
        transition_summary,
        release_ready=gate["release_ready"],
        alpha=float(protocol["inference"]["alpha"]),
        family=family,
    )
    save(innovations, out_dir, "wf18_quote_innovations")
    save(pair_coupling, out_dir, "wf18_pair_coupling")
    save(null, out_dir, "wf18_circular_null")
    save(robustness, out_dir, "wf18_robustness_checks")
    save(risk_set, out_dir, "wf18_owned_choice_risk_set")
    save(snr, out_dir, "wf18_preperiod_snr")
    save(snr_panel, out_dir, "wf18_snr_coupling_panel")
    save(wedge, out_dir, "wf18_elasticity_wedges")
    save(transition_panel, out_dir, "wf18_forward_transitions")
    summary = {
        "study_id": protocol["study"]["id"],
        "analysis_id": protocol["study"]["analysis_id"],
        "evidence_status": "monitoring"
        if not gate["release_ready"]
        else "support_ready_not_yet_released",
        "source": source,
        "protocol_sha256": protocol_sha,
        "split": {
            "date_range": [str(split["all_dates"][0])[:10], str(split["all_dates"][-1])[:10]],
            "calibration_days": len(split["calibration_dates"]),
            "mechanism_days": len(split["mechanism_dates"]),
            "outcome_days": len(split["outcome_dates"]),
            "calibration_end": str(split["calibration_end"]),
            "mechanism_start": str(split["mechanism_start"]),
            "mechanism_end": str(split["mechanism_end"]),
            "outcome_start": str(split["outcome_start"]),
        },
        "residualization": residual_summary,
        "sc1_residual_coupling": coupling_summary,
        "robustness": robustness_summary,
        "sc2_snr_gradient": snr_summary,
        "sc3_elasticity_wedge": wedge_summary,
        "sc4_forward_transition": transition_summary,
        "multiplicity": family,
        "support_gate": gate,
        "claim_level": claims,
        "collusion_identified": False,
        "provider_algorithm_identified": False,
        "communication_identified": False,
        "claim_boundary": (
            "WF18 tests an ordered HMP-consistent property chain. Public quote coupling and "
            "owned-routing specification wedges do not reveal provider beliefs, algorithms, "
            "communications, intent, marginal cost, or market-wide flow."
        ),
    }
    save_json(summary, out_dir, "wf18_summary")
    save_json(gate, out_dir, "wf18_release_preflight")
    (out_dir / "source-revision.txt").write_text(
        str(source.get("revision") or "local") + "\n", encoding="utf-8"
    )
    _render(
        out_dir, pair_coupling, null, coupling_summary, snr_panel, wedge, transition_panel, gate
    )
    return summary


def preflight(
    out_dir: Path = DEFAULT_STUDY_DIR, *, config_path: Path = DEFAULT_CONFIG
) -> dict[str, Any]:
    """Sample-only preflight: counts rows and dates without reading price values or selections."""
    protocol, protocol_sha = load_protocol(config_path)
    with data.pinned_analysis_source() as source:
        price_support = data.q(
            f"""
            select cast(dt as varchar) as dt, count(*) as rows,
                   count(distinct model_id) as models,
                   count(distinct provider_name) as providers
            from read_parquet(
              '{data.table_glob("pricing_changes", layer="derived")}',
              union_by_name=true
            )
            where field = 'price_completion'
            group by 1 order by 1
            """
        ).df()
        pair_support = data.q(
            f"""
            with provider_models as (
              select distinct model_id, provider_name
              from read_parquet(
                '{data.table_glob("pricing_changes", layer="derived")}',
                union_by_name=true
              )
              where field = 'price_completion'
            ), model_counts as (
              select model_id, count(*) as providers
              from provider_models group by 1
            )
            select count(*) as models,
                   sum(providers * (providers - 1) / 2) as possible_pair_model_clusters
            from model_counts
            """
        ).df()
        attempt_support = _optional_query(
            f"""
            select count(distinct coalesce(
                     json_extract_string(metadata_json, '$.task_id'), event_id
                   )) as tasks
            from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
            where study_id in (
              'openrouter-route-calibration-v1',
              'openrouter-market-measurement-v1'
            )
              and policy in ('default_budgeted_iid', 'default_broad', 'openrouter_default')
            """
        )
    dates = pd.to_datetime(
        price_support.get("dt", pd.Series(dtype=str)), utc=True, errors="coerce"
    ).dropna()
    total_days_required = (
        int(protocol["split"]["minimum_calibration_days"])
        + int(protocol["split"]["minimum_mechanism_days"])
        + int(protocol["split"]["minimum_outcome_days"])
    )
    possible_pairs = (
        int(pair_support.iloc[0]["possible_pair_model_clusters"] or 0)
        if not pair_support.empty
        else 0
    )
    model_count = int(pair_support.iloc[0]["models"] or 0) if not pair_support.empty else 0
    delegated_tasks = int(attempt_support.iloc[0]["tasks"]) if not attempt_support.empty else 0
    price_rows = int(price_support.get("rows", pd.Series(dtype=int)).sum())
    sample_checks = {
        "complete_days": int(dates.nunique()) >= total_days_required,
        "models": model_count >= int(protocol["support"]["minimum_models"]),
        "price_rows": price_rows >= int(protocol["support"]["minimum_price_experiments"]),
        "possible_pair_model_clusters": possible_pairs
        >= int(protocol["support"]["minimum_pair_model_clusters"]),
        "delegated_tasks": delegated_tasks >= int(protocol["support"]["minimum_default_choices"]),
    }
    result = {
        "study_id": protocol["study"]["id"],
        "protocol_sha256": protocol_sha,
        "source": source,
        "complete_price_days": int(dates.nunique()),
        "price_rows": price_rows,
        "models": model_count,
        "providers": int(price_support.get("providers", pd.Series(dtype=int)).max() or 0),
        "possible_pair_model_clusters": possible_pairs,
        "delegated_tasks": delegated_tasks,
        "sample_checks": sample_checks,
        "sample_gate_candidate": bool(all(sample_checks.values())),
        "outcomes_accessed": False,
        "claim_boundary": (
            "Assignment/sample support only; quote values and routing outcomes are not read."
        ),
    }
    save_json(result, out_dir, "wf18_assignment_only_preflight")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_STUDY_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    result = (
        preflight(args.out, config_path=args.config)
        if args.preflight
        else run(args.out, config_path=args.config)
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
