"""Run and package the prospective market-share HMP controlled experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import stats

from ..market_share_hmp import (
    INPUT_TOKENS,
    MODEL_ID,
    OUTPUT_TOKENS,
    parse_time,
    provider_key,
)
from .market_share_hmp import controlled_router_factorial, run_factorial

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "glm52_market_share_hmp_v1.toml"
DEFAULT_OUT = ROOT / "data" / "analysis" / "glm52-market-share-hmp-v1" / "simulation"


def public_price_calibration(data_root: Path | None, protocol: dict) -> dict:
    fallback = {
        "status": "fallback_stylized",
        "low_price": 0.65,
        "high_price": 1.0,
        "anchor_price": 1.0,
        "marginal_cost": 0.20,
        "snapshots": 0,
        "rows": 0,
        "boundary": "Fallback prices are stylized and serving cost is not observed.",
    }
    if data_root is None:
        return fallback
    frames = []
    for path in sorted((data_root / "curated" / "endpoints_snapshots").glob("dt=*/*.parquet")):
        try:
            frames.append(pq.ParquetFile(path).read().to_pandas())
        except (OSError, pa.ArrowInvalid):
            continue
    if not frames:
        return fallback
    frame = pd.concat(frames, ignore_index=True)
    required = {"run_ts", "model_id", "provider_name", "price_prompt", "price_completion"}
    if not required.issubset(frame.columns):
        return fallback
    frame = frame[frame["model_id"].astype(str).eq(MODEL_ID)].copy()
    calibration_end = parse_time(protocol["study"]["calibration_end_utc"])
    frame = frame[frame["run_ts"].map(parse_time).le(calibration_end)].copy()
    for column in ("price_prompt", "price_completion", "price_request"):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["quote"] = (
        frame["price_prompt"] * INPUT_TOKENS
        + frame["price_completion"] * OUTPUT_TOKENS
        + frame["price_request"]
    )
    frame = frame[frame["quote"].gt(0)].copy()
    frame["provider_key"] = frame["provider_name"].map(provider_key)
    frame = frame.sort_values("quote").drop_duplicates(["run_ts", "provider_key"])
    active = {provider_key(item) for item in protocol["providers"]["active"]}
    anchors = {provider_key(item) for item in protocol["providers"]["anchors"]}
    ratios = []
    for _, group in frame.groupby("run_ts"):
        active_quotes = group.loc[group["provider_key"].isin(active), "quote"]
        anchor_quotes = group.loc[group["provider_key"].isin(anchors), "quote"]
        if len(active_quotes) and len(anchor_quotes):
            ratios.append(float(active_quotes.median() / anchor_quotes.median()))
    if not ratios:
        return fallback
    ratio = float(np.median(ratios))
    low_price = min(max(ratio, 0.21), 0.98)
    return {
        "status": "public_glm52_relative_price_calibration",
        "low_price": low_price,
        "high_price": 1.0,
        "anchor_price": 1.0,
        "marginal_cost": 0.25 * low_price,
        "raw_median_active_to_anchor_quote": ratio,
        "snapshots": len(ratios),
        "rows": int(len(frame)),
        "boundary": (
            "Prices are calibrated to public GLM-5.2 quotes; serving cost, private "
            "eligibility, provider objectives, and algorithms remain scenarios."
        ),
    }


def _paired(frame: pd.DataFrame) -> pd.DataFrame:
    index = [
        "n_active",
        "signal_to_noise",
        "reward_memory",
        "router_eta",
        "algorithm",
        "seed",
        "horizon",
    ]
    values = [
        "elasticity_learning_time",
        "elasticity_learned",
        "mean_action_correlation",
        "all_low_share",
        "all_high_share",
        "mean_active_group_share",
        "mean_anchor_group_share",
        "mean_buyer_price",
    ]
    paired = frame.pivot_table(
        index=index, columns="arm", values=values, aggfunc="first"
    ).reset_index()
    paired.columns = [
        "__".join(str(part) for part in column if str(part))
        if isinstance(column, tuple)
        else str(column)
        for column in paired.columns
    ]
    for outcome in (
        "mean_action_correlation",
        "all_low_share",
        "all_high_share",
        "mean_active_group_share",
        "mean_anchor_group_share",
        "mean_buyer_price",
    ):
        paired[f"{outcome}__coupled_minus_shuffled"] = (
            paired[f"{outcome}__coupled"] - paired[f"{outcome}__marginal_preserving_shuffle"]
        )
    coupled_time = paired["elasticity_learning_time__coupled"].fillna(paired["horizon"] + 1)
    shuffled_time = paired["elasticity_learning_time__marginal_preserving_shuffle"].fillna(
        paired["horizon"] + 1
    )
    paired["learning_time_censored__coupled"] = coupled_time
    paired["learning_time_censored__marginal_preserving_shuffle"] = shuffled_time
    paired["learning_time__coupled_minus_shuffled"] = coupled_time - shuffled_time
    return paired


def seed_clustered_interval(frame: pd.DataFrame, outcome: str) -> dict:
    """Equal-cell mean and t interval using simulation seed as the sampling unit."""
    seed_means = frame.groupby("seed", sort=True)[outcome].mean().astype(float)
    estimate = float(seed_means.mean()) if len(seed_means) else None
    if len(seed_means) < 2:
        return {
            "estimate": estimate,
            "ci95_lower": None,
            "ci95_upper": None,
            "seed_clusters": int(len(seed_means)),
        }
    standard_error = float(stats.sem(seed_means.to_numpy(dtype=float)))
    radius = float(stats.t.ppf(0.975, len(seed_means) - 1) * standard_error)
    return {
        "estimate": estimate,
        "ci95_lower": estimate - radius,
        "ci95_upper": estimate + radius,
        "seed_clusters": int(len(seed_means)),
    }


def _simulation_intervals(paired: pd.DataFrame) -> dict:
    frame = paired.copy()
    frame["elasticity_learning_rate__coupled_minus_shuffled"] = frame[
        "elasticity_learned__coupled"
    ].astype(float) - frame["elasticity_learned__marginal_preserving_shuffle"].astype(float)
    outcomes = {
        "learning_time_censored_difference": "learning_time__coupled_minus_shuffled",
        "learning_rate_difference": "elasticity_learning_rate__coupled_minus_shuffled",
        "action_correlation_difference": "mean_action_correlation__coupled_minus_shuffled",
        "active_share_difference": "mean_active_group_share__coupled_minus_shuffled",
        "buyer_price_difference": "mean_buyer_price__coupled_minus_shuffled",
    }
    groups = {
        "all_multiple_active": frame[frame["n_active"].gt(1)],
        "ucb_multiple_active": frame[frame["n_active"].gt(1) & frame["algorithm"].eq("ucb")],
        "non_ucb_homogeneous_family_pool_multiple_active": frame[
            frame["n_active"].gt(1) & frame["algorithm"].ne("ucb")
        ],
        "ucb_singleton_control": frame[frame["n_active"].eq(1) & frame["algorithm"].eq("ucb")],
        "non_ucb_homogeneous_family_pool_singleton_control": frame[
            frame["n_active"].eq(1) & frame["algorithm"].ne("ucb")
        ],
    }
    return {
        label: {name: seed_clustered_interval(rows, column) for name, column in outcomes.items()}
        for label, rows in groups.items()
    }


def critical_memory_screen(paired: pd.DataFrame) -> dict:
    """Compare a smooth memory curve with a one-hinge threshold on held-out seeds."""

    def fit_group(frame: pd.DataFrame) -> dict:
        seeds = sorted(frame["seed"].unique())
        memories = sorted(frame["reward_memory"].unique())
        if len(seeds) < 4 or len(memories) < 4:
            return {"status": "insufficient_seed_or_memory_support"}
        split = seeds[max(1, int(np.floor(0.6 * len(seeds)))) - 1]
        train = frame[frame["seed"].le(split)].copy()
        test = frame[frame["seed"].gt(split)].copy()
        if train.empty or test.empty:
            return {"status": "insufficient_holdout_support"}

        def design(rows: pd.DataFrame) -> pd.DataFrame:
            categories = pd.get_dummies(
                rows[["n_active", "signal_to_noise", "router_eta", "algorithm"]].astype(str),
                drop_first=True,
                dtype=float,
            )
            memory = rows["reward_memory"].astype(float).reset_index(drop=True)
            return pd.concat(
                [
                    pd.Series(1.0, index=range(len(rows)), name="intercept"),
                    memory.rename("memory"),
                    memory.pow(2).rename("memory_squared"),
                    categories.reset_index(drop=True),
                ],
                axis=1,
            )

        train_x = design(train)
        test_x = design(test).reindex(columns=train_x.columns, fill_value=0.0)
        train_y = (train["learning_time__coupled_minus_shuffled"] / train["horizon"]).to_numpy(
            dtype=float
        )
        test_y = (test["learning_time__coupled_minus_shuffled"] / test["horizon"]).to_numpy(
            dtype=float
        )

        def fit_predict(left: pd.DataFrame, right: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
            coefficients = np.linalg.pinv(left.to_numpy(dtype=float)) @ train_y
            train_prediction = left.to_numpy(dtype=float) @ coefficients
            test_prediction = right.to_numpy(dtype=float) @ coefficients
            return train_prediction, test_prediction

        _, base_test = fit_predict(train_x, test_x)
        candidates = memories[1:-1]
        best: tuple[float, float, np.ndarray] | None = None
        for threshold in candidates:
            left = train_x.assign(
                memory_hinge=np.maximum(train["reward_memory"].to_numpy(dtype=float) - threshold, 0)
            )
            right = test_x.assign(
                memory_hinge=np.maximum(test["reward_memory"].to_numpy(dtype=float) - threshold, 0)
            )
            train_prediction, test_prediction = fit_predict(left, right)
            train_mse = float(np.mean((train_y - train_prediction) ** 2))
            if best is None or train_mse < best[1]:
                best = (float(threshold), train_mse, test_prediction)
        assert best is not None
        base_mse = float(np.mean((test_y - base_test) ** 2))
        threshold_mse = float(np.mean((test_y - best[2]) ** 2))
        return {
            "status": "estimated",
            "training_seed_max": int(split),
            "holdout_seeds": [int(seed) for seed in seeds if seed > split],
            "selected_threshold": best[0],
            "smooth_holdout_mse": base_mse,
            "threshold_holdout_mse": threshold_mse,
            "threshold_to_smooth_mse_ratio": (threshold_mse / base_mse if base_mse > 0 else None),
            "threshold_improves_holdout": bool(threshold_mse < base_mse),
            "boundary": (
                "A selected hinge is a simulation prediction comparison, not evidence of a "
                "live phase transition or a deployed provider learner."
            ),
        }

    return {
        "multiple_active": fit_group(paired[paired["n_active"].gt(1)]),
        "singleton_negative_control": fit_group(paired[paired["n_active"].eq(1)]),
    }


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    config_path: Path = DEFAULT_CONFIG,
    seeds: int | None = None,
    horizon: int | None = None,
    data_root: Path | None = None,
    source_revision: str | None = None,
) -> dict:
    payload = config_path.read_bytes()
    protocol = tomllib.loads(payload.decode("utf-8"))
    calibration = public_price_calibration(data_root, protocol)
    controlled = controlled_router_factorial(protocol, calibration=calibration)
    simulations = run_factorial(protocol, seeds=seeds, horizon=horizon, calibration=calibration)
    paired = _paired(simulations)
    critical_memory = critical_memory_screen(paired)
    out_dir.mkdir(parents=True, exist_ok=True)
    controlled.to_parquet(out_dir / "controlled_router_factorial.parquet", index=False)
    simulations.to_parquet(out_dir / "multiagent_factorial.parquet", index=False)
    paired.to_parquet(out_dir / "paired_signal_interventions.parquet", index=False)
    clustered_intervals = _simulation_intervals(paired)

    singleton_error = controlled[controlled["n_cutters"].eq(1)]["path_wedge"].abs().max()
    group = controlled[controlled["n_cutters"].eq(controlled["n_active"])]
    monotone = (
        group.groupby(["router_eta", "cut_fraction"])
        .apply(
            lambda rows: (
                rows.sort_values("n_active")["path_wedge"].diff().dropna().ge(-1e-12).all()
            ),
            include_groups=False,
        )
        .all()
    )
    plot_rows = []
    for (active, algorithm), rows in paired.groupby(["n_active", "algorithm"]):
        record = {"n_active": int(active), "algorithm": str(algorithm)}
        for label, outcome in (
            ("learning_time", "learning_time__coupled_minus_shuffled"),
            ("action_correlation", "mean_action_correlation__coupled_minus_shuffled"),
            ("active_share", "mean_active_group_share__coupled_minus_shuffled"),
        ):
            interval = seed_clustered_interval(rows, outcome)
            record[f"{label}_estimate"] = interval["estimate"]
            record[f"{label}_lower"] = interval["ci95_lower"]
            record[f"{label}_upper"] = interval["ci95_upper"]
        plot_rows.append(record)
    grouped = pd.DataFrame(plot_rows)

    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.4), constrained_layout=True)
    focal = group[
        np.isclose(group["router_eta"], float(protocol["study"]["frozen_eta"]))
        & np.isclose(group["cut_fraction"], 0.10)
    ]
    axes[0, 0].plot(focal["n_active"], focal["path_wedge"], marker="o", color="#1f4e79")
    axes[0, 0].axhline(0, color="black", lw=0.8)
    axes[0, 0].set(title="A. Exact path wedge", xlabel="active cutters", ylabel="elasticity wedge")
    for algorithm, rows in grouped.groupby("algorithm"):
        rows = rows.sort_values("n_active")
        for axis, label in (
            (axes[0, 1], "learning_time"),
            (axes[1, 0], "action_correlation"),
            (axes[1, 1], "active_share"),
        ):
            estimate = rows[f"{label}_estimate"].to_numpy(dtype=float)
            lower = rows[f"{label}_lower"].fillna(rows[f"{label}_estimate"]).to_numpy(dtype=float)
            upper = rows[f"{label}_upper"].fillna(rows[f"{label}_estimate"]).to_numpy(dtype=float)
            axis.errorbar(
                rows["n_active"],
                estimate,
                yerr=np.vstack([estimate - lower, upper - estimate]),
                marker="o",
                capsize=2.5,
                linewidth=1.2,
                label=algorithm,
            )
    axes[0, 1].axhline(0, color="black", lw=0.8)
    axes[0, 1].set(
        title="B. Elasticity learning time",
        xlabel="active learners",
        ylabel="coupled minus shuffled periods",
    )
    axes[1, 0].axhline(0, color="black", lw=0.8)
    axes[1, 0].set(
        title="C. Common action response",
        xlabel="active learners",
        ylabel="coupled minus shuffled correlation",
    )
    axes[1, 1].axhline(0, color="black", lw=0.8)
    axes[1, 1].set(
        title="D. Active-group allocation",
        xlabel="active learners",
        ylabel="coupled minus shuffled share",
    )
    axes[0, 1].legend(frameon=False, fontsize=7)
    fig.suptitle("GLM-5.2 market-share HMP mechanism screen\n95% t intervals clustered by seed")
    fig.savefig(out_dir / "market_share_hmp_simulation.png", dpi=180)
    fig.savefig(out_dir / "market_share_hmp_simulation.pdf")
    plt.close(fig)

    ucb = paired[paired["algorithm"].eq("ucb") & paired["n_active"].gt(1)]
    non_ucb_pool = paired[paired["algorithm"].ne("ucb") & paired["n_active"].gt(1)]
    summary = {
        "study_id": protocol["study"]["study_id"],
        "protocol_sha256": hashlib.sha256(payload).hexdigest(),
        "calibration": calibration,
        "calibration_source_revision": source_revision,
        "controlled_cells": int(len(controlled)),
        "simulation_rows": int(len(simulations)),
        "paired_cells": int(len(paired)),
        "exact_singleton_zero_wedge_passed": bool(singleton_error <= 1e-12),
        "maximum_singleton_absolute_wedge": float(singleton_error),
        "group_wedge_monotone_in_active_count": bool(monotone),
        "ucb_mean_learning_time_coupled_minus_shuffled": (
            float(ucb["learning_time__coupled_minus_shuffled"].mean()) if not ucb.empty else None
        ),
        "ucb_coupled_learning_rate": (
            float(ucb["elasticity_learned__coupled"].mean()) if not ucb.empty else None
        ),
        "ucb_shuffled_learning_rate": (
            float(ucb["elasticity_learned__marginal_preserving_shuffle"].mean())
            if not ucb.empty
            else None
        ),
        "non_ucb_homogeneous_family_pool_mean_learning_time_coupled_minus_shuffled": (
            float(non_ucb_pool["learning_time__coupled_minus_shuffled"].mean())
            if not non_ucb_pool.empty
            else None
        ),
        "non_ucb_homogeneous_family_pool_coupled_learning_rate": (
            float(non_ucb_pool["elasticity_learned__coupled"].mean())
            if not non_ucb_pool.empty
            else None
        ),
        "non_ucb_homogeneous_family_pool_shuffled_learning_rate": (
            float(non_ucb_pool["elasticity_learned__marginal_preserving_shuffle"].mean())
            if not non_ucb_pool.empty
            else None
        ),
        "seed_clustered_intervals": clustered_intervals,
        "critical_memory_threshold_screen": critical_memory,
        "empirical_property_chain_passed": False,
        "mechanism_validated": False,
        "claim_boundary": (
            "The price-path identity is exact for the declared router and the signal-order "
            "intervention is simulated. No live HMP, algorithm, collusion, or welfare claim "
            "is promoted without the separately gated empirical property chain."
        ),
    }
    (out_dir / "market_share_hmp_simulation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seeds", type=int)
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.out,
                config_path=args.config,
                seeds=args.seeds,
                horizon=args.horizon,
                data_root=args.data_root,
                source_revision=args.source_revision,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
