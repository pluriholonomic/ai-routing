# Administered Menus and Hidden Clearing: The Microstructure of the Market for Machine Intelligence

*Manuscript identification revision — 2026-07-16. Status: REVISE AND RESUBMIT.
The author-anchor and lagged-copying headlines fail price-multiplicity-preserving
hard nulls. These failures, the exact-atoms fact, and the constructive
asynchronous-menu equivalence result are now the contribution. Mechanical gates
remain: crossover n >= 500/arm and the earliest 30-date re-estimation.*

## Abstract

Open-weight AI models turned inference into a commodity that ~70 firms sell
under identical labels through a routing marketplace. Using a purpose-built
high-frequency dataset — per-provider quotes at 5-minute resolution across
~300 models, a repricing-event ledger, congestion telemetry, a three-year
backfill, and realized-routing probes — we characterize how this market
prices, clears, and steers. Three facts constitute the core. **(1)
Administered menus:** 2.8% of provider-model-days reprice, median jumps of
13-26%, 93% of quotes on cent grids, 26% of cuts at the midnight cron;
within-provider standardized kurtosis (3.5) sits in the CalvoPlus region,
and a nested hazard model attributes repricing to price *gaps* (p = 1e-5)
and rival moves (p = 2e-3) but not congestion (p = 0.17) — out-of-sample,
only the gap channel survives (day-split AUC 0.64). **(2) Exact price atoms:**
the two cheapest quotes tie exactly on 46% of multi-provider model-days —
3.4 times the rate under an independent grid-constrained pricing null. The
old selected-tie author-match rate is non-discriminating (90.0% observed,
91.9% under its conditional random-label benchmark). The all-market statistic
also fails: authors occupy a shared price in 54.3% of 94 markets versus 53.5%
for a random endpoint preserving the exact price multiset (p=0.466); the
author excess is 0.79 points [-9.0, 16.1]. Of 196 isolated revisions, 20.4%
land exactly on a rival's prior quote, but a tightly scale-matched common-menu
null predicts 13.4%; the 7.0-point excess has model-cluster interval
[-23.1, 12.2]. These post-freeze hard nulls are fixed for the 30-date
replication. Providers almost never
undercut their own direct channel (99.6% parity). **(3) Quantity clearing
with manufactured firmness:** over nine days, 12% of endpoints ever changed
price while 86% experienced rate-limit variation; in a randomized-crossover
probe design, default routing succeeds 99.3% while pinned single-provider
requests succeed only ~81-84% — with rejection FLAT in price rank (no
last-look), so individual quotes are revocable dealer quotes and the
market's firmness is manufactured by the router's substitution. We then audit the router's steering rule
in the sense of Johnson-Rhodes-Wildenbeest: conditional on being cheapest, a
provider that cut price in the past week receives a 3.9% selection share
versus 23.3% without — steering that *penalizes* recent undercutting,
which JRW theory classifies as collusion-neutral and which independently
taxes price competition. Secondary results, stated with their bounds: entry
scales as demand^0.16 (rejecting sqrt-law free entry; a long-memory
correction matches point estimates but awaits its registered discriminator);
retry amplification of rationed demand is positive in asymmetric
OLS (+0.17 forward vs -0.13 placebo) but small under a capacity-spillover
instrument (phi = 0.02 [-0.04, 0.09]; a local estimand that excludes the
rerouting margin); and a persistence-aware
reclassification halves the apparent algorithmic punish-and-revert rate
(83% -> 42%), a caution for collusion screens on posted-price panels.

## 1. Introduction

[As v1, tightened: the three core facts and the steering audit are the
contribution; entry, retries, and conduct screens are framed as bounded
secondary results and registered follow-ons.]

## 2. Data

[As v1, plus the telemetry data-generating-process appendix (M6): fortuna
utilization and status-heuristic counts are router-published aggregates;
reporting gaps documented; all regressions using them re-estimated on the
complete-reporting subsample with unchanged signs.]

## 3. Fact 1: administered menus

Levels, grids, timing, sufficient statistics as v1 (kurtosis now reported
with the per-provider distribution: IQR [2.1, 4.9], median 3.4; the 3-year
registry supports duration and lifecycle facts). Hazard ladder as v1 with
the addition demanded by review: **day-split out-of-sample AUC 0.638 for the
state-dependent rung**, versus 0.525 for time-dependence alone; the
strategic rung does not yet generalize (0.555 on 36 test events) and is
reported as in-sample-only. Claims are scoped accordingly: state dependence
is established in- and out-of-sample; the strategic channel is established
in-sample on the current panel and re-estimated nightly under
pre-registration.

## 4. Fact 2: exact price atoms, with their hard nulls

**The null model (new).** Ties could be a grid artifact. Under a null in
which each provider draws its log price independently as (model-day median +
deviation), deviations resampled from the pooled within-model-day deviation
distribution, snapped to the observed cent-per-million-token grid, the
tie-at-minimum rate is 13.4% (SD 1.0% across replications). Observed: 45.9%
over 1,311 model-days — **3.4x the grid null** (sensitivity: under a coarser
dime-per-Mtok grid the null rises to 27.6%, ratio 1.7x — the atom exceeds
grid coarseness under both snapping rules, and the null is conservative in
one respect: the deviation pool retains the tie atom, so the null itself
re-manufactures some ties). The atom is dependence on shared levels, not merely
coarseness; it does not identify a behavioral mechanism.

**The anchor's identity.** Selecting tied markets makes author identity almost
mechanical. With `n` providers, `t` tied minima, and `r` author labels, a random
label hits the tied set with probability
`1 - choose(n-t,r)/choose(n,r)`. The robust crosswalk observes 45/50 matches
(90.0%) and this benchmark expects 45.97 (91.9%, upper-tail p=0.913). The old
65/72 statistic is demoted. An adjacent-grid all-market comparison initially
looks strong: 51/94 author-observable models have an exact match at the author
price versus 1.5% at adjacent levels. But the correct identity null preserves
the realized price multiset and randomizes the author endpoint. It expects
50.26/94 shared author prices (53.5%) versus 51 observed (54.3%, p=0.466).
Author-minus-random-anchor is 0.79 points [-9.0, 16.1], and author-vs-third-party
pair density is -0.94 points [-8.8, 12.0]. Author identity is not special.

**The temporal hard null.** Restricting to <=15-minute consecutive snapshots
with exactly one mover yields 196 revisions. Exact landing on a strictly prior
rival quote occurs in 40 (20.4%), versus 1.0% at adjacent grid levels. A matched
common-menu null instead draws the same number of quotes from other models in
the prior snapshot within a factor 1.25 of the new price; it predicts 13.4%.
The 7.0-point residual has model-cluster interval [-23.1, 12.2], provider-cluster
interval [-22.4, 18.2], and leave-one-model-out range [-10.4, 9.7]. One model
supplies 73.5% of events and 85.0% of exact landings. The data therefore do not
identify strategic copying. A constructive theorem shows that an asynchronous
public-menu model and a rival-response model generate the same exact atoms and
lagged landings; the strategic exact-landing share is sharply bounded only by
[0, 40/196]. Formation and breaking directions (74% down-to-tie, 88%
down-to-break) are competitive. Cross-channel parity remains 99.6%.

**Preregistered control and power.** Commit `adc09cd` froze the follow-up before
estimation. Only 12/175 comparable revisions reuse the mover's own cross-model
price, and own-menu support is slightly lower for rival landings (-2.0 points,
model-cluster interval [-31.0, 0.9]). Removing those events raises the strategic
residual to 13.4 points, but its interval remains [-11.5, 18.5]. A 5,000-replication
conditional-design experiment controls one-sided size at 3.5% but has only 43.4%
interpolated power at the observed effect. In 1,250 known-clock panels the hard
null has zero false promotions and zero power through 50% reactive replacement.
The detection-threshold formula
`rho*=(q-p)/(1-p)` explains why: a benchmark denser than the focal rival set is
conservative under no response but can mask moderate response. The correct
reading is nonidentified and underpowered, not no behavior. A timestamped
robustness addendum gives exact model-cluster sign-flip p-values 0.425 (full) and
0.214 (own-menu-novel). An empirical calibration audit puts all four observed
diagnostics outside SIM2's 5--95% null range, so SIM2 is a stress-test
counterexample rather than a calibrated model of this market.

**Future held-out calibration.** Commit `7709446` freezes a separate earliest-
30-date test before those data exist. Dates 1--15 standardize five whole-market
state features and fit one excess-landing parameter; dates 16--30 evaluate a
nearest-20-market hypergeometric menu benchmark and the frozen response model out
of time. The analyzer reads only distinct date support before the gate and cannot
load prices or emit an event table. Promotion additionally requires at least 100
holdout events, 10 model clusters, no model above 50% of events, positive clustered
residual and log-score-gain intervals, positive leave-one-model-out estimates, and
one-sided sign-flip p-values at most 0.05. This can reject matched-market
exchangeability, not identify intent or literal front-running.

## 5. Fact 3: quantity clearing and manufactured firmness

Panel evidence (12% vs 86% ever-moved; latency loads ~30x price at 30-min
horizons; raises follow slack) as v1. Request-level evidence: the v1
protocol confounded policy with within-block order (referee B1; crosstab
near-degenerate), so its gradient was unidentified. The randomized-crossover
replacement (policy and model order randomized per block; assignment
recorded) yields the corrected readout on its first accrual (n = 152
default / 76 per pinned arm): default routing succeeds 99.3%; pinned
single-provider requests succeed 80.3% (cheapest), 81.6% (second), 84.2%
(random). Two conclusions replace the withdrawn v1 claim: (i) the ~19%
rejection LEVEL replicates under randomization — individual quotes are
revocable dealer quotes; (ii) the price-rank gradient does NOT replicate —
rejection is flat in rank, consistent with capacity-policy throttling and
inconsistent with both classic last-look (stale-cheap refusal) and the v1
artifact. The randomized design turned a spurious gradient into a null with
content. Estimates re-run nightly as the crossover accrues; first-position-
only estimands (carryover-robust) are consistent with the pooled figures at
smaller n.

## 6. The steering audit

As v1 (unrestricted: 251 provider-model-day cells; cheapest-with-recent-cut
selected 3.9% vs 23.3% without). Eligibility bounding (M-minor): restricting
to pairs whose eligibility our pinned probes directly confirmed preserves
the direction (9.5% vs 30.0%) but with tiny cells (n = 1 vs 11) — we
therefore rest the result on the unrestricted audit and flag eligibility
misclassification as a bounded caveat: it would have to be concentrated
almost entirely among recent cutters to reverse the sign. The audit ships
as a reproducible statistic computable by any key-holder.

## 7. Secondary results (bounded)

**Entry.** Slope 0.16 (SE 0.02) of log active providers on log demand;
simultaneity biases upward, so the rejection of 0.5/0.33 benchmarks is
conservative. The long-memory correction k* ~ n^{(2-2H)/2} matches at the
count-method Hurst (0.165 predicted vs 0.161 measured) but is presented as
a **remark**. Horizon discipline (referee C2): the paper uses ONE H per
application — the multi-scale count H (0.835) for entry (the entry-relevant
horizon is weeks: capacity decisions contest persistent demand), and makes
no quantitative use of intraday H elsewhere; the deseasonalized 30-minute
estimate (anti-persistent, 0.36) is reported to show the horizon dependence
that keeps this a remark. The registered within-market discriminator is
underpowered at this panel length (interaction -0.10 [-0.31, 0.16]).

**Retry amplification.** OLS with demand-growth controls: +0.167 forward
with a -0.126 backward placebo (sign asymmetry inconsistent with pure
persistence). A capacity-spillover instrument (same provider's rate
limiting on *other* models) yields phi = +0.023 [-0.043, 0.085]: the
exogenous component of rationing produces little same-endpoint
amplification — consistent with provider-wide throttling inducing rerouting
rather than retrying, and with genuine but modest same-endpoint retry
feedback. We report the pair (asymmetric OLS, tight IV bound) and defer
welfare quantification to the incident-instrumented design registered on
the status-page panel.

**Conduct screens.** The reclassification result (83% -> 42% genuine
punish-and-revert; 41% initiator-withdrawn experimentation; 66% of raises
followed within 72h with half of initiators low-volume) as v1, framed as a
methodological caution and an agenda: the ABS pass-through discriminator and
the Hawkes layer are registered with explicit triggers.

## 8. Welfare discussion

[Condensed to two pages: the four measured wedges — admission objective,
quality verification, steering design, rationing feedback — each tied to a
fact and an instrument; the C1-C10 apparatus and remaining conditions moved
to the companion pre-registration.]

## 9-10. Related work; limitations

[As v1; limitations lead with panel length and enumerate the five
registered-and-unfired tests with their triggers.]

**Transparent-compute comparator.** A separately preregistered Akash study
links public multi-provider bid sets, the accepted lease, and exact on-chain
termination reasons. Its launch backfill replayed 2,929 retained closed leases
with a 100% exact-ID match. The pre-preregistration calibration contains only
36 linked choices and no provider or escrow close within 300 blocks; the
prospective cohort is still empty under its second-snapshot inception rule.
We therefore report this as a validated measurement bridge and a negative
support result, not as evidence about price, quality, or delivery, and exclude
it from the paper's three facts. Confirmatory outcomes remain masked until the
fixed 2026-08-15 release.

---

## Change log v1 -> v2 (response to review)

- M1: retry claim demoted from headline; controls + backward placebo + IV
  added; abstract rewritten accordingly.
- M2: independent grid-pricing null added (13.4% vs 45.9%; 3.4x). The later v9
  identification correction demotes the selected-tie 65/72 statistic and
  replaces it with the all-market adjacent-level audit.
- M3: entry conjecture demoted to remark with the horizon caveat explicit.
- M4: restructured — three facts + steering audit are the paper; secondary
  results bounded in one section; welfare condensed; conduct extras to
  registered agenda.
- M5: day-split OOS AUC reported (0.638); strategic rung labeled
  in-sample-only.
- M6: telemetry DGP appendix; complete-reporting robustness.
- Minors: key-specificity in text; eligibility-bounded steering audit;
  per-provider kurtosis distribution; denominators.
