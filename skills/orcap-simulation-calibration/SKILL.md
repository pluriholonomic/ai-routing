---
name: orcap-simulation-calibration
description: Use when building, validating, or consuming the frozen calibration bundle for the strategic market environment — fitting provider species, repricing hazards, rationing slopes, demand processes, cost bands, or service profiles from the captured OpenRouter panel; enforcing train/validation/test split discipline; or writing held-out predictive gate reports. Covers src/orcap/market_env/calibration.py and WP2 of the execution plan.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orcap, simulation, calibration, holdout, panel-data]
    related_skills: [orcap-market-env-kernel, orcap-strategic-experiments, orcap-repo-orientation, orcap-experiment-audit]
---

# ORCAP Simulation Calibration

## Overview

Calibration fits every simulator primitive that CAN be fitted from the
captured panel, on a frozen train window, and emits an immutable bundle that
any kernel version consumes. It is kernel-independent: reads parquet through
`src/orcap/analysis/data.py`, emits plain dicts/frames.

Execution plan WP2 (docs/strategic-routing-simulation-execution-plan-2026-07-18.md).
Implementation: `src/orcap/market_env/calibration.py`.

## Holdout discipline (hard rules)

1. **Time-based split only** — never a random row split for time-series
   behavior. Frozen: train = earliest 60% of eligible dates, validation = next
   20%, test = latest 20%. `calibration.py` fits on `train_frac` only.
2. **Grouped holdouts** — at least one model family is never used for fit;
   a provider-type holdout is kept for transport checks.
3. **Validation moments are never fitted anywhere** — flow elasticity,
   elasticity wedge, dispersion level, adopter level-persistence are scored,
   not tuned.
4. The last `1 - train_frac` of dates are never touched during fitting.

Violation of any of these invalidates every downstream simulation claim.

## Fitted objects and their sources

| Object | Source tables | Failure fallback |
|---|---|---|
| Candidate-set / quote-state bootstrap | endpoints_snapshots, routing_simulation | empirical bootstrap |
| Provider/type quote menu + price-change-size dist | pricing_changes | wide sensitivity band |
| Quote-clock hazard / renewal | pricing_changes, BM1-BM5 outputs | type-only hazard |
| Brown-MacKay strictly-prior rival-response prior | reaction panels (bm2) | own-state-only prediction |
| Service-time / rejection / failure / fallback | router_route_attempts, perf_comparisons_daily, llm-d/Vidur grids | provider-type medians |
| Capacity low/base/high bands | H19 type panel, capital-strata labels | label-free clustering sensitivity |
| Demand-regime transitions | model_activity_daily, rankings_weekly | Poisson null |
| Arrival process (Poisson / NegBin / Hawkes) | congestion_intraday where genuinely observed | Poisson |
| User value / quality bands | cached benchmark/eval outcomes | wide band |
| Cost identified sets | GPU spot book + throughput bands (THROUGHPUT_BAND_TOK_PER_GPU_HR) | identified set, never a point estimate |

Capitalization/financing/data-center claims are noisy public labels — use as
coarse priors or strata, then run a label-free sensitivity analysis. Never a
capacity measurement.

## Calibration strata (prespecified before fitting)

1. model author / first-party provider
2. author-price anchor / apparent list-price passthrough
3. large reserved-capacity infrastructure provider
4. funded specialist inference provider
5. small / elastic-capacity inference startup
6. broad multi-model aggregator/host
7. unknown

Existing helpers: `analysis.pm9_author_anchor.is_author_provider`,
`analysis.wf13_provider_strata.tier_of/tiers`, `OWNED_TIERS`.

## Bundle layout (immutable)

```
output/market_env/calibration/<revision>/
  bundle.json      # scalars: species params, repricing hazard, rationing
                   # slopes, demand process, cost bands, router steering
                   # penalty (CUT_PENALTY_THETA), train/holdout split
  pairs.parquet    # per (model, provider) classification + fitted margins
  data_card.md     # provenance, claim boundaries, holdout declaration
```

Target full bundle (WP2 deliverable) adds `calibration.parquet`,
`cost_bands.parquet`, `service_profiles.parquet`, `scenario_support.parquet`,
`split_manifest.json`, `calibration_report.json`.

## Predictive gates (all must pass or object is replaced)

- quote-clock model beats type-only hazard on held-out log score;
- reaction prior beats own-state-only prediction on the frozen temporal test
  (existing paired model-cluster test);
- service model improves held-out CRPS/log score over provider-type medians;
- simulated quote transitions reproduce change rate, step-size distribution,
  cross-provider dispersion, and persistence within prespecified tolerances;
- coverage and missingness published for every fitted object.

If a fitted object fails: replace with transparent empirical bootstrap or wide
sensitivity band. Never hide a failed calibration behind a neural policy.

## Consuming the bundle

The kernel and scenario loader stay calibration-free. Adapters translate
bundle rows into `ProviderSpec`/`Workload`/strategy-parameter distributions
at scenario-construction time. Named-provider parameters initialize
distributions over strategy parameters; report by strategy class and provider
type.

## Common commands

```bash
uv run pytest tests/market_env/test_calibration.py -q
# inspect a bundle
python -c "import json; print(json.load(open('output/market_env/calibration/<rev>/bundle.json')))"
```
