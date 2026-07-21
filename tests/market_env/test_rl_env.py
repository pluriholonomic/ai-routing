from __future__ import annotations

import pytest

from orcap.market_env.kernel import MarketKernel
from orcap.market_env.rl_env import StrategicRoutingParallelEnv
from orcap.market_env.routers import InversePriceRouter
from orcap.market_env.types import ProviderAction, ProviderSpec, Workload


def _environment(seed: int = 7) -> StrategicRoutingParallelEnv:
    providers = (
        ProviderSpec(
            "owned",
            marginal_cost=0.2,
            physical_capacity=3,
            reliability=0.9,
        ),
        ProviderSpec(
            "spot",
            marginal_cost=0.4,
            physical_capacity=3,
            reliability=0.8,
        ),
    )
    workload = Workload(
        "test",
        input_tokens=10,
        output_tokens=2,
        delivered_value=2.0,
        failure_loss=1.0,
        max_attempts=2,
    )
    kernel = MarketKernel(
        providers,
        workload,
        InversePriceRouter(2.0),
        seed=seed,
    )
    return StrategicRoutingParallelEnv(kernel, horizon_epochs=2)


def test_parallel_api_hides_rival_private_technology_and_reconciles_rewards():
    env = _environment()
    initial = env.reset(seed=11)
    assert set(initial) == {"owned", "spot"}
    assert initial["owned"].public_quotes == ()
    assert not hasattr(initial["owned"], "marginal_cost")
    assert not hasattr(initial["owned"], "physical_capacity")

    actions = {"owned": ProviderAction(0.8), "spot": ProviderAction(1.0)}
    transition = env.step(actions, demand=4)
    assert sum(transition.rewards.values()) == pytest.approx(
        transition.market_result.total_provider_profit
    )
    assert transition.observations["owned"].own_profit == pytest.approx(
        transition.rewards["owned"]
    )
    assert transition.observations["owned"].public_quotes == (
        ("owned", 0.8),
        ("spot", 1.0),
    )
    assert not any(transition.terminations.values())


def test_reset_replays_exact_transition_and_horizon_terminates():
    env = _environment()
    actions = {"owned": ProviderAction(0.8), "spot": ProviderAction(1.0)}
    env.reset(seed=29)
    first = env.step(actions, demand=5).market_result
    final = env.step(actions, demand=5)
    assert all(final.terminations.values())
    assert env.agents == ()
    with pytest.raises(RuntimeError):
        env.step(actions, demand=1)

    env.reset(seed=29)
    replay = env.step(actions, demand=5).market_result
    assert replay == first


def test_parallel_api_rejects_invalid_horizon():
    with pytest.raises(ValueError):
        StrategicRoutingParallelEnv(_environment().kernel, horizon_epochs=0)
