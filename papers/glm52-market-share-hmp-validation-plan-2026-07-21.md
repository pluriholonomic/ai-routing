# GLM-5.2 market-share HMP validation plan

Status: preregistered and implemented for prospective collection. Phase 0 is
complete; the live pilot and fixed-duration confirmatory gates necessarily
accrue in calendar time. This document does not promote a result. It extends
`marketshare-quality-memory-validation-plan-2026-07-21.md` with the experiment
needed to test whether *multiple active price experimenters* create an
Hansen--Misra--Pai-style market-share learning channel.

Date: 2026-07-21 America/New_York / 2026-07-22 UTC.

Implementation note: the outcome-free detector and single paid dispatcher are
two jobs in one serialized `glm52-market-share-hmp.yml` workflow. Keeping the
provisional event write, immutable assignment upload, and execution under one
workflow-level concurrency lock removes the plan/execute race that separate
workflows would introduce. Monitoring and the full simulation remain separate
workflows. The event ledger is staged: provisional at the cut, multiplicity
finalized after 15 minutes, and confirmatory-clean only after the frozen
60-minute contamination window. Outcomes remain blinded in published monitor
artifacts until every duration, support, integrity, coverage, and concentration
gate passes.

## 1. The conjecture we should actually test

Let the router's conditional probability of choosing provider `i` from exact
eligible menu `N_t` be

\[
 s_{it}=\frac{\exp\{-\eta x_{it}+a_{it}\}}
 {\sum_{j\in N_t}\exp\{-\eta x_{jt}+a_{jt}\}},
 \qquad x_{it}=\log p_{it}.
\]

`eta` is the price exponent and `a` is the non-price routing score, including
quality, health, capacity, and any score memory. Under the price-only rule,
`a=0`. A public shadow share is the value of `s` under that restriction; it is
not realized market share.

For a unilateral change by provider `i`, define the positive elasticity
magnitude

\[
 E^U_i=-\frac{d\log s_i}{d\log p_i}
       =(1-s_i)(\eta-h'_i),
\]

where `h'_i=da_i/dx_i` is zero under the price-only rule. If a set `C` of
providers moves its log price in the same direction and at the same local rate,
then, for `i in C`,

\[
 E^C_i=-\frac{d\log s_i}{d x_C}
       =(1-S_C)(\eta-h'_C),
 \qquad S_C=\sum_{j\in C}s_j.
\]

The market-share path wedge is therefore

\[
 W_{iC}=E^U_i-E^C_i=(\eta-h'_C)(S_C-s_i).
\]

The first sharp implication is mechanical: with one cutter, `C={i}` and the
wedge is exactly zero. With multiple co-moving cutters, the wedge grows with
the *share mass of the other cutters*, not with a raw count. The group can gain
share from passive providers even when its members gain little share from one
another. This is the routing analogue of correlated price experiments: a
provider learning from the group path sees a different reward slope from a
provider experimenting unilaterally.

The dynamic HMP conjecture is stronger:

> When several providers repeatedly make directionally aligned price
> experiments and observe sufficiently precise routing rewards, memory makes
> the group-path elasticity easier to learn than the unilateral elasticity.
> Above a critical combination of co-cutter share, signal precision, and
> memory, behavior shifts toward recurrent common price paths. The shifted
> demand is borne mainly by passive providers. With one active provider, or
> after common reward ordering is broken, the discontinuity disappears.

This is not yet an empirical result. It is a property chain. A positive result
must establish each link in order; a later link cannot rescue an earlier
failure.

## 2. Why GLM-5.2 is the focal market

The frozen eight-day provider taxonomy contains seven GLM-5.2 active
undercutters and 117 price changes:

| Provider | Frozen active price changes |
|---|---:|
| Novita | 48 |
| StreamLake | 47 |
| Inceptron | 10 |
| Io Net | 9 |
| Alibaba | 1 |
| AtlasCloud | 1 |
| Baidu | 1 |

The next-richest market, Kimi K2.7 Code, has four active undercutters and only
13 changes. GLM-5.2 is therefore the only current public market with meaningful
variation in both active-provider multiplicity and repricing frequency.

The existing evidence is diagnostic, not affirmative:

- the public inverse-power surface shows a large conditional share-transfer
  opportunity;
- only Novita and StreamLake currently contribute meaningful natural-event
  support;
- the existing owned natural-event panel has 45 type-event rows spanning nine
  registered events, only eight pre- and eight post-event requests in total,
  and no event clears its pre/post support gate;
- only 36 paid default attempts across three events currently enter the frozen
  WF19 aggregate;
- among 942 GLM-5.2 downward rival-event exposures, the observed response rate
  is 37.7%, below the 45.9% clock-shift placebo rate; and
- the current HMP residual-coupling statistic is positive but not significant
  (`p=0.110`) and is concentrated in one pair.

Thus the present data establish neither reactive co-cutting nor an HMP learning
mechanism. The new design uses the public surface to discover events, paid
owned traffic to measure realized choices, an owned router to manipulate the
allocation rule, and simulation to manipulate provider learning.

## 3. Ordered hypotheses and claim boundary

### H1: exact static path identity

Holding the menu and score fixed, the measured finite-change share response
matches the softmax/inverse-power identity. The co-mover wedge is zero for a
singleton and increases with the pre-event share mass of other co-movers.

This is a mathematical and implementation check, not an economic finding.

### H2: public multiplicity gradient

After conditioning on cut depth, starting share, exact menu, author-price
changes, public health, and clock effects, natural events with greater
co-cutter share have a smaller within-active-provider share response and a
larger active-group-to-passive-group transfer.

This is observational. The primary continuous regressor is co-cutter share,
not an arbitrary singleton/pair/multiple bin.

### H3: realized owned-routing gradient

For the project's requests, the elasticity of realized first choice to a focal
provider's price is more negative when it moves alone than along a co-cutter
path. The difference is ordered by co-cutter share and is not explained by
fallback, derank, capacity, or prompt composition.

Natural repricing remains observational. Randomized choice-set contrasts
identify the effect of this project's eligible menu, not the causal effect of a
provider choosing to reprice.

### H4: passive-liquidity incidence

Conditional on a common cut by active providers, the active group gains owned
choice share while shares within the active group move less. The displaced
share comes disproportionately from anchor adopters and other passive
providers. Quote-revenue incidence, buyer cost, success, latency, and fidelity
are reported separately.

This hypothesis does not assume that a cut is collusive or socially harmful.
It can increase buyer welfare.

### H5: temporal learning channel

Past co-cutter paths improve future choice or quote prediction beyond current
price, current score, provider/model effects, and clock controls. The effect is
monotone in a prespecified memory statistic and vanishes under future-lead,
circular-shift, and common-order-breaking placebos.

### H6: HMP mechanism transport

In a calibrated multi-agent environment, preserving each provider's marginal
reward process but breaking common reward-signal ordering attenuates the
multiplicity gradient, increases the time needed to learn the group-path
elasticity, and removes any critical-memory transition. The result must survive
at least one heterogeneous learner family beyond the focal UCB agents.

Only H1--H6 in order permits the phrase `HMP-consistent market-share learning
channel`. Nothing in this design identifies communication, agreement, intent,
provider cost, a deployed UCB algorithm, or market-wide OpenRouter flow.

## 4. Frozen event and state definitions

### 4.1 Provider states

Freeze the active-provider label from a preperiod ending before the first new
outcome. Do not relabel a provider from the confirmatory period. The primary
groups are active undercutters, anchor adopters, static discounters, premium
differentiated providers, and unclassified providers.

### 4.2 Price

Use the request-shaped prompt/completion quote for the frozen probe shape. The
primary price is the token-weighted effective quote. Prompt-only and
completion-only quotes are mandatory sensitivities. Exclude zero-priced
endpoints from the paid analysis and analyze free endpoints separately.

### 4.3 Natural cut

A focal cut is the first observed decline of at least 2% in request-shaped
price after two consecutive unchanged five-minute captures. A provider must
remain publicly eligible for two post-event captures. The primary co-move
window is 15 minutes; sensitivities are 5, 30, and 60 minutes.

At the end of the fixed window, label the event:

- singleton: no other frozen active provider cuts;
- pair: exactly one other active provider cuts;
- multiple: at least two other active providers cut.

The continuous treatment is

\[
 Z_{iC,t}=\sum_{j\ne i:\,j\text{ cuts in window}}
 s_{j,t^-}\frac{|\Delta x_{jt}|}{|\Delta x_{it}|},
\]

truncated only at the preregistered 99th percentile from the calibration
period. A matched co-move sensitivity requires depth ratios between 0.5 and
2.0. A provisional event ID is written at the focal cut; its multiplicity label
is filled after the window without using a routing outcome.

### 4.4 Clean event

The confirmatory panel excludes author-benchmark changes, model launches,
provider-set changes, visible derank transitions, rate-limit or derankable-error
spikes, missing menus, and simultaneous public capacity-ceiling changes in the
60-minute event window. All excluded events remain in a signed diagnostic
ledger.

### 4.5 Memory exposure

Freeze three compatible summaries before analysis:

1. exponentially weighted co-cutter mass with half-lives 1, 4, 16, 48, 96,
   288, and 672 fifteen-minute blocks;
2. run length of consecutive same-direction active-group events; and
3. finite memory `M` in `{1, 2, 4, 8, 16, 32, 64}` events.

No best lag is selected in sample. Primary model selection uses expanding
whole-day future folds. The existing score-memory study remains a separate
study; only its frozen lagged aggregate states may be joined, and its cadence,
outcomes, or stopping rule may not be changed for this design.

## 5. Experiment A: public-price multiplicity event study

This is the cheap, high-frequency screen.

For every clean natural event, snapshot the exact price-only shares immediately
before the focal cut and at `+5m`, `+15m`, `+60m`, `+4h`, and `+24h`. Record:

- focal-provider shadow-share change;
- active-group shadow-share change;
- within-active redistribution;
- anchor, static-discounter, author, and premium share loss;
- the exact mechanical wedge `W_iC`;
- provider-set, enforcement, capacity, and benchmark state; and
- quote-revenue indices at fixed request volume.

First verify the exact finite-change formula to numerical tolerance. Then
estimate the descriptive residual

\[
 R_{et}=\Delta\log s_{i,e,t}-\Delta\log s^{\mathrm{mechanical}}_{i,e,t}.
\]

Under the price-only public calculation this residual must be zero; a nonzero
value is a pipeline bug. Economic inference concerns subsequent quotes and
realized owned choices, not this deterministic residual.

The quote-response regression is an event-time local projection:

\[
 \Delta x_{i,e,t+h}=\alpha_i+\lambda_{d,h}
 +\beta_h Z_{iC,e}+\gamma_h\Delta x_{i,e}
 +\Gamma_h X_e+u_{e,h},
\]

where `X` contains starting group share, menu size, author-price distance,
public health, and UTC clock controls. Inference uses provider-pair/model-day
clusters and circular shifts of provider event clocks. The primary check is
whether `beta_h` exceeds the identical clock-preserving placebo, not whether a
conventional unclustered `p` value is small.

## 6. Experiment B: paid realized-routing blocks around natural events

### 6.1 Trigger and horizons

The public detector writes an immutable assignment-only event manifest before
any paid request. Clean candidates trigger blocks at `0`, `+15m`, `+60m`, and
`+4h`; the `+24h` block is lower priority and runs only if the daily budget and
menu-continuity gates pass. A block is analyzed even if a provider reverses its
price later.

### 6.2 Randomized arms

Run identical one-token route-selection probes in randomized complete blocks:

1. **Broad default:** all eligible providers, delegated default routing.
2. **Broad price-sort:** the same menu under the explicit price-sort policy.
3. **Singleton menu:** focal cutter plus a frozen set of eligible anchors.
4. **Pair menu:** focal cutter, one prespecified active co-cutter, and the same
   anchors.
5. **Active-group menu:** all eligible frozen active providers plus the same
   anchors.
6. **Anchor-only control:** the frozen anchor set without an active cutter.

The pair is chosen by a seed committed in the assignment manifest, not by the
post-event winner. The anchor set is frozen from the pre-event menu. Provider
pins are operational controls only and never enter delegated-share estimates.
Fresh sessions, request hashes, and arm order prevent persistence and clock
confounding.

Because an event trigger cannot observe a request before an unanticipated cut,
run a separate HMP-specific hourly background block with two replicates of the
same six arms and a deterministically rotating focal provider. The latest
strictly prior background block is the pre-event owned-routing measurement.
These rows are not pooled with the pre-existing GLM campaign, and a due natural
event always has queue priority.

These arms separate three objects:

- broad default versus broad price-sort estimates the non-price scoring wedge;
- singleton versus pair versus active-group menus causally estimate the effect
  of owned-menu multiplicity at fixed public prices; and
- pre/post natural-event changes estimate the observational realized response
  to provider repricing.

### 6.3 Outcomes

Retrieve the selected provider through the generation endpoint and record
first attempted provider, completion provider, fallback, success, cost, time to
first token, total latency, and throughput. Primary outcome is first-choice
share; completion share is secondary because failover mixes allocation and
execution quality.

For event `e` and arm `r`, estimate:

\[
 \widehat E_{er}=-\frac{\Delta\log \widehat s_{er}}
 {\Delta\log p_e}, \qquad
 \widehat W_e=\widehat E_{e,\mathrm{singleton}}
 -\widehat E_{e,\mathrm{active\ group}}.
\]

The more stable primary estimator is a block-level conditional multinomial
choice model with event fixed effects and interactions of relative log price
with `Z_iC`, rather than a ratio when a cell has zero selections. Report the
finite-difference estimator as an interpretable companion.

### 6.4 Quality bank

One-token probes cannot establish welfare. Every six hours, use the existing
versioned quality bank to obtain structured-output validity, tool-call
validity, task fidelity, success, latency, and cost for supported providers.
Join quality only from measurements strictly before the routing block. Report
quality-qualified completions per dollar and cost per successful qualified
completion. Do not infer quality from price or provider type.

## 7. Experiment C: controlled-router price and memory intervention

OpenRouter does not let this project alter a provider's displayed quote. The
causal price-path experiment must therefore run in the owned router or replay
environment, using the exact historical GLM-5.2 menus and observed quality
states.

Factorially randomize:

- price cut depth: 0%, 2%, 5%, 10%, 20%, 30%;
- number of cutters: 1, 2, 3, 5, 7;
- co-cutter pre-event share mass: quintiles;
- price exponent: 1.26, 1.648278, 2.04;
- score rule: price only, current quality, geometric quality memory, finite
  failure memory; and
- memory length: the frozen grid in Section 4.5.

Use common random request streams and failure/quality draws across arms. The
first test is exact recovery of the static path wedge. The next tests estimate
how the score derivative `h'_C(M)` changes the wedge and whether the total
demand elasticity `delta` places the system across

\[
 \chi_C(M)=\delta+(1-S_C)(\eta-h'_C(M))=1.
\]

Treat `chi=1` as a theoretical regime boundary, not evidence of a phase
transition in live behavior. A live critical-memory claim requires Experiment
B plus the temporal gate in Experiment D.

## 8. Experiment D: multi-agent learning and critical memory

### 8.1 Environment

Replay historical menus and arrivals or sample from a held-out calibrated
arrival process. Each provider chooses a price on its own empirically supported
grid and faces capacity, stochastic success, latency, and a serving-cost
scenario. Costs remain scenario bounds because they are not observed.

Fit only nuisance features from the calibration period: price grid, update
cadence, availability, capacity, quality distribution, and quote distance from
the author benchmark. Do not claim that the fitted policy is the real
provider's algorithm.

### 8.2 Agent families

The focal agents use the HMP-style independent UCB experiments. Transport must
also include:

- epsilon-greedy bandits;
- Thompson sampling;
- Q-learning with finite state memory;
- static anchor and static discounter agents; and
- heterogeneous mixtures with one or more active learners.

Run active counts `K in {1,2,3,5,7}`. The `K=1` cell is the necessary negative
control. Vary signal-to-noise ratio, memory, price exponent, active-group share,
cost heterogeneity, capacity, and quality dispersion on a frozen grid.

### 8.3 Causal HMP intervention

For each seed, create two worlds with identical marginal exogenous shock
sequences for every provider:

- **coupled:** exogenous reward shocks retain their common time ordering; and
- **decoupled:** each provider's exogenous shock series is independently permuted in
  time within the same public-state strata.

The intervention preserves marginal exogenous-shock distributions and breaks
only common shock ordering. Once actions diverge, endogenous realized rewards
need not have identical marginals. This is the simulation analogue of the HMP
comparison, not an equality claim about realized reward paths.

### 8.4 Primary simulation estimands

- time to estimate `E^C` within 10% relative error and 95% coverage;
- time to a recurrent common-price regime;
- unilateral-minus-path elasticity wedge;
- active-group and anchor share;
- provider revenue and bounded profit;
- buyer generalized cost and quality-qualified completions;
- router revenue and concentration;
- unilateral deviation gain and exploitability; and
- frequency and duration of common high-price and common low-price regimes.

A critical-memory result requires a preregistered discontinuity or sharp change
in learning time, not a heatmap that merely looks nonlinear. Compare smooth
models against a threshold model in held-out seeds, report the estimated
boundary with uncertainty, and require the threshold model to improve held-out
prediction. The boundary must disappear or move materially in the decoupled
and `K=1` controls.

## 9. Statistical design

### 9.1 Primary estimators

- Experiment A: circular-shift randomization inference and event-time local
  projections.
- Experiment B menu arms: exact randomization inference within event-by-replicate
  blocks, plus a conditional multinomial model.
- Experiment B natural cuts: event-clustered event study with whole-event
  bootstrap intervals; causal language is prohibited.
- Experiment C: finite-population factorial contrasts with common random
  numbers.
- Experiment D: paired-seed coupled-minus-decoupled contrasts and held-out
  threshold comparison.

### 9.2 Ordered family

Apply Holm correction in the frozen order H2, H3, H4, H5. H1 is an exact
implementation check and H6 is a separate simulation transport family. Report
effect sizes and intervals even when a gate fails.

### 9.3 Mandatory falsification

- price increases instead of cuts;
- inactive-provider and non-GLM events;
- circular provider-clock shifts;
- future leads and lag reversal;
- author-price and enforcement windows included versus excluded;
- prompt-only versus completion-only price;
- 5-, 15-, 30-, and 60-minute co-move windows;
- whole-provider, whole-pair, whole-day, and whole-model leave-outs;
- same marginals with common reward ordering broken;
- active-provider identity shuffles; and
- cut depth and co-cutter mass permuted independently within event strata.

No provider pair may contribute more than 20% of the confirmatory H2--H5
statistic. If this concentration gate fails, the result is explicitly a
Novita--StreamLake case study.

## 10. Support, precision, and stop rules

### Pilot gate

Run a seven-day operational pilot without inferential promotion. Require:

- at least 10 clean natural events in total;
- at least 200 covered delegated choices in each observed singleton, pair, and
  multiple stratum;
- at least three selected active providers;
- 90% exact-menu coverage;
- 95% assignment-to-attempt integrity; and
- no duplicate spend or queue replay.

Use pilot outcomes only to estimate cluster variance, failure rates, and the
final request count. Do not choose outcomes, lag signs, or event windows from
the pilot.

### Confirmatory gate

Accrue at least 28 complete days, 30 independent clean events in each of the
singleton, pair, and multiple strata, 10 unique provider-pair clusters, and
800 covered delegated choices per stratum. At a 25% baseline share, 800
independent Bernoulli choices per cell gives only roughly 6--7 percentage-point
minimum detectable two-arm differences at conventional 80% power; event
clustering will generally require more. Therefore the final count is the
larger of 800 and the variance-based pilot calculation, capped prospectively by
budget rather than stopped after a favorable estimate.

The confirmatory release also requires three active providers selected, 90%
menu coverage, exact assignment integrity, and no provider-pair concentration
above 20%. Quality claims require at least 100 completed scored tasks per
supported provider/model/task stratum. If natural pair or multiple events do
not reach their fixed counts, extend time rather than changing the event
definition.

### Stop rules

Stop paid execution only for a spend cap, secret or redaction failure, more than
10% malformed generation records, more than 20% request failure over two
consecutive blocks, or an API/provider policy issue. Never stop because an
effect is large, small, or has crossed a significance threshold.

## 11. Remote execution architecture

The current GitHub workflows share paid-workflow concurrency. GitHub retains at
most one pending run per concurrency group, so many independently scheduled
event-triggered workflows can replace one another. This experiment should use
a queue, not a burst of workflow dispatches.

### Workflows

1. `glm52-hmp-event-detector.yml` runs every five minutes, reads the newest
   immutable public revision, and writes candidate and finalized event
   manifests. It spends nothing.
2. `glm52-hmp-paid-dispatcher.yml` is the only paid worker. It drains the queue
   in timestamp order under one concurrency group, validates the immutable
   assignment, reserves budget, executes once, and writes a spend checkpoint.
3. `glm52-hmp-compactor.yml` runs nightly and consolidates candidates,
   assignments, attempts, menus, quality, and spend into the private Hugging
   Face dataset.
4. `glm52-hmp-monitor.yml` refreshes assignment integrity, support, precision,
   concentration, and aggregate plots. It must not expose request payloads.

### Exact-once protocol

- event ID is a hash of model, focal provider, first qualifying timestamp,
  pre-event quote, and source revision;
- queue key is event ID, horizon, replicate, and arm;
- assignment is immutable before execution;
- a reserve/execute/settle spend ledger rejects duplicate keys;
- a failed request may use only the preregistered retry count and retains the
  original assignment; and
- compaction is idempotent and validates one assignment-to-attempt join.

### Private Hugging Face tables

- `glm52_hmp_candidates`
- `glm52_hmp_events`
- `glm52_hmp_assignments`
- `glm52_hmp_attempts`
- `glm52_hmp_menu_state`
- `glm52_hmp_quality`
- `glm52_hmp_spend_ledger`
- `glm52_hmp_aggregate`
- `glm52_hmp_preregistration`

Only redacted aggregates, gates, code commit, dataset revision, and frozen
protocol hash may be public. Request-level generation records remain private.
The H81/H95 releases, the existing GLM campaign, and the score-memory campaign
must not be re-queried, amended, pooled, or cadence-adjusted by this study.

## 12. Budget

The current one-token route-selection probes have been extremely cheap, but
the design must cap spend using the provider's quoted worst case, not a recent
mean. Use:

- `$5` seven-day pilot cap;
- `$5` per UTC-day hard cap;
- `$50` core confirmatory route-selection cap;
- a separately approved quality-bank cap after the pilot power calculation;
  and
- `$1` maximum per workflow run.

At the recent approximate cost of `7e-5` dollars per one-token request, even
3,600 route-selection requests are nominally below one dollar. The larger cap
covers price dispersion, retries, longer quality tasks, and API changes. The
remaining account credit is not authorization to spend it; the dispatcher
fails closed at the study caps.

## 13. Figures and tables fixed before analysis

Every experiment gets a diagnostic and an estimand plot. Use direct labels,
event counts, intervals, and visible support warnings; no decorative panels.

1. GLM-5.2 provider price paths with natural singleton, pair, and multiple
   events marked.
2. Mechanical versus realized elasticity by co-cutter share, with the
   singleton zero-wedge benchmark.
3. Forest plot of singleton, pair, and multiple elasticity and the pairwise
   wedges.
4. Active-group gain and anchor/static/premium loss around event time.
5. Default-minus-price-sort residual score by provider and event horizon.
6. Quote, realized choice, fallback, latency, and quality time series for each
   supported provider.
7. Memory-by-co-cutter-share response surface with the `chi=1` boundary and
   uncertainty, not a fitted line without raw support.
8. Simulation phase diagram over active count, SNR, and memory for learning
   time and exploitability.
9. Coupled-minus-decoupled paired-seed contrasts for every learner family.
10. Placebo and leave-one-provider/pair specification curve.

The primary table reports the whole ordered chain H1--H6, support gates, effect
sizes, confidence intervals or randomization intervals, corrected `p` values,
and permitted language in the same row.

## 14. Decision and manuscript-entry rules

| Evidence reached | Permitted conclusion |
|---|---|
| H1 only | The path-elasticity wedge is an exact property of the declared routing rule. |
| H1--H2 | GLM-5.2 public quote paths exhibit a multiplicity gradient consistent with the mechanical channel. |
| H1--H3 | The project's realized choices exhibit an owned-routing multiplicity gradient. |
| H1--H4 | Active-group cuts shift owned routing from passive providers, with buyer outcomes reported separately. |
| H1--H5 | Lagged co-cutter exposure predicts the owned-routing or quote response beyond current state. |
| H1--H6 | Empirical properties and calibrated causal simulation support an HMP-consistent market-share learning channel. |

If H2 fails, the central empirical conclusion is still useful and positive:
the observed GLM-5.2 market is compatible with independent active repricing
rather than a correlated market-share learning channel. If H3 fails while H2
passes, public quote synchronization does not transport to this project's
realized routing. If H5 fails, the result supports a contemporaneous
multiplicity mechanism without detectable temporal learning. If H6 is UCB-only,
the theory remains a focal algorithm example rather than a robust mechanism.

No result enters the EC paper as evidence of collusion. The paper may discuss
collusive susceptibility only through deviation gain, buyer harm, and the
ordered mechanism tests. Low common prices, better quality, or lower buyer cost
are evidence against a harmful-collusion interpretation even when price paths
are synchronized.

## 15. Execution order and deliverables

### Phase 0: preregistration and implementation, 1--2 days

- freeze code/data revisions, labels, event rules, arms, lag grid, seeds,
  estimands, plots, support gates, and spend caps;
- build synthetic fixtures for singleton, pair, multiple, event reversal,
  derank contamination, duplicate queue entries, and missing menu;
- add property tests for share conservation, finite-change identities,
  assignment integrity, exact-once spend, redaction, and coupled/decoupled
  marginal equality; and
- run a zero-spend remote dry run.

### Phase 1: operational pilot, 7 days

- activate the detector and paid dispatcher;
- validate queue latency, exact-menu coverage, realized-provider recovery,
  failure rate, and spend;
- render support-only plots and calculate the blinded variance/power update;
  and
- freeze the confirmatory sample size before opening confirmatory outcomes.

### Phase 2: confirmatory live collection, at least 28 days

- run at the frozen cadence and event triggers;
- compact nightly to immutable private revisions;
- monitor only assignment, spend, integrity, coverage, and support counts; and
- do not alter the event threshold because one multiplicity cell accrues slowly.

### Phase 3: controlled router and simulation

- run the price-depth by multiplicity factorial on historical GLM-5.2 menus;
- fit nuisance distributions on the calibration split only;
- run paired coupled/decoupled seeds across learner families; and
- freeze the result bundle independent of sign.

### Phase 4: release and paper integration

- publish a data card, protocol hash, aggregate tables, figures, and immutable
  result manifest;
- run the full unit, integration, synthetic-recovery, redaction, and evidence
  audits;
- conduct a new adversarial EC review using only claims allowed by Section 14;
  and
- revise the EC paper once around the frozen result, with a negative or partial
  result treated symmetrically.

Required deliverables are the preregistration, remote workflows, queue and spend
ledger, data dictionary, simulator configuration, power report, aggregate
dashboard, ten fixed figure families, theorem/derivation appendix, frozen
result manifest, and manuscript claim ledger.
