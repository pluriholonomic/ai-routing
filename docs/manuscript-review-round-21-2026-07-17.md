# Independent-style review, round 21

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7.1/10, weak reject pending the registered H81 release.**

## Summary judgment

This revision closes the last avoidable inferential defect I can identify before
the focal outcome is opened. H81 now has a coherent stopped-design estimand,
exact conditional Fisher tests for its binary primary outcome, simultaneous
descriptive intervals, explicit outcome and treatment-record attrition bounds,
and a marker-first one-time release. The paper states these pieces compactly and
does not use them to imply an outcome that has not been observed.

The recommendation nevertheless remains weak reject. The title contribution is
still a randomized clearing decomposition without a released effect. No further
methodological elaboration can replace that empirical object. An accept decision
requires at least the unchanged H81 release and an honest report of whatever it
shows.

## Evidence reviewed in this round

- Code commits `55b5087` and `5cc0a4a`, made while H81 remained below 40
  observations per arm and before any H81 outcome query.
- The 542-test repository suite, including the production 100,000-draw audit
  setting.
- The pinned outcome-free release audit at revision `8ce9eb75ed6e`: 82 H81
  blocks with counts 32/23/27 and four of 120 H95 triplets.
- Full remote reanalysis workflow `29561010800`, which completed acquisition
  hydration, all analyses, memo rendering, HF publication, and Space publication
  successfully at 07:20 UTC. The subsequent newer run started normally.
- The rendered manuscript and its protocol, evidence ledger, and theorem-
  validation matrix.

## Material improvement

### 1. The primary randomization p-values are now finite exact sums

Under the conditional preterminal design, arm counts are fixed. With a binary
outcome and `K` total successes, the vector of successes assigned to the three
arms has a multivariate-hypergeometric law. The analyzer now sums that support
for the directional and absolute contrast tails. It does not approximate the
published p-value by repeatedly shuffling labels.

This is the right null distribution for a Fisher sharp-null test conditional on
the stopping information used by the estimator. It also removes an unnecessary
random seed from the published inferential result.

### 2. Exact enumeration has two independent implementation checks

First, a five-block `2/2/1` fixture enumerates all 30 unique label assignments;
the closed-form support agrees with brute force to machine precision. Second,
the production analyzer retains 100,000 fixed-count permutations and records the
maximum discrepancy across one- and two-sided tails. The release fails closed
if that discrepancy exceeds 0.01. The exact support mass itself must equal one
within `1e-12`.

The one-percentage-point tolerance is an implementation alarm, not an
inferential tolerance or a license to perturb the exact p-value. The manuscript
now makes that distinction.

### 3. The newest full public-data rerun is operational

Workflow `29561010800` was not stuck. Its full screen took about 24 minutes after
hydration and then published normally. The newer published memo reports 2.27
million endpoint-price observations and 1,506 price-field changes in its live
screen, while the focal manuscript deliberately remains on corrected immutable
public-input revision `b389923...` with 2,004,680 distinct listings and the exact
3,219-of-3,219 completed-day event rebuild through July 16.

That separation is appropriate. The live memo's core source-health profile was
red because the OpenRouter API source was red even though the frontend source
was green. The open July 17 acquisition day should not silently replace the
paper's audited completed-day cut.

## Remaining reasons for rejection

### 1. H81 still has no released outcome

At the authoritative gate audit, H81 has 32 delegated-default, 23 no-fallback,
and 27 explicit-price-order-with-fallback first positions. No arm has reached
40, so no success rate, effect, confidence interval, exact p-value, realized
missingness pattern, or selected-provider result exists. Exact inference makes a
future result more credible; it does not create a current result.

### 2. The exact p-value tests a Fisher sharp null

The manuscript correctly calls the Newcombe and Bonferroni-Newcombe intervals
descriptive and does not call them inverted randomization intervals. It should
preserve this boundary after release. Rejecting the exact sharp null is not, by
itself, an exact confidence statement for a finite-population average effect
under heterogeneous treatment effects. The released discussion should lead
with effect magnitude and familywise interval, then state precisely what the
Fisher test rejects.

### 3. H81 transport remains narrow

Two models at adjacent ranking positions recur with zero eligible-support
turnover. H81 can identify an owned-account policy effect on those model-time
blocks. It cannot establish the market-wide value of fallback or hidden
selection. The manuscript must retain this finite-support interpretation even
if the result is large and precise.

### 4. H95 and PM1 remain future evidence

H95 has four of 120 fixed-horizon triplets. PM1 has 10 complete dates toward its
30-date, one-shot 15/15 split and may still fail its events-per-parameter support
gate. Neither may be substituted for H81, stopped early, pooled with H81, or
weakened after seeing an unfavorable result.

### 5. Live acquisition health needs a completed-day rule

The full rerun succeeded, but a successful workflow is not the same as a green
source profile. Paper updates should continue to require an immutable revision,
completed UTC dates, deduplication and event-ledger reconstruction, and explicit
source-health disclosure. The live memo can remain an operational dashboard;
it is not automatically a manuscript vintage.

## Required acceptance package

1. Let H81 reach its original 40-per-arm gate without changing cadence,
   eligibility, outcome coding, stopping, or model support.
2. Publish exactly the preterminal prefix selected by the frozen stopping rule.
   Report assignment replay, treatment compliance, arm counts, missingness,
   point effects, marginal and familywise intervals, exact one- and two-sided
   Fisher tails, Holm-adjusted directional tests, Monte Carlo discrepancy audit,
   the decomposition identity, intended-assignment bounds, and model-specific
   sensitivity.
3. Keep a null, sign reversal, wide identified set, failed audit, or failed
   transport check as the central result if the frozen release produces it.
4. Rewrite the abstract and conclusion around the realized sign, magnitude,
   uncertainty, and finite-support boundary. Do not replace the randomized
   contribution with another observational correlation.
5. Continue H95 to exactly 120 written triplets and PM1 to its unchanged
   completed-date and support gates as independent transport and temporal-
   prediction evidence.
6. Promote a newer public-data vintage only after the completed-day provenance
   audit passes; do not mix the current incomplete live memo cut into the pinned
   descriptive tables.

## Decision

The pre-release analysis is now acceptance-quality. The empirical paper is not
yet acceptance-ready because its focal empirical result remains physically
unqueried. My score rises only marginally, from 7.0 to 7.1, because the exact
test and fail-closed audit remove real risk but do not change the evidence set.
If H81 opens cleanly and the authors report the result without sign-dependent
revision or overgeneralization, I would expect the next decision to turn on the
substantive effect and its uncertainty rather than on methods or exposition.
