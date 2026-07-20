"""Calibrated strategic screening for adaptive routing mechanisms.

This module samples immutable historical provider menus, places explicit
marginal-cost and capacity bands around them, and searches for unilateral and
two-provider deviations.  It also runs sequential global best-response dynamics
and independent UCB pricing agents.  The simulation is a bounded adversarial
audit, not an estimate of named-provider conduct.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..market_env.exploitability import (
    coalition_grid_audit,
    expected_capacity_profits,
    unilateral_grid_audit,
)
from ..market_env.routers import InversePriceRouter
from ..market_env.routers_adaptive import (
    AdaptiveMonotoneRouter,
    HardenedAdaptiveRouter,
    MenuProjectedRouter,
)
from ..market_env.strategies_qlearn import train_symmetric
from ..market_env.types import ProviderAction, ProviderSpec
from .adaptive_router_counterfactual import load_hourly_menus

DEFAULT_OUT = Path("data/analysis/adaptive-router-adversarial-simulation")
POLICIES = (
    "baseline_eta2",
    "fixed_eta125_eps10",
    "menu_adaptive_raw",
    "menu_adaptive_hardened",
)
COST_FRACTIONS = (0.25, 0.50, 0.75)
CAPACITY_REGIMES = {"scarce": 0.75, "balanced": 1.0, "spare": 2.0}
DEVIATION_MULTIPLIERS = (0.60, 0.80, 1.00, 1.01, 1.05, 1.20, 1.50)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def router_for(policy: str):
    if policy == "baseline_eta2":
        return InversePriceRouter(2.0)
    if policy == "fixed_eta125_eps10":
        return AdaptiveMonotoneRouter(eta=1.25, exploration=0.10)
    if policy == "menu_adaptive_raw":
        return MenuProjectedRouter()
    if policy == "menu_adaptive_hardened":
        return HardenedAdaptiveRouter()
    raise ValueError(f"unknown policy {policy!r}")


def _sample_menus(frame: pd.DataFrame, max_menus: int) -> pd.DataFrame:
    keys = frame[["run_ts", "model_id", "dt"]].drop_duplicates().copy()
    keys["order"] = keys.apply(
        lambda row: hashlib.sha256(
            f"{row['run_ts']}|{row['model_id']}|20260720".encode()
        ).hexdigest(),
        axis=1,
    )
    selected = keys.sort_values("order", kind="stable").head(max_menus)
    return frame.merge(selected.drop(columns="order"), on=["run_ts", "model_id", "dt"])


def _market_from_menu(
    group: pd.DataFrame,
    *,
    cost_fraction: float,
    capacity_multiplier: float,
    demand: int = 120,
    max_providers: int = 4,
) -> tuple[dict[str, ProviderSpec], dict[str, ProviderAction]]:
    chosen = group.sort_values("expected_quote_usd", kind="stable").head(max_providers)
    per_provider_capacity = max(1, math.ceil(capacity_multiplier * demand / len(chosen)))
    specs: dict[str, ProviderSpec] = {}
    actions: dict[str, ProviderAction] = {}
    for _, row in chosen.iterrows():
        provider = str(row["provider_name"]).casefold()
        quote = float(row["expected_quote_usd"])
        specs[provider] = ProviderSpec(
            provider=provider,
            marginal_cost=cost_fraction * quote,
            physical_capacity=per_provider_capacity,
            reliability=float(row["quality"]),
            base_latency_ms=250.0,
        )
        actions[provider] = ProviderAction(quote)
    return specs, actions


def sequential_best_response(
    router,
    specs: dict[str, ProviderSpec],
    initial: dict[str, ProviderAction],
    *,
    demand: int,
    rounds: int = 40,
) -> dict[str, Any]:
    """Sequential global grid best responses with a frozen provider order."""
    actions = dict(initial)
    if hasattr(router, "advance"):
        router.advance(specs, actions)
    base_quotes = {provider: action.quote for provider, action in initial.items()}
    paths = {provider: [action.quote] for provider, action in initial.items()}
    for _ in range(rounds):
        for provider in sorted(specs):
            candidates = sorted(
                {
                    max(
                        specs[provider].marginal_cost,
                        base_quotes[provider] * multiplier,
                    )
                    for multiplier in DEVIATION_MULTIPLIERS
                }
            )
            best_action = actions[provider]
            best_profit = expected_capacity_profits(
                router, specs, actions, demand=demand
            ).profits[provider]
            for quote in candidates:
                trial = dict(actions)
                trial[provider] = ProviderAction(quote)
                profit = expected_capacity_profits(
                    router, specs, trial, demand=demand
                ).profits[provider]
                if profit > best_profit + 1e-12:
                    best_profit = profit
                    best_action = trial[provider]
            actions[provider] = best_action
        if hasattr(router, "advance"):
            router.advance(specs, actions)
        for provider in sorted(specs):
            paths[provider].append(actions[provider].quote)
    final = expected_capacity_profits(router, specs, actions, demand=demand)
    audit = unilateral_grid_audit(
        router,
        specs,
        actions,
        demand=demand,
        quote_multipliers=DEVIATION_MULTIPLIERS,
    )
    return {
        "final_quotes": {provider: action.quote for provider, action in actions.items()},
        "final_profits": final.profits,
        "mean_final_quote": float(np.mean([action.quote for action in actions.values()])),
        "mean_final_profit": float(np.mean(list(final.profits.values()))),
        "max_deviation_gain": audit["max_gain"],
        "max_deviation_gain_relative": audit["max_gain_relative_to_mean_abs_profit"],
        "converged_last_five": all(
            len(values) >= 6 and len(set(values[-5:])) == 1 for values in paths.values()
        ),
        "paths": paths,
    }


@dataclass
class UCBAgent:
    arms: np.ndarray
    exploration: float = 2.0

    def __post_init__(self) -> None:
        self.counts = np.zeros(len(self.arms), dtype=int)
        self.values = np.zeros(len(self.arms), dtype=float)

    def choose(self, step: int) -> int:
        unseen = np.flatnonzero(self.counts == 0)
        if len(unseen):
            return int(unseen[0])
        bonus = self.exploration * np.sqrt(np.log(step + 1) / self.counts)
        return int(np.argmax(self.values + bonus))

    def update(self, arm: int, reward: float) -> None:
        self.counts[arm] += 1
        self.values[arm] += (reward - self.values[arm]) / self.counts[arm]


def train_ucb_market(
    router,
    specs: dict[str, ProviderSpec],
    initial: dict[str, ProviderAction],
    *,
    demand: int,
    steps: int,
    seed: int,
) -> dict[str, Any]:
    """Independent UCB price learners with seeded asynchronous action order."""
    rng = np.random.default_rng(seed)
    names = sorted(specs)
    grids = {
        provider: np.array(
            sorted(
                {
                    max(
                        specs[provider].marginal_cost,
                        initial[provider].quote * multiplier,
                    )
                    for multiplier in DEVIATION_MULTIPLIERS
                }
            )
        )
        for provider in names
    }
    agents = {provider: UCBAgent(grids[provider]) for provider in names}
    actions = dict(initial)
    if hasattr(router, "advance"):
        router.advance(specs, actions)
    tail_profits: list[float] = []
    tail_quotes: list[float] = []
    for step in range(steps):
        order = list(rng.permutation(names))
        selected: dict[str, int] = {}
        for provider in order:
            arm = agents[provider].choose(step)
            selected[provider] = arm
            actions[provider] = ProviderAction(float(grids[provider][arm]))
        profile = expected_capacity_profits(router, specs, actions, demand=demand)
        for provider in names:
            agents[provider].update(selected[provider], profile.profits[provider])
        if hasattr(router, "advance"):
            router.advance(specs, actions)
        if step >= max(0, steps - 100):
            tail_profits.append(float(np.mean(list(profile.profits.values()))))
            tail_quotes.append(float(np.mean([action.quote for action in actions.values()])))

    greedy_actions = {
        provider: ProviderAction(float(grids[provider][int(np.argmax(agents[provider].values))]))
        for provider in names
    }
    final = expected_capacity_profits(router, specs, greedy_actions, demand=demand)
    audit = unilateral_grid_audit(
        router,
        specs,
        greedy_actions,
        demand=demand,
        quote_multipliers=DEVIATION_MULTIPLIERS,
    )
    return {
        "seed": seed,
        "greedy_quotes": {
            provider: action.quote for provider, action in greedy_actions.items()
        },
        "mean_tail_quote": float(np.mean(tail_quotes)),
        "mean_tail_profit": float(np.mean(tail_profits)),
        "final_mean_profit": float(np.mean(list(final.profits.values()))),
        "max_deviation_gain": audit["max_gain"],
        "max_deviation_gain_relative": audit["max_gain_relative_to_mean_abs_profit"],
    }


def train_q_screen(
    policy: str,
    *,
    seeds: int,
    max_epochs: int,
) -> list[dict[str, Any]]:
    """Run the existing Calvano-style tabular-Q benchmark for one router."""
    rows = []
    stable_window = max(100, min(10_000, max_epochs // 5))
    for seed in range(seeds):
        result = train_symmetric(
            router_for(policy),
            n_agents=3,
            mc=0.2,
            demand=1.0,
            anchor=1.0,
            max_epochs=max_epochs,
            stable_window=stable_window,
            seed=seed,
            check_every=max(10, min(1_000, stable_window // 5)),
        )
        rows.append(
            {
                "policy": policy,
                "seed": seed,
                "epochs_run": int(result["epochs_run"]),
                "converged": bool(result["converged"]),
                "mean_profit": float(result["mean_profit"]),
                "pi_nash": float(result["pi_nash"]),
                "pi_monopoly": float(result["pi_monopoly"]),
                "calvano_delta": result["calvano_delta"],
                "final_prices_json": json.dumps(
                    result["final_prices"], sort_keys=True, separators=(",", ":")
                ),
            }
        )
    return rows


def _plot(static: pd.DataFrame, learning: pd.DataFrame, out_dir: Path) -> None:
    colors = {
        "baseline_eta2": "#4c78a8",
        "fixed_eta125_eps10": "#f58518",
        "menu_adaptive_raw": "#e45756",
        "menu_adaptive_hardened": "#54a24b",
    }
    figure, axes = plt.subplots(1, 3, figsize=(11.0, 3.8))
    metrics = (
        ("max_unilateral_gain_relative", "Unilateral exploitability"),
        ("max_coalition_gain_relative", "Two-provider exploitability"),
    )
    for axis, (metric, label) in zip(axes[:2], metrics, strict=True):
        values = [static.loc[static["policy"] == policy, metric] for policy in POLICIES]
        boxes = axis.boxplot(values, tick_labels=POLICIES, showfliers=False, patch_artist=True)
        for patch, policy in zip(boxes["boxes"], POLICIES, strict=True):
            patch.set_facecolor(colors[policy])
            patch.set_alpha(0.65)
        axis.tick_params(axis="x", rotation=35, labelsize=7)
        axis.set_ylabel(label)
        axis.grid(axis="y", alpha=0.2)
    grouped = learning.groupby("policy")["max_deviation_gain_relative"].mean().reindex(POLICIES)
    axes[2].bar(
        range(len(POLICIES)),
        grouped,
        color=[colors[policy] for policy in POLICIES],
        alpha=0.75,
    )
    axes[2].set_xticks(range(len(POLICIES)), POLICIES, rotation=35, ha="right", fontsize=7)
    axes[2].set_ylabel("Post-UCB unilateral exploitability")
    axes[2].grid(axis="y", alpha=0.2)
    figure.suptitle("Calibrated strategic router screening")
    figure.tight_layout()
    for extension in ("png", "pdf"):
        figure.savefig(out_dir / f"adaptive-adversarial-simulation.{extension}", dpi=180)
    plt.close(figure)


def run_simulation(
    *,
    data_root: Path,
    out_dir: Path = DEFAULT_OUT,
    max_menus: int = 200,
    learning_menus: int = 8,
    learning_steps: int = 2_000,
    learning_seeds: int = 10,
    q_learning_epochs: int = 100_000,
    demand: int = 120,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    menus = load_hourly_menus(data_root)
    available_dates = pd.to_datetime(menus["dt"], utc=True, errors="raise")
    if start_date is not None:
        start = pd.Timestamp(start_date, tz="UTC")
        menus = menus.loc[available_dates >= start].copy()
        available_dates = available_dates.loc[menus.index]
    if end_date is not None:
        end = pd.Timestamp(end_date, tz="UTC")
        menus = menus.loc[available_dates <= end].copy()
    if menus.empty:
        raise ValueError(
            "no eligible menus after applying the frozen date window "
            f"[{start_date or '-infinity'}, {end_date or '+infinity'}]"
        )
    menus = _sample_menus(menus, max_menus)
    static_rows = []
    br_rows = []
    learning_rows = []
    q_rows = []
    for menu_index, ((run_ts, model_id), group) in enumerate(
        menus.groupby(["run_ts", "model_id"], sort=False)
    ):
        metadata = {
            "run_ts": str(run_ts),
            "dt": str(group["dt"].iloc[0]),
            "model_id": str(model_id),
            "menu_index": menu_index,
        }
        for cost_fraction in COST_FRACTIONS:
            for capacity_name, capacity_multiplier in CAPACITY_REGIMES.items():
                specs, actions = _market_from_menu(
                    group,
                    cost_fraction=cost_fraction,
                    capacity_multiplier=capacity_multiplier,
                    demand=demand,
                )
                if len(specs) < 3:
                    continue
                for policy in POLICIES:
                    router = router_for(policy)
                    if hasattr(router, "advance"):
                        router.advance(specs, actions)
                    unilateral = unilateral_grid_audit(
                        router,
                        specs,
                        actions,
                        demand=demand,
                        quote_multipliers=DEVIATION_MULTIPLIERS,
                        capacity_fractions=(0.5, 1.0),
                    )
                    coalition = coalition_grid_audit(
                        router,
                        specs,
                        actions,
                        demand=demand,
                        quote_multipliers=DEVIATION_MULTIPLIERS,
                    )
                    baseline = unilateral["baseline"]
                    static_rows.append(
                        metadata
                        | {
                            "policy": policy,
                            "cost_fraction": cost_fraction,
                            "capacity_regime": capacity_name,
                            "providers": len(specs),
                            "max_unilateral_gain": unilateral["max_gain"],
                            "max_unilateral_gain_relative": unilateral[
                                "max_gain_relative_to_mean_abs_profit"
                            ],
                            "max_coalition_gain": coalition["max_gain"],
                            "max_coalition_gain_relative": coalition[
                                "max_gain_relative_to_market_abs_profit"
                            ],
                            "baseline_payment": baseline["payment"],
                            "baseline_mean_profit": float(
                                np.mean(list(baseline["profits"].values()))
                            ),
                        }
                    )
                    if (
                        menu_index < learning_menus
                        and cost_fraction == 0.50
                        and capacity_name == "balanced"
                    ):
                        br = sequential_best_response(
                            copy.deepcopy(router),
                            specs,
                            actions,
                            demand=demand,
                        )
                        br_rows.append(metadata | {"policy": policy} | br)
                        for seed in range(learning_seeds):
                            learned = train_ucb_market(
                                router_for(policy),
                                specs,
                                actions,
                                demand=demand,
                                steps=learning_steps,
                                seed=seed,
                            )
                            learning_rows.append(metadata | {"policy": policy} | learned)

    for policy in POLICIES:
        q_rows.extend(
            train_q_screen(
                policy,
                seeds=learning_seeds,
                max_epochs=q_learning_epochs,
            )
        )

    static = pd.DataFrame(static_rows)
    best_response = pd.DataFrame(br_rows)
    learning = pd.DataFrame(learning_rows)
    q_learning = pd.DataFrame(q_rows)
    static.to_parquet(out_dir / "adaptive-adversarial-static.parquet", index=False)
    best_response.to_parquet(
        out_dir / "adaptive-adversarial-best-response.parquet", index=False
    )
    learning.to_parquet(out_dir / "adaptive-adversarial-ucb.parquet", index=False)
    q_learning.to_parquet(
        out_dir / "adaptive-adversarial-q-learning.parquet", index=False
    )
    _plot(static, learning, out_dir)

    policy_summary = (
        static.groupby("policy")
        .agg(
            cells=("policy", "size"),
            mean_unilateral_exploitability=("max_unilateral_gain_relative", "mean"),
            p95_unilateral_exploitability=(
                "max_unilateral_gain_relative",
                lambda values: values.quantile(0.95),
            ),
            mean_coalition_exploitability=("max_coalition_gain_relative", "mean"),
            p95_coalition_exploitability=(
                "max_coalition_gain_relative",
                lambda values: values.quantile(0.95),
            ),
        )
        .reset_index()
    )
    learning_summary = (
        learning.groupby("policy")
        .agg(
            runs=("policy", "size"),
            mean_post_learning_exploitability=("max_deviation_gain_relative", "mean"),
            p95_post_learning_exploitability=(
                "max_deviation_gain_relative",
                lambda values: values.quantile(0.95),
            ),
        )
        .reset_index()
    )
    result = {
        "status": "complete",
        "menus": int(static[["run_ts", "model_id"]].drop_duplicates().shape[0]),
        "static_cells": len(static),
        "best_response_cells": len(best_response),
        "learning_runs": len(learning),
        "q_learning_runs": len(q_learning),
        "learning_steps": learning_steps,
        "learning_seeds": learning_seeds,
        "q_learning_epochs": q_learning_epochs,
        "date_window": {
            "start_date": start_date,
            "end_date": end_date,
            "observed_min": pd.Timestamp(static["dt"].min()).date().isoformat(),
            "observed_max": pd.Timestamp(static["dt"].max()).date().isoformat(),
        },
        "policies": policy_summary.to_dict(orient="records"),
        "learning": learning_summary.to_dict(orient="records"),
        "q_learning": (
            q_learning.groupby("policy")
            .agg(
                runs=("policy", "size"),
                convergence_rate=("converged", "mean"),
                mean_calvano_delta=("calvano_delta", "mean"),
            )
            .reset_index()
            .to_dict(orient="records")
        ),
        "claim_boundary": (
            "Calibrated bounded strategic simulation using public menu states, declared "
            "cost/capacity bands, a finite global deviation grid, sequential best "
            "responses, and independent UCB learners. It is not proof against all "
            "history-dependent strategies and does not identify named-provider conduct."
        ),
    }
    result = _json_safe(result)
    (out_dir / "adaptive-adversarial-simulation-summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-menus", type=int, default=200)
    parser.add_argument("--learning-menus", type=int, default=8)
    parser.add_argument("--learning-steps", type=int, default=2_000)
    parser.add_argument("--learning-seeds", type=int, default=10)
    parser.add_argument("--q-learning-epochs", type=int, default=100_000)
    parser.add_argument("--demand", type=int, default=120)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()
    print(
        json.dumps(
            run_simulation(
                data_root=args.data_root,
                out_dir=args.output_dir,
                max_menus=args.max_menus,
                learning_menus=args.learning_menus,
                learning_steps=args.learning_steps,
                learning_seeds=args.learning_seeds,
                q_learning_epochs=args.q_learning_epochs,
                demand=args.demand,
                start_date=args.start_date,
                end_date=args.end_date,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
