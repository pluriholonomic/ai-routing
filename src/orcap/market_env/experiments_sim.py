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
E_SIM4_AUDITED_RUN = OUT / "esim4" / "fc6f9c8656" / "results.json"
E_SIM4B_ARCHIVED_RUN = OUT / "esim4b" / "c02d276c74" / "results.json"
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
    anchor_provider = min((p for p in authors), key=lambda p: provs[p]["price"], default=None)
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
                cls,
                bundle["species"],
                anchor_provider,
                margin_log=margin if cls in ("below_static", "above") else None,
                seed=pseed,
            )
        else:
            strategies[name] = StaticStrategy(price)
    workload = Workload(
        name="short_chat",
        input_tokens=1000,
        output_tokens=256,
        delivered_value=max(v["price"] for v in provs.values()) * 3,
    )
    kernel = MarketKernel(
        tuple(specs.values()), workload, InversePriceRouter(exponent=2.0), seed=seed
    )
    return kernel, specs, strategies, anchor_provider, classes, authors


def run_market(
    bundle: dict, model_id: str, seed: int, epochs: int, burn_in: int, author_hazard: float = 0.02
) -> pd.DataFrame:
    kernel, specs, strategies, anchor_provider, classes, authors = build_market(
        bundle, model_id, seed, author_hazard
    )
    rng = np.random.default_rng(_market_seed(seed, model_id))
    ar1 = bundle["demand"].get("ar1_median") or 0.5
    sigma = bundle["demand"].get("sigma_dlog_median") or 0.3
    p_anchor0 = bundle["markets"][model_id]["anchor_price"]
    quotes = {p: s.act(specs[p], {anchor_provider: p_anchor0}).quote for p, s in strategies.items()}
    p0 = float(np.median(list(quotes.values())))
    log_dev = 0.0
    results, anchor_prices = [], []
    for _t in range(epochs):
        actions = {p: s.act(specs[p], dict(quotes)) for p, s in strategies.items()}
        quotes = {p: a.quote for p, a in actions.items()}
        anchor_prices.append(quotes[anchor_provider])
        log_dev = ar1 * log_dev + sigma * rng.standard_normal()
        p_med = float(np.median(list(quotes.values())))
        demand = int(round(BASE_DEMAND * np.exp(log_dev) * (p_med / p0) ** END_USER_ELASTICITY))
        results.append(kernel.step(actions, demand=max(demand, 1)))
    traj = moments.trajectory_from_epoch_results(results, model_id, classes, anchor_prices, authors)
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
    log.info(
        "market-conditional targets: %s | author cadence %.4f",
        {k: v[0] for k, v in targets.items()},
        author_hazard,
    )
    per_seed = []
    for seed in range(seeds):
        trajs = [run_market(bundle, m, seed, epochs, burn_in, author_hazard) for m in markets]
        mom = moments.compute_moments(pd.concat(trajs, ignore_index=True))
        per_seed.append(mom)
        log.info("seed %d distance %.4f", seed, moments.moment_distance(mom, targets)["distance"])
    keys = sorted({k for m in per_seed for k in m if m[k] is not None})
    mean_moments = {
        k: float(np.mean([m[k] for m in per_seed if m.get(k) is not None])) for k in keys
    }
    sd_moments = {k: float(np.std([m[k] for m in per_seed if m.get(k) is not None])) for k in keys}
    score = moments.moment_distance(mean_moments, targets)
    w2_ok = all(
        abs(score["relative_errors"].get(k) or 0) <= W2_MAX_REL_ERR
        for k, (_, w) in targets.items()
        if w >= 2
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
    canonical_result = json.dumps(result, sort_keys=True, default=str).encode()
    rid = hashlib.blake2b(canonical_result, digest_size=5).hexdigest()
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
    commit_source_hash = hashlib.sha256()
    commit_source_available = True
    for source in source_files:
        source_hash.update(source.as_posix().encode())
        source_hash.update(b"\0")
        source_hash.update(source.read_bytes())
        source_hash.update(b"\0")
        committed = subprocess.run(
            ["git", "show", f"{commit}:{source.as_posix()}"],
            capture_output=True,
        )
        if committed.returncode != 0:
            commit_source_available = False
            continue
        commit_source_hash.update(source.as_posix().encode())
        commit_source_hash.update(b"\0")
        commit_source_hash.update(committed.stdout)
        commit_source_hash.update(b"\0")
    current_source_digest = source_hash.hexdigest()
    committed_source_digest = commit_source_hash.hexdigest() if commit_source_available else None
    input_hashes = {}
    for key, value in sorted(result.items()):
        if not key.startswith("source_") or not isinstance(value, str):
            continue
        input_path = Path(value)
        if input_path.is_file():
            input_hashes[key] = hashlib.sha256(input_path.read_bytes()).hexdigest()
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": rid,
                "experiment": result.get("experiment"),
                "commit": commit,
                "bundle_rev": result.get("bundle_rev"),
                "seeds": result.get("seeds"),
                "result_sha256": hashlib.sha256(canonical_result).hexdigest(),
                "market_env_source_sha256": current_source_digest,
                "market_env_commit_source_sha256": committed_source_digest,
                "market_env_source_matches_commit": bool(
                    committed_source_digest == current_source_digest
                ),
                "input_artifact_sha256": input_hashes,
            },
            indent=1,
        )
    )
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
            outcomes.append(
                {
                    "seed": seed,
                    "learned_class": learned,
                    "median_log_rel": round(med_rel, 3),
                    "changes_per_day": round(cpd, 3),
                    "share_at_anchor": round(at_anchor, 3),
                }
            )
        out[slot] = outcomes
    result = {
        "experiment": "E-SIM2",
        "replaced_slot_outcomes": out,
        "seeds": seeds,
        "train_epochs": train_epochs,
    }
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
                InversePriceRouter(a),
                n_agents=3,
                mc=0.2,
                max_epochs=300_000,
                stable_window=40_000,
                seed=seed * 13 + 1,
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
            rows.append(
                {
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
                }
            )
        deltas = [x["calvano_delta"] for x in rows if x["calvano_delta"] is not None]
        prices = [np.mean(list(x["final_prices"].values())) for x in rows]
        sweep.append(
            {
                "exponent": a,
                "mean_price": round(float(np.mean(prices)), 4),
                "mean_delta": round(float(np.mean(deltas)), 4) if deltas else None,
                "sd_delta": round(float(np.std(deltas)), 4) if deltas else None,
                "n_delta_defined": len(deltas),
                "converged_seeds": int(sum(x["converged"] for x in rows)),
                "equilibrium_consistent_seeds": int(sum(x["equilibrium_consistent"] for x in rows)),
                "punish_and_revert_seed_share": round(
                    float(np.mean([x["punish_and_revert_share"] > 0 for x in rows])), 4
                ),
                "per_seed": rows,
            }
        )
    arm_prices = [row["mean_price"] for row in sweep]
    adjacent = []
    for left, right in zip(sweep[:-1], sweep[1:], strict=True):
        differences = [
            rrow["mean_price"] - lrow["mean_price"]
            for lrow, rrow in zip(left["per_seed"], right["per_seed"], strict=True)
        ]
        adjacent.append(
            {
                "from_exponent": left["exponent"],
                "to_exponent": right["exponent"],
                "mean_price_difference": float(np.mean(differences)),
                "paired_bootstrap_ci95": _paired_bootstrap_ci(differences),
            }
        )
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
    from .diagnostics_collusion import (
        cut_response,
        deviation_audit,
        permanent_cut_audit,
    )
    from .routers_steering import CutPenaltyRouter
    from .strategies_qlearn import TabularQAgent, expected_profits, price_grid

    _require_esim1_pass()
    grid = price_grid(1.0)
    arms = {"penalty_off": None, "penalty_on": 0.17}
    out = {}
    for arm, theta in arms.items():
        rows = []
        for seed in range(seeds):
            router = (
                InversePriceRouter(2.0)
                if theta is None
                else CutPenaltyRouter(2.0, theta=theta, memory=7)
            )
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
            if theta is None:
                dynamic_audit = None
            else:
                penalty_snapshot = CutPenaltyRouter(2.0, theta=theta, memory=7)
                for _ in range(7):
                    penalty_snapshot.advance(quotes)
                dynamic_audit = permanent_cut_audit(
                    quotes,
                    costs,
                    slot,
                    InversePriceRouter(2.0),
                    penalty_snapshot,
                    1.0,
                    grid,
                    gamma=agent.gamma,
                    penalty_memory=7,
                )
            rows.append(
                {
                    "seed": seed,
                    "learner_median_price": round(float(np.median(prices)), 4),
                    "learner_changes_per_day": round(reprices / 55, 3),
                    "market_mean_price": round(float(np.mean([np.mean(list(quotes.values()))])), 4),
                    "max_deviation_gain_relative": audit["max_gain_rel_to_mean_profit"],
                    "equilibrium_consistent": audit["equilibrium_consistent"],
                    "cut_response": response_audit["verdict"],
                    "permanent_cut_audit": dynamic_audit,
                }
            )
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
        "penalty_on_permanent_cut_profitable_seeds": int(
            sum(row["permanent_cut_audit"]["permanent_cut_profitable"] for row in out["penalty_on"])
        ),
        "claim_boundary": (
            "Paired common-seed simulation contrast under a calibrated steering "
            "penalty; not a causal estimate of the proprietary live router. A "
            "profitable permanent-cut audit means a learned high-price state is "
            "a path-dependent learning outcome, not an equilibrium claim."
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
        "penalty_cheapest": lambda: CutPenaltyRouter(2.0, theta=0.17, memory=7, cheapest_only=True),
    }
    out: dict[str, dict] = {}
    for model_id, m in bundle["markets"].items():
        provs = m["providers"]
        anchor = float(m["anchor_price"])
        below = [
            (name, v)
            for name, v in provs.items()
            if not v["is_author"] and v["anchor_class"].startswith("below")
        ]
        if not below:
            continue
        slot = min(below, key=lambda kv: kv[1]["price"])[0]
        min_price = min(v["price"] for v in provs.values())
        tiers = bundle["cost"].get("provider_tiers", {})
        costs = {
            name: _marginal_cost(
                tiers.get(name, "unknown"), float(v["price"]), min_price, bundle["cost"]
            )
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
                            cls,
                            bundle["species"],
                            min(
                                (p for p, vv in provs.items() if vv["is_author"]),
                                key=lambda p: provs[p]["price"],
                            ),
                            margin_log=margin if cls in ("below_static", "above") else None,
                            seed=seed * 1000 + i,
                        )
                specs = {
                    name: ProviderSpec(
                        provider=name, marginal_cost=costs[name], physical_capacity=1
                    )
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
                rows.append(
                    {
                        "seed": seed,
                        "learner_median_rel_anchor": round(float(np.median(prices) / anchor), 4),
                        "market_mean_rel_anchor": round(
                            float(np.mean(list(quotes.values())) / anchor), 4
                        ),
                    }
                )
            market_out[arm] = rows
        out[model_id] = {"slot": slot, "n_providers": len(provs), "arms": market_out}
    result = {
        "experiment": "E-SIM4b",
        "markets": out,
        "seeds": seeds,
        "theta": 0.17,
        "memory": 7,
        "bundle_rev": bundle["rev"],
    }
    _write_run(result, "esim4b")
    return result


def run_esim5(
    seeds: int = 20,
    train_steps: int = 300_000,
    evaluation_steps: int = 10_000,
) -> dict:
    """History-aware versus state-aliased learning under the E-SIM4 penalty.

    The terminal profiles and permanent-cut actions come from the immutable
    audited E-SIM4 result.  Rival prices are reconstructed from E-SIM4's frozen
    stylized-world design and checked against the archived discounted values
    before either learner is trained.
    """
    from .state_aliasing import (
        HIGH,
        LOW,
        BinaryCutPenaltyMDP,
        evaluate_deterministic_policy,
        solve_exact,
        train_q,
    )

    _require_esim1_pass()
    if seeds != 20 or train_steps != 300_000 or evaluation_steps != 10_000:
        raise ValueError("E-SIM5 confirmatory design is frozen at 20/300000/10000")
    if not E_SIM4_AUDITED_RUN.exists():
        raise FileNotFoundError(f"missing frozen E-SIM4 input: {E_SIM4_AUDITED_RUN}")
    source = json.loads(E_SIM4_AUDITED_RUN.read_text())
    penalty_rows = source["arms"]["penalty_on"]
    if source.get("seeds") != 20 or len(penalty_rows) != 20:
        raise ValueError("frozen E-SIM4 input must contain exactly 20 seeds")

    rival_prices = (1.0, 1.0, float(np.exp(-0.4)), float(np.exp(0.34)))
    rows: list[dict] = []
    for row in penalty_rows:
        audit = row["permanent_cut_audit"]
        mdp = BinaryCutPenaltyMDP(
            low_price=float(audit["best_permanent_cut"]["price"]),
            high_price=float(row["learner_median_price"]),
            marginal_cost=0.2,
            rival_prices=rival_prices,
            exponent=2.0,
            theta=float(source["theta"]),
            memory=int(source["memory_epochs"]),
            gamma=0.95,
        )
        if not np.isclose(mdp.permanent_high_value(), audit["stay_discounted_value"], atol=1e-10):
            raise ValueError("reconstructed E-SIM4 stay value does not match archive")
        if not np.isclose(
            mdp.permanent_low_value(),
            audit["best_permanent_cut"]["discounted_value"],
            atol=1e-10,
        ):
            raise ValueError("reconstructed E-SIM4 cut value does not match archive")

        exact = solve_exact(mdp)
        always_low = np.full(mdp.n_states, LOW, dtype=np.int8)
        enumerated_low = evaluate_deterministic_policy(mdp, always_low)[mdp.initial_state]
        formula_error = abs(float(enumerated_low) - mdp.permanent_low_value())
        if exact.bellman_residual > 1e-10 or formula_error > 1e-10:
            raise RuntimeError("E-SIM5 exact-benchmark validity gate failed")

        seed = int(row["seed"])
        aware = train_q(
            mdp,
            "history",
            seed=seed,
            train_steps=train_steps,
            evaluation_steps=evaluation_steps,
        )
        aliased = train_q(
            mdp,
            "aliased",
            seed=seed,
            train_steps=train_steps,
            evaluation_steps=evaluation_steps,
        )
        exact_initial = float(exact.values[mdp.initial_state])
        aware["normalized_discounted_regret"] = float(aware["discounted_regret"]) / abs(
            exact_initial
        )
        aliased["normalized_discounted_regret"] = float(aliased["discounted_regret"]) / abs(
            exact_initial
        )
        rows.append(
            {
                "seed": seed,
                "profile": {
                    "low_price": mdp.low_price,
                    "high_price": mdp.high_price,
                    "rival_prices": list(mdp.rival_prices),
                },
                "exact": {
                    "initial_action": int(exact.policy[mdp.initial_state]),
                    "initial_action_label": (
                        "low" if exact.policy[mdp.initial_state] == LOW else "high"
                    ),
                    "initial_value": exact_initial,
                    "bellman_residual": exact.bellman_residual,
                    "iterations": exact.iterations,
                    "permanent_low_formula_error": formula_error,
                    "policy": exact.policy.tolist(),
                },
                "history_aware_q": aware,
                "aliased_q": aliased,
            }
        )

    price_differences = [
        float(row["history_aware_q"]["median_price"]) - float(row["aliased_q"]["median_price"])
        for row in rows
    ]
    low_share_differences = [
        float(row["history_aware_q"]["low_action_share"])
        - float(row["aliased_q"]["low_action_share"])
        for row in rows
    ]
    regret_differences = [
        float(row["history_aware_q"]["normalized_discounted_regret"])
        - float(row["aliased_q"]["normalized_discounted_regret"])
        for row in rows
    ]
    price_ci = _paired_bootstrap_ci(price_differences)
    exact_cuts = sum(row["exact"]["initial_action"] == LOW for row in rows)
    aware_agrees = sum(bool(row["history_aware_q"]["first_action_agrees_exact"]) for row in rows)
    aware_low_regret = sum(
        float(row["history_aware_q"]["normalized_discounted_regret"]) <= 0.05 for row in rows
    )
    aliased_stays_high = sum(
        row["aliased_q"]["first_action"] == HIGH
        and float(row["aliased_q"]["low_action_share"]) <= 0.10
        for row in rows
    )
    gates = {
        "exact_cuts_20_of_20": exact_cuts == 20,
        "primary_ci_strictly_negative": bool(price_ci and price_ci[1] < 0),
        "history_aware_exact_first_action_at_least_16": aware_agrees >= 16,
        "history_aware_low_regret_at_least_16": aware_low_regret >= 16,
        "aliased_high_at_least_16": aliased_stays_high >= 16,
    }
    result = {
        "experiment": "E-SIM5",
        "source_esim4": str(E_SIM4_AUDITED_RUN),
        "seeds": seeds,
        "train_steps": train_steps,
        "evaluation_steps": evaluation_steps,
        "theta": float(source["theta"]),
        "memory": int(source["memory_epochs"]),
        "gamma": 0.95,
        "rows": rows,
        "primary": {
            "estimand": "median_price_history_aware_minus_aliased",
            "paired_mean": float(np.mean(price_differences)),
            "paired_bootstrap_ci95": price_ci,
        },
        "secondary": {
            "low_action_share_paired_mean": float(np.mean(low_share_differences)),
            "low_action_share_paired_bootstrap_ci95": _paired_bootstrap_ci(low_share_differences),
            "normalized_regret_paired_mean": float(np.mean(regret_differences)),
            "normalized_regret_paired_bootstrap_ci95": _paired_bootstrap_ci(regret_differences),
            "exact_cut_profiles": exact_cuts,
            "history_aware_exact_first_action": aware_agrees,
            "history_aware_low_regret": aware_low_regret,
            "aliased_stays_high": aliased_stays_high,
        },
        "mechanism_gates": gates,
        "state_aliasing_mechanism_supported": bool(all(gates.values())),
        "claim_boundary": (
            "Controlled two-action calibrated counterfactual. Passing identifies "
            "a bounded-learner state-aliasing mechanism, not live-router causality, "
            "provider conduct, equilibrium, or collusion."
        ),
    }
    _write_run(result, "esim5")
    return result


def run_esim6(
    seeds: int = 20,
    train_transitions: int = 300_000,
    evaluation_transitions: int = 10_000,
) -> dict:
    """Primitive Q-learning versus a payoff-equivalent persistent-cut option."""
    from .state_aliasing import (
        LOW,
        BinaryCutPenaltyMDP,
        solve_exact,
        solve_exact_with_option,
        train_option_q,
        train_q,
    )

    _require_esim1_pass()
    if seeds != 20 or train_transitions != 300_000 or evaluation_transitions != 10_000:
        raise ValueError("E-SIM6 confirmatory design is frozen at 20/300000/10000")
    if not E_SIM4_AUDITED_RUN.exists():
        raise FileNotFoundError(f"missing frozen E-SIM4 input: {E_SIM4_AUDITED_RUN}")
    source = json.loads(E_SIM4_AUDITED_RUN.read_text())
    source_rows = source["arms"]["penalty_on"]
    if source.get("seeds") != 20 or len(source_rows) != 20:
        raise ValueError("frozen E-SIM4 input must contain exactly 20 seeds")

    memories = (1, 3, 5, 7, 9, 12)
    rival_prices = (1.0, 1.0, float(np.exp(-0.4)), float(np.exp(0.34)))
    sweep: list[dict] = []
    for memory in memories:
        rows: list[dict] = []
        for source_row in source_rows:
            audit = source_row["permanent_cut_audit"]
            mdp = BinaryCutPenaltyMDP(
                low_price=float(audit["best_permanent_cut"]["price"]),
                high_price=float(source_row["learner_median_price"]),
                marginal_cost=0.2,
                rival_prices=rival_prices,
                exponent=2.0,
                theta=float(source["theta"]),
                memory=memory,
                gamma=0.95,
            )
            exact = solve_exact(mdp)
            exact_option = solve_exact_with_option(mdp)
            exact_gap = float(np.max(np.abs(exact.values - exact_option.values)))
            if (
                exact.bellman_residual > 1e-10
                or exact_option.bellman_residual > 1e-10
                or exact_gap > 1e-10
            ):
                raise RuntimeError("E-SIM6 exact option-equivalence gate failed")
            seed = int(source_row["seed"])
            primitive = train_q(
                mdp,
                "history",
                seed=seed,
                train_steps=train_transitions,
                evaluation_steps=evaluation_transitions,
            )
            option = train_option_q(
                mdp,
                seed=seed,
                train_transitions=train_transitions,
                evaluation_transitions=evaluation_transitions,
            )
            exact_value = float(exact.values[mdp.initial_state])
            for learned in (primitive, option):
                learned["normalized_discounted_regret"] = float(learned["discounted_regret"]) / abs(
                    exact_value
                )
            rows.append(
                {
                    "seed": seed,
                    "memory": memory,
                    "exact_initial_action": int(exact.policy[mdp.initial_state]),
                    "exact_initial_action_label": (
                        "low" if exact.policy[mdp.initial_state] == LOW else "high"
                    ),
                    "exact_initial_value": exact_value,
                    "exact_option_value_gap": exact_gap,
                    "primitive_q": primitive,
                    "commit_option_q": option,
                }
            )

        regret_differences = [
            float(row["commit_option_q"]["normalized_discounted_regret"])
            - float(row["primitive_q"]["normalized_discounted_regret"])
            for row in rows
        ]
        price_differences = [
            float(row["commit_option_q"]["median_price"])
            - float(row["primitive_q"]["median_price"])
            for row in rows
        ]
        exact_low = sum(row["exact_initial_action"] == LOW for row in rows)
        primitive_success = sum(
            bool(row["primitive_q"]["first_action_agrees_exact"])
            and float(row["primitive_q"]["normalized_discounted_regret"]) <= 0.05
            for row in rows
        )
        option_success = sum(
            bool(row["commit_option_q"]["first_action_agrees_exact"])
            and float(row["commit_option_q"]["normalized_discounted_regret"]) <= 0.05
            for row in rows
        )
        sweep.append(
            {
                "memory": memory,
                "exact_low_profiles": exact_low,
                "primitive_success_profiles": primitive_success,
                "option_success_profiles": option_success,
                "primitive_mean_normalized_regret": float(
                    np.mean([row["primitive_q"]["normalized_discounted_regret"] for row in rows])
                ),
                "option_mean_normalized_regret": float(
                    np.mean(
                        [row["commit_option_q"]["normalized_discounted_regret"] for row in rows]
                    )
                ),
                "option_minus_primitive_regret": {
                    "paired_mean": float(np.mean(regret_differences)),
                    "paired_bootstrap_ci95": _paired_bootstrap_ci(regret_differences),
                },
                "option_minus_primitive_median_price": {
                    "paired_mean": float(np.mean(price_differences)),
                    "paired_bootstrap_ci95": _paired_bootstrap_ci(price_differences),
                },
                "rows": rows,
            }
        )

    calibrated = next(row for row in sweep if row["memory"] == 7)
    calibrated_ci = calibrated["option_minus_primitive_regret"]["paired_bootstrap_ci95"]
    gates = {
        "exact_option_values_equal_everywhere": bool(
            max(row["exact_option_value_gap"] for arm in sweep for row in arm["rows"]) <= 1e-10
        ),
        "primary_regret_ci_strictly_negative": bool(calibrated_ci and calibrated_ci[1] < 0),
        "option_success_at_least_16": calibrated["option_success_profiles"] >= 16,
        "option_low_regret_at_least_16": sum(
            float(row["commit_option_q"]["normalized_discounted_regret"]) <= 0.05
            for row in calibrated["rows"]
        )
        >= 16,
        "primitive_success_at_most_4": calibrated["primitive_success_profiles"] <= 4,
    }
    result = {
        "experiment": "E-SIM6",
        "source_esim4": str(E_SIM4_AUDITED_RUN),
        "seeds": seeds,
        "train_transitions": train_transitions,
        "evaluation_transitions": evaluation_transitions,
        "memories": list(memories),
        "sweep": sweep,
        "primary": {
            "memory": 7,
            "estimand": "normalized_regret_option_minus_primitive",
            **calibrated["option_minus_primitive_regret"],
        },
        "mechanism_gates": gates,
        "delayed_credit_intervention_supported": bool(all(gates.values())),
        "claim_boundary": (
            "A passing result identifies a delayed-credit barrier and its removal "
            "by a payoff-equivalent commitment option in the controlled calibrated "
            "MDP. It does not identify live-router causality, provider conduct, "
            "equilibrium, or collusion."
        ),
    }
    _write_run(result, "esim6")
    return result


def run_esim7(
    seeds: int = 20,
    train_transitions: int = 300_000,
    evaluation_transitions: int = 10_000,
) -> dict:
    """Transport E-SIM6 to all four frozen calibrated price books."""
    from .state_aliasing import (
        LOW,
        BinaryCutPenaltyMDP,
        solve_exact,
        solve_exact_with_option,
        train_option_q,
        train_q,
    )
    from .strategies_qlearn import price_grid

    bundle_rev = _require_esim1_pass()
    if seeds != 20 or train_transitions != 300_000 or evaluation_transitions != 10_000:
        raise ValueError("E-SIM7 confirmatory design is frozen at 20/300000/10000")
    if not E_SIM4B_ARCHIVED_RUN.exists():
        raise FileNotFoundError(f"missing frozen E-SIM4b input: {E_SIM4B_ARCHIVED_RUN}")
    source = json.loads(E_SIM4B_ARCHIVED_RUN.read_text())
    if source.get("bundle_rev") != bundle_rev or source.get("seeds") != 4:
        raise ValueError("E-SIM4b archive does not match the frozen calibration")
    bundle_path = CAL_OUT / bundle_rev / "bundle.json"
    bundle = json.loads(bundle_path.read_text())

    markets: dict[str, dict] = {}
    for model_id, source_market in source["markets"].items():
        market = bundle["markets"][model_id]
        providers = market["providers"]
        slot = source_market["slot"]
        anchor = float(market["anchor_price"])
        high_price = anchor * float(
            source_market["arms"]["penalty_any"][0]["learner_median_rel_anchor"]
        )
        min_price = min(float(provider["price"]) for provider in providers.values())
        tiers = bundle["cost"].get("provider_tiers", {})
        slot_price = float(providers[slot]["price"])
        marginal_cost = _marginal_cost(
            tiers.get(slot, "unknown"), slot_price, min_price, bundle["cost"]
        )
        rivals = tuple(
            float(provider["price"])
            for name, provider in sorted(providers.items())
            if name != slot and float(provider["price"]) > 0
        )
        candidates = [
            float(price)
            for price in price_grid(anchor)
            if marginal_cost < price < high_price - 1e-12
        ]
        if not candidates:
            raise ValueError(f"no feasible lower action for {model_id}")
        candidate_mdps = [
            BinaryCutPenaltyMDP(
                low_price=price,
                high_price=high_price,
                marginal_cost=marginal_cost,
                rival_prices=rivals,
                exponent=2.0,
                theta=0.17,
                memory=7,
                gamma=0.95,
            )
            for price in candidates
        ]
        mdp = max(candidate_mdps, key=lambda candidate: candidate.permanent_low_value())
        exact = solve_exact(mdp)
        exact_option = solve_exact_with_option(mdp)
        exact_gap = float(np.max(np.abs(exact.values - exact_option.values)))
        if (
            exact.bellman_residual > 1e-10
            or exact_option.bellman_residual > 1e-10
            or exact_gap > 1e-10
        ):
            raise RuntimeError(f"E-SIM7 exact gate failed for {model_id}")

        u_high = mdp.reward(mdp.initial_state, 1)
        u_penalized_low = mdp.reward(mdp.initial_state, LOW)
        u_low = mdp.reward(0, LOW)
        ratio = (
            (u_high - u_penalized_low) / (u_low - u_penalized_low)
            if u_low > u_penalized_low
            else np.nan
        )
        rational_boundary = float(np.log(ratio) / np.log(mdp.gamma)) if 0 < ratio < 1 else None
        eligible = bool(u_low > u_high > u_penalized_low and exact.policy[mdp.initial_state] == LOW)
        rows: list[dict] = []
        for seed in range(seeds):
            primitive = train_q(
                mdp,
                "history",
                seed=seed,
                train_steps=train_transitions,
                evaluation_steps=evaluation_transitions,
            )
            option = train_option_q(
                mdp,
                seed=seed,
                train_transitions=train_transitions,
                evaluation_transitions=evaluation_transitions,
            )
            exact_value = float(exact.values[mdp.initial_state])
            for learned in (primitive, option):
                learned["normalized_discounted_regret"] = float(learned["discounted_regret"]) / abs(
                    exact_value
                )
            rows.append(
                {
                    "seed": seed,
                    "primitive_q": primitive,
                    "commit_option_q": option,
                }
            )
        regret_differences = [
            float(row["commit_option_q"]["normalized_discounted_regret"])
            - float(row["primitive_q"]["normalized_discounted_regret"])
            for row in rows
        ]
        price_differences = [
            float(row["commit_option_q"]["median_price"])
            - float(row["primitive_q"]["median_price"])
            for row in rows
        ]
        option_success = sum(
            bool(row["commit_option_q"]["first_action_agrees_exact"])
            and float(row["commit_option_q"]["normalized_discounted_regret"]) <= 0.05
            for row in rows
        )
        primitive_success = sum(
            bool(row["primitive_q"]["first_action_agrees_exact"])
            and float(row["primitive_q"]["normalized_discounted_regret"]) <= 0.05
            for row in rows
        )
        regret_ci = _paired_bootstrap_ci(regret_differences)
        market_gate = bool(
            eligible
            and regret_ci
            and regret_ci[1] < 0
            and option_success >= 16
            and primitive_success <= 4
        )
        markets[model_id] = {
            "slot": slot,
            "n_providers": len(providers),
            "profile": {
                "anchor_price": anchor,
                "high_price": high_price,
                "low_price": mdp.low_price,
                "marginal_cost": marginal_cost,
                "u_high": u_high,
                "u_penalized_low": u_penalized_low,
                "u_low": u_low,
                "rational_memory_boundary": rational_boundary,
                "exact_initial_action": (
                    "low" if exact.policy[mdp.initial_state] == LOW else "high"
                ),
                "delayed_credit_eligible": eligible,
                "exact_option_value_gap": exact_gap,
            },
            "option_minus_primitive_regret": {
                "paired_mean": float(np.mean(regret_differences)),
                "paired_bootstrap_ci95": regret_ci,
            },
            "option_minus_primitive_median_price": {
                "paired_mean": float(np.mean(price_differences)),
                "paired_bootstrap_ci95": _paired_bootstrap_ci(price_differences),
            },
            "option_success_profiles": option_success,
            "primitive_success_profiles": primitive_success,
            "market_transport_gate": market_gate,
            "rows": rows,
        }

    eligible_markets = [
        model_id
        for model_id, market in markets.items()
        if market["profile"]["delayed_credit_eligible"]
    ]
    gates = {
        "exact_option_values_equal_everywhere": bool(
            max(market["profile"]["exact_option_value_gap"] for market in markets.values()) <= 1e-10
        ),
        "at_least_three_eligible_markets": len(eligible_markets) >= 3,
        "every_eligible_market_passes": bool(
            eligible_markets
            and all(markets[model_id]["market_transport_gate"] for model_id in eligible_markets)
        ),
    }
    result = {
        "experiment": "E-SIM7",
        "source_esim4b": str(E_SIM4B_ARCHIVED_RUN),
        "bundle_rev": bundle_rev,
        "seeds": seeds,
        "train_transitions": train_transitions,
        "evaluation_transitions": evaluation_transitions,
        "markets": markets,
        "eligible_markets": eligible_markets,
        "transport_gates": gates,
        "cross_market_transport_supported": bool(all(gates.values())),
        "claim_boundary": (
            "Cross-price-book calibrated counterfactual using frozen quotes and "
            "cost rules. It does not identify live-router causality, equilibrium, "
            "provider conduct, or a population-average market effect."
        ),
    }
    _write_run(result, "esim7")
    return result


def run_esim8(
    seeds: int = 20,
    train_transitions: int = 300_000,
    evaluation_transitions: int = 10_000,
) -> dict:
    """Frozen 3-by-3 alpha/exploration robustness grid for E-SIM6."""
    from .state_aliasing import (
        LOW,
        BinaryCutPenaltyMDP,
        solve_exact,
        solve_exact_with_option,
        train_option_q,
        train_q,
    )

    _require_esim1_pass()
    if seeds != 20 or train_transitions != 300_000 or evaluation_transitions != 10_000:
        raise ValueError("E-SIM8 confirmatory design is frozen at 20/300000/10000")
    source = json.loads(E_SIM4_AUDITED_RUN.read_text())
    source_row = source["arms"]["penalty_on"][0]
    audit = source_row["permanent_cut_audit"]
    mdp = BinaryCutPenaltyMDP(
        low_price=float(audit["best_permanent_cut"]["price"]),
        high_price=float(source_row["learner_median_price"]),
        marginal_cost=0.2,
        rival_prices=(1.0, 1.0, float(np.exp(-0.4)), float(np.exp(0.34))),
        exponent=2.0,
        theta=0.17,
        memory=7,
        gamma=0.95,
    )
    exact = solve_exact(mdp)
    exact_option = solve_exact_with_option(mdp)
    exact_gap = float(np.max(np.abs(exact.values - exact_option.values)))
    if exact_gap > 1e-10 or exact.policy[mdp.initial_state] != LOW:
        raise RuntimeError("E-SIM8 exact benchmark gate failed")

    cells: list[dict] = []
    for alpha in (0.05, 0.15, 0.30):
        for beta in (1e-5, 2e-5, 4e-5):
            rows: list[dict] = []
            for seed in range(seeds):
                primitive = train_q(
                    mdp,
                    "history",
                    seed=seed,
                    alpha=alpha,
                    beta=beta,
                    train_steps=train_transitions,
                    evaluation_steps=evaluation_transitions,
                )
                option = train_option_q(
                    mdp,
                    seed=seed,
                    alpha=alpha,
                    beta=beta,
                    train_transitions=train_transitions,
                    evaluation_transitions=evaluation_transitions,
                )
                exact_value = float(exact.values[mdp.initial_state])
                for learned in (primitive, option):
                    learned["normalized_discounted_regret"] = float(
                        learned["discounted_regret"]
                    ) / abs(exact_value)
                rows.append(
                    {
                        "seed": seed,
                        "primitive_q": primitive,
                        "commit_option_q": option,
                    }
                )
            differences = [
                float(row["commit_option_q"]["normalized_discounted_regret"])
                - float(row["primitive_q"]["normalized_discounted_regret"])
                for row in rows
            ]
            interval = _paired_bootstrap_ci(differences)
            option_success = sum(
                bool(row["commit_option_q"]["first_action_agrees_exact"])
                and float(row["commit_option_q"]["normalized_discounted_regret"]) <= 0.05
                for row in rows
            )
            primitive_success = sum(
                bool(row["primitive_q"]["first_action_agrees_exact"])
                and float(row["primitive_q"]["normalized_discounted_regret"]) <= 0.05
                for row in rows
            )
            cell_pass = bool(
                interval and interval[1] < 0 and option_success >= 16 and primitive_success <= 4
            )
            cells.append(
                {
                    "alpha": alpha,
                    "beta": beta,
                    "option_minus_primitive_regret": {
                        "paired_mean": float(np.mean(differences)),
                        "paired_bootstrap_ci95": interval,
                    },
                    "option_success_profiles": option_success,
                    "primitive_success_profiles": primitive_success,
                    "cell_robustness_gate": cell_pass,
                    "rows": rows,
                }
            )
    passing_cells = sum(cell["cell_robustness_gate"] for cell in cells)
    result = {
        "experiment": "E-SIM8",
        "source_esim4": str(E_SIM4_AUDITED_RUN),
        "seeds": seeds,
        "train_transitions": train_transitions,
        "evaluation_transitions": evaluation_transitions,
        "alpha_grid": [0.05, 0.15, 0.30],
        "beta_grid": [1e-5, 2e-5, 4e-5],
        "exact_option_value_gap": exact_gap,
        "cells": cells,
        "passing_cells": passing_cells,
        "robustness_gate": passing_cells >= 7,
        "claim_boundary": (
            "Local tabular-Q robustness grid around the controlled E-SIM6 "
            "profile. It does not transport to other learner classes or actual "
            "provider algorithms."
        ),
    }
    _write_run(result, "esim8")
    return result


def run_esim9(
    seeds: int = 20,
    train_transitions: int = 300_000,
    evaluation_transitions: int = 10_000,
) -> dict:
    """Multi-step TD replication of the E-SIM6 delayed-credit mechanism."""
    from .state_aliasing import (
        LOW,
        BinaryCutPenaltyMDP,
        solve_exact,
        train_n_step_q,
        train_option_q,
        train_q,
    )

    _require_esim1_pass()
    if seeds != 20 or train_transitions != 300_000 or evaluation_transitions != 10_000:
        raise ValueError("E-SIM9 confirmatory design is frozen at 20/300000/10000")
    source = json.loads(E_SIM4_AUDITED_RUN.read_text())
    source_rows = source["arms"]["penalty_on"]
    if source.get("seeds") != 20 or len(source_rows) != 20:
        raise ValueError("frozen E-SIM4 input must contain exactly 20 seeds")

    memory = 7
    n_steps = memory + 1
    rival_prices = (1.0, 1.0, float(np.exp(-0.4)), float(np.exp(0.34)))
    rows: list[dict] = []
    for source_row in source_rows:
        audit = source_row["permanent_cut_audit"]
        mdp = BinaryCutPenaltyMDP(
            low_price=float(audit["best_permanent_cut"]["price"]),
            high_price=float(source_row["learner_median_price"]),
            marginal_cost=0.2,
            rival_prices=rival_prices,
            exponent=2.0,
            theta=float(source["theta"]),
            memory=memory,
            gamma=0.95,
        )
        seed = int(source_row["seed"])
        primitive = train_q(
            mdp,
            "history",
            seed=seed,
            train_steps=train_transitions,
            evaluation_steps=evaluation_transitions,
        )
        multi_step = train_n_step_q(
            mdp,
            seed=seed,
            n_steps=n_steps,
            train_steps=train_transitions,
            evaluation_steps=evaluation_transitions,
        )
        option = train_option_q(
            mdp,
            seed=seed,
            train_transitions=train_transitions,
            evaluation_transitions=evaluation_transitions,
        )
        exact = solve_exact(mdp)
        if exact.policy[mdp.initial_state] != LOW:
            raise RuntimeError("E-SIM9 frozen profile must be delayed-credit eligible")
        exact_value = float(exact.values[mdp.initial_state])
        for learned in (primitive, multi_step, option):
            learned["normalized_discounted_regret"] = float(learned["discounted_regret"]) / abs(
                exact_value
            )
        rows.append(
            {
                "seed": seed,
                "primitive_q": primitive,
                "n_step_q": multi_step,
                "commit_option_q": option,
            }
        )

    differences = [
        float(row["n_step_q"]["normalized_discounted_regret"])
        - float(row["primitive_q"]["normalized_discounted_regret"])
        for row in rows
    ]

    def successful(learned: dict) -> bool:
        return bool(
            learned["first_action_agrees_exact"]
            and float(learned["normalized_discounted_regret"]) <= 0.05
        )

    primitive_success = sum(successful(row["primitive_q"]) for row in rows)
    n_step_success = sum(successful(row["n_step_q"]) for row in rows)
    option_success = sum(successful(row["commit_option_q"]) for row in rows)
    interval = _paired_bootstrap_ci(differences)
    gates = {
        "n_step_regret_ci_strictly_negative": bool(interval and interval[1] < 0),
        "n_step_success_at_least_16": n_step_success >= 16,
        "primitive_success_at_most_4": primitive_success <= 4,
    }
    result = {
        "experiment": "E-SIM9",
        "source_esim4": str(E_SIM4_AUDITED_RUN),
        "seeds": seeds,
        "memory": memory,
        "n_steps": n_steps,
        "train_transitions": train_transitions,
        "evaluation_transitions": evaluation_transitions,
        "rows": rows,
        "primary": {
            "estimand": "normalized_regret_n_step_minus_primitive",
            "paired_mean": float(np.mean(differences)),
            "paired_bootstrap_ci95": interval,
        },
        "primitive_success_profiles": primitive_success,
        "n_step_success_profiles": n_step_success,
        "option_success_profiles": option_success,
        "mechanism_gates": gates,
        "multi_step_credit_supported": bool(all(gates.values())),
        "claim_boundary": (
            "Controlled tabular-Q replication with primitive price paths held "
            "fixed. Passing identifies multi-step temporal credit, not live-router "
            "causality, provider conduct, equilibrium, or collusion."
        ),
    }
    _write_run(result, "esim9")
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
    elif args.experiment == "E-SIM5":
        print(json.dumps(run_esim5(seeds=args.seeds), indent=1, default=str))
    elif args.experiment == "E-SIM6":
        result = run_esim6(seeds=args.seeds)
        print(
            json.dumps(
                {
                    "experiment": result["experiment"],
                    "primary": result["primary"],
                    "mechanism_gates": result["mechanism_gates"],
                    "delayed_credit_intervention_supported": (
                        result["delayed_credit_intervention_supported"]
                    ),
                },
                indent=1,
            )
        )
    elif args.experiment == "E-SIM7":
        result = run_esim7(seeds=args.seeds)
        print(
            json.dumps(
                {
                    "experiment": result["experiment"],
                    "eligible_markets": result["eligible_markets"],
                    "transport_gates": result["transport_gates"],
                    "cross_market_transport_supported": (
                        result["cross_market_transport_supported"]
                    ),
                    "market_summaries": {
                        model_id: {
                            "profile": market["profile"],
                            "regret": market["option_minus_primitive_regret"],
                            "option_success": market["option_success_profiles"],
                            "primitive_success": market["primitive_success_profiles"],
                            "gate": market["market_transport_gate"],
                        }
                        for model_id, market in result["markets"].items()
                    },
                },
                indent=1,
            )
        )
    elif args.experiment == "E-SIM8":
        result = run_esim8(seeds=args.seeds)
        print(
            json.dumps(
                {
                    "experiment": result["experiment"],
                    "passing_cells": result["passing_cells"],
                    "robustness_gate": result["robustness_gate"],
                    "cells": [
                        {
                            "alpha": cell["alpha"],
                            "beta": cell["beta"],
                            "regret": cell["option_minus_primitive_regret"],
                            "option_success": cell["option_success_profiles"],
                            "primitive_success": cell["primitive_success_profiles"],
                            "gate": cell["cell_robustness_gate"],
                        }
                        for cell in result["cells"]
                    ],
                },
                indent=1,
            )
        )
    elif args.experiment == "E-SIM9":
        result = run_esim9(seeds=args.seeds)
        print(
            json.dumps(
                {
                    "experiment": result["experiment"],
                    "primary": result["primary"],
                    "primitive_success_profiles": result["primitive_success_profiles"],
                    "n_step_success_profiles": result["n_step_success_profiles"],
                    "option_success_profiles": result["option_success_profiles"],
                    "mechanism_gates": result["mechanism_gates"],
                    "multi_step_credit_supported": result["multi_step_credit_supported"],
                },
                indent=1,
            )
        )
    else:
        raise SystemExit(f"unknown experiment {args.experiment}")


if __name__ == "__main__":
    main()
