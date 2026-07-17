# Theorem and empirical-claim validation matrix

Status: execution matrix updated after the 2026-07-17 evidence audit. This plan
separates logical theorem validation, estimator validation, empirical tests, and
data acquisition. A simulation can validate code or demonstrate identification;
it cannot turn a theorem into an empirical market fact.

## Priority order

1. H81 stopped-design correction and theorem validation.
2. H81 release and independent fixed-horizon replication with broader support.
3. H93/H94 longitudinal cross-router price collection.
4. H82/H84 prospective holdouts with realized owned-traffic linkage.
5. Counterexample and coverage suites for the public-timing theorems.
6. Companion-only revenue and free-entry validations.

The first item is implemented. The H81 analyzer now queries only assignment and
support fields before its gate, excludes the gate-hitting terminal block after
release, and uses fixed-count conditional randomization. The 20,000-draw theorem
validation and 2,000-experiment size audit are in
`src/orcap/analysis/h81_theorem_validation.py`.

The companion logical/numerical suite is also implemented in
`src/orcap/analysis/theory_validation_suite.py`. It validates the detection
identity over 20 cells (maximum absolute simulation error 2.23 Monte Carlo
standard errors), the quantity/revenue coefficient identity to `1e-14`, the
free-entry ceiling and equal-margin overentry result over 144 grid cells, and
60,198 finite coarsening witnesses with zero construction failures. These are
implementation and theorem checks, not empirical calibration.

## T1. Randomized fallback and hidden-selection decomposition

### Logical claim

Conditional on the balance stopping time, terminal arm, and preterminal counts,
the first `T-1` treatment labels are a uniform fixed-count permutation. Their
arm means equal conditional Horvitz-Thompson means and unbiasedly estimate the
finite-population policy means. Fallback plus hidden selection equals total
delegation as both an estimand and estimator identity.

### Validation experiments

1. **Seed replay and treatment compliance**
   - Input: outcome-free H81 assignment rows and candidate telemetry.
   - Test: reproduce the first policy from every 64-bit seed; verify provider
     `order`, `only`, and `allow_fallbacks` fields against the policy label.
   - Pass rule: 100% replay and treatment compliance. Any failure invalidates
     the affected block and triggers a collector incident, not an outcome-based
     exclusion.
   - Current result: 84/84 for both checks at revision `42334a84`; arm counts
     are 32, 24, and 28 and outcomes remain unqueried.

2. **Stopped-design Monte Carlo**
   - Fix heterogeneous, policy-specific, time-varying potential outcomes.
   - Draw production labels until all arm counts reach 40.
   - Compare the old terminal-inclusive estimator with the corrected conditional
     preterminal estimator.
   - Pass rule: corrected bias no larger than 3.5 Monte Carlo standard errors in
     every primary contrast; the identity must hold to machine precision.
   - Current result: corrected biases are approximately `-1.04e-4`, `-0.05e-4`,
     and `-1.09e-4`, all within Monte Carlo error. The old terminal-inclusive
     fallback estimator has detectable bias under the deliberately trending DGP.

3. **Pairwise sharp-null randomization size**
   - Generate a common heterogeneous outcome path under the sharp null.
   - Preserve each realized preterminal arm-count multiset and hold the nuisance
     third-policy assignment fixed. For each primary pair, sum the exact two-arm
     hypergeometric law; use simulation only to estimate repeated-experiment
     rejection frequency.
   - Pass rule: the 5% rejection rate must lie inside a predeclared Monte Carlo
     tolerance of `[0.03,0.07]` with at least 2,000 experiments for the final
     release audit.
   - Current final audit: 5.05% in 2,000 experiments (Monte Carlo standard error
     0.49 percentage points), inside the declared tolerance.
   - Nuisance-arm stress test: in 2,000 stopped experiments per primary null,
     the two focal policies share exactly the same fixed outcome path while the
     third policy has a large time-varying effect. The corrected pairwise test
     rejects at 3.45% and 3.60%; the superseded all-arm permutation rejects at
     5.65% and 6.70%. This proves that the old global-sharp-null law was not a
     valid reference experiment for the registered pairwise nulls.
   - Exact-enumerator audit: all six assignments in a four-block `2/2` pair
     fixture agree with brute-force label enumeration to machine precision.
     The 100,000-draw tails permute the contrasted pair only and remain
     discrepancy checks; the release fails closed above one percentage point.

4. **Exact pre-outcome power surface**
   - Enumerate independent-Bernoulli scenario power at the conservative minimum
     preterminal pair counts 39 and 40, over baseline success probabilities 25%,
     50%, and 75% and effect increments of 2.5 percentage points.
   - Report both the unadjusted 5% test and the Bonferroni 2.5% threshold, which
     lower-bounds marginal power under the registered two-test Holm procedure.
   - Current result: 80% power requires effects of 22.5--30 percentage points
     unadjusted and 25--35 points at the Bonferroni threshold. H81 can detect
     large wedges but cannot treat a nonsignificant result as equivalence.
   - Boundary: this is a model-based planning surface, not an empirical outcome
     estimate and not a post-outcome sample-size amendment.

5. **Finite-population interval and joint-Holm audit**
   - Condition on the terminal policy and preterminal counts. For each policy
     mean use the Hoeffding--Serfling sampling-without-replacement radius
     `sqrt((1-(n_p-1)/B) log(6 / 0.05) / (2 n_p))`; union-bound the three means and propagate
     their intervals to both primary contrasts.
   - Stress five fixed binary schedules with 3,000 stopped assignments each and
     compare marginal Newcombe, Bonferroni-Newcombe family, and design-Hoeffding--Serfling
     coverage and width.
   - Enumerate every triple of arm success counts under Bernoulli planning
     scenarios, apply both exact pairwise Fisher tests and the registered Holm
     step-down rule, and repeat for each possible minimum-count terminal arm.
   - Current result: worst marginal Newcombe coverage is 94.67%, worst
     Bonferroni-Newcombe family coverage is 95.13%, and design-Hoeffding--Serfling family
     coverage is at least 99.93% in the audit. The design guarantee comes from the bound,
     not the simulation; mean design interval width is about 0.76. Worst-terminal
     80% Holm power requires a 35-point component effect on the fixed grid.
   - Boundary: Newcombe remains descriptive under a binomial interpretation;
     the conservative Hoeffding--Serfling interval is the finite-population design-valid
     confidence set. Neither result reveals an H81 outcome.

6. **Missingness adversary**
   - Replace a verified binary outcome with `unknown`; delete spend, latency,
     and selected-provider fields by treatment, success, and quote level; and
     corrupt a treatment-control record before a valid replacement reaches the
     gate.
   - Verify that unknown outcomes are never coded as failure, incomplete binary
     outcomes suppress point/randomization inference, and `[0,1]` arm bounds
     propagate to every contrast. Reconstruct intended first policies from
     their seeds and send missing/noncompliant treatment records to both
     endpoints; any unreconstructable arm must yield `[-1,1]`.
   - Explicit-order spend bounds use only protocol-valid quote caps; delegated
     default receives no invalid public-set upper cap.
   - Pass rule: reported bound coverage is 100% over generated schedules and no
     point estimate appears when its completeness rule fails.
   - Current result: implemented before outcome access in commit `4d66fda`.
     Both adversarial tests and the current full 561-test suite pass. The two primary
     intervals additionally receive Bonferroni-Newcombe familywise adjustment;
     their exact conditional Fisher p-values retain the registered Holm family.

7. **External-support and leave-one-model-out audit**
   - Report model dominance, effective model count, support turnover, arm balance
     by model, and leave-one-model-out contrasts after release.
   - Pass rule for a broad claim: at least eight models, effective model count at
     least five, no model above 35% of blocks, and both primary directions stable
     under leave-one-model-out. These are transport gates, not causal-validity
     gates.
   - Current result: fails transport decisively; only two models recur and support
     turnover is zero.

### Independent replication design: implemented as H95

H95 was frozen in commit `00351dd` before its first inference request and its
first remote workflow completed successfully in run `29555584388`. It uses the
first 120 prospectively written three-model triplet plans: 360 confirmatory
first-position blocks with exact 120-per-arm balance. At each run it screens
OpenRouter ranks 7--30, requires a Hugging Face id and at least two positive-price
providers, uniformly samples three eligible models, and assigns each H81 policy
to first position exactly once. The full eligibility funnel is written before
requests. Missing planned records and noncompliance are coded as failure;
an unknown or malformed outcome on an otherwise compliant recorded request is
measurement missing and cannot be silently converted to failure.

A prerelease red-team amendment in commit `f170d89` was deployed while the
fixed horizon was 4/120 and before any H95 outcome field was queried. A second
outcome-blind audit at 5/120 found that the six-assignment law tests the global
three-policy sharp null, not either registered pairwise null with an unrestricted
nuisance policy. Published Fisher tails now condition on each triplet's nuisance
assignment and convolve the two allowed focal-policy swaps. The 100,000-draw
conditional-swap audit is implementation-only, and the release fails closed
above a 0.01 tail discrepancy. Exact two-triplet results match brute-force
enumeration of all four conditional assignments. Unknown measurement
outcomes suppress every complete-data point estimate and randomization test and
enter `[0,1]` bounds. Missing planned requests, assignment noncompliance,
duplicate first records, and auditable provider-control failures remain
structural intent-to-treat zeros under the original protocol. The two primary
tests receive Holm adjustment. In two mixed-null 5,000-experiment schedules,
the corrected law's worst elementary and Holm true-null rejection is 4.06%,
versus 8.12% for the superseded law. Paired Student-t intervals remain
descriptive, with Bonferroni 95% familywise intervals over the two primary
contrasts. A bounded-outcome Hoeffding interval adds design-valid simultaneous
coverage over the two primary contrasts; its radius at 120 triplets is 0.270.
Across five fixed schedules, worst observed design-family coverage is 99.90%
and mean width 0.540, versus paired-t family coverage 95.52% and mean width
0.290. The inequality, not simulation, gives the design guarantee.

The three model blocks are sequential. Random assignment of policy across
models and positions absorbs position-only drift, but the direct-policy
estimand also requires no treatment-dependent carryover from an earlier model
block. The release therefore writes a position-by-policy panel; position-zero
cells have no preceding H95 block in the triplet. This is a falsification and
sensitivity diagnostic, not a proof of no interference.

The design uses a fixed horizon rather than the H81 arm-balance stopping rule and
is never pooled with H81. At revision `30b430e2`, five compliant triplets have
accrued: 15 blocks over nine unique models, effective model count 7.76, perfect
plan compliance and replay, no missing first record, and no outcome query. The
first 12 first-position rows predate the new row-level order-length fields and
remain `legacy_treatment_metadata_unverified`. All three rows in the first
hardened triplet carry the full provider-control metadata and pass, giving 20%
coverage and 100% pass among auditable rows. The release reports coverage and
pass rates rather than silently certifying legacy rows. No H95 outcome is
queried before 120 plans exist. Broad
transport additionally requires at least eight audited model ids, effective
model count five, no model above 35% of plans, no six-hour bin above 20%, and both
primary effect directions stable when each model's containing triplets are
dropped whole. The current five-triplet support fails the time gate because its
largest six-hour bin contains three of five triplets; this is an early-accrual
diagnostic, not a causal-design failure. Adversarial H95 tests and the full
repository suite pass. The launch establishes prospective operation
only; it is not an empirical effect result.

## T2. Asynchronous-menu observational equivalence

### Logical claim

An exact cross-sectional price match or landing on a strictly prior rival price
can be generated by both a nonreactive latent-menu model and a rival-reactive
model. The strategic share is sharply bounded by `[0,L/N]` without additional
restrictions.

### Validation experiments

1. **Constructive witness generator**
   - For every discrete observed panel in an exhaustive small state space
     (three providers, three price atoms, four snapshots), construct both a
     nonreactive provider-clock witness and a reactive rival-trigger witness.
   - Pass rule: both witnesses reproduce every observed panel and every exact
     landing bit-for-bit; otherwise produce a counterexample and narrow the
     theorem.

2. **Sharpness endpoints**
   - For each observed event set, assign zero events and then all `L` exact
     events to the strategic mechanism while preserving observables.
   - Pass rule: both endpoint constructions satisfy the model assumptions; this
     proves attainability rather than merely reporting an outer bound.

3. **Assumption-ablation search**
   - Remove latent public state, restrict refresh clocks, impose monotone best
     responses, and cap reaction delay.
   - Enumerate when equivalence breaks. The output should be a map from added
   contract/log fields to the identified object, not another market estimate.

Current execution: the shared finite construction suite generated 60,198
changed-provider leader witnesses over 20,000 sampled transitions with zero
construction failures. Exhaustive small-state enumeration and assumption
ablation remain open.

### Missing data that would restore identification

- provider quote-update timestamps finer than the five-minute capture bin;
- a public or shared provider refresh schedule;
- exogenous provider visibility/adoption shocks;
- router or provider logs linking a displayed quote update to request arrival.

## T3. Detection threshold of a dominating menu null

### Logical claim

For nonreactive landing probability `p`, benchmark probability `q`, and reactive
replacement probability `rho`, the residual expectation is
`p-q+rho(1-p)` and changes sign only above `(q-p)/(1-p)` when `q>=p`.

### Validation experiments

1. **Algebra grid**
   - Sweep `p` and `q` on `[0.01,0.99]`, and `rho` on `[0,1]`.
   - Simulate at least 100,000 events per cell near the analytic threshold.
   - Pass rule: empirical residual differs from the formula by no more than four
     Monte Carlo standard errors and the sign transition occurs in the containing
     grid interval.

2. **Finite-panel size and power**
   - Preserve the empirical event-specific `(p_e,q_e)` vector and model clusters.
   - Compare independent-event, cluster-shock, and provider-clock DGPs.
   - Report size, power, and calibration distance separately. A well-sized test
     on a DGP that cannot reproduce the empirical event count is not validated.

3. **Benchmark dominance diagnostic**
   - Plot the distribution of event-level thresholds and identify which public
     menu construction dominates each event.
   - Pass rule for empirical use: the fitted null must reproduce event count,
   exact-landing mass, menu probability, and tie mass on held-out dates.

Current execution: the analytic expectation and simulated residual agree over
20 validation cells, every sign away from the threshold matches, and the maximum
absolute discrepancy is 2.23 Monte Carlo standard errors. The empirical-vector
size/power and held-out benchmark-dominance checks remain open.

## T4. Coarsened-timing equivalence and named-rival bounds

### Logical claim

When multiple providers change within one observation interval, any changed
provider can be made the latent first mover under an admissible reactive path.
Without additional restrictions, a named-rival response share lies between zero
and the fraction of events with a unique eligible named rival.

### Validation experiments

1. **Path-construction property test**
   - Randomly generate sampled transitions with two to six changed providers.
   - For each provider, construct a right-continuous latent path that makes it the
     first mover while matching both sampled endpoints.
   - Pass rule: construction succeeds for 100,000 generated transitions and an
     exhaustive small price grid.

2. **Bound sharpness test**
   - For every unique-rival indicator vector, construct compatible histories at
     the zero and upper endpoints.
   - Pass rule: sampled quotes and strict-prior-rival identities remain unchanged.

3. **Cadence sensitivity**
   - Coarsen sub-minute synthetic event logs to one, five, fifteen, and sixty
     minutes.
   - Plot the identified-set width against cadence and simultaneous-change mass.
   - This quantifies the value of new timestamp data without pretending more
     five-minute observations resolve within-bin order.

## T5. Quantity-share and revenue-share identity

### Logical claim

With a common sample, weights, controls, and market effects, the log quantity-
share price coefficient is exactly the log revenue-share coefficient minus one;
residuals and residual-based standard errors are identical.

### Validation experiments

1. Generate panels with arbitrary prices, quantities, weights, fixed effects,
   heteroskedasticity, and clustered errors. Verify coefficient difference one,
   residual equality, and covariance equality to `1e-10`.
2. Introduce zeros, winsorization, inconsistent samples, inconsistent weights,
   and approximate fixed-effect solvers one at a time. Record exactly which data
   transformations break the identity.
3. Re-run H92 with an explicit row-hash proving both regressions use the identical
   sample. Treat any near-minus-one elasticity as accounting, not a first-order
   condition.

Current execution: on a synthetic panel with common rows, weights, and fixed
effects, the coefficient identity error is `-9.99e-15`, the maximum residual
difference is `2.66e-14`, and the HC1 standard-error difference is `2.78e-17`.
The transformation-ablation matrix and empirical row-hash audit remain open.

Disposition: companion paper. Even perfect validation does not estimate causal
demand or revenue maximization.

## T6. Finite entry and reliability/business-stealing wedge

### Logical claim

In the independent symmetric benchmark, marginal reliability value declines
geometrically, positive setup cost makes efficient entry finite, and private
entry can exceed or fall short of efficient entry.

### Validation experiments

1. Exhaustively solve integer welfare and zero-profit entry for a grid over
   `(D,v,p,c,F,a)` and compare with the proposition's inequalities.
2. Search boundaries `a -> 0`, `a -> 1`, `F -> 0`, `p -> c`, and `v -> c` for
   undefined or discontinuous cases. Verify the stated domain excludes them.
3. Add correlated deliverability through a beta-binomial common shock and binding
   capacity. Identify which conclusions survive and label those as conjectures,
   not extensions of the proved proposition.

Current execution: all 144 independent-deliverability grid cells satisfy the
analytic entry ceiling and equal-margin overentry implication, and none hits the
integer search boundary. Correlated delivery and capacity extensions remain
unproved conjectures.

### Missing empirical primitives

Demand value, provider marginal cost, setup cost, provider margin, correlated
deliverability, capacity, and entry/exit are not jointly observed. No public-data
pipeline can estimate the welfare count without additional assumptions. A
provider or router partnership, randomized admission fee, or capacity auction is
required. The theorem stays in the companion appendix.

## E1. H82/H84 public operational mechanisms

### H82 future-only holdout

- Keep the frozen discovery specification and failed pretrends visible.
- Run H83 only on timestamps strictly after the H82 cutoff.
- Require at least 28 calendar days, the prespecified event count, and passing
  placebo/pretrend gates before causal language.
- Link events to owned attempts only prospectively and by predeclared time window.

### H84/H85 stale-quote mechanism

- Preserve H84 as a negative directional discovery result.
- H85 uses no H84 observations for feature fitting or threshold selection.
- Primary result: stale-cheap score versus next capacity event and realized fill.
- Negative controls: backward event, future price staleness, random provider
  permutation, and same-provider other-model event.

### Data improvement

Increase router-side event resolution by retaining the published 5m/30m counters,
derank transitions, capacity ceilings, and owned attempt timestamps. Only a router
partnership can provide request ordering or full cross-user flow.

## E2. H93/H94 longitudinal cross-router pricing

### Current state

The pinned revision contains exactly one catalog snapshot. The 28/29 equality
result is a cross-sectional coverage fact with Wilson interval `[0.8282,0.9939]`.
There are zero price events, common shocks, or simulated switches.

### Acquisition

- `router-catalogs.yml` runs hourly on a GitHub-hosted runner and buffers Glama,
  Requesty, and NemoRouter public catalogs.
- `compact.yml` includes those artifacts in the nightly Hugging Face push.
- Add a source-health alert if any router has fewer than 18 successful snapshots
  in a rolling 24 hours; distinguish source failure from a legitimately empty
  catalog.
- Retain raw source timestamps, retrieval hashes, exact provider/model strings,
  component prices, and normalization decisions.

### H93 gates

Seven elapsed days, all three routers repeated, at least 48 snapshots per router,
at least 10 linked competitive models, 30 source-specific price events, 15 common
provider-model shocks, and 15 simulated route switches. Equality is reported at
every cut; pass-through is reported only after all longitudinal gates pass.

### H94 design

H94 must be activated by a freeze commit before eligible future observations.
Use source-specific price events, distributed lead/lag coefficients, provider-
model fixed effects, matched no-change controls, and simulated routing switches.
Decoy events and impossible leads are falsification tests. The outcome is public
quote pass-through, not realized allocation or markup.

## E3. PM1 temporal repricing validation

### Frozen split and leakage boundary

Wait for 30 completed UTC quote dates, excluding the open date. Fit once on
dates 1--15 and score dates 16--30 once. Every state, GPU, congestion, and rival
feature is measured at the prior UTC close; the provider-activity control is
estimated from training outcomes only. Before this gate, the readiness path may
query represented dates but not the pricing-event table, coefficients,
predictions, loss, or AUC.

### Estimator audit and amendment

The primary L3 rung contains 17 parameters including the intercept. The first
implementation used an unpenalized logistic GLM and allowed promotion with 50
training events, only 2.94 events per parameter. Before the holdout existed,
commit `1719ade` replaced it with training-standardized L2 logistic regression,
fixed `C=1`, no holdout tuning. A complete-separation adversary now produces
finite probabilities.

The minimum identification gate requires:

- 10 training events and 10 training nonevents per L3 parameter;
- 50 test events and 50 test nonevents;
- events on at least 10 training and 10 test dates; and
- at least 10 test models.

Failure returns `insufficient_identifying_support`; it does not select a smaller
post-hoc rung. The primary estimand remains the date-weighted paired holdout
log-loss improvement of L3 over L2. Four adjacent contrasts receive Holm
adjustment, with date- and model-cluster bootstrap intervals and
leave-one-model-out sensitivity. This is predictive validation, not causal
pricing-response identification.

## Additional public data acquisition

1. **Router catalogs:** Glama, Requesty, NemoRouter, TokenRouter, and any public
   TrueFoundry or Portkey catalog endpoints. Qualify sources before inclusion;
   documentation without provider-level prices is institutional evidence only.
2. **Transparent allocation comparators:** Akash accepted bids and terminations,
   Livepeer orchestrator selection, Bittensor/Chutes miner assignment, and Nosana
   job allocation. These validate measurement methods where allocation is public;
   they are not pooled with token-priced inference.
3. **Quality and workload:** public benchmark/eval leaderboards with exact model
   versions, plus owned prompt-class metadata that stores no payload. Quality must
   be lagged or externally measured to avoid post-routing conditioning.
4. **GPU input costs:** Ornn and other qualified GPU price panels, joined only at
   region, accelerator, and time resolutions they actually support. They test a
   cost channel; they do not identify provider marginal cost by themselves.
5. **Harness allocation:** public app/model token panels and, if available,
   Hermes aggregate model-choice logs. App token shares explain model demand, not
   within-model provider routing unless a provider identifier is present.

## Submission gates

The focal paper is not submission-ready until all of the following hold:

1. H81 releases its original gate without changing sign-dependent rules.
2. The corrected stopped-design inference passes at least 2,000 size experiments.
3. The main table reports H81 support, missingness, both primary contrasts, the
   decomposition identity, and leave-one-model-out sensitivity.
4. H93 is either still labeled one-cross-section coverage or passes every
   longitudinal gate; there is no intermediate pass-through language.
5. Every theorem in the LaTeX is present in the machine-readable evidence
   registry and has a proof plus a validation artifact or a disclosed missing
   validation.
6. The release manifest hashes the paper, bibliography, every included figure,
   protocols, analyzers, tests, and amendment ledger.
7. A fresh reviewer can reproduce the paper from the pinned dataset revision
   without accessing prompts, completions, or secrets.
