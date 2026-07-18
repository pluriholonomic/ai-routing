"""SM2 — seeded router welfare screening with real allocation frictions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from ..market_env import (
    InversePriceRouter,
    LowestCostRouter,
    MarketKernel,
    ProviderAction,
    ProviderSpec,
    RandomRouter,
    ReliabilityWeightedRouter,
    Workload,
)
from .common import DEFAULT_OUT, save, save_json


@dataclass(frozen=True)
class ScreeningScenario:
    scenario: str
    providers: tuple[ProviderSpec, ...]
    workload: Workload
    actions: dict[str, ProviderAction]
    mean_demand: float


def scenarios() -> tuple[ScreeningScenario, ...]:
    """Return the frozen capacity/reliability screening designs."""
    actions = {"cheap": ProviderAction(0.0020), "safe": ProviderAction(0.0024)}

    def workload(
        name: str,
        failure_loss: float,
        fallback_latency_ms: float,
        *,
        max_attempts: int | None = None,
    ) -> Workload:
        return Workload(
            name,
            input_tokens=1_000,
            output_tokens=256,
            delivered_value=0.02,
            latency_cost_per_ms=0.000001,
            failure_loss=failure_loss,
            fallback_latency_ms=fallback_latency_ms,
            max_attempts=max_attempts,
        )

    def provider(
        name: str,
        *,
        cost: float,
        capacity: int,
        reliability: float,
        latency: float,
    ) -> ProviderSpec:
        return ProviderSpec(
            name,
            marginal_cost=cost,
            physical_capacity=capacity,
            capital_cost_per_slot=0.000002,
            base_latency_ms=latency,
            reliability=reliability,
        )

    return (
        ScreeningScenario(
            "spare_homogeneous_service",
            (
                provider("cheap", cost=0.0010, capacity=30, reliability=0.99, latency=250),
                provider("safe", cost=0.0012, capacity=30, reliability=0.99, latency=250),
            ),
            workload("short_chat", failure_loss=0.02, fallback_latency_ms=100),
            actions,
            12,
        ),
        ScreeningScenario(
            "cheap_provider_capacity_scarce",
            (
                provider("cheap", cost=0.0010, capacity=4, reliability=0.99, latency=250),
                provider("safe", cost=0.0012, capacity=30, reliability=0.99, latency=250),
            ),
            workload("short_chat", failure_loss=0.02, fallback_latency_ms=200),
            actions,
            12,
        ),
        ScreeningScenario(
            "cheap_provider_unreliable_low_loss",
            (
                provider("cheap", cost=0.0010, capacity=30, reliability=0.75, latency=200),
                provider("safe", cost=0.0012, capacity=30, reliability=0.99, latency=250),
            ),
            workload(
                "short_chat",
                failure_loss=0.002,
                fallback_latency_ms=100,
                max_attempts=1,
            ),
            actions,
            12,
        ),
        ScreeningScenario(
            "cheap_provider_unreliable_high_loss",
            (
                provider("cheap", cost=0.0010, capacity=30, reliability=0.75, latency=200),
                provider("safe", cost=0.0012, capacity=30, reliability=0.99, latency=250),
            ),
            workload(
                "short_chat",
                failure_loss=0.02,
                fallback_latency_ms=100,
                max_attempts=1,
            ),
            actions,
            12,
        ),
    )


def routers() -> dict[str, object]:
    return {
        "inverse_square": InversePriceRouter(2),
        "lowest_cost": LowestCostRouter(),
        "uniform_random": RandomRouter(),
        "reliability_weighted": ReliabilityWeightedRouter(
            exponent=2,
            reliability_exponent=4,
        ),
    }


def _episode(
    design: ScreeningScenario,
    *,
    router_name: str,
    seed: int,
    horizon_epochs: int,
) -> dict:
    router = routers()[router_name]
    kernel = MarketKernel(
        design.providers,
        design.workload,
        router,
        seed=seed,
    )
    demand_rng = np.random.default_rng(np.random.SeedSequence([seed, 811]))
    demand_path = demand_rng.poisson(design.mean_demand, size=horizon_epochs)
    welfare = 0.0
    user_utility = 0.0
    provider_profit = 0.0
    payments = 0.0
    latency = 0.0
    total_requests = 0
    served = 0
    fallback = 0
    provider_served = {provider.provider: 0 for provider in design.providers}
    capacity_rejections = 0
    technical_failures = 0

    for demand in demand_path:
        result = kernel.step(design.actions, demand=int(demand))
        welfare += result.total_welfare
        user_utility += result.total_user_utility
        provider_profit += result.total_provider_profit
        payments += result.total_payment
        total_requests += result.demand
        served += result.served_requests
        latency += sum(request.latency_ms for request in result.requests)
        fallback += sum(len(request.attempted_providers) > 1 for request in result.requests)
        for request in result.requests:
            if request.served_provider:
                provider_served[request.served_provider] += 1
        capacity_rejections += sum(row.capacity_rejections for row in result.providers)
        technical_failures += sum(row.technical_failures for row in result.providers)

    shares = np.array(list(provider_served.values()), dtype=float)
    shares = shares / shares.sum() if shares.sum() else np.zeros_like(shares)
    return {
        "scenario": design.scenario,
        "router": router_name,
        "seed": seed,
        "horizon_epochs": horizon_epochs,
        "requests": total_requests,
        "served_requests": served,
        "welfare_per_request": welfare / total_requests,
        "user_utility_per_request": user_utility / total_requests,
        "provider_profit_per_request": provider_profit / total_requests,
        "payment_per_request": payments / total_requests,
        "success_rate": served / total_requests,
        "fallback_rate": fallback / total_requests,
        "mean_latency_ms": latency / total_requests,
        "served_hhi": float(np.square(shares).sum()),
        "capacity_rejections_per_request": capacity_rejections / total_requests,
        "technical_failures_per_request": technical_failures / total_requests,
    }


def screening_panel(
    *,
    seeds: tuple[int, ...] = tuple(range(30)),
    horizon_epochs: int = 288,
) -> pd.DataFrame:
    rows = [
        _episode(
            design,
            router_name=router_name,
            seed=seed,
            horizon_epochs=horizon_epochs,
        )
        for design in scenarios()
        for seed in seeds
        for router_name in routers()
    ]
    return pd.DataFrame(rows)


def contrasts(panel: pd.DataFrame) -> pd.DataFrame:
    """Paired router differences relative to inverse-square routing."""
    outcomes = [
        "welfare_per_request",
        "user_utility_per_request",
        "provider_profit_per_request",
        "success_rate",
        "fallback_rate",
        "mean_latency_ms",
        "served_hhi",
    ]
    rows: list[dict] = []
    baseline = panel[panel["router"] == "inverse_square"].set_index(["scenario", "seed"])
    for router in ["lowest_cost", "uniform_random", "reliability_weighted"]:
        treatment = panel[panel["router"] == router].set_index(["scenario", "seed"])
        for scenario in sorted(panel["scenario"].unique()):
            for outcome in outcomes:
                difference = (
                    treatment.loc[scenario, outcome].sort_index()
                    - baseline.loc[scenario, outcome].sort_index()
                )
                mean = float(difference.mean())
                sem = float(stats.sem(difference))
                critical = float(stats.t.ppf(0.975, len(difference) - 1))
                rows.append(
                    {
                        "scenario": scenario,
                        "router": router,
                        "baseline": "inverse_square",
                        "outcome": outcome,
                        "seeds": int(len(difference)),
                        "mean_difference": mean,
                        "ci95_low": mean - critical * sem,
                        "ci95_high": mean + critical * sem,
                        "positive_share": float((difference > 0).mean()),
                    }
                )
    return pd.DataFrame(rows)


def summary(panel: pd.DataFrame, paired: pd.DataFrame) -> dict:
    welfare = paired[paired["outcome"] == "welfare_per_request"]
    winners = (
        panel.groupby(["scenario", "router"], as_index=False)["welfare_per_request"]
        .mean()
        .sort_values(["scenario", "welfare_per_request"], ascending=[True, False])
        .groupby("scenario", as_index=False)
        .first()
    )
    return {
        "experiment_id": "sm2-router-welfare-screening-v1",
        "evidence_status": "synthetic_screening_not_confirmatory",
        "episodes": int(len(panel)),
        "seeds": int(panel["seed"].nunique()),
        "horizon_epochs": int(panel["horizon_epochs"].iloc[0]),
        "winning_router_by_scenario": winners[
            ["scenario", "router", "welfare_per_request"]
        ].to_dict("records"),
        "welfare_contrasts": welfare.to_dict("records"),
        "accounting_boundary": (
            "Welfare cancels provider payments and includes resource, capacity, "
            "latency, and failure costs."
        ),
        "evidence_boundary": (
            "This is a synthetic static-strategy screening result. It is not an "
            "equilibrium estimate, calibrated market effect, or claim about a "
            "live router."
        ),
    }


def plot_welfare(paired: pd.DataFrame, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    view = paired[paired["outcome"] == "welfare_per_request"].copy()
    order = [
        "spare_homogeneous_service",
        "cheap_provider_capacity_scarce",
        "cheap_provider_unreliable_low_loss",
        "cheap_provider_unreliable_high_loss",
    ]
    labels = {
        "spare_homogeneous_service": "Spare capacity",
        "cheap_provider_capacity_scarce": "Cheap provider capacity-scarce",
        "cheap_provider_unreliable_low_loss": "Cheap provider unreliable; low loss",
        "cheap_provider_unreliable_high_loss": "Cheap provider unreliable; high loss",
    }
    fig, axis = plt.subplots(figsize=(9.4, 4.6), constrained_layout=True)
    offsets = {
        "lowest_cost": -0.18,
        "uniform_random": 0.0,
        "reliability_weighted": 0.18,
    }
    colors = {
        "lowest_cost": "#2457A6",
        "uniform_random": "#C45122",
        "reliability_weighted": "#228B69",
    }
    markers = {
        "lowest_cost": "o",
        "uniform_random": "s",
        "reliability_weighted": "^",
    }
    for router in ["lowest_cost", "uniform_random", "reliability_weighted"]:
        rows = view[view["router"] == router].set_index("scenario").loc[order]
        y = np.arange(len(order)) + offsets[router]
        x = rows["mean_difference"].to_numpy() * 1_000
        low = (rows["mean_difference"] - rows["ci95_low"]).to_numpy() * 1_000
        high = (rows["ci95_high"] - rows["mean_difference"]).to_numpy() * 1_000
        axis.errorbar(
            x,
            y,
            xerr=np.vstack([low, high]),
            fmt=markers[router],
            color=colors[router],
            capsize=3,
            linewidth=1.5,
            label=router.replace("_", " "),
        )
    axis.axvline(0, color="#555555", linewidth=1, linestyle="--")
    axis.set_yticks(np.arange(len(order)), [labels[item] for item in order])
    axis.invert_yaxis()
    axis.set_xlabel("Welfare difference vs inverse-square (USD per 1,000 requests)")
    axis.set_title("Router welfare depends on the allocation friction")
    axis.legend(
        frameon=False,
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
    )
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.grid(axis="x", color="#dddddd", linewidth=0.7)
    png = out_dir / "sm2_router_welfare.png"
    pdf = out_dir / "sm2_router_welfare.pdf"
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = screening_panel()
    paired = contrasts(panel)
    save(panel, out_dir, "sm2_router_welfare_episodes")
    save(paired, out_dir, "sm2_router_welfare_contrasts")
    result = summary(panel, paired)
    save_json(result, out_dir, "sm2_router_welfare_summary")
    plot_welfare(paired, out_dir)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
