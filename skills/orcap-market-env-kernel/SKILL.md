---
name: orcap-market-env-kernel
description: Use when working on the strategic inference-provider market kernel in src/orcap/market_env/ — adding types, routers, strategies, or scenarios; debugging seeded reproducibility, capacity, or welfare accounting; writing kernel invariant tests; or deciding what belongs in the kernel versus adapters/calibration. Covers the vertical-slice architecture, scenario schema, and the mandatory accounting invariants.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orcap, simulation, market-kernel, strategic-routing, testing]
    related_skills: [orcap-simulation-calibration, orcap-router-conformance, orcap-strategic-experiments, orcap-repo-orientation]
---

# ORCAP Market Kernel

## Overview

`src/orcap/market_env/` is the framework-independent deterministic kernel for
the strategic provider-pricing game. It is the foundation for every later
layer (calibration, PettingZoo RL, executable-router conformance). The kernel
must stay free of RL frameworks, experiment-specific data loading, and network
calls.

Frozen scientific protocol: `experiments/strategic-routing-simulation-v1/preregistration.md`.
Execution plan: `docs/strategic-routing-simulation-execution-plan-2026-07-18.md`
(WP1 = this kernel). Analytical benchmark: `docs/strategic-routing-theory-v1.md`.

## Architecture (current state)

```
src/orcap/market_env/
  __init__.py      # public exports — keep in sync
  types.py         # Workload, ProviderSpec, ProviderAction, RequestOutcome,
                   # ProviderEpochResult, EpochResult, Availability enum
  kernel.py        # MarketKernel: request-level fallback, seeded settlement
  routers.py       # RouterMechanism ABC + InversePriceRouter, LowestCostRouter,
                   # RandomRouter, ReliabilityWeightedRouter
  strategies.py    # StaticStrategy, CostPlusStrategy, AuthorAnchorStrategy,
                   # UndercutStrategy (pure functions, no kernel mutation)
  strategies_species.py  # fitted behavioral species: adopter, below_static,
                   # below_active, above (wf13 four-species classification)
  strategies_qlearn.py   # Calvano-comparable tabular Q-learning sellers;
                   # router probabilities as expected demand curve
  strategies_llm.py      # LLM-prompted pricing agents (FGS protocol);
                   # prompt variant is the treatment axis
  theory.py        # symmetric_interior_price, symmetric_profit_gradient,
                   # unilateral_profit (SM1 closed forms)
  scenario.py      # MarketScenario + load_scenario (TOML, schema_version=1)
  calibration.py   # panel-fitted bundle writer (kernel-independent)
  moments.py       # moment harness: same statistics on sim trajectory and
                   # observed panel (indirect inference)
  diagnostics_collusion.py  # calvano_delta, cut_response, deviation audit
  experiments_sim.py       # E-SIM registered runs (E-SIM1 species-world gate)

config/strategic_routing_v1.toml          # frozen vertical-slice scenario
docs/simulation-moments-preregistration.md # frozen E-SIM1 validation targets
tests/test_market_env.py                  # invariant + theory tests
tests/market_env/                         # calibration, moments, species,
                                          # qlearn, llm_agent tests
```

The execution plan's target layout (`routers/`, `strategies/`, `diagnostics/`,
`adapters/` subpackages, `demand.py`, `queues.py`, `env.py`, `replay.py`,
`metrics.py`, `release.py`) is mostly unbuilt — extend the flat modules into
subpackages only when a second member of the family exists. Do not scatter
experiment data loading inside the kernel.

## Kernel invariants (must hold after every change)

These are tested in `tests/test_market_env.py`; any new mechanism must satisfy
all of them plus its own:

1. **Seeded bitwise reproducibility** — same base seed and scenario gives
   identical `EpochResult` sequences. Substreams use
   `MarketKernel._subseed(*parts)` (blake2b over `base_seed|parts`), so common
   random numbers hold across router treatments. Never call `random` directly
   in kernel code; draw through `self._uniform(...)` or a per-request
   `Random(self._subseed("route", epoch, request_index))`.
2. **Route probabilities sum to one** over the eligible set
   (`RouterMechanism.eligible` excludes WITHDRAWN, zero admitted fraction, and
   zero physical capacity). An empty eligible set returns `{}` and every
   request fails unserved — fail closed, never invent a provider.
3. **No service above capacity** — attempted requests per provider are capped
   at `floor(physical_capacity * admitted_fraction * degraded_multiplier)`;
   excess attempts become `capacity_rejections` and fall back.
4. **Each request terminates exactly once** — served by one provider or
   counted failed after exhausting `ordered_attempts` (truncated to
   `workload.max_attempts` when set).
5. **Fallback order has no duplicates** — `ordered_attempts` samples weighted
   without replacement.
6. **Internal transfers cancel from welfare** — payments appear in user
   utility and provider profit but not in `total_welfare`
   (= delivered value - latency cost - resource cost - capital cost -
   failure loss). Test: perturb quotes holding allocation fixed; welfare is
   unchanged.
7. **Monopoly reduction** — one provider must reproduce its direct
   queue/failure outcome.
8. **Inverse-square semantics match `orcap.routing_simulation`** on shared
   fixtures — the empirical surface and the strategic kernel use the same
   quote-cost rule.
9. **Zero/missing quotes fail closed** — `ProviderAction` validates
   finite positive quote at construction.

Performance gate (WP1): >= 25,000 provider-epoch transitions/sec for a
four-provider fixture on laptop CPU, excluding logging. Profile and vectorize
before any RL work if missed.

## Scenario schema (config/strategic_routing_v1.toml)

`load_scenario(path)` enforces `schema_version = 1` and rejects unknown
top-level fields. Required: `scenario_id`, `horizon_epochs`,
`demand_per_epoch`, `[workload]`, and one or more `[[providers]]`.

Workload fields: `name`, `input_tokens`, `output_tokens`, `delivered_value`,
`latency_cost_per_ms`, `failure_loss`, `fallback_latency_ms`, `max_attempts`
(null = attempt all). Provider fields: `provider`, `marginal_cost`,
`physical_capacity`, `capital_cost_per_slot`, `base_latency_ms`,
`reliability`, `degraded_capacity_multiplier`, `degraded_reliability_multiplier`.

The `max_attempts` margin matters economically: unlimited attempts make
technical-failure order-invariant (see
`experiments/strategic-routing-simulation-v1/amendment-2026-07-18-attempt-limit.md`);
`max_attempts = 1` makes first-route reliability allocative. Choose
deliberately per experiment, never silently.

## Theory anchors

`theory.py` encodes SM1: for inverse-power routing
`s_i = p_i^(-eta) / sum_j p_j^(-eta)`, the symmetric interior price is
`p* = eta(n-1)c / (eta(n-1) - n)`, finite exactly when `eta > n/(n-1)`; the
free-entry limit is `p*/c -> eta/(eta-1)` (inverse-square: 2c, Lerner 1/2).
New mechanisms should ship with an executable benchmark in `theory.py` plus a
recovery test, not only a doc claim.

## Common commands

```bash
uv run pytest tests/test_market_env.py tests/market_env/ -q
uv run ruff check src/orcap/market_env tests/test_market_env.py
```

Note: another workstream may be extending `market_env/` concurrently; if a
full-suite run shows a failure that vanishes on rerun or in isolation, re-check
`git status` and the newest file mtimes before assuming your change caused it.

## Claim boundaries

- Kernel outputs are **synthetic** evidence: simulated shares are never
  realized OpenRouter flow; fitted named-provider parameters initialize
  distributions over strategy parameters, reported by strategy class and
  provider type, never "Provider X uses strategy Y".
- Welfare is meaningful only with elastic demand, heterogeneous cost/quality,
  capacity, failure, or latency in the model; with identical costs and
  inelastic demand, prices are transfers (SM1 Prop. 2).
- Deterministic settlement is the default; an event-time engine is added only
  for last-look / asynchronous-quote-clock experiments.
