"""Minimal deterministic episode for the strategic routing parallel API."""

from __future__ import annotations

import json

from orcap.market_env.kernel import MarketKernel
from orcap.market_env.rl_env import StrategicRoutingParallelEnv
from orcap.market_env.routers import InversePriceRouter
from orcap.market_env.types import ProviderAction, ProviderSpec, Workload


def run_demo(*, seed: int = 17, horizon: int = 4) -> dict:
    providers = (
        ProviderSpec("owned", marginal_cost=0.20, physical_capacity=5, reliability=0.95),
        ProviderSpec("spot", marginal_cost=0.35, physical_capacity=4, reliability=0.85),
    )
    workload = Workload(
        "demo",
        input_tokens=256,
        output_tokens=32,
        delivered_value=2.0,
        failure_loss=1.0,
        latency_cost_per_ms=0.00001,
        max_attempts=2,
    )
    kernel = MarketKernel(
        providers,
        workload,
        InversePriceRouter(exponent=2.0),
        seed=seed,
    )
    env = StrategicRoutingParallelEnv(kernel, horizon_epochs=horizon)
    env.reset(seed=seed)
    epochs = []
    for epoch in range(horizon):
        actions = {
            "owned": ProviderAction(quote=0.80 + 0.02 * epoch),
            "spot": ProviderAction(quote=0.95 - 0.01 * epoch),
        }
        transition = env.step(actions, demand=6 + epoch)
        market = transition.market_result
        reconciliation_error = (
            market.total_user_utility
            + market.total_provider_profit
            - market.total_welfare
        )
        epochs.append(
            {
                "epoch": epoch,
                "demand": 6 + epoch,
                "quotes": {provider: action.quote for provider, action in actions.items()},
                "provider_profit": transition.rewards,
                "user_utility": market.total_user_utility,
                "social_welfare": market.total_welfare,
                "reconciliation_error": reconciliation_error,
                "done": all(transition.terminations.values()),
            }
        )
    return {
        "seed": seed,
        "horizon": horizon,
        "agents": list(env.possible_agents),
        "router": "inverse_price",
        "epochs": epochs,
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, sort_keys=True))
