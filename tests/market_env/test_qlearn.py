import numpy as np
import pytest

from orcap.market_env.routers import InversePriceRouter, LowestCostRouter
from orcap.market_env.strategies_qlearn import (
    expected_profits,
    monopoly_profit,
    nash_profit,
    price_grid,
    train_symmetric,
)


def test_price_grid_contains_anchor_exactly():
    g = price_grid(1.0)
    assert 1.0 in g
    assert len(g) == 15
    assert g[0] < 0.5 < 1.5 < g[-1]


def test_expected_profits_sum_to_margin_times_demand():
    r = InversePriceRouter(2.0)
    pis = expected_profits({"a": 1.0, "b": 1.0}, {"a": 0.2, "b": 0.2}, r, demand=10)
    assert abs(pis["a"] - pis["b"]) < 1e-12
    assert abs(sum(pis.values()) - 10 * 0.8) < 1e-9


def test_bertrand_wta_nash_is_one_tick_above_cost():
    g = price_grid(1.0)
    r = LowestCostRouter()
    pi_n = nash_profit(g, mc=0.2, router=r, demand=1.0)
    # winner-take-all: undercutting drives price to the lowest grid point
    # above cost; per-agent expected profit is tiny
    ticks_above = g[g > 0.2]
    assert pi_n <= 1.0 * (ticks_above[1] - 0.2) / 2 + 1e-9


def test_inverse_square_duopoly_knife_edge():
    """FOC: symmetric Nash p* = c*a(n-1)/(a(n-1)-n). At a=2, n=2 the
    denominator is 0 -- best response is unbounded, so Nash = cartel = grid
    max. OpenRouter's documented exponent sits exactly at the two-provider
    knife edge; price discipline requires n >= 3."""
    g = price_grid(1.0)
    r = InversePriceRouter(2.0)
    pi_n = nash_profit(g, mc=0.2, router=r, demand=1.0, n_agents=2)
    pi_m = monopoly_profit(g, mc=0.2, router=r, demand=1.0, n_agents=2)
    assert pi_n == pytest.approx(pi_m) == pytest.approx((g[-1] - 0.2) / 2)


def test_monopoly_exceeds_nash_with_three_providers():
    # a=2, n=3: interior Nash p* = 4c = 0.8 < grid max -> collusion gap opens
    g = price_grid(1.0)
    r = InversePriceRouter(2.0)
    pi_n = nash_profit(g, mc=0.2, router=r, demand=1.0, n_agents=3)
    pi_m = monopoly_profit(g, mc=0.2, router=r, demand=1.0, n_agents=3)
    assert pi_m > pi_n > 0
    p_nash_per_agent = pi_n * 3 + 0.2  # invert pi = (p-c)/3
    assert 0.55 < p_nash_per_agent < 1.1  # near the interior p*=0.8 on the grid


def test_single_agent_learns_monopoly_price():
    r = InversePriceRouter(2.0)
    out = train_symmetric(r, n_agents=1, mc=0.2, max_epochs=60_000,
                          stable_window=10_000, seed=3)
    assert out["final_prices"]["a0"] == pytest.approx(float(out["grid"][-1]))


@pytest.mark.slow
def test_calvano_smoke_supra_competitive():
    # n=3: the collusion gap exists (pi_M > pi_N); at n=2 the knife edge
    # makes Delta undefined
    r = InversePriceRouter(2.0)
    out = train_symmetric(r, n_agents=3, mc=0.2, max_epochs=400_000,
                          stable_window=50_000, seed=11)
    assert out["calvano_delta"] is not None
    assert out["calvano_delta"] > 0.05
