# Adaptive router adversarial-validation plan

**Date:** 2026-07-20  
**Status:** v1 screening executed remotely; v2 superseded before release after a
seed-integrity failure; corrected future-only v3 is frozen and remotely scheduled
**Applies to:** `openrouter-adaptive-monotone-v1` router family and the strategic-routing
market environment

## 1. Objective

Test whether the adaptive monotone router remains useful when inference providers can
change quotes, capacity, availability, and service quality in response to the allocation
rule. The target is not the unqualified statement that the mechanism is manipulation
proof. The target is a bounded robustness statement over a declared empirical support
and a declared family of unilateral and small-coalition deviations.

The validation program separates four evidence objects:

1. **Historical mechanical robustness:** perturb observed menus while holding the
   historical market state fixed.
2. **Calibrated strategic robustness:** endogenize provider actions in a simulation
   whose exogenous state transitions are fitted or bounded from historical data.
3. **Owned-traffic feasibility:** use randomized paid requests to estimate realized
   success, latency, cost, and quote firmness under emulated router allocations.
4. **Live strategic response:** only a sustained, observable deployment can identify
   whether providers reprice or withhold capacity because of the rule.

No result from one layer is substituted for another. In particular, a simulation does
not identify actual provider conduct, and a small paid-probe campaign does not identify
market-wide strategic response.

## 2. Noninterference with existing studies

The preregistered `openrouter-adaptive-monotone-v1` study remains unchanged. Its first
120 launched rectangular blocks, five arms per block, assignment procedure, outcome
definitions, budget ceilings, and analysis are frozen. No adversarial result is read or
used to modify that study.

All work below uses a new study namespace, provisionally
`adaptive-router-adversarial-v1`. Any additional paid study is separately
preregistered and starts only after its assignment and analysis code is committed.

## 3. Router treatments

Every empirical replay and strategic experiment includes the same core treatments:

1. `baseline_eta2`: public uptime times price to power -2.
2. `fixed_eta145`: the pre-study calibrated exponent.
3. `eta2_eps10`: inverse-square with ten-percent independent exploration.
4. `fixed_eta125_eps10`: the historical holdout-selected rule.
5. `menu_adaptive_raw`: the current per-menu constraint projection.
6. `menu_adaptive_hardened`: the proposed robust version.
7. `uniform`: diagnostic lower-information control.
8. `quality_adjusted_oracle`: simulation-only benchmark using the true simulated
   service state; never presented as deployable.
9. `welfare_oracle`: simulation-only benchmark where private primitives are known.

The hardened adaptive treatment has the following frozen design dimensions:

- policy parameters are committed for a fixed epoch rather than recomputed after every
  provider change;
- accepted provider quotes are locked within that epoch; an upward reprice is ineligible
  until the next commitment, while a cut enters the lagged score gradually;
- price and quality inputs are lagged exponentially weighted aggregates;
- quote age and quote-to-fill agreement enter eligibility or score penalties;
- provider-independent exploration has a positive floor;
- allocation gains obey a per-provider one-sided trust region; allocation losses caused
  by the provider's own higher price or worse quality are never protected;
- market share is capped at the economic-operator level;
- the parameter choice affecting provider `i` is computed from a leave-one-provider-out
  menu when feasible;
- the cross-provider log-share/log-price Jacobian is constrained directly.

These components are evaluated factorially before being combined. The promoted policy
must not be selected from the confirmatory test outcomes.

## 4. Formal estimands

Let `theta` be a router, `sigma` a provider-policy profile, and `omega` a market
environment containing demand, costs, capacities, service processes, and public-signal
noise. Provider `i`'s discounted profit is `U_i(theta, sigma, omega)`.

### 4.1 Unilateral exploitability

For a declared deviation class `D_i`,

```
X_i(theta, sigma, omega)
  = sup_{d in D_i} [U_i(theta, d, sigma_-i, omega)
                    - U_i(theta, sigma, omega)].
```

Report absolute gain, gain divided by baseline profit, and gain divided by market
payment. A zero found by one optimizer is not treated as a proof that the supremum is
zero.

### 4.2 Coalition exploitability

For coalitions of at most `k=2` providers in the primary study,

```
X_C(theta, sigma, omega)
  = sup_{d_C in D_C} sum_{i in C}
      [U_i(theta, d_C, sigma_-C, omega) - U_i(theta, sigma, omega)].
```

Three-provider coalitions are a sensitivity analysis. Coalition policies may share
public observations and internal state but cannot observe future demand or random
router draws.

### 4.3 User and system outcomes

For each treatment report:

- expected quoted and realized payment;
- request success and bounded latency;
- attempted and served provider shares;
- HHI, maximum share, and operator-level HHI;
- failure, rate-limit, stale-quote, fallback, and capacity-rejection rates;
- transfer-free welfare where simulated private primitives are known;
- welfare and provider-profit identified intervals where primitives are bounded;
- unilateral and coalition exploitability;
- worst-case regret relative to the feasible oracle;
- frequency and magnitude of router constraint violations.

### 4.4 Robust-router selection problem

The simulation-level design object is

```
min_theta sup_{omega in Omega} {
    user_regret(theta, omega)
  + lambda_u max_i X_i(theta, omega)
  + lambda_c max_{|C| <= 2} X_C(theta, omega)
  + lambda_v constraint_violations(theta, omega)
}.
```

The lambdas, uncertainty set `Omega`, and feasible policy grid are frozen before the
confirmatory run. Because public data do not identify user value or provider marginal
cost, the empirical analysis reports observable components and the simulation reports
results over cost/value bands.

## 5. Workstream A: historical adversarial replay

### A0. Freeze the historical population

Use one immutable Hugging Face revision. Build one provider menu per model-hour using
the same inclusion and collapse rules as the existing counterfactual. Freeze a 60/20/20
date split:

- training: select nuisance parameters and candidate hardening thresholds;
- validation: choose one promoted hardened policy;
- test: run once and report all outcomes.

Also freeze model-family and provider-type transport holdouts. Never split individual
rows randomly across time.

### A1. Single-provider quote manipulation surface

For every eligible provider-menu observation, replace that provider's quote by each
feasible multiplier in a frozen grid spanning substantial cuts and increases. Recompute
allocation and policy parameters without modifying other providers.

Primary outputs:

- maximum allocation gain from a quote perturbation;
- price paid per percentage point of allocation gained;
- discontinuity when the adaptive parameter changes;
- trust-region binding rate;
- effect on other providers' allocations;
- gain under each marginal-cost band.

The cost-free empirical estimand is allocation manipulability. Profitability is only an
identified interval over cost bands.

### A2. Quote fading and phantom liquidity

Construct attacks in which a provider posts a low price at menu freeze and then:

- rejects the request;
- rate-limits after a capacity threshold;
- restores its old quote;
- withdraws before execution;
- delivers at degraded latency or reliability.

Replay each attack using empirical failure, latency, rate-limit, and quote-lifetime
distributions. Compare instantaneous public quality, lagged realized quality, and the
quote-firmness penalty.

Primary estimands are attempted-versus-served share, bounded user loss, attacker's
profit interval, and the number of honest requests required before the penalty detects
the attack.

### A3. Timing and snapshot attacks

Shift observed quote changes relative to the five-minute capture clock and the policy
commitment boundary. Include just-before-snapshot, just-after-snapshot, and randomly
jittered timing.

This measures how much traffic can be captured by exploiting observation cadence. It
does not claim that any named provider actually uses the strategy.

### A4. Capacity withdrawal and quality shading

For each provider, apply low/base/high capacity and service shocks calibrated from
public ceilings, enforcement events, and owned attempts. Permit the provider to quote
cheaply while admitting only a fraction of physical capacity.

Compare policies on served share, queue failure, fallback, payment, and the divergence
between advertised and realized quality.

### A5. Sybil and operator-splitting attacks

Clone a provider into two through five nominal endpoints while preserving combined
physical capacity and cost. Compare endpoint-level and operator-level exploration,
share caps, and HHI.

A robust policy should not materially increase the combined allocation of a provider
merely because it splits identities. Where operator identity is unknown, report the
worst-case grouping sensitivity rather than assuming endpoint independence.

### A6. Coalition perturbations

For every two-provider pair on supported menus, search a bounded joint quote grid and
capacity-withdrawal grid. Measure joint gain and harm to users and nonmembers. Separate:

- parallel price increases;
- alternating undercuts;
- market division through capacity withdrawal;
- one provider acting as a low-price traffic attractor while the other remains high;
- common shocks in which both move for nonstrategic reasons.

This is a vulnerability audit, not an empirical collusion test.

### A7. Historical replay inference

The independent sampling unit is a model-day cluster. Report equal-weighted cluster
means and 95% cluster-bootstrap intervals. For maxima and worst-case statistics, also
report the median, 90th, 95th, and 99th percentiles so a single pathological menu is not
confused with typical performance.

## 6. Workstream B: calibrated strategic market simulation

### B0. Extend the environment

Add an `AdaptiveMonotoneRouter` implementation behind the existing
`RouterMechanism` interface. The environment state contains:

- current and lagged public quotes;
- current and lagged public and realized service signals;
- quote age and quote-to-fill history;
- physical and admitted capacity;
- provider group/operator identity where known;
- demand/load regime;
- router policy commitment state;
- provider-specific internal memory hidden from rivals and the router.

Provider actions include quote, admitted-capacity fraction, availability, and a bounded
service-effort choice. Every action must pass feasibility and accounting checks.

### B1. Calibration bundle

Build one immutable calibration release with:

- historical menu-state bootstrap;
- quote-change hazard and step-size distributions;
- strictly-prior rival-response transition models;
- service-time, failure, rejection, and rate-limit models;
- provider-type capacity bands;
- demand/load regimes;
- marginal-cost, fixed-capacity-cost, and user-value identified sets;
- a data card stating coverage and failed predictive gates.

Fit on the training dates, choose nuisance specifications on validation dates, and read
the test split once. A learned transition model must outperform a transparent empirical
bootstrap on held-out log score or be discarded.

### B2. Exact and scripted adversaries

Start with attacks whose behavior is inspectable:

1. global one-period price best response;
2. finite-horizon dynamic programming in two-provider discrete-action games;
3. cost-plus and author-anchor strategies;
4. one-tick and large-jump undercutting;
5. Calvo/menu-cost repricing;
6. Brown-MacKay fast reaction using only strictly prior information;
7. capacity-aware shading and withdrawal;
8. stale-quote plus post-route rejection;
9. snapshot-timing strategies;
10. joint-profit and two-provider coalition oracles.

The exact two-provider cases are ground truth for validating later learning and
black-box deviation searches.

### B3. Learning adversaries

Use a ladder rather than one favored algorithm:

1. UCB and Thompson-sampling price bandits;
2. tabular Q-learning on small Markov states;
3. independent DQN/PPO for discrete price and capacity;
4. PPO and SAC for continuous actions;
5. recurrent PPO/SAC when state memory is relevant;
6. black-box global optimization over interpretable reactive-policy parameters.

LLM agents may be retained as qualitative red-team policies but do not satisfy a
robustness gate.

Each learned strategy must beat its static initialization and a random strategy on
held-out profit. In low-dimensional fixtures it must recover the exact best response to
within a frozen tolerance.

### B4. Policy-space response-oracle loop

For every promoted router:

1. initialize the provider population with transparent strategies;
2. evaluate the current provider-policy mixture;
3. train multiple unilateral best-response candidates using independent algorithms and
   seeds;
4. globally search the interpretable reactive-policy class;
5. add every materially profitable deviation to the population;
6. repeat for two-provider coalition deviations;
7. re-optimize only the training-stage router over the expanded population;
8. stop after three consecutive iterations find no deviation above the frozen
   exploitability tolerance, or after a fixed maximum iteration count;
9. evaluate the frozen router and policy population once on confirmatory seeds and
   calibration draws.

Failure to find a deviation is reported as bounded exploitability relative to the
searched classes, never as proof of equilibrium.

### B5. General-equilibrium stressors

Cross the strategy population with:

- two, four, eight, and sixteen providers;
- spare, balanced, and scarce capacity;
- inelastic, moderately elastic, and high-elasticity demand;
- low, medium, and high public-signal noise;
- fast and slow provider update clocks;
- homogeneous and heterogeneous costs;
- provider entry, withdrawal, and fixed capacity costs;
- correlated and independent quality-price shocks;
- single-model and model-substitution demand.

The primary confirmatory factorial should remain small enough to execute completely.
Larger sweeps are sensitivity analyses and cannot replace the frozen cells.

### B6. Simulation inference

Screen with at least 10 independent training seeds. A promoted comparison uses:

- 30 independent training seeds;
- 50 held-out evaluation seeds per learned policy;
- 20 calibration/bootstrap draws;
- common demand and failure randomness across router treatments;
- whole-seed or whole-calibration-draw resampling;
- paired bootstrap intervals and sign-flip tests where valid;
- Holm correction within each preregistered hypothesis family.

Do not treat epochs, requests, or provider actions as independent observations.

## 7. Workstream C: empirical owned-traffic validation

### C1. Complete the existing paid study

Allow `openrouter-adaptive-monotone-v1` to reach exactly its first 120 launched blocks.
Its result estimates policy-emulated success, bounded latency, realized cost,
quote-to-fill slippage, and endpoint agreement. It does not estimate provider response.

Use it to calibrate or reject the service and quote-firmness components of the
simulator. Do not tune the original study or pool its outcomes into the later
confirmatory adversarial analysis.

### C2. New quote-firmness experiment

After C1 is frozen, preregister a second paid experiment that oversamples menus with:

- large price dispersion;
- a very cheap provider;
- recent quote changes;
- recent rate-limit or derank activity;
- disagreement between public uptime and owned-attempt history.

Randomize exact endpoint assignments within model/request-shape blocks. Retain no
payloads. Primary outcomes are success, bounded latency, realized cost, stale-price
failure, and quote-to-fill disagreement. Estimate intention-to-treat effects and do not
replace failed assignments with a new provider.

This study measures whether apparent cheap liquidity is firm. It still does not show
that a provider anticipated or reacted to other users' flow.

### C3. Policy switchback deployment

A causal provider-response experiment requires a harness or gateway with recurring,
observable traffic. Randomize the fixed baseline and hardened adaptive policy in long
model-by-time switchback blocks with guard periods. Freeze:

- eligible models and provider sets;
- policy-block length and randomization sequence;
- minimum exposure and completed-date horizon;
- price, capacity, success, latency, and availability outcomes;
- carryover and interference analysis;
- untreated model/provider controls where credible.

Primary strategic-response estimands are changes in quote hazard, quote level,
admitted capacity, availability, and quote-to-fill agreement following policy exposure.
Use randomization inference at the policy-block level and cluster by model-day or the
coarser randomization unit.

The present paid-probe budget can validate request-level outcomes but is unlikely to be
large enough to make providers reprice. C3 should use organic harness volume, a router
partner, or a provider data partnership; otherwise it remains a service experiment.

### C4. Empirical-to-simulation validation

Before interpreting strategic simulation:

- check that simulated arm-level success, latency, cost, and quote-to-fill slippage
  cover the paid estimates;
- check that simulated quote hazards, step sizes, persistence, and cross-provider
  dispersion cover the historical test split;
- check that policy rankings are stable after reweighting simulation states to the
  paid-study menu population;
- reject rather than retune a model that fails the frozen transport gates.

## 8. Hypotheses and gates

### H-AR1: mechanical manipulation resistance

The hardened policy reduces the 95th percentile of single-provider allocation gain
from feasible quote perturbations relative to both `baseline_eta2` and
`menu_adaptive_raw`, without violating the frozen payment and service constraints.

### H-AR2: quote-fading resistance

The hardened policy reduces attempted-minus-served share and bounded user loss under
quote fading. The result must hold in historical perturbations and calibrated service
simulation; the paid study tests the required service calibration.

### H-AR3: unilateral exploitability

The hardened policy reduces maximum normalized unilateral deviation gain relative to
the baseline across the primary cost/capacity bands. Promotion requires agreement
between exact low-dimensional audits and at least two independent adversary families.

### H-AR4: small-coalition robustness

No declared two-provider deviation class obtains a materially larger normalized gain
under the hardened policy than under the baseline. This is a bounded coalition audit,
not a claim that collusion is absent.

### H-AR5: sybil resistance

Splitting one provider into multiple endpoint identities does not materially increase
its combined expected allocation or profit after operator-level constraints.

### H-AR6: transport

The sign of the user-outcome and exploitability comparison survives the frozen temporal,
model-family, provider-type, demand, and cost/capacity holdouts. Any sign boundary is
reported as an identified-set boundary.

### H-AR7: realized feasibility

On owned requests, the hardened policy is noninferior to the baseline on success and
bounded latency, and its realized cost lies within the preregistered tolerance. This is
necessary but not sufficient for strategic robustness.

Exact numerical materiality and noninferiority margins are selected from training data,
power simulations, and operational requirements, then frozen before validation and
test outcomes are read.

## 9. Power and sample-size plan

Use the existing historical and paid preflight data to simulate power before freezing
new paid horizons. The independent unit must match randomization:

- historical replay: model-day cluster;
- existing paid study: model/request-shape block;
- quote-firmness study: randomized endpoint block;
- switchback deployment: model-by-time policy block;
- strategic simulation: training seed or calibration draw.

Choose a fixed horizon that provides at least 80% power for the smallest operationally
meaningful success, bounded-latency, and quote-firmness effects. Strategic quote-response
events will likely require weeks rather than hundreds of closely spaced requests.
Absence of sufficient exposure is reported as underpowered, not as no strategic
response.

## 10. Budget

The existing study retains its frozen `$40` campaign ceiling. A reasonable use of the
available `$500` credit is:

- up to `$40` for the existing five-arm study;
- approximately `$100-$150` for the separately preregistered quote-firmness study;
- a reserved replication and operational-failure budget;
- no attempt to spend the balance merely to create nominal sample size.

Simulation should run on remote CPU infrastructure. The remaining paid credit is not
assumed sufficient to induce economically meaningful provider repricing. If no organic
harness or partner flow exists, the provider-response claim stays simulation-only.

## 11. Software and testing plan

### Core implementation

- `src/orcap/market_env/routers_adaptive.py`: fixed, raw-adaptive, and hardened routers;
- `src/orcap/market_env/adversaries.py`: scripted unilateral attacks;
- `src/orcap/market_env/adversaries_joint.py`: coalition and sybil attacks;
- `src/orcap/market_env/exploitability.py`: global and dynamic deviation audits;
- `src/orcap/market_env/psro.py`: policy-space response-oracle driver;
- `src/orcap/analysis/adaptive_adversarial_replay.py`: historical perturbation panel;
- `src/orcap/analysis/adaptive_adversarial_report.py`: frozen analysis and figures;
- versioned configuration and preregistration under
  `experiments/adaptive-router-adversarial-v1/`.

### Required invariant tests

- allocation probabilities are finite, nonnegative, and sum to one;
- price monotonicity holds between policy updates;
- trust regions and share caps cannot be bypassed by missing providers;
- leave-one-out adaptation does not read the excluded provider's current action;
- no provider serves above physical or admitted capacity;
- transfers cancel from transfer-free welfare;
- sybil clones conserve combined cost and capacity;
- adversaries cannot access future random draws or outcomes;
- seeded replay is exact;
- exhaustive and learned best responses agree in toy games;
- assignment manifests are written before paid outcomes;
- failed and nonconvergent training seeds remain in reports;
- historical and calibration test splits cannot be opened by training commands.

### Statistical tests

- synthetic-null confidence-interval coverage;
- whole-cluster resampling rather than row bootstrap;
- deterministic multiple-testing family construction;
- permutation invariance under provider relabeling;
- result-manifest/source-hash equality;
- claim-table numbers locked to immutable result artifacts.

## 12. Remote execution

Add four GitHub Actions workflows:

1. `adaptive-adversarial-smoke.yml`: pull-request invariants and tiny exact games;
2. `adaptive-adversarial-screening.yml`: scheduled or manual bounded historical and
   simulation screening;
3. `adaptive-adversarial-confirmatory.yml`: manual marker-first release from a signed
   scenario manifest and immutable data revision;
4. `adaptive-adversarial-monitor.yml`: outcome-blind completeness, integrity, budget,
   and artifact monitoring.

Every workflow must check out an exact commit, use `uv.lock`, record the immutable
Hugging Face revision, use frozen seeds, shard by intended scenario rather than outcome,
and publish failed/nonconvergent shards. Confirmatory aggregation begins only after all
intended shards exist. No workflow depends on this laptop remaining online.

Store on Hugging Face:

- calibration bundle and data card;
- historical attack assignments and aggregates;
- signed simulation scenario manifest;
- per-seed aggregate results and sparse audit trajectories;
- model checkpoints used in frozen evaluation;
- paid assignment and redacted attempt tables;
- immutable release manifest, figures, and claim ledger.

Do not store prompts, completions, secrets, session identifiers, or unnecessary
request-level payloads.

## 13. Execution order

### Phase 0: protocol freeze

1. Freeze hypotheses, uncertainty sets, policy grid, outcomes, and claim boundaries.
2. Freeze one historical revision and train/validation/test split.
3. Run power simulations and select new paid-study horizons.
4. Commit assignment-generation and analysis code before outcomes.

### Phase 1: deterministic and historical attacks

1. Implement the adaptive router adapter and hardening primitives.
2. Pass allocation, accounting, and information-set invariants.
3. Run A1-A6 on training and validation data.
4. Promote exactly one hardened policy.
5. Freeze it before reading the historical test split.

### Phase 2: calibrated strategic environment

1. Release the immutable calibration bundle.
2. Implement exact/scripted adversaries and validate against toy games.
3. Run the primary cost, capacity, demand, and entry factorial.
4. Reject or narrow any claim when simulation misses held-out empirical moments.

### Phase 3: adaptive adversaries

1. Add bandit and tabular agents.
2. Add PPO/SAC only after small-game recovery gates pass.
3. Run the unilateral response-oracle loop.
4. Run coalition and sybil response-oracle loops.
5. Freeze the final router before confirmatory seeds.

### Phase 4: prospective validation

1. Complete and release the existing 120-block paid study unchanged.
2. Validate the simulation's service layer against its outcomes.
3. Preregister and execute the quote-firmness study.
4. Execute a switchback deployment only if meaningful recurring harness or partner flow
   exists.

### Phase 5: confirmatory release

1. Run every intended scenario on remote CI.
2. Aggregate only after completeness and integrity gates pass.
3. Publish the full grid, including negative and nonconvergent results.
4. Produce a claim ledger separating historical, paid, simulated, and causal evidence.
5. Conduct an adversarial mechanism-design and ML-simulation review before paper use.

## 14. Decision rule

Classify the result as follows:

- **Robust within tested classes:** historical attack gates, exact-deviation gates,
  multi-algorithm response-oracle gates, transport gates, and owned-traffic feasibility
  all pass.
- **Conditionally robust:** the policy dominates only inside stated cost, capacity,
  demand, or coalition bounds. Publish the boundary.
- **Mechanically useful but strategically vulnerable:** historical allocation benefits
  remain, but profitable provider deviations undo them.
- **Not supported:** the hardened policy fails realized service constraints or does not
  improve worst-case outcomes over the baseline.

Even the strongest classification does not establish dominant-strategy truthfulness,
absence of collusion, or market-wide welfare. Those require stronger mechanism results
or direct market-level experimental access.

## 15. Executed screening and prospective release

The full v1 screen completed in GitHub Actions run `29780088479` against immutable HF
revision `0a7c6bef4acb87f81c9d22b1748e7a610107a03e`. Its artifact contains 4,878 historical
menus, 652,680 quote-attack rows, 7,200 strategic cells, 320 UCB runs, and 40 bounded
Q-learning runs. The screening verdict is mixed: the hardened mechanism is much less
manipulable under historical, static, coalition, and sequential-best-response attacks,
but leaves larger residual deviation gains after the deterministic-reward UCB learning
path. Full results and boundaries are recorded in
`docs/adaptive-router-adversarial-screening-results-2026-07-20.md`.

The UCB audit also showed that its nominal seeds were duplicates because the only seeded
object was an economically irrelevant within-epoch permutation. Version 2 was therefore
superseded before release. Version 3 uses realized multinomial routed quantities with
capacity clipping, retains the adverse UCB acceptance threshold, moves the untouched
test window to 2026-07-22 through 2026-08-04, and is eligible to release once after
2026-08-05. The scheduled marker-first workflow runs remotely and does not depend on
this computer.

A post-freeze engineering audit of the corrected stochastic learner was also completed
on eight historical menus. Every menu-policy cell produced ten distinct realized
tail-profit paths. The hardened rule reduced mean absolute post-UCB deviation gain to
0.534 of inverse-square, but its normalized ratio was 4.062 because mean provider profit
contracted even more. This audit validates the seed correction and sharpens the
denominator interpretation; it is not a prospective outcome, does not satisfy the
version-3 gate, and did not change any frozen parameter or threshold.
