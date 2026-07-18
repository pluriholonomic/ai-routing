"""Registered simulation experiments (E-SIM series).

E-SIM1 — species-world validation (the gate for everything downstream):
fitted behavioral species x inverse-square router x AR(1) replay-shaped
demand, top calibrated model markets, multi-seed. The run PASSES when
`moments.moment_distance` against the pre-registered targets
(docs/simulation-moments-preregistration.md) satisfies:
  distance <= 0.04, no weight-2 moment off by > 35%, and the flow-elasticity
  sign/order gates hold.

Usage:
  uv run python -m orcap.market_env.experiments_sim --experiment E-SIM1
  ... --seeds 20 --epochs 56 --burn-in 7 [--bundle <rev>]

Outputs: output/market_env/esim1/<run_id>/{results.json, manifest.json}.

Downstream experiments (E-SIM2 learner substitution, E-SIM3 router
temperature sweep, E-SIM4 cut-penalty counterfactual) refuse to run until a
passing E-SIM1 manifest exists for the same bundle rev.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import moments
from .calibration import DEFAULT_OUT as CAL_OUT
from .calibration import fit as fit_bundle
from .calibration import load as load_bundle
from .kernel import MarketKernel
from .routers import InversePriceRouter
from .strategies import StaticStrategy
from .strategies_species import species_strategy
from .types import ProviderAction, ProviderSpec, Workload

log = logging.getLogger(__name__)

OUT = Path("output/market_env")
BASE_DEMAND = 200
END_USER_ELASTICITY = -0.05
DISTANCE_PASS = 0.04
W2_MAX_REL_ERR = 0.35


@dataclass
class AnchorWalkStrategy:
    """The model author's exogenous repricing process: a rare multiplicative
    random walk (hazard = observed author cadence). Anchor moves are what
    adopters follow and what generates within-pair price variation."""

    initial: float
    hazard: float = 0.03
    step: float = 0.05
    seed: int = 0
    _rng: np.random.Generator = field(init=False, repr=False)
    _current: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        self._current = self.initial

    def act(self, spec, public_quotes) -> ProviderAction:
        del spec, public_quotes
        if self._rng.random() < self.hazard:
            self._current *= float(np.exp(self._rng.choice([-1, 1]) * self.step))
        return ProviderAction(self._current)


def _marginal_cost(tier: str, price: float, min_price: float, cost_cfg: dict) -> float:
    owned = set(cost_cfg.get("owned_tiers", ())) | {"funded_neocloud"}
    lo, hi = cost_cfg.get("owned_capacity_cost_band_frac_of_min_price", [0.05, 0.25])
    if tier in owned or tier == "unknown":
        return float(min_price * (lo + hi) / 2)
    band = cost_cfg.get("spot_cost_per_mtok_band") or {}
    spot = band.get("tok_per_gpu_hr_3M")
    mc = float(spot) if spot else float(min_price * hi)
    return float(np.clip(mc, min_price * lo, price * 0.8))


def build_market(bundle: dict, model_id: str, seed: int, author_hazard: float = 0.02):
    m = bundle["markets"][model_id]
    provs = m["providers"]
    anchor_price = float(m["anchor_price"])
    authors = {p for p, v in provs.items() if v["is_author"]}
    anchor_provider = min(
        (p for p in authors), key=lambda p: provs[p]["price"], default=None
    )
    if anchor_provider is None:
        raise ValueError(f"market {model_id} has no author provider")
    min_price = min(v["price"] for v in provs.values())
    tiers = bundle["cost"].get("provider_tiers", {})
    specs, strategies, classes = {}, {}, {}
    for i, (name, v) in enumerate(sorted(provs.items())):
        price = float(v["price"])
        cls = v["anchor_class"]
        classes[name] = cls
        mc = _marginal_cost(tiers.get(name, "unknown"), price, min_price, bundle["cost"])
        specs[name] = ProviderSpec(
            provider=name,
            marginal_cost=mc,
            physical_capacity=BASE_DEMAND * 4,
        )
        pseed = seed * 1000 + i
        if v["is_author"]:
            if name == anchor_provider:
                strategies[name] = AnchorWalkStrategy(price, hazard=author_hazard, seed=pseed)
            else:
                strategies[name] = StaticStrategy(price)
        elif cls in bundle["species"]:
            margin = float(np.log(price / anchor_price)) if price > 0 else 0.0
            strategies[name] = species_strategy(
                cls, bundle["species"], anchor_provider,
                margin_log=margin if cls in ("below_static", "above") else None,
                seed=pseed,
            )
        else:
            strategies[name] = StaticStrategy(price)
    workload = Workload(
        name="short_chat", input_tokens=1000, output_tokens=256,
        delivered_value=max(v["price"] for v in provs.values()) * 3,
    )
    kernel = MarketKernel(
        tuple(specs.values()), workload, InversePriceRouter(exponent=2.0), seed=seed
    )
    return kernel, specs, strategies, anchor_provider, classes, authors


def run_market(bundle: dict, model_id: str, seed: int, epochs: int, burn_in: int,
               author_hazard: float = 0.02) -> pd.DataFrame:
    kernel, specs, strategies, anchor_provider, classes, authors = build_market(
        bundle, model_id, seed, author_hazard
    )
    rng = np.random.default_rng(seed * 7919 + hash(model_id) % 10_000)
    ar1 = bundle["demand"].get("ar1_median") or 0.5
    sigma = bundle["demand"].get("sigma_dlog_median") or 0.3
    p_anchor0 = bundle["markets"][model_id]["anchor_price"]
    quotes = {p: s.act(specs[p], {anchor_provider: p_anchor0}).quote
              for p, s in strategies.items()}
    p0 = float(np.median(list(quotes.values())))
    log_dev = 0.0
    results, anchor_prices = [], []
    for _t in range(epochs):
        actions = {p: s.act(specs[p], dict(quotes)) for p, s in strategies.items()}
        quotes = {p: a.quote for p, a in actions.items()}
        anchor_prices.append(quotes[anchor_provider])
        log_dev = ar1 * log_dev + sigma * rng.standard_normal()
        p_med = float(np.median(list(quotes.values())))
        demand = int(round(
            BASE_DEMAND * np.exp(log_dev) * (p_med / p0) ** END_USER_ELASTICITY
        ))
        results.append(kernel.step(actions, demand=max(demand, 1)))
    traj = moments.trajectory_from_epoch_results(
        results, model_id, classes, anchor_prices, authors
    )
    return traj[traj.epoch >= burn_in]


def run_esim1(bundle_rev: str | None, seeds: int, epochs: int, burn_in: int) -> dict:
    if bundle_rev is None:
        revs = sorted(CAL_OUT.glob("*/bundle.json"))
        bundle = json.loads(revs[-1].read_text()) if revs else None
        if bundle is None:
            bundle = json.loads(json.dumps(fit_bundle().__dict__, default=list))
    else:
        bundle = load_bundle(bundle_rev)
    markets = list(bundle["markets"])
    targets, author_hazard = moments.conditional_targets(markets, bundle["train_dates"])
    log.info("market-conditional targets: %s | author cadence %.4f",
             {k: v[0] for k, v in targets.items()}, author_hazard)
    per_seed = []
    for seed in range(seeds):
        trajs = [run_market(bundle, m, seed, epochs, burn_in, author_hazard)
                 for m in markets]
        mom = moments.compute_moments(pd.concat(trajs, ignore_index=True))
        per_seed.append(mom)
        log.info("seed %d distance %.4f", seed,
                 moments.moment_distance(mom, targets)["distance"])
    keys = sorted({k for m in per_seed for k in m if m[k] is not None})
    mean_moments = {
        k: float(np.mean([m[k] for m in per_seed if m.get(k) is not None]))
        for k in keys
    }
    sd_moments = {
        k: float(np.std([m[k] for m in per_seed if m.get(k) is not None]))
        for k in keys
    }
    score = moments.moment_distance(mean_moments, targets)
    w2_ok = all(
        abs(score["relative_errors"].get(k) or 0) <= W2_MAX_REL_ERR
        for k, (_, w) in targets.items() if w >= 2
    )
    gates = score["holdout_gates"]
    passed = (
        score["distance"] <= DISTANCE_PASS
        and w2_ok
        and gates.get("flow_elasticity_sign", False)
        and gates.get("flow_elasticity_order", False)
    )
    return {
        "experiment": "E-SIM1",
        "bundle_rev": bundle["rev"],
        "markets": markets,
        "seeds": seeds,
        "epochs": epochs,
        "burn_in": burn_in,
        "targets_market_conditional": {k: v[0] for k, v in targets.items()},
        "author_hazard": round(author_hazard, 4),
        "mean_moments": {k: round(v, 4) for k, v in mean_moments.items()},
        "sd_moments": {k: round(v, 4) for k, v in sd_moments.items()},
        "score": score,
        "weight2_within_35pct": w2_ok,
        "passed": bool(passed),
    }


def _write_run(result: dict, name: str) -> Path:
    rid = hashlib.blake2b(
        json.dumps(result, sort_keys=True, default=str).encode(), digest_size=5
    ).hexdigest()
    d = OUT / name / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps(result, indent=1, default=str))
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        commit = "unknown"
    (d / "manifest.json").write_text(json.dumps({
        "run_id": rid, "experiment": result.get("experiment"), "commit": commit,
        "bundle_rev": result.get("bundle_rev"), "seeds": result.get("seeds"),
    }, indent=1))
    return d


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="E-SIM1")
    ap.add_argument("--bundle", default=None)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--epochs", type=int, default=56)
    ap.add_argument("--burn-in", type=int, default=7)
    args = ap.parse_args()
    if args.experiment != "E-SIM1":
        raise SystemExit("only E-SIM1 is implemented; E-SIM2..4 unlock on a pass")
    result = run_esim1(args.bundle, args.seeds, args.epochs, args.burn_in)
    d = _write_run(result, "esim1")
    print(json.dumps(result, indent=1, default=str))
    print(f"run dir: {d}")


if __name__ == "__main__":
    main()
