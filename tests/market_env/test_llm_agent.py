import json

import httpx
import pytest

from orcap.market_env.diagnostics_collusion import cut_response, deviation_audit
from orcap.market_env.routers import InversePriceRouter
from orcap.market_env.strategies_llm import LLMPricingAgent, _extract_price
from orcap.market_env.strategies_qlearn import price_grid
from orcap.market_env.types import ProviderSpec

SPEC = ProviderSpec(provider="Me", marginal_cost=0.2, physical_capacity=10)


def mock_client(price_text: str, cost: float = 0.001) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": price_text}}],
            "usage": {"cost": cost},
        })
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extract_price():
    assert _extract_price("I will undercut.\nPRICE: 0.85") == 0.85
    assert _extract_price("PRICE: $1.20") == 1.20
    assert _extract_price("no idea") is None


def test_llm_agent_prices_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("orcap.market_env.strategies_llm.CACHE_DIR", tmp_path)
    a = LLMPricingAgent("Me", 0.2, client=mock_client("cut a bit\nPRICE: 0.9"))
    q1 = a.act(SPEC, {"Me": 1.0, "R1": 1.0, "R2": 1.1})
    assert q1.quote == 0.9
    assert a.calls == 1
    # the state key includes a 3-epoch history window: once prices and
    # profits stabilize the window saturates and states repeat -> cache hits
    a2_quotes = {"Me": 0.9, "R1": 1.0, "R2": 1.1}
    for _ in range(6):
        a.observe(0.5)
        a.act(SPEC, a2_quotes)
    assert a.cache_hits >= 1


def test_llm_agent_budget_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr("orcap.market_env.strategies_llm.CACHE_DIR", tmp_path)
    a = LLMPricingAgent("Me", 0.2, budget_usd=0.0015,
                        client=mock_client("PRICE: 0.9", cost=0.001))
    a.act(SPEC, {"Me": 1.0, "R1": 1.0})
    a.observe(0.1)
    a.act(SPEC, {"Me": 0.9, "R1": 0.8})
    a.observe(0.1)
    assert a.spent_usd >= 0.0015
    # further novel states do not call the API
    calls_before = a.calls
    a.act(SPEC, {"Me": 0.9, "R1": 0.55})
    assert a.calls == calls_before
    assert a.exhausted


def test_llm_agent_floor_at_cost(tmp_path, monkeypatch):
    monkeypatch.setattr("orcap.market_env.strategies_llm.CACHE_DIR", tmp_path)
    a = LLMPricingAgent("Me", 0.5, client=mock_client("PRICE: 0.01"))
    q = a.act(SPEC, {"Me": 1.0, "R1": 1.0})
    assert q.quote >= 0.5


def test_cut_response_classifies_matcher():
    def matcher(quotes):
        rivals = [v for k, v in quotes.items() if k != "Me"]
        return min(rivals) * 0.99
    out = cut_response(matcher, {"Me": 1.0, "R": 1.0}, "Me", "R")
    assert out["verdict"] == "match"


def test_cut_response_classifies_ignorer():
    out = cut_response(lambda q: 1.0, {"Me": 1.0, "R": 1.0}, "Me", "R")
    assert out["verdict"] == "ignore"


def test_deviation_audit_inverse_square_barely_disciplines():
    # under 1/p^2 routing at n=3, even the cartel ceiling is within ~2% of
    # unilateral stability -- the router barely disciplines (finding worth
    # its own test); the gain must still be positive
    g = price_grid(1.0)
    r = InversePriceRouter(2.0)
    prices = {"a": float(g[-1]), "b": float(g[-1]), "c": float(g[-1])}
    out = deviation_audit(prices, dict.fromkeys(prices, 0.2), r, 1.0, g)
    assert 0 < out["max_gain_rel_to_mean_profit"] < 0.05


def test_deviation_audit_flags_wta_cartel():
    from orcap.market_env.routers import LowestCostRouter

    g = price_grid(1.0)
    prices = {"a": float(g[-1]), "b": float(g[-1]), "c": float(g[-1])}
    out = deviation_audit(prices, dict.fromkeys(prices, 0.2), LowestCostRouter(), 1.0, g)
    # winner-take-all: undercutting grabs the whole market -- huge gain
    assert not out["equilibrium_consistent"]
