"""WF20 — finite-menu informational-congestion scaling diagnostics.

This module estimates how the effective rank of public provider price
innovations changes as increasingly many active undercutters are included in a
fixed model menu. It is a property test for one primitive of the proposed
informational-congestion theorem. Public quote-implied shares are never called
realized market share, and finite-menu rank slopes are never called asymptotic
proofs.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..market_share_hmp import routing_shares, signal_effective_rank
from . import data
from .common import DEFAULT_OUT, save, save_json
from .pm9_author_anchor import is_author_provider

GLM52 = "z-ai/glm-5.2"
ETA = 1.6482780609377246
INPUT_TOKENS = 1_000
OUTPUT_TOKENS = 256
TRAIN_FRACTION = 0.60
MIN_SNAPSHOTS = 96
MIN_PROVIDER_COVERAGE = 0.70
MIN_TRAIN_CHANGES = 2
MIN_ACTIVE_PROVIDERS = 3
BOOTSTRAP_DRAWS = 500
BOOTSTRAP_BLOCK_HOURS = 6
SEED = 20260722
INNOVATION_HORIZONS = (1, 6, 24)
PRIMARY_INNOVATION_HORIZON = 1


def load_quotes() -> pd.DataFrame:
    """Load one provider-best positive short-chat quote per public menu."""

    frame = data.q(
        f"""
        with quotes as (
          select run_ts, cast(dt as varchar) as dt, model_id, provider_name,
                 price_prompt * {INPUT_TOKENS}
                   + price_completion * {OUTPUT_TOKENS}
                   + coalesce(price_request, 0) as quote_usd
          from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
          where provider_name is not null
            and model_id is not null
            and model_id not like '%:free'
            and price_prompt >= 0
            and price_completion >= 0
            and coalesce(price_request, 0) >= 0
            and price_prompt * {INPUT_TOKENS}
                  + price_completion * {OUTPUT_TOKENS}
                  + coalesce(price_request, 0) > 0
            and (context_length is null or context_length >= {INPUT_TOKENS + OUTPUT_TOKENS})
        )
        select run_ts, dt, model_id, provider_name, min(quote_usd) as quote_usd
        from quotes
        group by all
        order by run_ts, model_id, provider_name
        """
    ).df()
    if frame.empty:
        return frame
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame["quote_usd"] = pd.to_numeric(frame["quote_usd"], errors="coerce")
    frame = frame.dropna(subset=["ts", "model_id", "provider_name", "quote_usd"])
    frame["is_author"] = [
        is_author_provider(str(model), str(provider))
        for model, provider in zip(frame["model_id"], frame["provider_name"], strict=True)
    ]
    return frame


def rank_and_factor_transport(
    train: np.ndarray,
    holdout: np.ndarray,
) -> dict[str, float]:
    """Estimate train effective rank and transport of its leading factor."""

    train = np.asarray(train, dtype=float)
    holdout = np.asarray(holdout, dtype=float)
    if train.ndim != 2 or holdout.ndim != 2 or train.shape[1] != holdout.shape[1]:
        raise ValueError("train and holdout must be matrices with matching columns")
    train = train[np.all(np.isfinite(train), axis=1)]
    holdout = holdout[np.all(np.isfinite(holdout), axis=1)]
    if min(len(train), len(holdout)) < 8 or train.shape[1] < 2:
        raise ValueError("insufficient complete train or holdout support")

    train_mean = train.mean(axis=0)
    train_scale = train.std(axis=0, ddof=1)
    if np.any(train_scale <= 1e-12):
        raise ValueError("train columns must vary")
    train_z = (train - train_mean) / train_scale
    holdout_z = (holdout - train_mean) / train_scale
    train_cov = np.cov(train_z, rowvar=False, ddof=1)
    holdout_cov = np.cov(holdout_z, rowvar=False, ddof=1)
    eigenvalues, eigenvectors = np.linalg.eigh(train_cov)
    leading = eigenvectors[:, int(np.argmax(eigenvalues))]
    train_total = float(np.trace(train_cov))
    holdout_total = float(np.trace(holdout_cov))
    train_share = float(np.max(eigenvalues) / train_total)
    holdout_share = float(leading @ holdout_cov @ leading / holdout_total)
    return {
        "effective_rank": signal_effective_rank(train_cov),
        "leading_factor_share_train": train_share,
        "leading_factor_share_holdout": holdout_share,
        "factor_optimism_gap": train_share - holdout_share,
        "train_rows": float(len(train)),
        "holdout_rows": float(len(holdout)),
    }


def _slope(curve: pd.DataFrame) -> float | None:
    if curve.empty or not {"active_count", "effective_rank"}.issubset(curve.columns):
        return None
    usable = curve[
        (curve["active_count"] >= 2)
        & (curve["effective_rank"] > 0)
        & np.isfinite(curve["effective_rank"])
    ]
    if len(usable) < 2 or usable["active_count"].nunique() < 2:
        return None
    return float(
        np.polyfit(
            np.log(usable["active_count"].to_numpy(dtype=float)),
            np.log(usable["effective_rank"].to_numpy(dtype=float)),
            1,
        )[0]
    )


def _hourly_innovations(
    group: pd.DataFrame,
    providers: list[str],
    cutoff: pd.Timestamp,
    *,
    horizon_hours: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    relative = group.pivot(index="ts", columns="provider_name", values="relative_log_quote")
    relative = relative.reindex(columns=providers).sort_index()
    hourly = relative.resample("1h").last().ffill(limit=1)
    innovations = hourly.diff(periods=horizon_hours).replace([np.inf, -np.inf], np.nan)
    return innovations[innovations.index < cutoff], innovations[innovations.index >= cutoff]


def _nested_curve(
    model_id: str,
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    provider_order: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for active_count in range(2, len(provider_order) + 1):
        providers = provider_order[:active_count]
        train_values = train[providers].dropna().to_numpy(dtype=float)
        holdout_values = holdout[providers].dropna().to_numpy(dtype=float)
        try:
            result = rank_and_factor_transport(train_values, holdout_values)
        except ValueError:
            continue
        rows.append(
            {
                "model_id": model_id,
                "active_count": active_count,
                "providers": providers,
                **result,
                "crowding_index": active_count / result["effective_rank"],
            }
        )
    return pd.DataFrame(rows)


def _block_resample(matrix: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    if matrix.empty:
        return matrix
    block = max(1, BOOTSTRAP_BLOCK_HOURS)
    pieces = [matrix.iloc[start : start + block] for start in range(0, len(matrix), block)]
    chosen = rng.integers(0, len(pieces), size=len(pieces))
    return pd.concat([pieces[index] for index in chosen], ignore_index=True).iloc[: len(matrix)]


def bootstrap_rank_slope(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    provider_order: list[str],
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = SEED,
) -> tuple[float | None, float | None, int]:
    """Block-bootstrap the nested effective-rank slope."""

    rng = np.random.default_rng(seed)
    slopes: list[float] = []
    for _ in range(draws):
        curve = _nested_curve(
            "bootstrap",
            _block_resample(train, rng),
            _block_resample(holdout, rng),
            provider_order,
        )
        slope = _slope(curve)
        if slope is not None and math.isfinite(slope):
            slopes.append(slope)
    if not slopes:
        return None, None, 0
    return (
        float(np.quantile(slopes, 0.025)),
        float(np.quantile(slopes, 0.975)),
        len(slopes),
    )


def _share_curve(
    group: pd.DataFrame,
    provider_order: list[str],
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    holdout = group[group["ts"] >= cutoff]
    for active_count in range(1, len(provider_order) + 1):
        members = set(provider_order[:active_count])
        for (run_ts, model_id), menu in holdout.groupby(["run_ts", "model_id"], sort=False):
            if not members.issubset(set(menu["provider_name"])):
                continue
            benchmark = float(menu["benchmark_quote"].iloc[0])
            if not math.isfinite(benchmark) or benchmark <= 0:
                continue
            prices = menu["quote_usd"].to_numpy(dtype=float)
            names = menu["provider_name"].astype(str).tolist()
            member_mask = np.asarray([name in members for name in names], dtype=bool)
            counterfactual = prices.copy()
            counterfactual[member_mask & (prices < benchmark)] = benchmark
            actual_share = routing_shares(prices, eta=ETA)
            counterfactual_share = routing_shares(counterfactual, eta=ETA)
            rows.append(
                {
                    "run_ts": run_ts,
                    "model_id": model_id,
                    "active_count": active_count,
                    "menu_count": len(prices),
                    "active_density": active_count / len(prices),
                    "actual_active_shadow_share": float(actual_share[member_mask].sum()),
                    "counterfactual_active_shadow_share": float(
                        counterfactual_share[member_mask].sum()
                    ),
                    "passive_to_active_shadow_transfer": float(
                        actual_share[member_mask].sum()
                        - counterfactual_share[member_mask].sum()
                    ),
                }
            )
    return pd.DataFrame(rows)


def _count_scaling(census: pd.DataFrame) -> dict[str, Any]:
    usable = census[
        (census["median_menu_count"] >= 2) & (census["active_provider_count"] >= 0)
    ].copy()
    if len(usable) < 8 or usable["median_menu_count"].nunique() < 3:
        return {"status": "insufficient_models", "models": int(len(usable))}
    x = np.log(usable["median_menu_count"].to_numpy(dtype=float))
    y = np.log1p(usable["active_provider_count"].to_numpy(dtype=float))
    slope = float(np.polyfit(x, y, 1)[0])
    rng = np.random.default_rng(SEED + 991)
    slopes = []
    for _ in range(BOOTSTRAP_DRAWS):
        indices = rng.integers(0, len(usable), size=len(usable))
        sample = usable.iloc[indices]
        if sample["median_menu_count"].nunique() < 3:
            continue
        slopes.append(
            float(
                np.polyfit(
                    np.log(sample["median_menu_count"].to_numpy(dtype=float)),
                    np.log1p(sample["active_provider_count"].to_numpy(dtype=float)),
                    1,
                )[0]
            )
        )
    return {
        "status": "finite_cross_model_scaling_diagnostic",
        "models": int(len(usable)),
        "log1p_count_scaling_gamma": slope,
        "model_bootstrap_95ci": (
            [float(np.quantile(slopes, 0.025)), float(np.quantile(slopes, 0.975))]
            if slopes
            else None
        ),
        "median_active_density": float(usable["active_provider_density"].median()),
        "share_zero_active": float(usable["active_provider_count"].eq(0).mean()),
        "boundary": (
            "Cross-model log-count scaling is a finite heterogeneous-market diagnostic. "
            "It is not a within-market asymptotic estimate."
        ),
    }


def build_panels(
    quotes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rank_curves: list[pd.DataFrame] = []
    share_curves: list[pd.DataFrame] = []
    model_rows: list[dict[str, Any]] = []
    census_rows: list[dict[str, Any]] = []
    for model_id, raw in quotes.groupby("model_id", sort=True):
        snapshots = sorted(raw["ts"].dropna().unique())
        if len(snapshots) < MIN_SNAPSHOTS:
            continue
        cutoff = pd.Timestamp(snapshots[int(len(snapshots) * TRAIN_FRACTION)])
        menu_counts = raw.groupby("run_ts")["provider_name"].nunique()
        total_menu = int(round(float(menu_counts.median())))
        coverage = raw.groupby("provider_name")["run_ts"].nunique() / len(snapshots)
        stable = sorted(coverage[coverage >= MIN_PROVIDER_COVERAGE].index.astype(str))
        if len(stable) < MIN_ACTIVE_PROVIDERS:
            continue

        group = raw[raw["provider_name"].isin(stable)].copy()
        author = group["quote_usd"].where(group["is_author"])
        author_benchmark = author.groupby(group["run_ts"], sort=False).transform("median")
        menu_benchmark = group.groupby("run_ts", sort=False)["quote_usd"].transform("median")
        group["benchmark_quote"] = author_benchmark.fillna(menu_benchmark)
        group["benchmark_source"] = np.where(
            author_benchmark.notna(), "model_author", "menu_median"
        )
        group["relative_log_quote"] = np.log(group["quote_usd"] / group["benchmark_quote"])

        train_quotes = group[group["ts"] < cutoff].sort_values("ts")
        activity_rows = []
        for provider, provider_rows in train_quotes[~train_quotes["is_author"]].groupby(
            "provider_name", sort=True
        ):
            values = provider_rows["relative_log_quote"].to_numpy(dtype=float)
            changes = int(np.sum(np.abs(np.diff(values)) > 1e-10))
            activity_rows.append(
                {
                    "provider_name": str(provider),
                    "changes": changes,
                    "median_relative_log_quote": float(np.median(values)),
                    "undercut_share": float(np.mean(values < -1e-10)),
                }
            )
        activity = pd.DataFrame(activity_rows)
        if activity.empty:
            continue
        active = activity[
            (activity["changes"] >= MIN_TRAIN_CHANGES)
            & (activity["median_relative_log_quote"] < 0)
        ].sort_values(
            ["changes", "undercut_share", "provider_name"],
            ascending=[False, False, True],
            kind="stable",
        )
        provider_order = active["provider_name"].astype(str).tolist()
        census_rows.append(
            {
                "model_id": str(model_id),
                "is_glm52": str(model_id) == GLM52,
                "snapshots": len(snapshots),
                "train_end": cutoff.isoformat(),
                "median_menu_count": total_menu,
                "stable_provider_count": len(stable),
                "active_provider_count": len(provider_order),
                "active_provider_density": len(provider_order) / max(total_menu, 1),
                "active_providers": provider_order,
                "benchmark_source_author_share": float(
                    group["benchmark_source"].eq("model_author").mean()
                ),
            }
        )
        if len(provider_order) < MIN_ACTIVE_PROVIDERS:
            continue

        supported_horizons = 0
        for horizon in INNOVATION_HORIZONS:
            train_innovations, holdout_innovations = _hourly_innovations(
                group, provider_order, cutoff, horizon_hours=horizon
            )
            curve = _nested_curve(
                str(model_id), train_innovations, holdout_innovations, provider_order
            )
            if len(curve) < 2:
                continue
            curve["innovation_horizon_hours"] = horizon
            slope = _slope(curve)
            ci_low, ci_high, successful_draws = bootstrap_rank_slope(
                train_innovations,
                holdout_innovations,
                provider_order,
                seed=SEED + horizon * 10_003 + sum(str(model_id).encode("utf-8")),
            )
            rank_curves.append(curve)
            model_rows.append(
                {
                    "model_id": str(model_id),
                    "is_glm52": str(model_id) == GLM52,
                    "innovation_horizon_hours": horizon,
                    "snapshots": len(snapshots),
                    "train_end": cutoff.isoformat(),
                    "median_menu_count": total_menu,
                    "stable_provider_count": len(stable),
                    "active_provider_count": len(provider_order),
                    "active_provider_density": len(provider_order) / max(total_menu, 1),
                    "active_providers": provider_order,
                    "rank_scaling_beta": slope,
                    "rank_scaling_beta_block_bootstrap_low": ci_low,
                    "rank_scaling_beta_block_bootstrap_high": ci_high,
                    "bootstrap_successful_draws": successful_draws,
                    "implied_kstar_exponent_alpha1": (
                        (1.0 + slope) / 2.0 if slope is not None else None
                    ),
                    "benchmark_source_author_share": float(
                        group["benchmark_source"].eq("model_author").mean()
                    ),
                }
            )
            supported_horizons += 1
        if not supported_horizons:
            continue
        shares = _share_curve(group, provider_order, cutoff)
        if not shares.empty:
            share_curves.append(shares)
    return (
        pd.concat(rank_curves, ignore_index=True) if rank_curves else pd.DataFrame(),
        pd.concat(share_curves, ignore_index=True) if share_curves else pd.DataFrame(),
        pd.DataFrame(model_rows),
        pd.DataFrame(census_rows),
    )


def summarize(
    rank_curve: pd.DataFrame,
    share_rows: pd.DataFrame,
    models: pd.DataFrame,
    census: pd.DataFrame,
) -> dict[str, Any]:
    boundary = (
        "Finite-menu effective-rank slopes and inverse-price shadow shares are public-quote "
        "diagnostics. They do not prove asymptotic scaling, realized market share, provider "
        "learning, costs, intent, collusion, revenue, profit, or welfare. The mapping from "
        "rank beta to k-star exponent is conditional on the proposed linear overfit law."
    )
    if census.empty:
        return {
            "evidence_status": "insufficient_supported_model_menus",
            "claim_boundary": boundary,
        }
    primary = (
        models[models["innovation_horizon_hours"].eq(PRIMARY_INNOVATION_HORIZON)]
        if not models.empty
        else models
    )
    glm = primary[primary["is_glm52"]] if not primary.empty else pd.DataFrame()
    comparators = primary[~primary["is_glm52"]] if not primary.empty else pd.DataFrame()
    if comparators.empty:
        comparator_slopes = np.asarray([], dtype=float)
    else:
        comparator_slopes = comparators["rank_scaling_beta"].dropna().to_numpy(dtype=float)
    glm_record = glm.iloc[0].to_dict() if len(glm) else None
    comparator = {
        "supported_models": int(len(comparators)),
        "median_rank_scaling_beta": (
            float(np.median(comparator_slopes)) if len(comparator_slopes) else None
        ),
        "model_dispersion_10_90": (
            [
                float(np.quantile(comparator_slopes, 0.10)),
                float(np.quantile(comparator_slopes, 0.90)),
            ]
            if len(comparator_slopes)
            else None
        ),
        "share_with_beta_at_least_0_8": (
            float(np.mean(comparator_slopes >= 0.8)) if len(comparator_slopes) else None
        ),
    }
    glm_census = census[census["is_glm52"]]
    non_glm_census = census[~census["is_glm52"]]
    return {
        "evidence_status": "finite_menu_property_test",
        "models_supported": int(models["model_id"].nunique()) if not models.empty else 0,
        "model_horizon_cells": int(len(models)),
        "models_in_active_count_census": int(len(census)),
        "glm52": glm_record,
        "glm52_horizon_sensitivity": (
            models[models["is_glm52"]][
                [
                    "innovation_horizon_hours",
                    "rank_scaling_beta",
                    "rank_scaling_beta_block_bootstrap_low",
                    "rank_scaling_beta_block_bootstrap_high",
                    "implied_kstar_exponent_alpha1",
                ]
            ].to_dict("records")
            if not models.empty
            else []
        ),
        "glm52_active_count_census": (
            glm_census.iloc[0].to_dict() if len(glm_census) else None
        ),
        "non_glm_comparator": comparator,
        "non_glm_active_count_scaling": _count_scaling(non_glm_census),
        "rank_curve_rows": int(len(rank_curve)),
        "shadow_share_rows": int(len(share_rows)),
        "free_models_excluded": True,
        "conditional_theory_mapping": (
            "If r(k) scales as k^beta and overfit loss is linear in k/r, then "
            "k-star scales as n^((1+beta)/2). Beta below one is sublinear-compatible; "
            "beta equal to one is linear-compatible."
        ),
        "claim_boundary": boundary,
    }


def _render(
    rank_curve: pd.DataFrame,
    share_rows: pd.DataFrame,
    models: pd.DataFrame,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.2), constrained_layout=True)
    primary = (
        models[models["innovation_horizon_hours"].eq(PRIMARY_INNOVATION_HORIZON)]
        if not models.empty
        else models
    )
    if rank_curve.empty:
        glm_rank = pd.DataFrame()
        other_rank = pd.DataFrame()
    else:
        primary_rank = rank_curve[
            rank_curve["innovation_horizon_hours"].eq(PRIMARY_INNOVATION_HORIZON)
        ]
        glm_rank = primary_rank[primary_rank["model_id"].eq(GLM52)]
        other_rank = primary_rank[~primary_rank["model_id"].eq(GLM52)]
    if not other_rank.empty:
        pooled = other_rank.groupby("active_count", as_index=False).agg(
            effective_rank=("effective_rank", "median")
        )
        axes[0, 0].plot(
            pooled["active_count"], pooled["effective_rank"], marker="o",
            color="#64748B", label="Non-GLM median"
        )
    if not glm_rank.empty:
        axes[0, 0].plot(
            glm_rank["active_count"], glm_rank["effective_rank"], marker="o",
            linewidth=2.2, color="#B91C1C", label="GLM-5.2"
        )
    maximum = int(rank_curve["active_count"].max()) if len(rank_curve) else 2
    axes[0, 0].plot([1, maximum], [1, maximum], "--", color="black", linewidth=0.8)
    axes[0, 0].set(
        title="A. Signal rank versus active count", xlabel="Active providers k",
        ylabel="Effective rank r(k)"
    )
    axes[0, 0].legend(frameon=False)

    for frame, color, label in (
        (glm_rank, "#B91C1C", "GLM-5.2"),
        (other_rank, "#64748B", "Non-GLM pooled"),
    ):
        if frame.empty:
            continue
        grouped = frame.groupby("active_count", as_index=False).agg(
            train=("leading_factor_share_train", "median"),
            holdout=("leading_factor_share_holdout", "median"),
        )
        axes[0, 1].plot(
            grouped["active_count"], grouped["train"], marker="o", color=color,
            label=f"{label} train"
        )
        axes[0, 1].plot(
            grouped["active_count"], grouped["holdout"], marker="x", linestyle="--",
            color=color, label=f"{label} holdout"
        )
    axes[0, 1].set(
        title="B. Does the common factor transport?", xlabel="Active providers k",
        ylabel="Variance share of train leading factor"
    )
    axes[0, 1].legend(frameon=False, fontsize=8)

    if not share_rows.empty:
        share_summary = share_rows.groupby(["model_id", "active_count"], as_index=False).agg(
            active_density=("active_density", "median"),
            transfer=("passive_to_active_shadow_transfer", "median"),
        )
        for model_id, group in share_summary.groupby("model_id", sort=True):
            axes[1, 0].plot(
                group["active_density"], 100 * group["transfer"], marker="o",
                alpha=1.0 if model_id == GLM52 else 0.25,
                linewidth=2.2 if model_id == GLM52 else 0.8,
                color="#B91C1C" if model_id == GLM52 else "#64748B",
                label="GLM-5.2" if model_id == GLM52 else None,
            )
    axes[1, 0].axhline(0, color="black", linewidth=0.7)
    axes[1, 0].set(
        title="C. Public-rule transfer, not realized share", xlabel="Active density k/n",
        ylabel="Passive-to-active shadow transfer (pp)"
    )
    if not share_rows.empty and GLM52 in set(share_rows["model_id"]):
        axes[1, 0].legend(frameon=False)

    ordered = (
        primary.sort_values(["is_glm52", "rank_scaling_beta"], ascending=[False, True])
        if not primary.empty
        else primary
    )
    colors = (
        ["#B91C1C" if flag else "#64748B" for flag in ordered["is_glm52"]]
        if not ordered.empty
        else []
    )
    if not ordered.empty:
        axes[1, 1].barh(
            ordered["model_id"], ordered["rank_scaling_beta"], color=colors
        )
    axes[1, 1].axvline(1.0, color="black", linestyle="--", linewidth=0.8)
    axes[1, 1].set(
        title="D. Finite-menu rank-scaling diagnostic",
        xlabel="beta in r(k) proportional to k^beta", ylabel=""
    )
    axes[1, 1].tick_params(axis="y", labelsize=7)
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"wf20_informational_congestion.{extension}", dpi=200)
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    with data.pinned_analysis_source() as source:
        quotes = load_quotes()
    rank_curve, share_rows, models, census = build_panels(quotes)
    summary = summarize(rank_curve, share_rows, models, census)
    summary["analysis_source"] = source
    save(rank_curve, out_dir, "wf20_rank_curve")
    save(share_rows, out_dir, "wf20_shadow_share_curve")
    save(models, out_dir, "wf20_model_scaling")
    save(census, out_dir, "wf20_model_census")
    save_json(summary, out_dir, "wf20_summary")
    _render(rank_curve, share_rows, models, out_dir)
    return summary


if __name__ == "__main__":
    run()
