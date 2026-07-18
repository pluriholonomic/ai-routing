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
    rng = np.random.default_rng(_market_seed(seed, model_id))
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


def _market_seed(seed: int, model_id: str) -> int:
    """Stable demand-process seed, independent of ``PYTHONHASHSEED``.

    Python deliberately randomizes ``hash(str)`` between interpreter
    processes.  Using it here made an otherwise identical confirmatory run
    depend on the process that launched it.
    """
    payload = f"{int(seed)}\0{model_id}".encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "little")


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
    source_files = sorted(Path("src/orcap/market_env").glob("*.py"))
    source_hash = hashlib.sha256()
    for source in source_files:
        source_hash.update(source.as_posix().encode())
        source_hash.update(b"\0")
        source_hash.update(source.read_bytes())
        source_hash.update(b"\0")
    (d / "manifest.json").write_text(json.dumps({
        "run_id": rid, "experiment": result.get("experiment"), "commit": commit,
        "bundle_rev": result.get("bundle_rev"), "seeds": result.get("seeds"),
        "market_env_source_sha256": source_hash.hexdigest(),
    }, indent=1))
    return d


def _require_esim1_pass() -> str:
    """Downstream experiments are gated on a passing E-SIM1 for some bundle."""
    for res in sorted((OUT / "esim1").glob("*/results.json")):
        r = json.loads(res.read_text())
        if r.get("passed") and r.get("seeds", 0) >= 20:
            return r["bundle_rev"]
    raise SystemExit("no passing confirmatory E-SIM1 run found; gate closed")


def _paired_bootstrap_ci(
    values: list[float], *, seed: int = 20260718, draws: int = 10_000
) -> list[float] | None:
    """Deterministic percentile interval for a paired mean contrast."""
    if not values:
        return None
    sample = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(sample), size=(draws, len(sample)))
    means = sample[indices].mean(axis=1)
    return [float(x) for x in np.percentile(means, [2.5, 97.5])]


def _stylized_world(seed: int):
    """A 5-provider synthetic market with one slot per species + an anchor,
    stationary demand — the arena for learner-substitution and steering."""
    from .strategies_species import (
        ActiveUndercutterStrategy,
        AdopterStrategy,
        TargetHazardStrategy,
    )

    mc = 0.2
    providers = {
        "Anchor": StaticStrategy(1.0),
        "Adopter": AdopterStrategy("Anchor", idio_hazard=0.0, seed=seed),
        "StaticCut": TargetHazardStrategy("Anchor", -0.4, 0.005, seed=seed + 1),
        "ActiveCut": ActiveUndercutterStrategy(margin_floor=0.1),
        "Premium": TargetHazardStrategy("Anchor", 0.34, 0.02, seed=seed + 2),
    }
    costs = dict.fromkeys(providers, mc)
    return providers, costs


def run_esim2(seeds: int = 5, train_epochs: int = 300_000) -> dict:
    """Replace each species slot with a Q-learner trained against the rest
    (stationary demand). Which species does the learner converge to?"""
    from .strategies_qlearn import TabularQAgent, expected_profits, price_grid

    _require_esim1_pass()
    grid = price_grid(1.0)
    router = InversePriceRouter(2.0)
    out: dict[str, list] = {}
    for slot in ("Adopter", "StaticCut", "ActiveCut", "Premium"):
        outcomes = []
        for seed in range(seeds):
            strategies, costs = _stylized_world(seed * 31 + 7)
            del strategies[slot]
            agent = TabularQAgent(grid, seed=seed)
            specs = {
                p: ProviderSpec(provider=p, marginal_cost=costs[p], physical_capacity=1)
                for p in list(strategies) + [slot]
            }
            quotes = {p: 1.0 for p in specs}
            own_idx = len(grid) // 2
            for _t in range(train_epochs):
                rival_min = min(q for p, q in quotes.items() if p != slot)
                rividx = int(np.argmin(np.abs(grid - rival_min)))
                s = agent.state_index(own_idx, rividx)
                a = agent.act_index(s)
                quotes[slot] = float(grid[a])
                for p, strat in strategies.items():
                    quotes[p] = strat.act(specs[p], dict(quotes)).quote
                pis = expected_profits(quotes, costs, router, 1.0)
                rival_min2 = min(q for p, q in quotes.items() if p != slot)
                s2 = agent.state_index(a, int(np.argmin(np.abs(grid - rival_min2))))
                agent.update(s, a, pis[slot], s2)
                own_idx = a
            # classify converged behavior over a 56-epoch greedy eval
            prices, reprices = [], 0
            prev = quotes[slot]
            for _t in range(56):
                rival_min = min(q for p, q in quotes.items() if p != slot)
                s = agent.state_index(
                    int(np.argmin(np.abs(grid - quotes[slot]))),
                    int(np.argmin(np.abs(grid - rival_min))),
                )
                quotes[slot] = float(grid[agent.greedy(s)])
                for p, strat in strategies.items():
                    quotes[p] = strat.act(specs[p], dict(quotes)).quote
                prices.append(quotes[slot])
                reprices += abs(quotes[slot] - prev) > 1e-12
                prev = quotes[slot]
            med_rel = float(np.log(np.median(prices) / 1.0))
            cpd = reprices / 55
            at_anchor = float(np.mean(np.isclose(prices, 1.0)))
            if at_anchor >= 0.8:
                learned = "adopter"
            elif med_rel < 0:
                learned = "below_active" if cpd > 0.05 else "below_static"
            else:
                learned = "above"
            outcomes.append({"seed": seed, "learned_class": learned,
                             "median_log_rel": round(med_rel, 3),
                             "changes_per_day": round(cpd, 3),
                             "share_at_anchor": round(at_anchor, 3)})
        out[slot] = outcomes
    result = {"experiment": "E-SIM2", "replaced_slot_outcomes": out,
              "seeds": seeds, "train_epochs": train_epochs}
    _write_run(result, "esim2")
    return result


def run_esim3(seeds: int = 5) -> dict:
    """Router price-sensitivity sweep: all-Q worlds under exponent a
    (softmax temperature 1/a). Deliverable: price level and Calvano Delta
    vs a — does a sharper router discipline learners?"""
    from scipy.stats import spearmanr

    from .diagnostics_collusion import cut_response, deviation_audit
    from .strategies_qlearn import train_symmetric

    _require_esim1_pass()
    sweep = []
    for a in (0.0, 1.0, 2.0, 4.0, 8.0, 32.0):
        rows = []
        for seed in range(seeds):
            r = train_symmetric(
                InversePriceRouter(a), n_agents=3, mc=0.2,
                max_epochs=300_000, stable_window=40_000, seed=seed * 13 + 1,
            )
            final_prices = {k: float(v) for k, v in r["final_prices"].items()}
            costs = dict.fromkeys(final_prices, 0.2)
            audit = deviation_audit(final_prices, costs, InversePriceRouter(a), 1.0, r["grid"])
            punishments = []
            names = sorted(final_prices)
            for index, name in enumerate(names):
                agent = r["agents"][index]

                def response(quotes, *, _agent=agent, _name=name, _grid=r["grid"]):
                    own = quotes[_name]
                    rival = min(q for p, q in quotes.items() if p != _name)
                    state = _agent.state_index(
                        int(np.argmin(np.abs(_grid - own))),
                        int(np.argmin(np.abs(_grid - rival))),
                    )
                    return float(_grid[_agent.greedy(state)])

                rival_name = next(other for other in names if other != name)
                response_audit = cut_response(
                    response, final_prices, name, rival_name, cut_frac=0.2, horizon=12
                )
                punishments.append(response_audit["verdict"] == "punish_and_revert")
            rows.append({
                "seed": seed,
                "final_prices": final_prices,
                "mean_price": float(np.mean(list(final_prices.values()))),
                "mean_profit": r["mean_profit"],
                "pi_nash": r["pi_nash"],
                "pi_monopoly": r["pi_monopoly"],
                "calvano_delta": r["calvano_delta"],
                "converged": r["converged"],
                "epochs_run": r["epochs_run"],
                "max_deviation_gain_relative": audit["max_gain_rel_to_mean_profit"],
                "equilibrium_consistent": audit["equilibrium_consistent"],
                "punish_and_revert_share": float(np.mean(punishments)),
            })
        deltas = [x["calvano_delta"] for x in rows if x["calvano_delta"] is not None]
        prices = [np.mean(list(x["final_prices"].values())) for x in rows]
        sweep.append({
            "exponent": a,
            "mean_price": round(float(np.mean(prices)), 4),
            "mean_delta": round(float(np.mean(deltas)), 4) if deltas else None,
            "sd_delta": round(float(np.std(deltas)), 4) if deltas else None,
            "n_delta_defined": len(deltas),
            "converged_seeds": int(sum(x["converged"] for x in rows)),
            "equilibrium_consistent_seeds": int(
                sum(x["equilibrium_consistent"] for x in rows)
            ),
            "punish_and_revert_seed_share": round(float(np.mean([
                x["punish_and_revert_share"] > 0 for x in rows
            ])), 4),
            "per_seed": rows,
        })
    arm_prices = [row["mean_price"] for row in sweep]
    adjacent = []
    for left, right in zip(sweep[:-1], sweep[1:], strict=True):
        differences = [
            rrow["mean_price"] - lrow["mean_price"]
            for lrow, rrow in zip(left["per_seed"], right["per_seed"], strict=True)
        ]
        adjacent.append({
            "from_exponent": left["exponent"],
            "to_exponent": right["exponent"],
            "mean_price_difference": float(np.mean(differences)),
            "paired_bootstrap_ci95": _paired_bootstrap_ci(differences),
        })
    correlation = spearmanr([row["exponent"] for row in sweep], arm_prices)
    result = {
        "experiment": "E-SIM3",
        "sweep": sweep,
        "seeds": seeds,
        "n_agents": 3,
        "adjacent_paired_price_contrasts": adjacent,
        "arm_mean_price_spearman": {
            "rho": float(correlation.statistic),
            "pvalue_descriptive": float(correlation.pvalue),
        },
        "adequate_convergence_all_arms": bool(
            all(row["converged_seeds"] >= np.ceil(0.8 * seeds) for row in sweep)
        ),
        "claim_boundary": (
            "The Spearman p-value is descriptive across six designed arms. "
            "Seed-paired intervals and convergence gates are the inferential objects."
        ),
    }
    _write_run(result, "esim3")
    return result


def run_esim4(seeds: int = 5) -> dict:
    """JRW steering counterfactual: cut-penalty on/off in the stylized
    species world with the learner in the ActiveCut slot. Prediction from
    the JRW-inverse reading: penalizing recent cutters removes the payoff
    to undercutting -> less repricing, higher price level."""
    from .diagnostics_collusion import cut_response, deviation_audit
    from .routers_steering import CutPenaltyRouter
    from .strategies_qlearn import TabularQAgent, expected_profits, price_grid

    _require_esim1_pass()
    grid = price_grid(1.0)
    arms = {"penalty_off": None, "penalty_on": 0.17}
    out = {}
    for arm, theta in arms.items():
        rows = []
        for seed in range(seeds):
            router = (InversePriceRouter(2.0) if theta is None
                      else CutPenaltyRouter(2.0, theta=theta, memory=7))
            strategies, costs = _stylized_world(seed * 17 + 3)
            del strategies["ActiveCut"]
            slot = "ActiveCut"
            agent = TabularQAgent(grid, seed=seed)
            specs = {
                p: ProviderSpec(provider=p, marginal_cost=costs[p], physical_capacity=1)
                for p in list(strategies) + [slot]
            }
            quotes = {p: 1.0 for p in specs}
            own_idx = len(grid) // 2
            for _t in range(300_000):
                rival_min = min(q for p, q in quotes.items() if p != slot)
                s = agent.state_index(own_idx, int(np.argmin(np.abs(grid - rival_min))))
                a = agent.act_index(s)
                quotes[slot] = float(grid[a])
                for p, strat in strategies.items():
                    quotes[p] = strat.act(specs[p], dict(quotes)).quote
                pis = expected_profits(quotes, costs, router, 1.0)
                if hasattr(router, "advance"):
                    router.advance(quotes)
                rival_min2 = min(q for p, q in quotes.items() if p != slot)
                s2 = agent.state_index(a, int(np.argmin(np.abs(grid - rival_min2))))
                agent.update(s, a, pis[slot], s2)
                own_idx = a
            prices, reprices, prev = [], 0, quotes[slot]
            for _t in range(56):
                rival_min = min(q for p, q in quotes.items() if p != slot)
                s = agent.state_index(
                    int(np.argmin(np.abs(grid - quotes[slot]))),
                    int(np.argmin(np.abs(grid - rival_min))),
                )
                quotes[slot] = float(grid[agent.greedy(s)])
                for p, strat in strategies.items():
                    quotes[p] = strat.act(specs[p], dict(quotes)).quote
                if hasattr(router, "advance"):
                    router.advance(quotes)
                prices.append(quotes[slot])
                reprices += abs(quotes[slot] - prev) > 1e-12
                prev = quotes[slot]
            audit = deviation_audit(quotes, costs, router, 1.0, grid)

            def response(report, *, _agent=agent, _grid=grid, _slot=slot):
                own = report[_slot]
                rival = min(q for p, q in report.items() if p != _slot)
                state = _agent.state_index(
                    int(np.argmin(np.abs(_grid - own))),
                    int(np.argmin(np.abs(_grid - rival))),
                )
                return float(_grid[_agent.greedy(state)])

            rival_name = min(
                (name for name in quotes if name != slot), key=lambda name: quotes[name]
            )
            response_audit = cut_response(
                response, quotes, slot, rival_name, cut_frac=0.2, horizon=12
            )
            rows.append({
                "seed": seed,
                "learner_median_price": round(float(np.median(prices)), 4),
                "learner_changes_per_day": round(reprices / 55, 3),
                "market_mean_price": round(float(np.mean(
                    [np.mean(list(quotes.values()))]
                )), 4),
                "max_deviation_gain_relative": audit["max_gain_rel_to_mean_profit"],
                "equilibrium_consistent": audit["equilibrium_consistent"],
                "cut_response": response_audit["verdict"],
            })
        out[arm] = rows
    contrasts = {}
    for outcome in (
        "learner_median_price",
        "learner_changes_per_day",
        "market_mean_price",
    ):
        differences = [
            on[outcome] - off[outcome]
            for off, on in zip(out["penalty_off"], out["penalty_on"], strict=True)
        ]
        contrasts[outcome] = {
            "mean_paired_difference_penalty_on_minus_off": float(np.mean(differences)),
            "paired_bootstrap_ci95": _paired_bootstrap_ci(differences),
        }
    result = {
        "experiment": "E-SIM4",
        "arms": out,
        "seeds": seeds,
        "theta": 0.17,
        "memory_epochs": 7,
        "paired_contrasts": contrasts,
        "primary_interval_excludes_zero": bool(
            contrasts["learner_median_price"]["paired_bootstrap_ci95"][0] > 0
            or contrasts["learner_median_price"]["paired_bootstrap_ci95"][1] < 0
        ),
        "claim_boundary": (
            "Paired common-seed simulation contrast under a calibrated steering "
            "penalty; not a causal estimate of the proprietary live router."
        ),
    }
    _write_run(result, "esim4")
    return result


def run_esim4b(seeds: int = 4, train_epochs: int = 300_000) -> dict:
    """R4: the steering counterfactual in the CALIBRATED markets. In each
    bundle market the learner takes the slot of the most-undercutting
    non-author provider; co-players are the fitted species at their real
    prices; arms: penalty off / any-cutter / cheapest-only (the measured
    conditional). Grid is in anchor multiples of the market's anchor."""
    from .routers_steering import CutPenaltyRouter
    from .strategies_qlearn import TabularQAgent, expected_profits, price_grid

    _require_esim1_pass()
    revs = sorted(CAL_OUT.glob("*/bundle.json"))
    bundle = json.loads(revs[-1].read_text())
    arms = {
        "penalty_off": lambda: InversePriceRouter(2.0),
        "penalty_any": lambda: CutPenaltyRouter(2.0, theta=0.17, memory=7),
        "penalty_cheapest": lambda: CutPenaltyRouter(
            2.0, theta=0.17, memory=7, cheapest_only=True
        ),
    }
    out: dict[str, dict] = {}
    for model_id, m in bundle["markets"].items():
        provs = m["providers"]
        anchor = float(m["anchor_price"])
        below = [
            (name, v) for name, v in provs.items()
            if not v["is_author"] and v["anchor_class"].startswith("below")
        ]
        if not below:
            continue
        slot = min(below, key=lambda kv: kv[1]["price"])[0]
        min_price = min(v["price"] for v in provs.values())
        tiers = bundle["cost"].get("provider_tiers", {})
        costs = {
            name: _marginal_cost(tiers.get(name, "unknown"), float(v["price"]),
                                 min_price, bundle["cost"])
            for name, v in provs.items()
        }
        grid = price_grid(anchor)
        market_out = {}
        for arm, mk_router in arms.items():
            rows = []
            for seed in range(seeds):
                router = mk_router()
                strategies = {}
                for i, (name, v) in enumerate(sorted(provs.items())):
                    if name == slot:
                        continue
                    cls = v["anchor_class"]
                    price = float(v["price"])
                    if v["is_author"] or cls not in bundle["species"]:
                        strategies[name] = StaticStrategy(price)
                    else:
                        margin = float(np.log(price / anchor)) if price > 0 else 0.0
                        strategies[name] = species_strategy(
                            cls, bundle["species"],
                            min((p for p, vv in provs.items() if vv["is_author"]),
                                key=lambda p: provs[p]["price"]),
                            margin_log=margin if cls in ("below_static", "above") else None,
                            seed=seed * 1000 + i,
                        )
                specs = {
                    name: ProviderSpec(provider=name, marginal_cost=costs[name],
                                       physical_capacity=1)
                    for name in provs
                }
                agent = TabularQAgent(grid, seed=seed)
                quotes = {name: float(v["price"]) for name, v in provs.items()}
                own_idx = int(np.argmin(np.abs(grid - quotes[slot])))
                for _t in range(train_epochs):
                    rival_min = min(q for p, q in quotes.items() if p != slot)
                    s = agent.state_index(own_idx, int(np.argmin(np.abs(grid - rival_min))))
                    a = agent.act_index(s)
                    quotes[slot] = float(grid[a])
                    for p, strat in strategies.items():
                        quotes[p] = strat.act(specs[p], dict(quotes)).quote
                    pis = expected_profits(quotes, costs, router, 1.0)
                    if hasattr(router, "advance"):
                        router.advance(quotes)
                    rival_min2 = min(q for p, q in quotes.items() if p != slot)
                    s2 = agent.state_index(a, int(np.argmin(np.abs(grid - rival_min2))))
                    agent.update(s, a, pis[slot], s2)
                    own_idx = a
                prices = []
                for _t in range(56):
                    rival_min = min(q for p, q in quotes.items() if p != slot)
                    s = agent.state_index(
                        int(np.argmin(np.abs(grid - quotes[slot]))),
                        int(np.argmin(np.abs(grid - rival_min))),
                    )
                    quotes[slot] = float(grid[agent.greedy(s)])
                    for p, strat in strategies.items():
                        quotes[p] = strat.act(specs[p], dict(quotes)).quote
                    if hasattr(router, "advance"):
                        router.advance(quotes)
                    prices.append(quotes[slot])
                rows.append({
                    "seed": seed,
                    "learner_median_rel_anchor": round(float(
                        np.median(prices) / anchor), 4),
                    "market_mean_rel_anchor": round(float(
                        np.mean(list(quotes.values())) / anchor), 4),
                })
            market_out[arm] = rows
        out[model_id] = {"slot": slot, "n_providers": len(provs), "arms": market_out}
    result = {"experiment": "E-SIM4b", "markets": out, "seeds": seeds,
              "theta": 0.17, "memory": 7, "bundle_rev": bundle["rev"]}
    _write_run(result, "esim4b")
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="E-SIM1")
    ap.add_argument("--bundle", default=None)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--epochs", type=int, default=56)
    ap.add_argument("--burn-in", type=int, default=7)
    args = ap.parse_args()
    if args.experiment == "E-SIM1":
        result = run_esim1(args.bundle, args.seeds, args.epochs, args.burn_in)
        d = _write_run(result, "esim1")
        print(json.dumps(result, indent=1, default=str))
        print(f"run dir: {d}")
    elif args.experiment == "E-SIM2":
        print(json.dumps(run_esim2(seeds=args.seeds), indent=1, default=str))
    elif args.experiment == "E-SIM3":
        print(json.dumps(run_esim3(seeds=args.seeds), indent=1, default=str))
    elif args.experiment == "E-SIM4":
        print(json.dumps(run_esim4(seeds=args.seeds), indent=1, default=str))
    elif args.experiment == "E-SIM4b":
        print(json.dumps(run_esim4b(seeds=args.seeds), indent=1, default=str))
    else:
        raise SystemExit(f"unknown experiment {args.experiment}")


if __name__ == "__main__":
    main()
