"""Historical replay for monotone, exploratory, and low-coupling router rules.

This is a mechanical no-provider-response counterfactual. It reports quote,
public uptime, concentration, and the router's local cross-provider price gain;
it does not label any scalar as welfare because user values and provider costs
are not observed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..adaptive_router import allocation_probabilities, policy_metrics

DEFAULT_OUT = Path("data/analysis/adaptive-router-counterfactual")
METRICS = (
    "expected_quote_usd",
    "expected_reliability",
    "hhi",
    "max_share",
    "cheapest_share",
    "cross_provider_gain",
    "own_price_gain",
)


def load_hourly_menus(data_root: Path, *, all_captures: bool = False) -> pd.DataFrame:
    pattern = data_root / "curated" / "endpoints_snapshots" / "dt=*" / "*.parquet"
    if not list((data_root / "curated" / "endpoints_snapshots").glob("dt=*/*.parquet")):
        raise FileNotFoundError(f"no endpoint snapshots below {pattern}")
    hourly_filter = "TRUE" if all_captures else "hour_rank = 1"
    query = f"""
    WITH raw AS (
      SELECT
        run_ts,
        dt,
        strptime(run_ts, '%Y%m%dT%H%M%SZ') AS observed_at,
        model_id,
        provider_name,
        tag AS endpoint_tag,
        price_prompt,
        price_completion,
        (96.0 * price_prompt + 8.0 * price_completion) AS expected_quote_usd,
        least(greatest(uptime_last_30m / 100.0, 0.01), 1.0) AS quality,
        row_number() OVER (
          PARTITION BY run_ts, model_id, lower(provider_name)
          ORDER BY (96.0 * price_prompt + 8.0 * price_completion), tag
        ) AS provider_rank
      FROM read_parquet('{pattern.as_posix()}')
      WHERE status = 0
        AND provider_name IS NOT NULL AND tag IS NOT NULL
        AND price_prompt > 0 AND price_completion > 0
        AND uptime_last_30m > 0
    ), collapsed AS (
      SELECT * EXCLUDE(provider_rank)
      FROM raw
      WHERE provider_rank = 1
    ), menu_keys AS (
      SELECT run_ts, dt, observed_at, model_id, count(*) AS candidate_count
      FROM collapsed
      GROUP BY ALL
      HAVING count(*) >= 3
    ), ranked_keys AS (
      SELECT *, row_number() OVER (
        PARTITION BY date_trunc('hour', observed_at), model_id
        ORDER BY observed_at DESC, run_ts DESC
      ) AS hour_rank
      FROM menu_keys
    ), selected AS (
      SELECT * EXCLUDE(hour_rank)
      FROM ranked_keys
      WHERE {hourly_filter}
    )
    SELECT c.*, s.candidate_count
    FROM collapsed c
    JOIN selected s USING (run_ts, dt, observed_at, model_id)
    ORDER BY observed_at, model_id, expected_quote_usd, provider_name
    """
    return duckdb.sql(query).df()


def _menu_arrays(group: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return (
        group["expected_quote_usd"].to_numpy(dtype=float),
        group["quality"].to_numpy(dtype=float),
    )


def tradeoff_grid(frame: pd.DataFrame) -> pd.DataFrame:
    accumulators: dict[
        tuple[float, float], dict[tuple[str, str], dict[str, float]]
    ] = {}
    etas = (0.50, 0.72, 0.90, 1.00, 1.25, 1.45, 1.75, 2.00, 2.16)
    explorations = (0.0, 0.02, 0.05, 0.10, 0.15, 0.20)
    for key in ((eta, epsilon) for eta in etas for epsilon in explorations):
        accumulators[key] = {}
    for _, group in frame.groupby(["run_ts", "model_id"], sort=False):
        costs, qualities = _menu_arrays(group)
        cluster_key = (str(group["dt"].iloc[0]), str(group["model_id"].iloc[0]))
        for (eta, epsilon), clusters in accumulators.items():
            metrics = policy_metrics(costs, qualities, eta=eta, exploration=epsilon)
            totals = clusters.setdefault(
                cluster_key, {metric: 0.0 for metric in METRICS} | {"menus": 0.0}
            )
            for metric in METRICS:
                totals[metric] += metrics[metric]
            totals["menus"] += 1
    rows = []
    for (eta, epsilon), clusters in accumulators.items():
        cluster_means = [
            {
                metric: totals[metric] / totals["menus"]
                for metric in METRICS
            }
            for totals in clusters.values()
        ]
        rows.append(
            {
                "eta": eta,
                "exploration": epsilon,
                "menus": int(sum(totals["menus"] for totals in clusters.values())),
                "model_day_clusters": len(cluster_means),
                **{
                    metric: float(np.mean([row[metric] for row in cluster_means]))
                    for metric in METRICS
                },
            }
        )
    grid = pd.DataFrame(rows)
    baseline = grid[(grid["eta"] == 2.0) & (grid["exploration"] == 0.0)].iloc[0]
    grid["quote_premium_pct"] = 100 * (
        grid["expected_quote_usd"] / baseline["expected_quote_usd"] - 1
    )
    grid["reliability_change_pp"] = 100 * (
        grid["expected_reliability"] - baseline["expected_reliability"]
    )
    grid["coupling_reduction_pct"] = 100 * (
        1 - grid["cross_provider_gain"] / baseline["cross_provider_gain"]
    )
    grid["hhi_change"] = grid["hhi"] - baseline["hhi"]
    grid["feasible"] = (grid["quote_premium_pct"] <= 2.0 + 1e-12) & (
        grid["reliability_change_pp"] >= -0.2 - 1e-12
    )
    return grid


def select_policy(grid: pd.DataFrame) -> dict[str, float]:
    feasible = grid[grid["feasible"]].copy()
    if feasible.empty:
        feasible = grid[(grid["eta"] == 2.0) & (grid["exploration"] == 0.0)].copy()
    chosen = feasible.sort_values(
        ["cross_provider_gain", "hhi", "expected_quote_usd"], kind="stable"
    ).iloc[0]
    return {"eta": float(chosen["eta"]), "exploration": float(chosen["exploration"])}


def evaluate_policies(frame: pd.DataFrame, chosen: dict[str, float]) -> pd.DataFrame:
    policies = {
        "baseline_eta2": {"eta": 2.0, "exploration": 0.0},
        "calibrated_eta145": {"eta": 1.45, "exploration": 0.0},
        "independent_explore_eta2_eps10": {"eta": 2.0, "exploration": 0.10},
        "cone_projected_historical": chosen,
    }
    rows: list[dict[str, Any]] = []
    for (run_ts, model_id), group in frame.groupby(["run_ts", "model_id"], sort=False):
        costs, qualities = _menu_arrays(group)
        metadata = {
            "run_ts": str(run_ts),
            "dt": str(group["dt"].iloc[0]),
            "observed_at": group["observed_at"].iloc[0],
            "model_id": str(model_id),
            "candidate_count": len(group),
        }
        for policy, parameters in policies.items():
            metrics = policy_metrics(costs, qualities, **parameters)
            shares = allocation_probabilities(costs, qualities, **parameters)
            rows.append(
                metadata
                | {
                    "policy": policy,
                    **parameters,
                    **metrics,
                    "dominance_inversions": _dominance_inversions(
                        costs, qualities, shares
                    ),
                }
            )
    return pd.DataFrame(rows)


def _dominance_inversions(
    costs: np.ndarray, qualities: np.ndarray, shares: np.ndarray
) -> int:
    inversions = 0
    for left in range(len(costs)):
        for right in range(len(costs)):
            strict = costs[left] < costs[right] or qualities[left] > qualities[right]
            if (
                costs[left] <= costs[right]
                and qualities[left] >= qualities[right]
                and strict
                and shares[left] + 1e-12 < shares[right]
            ):
                inversions += 1
    return inversions


def policy_summary(evaluated: pd.DataFrame, *, sample: str) -> pd.DataFrame:
    clustered = (
        evaluated.groupby(["dt", "model_id", "policy"], as_index=False)[list(METRICS)]
        .mean()
    )
    summary = clustered.groupby("policy", as_index=False)[list(METRICS)].mean()
    summary.insert(1, "sample", sample)
    summary["model_day_clusters"] = clustered.groupby("policy").size().reindex(
        summary["policy"]
    ).to_numpy()
    baseline = summary.set_index("policy").loc["baseline_eta2"]
    summary["quote_premium_pct_vs_baseline"] = 100 * (
        summary["expected_quote_usd"] / baseline["expected_quote_usd"] - 1
    )
    summary["reliability_change_pp_vs_baseline"] = 100 * (
        summary["expected_reliability"] - baseline["expected_reliability"]
    )
    summary["coupling_reduction_pct_vs_baseline"] = 100 * (
        1 - summary["cross_provider_gain"] / baseline["cross_provider_gain"]
    )
    return summary


def paired_intervals(
    evaluated: pd.DataFrame, *, draws: int = 1_000, seed: int = 20260720
) -> pd.DataFrame:
    cluster = (
        evaluated.groupby(["dt", "model_id", "policy"], as_index=False)[list(METRICS)]
        .mean()
    )
    pivot = cluster.pivot(index=["dt", "model_id"], columns="policy", values=list(METRICS))
    rng = np.random.default_rng(seed)
    rows = []
    policies = sorted(set(evaluated["policy"]) - {"baseline_eta2"})
    for policy in policies:
        derived = {
            "quote_premium_pct": (
                "expected_quote_usd",
                lambda candidate, baseline: 100 * (candidate / baseline - 1),
            ),
            "reliability_change_pp": (
                "expected_reliability",
                lambda candidate, baseline: 100 * (candidate - baseline),
            ),
            "hhi_change": ("hhi", lambda candidate, baseline: candidate - baseline),
            "coupling_reduction_pct": (
                "cross_provider_gain",
                lambda candidate, baseline: 100 * (1 - candidate / baseline),
            ),
        }
        for label, (source_metric, transform) in derived.items():
            pair = pivot[source_metric][["baseline_eta2", policy]].dropna()
            baseline = pair["baseline_eta2"].to_numpy()
            candidate = pair[policy].to_numpy()
            indices = rng.integers(0, len(pair), size=(draws, len(pair)))
            estimates = transform(candidate[indices].mean(axis=1), baseline[indices].mean(axis=1))
            low, high = np.quantile(estimates, [0.025, 0.975])
            rows.append(
                {
                    "policy": policy,
                    "metric": label,
                    "clusters": len(pair),
                    "paired_difference": float(transform(candidate.mean(), baseline.mean())),
                    "bootstrap_ci_low": float(low),
                    "bootstrap_ci_high": float(high),
                    "interval_scope": "model-day cluster bootstrap; descriptive panel",
                }
            )
        for metric in METRICS:
            pair = pivot[metric][["baseline_eta2", policy]].dropna()
            differences = pair[policy].to_numpy() - pair["baseline_eta2"].to_numpy()
            estimates = []
            if len(differences):
                indices = rng.integers(0, len(differences), size=(draws, len(differences)))
                estimates = differences[indices].mean(axis=1)
            low, high = (
                np.quantile(estimates, [0.025, 0.975]) if len(estimates) else (np.nan, np.nan)
            )
            rows.append(
                {
                    "policy": policy,
                    "metric": metric,
                    "clusters": len(differences),
                    "paired_difference": float(differences.mean()) if len(differences) else None,
                    "bootstrap_ci_low": float(low),
                    "bootstrap_ci_high": float(high),
                    "interval_scope": "model-day cluster bootstrap; descriptive panel",
                }
            )
    return pd.DataFrame(rows)


def _plot_tradeoff(grid: pd.DataFrame, chosen: dict[str, float], out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for epsilon, group in grid.groupby("exploration"):
        ax.plot(
            group["quote_premium_pct"],
            group["coupling_reduction_pct"],
            marker="o",
            markersize=3.5,
            linewidth=1,
            label=f"exploration={epsilon:.2f}",
        )
    selected = grid[
        (grid["eta"] == chosen["eta"]) & (grid["exploration"] == chosen["exploration"])
    ].iloc[0]
    ax.scatter(
        [selected["quote_premium_pct"]],
        [selected["coupling_reduction_pct"]],
        marker="*",
        s=150,
        color="black",
        zorder=5,
        label="training-selected rule",
    )
    ax.axvline(2.0, color="0.45", linestyle="--", linewidth=1, label="2% quote constraint")
    ax.set_xlabel("Expected quote premium versus η=2 baseline (%)")
    ax.set_ylabel("Reduction in local cross-provider price gain (%)")
    ax.set_title("Historical menu replay: cost–coupling frontier")
    ax.grid(alpha=0.2)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"adaptive-router-frontier.{extension}", dpi=180)
    plt.close(fig)


def _plot_timeseries(evaluated: pd.DataFrame, split_date: str, out_dir: Path) -> pd.DataFrame:
    clustered = evaluated.groupby(
        ["dt", "model_id", "policy"], as_index=False
    )[list(METRICS)].mean()
    daily = clustered.groupby(["dt", "policy"], as_index=False)[list(METRICS)].mean()
    baseline = daily[daily["policy"] == "baseline_eta2"].set_index("dt")
    candidate = daily[daily["policy"] == "cone_projected_historical"].set_index("dt")
    joined = candidate.join(baseline, lsuffix="_candidate", rsuffix="_baseline").reset_index()
    joined["quote_premium_pct"] = 100 * (
        joined["expected_quote_usd_candidate"] / joined["expected_quote_usd_baseline"] - 1
    )
    joined["reliability_change_pp"] = 100 * (
        joined["expected_reliability_candidate"]
        - joined["expected_reliability_baseline"]
    )
    joined["hhi_change"] = joined["hhi_candidate"] - joined["hhi_baseline"]
    joined["coupling_reduction_pct"] = 100 * (
        1 - joined["cross_provider_gain_candidate"] / joined["cross_provider_gain_baseline"]
    )
    joined["sample"] = np.where(joined["dt"] < split_date, "training", "holdout")
    x = pd.to_datetime(joined["dt"])
    figure, axes = plt.subplots(2, 2, figsize=(9.2, 6.2), sharex=True)
    panels = (
        ("quote_premium_pct", "Quote premium (%)", 0.0),
        ("reliability_change_pp", "Reliability change (pp)", 0.0),
        ("hhi_change", "HHI change", 0.0),
        ("coupling_reduction_pct", "Coupling reduction (%)", 0.0),
    )
    for ax, (column, label, reference) in zip(axes.flat, panels, strict=True):
        ax.plot(x, joined[column], color="#1f4e79", marker="o", markersize=3, linewidth=1.2)
        ax.axhline(reference, color="0.5", linewidth=0.8)
        ax.axvline(pd.Timestamp(split_date), color="#a33", linestyle="--", linewidth=1)
        ax.set_ylabel(label)
        ax.grid(alpha=0.2)
    axes[0, 0].set_title("Cone-projected rule minus η=2 baseline")
    axes[0, 1].set_title(f"Dashed line: holdout begins {split_date}")
    figure.autofmt_xdate(rotation=25)
    figure.tight_layout()
    for extension in ("png", "pdf"):
        figure.savefig(out_dir / f"adaptive-router-daily-effects.{extension}", dpi=180)
    plt.close(figure)
    return joined


def run_analysis(
    *,
    data_root: Path,
    out_dir: Path = DEFAULT_OUT,
    all_captures: bool = False,
    bootstrap_draws: int = 1_000,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    menus = load_hourly_menus(data_root, all_captures=all_captures)
    dates = sorted(menus["dt"].astype(str).unique())
    if len(dates) < 4:
        raise RuntimeError("at least four dates are required for a temporal holdout")
    split_index = min(max(int(np.floor(0.70 * len(dates))), 1), len(dates) - 1)
    split_date = dates[split_index]
    training = menus[menus["dt"].astype(str) < split_date]
    grid = tradeoff_grid(training)
    chosen = select_policy(grid)
    evaluated = evaluate_policies(menus, chosen)
    evaluated_training = evaluated[evaluated["dt"].astype(str) < split_date]
    evaluated_holdout = evaluated[evaluated["dt"].astype(str) >= split_date]
    summaries = pd.concat(
        [
            policy_summary(evaluated_training, sample="training"),
            policy_summary(evaluated_holdout, sample="holdout"),
        ],
        ignore_index=True,
    )
    intervals = paired_intervals(evaluated_holdout, draws=bootstrap_draws)
    daily = _plot_timeseries(evaluated, split_date, out_dir)
    _plot_tradeoff(grid, chosen, out_dir)
    grid.to_csv(out_dir / "adaptive-router-tradeoff-grid.csv", index=False)
    summaries.to_csv(out_dir / "adaptive-router-policy-summary.csv", index=False)
    intervals.to_csv(out_dir / "adaptive-router-paired-intervals.csv", index=False)
    daily.to_csv(out_dir / "adaptive-router-daily-effects.csv", index=False)
    evaluated.to_parquet(out_dir / "adaptive-router-menu-policy.parquet", index=False)
    holdout_selected = summaries[
        (summaries["sample"] == "holdout")
        & (summaries["policy"] == "cone_projected_historical")
    ].iloc[0]
    summary = {
        "status": "complete",
        "source_first_run_ts": str(menus["run_ts"].min()),
        "source_last_run_ts": str(menus["run_ts"].max()),
        "source_dates": len(dates),
        "hourly_menu_count": int(menus[["run_ts", "model_id"]].drop_duplicates().shape[0]),
        "models": int(menus["model_id"].nunique()),
        "providers": int(menus["provider_name"].nunique()),
        "training_end_exclusive": split_date,
        "holdout_start": split_date,
        "selected_eta": chosen["eta"],
        "selected_exploration": chosen["exploration"],
        "holdout_quote_premium_pct": float(
            holdout_selected["quote_premium_pct_vs_baseline"]
        ),
        "holdout_reliability_change_pp": float(
            holdout_selected["reliability_change_pp_vs_baseline"]
        ),
        "holdout_coupling_reduction_pct": float(
            holdout_selected["coupling_reduction_pct_vs_baseline"]
        ),
        "fixed_live_horizon_blocks": 120,
        "welfare_identified": False,
        "claim_boundary": (
            "Mechanical replay holding menus and provider behavior fixed. Quote, public "
            "uptime, concentration, and local allocation derivatives are identified on "
            "observed menus; user value, provider cost, endogenous repricing, dynamic "
            "equilibrium, and scalar welfare are not."
        ),
    }
    (out_dir / "adaptive-router-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(
        "# Adaptive monotone router counterfactual\n\n"
        f"The training prefix selected `eta={chosen['eta']:.2f}` and "
        f"`exploration={chosen['exploration']:.2f}` subject to a 2% expected-quote "
        "premium and 0.2 percentage-point public-uptime loss constraint. On the "
        f"temporal holdout, its quote premium is "
        f"{summary['holdout_quote_premium_pct']:.3f}%, public-uptime change is "
        f"{summary['holdout_reliability_change_pp']:.3f} pp, and the reduction in "
        f"local cross-provider price gain is "
        f"{summary['holdout_coupling_reduction_pct']:.3f}%.\n\n"
        "These are no-provider-response menu-replay quantities, not welfare or dynamic "
        "equilibrium estimates. The live paid study tests realized owned-request outcomes "
        "at a separately preregistered 120-block horizon.\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--all-captures", action="store_true")
    parser.add_argument("--bootstrap-draws", type=int, default=1_000)
    args = parser.parse_args()
    print(
        json.dumps(
            run_analysis(
                data_root=args.data_root,
                out_dir=args.output_dir,
                all_captures=args.all_captures,
                bootstrap_draws=args.bootstrap_draws,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
