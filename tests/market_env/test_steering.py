from random import Random

from orcap.market_env.routers_steering import CutPenaltyRouter
from orcap.market_env.types import ProviderAction, ProviderSpec

SPECS = {p: ProviderSpec(provider=p, marginal_cost=0.2, physical_capacity=10)
         for p in ("a", "b")}


def test_cut_penalty_downweights_recent_cutter():
    r = CutPenaltyRouter(2.0, theta=0.17, memory=7)
    r.advance({"a": 1.0, "b": 1.0})
    acts = {"a": ProviderAction(0.8), "b": ProviderAction(1.0)}  # a cut
    probs = r.probabilities(SPECS, acts)
    base = CutPenaltyRouter(2.0, theta=1.0, memory=7)
    base.advance({"a": 1.0, "b": 1.0})
    probs_nopen = base.probabilities(SPECS, acts)
    assert probs["a"] < probs_nopen["a"]
    assert abs(sum(probs.values()) - 1) < 1e-9


def test_cut_penalty_expires_with_memory():
    r = CutPenaltyRouter(2.0, theta=0.17, memory=2)
    r.advance({"a": 1.0, "b": 1.0})
    acts = {"a": ProviderAction(0.8), "b": ProviderAction(1.0)}
    for _ in range(3):
        r.advance({p: a.quote for p, a in acts.items()})
    probs = r.probabilities(SPECS, acts)
    # after the cut ages out of memory, weights revert to pure inverse-square
    w_a, w_b = 0.8 ** -2, 1.0 ** -2
    assert abs(probs["a"] - w_a / (w_a + w_b)) < 1e-9


def test_ordered_attempts_covers_all_eligible():
    r = CutPenaltyRouter(2.0)
    acts = {"a": ProviderAction(0.8), "b": ProviderAction(1.0)}
    order = r.ordered_attempts(SPECS, acts, Random(1))
    assert sorted(order) == ["a", "b"]
