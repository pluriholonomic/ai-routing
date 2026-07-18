"""Mechanism-comparison experiments (E-SIM6/7): objective frontier and quality.

E-MECH1 (formerly E-SIM6; renamed to avoid collision with the
parallel-session E-SIM5-9 series) — mechanism frontier with heterogeneous provider types.
  Two-type market (owned-capacity c_L=0.10 x2, spot-dependent c_S=0.50 x3,
  the calibrated cost-band endpoints) with Q-learning providers under
  candidate mechanisms:
    a in {1, 2, 4, 6.25 (= adaptive a*(n) at Lerner target 0.2), 32 (~WTA)},
    uniform (a=0), and a=2 + cut-penalty (the deployed pair).
  Metrics at the learned profile: flow-weighted price (platform revenue
  proxy), allocative welfare v - sum s_i c_i, spot-type flow share and
  profit (viability), and theory-Nash comparators.

E-MECH2 — quality game (adverse selection and its repair).
  Symmetric n=3, each agent chooses (price, quality in {hi, lo}); lo saves
  Delta = 0.08 of cost and damages delivered quality by d = 0.2. Router
  weight w = q^b * p^(-a). Theory threshold: b* solves
  (1/n)(p-c) = [(1-d)^b/((1-d)^b + n-1)](p-c+Delta) — b* = 0.63 at the
  baseline. Arms b in {0, 0.5, 1, 2}: measure the learned hi-quality share.
  b=0 (the deployed, quality-blind rule) predicts full shading; b >= 1
  predicts full quality.

Both use expected-allocation rewards (exact under non-binding capacity) and
the same tabular Q machinery as E-SIM2/3/4. Gated on the passing E-SIM1.
"""

from __future__ import annotations

import argparse
import json
import logging

import numpy as np

from .experiments_sim import _require_esim1_pass, _write_run
from .routers import InversePriceRouter, RandomRouter
from .routers_steering import CutPenaltyRouter
from .strategies_qlearn import TabularQAgent, expected_profits, price_grid

log = logging.getLogger(__name__)

V_REQ = 2.0          # delivered value per request (welfare accounting)
C_OWNED, C_SPOT = 0.10, 0.50
N_OWNED, N_SPOT = 2, 3
LERNER_TARGET = 0.2


def adaptive_exponent(n: int, lerner: float = LERNER_TARGET) -> float:
    """a*(n) = n / (lerner * (n-1)): holds symmetric equilibrium Lerner at
    the target across market thickness (from Theorem 1's FOC)."""
    return n / (lerner * (n - 1))


def _train_two_type(router, seeds: int, train_epochs: int) -> list[dict]:
    names = [f"L{i}" for i in range(N_OWNED)] + [f"S{i}" for i in range(N_SPOT)]
    costs = {p: (C_OWNED if p.startswith("L") else C_SPOT) for p in names}
    grid = price_grid(1.0)
    rows = []
    for seed in range(seeds):
        agents = {p: TabularQAgent(grid, seed=seed * 100 + i)
                  for i, p in enumerate(names)}
        idx = {p: len(grid) // 2 for p in names}
        for _t in range(train_epochs):
            states, acts = {}, {}
            for p in names:
                rival = min(idx[q] for q in names if q != p)
                states[p] = agents[p].state_index(idx[p], rival)
                acts[p] = agents[p].act_index(states[p])
            prices = {p: float(grid[acts[p]]) for p in names}
            pis = expected_profits(prices, costs, router, 1.0)
            if hasattr(router, "advance"):
                router.advance(prices)
            for p in names:
                rival2 = min(acts[q] for q in names if q != p)
                s2 = agents[p].state_index(acts[p], rival2)
                agents[p].update(states[p], acts[p], pis[p], s2)
            idx = acts
        # greedy convergence
        for _t in range(100):
            for p in names:
                rival = min(idx[q] for q in names if q != p)
                idx[p] = agents[p].greedy(agents[p].state_index(idx[p], rival))
        prices = {p: float(grid[idx[p]]) for p in names}
        pis = expected_profits(prices, costs, router, 1.0)
        specs_shares = _shares(prices, router, costs)
        flow_price = sum(specs_shares[p] * prices[p] for p in names)
        alloc_cost = sum(specs_shares[p] * costs[p] for p in names)
        rows.append({
            "seed": seed,
            "prices": {p: round(v, 3) for p, v in prices.items()},
            "flow_price": round(flow_price, 4),
            "welfare": round(V_REQ - alloc_cost, 4),
            "spot_flow_share": round(sum(specs_shares[p] for p in names
                                         if p.startswith("S")), 4),
            "spot_profit": round(sum(pis[p] for p in names if p.startswith("S")), 5),
        })
    return rows


def _shares(prices, router, costs):
    from .types import ProviderAction, ProviderSpec
    specs = {p: ProviderSpec(provider=p, marginal_cost=costs[p], physical_capacity=1)
             for p in prices}
    actions = {p: ProviderAction(v) for p, v in prices.items()}
    return router.probabilities(specs, actions)


def run_esim6(seeds: int = 5, train_epochs: int = 300_000) -> dict:
    _require_esim1_pass()
    n = N_OWNED + N_SPOT
    arms = {
        "uniform": RandomRouter(),
        "a1": InversePriceRouter(1.0),
        "a2_deployed": InversePriceRouter(2.0),
        "a2_cutpenalty_deployed_pair": CutPenaltyRouter(2.0, theta=0.17, memory=7),
        "a4": InversePriceRouter(4.0),
        "a_adaptive_6.25": InversePriceRouter(adaptive_exponent(n)),
        "a32_wta": InversePriceRouter(32.0),
    }
    out = {}
    for arm, router in arms.items():
        rows = _train_two_type(router, seeds, train_epochs)
        out[arm] = {
            "per_seed": rows,
            "mean_flow_price": round(float(np.mean([r["flow_price"] for r in rows])), 4),
            "mean_welfare": round(float(np.mean([r["welfare"] for r in rows])), 4),
            "mean_spot_share": round(float(np.mean([r["spot_flow_share"] for r in rows])), 4),
            "mean_spot_profit": round(float(np.mean([r["spot_profit"] for r in rows])), 5),
        }
        log.info("%s: %s", arm, {k: v for k, v in out[arm].items() if k != "per_seed"})
    result = {"experiment": "E-MECH1", "arms": out, "seeds": seeds,
              "config": {"v": V_REQ, "c_owned": C_OWNED, "c_spot": C_SPOT,
                         "n_owned": N_OWNED, "n_spot": N_SPOT,
                         "adaptive_exponent": adaptive_exponent(n)}}
    _write_run(result, "emech1")
    return result


class QualityQAgent(TabularQAgent):
    """Q-learner over the widened price x quality action space."""

    def __post_init__(self) -> None:
        n = len(self.grid)
        self._rng = np.random.default_rng(self.seed)
        self.Q = np.full((n * n, n * 2), float(self.q_init))

    def act_index(self, state: int) -> int:
        eps = float(np.exp(-self.beta * self.t))
        self.t += 1
        if self._rng.random() < eps:
            return int(self._rng.integers(self.Q.shape[1]))
        row = self.Q[state]
        return int(self._rng.choice(np.flatnonzero(row == row.max())))


class QualityRouter(InversePriceRouter):
    """w = q^b * p^(-a); quality per provider is set via set_quality()."""

    def __init__(self, exponent: float = 2.0, quality_exponent: float = 0.0) -> None:
        super().__init__(exponent=exponent)
        self.b = float(quality_exponent)
        self.quality: dict[str, float] = {}

    def set_quality(self, quality: dict[str, float]) -> None:
        self.quality = dict(quality)

    def probabilities(self, specs, actions):
        base = super().probabilities(specs, actions)
        if not base or not self.quality:
            return base
        weights = {p: w * (self.quality.get(p, 1.0) ** self.b) for p, w in base.items()}
        total = sum(weights.values())
        return {p: w / total for p, w in weights.items()} if total > 0 else base


def run_esim7(seeds: int = 5, train_epochs: int = 300_000,
              d: float = 0.2, delta: float = 0.08) -> dict:
    _require_esim1_pass()
    n, c = 3, 0.2
    grid = price_grid(1.0)
    out = {}
    for b in (0.0, 0.5, 1.0, 2.0):
        rows = []
        for seed in range(seeds):
            router = QualityRouter(2.0, quality_exponent=b)
            names = [f"a{i}" for i in range(n)]
            # action = price index * 2 + quality bit (0=lo, 1=hi)
            agents = {p: QualityQAgent(grid, beta=1e-5, seed=seed * 100 + i)
                      for i, p in enumerate(names)}
            idx = {p: len(grid) // 2 for p in names}
            qual = {p: 1 for p in names}
            for _t in range(train_epochs):
                states, acts = {}, {}
                for p in names:
                    rival = min(idx[q] for q in names if q != p)
                    states[p] = agents[p].state_index(idx[p], rival)
                    a_full = agents[p].act_index(states[p])
                    acts[p] = a_full
                prices = {p: float(grid[acts[p] // 2]) for p in names}
                qual = {p: acts[p] % 2 for p in names}
                router.set_quality({p: (1.0 if qual[p] else 1.0 - d) for p in names})
                costs = {p: (c if qual[p] else c - delta) for p in names}
                pis = expected_profits(prices, costs, router, 1.0)
                for p in names:
                    rival2 = min(acts[q] // 2 for q in names if q != p)
                    s2 = agents[p].state_index(acts[p] // 2, rival2)
                    agents[p].update(states[p], acts[p], pis[p], s2)
                idx = {p: acts[p] // 2 for p in names}
            hi_share = float(np.mean([qual[p] for p in names]))
            rows.append({"seed": seed, "hi_quality_share": hi_share,
                         "prices": {p: round(float(grid[idx[p]]), 3) for p in names}})
        out[f"b{b}"] = {
            "per_seed": rows,
            "mean_hi_quality_share": round(float(np.mean(
                [r["hi_quality_share"] for r in rows])), 3),
        }
        log.info("b=%s: hi share %.3f", b, out[f"b{b}"]["mean_hi_quality_share"])
    result = {"experiment": "E-MECH2", "arms": out, "seeds": seeds,
              "config": {"n": n, "c": c, "d": d, "delta": delta,
                         "b_star_theory": 0.63}}
    _write_run(result, "emech2")
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", required=True, choices=["E-MECH1", "E-MECH2"])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=300_000)
    args = ap.parse_args()
    fn = run_esim6 if args.experiment == "E-MECH1" else run_esim7
    print(json.dumps(fn(seeds=args.seeds, train_epochs=args.epochs),
                     indent=1, default=str))


if __name__ == "__main__":
    main()
