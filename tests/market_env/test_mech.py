import numpy as np

from orcap.market_env.experiments_mech import (
    QualityRouter,
    adaptive_exponent,
)
from orcap.market_env.strategies_qlearn import expected_profits
from orcap.market_env.types import ProviderAction, ProviderSpec


def test_adaptive_exponent_pins_lerner():
    # a*(n) = n/(l*(n-1)); check the induced symmetric equilibrium Lerner
    for n in (2, 3, 5, 10):
        a = adaptive_exponent(n, lerner=0.2)
        # symmetric FOC: (p-c)/p = 1/(a(1-1/n)) should equal the target
        assert abs(1 / (a * (1 - 1 / n)) - 0.2) < 1e-12


def test_quality_router_reweights_and_normalizes():
    r = QualityRouter(2.0, quality_exponent=1.0)
    specs = {p: ProviderSpec(provider=p, marginal_cost=0.2, physical_capacity=1)
             for p in ("hi", "lo")}
    acts = {p: ProviderAction(1.0) for p in specs}
    r.set_quality({"hi": 1.0, "lo": 0.8})
    probs = r.probabilities(specs, acts)
    assert abs(sum(probs.values()) - 1) < 1e-12
    assert probs["hi"] > probs["lo"]
    assert abs(probs["lo"] / probs["hi"] - 0.8) < 1e-9


def test_quality_blind_makes_shading_dominant():
    # same price, shading saves cost, b=0: profit strictly higher for lo
    r = QualityRouter(2.0, quality_exponent=0.0)
    r.set_quality({"a0": 0.8, "a1": 1.0, "a2": 1.0})
    pis = expected_profits({"a0": 1.0, "a1": 1.0, "a2": 1.0},
                           {"a0": 0.12, "a1": 0.2, "a2": 0.2}, r, 1.0)
    assert pis["a0"] > pis["a1"]


def test_quality_weight_above_threshold_deters_shading():
    # b=2 > b*=0.63: deviator to lo loses despite cost saving
    n, d, delta, p, c = 3, 0.2, 0.08, 1.0, 0.2
    b = 2.0
    k = (1 - d) ** b
    s_hi, s_lo = 1 / n, k / (k + n - 1)
    assert s_hi * (p - c) > s_lo * (p - c + delta)
