"""Support-gated monitor for information-congestion v1."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..information_congestion import DEFAULT_CONFIG, load_protocol
from ..market_share_hmp import signal_effective_rank
from .information_congestion_readiness import read_table, task_id_from_metadata


def operational_surplus(frame: pd.DataFrame, weights: dict[str, Any]) -> pd.Series:
    success = frame["outcome"].astype(str).eq("succeeded").astype(float)
    cost = pd.to_numeric(frame.get("cost_usd", 0.0), errors="coerce").fillna(0.0)
    latency_seconds = (
        pd.to_numeric(frame.get("latency_ms", 0.0), errors="coerce").fillna(0.0) / 1000.0
    )
    fallback = frame.get("fallback_triggered", False)
    fallback = pd.Series(fallback, index=frame.index).fillna(False).astype(bool).astype(float)
    failure = 1.0 - success
    return (
        float(weights["success_value"]) * success
        - float(weights["cost_usd_multiplier"]) * cost
        - float(weights["latency_cost_per_second"]) * latency_seconds
        - float(weights["fallback_cost"]) * fallback
        - float(weights["failure_cost"]) * failure
    )


def choice_panel(
    assignments: pd.DataFrame,
    attempts: pd.DataFrame,
    *,
    weights: dict[str, Any],
) -> pd.DataFrame:
    if assignments.empty:
        return pd.DataFrame()
    planned = assignments.drop_duplicates("task_id", keep="last").copy()
    if attempts.empty:
        planned["attempt_observed"] = False
        return planned
    observed = attempts.copy()
    if "task_id" not in observed:
        observed["task_id"] = observed.get(
            "metadata_json", pd.Series(index=observed.index, dtype=object)
        ).map(task_id_from_metadata)
    observed = observed.dropna(subset=["task_id"]).drop_duplicates("task_id", keep="last")
    keep = [
        column
        for column in (
            "task_id",
            "outcome",
            "selected_provider",
            "latency_ms",
            "cost_usd",
            "fallback_triggered",
            "retry_reason",
        )
        if column in observed
    ]
    panel = planned.merge(observed[keep], on="task_id", how="left")
    panel["attempt_observed"] = panel["outcome"].notna()
    panel["operational_surplus"] = operational_surplus(panel, weights)
    selected_sets = panel["selected_provider_keys"].map(
        lambda value: {
            str(item).strip().casefold()
            for item in (
                value.tolist()
                if hasattr(value, "tolist")
                else value
                if isinstance(value, list)
                else []
            )
        }
    )
    selected = panel.get("selected_provider", pd.Series(index=panel.index, dtype=object))
    panel["exact_menu_covered"] = [
        str(provider or "").strip().casefold() in allowed
        for provider, allowed in zip(selected, selected_sets, strict=True)
    ]
    return panel


def outcome_surface(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty or "operational_surplus" not in panel:
        return pd.DataFrame()
    observed = panel[panel["attempt_observed"]].copy()
    if observed.empty:
        return pd.DataFrame()
    dimensions = ["target_n", "target_k", "overlap_arm", "router_rule"]
    return (
        observed.groupby(dimensions, dropna=False, sort=True)
        .agg(
            choices=("task_id", "nunique"),
            blocks=("block_id", "nunique"),
            success_rate=("outcome", lambda values: values.astype(str).eq("succeeded").mean()),
            mean_cost_usd=("cost_usd", "mean"),
            mean_latency_ms=("latency_ms", "mean"),
            fallback_rate=("fallback_triggered", "mean"),
            exact_menu_coverage=("exact_menu_covered", "mean"),
            mean_operational_surplus=("operational_surplus", "mean"),
        )
        .reset_index()
    )


def kstar_by_n(surface: pd.DataFrame, *, primary_rule: str = "default") -> pd.DataFrame:
    if surface.empty:
        return pd.DataFrame()
    selected = surface[surface["router_rule"].astype(str).eq(primary_rule)].copy()
    if selected.empty:
        return pd.DataFrame()
    collapsed = (
        selected.groupby(["target_n", "target_k"], sort=True)
        .apply(
            lambda group: pd.Series(
                {
                    "choices": int(group["choices"].sum()),
                    "blocks": int(group["blocks"].sum()),
                    "mean_operational_surplus": float(
                        np.average(
                            group["mean_operational_surplus"],
                            weights=np.maximum(group["choices"], 1),
                        )
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    rows = []
    for n, group in collapsed.groupby("target_n", sort=True):
        group = group.sort_values(["mean_operational_surplus", "target_k"], ascending=[False, True])
        best = group.iloc[0]
        rows.append(
            {
                "target_n": int(n),
                "k_star": int(best["target_k"]),
                "k_star_share": float(best["target_k"] / n),
                "mean_operational_surplus": float(best["mean_operational_surplus"]),
                "supported_k_values": int(group["target_k"].nunique()),
                "interior": bool(
                    int(best["target_k"]) > int(group["target_k"].min())
                    and int(best["target_k"]) < int(group["target_k"].max())
                ),
            }
        )
    return pd.DataFrame(rows)


def estimate_tau(kstars: pd.DataFrame) -> float | None:
    if kstars.empty:
        return None
    usable = kstars[
        kstars["interior"]
        & kstars["k_star_share"].gt(0)
        & kstars["target_n"].gt(1)
    ]
    if len(usable) < 3 or usable["target_n"].nunique() < 3:
        return None
    slope = np.polyfit(
        np.log(usable["target_n"].to_numpy(dtype=float)),
        np.log(usable["k_star_share"].to_numpy(dtype=float)),
        1,
    )[0]
    return float(-slope)


def bootstrap_tau(
    panel: pd.DataFrame,
    *,
    draws: int,
    seed: int = 20260723,
) -> tuple[float | None, float | None, int]:
    observed = panel[panel.get("attempt_observed", False)].copy() if not panel.empty else panel
    if observed.empty or observed["block_id"].nunique() < 3:
        return None, None, 0
    blocks = sorted(observed["block_id"].astype(str).unique())
    by_block = {block: observed[observed["block_id"].astype(str).eq(block)] for block in blocks}
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(draws):
        sampled = rng.choice(blocks, size=len(blocks), replace=True)
        pieces = []
        for index, block in enumerate(sampled):
            piece = by_block[str(block)].copy()
            piece["block_id"] = f"bootstrap-{index}-{block}"
            pieces.append(piece)
        draw = pd.concat(pieces, ignore_index=True)
        tau = estimate_tau(kstar_by_n(outcome_surface(draw)))
        if tau is not None and math.isfinite(tau):
            values.append(tau)
    if not values:
        return None, None, 0
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high), len(values)


def rank_curve(
    snapshots: pd.DataFrame,
    models: list[str],
    menu_sizes: list[int],
    *,
    seed: int = 20260723,
    subsets_per_size: int = 50,
) -> pd.DataFrame:
    required = {"run_ts", "model_id", "provider_name", "price_prompt", "price_completion"}
    if snapshots.empty or not required.issubset(snapshots):
        return pd.DataFrame()
    frame = snapshots[snapshots["model_id"].astype(str).isin(models)].copy()
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame["quote"] = (
        96 * pd.to_numeric(frame["price_prompt"], errors="coerce")
        + 8 * pd.to_numeric(frame["price_completion"], errors="coerce")
        + pd.to_numeric(frame.get("price_request", 0), errors="coerce").fillna(0)
    )
    frame["provider_key"] = frame["provider_name"].astype(str).str.strip().str.casefold()
    frame = frame.dropna(subset=["ts", "quote"])
    frame = frame[frame["quote"].gt(0)]
    rng = np.random.default_rng(seed)
    rows = []
    for model_id, group in frame.groupby("model_id", sort=True):
        pivot = (
            group.sort_values(["ts", "provider_key", "quote"], kind="stable")
            .drop_duplicates(["ts", "provider_key"], keep="first")
            .pivot(index="ts", columns="provider_key", values="quote")
            .resample("1h")
            .last()
            .ffill(limit=1)
        )
        innovations = np.log(pivot).diff()
        variable = [
            column
            for column in innovations.columns
            if innovations[column].notna().sum() >= 8
            and float(innovations[column].std(skipna=True) or 0.0) > 1e-12
        ]
        for n in sorted(set(int(value) for value in menu_sizes)):
            if n < 2 or len(variable) < n:
                continue
            combinations = math.comb(len(variable), n)
            draws = min(subsets_per_size, combinations)
            seen = set()
            ranks = []
            attempts = 0
            while len(seen) < draws and attempts < draws * 20:
                attempts += 1
                subset = tuple(sorted(rng.choice(variable, size=n, replace=False)))
                if subset in seen:
                    continue
                seen.add(subset)
                matrix = innovations[list(subset)].dropna()
                if len(matrix) < 8:
                    continue
                cov = np.cov(matrix.to_numpy(dtype=float), rowvar=False, ddof=1)
                rank = signal_effective_rank(cov)
                if math.isfinite(rank) and rank > 0:
                    ranks.append(rank)
            if ranks:
                rows.append(
                    {
                        "model_id": model_id,
                        "target_n": n,
                        "effective_rank": float(np.mean(ranks)),
                        "rank_sd": float(np.std(ranks, ddof=1)) if len(ranks) > 1 else 0.0,
                        "subsets": len(ranks),
                        "variable_providers": len(variable),
                    }
                )
    return pd.DataFrame(rows)


def estimate_beta(curve: pd.DataFrame) -> float | None:
    if curve.empty or curve["target_n"].nunique() < 2:
        return None
    x = np.log(curve["target_n"].to_numpy(dtype=float))
    y = np.log(curve["effective_rank"].to_numpy(dtype=float))
    if curve["model_id"].nunique() > 1:
        temp = curve.assign(x=x, y=y)
        x = (temp["x"] - temp.groupby("model_id")["x"].transform("mean")).to_numpy()
        y = (temp["y"] - temp.groupby("model_id")["y"].transform("mean")).to_numpy()
        cohort_counts = temp.groupby("model_id")["model_id"].transform("size").to_numpy()
        weights = 1.0 / cohort_counts
        denominator = float(np.sum(weights * x * x))
        return float(np.sum(weights * x * y) / denominator) if denominator > 0 else None
    return float(np.polyfit(x, y, 1)[0])


def identifying_rank_model_count(curve: pd.DataFrame) -> int:
    """Count cohorts with within-model subset-size variation for the slope."""

    if curve.empty or not {"model_id", "target_n"}.issubset(curve):
        return 0
    counts = curve.groupby("model_id")["target_n"].nunique()
    return int(counts.ge(2).sum())


def bootstrap_beta(
    curve: pd.DataFrame, *, draws: int, seed: int = 20260724
) -> tuple[float | None, float | None, int]:
    if curve.empty:
        return None, None, 0
    models = sorted(curve["model_id"].astype(str).unique())
    rng = np.random.default_rng(seed)
    values = []
    for draw in range(draws):
        pieces = []
        sampled_models = rng.choice(models, size=len(models), replace=True)
        for position, model in enumerate(sampled_models):
            piece = curve[curve["model_id"].astype(str).eq(str(model))].copy()
            if piece.empty:
                continue
            # Propagate finite random-subset uncertainty rather than treating
            # each model-size mean as an exact covariance object.
            rank_sd = pd.to_numeric(piece.get("rank_sd", 0.0), errors="coerce").fillna(0.0)
            subsets = pd.to_numeric(piece.get("subsets", 1), errors="coerce").fillna(1.0)
            standard_error = rank_sd / np.sqrt(np.maximum(subsets, 1.0))
            perturbed = rng.normal(
                piece["effective_rank"].to_numpy(dtype=float),
                standard_error.to_numpy(dtype=float),
            )
            piece["effective_rank"] = np.maximum(perturbed, 1e-9)
            piece["model_id"] = f"bootstrap-{draw}-{position}-{model}"
            pieces.append(piece)
        beta = estimate_beta(pd.concat(pieces, ignore_index=True)) if pieces else None
        if beta is not None and math.isfinite(beta):
            values.append(beta)
    if not values:
        return None, None, 0
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high), len(values)


def fit_congestion_gamma(
    surface: pd.DataFrame, ranks: pd.DataFrame, *, primary_rule: str = "default"
) -> dict[str, float] | None:
    """Fit the registered reduced-form curvature as a secondary mechanism check."""

    if surface.empty or ranks.empty:
        return None
    selected = surface[
        surface["router_rule"].astype(str).eq(primary_rule)
        & surface["mean_operational_surplus"].notna()
    ].copy()
    if selected.empty:
        return None
    selected = (
        selected.groupby(["target_n", "target_k"], sort=True)
        .apply(
            lambda group: pd.Series(
                {
                    "choices": float(group["choices"].sum()),
                    "y": float(
                        np.average(
                            group["mean_operational_surplus"],
                            weights=np.maximum(group["choices"], 1),
                        )
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    rank_map = ranks.groupby("target_n")["effective_rank"].mean().to_dict()
    selected["rank"] = selected["target_n"].map(rank_map)
    selected = selected[selected["rank"].notna()]
    if len(selected) < 6 or selected["target_k"].nunique() < 3:
        return None
    n = selected["target_n"].to_numpy(dtype=float)
    k = selected["target_k"].to_numpy(dtype=float)
    rank = selected["rank"].to_numpy(dtype=float)
    x = k / n
    y = selected["y"].to_numpy(dtype=float)
    weights = np.sqrt(np.maximum(selected["choices"].to_numpy(dtype=float), 1.0))
    best = None
    for gamma in np.linspace(0.0, 3.0, 61):
        ratio = np.divide(k, rank, out=np.zeros_like(k), where=rank > 0)
        z = x * x * np.power(ratio, gamma)
        design = np.column_stack([np.ones(len(x)), x, -z])
        coef, *_ = np.linalg.lstsq(design * weights[:, None], y * weights, rcond=None)
        intercept, benefit, congestion = (float(value) for value in coef)
        if benefit <= 0 or congestion <= 0:
            continue
        residual = y - design @ coef
        sse = float(np.sum(weights * weights * residual * residual))
        candidate = {
            "gamma": float(gamma),
            "intercept": intercept,
            "benefit": benefit,
            "congestion": congestion,
            "weighted_sse": sse,
        }
        if best is None or sse < best["weighted_sse"]:
            best = candidate
    return best


def bootstrap_gamma(
    panel: pd.DataFrame,
    ranks: pd.DataFrame,
    *,
    draws: int,
    seed: int = 20260725,
) -> tuple[float | None, float | None, int]:
    observed = panel[panel.get("attempt_observed", False)].copy() if not panel.empty else panel
    if observed.empty or observed["block_id"].nunique() < 6:
        return None, None, 0
    blocks = sorted(observed["block_id"].astype(str).unique())
    by_block = {block: observed[observed["block_id"].astype(str).eq(block)] for block in blocks}
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(draws):
        sampled = rng.choice(blocks, size=len(blocks), replace=True)
        pieces = []
        for index, block in enumerate(sampled):
            piece = by_block[str(block)].copy()
            piece["block_id"] = f"bootstrap-{index}-{block}"
            pieces.append(piece)
        fit = fit_congestion_gamma(outcome_surface(pd.concat(pieces, ignore_index=True)), ranks)
        if fit is not None:
            values.append(float(fit["gamma"]))
    if not values:
        return None, None, 0
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high), len(values)


def _plot(surface: pd.DataFrame, kstars: pd.DataFrame, ranks: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    if surface.empty:
        axes[0, 0].text(0.5, 0.5, "No paid outcomes yet", ha="center", va="center")
        axes[0, 1].text(0.5, 0.5, "No response surface yet", ha="center", va="center")
    else:
        support = surface.pivot_table(
            index="target_k", columns="target_n", values="choices", aggfunc="sum", fill_value=0
        )
        image = axes[0, 0].imshow(support.to_numpy(), aspect="auto", origin="lower")
        axes[0, 0].set_xticks(range(len(support.columns)), support.columns)
        axes[0, 0].set_yticks(range(len(support.index)), support.index)
        axes[0, 0].set_xlabel("eligible menu n")
        axes[0, 0].set_ylabel("responsive exposure k")
        axes[0, 0].set_title("Covered choices")
        fig.colorbar(image, ax=axes[0, 0], shrink=0.8)
        primary = surface[surface["router_rule"].astype(str).eq("default")]
        for n, group in primary.groupby("target_n", sort=True):
            collapsed = group.groupby("target_k")["mean_operational_surplus"].mean()
            axes[0, 1].plot(collapsed.index, collapsed.values, marker="o", label=f"n={n}")
        axes[0, 1].set_xlabel("responsive exposure k")
        axes[0, 1].set_ylabel("mean operational surplus")
        axes[0, 1].set_title("Randomized response surface")
        axes[0, 1].legend(frameon=False, fontsize=8)
    if kstars.empty:
        axes[1, 0].text(0.5, 0.5, "No interior k* yet", ha="center", va="center")
    else:
        axes[1, 0].plot(kstars["target_n"], kstars["k_star_share"], marker="o")
        axes[1, 0].set_xscale("log")
        axes[1, 0].set_yscale("log")
        axes[1, 0].set_xlabel("eligible menu n")
        axes[1, 0].set_ylabel("k*/n")
        axes[1, 0].set_title("Direct shrinking-share estimand")
    if ranks.empty:
        axes[1, 1].text(0.5, 0.5, "Insufficient varying providers", ha="center", va="center")
    else:
        for model, group in ranks.groupby("model_id", sort=True):
            axes[1, 1].plot(group["target_n"], group["effective_rank"], marker="o", label=model)
        axes[1, 1].set_xscale("log")
        axes[1, 1].set_yscale("log")
        axes[1, 1].set_xlabel("provider subset n")
        axes[1, 1].set_ylabel("effective rank")
        axes[1, 1].set_title("Mechanism check")
        axes[1, 1].legend(frameon=False, fontsize=7)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def run(
    data_root: Path,
    output_dir: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    support_only: bool = False,
) -> dict[str, Any]:
    protocol, protocol_sha256 = load_protocol(config_path)
    study_id = str(protocol["study"]["study_id"])
    assignments = read_table(data_root, "ic_assignments")
    attempts = pd.DataFrame() if support_only else read_table(data_root, "ic_attempts")
    quality_assignments = read_table(data_root, "ic_quality_assignments")
    quality = pd.DataFrame() if support_only else read_table(data_root, "ic_quality")
    if not assignments.empty and "study_id" in assignments:
        assignments = assignments[assignments["study_id"].astype(str).eq(study_id)]
    if not attempts.empty and "study_id" in attempts:
        attempts = attempts[attempts["study_id"].astype(str).eq(study_id)]
    quality_study_id = "openrouter-information-congestion-quality-v1"
    if not quality_assignments.empty and "study_id" in quality_assignments:
        quality_assignments = quality_assignments[
            quality_assignments["study_id"].astype(str).eq(quality_study_id)
        ]
    if not quality.empty and "study_id" in quality:
        quality = quality[quality["study_id"].astype(str).eq(quality_study_id)]
    panel = choice_panel(assignments, attempts, weights=dict(protocol["outcomes"]))
    surface = outcome_surface(panel)
    kstars = kstar_by_n(surface)
    tau = estimate_tau(kstars)
    draws = int(protocol["rank"]["bootstrap_draws"])
    tau_low, tau_high, tau_draws = bootstrap_tau(panel, draws=min(draws, 2000))
    snapshots = read_table(data_root, "endpoints_snapshots")
    ranks = rank_curve(
        snapshots,
        list(protocol["study"]["models"]),
        list(protocol["rank"]["subset_sizes"]),
    )
    beta = estimate_beta(ranks)
    beta_low, beta_high, beta_draws = bootstrap_beta(ranks, draws=min(draws, 2000))
    gamma_fit = fit_congestion_gamma(surface, ranks)
    gamma_low, gamma_high, gamma_draws = bootstrap_gamma(
        panel, ranks, draws=min(draws, 500)
    )
    gamma = gamma_fit["gamma"] if gamma_fit is not None else None
    theory_tau = (
        float(gamma * (1.0 - beta) / (1.0 + gamma))
        if gamma is not None and beta is not None
        else None
    )
    coverage = (
        float(panel.loc[panel["attempt_observed"], "exact_menu_covered"].mean())
        if not panel.empty and panel["attempt_observed"].any()
        else None
    )
    supported_bins = int(kstars["target_n"].nunique()) if not kstars.empty else 0
    interior_bins = int(kstars["interior"].sum()) if not kstars.empty else 0
    rank_models = identifying_rank_model_count(ranks)
    rank_points = int(len(ranks))
    # The primary pooled slope weights model cohorts equally regardless of how
    # many feasible subset sizes each model contributes.
    cohort_weight = float(1.0 / rank_models) if rank_models else None
    rank_support_gate = bool(
        rank_models >= int(protocol["rank"]["minimum_model_cohorts"])
        and rank_points >= int(protocol["rank"]["minimum_rank_points"])
        and cohort_weight is not None
        and cohort_weight <= float(protocol["rank"]["maximum_cohort_weight"])
    )
    strong_direct_gate = bool(
        tau_low is not None
        and tau_low > float(protocol["rank"]["primary_tau_margin"])
        and supported_bins >= int(protocol["rank"]["minimum_market_size_bins"])
        and interior_bins >= 3
        and beta_high is not None
        and beta_high < 1.0 - float(protocol["rank"]["primary_beta_margin"])
        and gamma_low is not None
        and gamma_low > 0
        and rank_support_gate
        and coverage is not None
        and coverage >= float(protocol["support"]["minimum_exact_menu_coverage"])
    )
    if quality.empty:
        quality_summary = pd.DataFrame()
    else:
        quality_frame = quality.copy()
        quality_frame["correct_numeric"] = (
            quality_frame["correct"].astype("boolean").astype(float)
        )
        quality_frame["success_numeric"] = (
            pd.to_numeric(quality_frame["http_status"], errors="coerce")
            .eq(200)
            .astype(float)
        )
        quality_frame["latency_numeric"] = pd.to_numeric(
            quality_frame["latency_ms"], errors="coerce"
        )
        quality_summary = (
            quality_frame.groupby(["model_id", "requested_provider"], dropna=False)
            .agg(
                observations=("task_id", "nunique"),
                correct_rate=("correct_numeric", "mean"),
                success_rate=("success_numeric", "mean"),
                mean_latency_ms=("latency_numeric", "mean"),
            )
            .reset_index()
        )
    result = {
        "format": "orcap-information-congestion-monitor-v1",
        "study_id": study_id,
        "protocol_sha256": protocol_sha256,
        "support": {
            "assignments": int(len(assignments)),
            "attempted_choices": int(panel["attempt_observed"].sum()) if not panel.empty else 0,
            "blocks": int(panel["block_id"].nunique()) if not panel.empty else 0,
            "supported_n_bins": supported_bins,
            "interior_n_bins": interior_bins,
            "exact_menu_coverage": coverage,
            "rank_models": rank_models,
            "rank_points": rank_points,
            "maximum_rank_cohort_weight": cohort_weight,
            "quality_assignments": int(len(quality_assignments)),
            "quality_observations": int(len(quality)),
            "quality_models": (
                int(quality["model_id"].nunique())
                if not quality.empty and "model_id" in quality
                else 0
            ),
            "quality_providers": (
                int(quality["requested_provider"].nunique())
                if not quality.empty and "requested_provider" in quality
                else 0
            ),
        },
        "estimates": {
            "tau": tau,
            "tau_ci95": [tau_low, tau_high],
            "tau_bootstrap_draws": tau_draws,
            "beta": beta,
            "beta_ci95": [beta_low, beta_high],
            "beta_bootstrap_draws": beta_draws,
            "gamma": gamma,
            "gamma_ci95": [gamma_low, gamma_high],
            "gamma_bootstrap_draws": gamma_draws,
            "theory_implied_tau": theory_tau,
            "theory_tau_gap": (
                float(tau - theory_tau)
                if tau is not None and theory_tau is not None
                else None
            ),
        },
        "gates": {
            "direct_shrinking_share": strong_direct_gate,
            "rank_support": rank_support_gate,
            "rank_mechanism_descriptive_only": not rank_support_gate,
            "support_only": support_only,
            "asymptotic_limit_identified": False,
            "full_social_welfare_identified": False,
        },
        "claim_boundary": (
            "Only a finite-range owned-menu exposure optimum can pass. The asymptotic "
            "limit and market-wide adaptive population remain unidentified."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    public_panel = panel.drop(
        columns=[column for column in ("selected_provider_keys",) if column in panel]
    )
    public_panel.to_parquet(output_dir / "ic_choice_panel.parquet", index=False)
    surface.to_csv(output_dir / "ic_outcome_surface.csv", index=False)
    kstars.to_csv(output_dir / "ic_kstar_scaling.csv", index=False)
    ranks.to_csv(output_dir / "ic_rank_panel.csv", index=False)
    quality_summary.to_csv(output_dir / "ic_quality_support.csv", index=False)
    (output_dir / "information-congestion-monitor.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _plot(surface, kstars, ranks, output_dir / "information-congestion-monitor.png")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--support-only", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.data_root,
                args.output_dir,
                config_path=args.config,
                support_only=args.support_only,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
