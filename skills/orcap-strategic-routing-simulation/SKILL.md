---
name: orcap-strategic-routing-simulation
description: Design, calibrate, execute, audit, and interpret ORCAP strategic routing simulations and paid OpenRouter route-calibration probes. Use when changing src/orcap/market_env, fitting provider or demand primitives, comparing router mechanisms, adding provider bidding or learning strategies, running E-SIM or E-MECH experiments, calibrating the inverse-price shadow router with H96 owned requests, or deciding whether a simulated result supports a mechanism, prediction, welfare, coordination, or live-market claim.
---

# ORCAP strategic routing simulation

Treat the simulation as a controlled mechanism laboratory, not a replica of
OpenRouter. Preserve the chain from public quote state, through paid H96
route-calibration evidence, to fitted primitives, synthetic counterfactuals,
and narrowly worded claims.

Read [references/simulation-protocol.md](references/simulation-protocol.md)
before changing the experiment design, adding a learner, fitting live data, or
promoting a result into the paper.

## Start from the question

Classify the task before editing:

1. **Kernel semantics:** routing, fallback, capacity, settlement, utility, or
   welfare. Work in `src/orcap/market_env/{types,kernel,routers,scenario}.py`.
2. **Behavior:** provider quote, admission, reaction, learning, or entry
   strategies. Work in `strategies*.py`; keep kernel state immutable.
3. **Calibration:** fit empirical primitives or validate simulated moments.
   Work in `calibration.py` and `moments.py`; never load panel data in the
   kernel.
4. **Router realism:** measure realized provider choices under public menus.
   Use H96 `capture_route_calibration.py` and its analysis; do not infer choices
   from quote arithmetic alone.
5. **Experiment:** compare mechanisms or strategies under paired random seeds.
   Work in `experiments_sim.py` or `experiments_mech.py` only after locating the
   frozen registry entry and gate.
6. **Executable-router conformance:** compare a repo router to the kernel
   adapter using the same frozen trace. Keep this separate from live-market
   calibration.

Completion criterion: name the economic question, unit of assignment,
treatments, outcome, counterfactual, calibration source, and maximum defensible
claim before running anything.

## Orient to the authoritative artifacts

Inspect, in order:

1. `git status --short`; preserve unrelated dirty-worktree changes.
2. `experiments/strategic-routing-simulation-v1/preregistration.md` and all
   applicable amendments.
3. `docs/strategic-routing-simulation-execution-plan-2026-07-18.md` and
   `docs/strategic-routing-theory-v1.md`.
4. The relevant implementation and tests under `src/orcap/market_env/` and
   `tests/market_env/`.
5. The calibration bundle at `output/market_env/calibration/<revision>/` and
   its data card.
6. The exact E-SIM/E-MECH output manifest, source fingerprint, seed ledger, and
   gate result.
7. For router realism, the H96 candidate, assignment, and owned-attempt tables;
   never inspect H81/H95 beyond their frozen release rules.

Do not treat a generated output directory as current merely because it exists.
Verify its code fingerprint, calibration revision, scenario, seeds, and gate.

## Preserve layer boundaries

Use this dependency direction:

```text
public quote and owned-route data
  -> immutable calibration bundle
  -> scenario adapter
  -> deterministic market kernel
  -> strategy or learner
  -> paired experiment runner
  -> diagnostics, uncertainty, and claim gate
```

Enforce these rules:

- Keep network calls, parquet loading, provider aliases, and named-provider
  labels out of the kernel.
- Represent named providers only in calibration inputs; report counterfactuals
  by strategy class or provider type unless a design directly identifies a
  named-provider quantity.
- Keep router mechanism, provider strategy, arrival process, service process,
  and accounting separate so each can be ablated.
- Use adapters to replay historical quote/demand states; never mutate archived
  observations to fit the simulator.
- Version every scenario and calibration bundle. Refuse silent defaults for
  missing cost, capacity, reliability, or user value.

## Build or change the kernel

Maintain all invariants:

- Same scenario and seed produce identical request and settlement paths.
- Common-random-number substreams remain identical across router treatments.
- Eligible route probabilities are non-negative and sum to one.
- A request terminates exactly once as served or failed.
- Attempted and served load never exceed admitted physical capacity.
- Fallback sequences contain no repeated endpoint.
- Internal payments cancel from total welfare.
- Missing or non-positive quotes fail closed.
- A one-provider market reduces to the direct service process.
- Shared inverse-price fixtures agree with `orcap.routing_simulation`.

Add a theory recovery test whenever a mechanism has an analytical benchmark.
Add an accounting identity test whenever a payoff or welfare component changes.

## Add a provider strategy

Implement a strategy as a deterministic action rule conditional on an explicit
information set and a passed RNG/subseed. Declare:

- observed state and private state;
- feasible quote and admission actions;
- update clock and quote latency;
- objective and discounting;
- memory available to the agent;
- capacity and cost constraints;
- whether the strategy is heuristic, fitted, optimal, or learned.

Test a static state, a unilateral deviation, a capacity boundary, and seeded
repeatability. Compare any learner with a static baseline, myopic best response,
and exact or grid-search oracle when tractable. Reward economic profit; treat
routed share as an outcome, not the default reward.

## Calibrate without leaking the test set

Use the earliest 60% of eligible dates for fit, the next 20% for model choice,
and the final 20% once for evaluation. Add grouped model-family and
provider-type holdouts where support permits.

For each primitive, record:

- source table and grain;
- eligibility and missingness;
- transformation and estimator;
- train, validation, and test dates;
- parameter or identified set;
- uncertainty and fallback;
- held-out score relative to a simple baseline.

Replace a failed fit with an empirical bootstrap or sensitivity band. Do not
hide a failed predictive gate inside a more flexible learner.

## Use H96 to calibrate router realism

H96 is an owned-request calibration panel, not market-wide routing data. Its
frozen two-day pilot crosses six multi-provider open-weight models, four
request shapes, and eight assignments per model-shape block:

- three budget-bounded default draws with independent session IDs;
- one explicit `provider.sort = price` draw;
- two exact endpoint-tag pins with fallback disabled;
- one default sticky seed and one repeat using the same session ID.

Use unique prompt nonces for independent draws and one shared nonce only inside
the sticky pair. Persist hashes, assignments, public candidates, selected
provider, latency, tokens, and cost; never persist prompts, completions, API
keys, or raw session IDs.

Estimate default-choice probabilities from compatible public candidate menus.
Compare the documented inverse-square exponent under both a request-shaped
all-in quote and a mean prompt/completion price index with a held-out fitted
exponent. Add provider effects only after support is adequate, and retain a
price-sort deterministic benchmark. Report candidate-set coverage, log loss,
Brier score, top-choice accuracy, total-variation error, cost regret, pinned
success, and sticky-repeat agreement. A selected provider name does not
identify an exact endpoint variant.

Never modify H81 or H95 to obtain H96 calibration data. Keep all three study
IDs, workflows, tables, and claim boundaries separate.

## Run experiments as paired designs

Freeze treatments, seeds, horizon, calibration draws, outcomes, and gates
before confirmatory execution. Use common random numbers across router arms.
Treat a training seed or calibration draw as the independent unit; epochs and
requests are repeated observations within it.

Use the repository ladder:

1. deterministic smoke test with no inferential output;
2. screening run for implementation and effect direction;
3. registered confirmatory run at the frozen horizon;
4. exact benchmark, deviation, and leave-one-market/provider-type audits;
5. immutable result bundle and claim gate.

Do not tune after seeing confirmatory outcomes. Preserve negative results and
failed gates. Add a dated amendment before a changed design is executed.

## Diagnose strategic coordination carefully

Never label a high-price path collusion from price level or concentration alone.
Require all of:

- price above a competitive benchmark with stable delivered service;
- payoff improvement relative to competitive play;
- profitable unilateral-deviation audit or approximate exploitability bound;
- response to an exogenous rival price cut;
- punishment/recovery dynamics that disappear under a memory or observability
  ablation;
- robustness across seeds, calibrations, cost/capacity bands, and unseen
  strategies.

Call results `supra-competitive coordination in the simulated mechanism` until
the full gate passes. Never translate a simulated coordination result into
provider conduct without direct empirical evidence.

## Evaluate welfare and mechanism performance

Report user utility, provider profit, router revenue/cost, harness value if
modeled, total welfare, delivered quality, latency, failure, payment,
concentration, capacity utilization, and entry/survival separately.

Compare each proposed mechanism with inverse-square, lowest-cost,
reliability-weighted, randomized, and welfare-oracle controls where supported.
Report price of anarchy or welfare regret only against a feasible oracle using
the same information and capacity constraints. If cost, quality, capacity, or
user value is set rather than identified, report welfare over the frozen
sensitivity band and show sign-change boundaries.

## Validate and hand off

Run the smallest relevant tests first, then the full market-environment suite:

```bash
uv run pytest tests/test_market_env.py tests/market_env/ -q
uv run ruff check src/orcap/market_env tests/test_market_env.py tests/market_env
uv run python -m orcap.market_env.experiments_sim --experiment E-SIM1
```

For H96, also run its collector and analysis unit tests, then a remote
`--preflight-only` workflow dispatch before any paid schedule. Verify the
artifact contains candidate and assignment tables but zero attempts.

Hand off with:

- exact code and calibration revisions;
- scenario, treatments, seeds, horizon, and independent unit;
- empirical versus simulated inputs;
- gate result and all failed components;
- effect sizes and intervals;
- sensitivity boundaries;
- paths to immutable artifacts;
- one explicit sentence stating what the result does not establish.
