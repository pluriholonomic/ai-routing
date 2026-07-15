"""H83 — future-only confirmation of a hidden-capacity overshoot cycle.

H82 discovered that successful share loads onto a soon-constrained endpoint,
breaks at a high-intensity rate-limit onset, and partially recovers while price
is sticky. H83 freezes that shape and excludes every event whose lead window
touches the discovery panel. Before the sample-only release gates are met, the
module exposes support diagnostics but no future shape coefficient.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save, save_json
from .h82_enforcement_substitution import (
    BOOTSTRAP_SEED,
    PRIMARY_PRE,
    build_event_time_panel,
    canonical_panel,
    daily_coverage,
    event_effects,
    event_registry,
    load_rows,
    match_negative_controls,
)

DISCOVERY_CUTOFF = pd.Timestamp("2026-07-15T12:00:00Z")
FIRST_ELIGIBLE_EVENT = DISCOVERY_CUTOFF + pd.to_timedelta(30, unit="min")
MIN_SUBWINDOW_CELLS = 2
BOOTSTRAP_DRAWS = 10_000

SHARE_METRICS = ["endpoint_success_share", "provider_success_share"]
COMPONENTS = {
    "loading": ((-15, -5), (-30, -20), 1),
    "break": ((5, 10), (-10, -5), -1),
    "recovery": ((45, 60), (5, 20), 1),
    "level_loss": ((5, 30), (-30, -5), -1),
}


def future_events(panel: pd.DataFrame) -> pd.DataFrame:
    events = event_registry(panel)
    if events.empty:
        return events
    return events[events["event_ts"].ge(FIRST_ELIGIBLE_EVENT)].reset_index(drop=True)


def _supported_mean(
    group: pd.DataFrame, metric: str, bounds: tuple[int, int]
) -> tuple[float, int]:
    values = group.loc[group["relative_minutes"].between(*bounds), metric].dropna()
    if len(values) < MIN_SUBWINDOW_CELLS:
        return np.nan, int(len(values))
    return float(values.mean()), int(len(values))


def shape_effects(event_time: pd.DataFrame, base_effects: pd.DataFrame) -> pd.DataFrame:
    """Construct the four frozen future-only shape components."""
    if event_time.empty:
        return pd.DataFrame()
    complete_map = (
        base_effects.set_index("event_id")["complete_event"].astype(bool).to_dict()
        if not base_effects.empty
        else {}
    )
    records: list[dict[str, Any]] = []
    for event_id, group in event_time.groupby("event_id", sort=False):
        first = group.iloc[0]
        event_ts = pd.Timestamp(first["event_ts"])
        record: dict[str, Any] = {
            "event_id": event_id,
            "event_class": first["event_class"],
            "event_ts": event_ts,
            "event_date": str(event_ts.date()),
            "model_permaslug": first["model_permaslug"],
            "endpoint_uuid": first["endpoint_uuid"],
            "provider_name": first["provider_name"],
            "cluster": f"{first['model_permaslug']}|{event_ts.date()}",
            "base_complete_event": bool(complete_map.get(event_id, False)),
        }
        supported = bool(record["base_complete_event"])
        for metric in SHARE_METRICS:
            for component, (positive_window, negative_window, _) in COMPONENTS.items():
                positive, positive_n = _supported_mean(group, metric, positive_window)
                negative, negative_n = _supported_mean(group, metric, negative_window)
                record[f"{metric}_{component}"] = (
                    positive - negative
                    if np.isfinite(positive) and np.isfinite(negative)
                    else np.nan
                )
                record[f"{metric}_{component}_positive_cells"] = positive_n
                record[f"{metric}_{component}_negative_cells"] = negative_n
                supported &= bool(
                    positive_n >= MIN_SUBWINDOW_CELLS
                    and negative_n >= MIN_SUBWINDOW_CELLS
                    and np.isfinite(record[f"{metric}_{component}"])
                )
        prices = group.loc[group["relative_minutes"].between(-30, 60), "price_completion"].dropna()
        if len(prices) >= 2:
            tolerance = max(1e-12, abs(float(prices.mean())) * 1e-9)
            record["price_sticky"] = bool(float(prices.max() - prices.min()) <= tolerance)
        else:
            record["price_sticky"] = np.nan
            supported = False
        record["complete_shape_event"] = supported
        record["accounting_residual_max"] = float(group["accounting_residual"].abs().max())
        records.append(record)
    return pd.DataFrame(records)


def matched_shape_contrasts(
    shapes: pd.DataFrame, base_matches: pd.DataFrame
) -> pd.DataFrame:
    """Apply H82's pre-treatment pairs to the frozen shape components."""
    if shapes.empty or base_matches.empty:
        return pd.DataFrame()
    supported = shapes[shapes["complete_shape_event"].astype(bool)].copy()
    high_columns = [
        "event_id",
        "event_ts",
        "cluster",
        *[
            f"{metric}_{component}"
            for metric in SHARE_METRICS
            for component in COMPONENTS
        ],
    ]
    low_columns = [
        "event_id",
        "event_ts",
        *[
            f"{metric}_{component}"
            for metric in SHARE_METRICS
            for component in COMPONENTS
        ],
    ]
    high = supported[supported["event_class"].eq("high")].loc[:, high_columns]
    low = supported[supported["event_class"].eq("low")].loc[:, low_columns]
    merged = base_matches.loc[:, ["high_event_id", "low_event_id", "match_score"]].merge(
        high,
        left_on="high_event_id",
        right_on="event_id",
        how="inner",
        validate="one_to_one",
    )
    merged = merged.merge(
        low,
        left_on="low_event_id",
        right_on="event_id",
        how="inner",
        suffixes=("_high", "_low"),
        validate="one_to_one",
    )
    for metric in SHARE_METRICS:
        for component in COMPONENTS:
            merged[f"{metric}_{component}_high_minus_low"] = (
                merged[f"{metric}_{component}_high"]
                - merged[f"{metric}_{component}_low"]
            )
    return merged


def cluster_interval(
    frame: pd.DataFrame,
    column: str,
    *,
    cluster_column: str = "cluster",
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED + 83,
) -> dict[str, Any]:
    """Return a mean and 90% equal-tailed interval (one-sided 95% bounds)."""
    sample = frame.loc[:, [column, cluster_column]].dropna()
    if sample.empty:
        return {"n": 0, "clusters": 0, "mean": None, "one_sided_95_bounds": [None, None]}
    grouped = sample.groupby(cluster_column, sort=False)[column]
    sums = grouped.sum().to_numpy(dtype=float)
    counts = grouped.size().to_numpy(dtype=float)
    estimate = float(sample[column].mean())
    if len(sums) == 1:
        bounds = [None, None]
    else:
        rng = np.random.default_rng(seed)
        indices = rng.integers(0, len(sums), size=(draws, len(sums)))
        sampled = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
        quantiles = np.quantile(sampled, [0.05, 0.95])
        bounds = [float(quantiles[0]), float(quantiles[1])]
    return {
        "n": int(len(sample)),
        "clusters": int(len(sums)),
        "mean": estimate,
        "one_sided_95_bounds": bounds,
    }


def _predicted_sign_pass(result: dict[str, Any], direction: int) -> bool:
    lower, upper = result["one_sided_95_bounds"]
    if lower is None or upper is None:
        return False
    return bool(lower > 0) if direction > 0 else bool(upper < 0)


def _all_leave_one_provider_signs(
    high: pd.DataFrame, column: str, direction: int
) -> bool:
    providers = high["provider_name"].dropna().unique()
    if not len(providers):
        return False
    for provider in providers:
        estimate = high.loc[~high["provider_name"].eq(provider), column].mean()
        if pd.isna(estimate) or np.sign(estimate) != direction:
            return False
    return True


def sample_release_cutoff(
    panel: pd.DataFrame,
    shapes: pd.DataFrame,
    matched: pd.DataFrame,
    coverage: pd.DataFrame,
    event_time: pd.DataFrame,
) -> pd.Timestamp | None:
    """Find the earliest sample-supported cut without consulting shape signs."""
    if shapes.empty or coverage.empty:
        return None
    high = shapes[
        shapes["complete_shape_event"].astype(bool) & shapes["event_class"].eq("high")
    ].copy()
    if high.empty:
        return None
    panel_by_day = panel.assign(day=panel["ts"].dt.strftime("%Y-%m-%d")).groupby("day")[
        "ts"
    ].max()
    complete_days = coverage[coverage["complete_day"].astype(bool)].sort_values("dt")
    if len(complete_days) < 28:
        return None
    for day in complete_days.iloc[27:]["dt"]:
        cutoff = pd.Timestamp(panel_by_day.get(day))
        if pd.isna(cutoff):
            continue
        prefix = high[high["event_ts"].le(cutoff)]
        if len(prefix) < 300:
            continue
        if prefix["model_permaslug"].nunique() < 20 or prefix["provider_name"].nunique() < 20:
            continue
        dominance = prefix["provider_name"].value_counts().iloc[0] / len(prefix)
        if dominance > 0.20:
            continue
        prefix_matches = matched[
            matched["event_ts_high"].le(cutoff) & matched["event_ts_low"].le(cutoff)
        ]
        if len(prefix_matches) < 250:
            continue
        event_ids = set(prefix["event_id"])
        residual = event_time[event_time["event_id"].isin(event_ids)][
            "accounting_residual"
        ].abs().max()
        if pd.isna(residual) or residual > 1e-9:
            continue
        return cutoff
    return None


def _shape_results(
    released_shapes: pd.DataFrame, released_matches: pd.DataFrame
) -> tuple[dict[str, Any], bool]:
    high = released_shapes[
        released_shapes["complete_shape_event"].astype(bool)
        & released_shapes["event_class"].eq("high")
    ].copy()
    results: dict[str, Any] = {}
    provider_joint_pass = True
    endpoint_sign_pass = True
    endpoint_break_pass = False
    matched_provider_pass = True
    matched_break_loss_pass = True
    leave_one_provider_pass = True
    for metric_offset, metric in enumerate(SHARE_METRICS):
        metric_results: dict[str, Any] = {}
        for component_offset, (component, (_, _, direction)) in enumerate(COMPONENTS.items()):
            column = f"{metric}_{component}"
            estimate = cluster_interval(
                high,
                column,
                seed=BOOTSTRAP_SEED + 830 + metric_offset * 10 + component_offset,
            )
            sign_pass = _predicted_sign_pass(estimate, direction)
            model_equal = high.groupby("model_permaslug")[column].mean().mean()
            loo_pass = _all_leave_one_provider_signs(high, column, direction)
            matched_column = f"{metric}_{component}_high_minus_low"
            matched_estimate = cluster_interval(
                released_matches,
                matched_column,
                cluster_column="cluster",
                seed=BOOTSTRAP_SEED + 930 + metric_offset * 10 + component_offset,
            )
            matched_sign = bool(
                matched_estimate["mean"] is not None
                and np.sign(matched_estimate["mean"]) == direction
            )
            metric_results[component] = {
                "high_event": estimate,
                "predicted_sign_interval_pass": sign_pass,
                "model_equal_weighted_mean": float(model_equal),
                "leave_one_provider_sign_pass": loo_pass,
                "matched_high_minus_low": matched_estimate,
                "matched_sign_pass": matched_sign,
            }
            if metric == "provider_success_share":
                provider_joint_pass &= sign_pass
                matched_provider_pass &= matched_sign
                leave_one_provider_pass &= loo_pass
                if component in {"break", "level_loss"}:
                    matched_break_loss_pass &= _predicted_sign_pass(
                        matched_estimate, direction
                    )
            else:
                endpoint_sign_pass &= bool(
                    estimate["mean"] is not None and np.sign(estimate["mean"]) == direction
                )
                if component == "break":
                    endpoint_break_pass = sign_pass
        results[metric] = metric_results
    sticky = high["price_sticky"].dropna()
    sticky_share = float(sticky.mean()) if len(sticky) else None
    confirmation = bool(
        provider_joint_pass
        and endpoint_sign_pass
        and endpoint_break_pass
        and matched_provider_pass
        and matched_break_loss_pass
        and leave_one_provider_pass
        and sticky_share is not None
        and sticky_share >= 0.95
    )
    results["joint_conditions"] = {
        "provider_component_intervals": provider_joint_pass,
        "endpoint_component_signs": endpoint_sign_pass,
        "endpoint_break_interval": endpoint_break_pass,
        "provider_matched_signs": matched_provider_pass,
        "provider_matched_break_and_loss_intervals": matched_break_loss_pass,
        "provider_leave_one_out_signs": leave_one_provider_pass,
        "price_sticky_share": sticky_share,
        "price_sticky_requirement": 0.95,
        "cycle_confirmed": confirmation,
    }
    return results, confirmation


def plot_released_paths(event_time: pd.DataFrame, out_dir: Path) -> None:
    if event_time.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharex=True, sharey=True)
    for axis, metric in zip(axes, SHARE_METRICS, strict=True):
        for event_class, color in [("high", "#B23A48"), ("low", "#3572A5")]:
            subset = event_time[event_time["event_class"].eq(event_class)].copy()
            pre = (
                subset[subset["relative_minutes"].between(*PRIMARY_PRE)]
                .groupby("event_id")[metric]
                .mean()
            )
            subset["normalized"] = subset[metric] - subset["event_id"].map(pre)
            path = subset.groupby("relative_minutes")["normalized"].agg(["mean", "std", "count"])
            se = path["std"] / np.sqrt(path["count"].clip(lower=1))
            axis.plot(path.index, path["mean"], marker="o", ms=3, color=color, label=event_class)
            axis.fill_between(
                path.index.to_numpy(dtype=float),
                (path["mean"] - 1.96 * se).to_numpy(dtype=float),
                (path["mean"] + 1.96 * se).to_numpy(dtype=float),
                color=color,
                alpha=0.13,
            )
        axis.axvline(0, color="black", ls="--", lw=1)
        axis.axhline(0, color="black", lw=0.6, alpha=0.4)
        axis.set_title(metric.replace("_", " ").title())
        axis.set_xlabel("Minutes from onset")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Change from event pre-mean")
    axes[0].legend(frameon=False)
    fig.suptitle("H83 future-only capacity-overshoot paths")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h83_capacity_overshoot.png", dpi=180)
    fig.savefig(out_dir / "h83_capacity_overshoot.pdf")
    plt.close(fig)


def analyze(rows: pd.DataFrame, out_dir: Path | None = None) -> dict[str, Any]:
    panel = canonical_panel(rows)
    if panel.empty:
        result = {
            "evidence_status": "future_holdout_power_gated",
            "outcomes_released": False,
            "claim_boundary": "No eligible post-discovery enforcement observations exist.",
        }
        if out_dir is not None:
            save_json(result, out_dir, "h83_summary")
        return result
    events = future_events(panel)
    event_time = build_event_time_panel(panel, events)
    base_effects = event_effects(event_time)
    shapes = shape_effects(event_time, base_effects)
    base_matches = match_negative_controls(base_effects)
    matched = matched_shape_contrasts(shapes, base_matches)
    post_panel = panel[panel["ts"].gt(DISCOVERY_CUTOFF)].copy()
    coverage = daily_coverage(post_panel)
    cutoff = sample_release_cutoff(panel, shapes, matched, coverage, event_time)

    eligible_high = events[
        events["analysis_eligible"].astype(bool) & events["event_class"].eq("high")
    ] if not events.empty else events
    complete_high = shapes[
        shapes["complete_shape_event"].astype(bool) & shapes["event_class"].eq("high")
    ] if not shapes.empty else shapes
    dominance = (
        float(complete_high["provider_name"].value_counts().iloc[0] / len(complete_high))
        if len(complete_high)
        else None
    )
    result: dict[str, Any] = {
        "evidence_status": "future_holdout_power_gated" if cutoff is None else "released",
        "preregistration": "docs/h83-capacity-overshoot-preregistration.md",
        "discovery_cutoff": DISCOVERY_CUTOFF.isoformat(),
        "first_eligible_event": FIRST_ELIGIBLE_EVENT.isoformat(),
        "outcomes_released": cutoff is not None,
        "release_cutoff": cutoff.isoformat() if cutoff is not None else None,
        "support": {
            "candidate_high_onsets": int(events["event_class"].eq("high").sum())
            if not events.empty
            else 0,
            "eligible_high_onsets": int(len(eligible_high)),
            "complete_shape_high_events": int(len(complete_high)),
            "complete_low_events": int(
                (
                    shapes["complete_shape_event"].astype(bool)
                    & shapes["event_class"].eq("low")
                ).sum()
            )
            if not shapes.empty
            else 0,
            "matched_pairs": int(len(matched)),
            "complete_days": int(coverage["complete_day"].sum()) if not coverage.empty else 0,
            "models": int(complete_high["model_permaslug"].nunique())
            if not complete_high.empty
            else 0,
            "providers": int(complete_high["provider_name"].nunique())
            if not complete_high.empty
            else 0,
            "provider_dominance": dominance,
            "maximum_accounting_residual": float(event_time["accounting_residual"].abs().max())
            if not event_time.empty
            else None,
        },
        "sample_release_requirements": {
            "complete_days": 28,
            "complete_high_events": 300,
            "models": 20,
            "providers": 20,
            "max_provider_dominance": 0.20,
            "matched_pairs": 250,
            "max_accounting_residual": 1e-9,
        },
        "claim_boundary": (
            "H83 is a future-only confirmation of a public mechanistic shape, not a "
            "randomized causal effect, private-router audit, intent test, or welfare estimate."
        ),
    }
    if cutoff is not None:
        released_shapes = shapes[shapes["event_ts"].le(cutoff)].copy()
        released_matches = matched[
            matched["event_ts_high"].le(cutoff) & matched["event_ts_low"].le(cutoff)
        ].copy()
        released_event_ids = set(released_shapes["event_id"])
        released_event_time = event_time[event_time["event_id"].isin(released_event_ids)].copy()
        shape_results, confirmed = _shape_results(released_shapes, released_matches)
        result["shape_results"] = shape_results
        result["evidence_status"] = (
            "future_holdout_capacity_cycle_confirmed"
            if confirmed
            else "future_holdout_capacity_cycle_rejected"
        )
        if out_dir is not None:
            save(released_event_time, out_dir, "h83_capacity_overshoot_event_time")
            save(released_shapes, out_dir, "h83_capacity_overshoot_effects")
            save(released_matches, out_dir, "h83_capacity_overshoot_matches")
            plot_released_paths(released_event_time, out_dir)
    if out_dir is not None:
        # Treatment/support fields are safe before release; future outcome paths
        # and coefficients are written only inside the released branch above.
        safe_columns = [
            "event_id",
            "event_class",
            "event_ts",
            "run_ts",
            "dt",
            "model_permaslug",
            "endpoint_uuid",
            "provider_name",
            "rate_limited_5m",
            "attempt_proxy_5m",
            "rate_limit_share_5m",
            "analysis_eligible",
            "exclusion_reason",
        ]
        safe_events = events.loc[:, [column for column in safe_columns if column in events]]
        save(safe_events, out_dir, "h83_capacity_overshoot_protocol_ledger")
        save(coverage, out_dir, "h83_capacity_overshoot_daily_coverage")
        save_json(result, out_dir, "h83_summary")
    return result


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    return analyze(load_rows(), out_dir)
