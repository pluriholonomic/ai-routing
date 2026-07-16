"""Preregistered PM5 finite-sample and known-clock menu simulations.

The public specification is frozen in
``manuscripts/pm5-negative-control-simulation-preregistration-2026-07-16.md``.
Production ``run`` intentionally exposes no tuning arguments. Smaller arguments
are accepted by pure helpers only so deterministic unit tests remain cheap.
"""

from __future__ import annotations

import argparse
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .pm5_tie_microstructure import (
    REFERENCE_GLOBAL_BAND_FACTOR,
    attach_global_price_menu_null,
    isolated_quote_change_events,
    quote_ticks,
    reference_price_landing_inference,
    reference_price_landing_panel,
)

SEED = 20260717
RHO_GRID = (0.0, 0.05, 0.10, 0.25, 0.50)
SIM1_REPLICATIONS = 1_000
SIM1_BOOTSTRAP_DRAWS = 2_000
SIM2_REPLICATIONS = 250
SIM2_BOOTSTRAP_DRAWS = 2_000
FROZEN_START_DATE = "2026-07-07"
FROZEN_END_DATE = "2026-07-15"


def _cluster_statistic(
    residual: np.ndarray,
    cluster_codes: np.ndarray,
    *,
    n_clusters: int,
    bootstrap_draws: int,
    rng: np.random.Generator,
) -> dict[str, float]:
    sums = np.bincount(cluster_codes, weights=residual, minlength=n_clusters)
    counts = np.bincount(cluster_codes, minlength=n_clusters).astype(float)
    estimate = float(residual.mean())
    draws = rng.integers(
        0,
        n_clusters,
        size=(int(bootstrap_draws), int(n_clusters)),
    )
    boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    total_sum = float(sums.sum())
    total_n = float(counts.sum())
    leave_one_out = np.array(
        [
            (total_sum - sums[index]) / (total_n - counts[index])
            for index in range(n_clusters)
            if total_n > counts[index]
        ],
        dtype=float,
    )
    lower, upper = np.quantile(boot, [0.025, 0.975])
    return {
        "estimate": estimate,
        "ci_low": float(lower),
        "ci_high": float(upper),
        "loo_min": float(leave_one_out.min()) if len(leave_one_out) else math.nan,
        "loo_max": float(leave_one_out.max()) if len(leave_one_out) else math.nan,
    }


def _summarize_simulation_rows(
    rows: pd.DataFrame,
    *,
    target_column: str | None = None,
) -> pd.DataFrame:
    summaries: list[dict[str, Any]] = []
    for rho, group in rows.groupby("rho", sort=True):
        target = (
            float(group[target_column].iloc[0]) if target_column is not None else None
        )
        estimate = group["estimate"].to_numpy(dtype=float)
        summary = {
            "rho": float(rho),
            "replications": int(len(group)),
            "mean_estimate": float(estimate.mean()),
            "estimate_p05": float(np.quantile(estimate, 0.05)),
            "estimate_median": float(np.quantile(estimate, 0.5)),
            "estimate_p95": float(np.quantile(estimate, 0.95)),
            "lower_bound_rejection_rate": float(group["reject_positive"].mean()),
            "joint_promotion_rate": float(group["promote_positive"].mean()),
        }
        if "n_events" in group:
            summary.update(
                {
                    "events_p05": float(group["n_events"].quantile(0.05)),
                    "events_median": float(group["n_events"].median()),
                    "events_p95": float(group["n_events"].quantile(0.95)),
                }
            )
        if "exact_landing_share" in group:
            summary.update(
                {
                    "mean_exact_landing_share": float(
                        group["exact_landing_share"].mean()
                    ),
                    "mean_menu_probability": float(
                        group["menu_probability"].mean()
                    ),
                }
            )
        if target is not None:
            summary.update(
                {
                    "target_excess": target,
                    "bias": float(estimate.mean() - target),
                    "rmse": float(np.sqrt(np.mean(np.square(estimate - target)))),
                    "interval_coverage": float(
                        ((group["ci_low"] <= target) & (group["ci_high"] >= target)).mean()
                    ),
                }
            )
        summaries.append(summary)
    return pd.DataFrame(summaries)


def event_level_size_power(
    panel: pd.DataFrame,
    *,
    rhos: tuple[float, ...] = RHO_GRID,
    replications: int = SIM1_REPLICATIONS,
    bootstrap_draws: int = SIM1_BOOTSTRAP_DRAWS,
    seed: int = SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SIM1: conditional size and power on the frozen event design."""
    usable = panel.dropna(subset=["global_menu_match_probability", "model_id"])
    if usable.empty:
        raise ValueError("SIM1 requires comparable frozen PM5 events")
    probabilities = usable["global_menu_match_probability"].to_numpy(dtype=float)
    cluster_codes, clusters = pd.factorize(usable["model_id"], sort=True)
    n_clusters = int(len(clusters))
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for rho in rhos:
        outcome_probability = probabilities + float(rho) * (1 - probabilities)
        target = float(np.mean(outcome_probability - probabilities))
        for replication in range(int(replications)):
            outcome = rng.binomial(1, outcome_probability).astype(float)
            statistic = _cluster_statistic(
                outcome - probabilities,
                cluster_codes,
                n_clusters=n_clusters,
                bootstrap_draws=bootstrap_draws,
                rng=rng,
            )
            rows.append(
                {
                    "rho": float(rho),
                    "replication": int(replication),
                    "n_events": int(len(usable)),
                    "n_model_clusters": n_clusters,
                    "target_excess": target,
                    **statistic,
                    "reject_positive": bool(statistic["ci_low"] > 0),
                    "promote_positive": bool(
                        statistic["ci_low"] > 0 and statistic["loo_min"] > 0
                    ),
                }
            )
    replication_frame = pd.DataFrame(rows)
    return replication_frame, _summarize_simulation_rows(
        replication_frame,
        target_column="target_excess",
    )


def simulate_known_clock_panel(
    *,
    rho: float,
    seed: int,
    n_models: int = 18,
    n_providers: int = 6,
    n_ticks: int = 576,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Generate one SIM2 quote panel with declared provider refresh clocks."""
    rng = np.random.default_rng(seed)
    menu = 1e-6 * np.power(1.25, np.arange(12, dtype=float))
    periods = rng.choice(np.array([6, 12, 24, 48]), size=n_providers, replace=True)
    phases = np.array(
        [rng.integers(0, int(period)) for period in periods],
        dtype=int,
    )
    model_effect = rng.integers(1, 8, size=n_models)
    provider_effect = rng.integers(-2, 3, size=n_providers)
    base_indices = np.clip(
        model_effect[:, None] + provider_effect[None, :],
        0,
        len(menu) - 1,
    )
    prices = menu[base_indices]
    history = np.empty((n_ticks, n_models, n_providers), dtype=float)
    latent_state = 0
    reactive_replacements = 0
    scheduled_refreshes = 0

    for tick in range(n_ticks):
        if tick and rng.random() > 0.94:
            latent_state = int(
                np.clip(latent_state + rng.choice(np.array([-1, 1])), -2, 2)
            )
        lagged = prices.copy()
        active = [
            provider
            for provider in range(n_providers)
            if tick > 0
            and tick >= phases[provider]
            and (tick - phases[provider]) % periods[provider] == 0
        ]
        for provider in active:
            for model in range(n_models):
                scheduled_refreshes += 1
                noise = int(rng.choice(np.array([-1, 0, 1]), p=[0.2, 0.6, 0.2]))
                index = int(
                    np.clip(
                        base_indices[model, provider] + latent_state + noise,
                        0,
                        len(menu) - 1,
                    )
                )
                target = float(menu[index])
                if rho > 0 and rng.random() < rho:
                    rival_indices = np.arange(n_providers) != provider
                    target = float(rng.choice(lagged[model, rival_indices]))
                    reactive_replacements += 1
                prices[model, provider] = target
        history[tick] = prices

    timestamps = pd.date_range(
        "2026-01-01T00:00:00Z",
        periods=n_ticks,
        freq="5min",
    )
    frame = pd.DataFrame(
        {
            "run_ts": np.repeat(timestamps.to_numpy(), n_models * n_providers),
            "model_id": np.tile(
                np.repeat([f"sim-model-{index:02d}" for index in range(n_models)], n_providers),
                n_ticks,
            ),
            "provider_name": np.tile(
                [f"sim-provider-{index:02d}" for index in range(n_providers)],
                n_ticks * n_models,
            ),
            "price": history.reshape(-1),
        }
    )
    metadata = {
        "rho": float(rho),
        "seed": int(seed),
        "n_models": int(n_models),
        "n_providers": int(n_providers),
        "n_ticks": int(n_ticks),
        "periods": [int(value) for value in periods],
        "phases": [int(value) for value in phases],
        "scheduled_refreshes": int(scheduled_refreshes),
        "reactive_replacements": int(reactive_replacements),
    }
    return frame, metadata


def _known_clock_replication(
    task: tuple[float, int, int, int, int, int, int, int],
) -> dict[str, Any]:
    (
        rho,
        replication,
        panel_seed,
        inference_seed,
        bootstrap_draws,
        n_models,
        n_providers,
        n_ticks,
    ) = task
    quotes, metadata = simulate_known_clock_panel(
        rho=float(rho),
        seed=int(panel_seed),
        n_models=int(n_models),
        n_providers=int(n_providers),
        n_ticks=int(n_ticks),
    )
    events = isolated_quote_change_events(quotes)
    event_panel = attach_global_price_menu_null(
        events,
        quotes,
        band_factor=REFERENCE_GLOBAL_BAND_FACTOR,
    ).dropna(subset=["global_menu_match_probability"])
    base = {
        "rho": float(rho),
        "replication": int(replication),
        "panel_seed": int(panel_seed),
        "inference_seed": int(inference_seed),
        **metadata,
    }
    if event_panel.empty:
        return {
            **base,
            "n_events": 0,
            "n_model_clusters": 0,
            "exact_landing_share": math.nan,
            "menu_probability": math.nan,
            "estimate": math.nan,
            "ci_low": math.nan,
            "ci_high": math.nan,
            "loo_min": math.nan,
            "loo_max": math.nan,
            "reject_positive": False,
            "promote_positive": False,
        }
    residual = (
        event_panel["exact_lagged_rival_match"].to_numpy(dtype=float)
        - event_panel["global_menu_match_probability"].to_numpy(dtype=float)
    )
    cluster_codes, clusters = pd.factorize(event_panel["model_id"], sort=True)
    statistic = _cluster_statistic(
        residual,
        cluster_codes,
        n_clusters=int(len(clusters)),
        bootstrap_draws=int(bootstrap_draws),
        rng=np.random.default_rng(int(inference_seed)),
    )
    return {
        **base,
        "n_events": int(len(event_panel)),
        "n_model_clusters": int(len(clusters)),
        "exact_landing_share": float(
            event_panel["exact_lagged_rival_match"].mean()
        ),
        "menu_probability": float(
            event_panel["global_menu_match_probability"].mean()
        ),
        **statistic,
        "reject_positive": bool(statistic["ci_low"] > 0),
        "promote_positive": bool(
            statistic["ci_low"] > 0 and statistic["loo_min"] > 0
        ),
    }


def known_clock_size_power(
    *,
    rhos: tuple[float, ...] = RHO_GRID,
    replications: int = SIM2_REPLICATIONS,
    bootstrap_draws: int = SIM2_BOOTSTRAP_DRAWS,
    seed: int = SEED,
    n_models: int = 18,
    n_providers: int = 6,
    n_ticks: int = 576,
    workers: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SIM2: run unchanged PM5 extraction/null on known-clock panels."""
    master = np.random.default_rng(seed)
    tasks = []
    for rho in rhos:
        for replication in range(int(replications)):
            panel_seed = int(master.integers(0, np.iinfo(np.uint32).max))
            inference_seed = int(master.integers(0, np.iinfo(np.uint32).max))
            tasks.append(
                (
                    float(rho),
                    int(replication),
                    panel_seed,
                    inference_seed,
                    int(bootstrap_draws),
                    int(n_models),
                    int(n_providers),
                    int(n_ticks),
                )
            )
    worker_count = workers or min(8, os.cpu_count() or 1)
    if worker_count == 1:
        rows = [_known_clock_replication(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            rows = list(executor.map(_known_clock_replication, tasks, chunksize=1))
    replication_frame = pd.DataFrame(rows)
    usable = replication_frame.dropna(subset=["estimate"]).copy()
    summary = _summarize_simulation_rows(usable)
    null_promotion = float(
        summary.loc[summary["rho"].eq(0), "joint_promotion_rate"].iloc[0]
    )
    summary["null_size_criterion_passes"] = bool(null_promotion <= 0.05)
    summary["power_interpretable"] = bool(null_promotion <= 0.05)
    return replication_frame, summary


def exact_cluster_sign_flip(
    panel: pd.DataFrame,
    *,
    outcome_column: str = "exact_lagged_rival_match",
    probability_column: str = "global_menu_match_probability",
    cluster_column: str = "model_id",
) -> dict[str, Any]:
    """RB1: enumerate the declared Rademacher cluster sign assignments exactly."""
    required = [outcome_column, probability_column, cluster_column]
    usable = panel.dropna(subset=required).copy()
    if usable.empty:
        return {
            "n_events": 0,
            "n_clusters": 0,
            "n_assignments": 0,
            "estimate": None,
            "observed_total": None,
            "one_sided_p": None,
            "two_sided_p": None,
        }
    usable["_residual"] = (
        usable[outcome_column].astype(float) - usable[probability_column].astype(float)
    )
    cluster_sums = (
        usable.groupby(cluster_column, sort=True)["_residual"]
        .sum()
        .to_numpy(dtype=np.longdouble)
    )
    n_clusters = int(len(cluster_sums))
    if n_clusters > 62:
        raise ValueError("exact sign-flip enumeration supports at most 62 clusters")
    n_assignments = 1 << n_clusters
    observed_total = np.sum(cluster_sums, dtype=np.longdouble)
    one_sided = 0
    two_sided = 0
    # Chunking keeps exact enumeration memory-bounded while preserving every 2^G arm.
    chunk_size = 1 << min(n_clusters, 16)
    bit_positions = np.arange(n_clusters, dtype=np.uint64)
    tolerance = np.longdouble(32) * np.finfo(np.longdouble).eps * max(
        np.longdouble(1), np.sum(np.abs(cluster_sums), dtype=np.longdouble)
    )
    for start in range(0, n_assignments, chunk_size):
        assignments = np.arange(
            start,
            min(start + chunk_size, n_assignments),
            dtype=np.uint64,
        )
        signs = (
            ((assignments[:, None] >> bit_positions[None, :]) & 1).astype(np.int8)
            * 2
            - 1
        )
        totals = signs.astype(np.longdouble) @ cluster_sums
        one_sided += int(np.count_nonzero(totals >= observed_total - tolerance))
        two_sided += int(
            np.count_nonzero(np.abs(totals) >= abs(observed_total) - tolerance)
        )
    return {
        "n_events": int(len(usable)),
        "n_clusters": n_clusters,
        "n_assignments": int(n_assignments),
        "estimate": float(usable["_residual"].mean()),
        "observed_total": float(observed_total),
        "one_sided_p": float(one_sided / n_assignments),
        "two_sided_p": float(two_sided / n_assignments),
        "assumption": "model-cluster sign symmetry; observational robustness only",
    }


def sim2_empirical_calibration(
    frozen_panel: pd.DataFrame,
    sim2_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """CAL1: compare frozen empirical statistics with the registered SIM2 null."""
    usable = frozen_panel.dropna(
        subset=["exact_lagged_rival_match", "global_menu_match_probability"]
    )
    if usable.empty:
        raise ValueError("CAL1 requires global-menu-comparable empirical events")
    null = sim2_rows[
        sim2_rows["rho"].eq(0)
        & sim2_rows["n_events"].gt(0)
        & sim2_rows["estimate"].notna()
    ].copy()
    if null.empty:
        raise ValueError("CAL1 requires nonempty rho-zero SIM2 replications")
    empirical = {
        "n_events": float(len(usable)),
        "exact_landing_share": float(usable["exact_lagged_rival_match"].mean()),
        "menu_probability": float(usable["global_menu_match_probability"].mean()),
        "estimate": float(
            (
                usable["exact_lagged_rival_match"]
                - usable["global_menu_match_probability"]
            ).mean()
        ),
    }
    labels = {
        "n_events": "Extracted event count",
        "exact_landing_share": "Exact lagged-rival landing share",
        "menu_probability": "Matched-menu probability",
        "estimate": "Exact-minus-menu residual",
    }
    rows = []
    for metric, value in empirical.items():
        p05, median, p95 = [
            float(number) for number in null[metric].quantile([0.05, 0.5, 0.95])
        ]
        rows.append(
            {
                "metric": metric,
                "label": labels[metric],
                "empirical": value,
                "sim2_null_p05": p05,
                "sim2_null_median": median,
                "sim2_null_p95": p95,
                "inside_sim2_null_p05_p95": bool(p05 <= value <= p95),
            }
        )
    table = pd.DataFrame(rows)
    probability_rows = table[table["metric"].isin(["exact_landing_share", "menu_probability"])]
    empirically_calibrated = bool(probability_rows["inside_sim2_null_p05_p95"].all())
    summary = {
        "n_sim2_null_replications": int(len(null)),
        "empirically_calibrated_on_registered_probabilities": empirically_calibrated,
        "required_description": (
            "empirically calibrated data-generating process"
            if empirically_calibrated
            else "stress-test counterexample, not an empirically calibrated data-generating process"
        ),
        "n_metrics_inside_p05_p95": int(table["inside_sim2_null_p05_p95"].sum()),
        "n_metrics_compared": int(len(table)),
    }
    return table, summary


def plot_menu_simulation(
    sim1_summary: pd.DataFrame,
    sim2_summary: pd.DataFrame,
    out_dir: Path,
    *,
    observed_excess: float = 0.070016770789,
    observed_menu_probability: float = 0.134064861864,
) -> list[str]:
    """Render the preregistered size/power results as a paper-ready figure."""
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    rho1 = sim1_summary["rho"].to_numpy(dtype=float)
    rho2 = sim2_summary["rho"].to_numpy(dtype=float)
    implied_rho = observed_excess / (1 - observed_menu_probability)
    figure, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))

    axes[0].plot(
        rho1,
        sim1_summary["joint_promotion_rate"],
        marker="o",
        color="#235789",
        label="promotion probability",
    )
    axes[0].axhline(0.05, color="#9c2c2c", linestyle="--", linewidth=1, label="5%")
    axes[0].axvline(
        implied_rho,
        color="#555555",
        linestyle=":",
        linewidth=1.2,
        label=f"observed-equivalent $\\rho={implied_rho:.2f}$",
    )
    axes[0].set_title("A. Frozen-design size and power")
    axes[0].set_xlabel("Reactive replacement probability $\\rho$")
    axes[0].set_ylabel("Joint promotion rate")
    axes[0].set_ylim(-0.02, 1.02)
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")

    axes[1].fill_between(
        rho2,
        sim2_summary["estimate_p05"].to_numpy(dtype=float),
        sim2_summary["estimate_p95"].to_numpy(dtype=float),
        color="#f2b134",
        alpha=0.28,
        label="5th--95th percentile",
    )
    axes[1].plot(
        rho2,
        sim2_summary["mean_estimate"],
        marker="o",
        color="#d17a00",
        label="mean matched-menu excess",
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_title("B. Known-clock test statistic")
    axes[1].set_xlabel("Reactive replacement probability $\\rho$")
    axes[1].set_ylabel("Exact-minus-menu probability")
    axes[1].legend(frameon=False, fontsize=8, loc="lower right")

    axes[2].plot(
        rho2,
        sim2_summary["mean_exact_landing_share"],
        marker="o",
        color="#2f7d32",
        label="exact lagged landing",
    )
    axes[2].plot(
        rho2,
        sim2_summary["mean_menu_probability"],
        marker="s",
        color="#7b2cbf",
        label="matched-menu benchmark",
    )
    axes[2].set_title("C. Why the structural test is conservative")
    axes[2].set_xlabel("Reactive replacement probability $\\rho$")
    axes[2].set_ylabel("Mean probability")
    axes[2].set_ylim(0.5, 1.0)
    axes[2].legend(frameon=False, fontsize=8, loc="lower right")

    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.18, linewidth=0.6)
    figure.tight_layout()
    paths = []
    for suffix in ("pdf", "png"):
        path = out_dir / f"pm5_menu_simulation.{suffix}"
        figure.savefig(path, dpi=220, bbox_inches="tight")
        paths.append(path.name)
    plt.close(figure)
    return paths


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    """Execute the immutable production specification and save all artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with data.pinned_analysis_source() as source_snapshot:
        quotes = quote_ticks()
        dates = pd.to_datetime(quotes["run_ts"], utc=True, errors="coerce").dt.strftime(
            "%Y-%m-%d"
        )
        frozen_quotes = quotes[
            dates.between(FROZEN_START_DATE, FROZEN_END_DATE, inclusive="both")
        ].copy()
        frozen_panel = reference_price_landing_panel(frozen_quotes)
        sim1_rows, sim1_summary = event_level_size_power(frozen_panel)
        sim2_rows, sim2_summary = known_clock_size_power()

    full_sign_flip = exact_cluster_sign_flip(frozen_panel)
    novel_sign_flip = exact_cluster_sign_flip(
        frozen_panel[frozen_panel["own_menu_novel"].eq(1)]
    )
    calibration_table, calibration_summary = sim2_empirical_calibration(
        frozen_panel,
        sim2_rows,
    )

    save(sim1_rows, out_dir, "pm5_sim1_event_level_replications")
    save(sim1_summary, out_dir, "pm5_sim1_summary")
    save(sim2_rows, out_dir, "pm5_sim2_known_clock_replications")
    save(sim2_summary, out_dir, "pm5_sim2_summary")
    save(calibration_table, out_dir, "pm5_sim2_empirical_calibration")
    figures = plot_menu_simulation(sim1_summary, sim2_summary, out_dir)
    null_sim1 = sim1_summary[sim1_summary["rho"].eq(0)].iloc[0].to_dict()
    null_sim2 = sim2_summary[sim2_summary["rho"].eq(0)].iloc[0].to_dict()
    frozen_inference = reference_price_landing_inference(frozen_panel)
    observed_excess = float(frozen_inference["exact_minus_global_menu"])
    observed_menu_probability = float(
        frozen_inference["global_menu_match_probability"]
    )
    implied_rho = observed_excess / (1 - observed_menu_probability)
    interpolated_power = float(
        np.interp(
            implied_rho,
            sim1_summary["rho"].to_numpy(dtype=float),
            sim1_summary["joint_promotion_rate"].to_numpy(dtype=float),
        )
    )
    summary = {
        "evidence_status": "preregistered_post_nine_date_simulation_complete",
        "source_snapshot": source_snapshot,
        "specification": {
            "seed": SEED,
            "rho_grid": list(RHO_GRID),
            "sim1_replications": SIM1_REPLICATIONS,
            "sim1_bootstrap_draws": SIM1_BOOTSTRAP_DRAWS,
            "sim2_replications": SIM2_REPLICATIONS,
            "sim2_bootstrap_draws": SIM2_BOOTSTRAP_DRAWS,
            "frozen_start_date": FROZEN_START_DATE,
            "frozen_end_date": FROZEN_END_DATE,
        },
        "frozen_design": {
            "n_events": int(len(frozen_panel)),
            "n_models": int(frozen_panel["model_id"].nunique()),
            "n_providers": int(frozen_panel["provider_name"].nunique()),
        },
        "sim1_null": null_sim1,
        "sim2_null": null_sim2,
        "sim2_power_interpretable": bool(
            sim2_summary["power_interpretable"].iloc[0]
        ),
        "observed_design_diagnostic": {
            "observed_excess": observed_excess,
            "observed_menu_probability": observed_menu_probability,
            "implied_reactive_probability": implied_rho,
            "linearly_interpolated_sim1_promotion_power": interpolated_power,
        },
        "sim2_max_grid_promotion_rate": float(
            sim2_summary["joint_promotion_rate"].max()
        ),
        "cluster_sign_flip_robustness": {
            "full_factor_1_25_panel": full_sign_flip,
            "own_menu_novel_panel": novel_sign_flip,
        },
        "sim2_empirical_calibration": calibration_summary,
        "sim2_power_interpretable_for_empirical_market": bool(
            calibration_summary["empirically_calibrated_on_registered_probabilities"]
        ),
        "figures": figures,
        "claim_boundary": (
            "SIM1 measures finite-sample inference on a declared conditional design; "
            "SIM2 measures size and power only inside one registered known-clock menu "
            "family, which CAL1 rejects as an empirical calibration and therefore remains "
            "a stress-test counterexample. Neither identifies private request order, "
            "intent, collusion, or welfare loss."
        ),
    }
    save_json(summary, out_dir, "pm5_menu_simulation_summary")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(run(args.out))


if __name__ == "__main__":
    main()
