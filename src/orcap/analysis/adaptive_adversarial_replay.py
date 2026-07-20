"""Historical adversarial replay for adaptive monotone routing policies.

The replay perturbs one observed provider at a time and measures allocation and
bounded-profit manipulability.  It uses observed menus, prices, and public uptime,
but not realized market-wide routing.  Profit is therefore reported over explicit
marginal-cost fractions rather than inferred for named providers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..adaptive_router import allocation_probabilities, projected_policy
from ..market_env.routers_adaptive import (
    _operator_neutral_probabilities,
    _trust_region,
)
from .adaptive_router_counterfactual import load_hourly_menus

DEFAULT_OUT = Path("data/analysis/adaptive-router-adversarial")
POLICIES = (
    "baseline_eta2",
    "fixed_eta125_eps10",
    "menu_adaptive_raw",
    "menu_adaptive_hardened",
)
QUOTE_MULTIPLIERS = (0.60, 0.75, 0.90, 1.00, 1.01, 1.05, 1.10, 1.25, 1.50)
COST_FRACTIONS = (0.25, 0.50, 0.75)


def _menu_hash(providers: list[str], costs: np.ndarray, qualities: np.ndarray) -> str:
    payload = [
        (provider, round(float(cost), 15), round(float(quality), 8))
        for provider, cost, quality in zip(providers, costs, qualities, strict=True)
    ]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _hardened_target(
    providers: list[str],
    costs: np.ndarray,
    qualities: np.ndarray,
    groups: dict[str, str],
) -> tuple[dict[str, float], float, dict[str, float]]:
    operators = sorted(set(groups.values()))
    representative_costs = {
        operator: min(
            float(costs[index])
            for index, provider in enumerate(providers)
            if groups[provider] == operator
        )
        for operator in operators
    }
    representative_qualities = {
        operator: max(
            float(qualities[index])
            for index, provider in enumerate(providers)
            if groups[provider] == operator
        )
        for operator in operators
    }
    etas: dict[str, float] = {}
    explorations = []
    for operator in operators:
        comparison = [other for other in operators if other != operator]
        if len(comparison) < 2:
            etas[operator] = 1.25
            explorations.append(0.10)
            continue
        choice = projected_policy(
            [representative_costs[other] for other in comparison],
            [representative_qualities[other] for other in comparison],
        )
        etas[operator] = float(choice["eta"])
        explorations.append(float(choice["exploration"]))
    epsilon = max(0.10, float(np.mean(explorations)) if explorations else 0.10)
    scores = {
        provider: float(qualities[index] * costs[index] ** (-etas[groups[provider]]))
        for index, provider in enumerate(providers)
    }
    probabilities = _operator_neutral_probabilities(
        scores,
        groups,
        exploration=epsilon,
        cap=0.60,
    )
    return probabilities, epsilon, etas


def policy_shares(
    policy: str,
    providers: list[str],
    costs: np.ndarray,
    qualities: np.ndarray,
    *,
    previous: dict[str, float] | None = None,
    operator_groups: dict[str, str] | None = None,
    reference_costs: np.ndarray | None = None,
) -> dict[str, float]:
    """Return one-menu policy shares with optional hardening state."""
    if policy == "baseline_eta2":
        values = allocation_probabilities(costs, qualities, eta=2.0)
        return dict(zip(providers, map(float, values), strict=True))
    if policy == "fixed_eta125_eps10":
        values = allocation_probabilities(costs, qualities, eta=1.25, exploration=0.10)
        return dict(zip(providers, map(float, values), strict=True))
    if policy == "menu_adaptive_raw":
        choice = projected_policy(costs, qualities)
        values = allocation_probabilities(
            costs,
            qualities,
            eta=float(choice["eta"]),
            exploration=float(choice["exploration"]),
        )
        return dict(zip(providers, map(float, values), strict=True))
    if policy == "menu_adaptive_hardened":
        groups = operator_groups or {provider: provider for provider in providers}
        reference = costs if reference_costs is None else reference_costs
        _, epsilon, operator_etas = _hardened_target(
            providers, reference, qualities, groups
        )
        effective_costs = np.where(
            costs >= reference,
            costs,
            0.25 * costs + 0.75 * reference,
        )
        scores = {}
        for index, provider in enumerate(providers):
            base_eta = operator_etas[groups[provider]]
            response_eta = base_eta
            if costs[index] > reference[index] + 1e-15:
                response_eta = max(base_eta, 2.0)
            relative_cost = effective_costs[index] / reference[index]
            if previous and provider in previous:
                scores[provider] = float(
                    previous[provider] * relative_cost ** (-response_eta)
                )
            else:
                scores[provider] = float(
                    qualities[index]
                    * reference[index] ** (-base_eta)
                    * relative_cost ** (-response_eta)
                )
            if costs[index] > reference[index] + 1e-15:
                scores[provider] = 0.0
        target = _operator_neutral_probabilities(
            scores,
            groups,
            exploration=0.0 if previous else epsilon,
            cap=0.60,
        )
        quote_lock_breached = bool(np.any(costs > reference + 1e-15))
        bounded = (
            target
            if quote_lock_breached
            else _trust_region(target, previous or {}, math.log(1.5))
        )
        return bounded
    raise ValueError(f"unknown policy {policy!r}")


def _attack_one_menu(
    group: pd.DataFrame,
    *,
    max_attack_providers: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    providers = [str(value).casefold() for value in group["provider_name"]]
    costs = group["expected_quote_usd"].to_numpy(dtype=float)
    qualities = group["quality"].to_numpy(dtype=float)
    menu_id = _menu_hash(providers, costs, qualities)
    metadata = {
        "menu_id": menu_id,
        "run_ts": str(group["run_ts"].iloc[0]),
        "dt": str(group["dt"].iloc[0]),
        "model_id": str(group["model_id"].iloc[0]),
        "candidate_count": len(group),
    }
    baselines = {
        policy: policy_shares(policy, providers, costs, qualities) for policy in POLICIES
    }
    ranking = sorted(
        range(len(providers)),
        key=lambda index: baselines["baseline_eta2"][providers[index]],
        reverse=True,
    )[:max_attack_providers]
    attacks: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for policy in POLICIES:
        baseline = baselines[policy]
        provider_rows = []
        for index in ranking:
            provider = providers[index]
            incumbent_price = float(costs[index])
            for multiplier in QUOTE_MULTIPLIERS:
                attacked_costs = costs.copy()
                attacked_costs[index] *= multiplier
                shares = policy_shares(
                    policy,
                    providers,
                    attacked_costs,
                    qualities,
                    previous=baseline if policy == "menu_adaptive_hardened" else None,
                    reference_costs=costs if policy == "menu_adaptive_hardened" else None,
                )
                row: dict[str, Any] = metadata | {
                    "policy": policy,
                    "provider": provider,
                    "incumbent_quote": incumbent_price,
                    "quote_multiplier": multiplier,
                    "attacked_quote": float(attacked_costs[index]),
                    "baseline_share": baseline[provider],
                    "attacked_share": shares[provider],
                    "share_gain": shares[provider] - baseline[provider],
                }
                for fraction in COST_FRACTIONS:
                    marginal_cost = fraction * incumbent_price
                    base_profit = baseline[provider] * (incumbent_price - marginal_cost)
                    attack_profit = shares[provider] * (
                        float(attacked_costs[index]) - marginal_cost
                    )
                    row[f"profit_gain_cost_frac_{fraction:.2f}"] = attack_profit - base_profit
                attacks.append(row)
                provider_rows.append(row)

        max_share = max(provider_rows, key=lambda row: row["share_gain"])
        cheapest = int(np.argmin(costs))
        fade_costs = costs.copy()
        fade_costs[cheapest] *= 0.75
        fade_shares = policy_shares(
            policy,
            providers,
            fade_costs,
            qualities,
            previous=baseline if policy == "menu_adaptive_hardened" else None,
            reference_costs=costs if policy == "menu_adaptive_hardened" else None,
        )

        clone = providers[cheapest] + "#clone"
        sybil_providers = providers + [clone]
        sybil_costs = np.append(costs, costs[cheapest])
        sybil_qualities = np.append(qualities, qualities[cheapest])
        groups = {provider: provider for provider in sybil_providers}
        groups[clone] = providers[cheapest]
        sybil_reference_costs = np.append(costs, costs[cheapest])
        sybil_shares = policy_shares(
            policy,
            sybil_providers,
            sybil_costs,
            sybil_qualities,
            operator_groups=groups if policy == "menu_adaptive_hardened" else None,
            reference_costs=(
                sybil_reference_costs if policy == "menu_adaptive_hardened" else None
            ),
        )
        sybil_combined = sybil_shares[providers[cheapest]] + sybil_shares[clone]
        summaries.append(
            metadata
            | {
                "policy": policy,
                "attacked_providers": len(ranking),
                "max_share_gain": float(max_share["share_gain"]),
                "max_share_gain_multiplier": float(max_share["quote_multiplier"]),
                "max_profit_gain_cost_frac_0.25": float(
                    max(row["profit_gain_cost_frac_0.25"] for row in provider_rows)
                ),
                "max_profit_gain_cost_frac_0.50": float(
                    max(row["profit_gain_cost_frac_0.50"] for row in provider_rows)
                ),
                "max_profit_gain_cost_frac_0.75": float(
                    max(row["profit_gain_cost_frac_0.75"] for row in provider_rows)
                ),
                "quote_fade_captured_share": float(fade_shares[providers[cheapest]]),
                "sybil_combined_share_gain": float(
                    sybil_combined - baseline[providers[cheapest]]
                ),
            }
        )
    return attacks, summaries


def _cluster_intervals(
    summaries: pd.DataFrame, *, draws: int, seed: int
) -> pd.DataFrame:
    metrics = (
        "max_share_gain",
        "max_profit_gain_cost_frac_0.25",
        "max_profit_gain_cost_frac_0.50",
        "max_profit_gain_cost_frac_0.75",
        "quote_fade_captured_share",
        "sybil_combined_share_gain",
    )
    cluster = summaries.groupby(["dt", "model_id", "policy"], as_index=False)[
        list(metrics)
    ].mean()
    pivot = cluster.pivot(index=["dt", "model_id"], columns="policy", values=list(metrics))
    rng = np.random.default_rng(seed)
    rows = []
    for policy in sorted(set(POLICIES) - {"baseline_eta2"}):
        for metric in metrics:
            pair = pivot[metric][["baseline_eta2", policy]].dropna()
            delta = pair[policy].to_numpy() - pair["baseline_eta2"].to_numpy()
            indices = rng.integers(0, len(delta), size=(draws, len(delta)))
            estimates = delta[indices].mean(axis=1)
            low, high = np.quantile(estimates, [0.025, 0.975])
            rows.append(
                {
                    "policy": policy,
                    "metric": metric,
                    "clusters": len(delta),
                    "paired_difference": float(delta.mean()),
                    "bootstrap_ci_low": float(low),
                    "bootstrap_ci_high": float(high),
                    "interval_scope": "model-day cluster bootstrap",
                }
            )
    return pd.DataFrame(rows)


def _plot(summaries: pd.DataFrame, out_dir: Path) -> None:
    colors = {
        "baseline_eta2": "#4c78a8",
        "fixed_eta125_eps10": "#f58518",
        "menu_adaptive_raw": "#e45756",
        "menu_adaptive_hardened": "#54a24b",
    }
    panels = (
        ("max_share_gain", "Maximum allocation gain"),
        ("max_profit_gain_cost_frac_0.50", "Maximum profit gain; cost = 50% of quote"),
        ("quote_fade_captured_share", "Share captured by a 25% fading quote"),
        ("sybil_combined_share_gain", "Two-identity combined share gain"),
    )
    figure, axes = plt.subplots(2, 2, figsize=(9.2, 6.6))
    for axis, (metric, label) in zip(axes.flat, panels, strict=True):
        for policy in POLICIES:
            values = np.sort(summaries.loc[summaries["policy"] == policy, metric])
            probability = np.arange(1, len(values) + 1) / len(values)
            axis.plot(values, probability, label=policy, color=colors[policy], linewidth=1.2)
        axis.set_xlabel(label)
        axis.set_ylabel("Empirical CDF")
        axis.grid(alpha=0.2)
    axes[0, 0].legend(frameon=False, fontsize=7)
    figure.suptitle("Historical adversarial menu replay")
    figure.tight_layout()
    for extension in ("png", "pdf"):
        figure.savefig(out_dir / f"adaptive-adversarial-replay.{extension}", dpi=180)
    plt.close(figure)


def run_replay(
    *,
    data_root: Path,
    out_dir: Path = DEFAULT_OUT,
    max_menus: int | None = None,
    max_attack_providers: int = 4,
    bootstrap_draws: int = 1_000,
    seed: int = 20260720,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    menus = load_hourly_menus(data_root)
    keys = menus[["run_ts", "model_id"]].drop_duplicates()
    if max_menus is not None:
        keys = keys.copy()
        keys["sample_order"] = keys.apply(
            lambda row: hashlib.sha256(
                f"{row['run_ts']}|{row['model_id']}|{seed}".encode()
            ).hexdigest(),
            axis=1,
        )
        keys = keys.sort_values("sample_order", kind="stable").head(max_menus)
        menus = menus.merge(
            keys.drop(columns="sample_order"),
            on=["run_ts", "model_id"],
            how="inner",
        )
    all_attacks: list[dict[str, Any]] = []
    all_summaries: list[dict[str, Any]] = []
    for _, group in menus.groupby(["run_ts", "model_id"], sort=False):
        attacks, summaries = _attack_one_menu(
            group,
            max_attack_providers=max_attack_providers,
        )
        all_attacks.extend(attacks)
        all_summaries.extend(summaries)
    attack_frame = pd.DataFrame(all_attacks)
    summary_frame = pd.DataFrame(all_summaries)
    intervals = _cluster_intervals(summary_frame, draws=bootstrap_draws, seed=seed)
    attack_frame.to_parquet(out_dir / "adaptive-adversarial-attacks.parquet", index=False)
    summary_frame.to_parquet(out_dir / "adaptive-adversarial-menu-summary.parquet", index=False)
    intervals.to_csv(out_dir / "adaptive-adversarial-paired-intervals.csv", index=False)
    _plot(summary_frame, out_dir)

    aggregate = summary_frame.groupby("policy").agg(
        menus=("menu_id", "nunique"),
        mean_max_share_gain=("max_share_gain", "mean"),
        p95_max_share_gain=("max_share_gain", lambda values: values.quantile(0.95)),
        mean_profit_gain_mid_cost=("max_profit_gain_cost_frac_0.50", "mean"),
        mean_quote_fade_share=("quote_fade_captured_share", "mean"),
        mean_sybil_gain=("sybil_combined_share_gain", "mean"),
    )
    result = {
        "status": "complete",
        "menus": int(summary_frame["menu_id"].nunique()),
        "models": int(summary_frame["model_id"].nunique()),
        "dates": int(summary_frame["dt"].nunique()),
        "attack_rows": len(attack_frame),
        "quote_multipliers": list(QUOTE_MULTIPLIERS),
        "cost_fractions": list(COST_FRACTIONS),
        "policies": aggregate.reset_index().to_dict(orient="records"),
        "claim_boundary": (
            "Historical public-menu perturbation holding rivals, demand, and service "
            "processes fixed. Allocation effects are mechanical; profit is an identified "
            "sensitivity over declared cost fractions. This does not identify actual "
            "provider strategy, equilibrium, collusion, or market-wide routing."
        ),
    }
    (out_dir / "adaptive-adversarial-summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-menus", type=int)
    parser.add_argument("--max-attack-providers", type=int, default=4)
    parser.add_argument("--bootstrap-draws", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args()
    print(
        json.dumps(
            run_replay(
                data_root=args.data_root,
                out_dir=args.output_dir,
                max_menus=args.max_menus,
                max_attack_providers=args.max_attack_providers,
                bootstrap_draws=args.bootstrap_draws,
                seed=args.seed,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
