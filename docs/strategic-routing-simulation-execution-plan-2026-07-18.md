# Strategic routing simulation: execution plan

**Date:** 2026-07-18
**Status:** implementation-ready plan
**Companion survey:** docs/open-source-routing-strategic-simulation-2026-07-18.md

## 1. Decision and target

Build a strategic provider market around a fast deterministic kernel in this
repository. Expose it through PettingZoo for multi-agent learning, but keep the
kernel free of any RL framework. Validate the kernel against executable routing
code in two stages:

1. LiteLLM for the first router-conformance baseline.
2. llm-d Router plus llm-d Inference Sim for the main executable systems test.

The first scientific object is a repeated provider-pricing and capacity game
for one fixed model and workload at a time. Provider agents choose public quote,
admitted capacity, and availability. A fixed router allocates requests. The
environment settles profit, user utility, reliability, and transfer-free social
welfare.

The first release should answer four questions:

1. How much do router rules change prices, reliability, concentration, profit,
   and welfare when providers react strategically?
2. When does faster repricing create Brown-MacKay competitive commitment, and
   when does it instead facilitate coordination?
3. Can reserved-capacity and author-price-anchoring types explain persistent
   public price gaps?
4. Can a router improve welfare by changing price sensitivity, reliability
   penalties, exploration, or capacity certification?

## 2. Claim boundaries

The simulation will support mechanism counterfactuals conditional on explicit
calibration assumptions. It will not, by itself:

- identify a named provider's private cost, capacity, strategy, or profit;
- turn public simulated routed share into realized market-wide flow;
- establish that observed repricing is collusion or front-running;
- estimate the equilibrium effect of a new router by replaying fixed historical
  quotes;
- call all Hugging Face-linked models open source without a separate license
  audit.

Named providers can supply input observations. Published strategic conclusions
must be type-conditioned or identified-set statements unless partner data
identify private primitives.

## 3. Formal environment

### 3.1 Market unit

The atomic market is:

    market = (model, workload shape, region, quote epoch)

A workload shape contains input tokens, output tokens, required features,
latency value, failure loss, and delivered-quality value. Version 1 uses the
four existing routing-simulation workloads: short chat, long context, tool chat,
and structured chat.

One episode spans enough five-minute epochs to contain both quote updates and
demand cycles. The default is seven days:

    12 epochs/hour x 24 hours/day x 7 days = 2,016 epochs

Short smoke episodes use 288 epochs. Long coordination tests use 8,064 epochs
and discard a frozen burn-in prefix.

### 3.2 Timing

At epoch t:

1. Each provider receives its public observation and private state.
2. Providers simultaneously choose quote, admitted capacity, availability, and
   optionally quote TTL.
3. The demand process emits a batch of requests.
4. The router filters candidates, scores them, and returns an ordered attempt
   list plus ex-ante selection probabilities.
5. Requests enter provider queues and may succeed, fail, time out, or fall back.
6. The environment settles transfers, costs, penalties, profit, user utility,
   and welfare.
7. Public performance and enforcement signals update after a configurable lag.

The base kernel is tick-based. An optional event-time engine is added only for
last-look, asynchronous quote clocks, and within-epoch reaction experiments.

### 3.3 Provider observation

Provider i sees:

- own quote menu, queue, admitted and physical capacity, realized owned flow,
  failures, prior profit, and next quote-clock state;
- public rival quotes and eligible-set membership;
- delayed public latency, throughput, uptime, derank, and rate-limit signals;
- public or noisy routed-share feedback, if the scenario exposes it;
- model, workload, time, and demand-regime features.

It does not see rivals' private costs, physical capacity, queues, or realized
flow. An omniscient state is available only to audit code and an optional
centralized critic.

### 3.4 Provider action

Version 1 action:

    a_i,t = (
        delta_log_input_quote,
        delta_log_output_quote,
        admitted_capacity_fraction,
        availability_state
    )

Price moves are projected onto either an empirical provider/type price menu or
a fixed log-price grid. Capacity is in [0, 1]. Availability is active, degraded,
or withdrawn.

Version 2 adds quote TTL and post-route admission, which are needed for stale
quote and phantom-liquidity experiments.

### 3.5 Router rule

Every router implements:

    eligible(request, provider_public_states) -> candidates
    score(request, candidates, public_state) -> scores
    route(request, scores, rng) -> ordered attempts and probabilities
    observe(route_outcome) -> updated router state

The core parametric score is:

    score_i = price_i^(-eta)
              reliability_i^(alpha)
              capacity_headroom_i^(beta)
              exp(-gamma * predicted_latency_i)

This nests inverse-square routing at eta = 2 and alpha = beta = gamma = 0.
Deterministic lowest cost, random, round-robin, power-of-two, least-busy,
capacity-certified, and welfare-oracle rules are separate mechanisms rather
than forced into this formula.

### 3.6 Queue and delivery model

The fast kernel begins with a finite-capacity queue:

- provider capacity is tokens/second or concurrent service slots;
- service time is calibrated from prompt and completion tokens plus provider
  type;
- congestion increases time to first token and inter-token latency;
- requests beyond queue/admission limits reject or time out;
- fallback attempts pay additional latency and router cost.

The default surrogate is deliberately simple and monotone. It is promoted only
if held-out llm-d Inference Sim and Vidur grids pass the fidelity gate in
Section 11.

### 3.7 Accounting

Provider epoch profit is:

    profit_i =
        delivered payments
        - variable inference cost
        - reserved-capacity capital cost
        - failure and shortfall penalties
        - quote/update menu cost

User utility is:

    user value from delivered quality
        - payment
        - latency disutility
        - failure loss

Closed-system welfare is:

    delivered value
        - resource cost
        - capacity capital cost
        - latency external cost
        - failure external cost
        - real router operating cost

Provider payments, router fees, and penalties that remain inside the modeled
system cancel from global welfare. They remain in agent utilities and
participation constraints.

## 4. Repository architecture

Add the following package:

    src/orcap/market_env/
      __init__.py
      types.py
      scenario.py
      kernel.py
      accounting.py
      queues.py
      demand.py
      env.py
      replay.py
      calibration.py
      metrics.py
      release.py
      routers/
        base.py
        inverse_price.py
        lowest_cost.py
        systems.py
        certified_capacity.py
        welfare_oracle.py
      strategies/
        base.py
        scripted.py
        brown_mackay.py
        capacity.py
        learned.py
      diagnostics/
        best_response.py
        exploitability.py
        collusion.py
        impulse_response.py
      adapters/
        litellm.py
        llmd.py
        vllm.py

Mirror the package in tests/market_env/. Do not put experiment-specific data
loading inside the kernel.

Add CLI commands:

    orcap market calibrate
    orcap market simulate
    orcap market train
    orcap market evaluate
    orcap market conformance
    orcap market release

All commands take a versioned YAML scenario and emit a manifest containing code
commit, input-data revision, dependency lock hash, scenario hash, seeds, and
output hashes.

## 5. Work package 0: freeze the scientific protocol

**Duration:** 1-2 engineer days
**Dependency:** none

### Tasks

1. Write experiments/strategic-routing-simulation-v1/preregistration.md.
2. Freeze primary router mechanisms, provider types, demand regimes, cost bands,
   seeds, estimands, and multiplicity families.
3. Freeze the distinction among historical replay, calibrated counterfactual,
   and executable conformance.
4. Predeclare promotion gates for empirical calibration, systems fidelity,
   equilibrium robustness, and paper claims.
5. Create a scenario schema with explicit units and bounds.

### Primary estimands

- mean transfer-free welfare per request;
- user utility and user payment per successful request;
- failure and fallback probability;
- p50 and p95 end-to-end latency;
- provider profit, markup, and survival/participation;
- HHI, top-provider share, and effective provider count;
- normalized price of anarchy relative to the welfare oracle;
- best-response regret and dynamic deviation gain.

### Gate

No RL training begins until every estimand has a tested accounting definition
and the scenario schema rejects ambiguous units.

## 6. Work package 1: deterministic vertical slice

**Duration:** 4-6 engineer days
**Dependency:** WP0

### Scope

One model, one workload, two providers, Poisson demand, fixed cost/capacity,
inverse-square and lowest-cost routers, and four scripted provider policies.

### Tasks

1. Implement immutable Request, ProviderState, ProviderAction, RouteAttempt,
   Settlement, and MarketState types.
2. Implement seeded demand generation and deterministic state transitions.
3. Implement inverse-square routing by reusing the exact quote-cost semantics
   in src/orcap/routing_simulation.py.
4. Implement lowest-cost, random, and welfare-oracle controls.
5. Implement capacity, queue, fallback, and failure transitions.
6. Implement profit, utility, and welfare settlement.
7. Add static-price, cost-plus, undercut, and author-anchor strategies.
8. Add trajectory logging with payload-free synthetic study IDs.
9. Add a historical-snapshot adapter that can initialize a market without
   mutating or querying analysis outputs at runtime.

### Required tests

- seeded runs are bitwise reproducible;
- route probabilities sum to one over eligible providers;
- no provider serves above admitted or physical capacity;
- each request terminates exactly once;
- fallback order contains no duplicate provider;
- internal transfers cancel from welfare;
- a one-provider monopoly reduces to its direct queue outcome;
- inverse-square probabilities match orcap.routing_simulation on fixtures;
- the welfare oracle weakly dominates feasible fixed rules on system cost;
- zero and missing quotes fail closed.

### Performance gate

On a laptop CPU, the kernel must sustain at least 25,000 provider-epoch
transitions per second for a four-provider fixture, excluding logging. If it
misses this gate, profile and vectorize before adding RL.

### Deliverable

A command that runs a seven-day two-provider scenario and writes a deterministic
summary, trajectory sample, and manifest in under one minute.

## 7. Work package 2: frozen calibration artifact

**Duration:** 5-8 engineer days
**Dependency:** WP0; can overlap late WP1

### Input tables

- endpoint and routing_simulation snapshots;
- pricing_changes and BM1-BM5 outputs;
- H19 provider feature/type panel;
- router_route_attempts for owned-traffic reliability, latency, cost, and
  fallback;
- router enforcement and capacity panels;
- app/model token and ranking panels;
- llm-d/Vidur synthetic service profiles;
- a separately sourced provider-capital and first-party-reference ledger.

### Calibration strata

Prespecify strata before fitting:

1. model author or first-party provider;
2. author-price anchor or apparent list-price passthrough;
3. large reserved-capacity infrastructure provider;
4. funded specialist inference provider;
5. small or elastic-capacity inference startup;
6. broad multi-model aggregator/host;
7. unknown.

Capitalization, financing announcements, and data-center claims are noisy
public labels, not capacity measurements. Use them as coarse priors or strata,
then run a label-free sensitivity analysis.

### Fitted objects

1. Candidate-set and quote-state bootstrap by model/workload/date.
2. Provider/type quote menu and price-change-size distribution.
3. Quote-clock hazard or renewal distribution.
4. Brown-MacKay strictly-prior rival-response prior with hierarchical
   shrinkage.
5. Service-time, rejection, failure, and fallback models.
6. Provider-type capacity low/base/high bands.
7. Model/workload demand-regime transitions.
8. Poisson, negative-binomial, and Hawkes arrival alternatives where arrivals
   are genuinely observed.
9. User value and quality bands from cached benchmark/eval outcomes.
10. Cost identified sets rather than point estimates.

### Split

Freeze:

- train: earliest 60% of eligible dates;
- validation: next 20%;
- test: latest 20%;
- grouped holdout by model so at least one model family is never used for fit;
- provider-type holdout for transport checks.

No random row split is allowed for time-series behavior.

### Predictive gates

- quote-clock model beats a type-only hazard on held-out log score;
- reaction prior beats own-state-only prediction on the frozen temporal test,
  with the existing paired model-cluster test;
- service model improves held-out CRPS/log score over provider-type medians;
- simulated quote transitions reproduce change rate, step-size distribution,
  cross-provider dispersion, and persistence within prespecified tolerances;
- coverage and missingness are published for every fitted object.

If a fitted object fails, replace it with a transparent empirical bootstrap or
wide sensitivity band. Do not hide a failed calibration behind a neural policy.

### Deliverable

A single immutable calibration bundle:

    calibration/strategic-routing-v1/<revision>/
      calibration.parquet
      cost_bands.parquet
      service_profiles.parquet
      scenario_support.parquet
      split_manifest.json
      calibration_report.json
      data_card.md

## 8. Work package 3: scripted provider strategy library

**Duration:** 3-5 engineer days
**Dependency:** WP1, calibration schema from WP2

Implement each strategy as a pure function of observation, internal memory, and
seed:

1. static quote and capacity;
2. author-price anchor with adjustable multiplier;
3. cost-plus markup;
4. one-tick undercut subject to margin floor;
5. Brown-MacKay fast reactor using only strictly prior public rival moves;
6. Calvo/menu-cost updater;
7. capacity-aware price shading and withdrawal;
8. stale quote plus post-route rejection;
9. Edgeworth capacity cycle;
10. random policy;
11. joint-profit oracle for an upper bound.

### Strategy recovery tests

- cost-plus converges to its target absent shocks;
- undercut never violates its margin floor;
- fast reactor cannot use simultaneous or future rival moves;
- Calvo frequency matches its configured hazard;
- capacity-aware shading is monotone in queue utilization;
- stale-quote policy separates attempted share from served share;
- joint-profit oracle never appears in a decentralized treatment.

### Causal use

Fitted named-provider parameters initialize a distribution over strategy
parameters. The simulator reports results by strategy class and provider type,
not “Provider X uses strategy Y.”

## 9. Work package 4: PettingZoo and learning

**Duration:** 5-8 engineer days
**Dependency:** WP1 and WP3

### Environment API

Wrap the kernel in InferenceMarketParallelEnv:

- one agent per provider;
- simultaneous quote-epoch actions;
- variable active-agent set for entry/exit;
- action and observation spaces generated from the scenario;
- global state only for centralized critics and diagnostics;
- terminated at episode horizon; truncated only by explicit safety limits.

Pass PettingZoo parallel_api_test and deterministic seeding tests.

### Training ladder

Do not begin with large neural policies.

1. Two providers, one price action, tabular Q-learning.
2. Two providers, price and capacity, independent tabular/Q-network agents.
3. Four providers, discrete price grid, independent PPO.
4. Four providers, continuous quote/capacity, PPO and SAC.
5. Recurrent policy only if delayed/noisy public state materially improves
   held-out reward.
6. Router-as-leader only after provider best-response tests pass.

### Reward

Provider reward is discounted economic profit. Routed share is logged but never
the default reward. Add a separate intentionally misspecified share-reward
treatment to measure reward hacking.

### Training protocol

- independent training and evaluation seeds;
- at least 10 training seeds in screening, 30 for promoted findings;
- common random numbers across router treatments;
- fixed checkpoint-selection rule based on validation reward;
- no selection on test welfare or collusion index;
- save aggregate learning curves and sparse audit trajectories, not every raw
  step;
- label nonconvergent runs and retain them in intent-to-train summaries.

### Sanity gates

- learned policies beat their static initialization on validation profit;
- tabular agents recover known two-provider benchmarks;
- a scripted one-step best response improves reward when regret is positive;
- random provider relabeling leaves symmetric scenarios invariant;
- conclusions survive at least two learning algorithms before being described
  as emergent strategic behavior.

## 10. Work package 5: router adapters and conformance

**Duration:** 7-12 engineer days
**Dependency:** WP1; can overlap WP4

### 10.1 LiteLLM

Implement first because it is Python-native and gives the shortest feedback
loop.

1. Represent each simulated provider as a local mock deployment.
2. Test weighted, lowest-cost, least-busy, latency, usage/rate-limit, and custom
   quote-score selection.
3. Feed identical provider snapshots to the surrogate and real router.
4. Run at least 10,000 selections per stochastic state.
5. Compare eligibility, deterministic choices, and stochastic selection
   frequencies.

### 10.2 llm-d Router plus Inference Sim

Run remotely on Linux with containers and Kind/Kubernetes.

1. Start one Inference Sim deployment per provider type.
2. Calibrate service profiles and failure injection.
3. Publish quote, capacity-headroom, queue, and latency endpoint metrics.
4. Add a quote scorer that returns price to the minus eta.
5. Compose quote, queue, latency, and reliability scorers with the stock
   weighted-random picker.
6. Replay controlled request traces under the same scenarios as the fast
   kernel.
7. Record selected endpoint, fallback, latency, throughput, queue state, and
   failure under a synthetic study ID.

### 10.3 vLLM Router

Use random, round-robin, power-of-two, and cache-aware policies as independent
non-price systems controls.

### Conformance gate

- candidate eligibility agrees exactly on supported fixtures;
- deterministic router choices agree exactly;
- each stochastic provider share lies inside its simultaneous 95% Monte Carlo
  interval and absolute error is at most two percentage points;
- fallback order and exclusion reasons agree;
- fast-kernel latency/failure distributions pass the systems-fidelity gate;
- disagreements are reported as adapter limitations, not averaged away.

## 11. Systems-fidelity gate

Fit the fast queue surrogate on one llm-d/Vidur grid and validate on a disjoint
grid over:

- request input/output length;
- provider service speed;
- concurrent load;
- queue limit;
- cache hit rate;
- failure and timeout rate;
- fallback depth.

Primary fidelity metrics:

- median and p95 latency relative error;
- Wasserstein distance for latency distribution;
- throughput relative error;
- failure and fallback calibration error;
- rank correlation of provider service quality.

Promotion thresholds:

- median latency relative error <= 10%;
- p95 latency relative error <= 20%;
- throughput relative error <= 10%;
- failure/fallback absolute calibration error <= 3 percentage points;
- provider ranking Spearman correlation >= 0.9.

If the surrogate misses a gate, systems conclusions must be rerun through the
executable backend or narrowed to accounting/mechanism outcomes.

## 12. Experiment suite

### E0. Benchmark recovery

**Purpose:** establish that the environment can recover known competition and
joint-profit controls.

**Treatments:** marginal-cost pricing, static Nash benchmark where computable,
joint-profit oracle, tabular learned agents.

**Primary test:** learned outcomes lie near the appropriate benchmark in simple
two-provider games; deviation regret is small after convergence.

**Promotion gate:** normalized regret <= 0.05 in at least 90% of promoted seeds.

### E1. Router mechanism benchmark

**Treatments:** inverse-square, eta grid, lowest-cost, weighted random,
least-busy, power-of-two, capacity-certified, and welfare oracle.

**Variation:** low/base/high load, homogeneous/heterogeneous costs,
homogeneous/heterogeneous capacity, reliable/unreliable providers.

**Primary outcomes:** welfare, user payment, failure, latency, profit, HHI,
price of anarchy.

**Hypothesis:** stronger price weight reduces quotes under spare capacity but
can lower welfare under congestion or unreliable cheap capacity.

### E2. Brown-MacKay clock asymmetry

**Treatments:** one provider's observation/update clock varies while cost,
capacity, and information are held fixed.

**Primary outcomes:** own price, own profit, routed share, rivals' prices,
consumer surplus.

**Support pattern:** the fast provider charges less and earns more while slow
rivals' prices rise. This is labeled competitive commitment, not collusion.

**Falsification:** shuffle provider clocks after preserving costs and capacity;
remove rival-price observability; use simultaneous-only information.

### E3. Price sensitivity and tick size

**Treatments:** eta in {0, 0.5, 1, 2, 4, 8}; empirical and counterfactual price
ticks; deterministic versus stochastic selection.

**Primary outcomes:** pass-through, markup, volatility, HHI, failure, welfare.

**Question:** where does price competition become a winner-take-most capacity
race?

### E4. Reserved-capacity provider types

**Treatments:** large reserved capacity/low short-run marginal cost, elastic
cloud capacity, small fixed capacity, and mixed markets.

**Hold fixed:** service quality, model, router, and demand draws in the first
factorial block.

**Primary outcomes:** price gap, utilization, peak-load markup, profit,
shortfall, entry/exit.

**Empirical bridge:** compare simulated conditional price gaps with held-out
H19/capital-strata gaps. Treat correspondence as model fit, not causal proof.

### E5. Author-price anchoring

**Treatments:** author anchor, cost-plus, undercut, fast reactor, and mixtures.

**Primary outcomes:** profit, survival, price dispersion, consumer surplus,
response to author reference-price shock.

**Question:** when is copying the model author's list price rational, and when
is it dominated?

**Falsification:** use placebo reference prices from unrelated models and
reference-price changes after the simulated epoch.

### E6. Stale quotes and phantom liquidity

**Treatments:** quote TTL, delayed refresh, post-route admission probability,
fallback policy, and derank penalty.

**Primary outcomes:** quoted share, attempted share, served share, fallback
cost, adverse-selection loss, welfare.

**Support pattern:** low stale quotes attract first attempts but fail to convert
to served requests and impose fallback/latency cost.

**Empirical bridge:** owned route attempts and enforcement-event aggregates,
with no market-wide-flow claim.

### E7. Emergent coordination

**Treatments:** independent PPO/SAC sellers under inverse-price, deterministic
lowest-cost, exploratory, and derank-penalty routers.

**Primary diagnostics:**

- normalized collusion index between competitive and joint-profit price;
- one-shot and dynamic deviation gain;
- best-response exploitability;
- undercut impulse response;
- punishment depth and restoration time;
- entry and leave-one-provider-out response.

**Claim gate:** high prices alone never count. A coordination claim requires
supra-competitive prices, low equilibrium regret, profitable-deviation
dynamics consistent with punishment/restoration, replication across algorithms,
and survival under provider relabeling.

### E8. Welfare-optimizing router

**Structure:** Stackelberg problem. The router commits to price, reliability,
capacity, exploration, and derank weights; providers learn/respond; the router
optimizes held-out user welfare subject to participation and reliability.

**Constraints:**

- provider expected profit >= outside option by type;
- failure <= policy threshold;
- latency p95 <= service-level threshold;
- no provider selected above certified/admitted capacity;
- optional router budget balance.

**Evaluation:** train router against one family of provider policies and test
against unseen strategies, costs, capacities, and demand regimes.

### E9. Entry and fragmentation

**Treatments:** number of providers, setup cost, reserved capacity, cache
fragmentation, and minimum-flow viability.

**Primary outcomes:** welfare, price, concentration, latency, cache hit rate,
provider survival.

**Question:** identify the region where free entry stops helping because flow
fragmentation and duplicated fixed capacity dominate competitive gains.

### E10. Harness/model-provider interaction

Add a nonstrategic model router first, then an optional harness agent.

**Treatments:** fixed model demand, RouteLLM/RouterBench-style quality-cost
routing, and joint model-provider routing.

**Primary outcomes:** end-to-end quality-adjusted utility, model concentration,
provider competition, and investment incentives.

**Boundary:** model routing and same-model provider procurement are reported as
separate decisions even when jointly optimized.

## 13. Statistical design

### Screening

For each experiment:

- 10 independent training seeds;
- 20 evaluation seeds per trained policy;
- 5 calibration draws;
- common demand and failure draws across router treatments.

Screen only for implementation failures, effect scale, and variance. Do not
publish screening p-values.

### Confirmatory simulation

For promoted contrasts:

- 30 independent training seeds;
- 50 held-out evaluation seeds;
- 20 calibration posterior/bootstrap draws;
- at least three demand regimes and two model-family holdouts.

The independent unit is the training seed or calibration draw, not an epoch or
request. Use paired treatment differences under common random numbers.

Report:

- mean and median paired effect;
- percentile and studentized bootstrap intervals over independent seeds;
- randomization/sign-flip p-values when the paired design supports them;
- family-wise Holm correction within each preregistered experiment;
- full distribution and sign stability, not only a p-value.

### Mechanism uncertainty

Decompose uncertainty into:

1. demand/process randomness;
2. RL training randomness;
3. calibration uncertainty;
4. private-cost/capacity identified-set uncertainty;
5. executable-router approximation error.

A result is robust only if its sign survives the prespecified cost/capacity
band. Otherwise report the boundary at which the sign changes.

## 14. Compute and storage plan

### Local development

- unit and invariant tests: under 3 minutes;
- vertical-slice seven-day scenario: under 1 minute;
- scripted screening suite: under 30 minutes on a laptop;
- no container or GPU dependency.

### Remote CPU simulation

Initial target:

- 5,000-10,000 epochs per episode;
- 10-30 training seeds;
- 4-8 providers;
- 2-6 router treatments per experiment.

Benchmark first. Budget a screening cap of 500 CPU-hours and a confirmatory cap
of 3,000 CPU-hours. Stop jobs that fail learning or accounting gates; do not
increase compute merely to find significance.

### Executable conformance

- LiteLLM: local/CI, 10,000 route draws per stochastic fixture;
- llm-d: remote Linux runner, 3-6 synthetic provider pods, 10,000-100,000
  requests across promoted fixtures;
- Vidur: offline held-out service grid;
- no GPU required for the initial conformance suite.

### Storage

Retain:

- scenario and release manifests;
- aggregate metrics per episode and seed;
- checkpoints used in frozen evaluation;
- sparse trajectories for deviation and impulse-response audits;
- executable conformance summaries and selected raw traces.

Do not retain every RL step. Target under 10 GB for version 1.

## 15. Remote workflow

Add .github/workflows/strategic-simulation.yml with three modes:

1. smoke on pull requests: invariants, PettingZoo API, tiny deterministic
   scenarios;
2. screening on workflow dispatch: scenario matrix with bounded CPU and
   artifact retention;
3. confirmatory release on a signed scenario manifest and immutable input-data
   revision.

The workflow must:

- check out an exact code commit;
- install from uv.lock;
- resolve and record one immutable Hugging Face dataset revision;
- refuse a dirty or mutable calibration input;
- use predeclared seeds from the scenario;
- shard by scenario, not by outcome;
- aggregate only after all intended shards finish;
- publish failed and nonconvergent runs;
- write a release manifest before rendering figures;
- never require this laptop to remain online.

Add a second remote workflow for llm-d conformance on a Linux/container runner.
Keep its results separate from the fast-kernel training outputs.

## 16. Milestones and gates

### M1. Deterministic market

**Target:** end of week 1
**Done when:** WP1 invariants and speed gate pass; inverse-square fixture matches
the existing simulator.

### M2. Calibrated scripted market

**Target:** end of week 2
**Done when:** frozen calibration bundle exists; transparent strategies run on
historical initial states; held-out predictive report is generated.

### M3. First router result

**Target:** middle of week 3
**Done when:** E1 scripted comparison runs remotely and LiteLLM conformance
passes.

### M4. Strategic learning

**Target:** end of week 4
**Done when:** tabular benchmark recovery and independent PPO/SAC sanity gates
pass; best-response diagnostics are automated.

### M5. Brown-MacKay and provider-type experiments

**Target:** end of week 5
**Done when:** E2, E4, E5, and E6 have screening reports, falsifications, and
cost/capacity sensitivity maps.

### M6. Executable and mechanism release

**Target:** weeks 6-7
**Done when:** llm-d conformance and systems-fidelity gates pass; E7-E9
confirmatory contrasts complete; immutable release bundle is published.

### M7. Paper integration

**Target:** week 8
**Done when:** every manuscript claim maps to an empirical, simulation, or
theory artifact; synthetic and observational evidence are visibly separated;
an adversarial EC/NeurIPS review cannot find an unqualified equilibrium or
named-provider claim.

## 17. Prioritized implementation order

Execute in this order:

1. protocol and scenario schema;
2. deterministic types, accounting, and inverse-square router;
3. two-provider vertical slice and invariant tests;
4. calibration bundle schema and historical snapshot adapter;
5. scripted strategies;
6. LiteLLM conformance;
7. E1 and E2 scripted pilots;
8. PettingZoo wrapper and tabular benchmark;
9. independent PPO/SAC plus regret audits;
10. E4-E7 strategic experiments;
11. llm-d/Vidur fidelity;
12. router-leader optimization and entry;
13. confirmatory remote release;
14. paper figures and claims.

Do not make llm-d infrastructure, a neural policy, or a full harness agent a
critical-path dependency for the first result.

## 18. Stop/go rules

### Stop and repair

- accounting or capacity invariants fail;
- held-out calibration is worse than transparent nulls;
- learned results disappear under provider relabeling;
- router adapter and executable code disagree beyond the conformance threshold;
- apparent collusion has large profitable unilateral deviations;
- conclusions depend on one seed, algorithm, model, or unreported cost point.

### Continue but narrow the claim

- private cost/capacity bands are wide;
- historical replay and calibrated equilibrium disagree;
- LiteLLM passes but llm-d systems fidelity fails;
- Brown-MacKay patterns are predictive but not causally identified in public
  data;
- provider-capital labels improve fit but are unstable under label-free
  clustering.

### Promote

- invariant, calibration, conformance, equilibrium, and robustness gates pass;
- result survives frozen holdouts and private-primitive sensitivity;
- the effect has economic magnitude, not only statistical significance;
- paper language matches the actual evidence object.

## 19. Definition of complete

Version 1 is complete when the repository contains:

1. a framework-independent deterministic market kernel;
2. a PettingZoo provider environment;
3. an immutable calibration bundle and data card;
4. transparent and learned provider strategies;
5. inverse-price, systems, certified-capacity, and welfare-oracle routers;
6. LiteLLM and llm-d conformance reports;
7. automated profit, welfare, concentration, regret, and collusion diagnostics;
8. remote reproducible workflows and immutable result manifests;
9. preregistered E1-E9 reports with negative results retained;
10. a paper claim ledger that separates historical evidence, calibrated
    counterfactuals, executable conformance, and mechanism theory.

The recommended first implementation ticket is WP1: build the deterministic
two-provider vertical slice and prove the accounting and routing invariants.
That creates a useful result even if later calibration or RL work fails.
