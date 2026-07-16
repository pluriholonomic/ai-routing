# Administered Menus and Focal Anchors: The Microstructure of the Market for Machine Intelligence

*Manuscript v3-pending — 2026-07-16. Status: v2 'accept' SET ASIDE by referee
panel (reviews-v2-panel.md): the v1 probe design confounds policy with
within-block order, so Fact 3's request-level gradient is unidentified and
its levels are upper bounds. Resubmission gated on the randomized-crossover
probe study (running) and >=60-day panel re-estimation. Surviving core:
Facts 1-2, aggregate quantity-clearing, and the steering audit (position-0
probes only).*

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
only the gap channel survives (day-split AUC 0.64). **(2) Focal anchoring:**
the two cheapest quotes tie exactly on 46% of multi-provider model-days —
3.4 times the rate under an independent grid-constrained pricing null — and
among tied markets where the model's author operates an endpoint (72 of
146), 90% of tie levels equal the author's first-party price exactly. The
author's price is the market's Knittel-Stango focal point. Providers never
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
instrument (phi = 0.02 [-0.04, 0.09]); and a persistence-aware
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

## 4. Fact 2: focal anchoring, with its null

**The null model (new).** Ties could be a grid artifact. Under a null in
which each provider draws its log price independently as (model-day median +
deviation), deviations resampled from the pooled within-model-day deviation
distribution, snapped to the observed cent-per-million-token grid, the
tie-at-minimum rate is 13.4% (SD 1.0% across replications). Observed: 45.9%
over 1,311 model-days — **3.4x the grid null** (sensitivity: under a coarser
dime-per-Mtok grid the null rises to 27.6%, ratio 1.7x — the atom exceeds
grid coarseness under both snapping rules, and the null is conservative in
one respect: the deviation pool retains the tie atom, so the null itself
re-manufactures some ties). The atom is coordination on levels, not
coarseness.

**The anchor's identity.** Among the 146 currently-tied models, 72 have an
author-operated endpoint; in 65 of those 72 (90%), the tie level equals the
author's first-party price to machine precision. Round-number focality
(61%) is subsumed: the author's prices are themselves round. Formation and
breaking directions (71% down-to-tie, 87% down-to-break) are competitive;
the anchor-following-vs-fossil discriminator (does the tie track author
repricings?) is registered and unfired — authors did not reprice in-window,
itself evidence the anchor is stable. Cross-channel: providers price their
own direct APIs at exact parity with their router quotes (99.6%; 0.4%
direct-below, sign-persistent) — voluntary MFN.

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
a **remark**: the estimator-horizon question is open (deseasonalized
30-minute demand is anti-persistent), and the registered within-market
discriminator is underpowered at this panel length (interaction -0.10
[-0.31, 0.16]).

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

---

## Change log v1 -> v2 (response to review)

- M1: retry claim demoted from headline; controls + backward placebo + IV
  added; abstract rewritten accordingly.
- M2: independent grid-pricing null added (13.4% vs 45.9%; 3.4x); author-
  price denominator (65/72) in main text.
- M3: entry conjecture demoted to remark with the horizon caveat explicit.
- M4: restructured — three facts + steering audit are the paper; secondary
  results bounded in one section; welfare condensed; conduct extras to
  registered agenda.
- M5: day-split OOS AUC reported (0.638); strategic rung labeled
  in-sample-only.
- M6: telemetry DGP appendix; complete-reporting robustness.
- Minors: key-specificity in text; eligibility-bounded steering audit;
  per-provider kurtosis distribution; denominators.
