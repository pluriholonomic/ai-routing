---
name: orcap-learned-provider-agents
description: Use when working on learned or behavioral provider pricing agents in the market environment — Calvano-style tabular Q-learning sellers, LLM-prompted pricing agents under the Fish-Gonczarowski-Shorrer protocol, fitted behavioral species strategies, the moment-validation harness (indirect inference against the observed panel), or collusion diagnostics (calvano_delta, cut response, deviation audits). Covers strategies_qlearn.py, strategies_llm.py, strategies_species.py, moments.py, diagnostics_collusion.py, experiments_sim.py.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orcap, simulation, marl, q-learning, llm-agents, collusion, validation]
    related_skills: [orcap-market-env-kernel, orcap-simulation-calibration, orcap-strategic-experiments]
---

# ORCAP Learned and Behavioral Provider Agents

## Overview

Three provider-agent tiers sit on top of the kernel's scripted baselines, plus
the validation and diagnostics machinery that decides what any of them may
claim. All implement the `ProviderStrategy` protocol from
`src/orcap/market_env/strategies.py`.

## Agent tiers

1. **Behavioral species** (`strategies_species.py`) — fitted to the
   split-sample-validated wf13 four-species classification:
   - `adopter`: quotes exactly the author/anchor price, follows anchor moves
     same epoch, tiny idiosyncratic hazard;
   - `below_static`: targets anchor*exp(margin), rare repricing hazard;
   - `below_active`: reprices around anchor with fitted cadence;
   - `above`: premium over anchor.
   Parameters come from the frozen calibration bundle (train window only).
   These are the E-SIM1 species-world agents.
2. **Tabular Q-learning** (`strategies_qlearn.py`) — Calvano-Calzolari-
   Denicolo-Pastorello (2020 AER) replication: the router IS the demand curve
   (inverse-square weights = softmax in log price), so their repeated
   Bertrand-with-logit-demand game nests directly. Training uses the router's
   EXPECTED allocation (probabilities x demand), not sampled route noise —
   this is the variance-reduction choice that makes tabular convergence
   tractable; document any change to it.
3. **LLM-prompted agents** (`strategies_llm.py`) — Fish-Gonczarowski-Shorrer
   protocol: each epoch the agent gets a plain-language market report (own
   cost band, public menu, own recent flow/profit) and returns a price. The
   PROMPT VARIANT is the treatment axis (e.g. "maximize long-run profit" vs
   neutral framing). Never let the prompt leak rival private state; the
   report builder is the information-structure enforcement point.

## Moment validation harness (moments.py)

Indirect inference: `moments.compute_moments` runs the SAME statistics on a
simulated trajectory as on the observed panel (`moments.observed_trajectory`,
daily grain, author-anchored markets). A simulation is validated against the
frozen targets in `docs/simulation-moments-preregistration.md`:

- dispersion (max/min ratio 1.34, sd log price 0.068);
- adopter atom share 0.834 (OOS persistence analog; weight 2);
- premium ladder (below_static -0.406, adopter 0.0, above +0.344 log);
- cadence per species per day (grain documented — sim epoch vs ledger);
- flow elasticity -0.78 (GATE, not fitted: same sign, within an order of
  magnitude; inherits the documented panel-length caveat).

E-SIM1 pass criteria: weighted `moment_distance` <= 0.04 AND no weight-2
moment off by > 35% AND the elasticity gate holds. Free parameters (menu-cost
kappa, hazard scale, demand noise sigma) tune ONLY against fitted-moment
distance — tuning against the elasticity gate is prohibited.

## Collusion diagnostics (diagnostics_collusion.py)

Applied to ANY converged strategy tier (behavioral, tabular-Q, LLM):

- `calvano_delta`: profit position between Nash and cartel benchmarks;
- `cut_response`: force one rival to cut, measure punishment/restoration
  dynamics (the EconEvals-style litmus);
- deviation audit: one-shot profitable-deviation scan of the frozen profile.

A coordination claim requires the full E7 gate (see
orcap-strategic-experiments): supra-competitive prices, low regret,
punishment/restoration-consistent deviation dynamics, replication across
algorithms, relabeling invariance. calvano_delta alone is never sufficient.

## Pitfalls

- Q-learning hyperparameters (exploration schedule, learning rate, state
  discretization) are pre-registered per experiment; do not tune on test
  outcomes.
- LLM agents: log prompt variant, model id, and seed in the run manifest;
  prompt-variant effects are the estimand, not noise. Keep API cost guards —
  cache identical reports, never call the API inside the kernel hot loop.
- Species agents: the adopter/below/above classification is fitted on train;
  re-deriving it on full-panel data leaks holdout information.
- All tiers: symmetric scenarios must be invariant under random provider
  relabeling; add the relabeling test when adding a tier.
