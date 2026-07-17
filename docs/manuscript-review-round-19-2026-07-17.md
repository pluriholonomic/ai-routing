# Independent-style review, round 19

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **6.8/10, weak reject pending the registered releases.**

## What materially improved

1. **The conference narrative is now proportionate to the evidence.** The main
   argument ends on page 13, with references on pages 14--15. The long
   price-atom nulls, calibration simulations, and proofs have moved to Appendix
   A. The main text retains one interpretation table and the high-level
   observational-equivalence result.
2. **PM1 now has a genuine temporal validation contract.** The new executable
   module waits for 30 completed UTC dates, excludes the open date, estimates on
   dates 1--15, and scores dates 16--30 once. Price gaps, GPU changes,
   congestion, and rival moves are prior-close variables; provider activity is
   learned from training outcomes only.
3. **The temporal test has an explicit inferential object.** The primary
   estimand is the date-weighted paired log-loss gain of lagged state over
   duration/calendar state. Adjacent-rung sign-flip tests receive Holm
   correction, and date-cluster, model-cluster, and leave-one-model-out
   diagnostics are fixed before release.
4. **Prospective accrual is real and remotely reproducible.** At immutable
   revision `1311e5e513c6`, H81 has 80 verified blocks with counts 31/23/26.
   H95 has three compliant triplets, nine blocks, eight unique models, and
   effective model count 7.36. Outcomes remain unqueried. Consolidation,
   confirmatory preflight, and remote health all passed on clean runners.

## Remaining reasons for rejection

### 1. The focal randomized estimands are still absent

The paper is correctly organized around fallback and hidden selection, but it
still reports neither effect. H81 lacks 9, 17, and 14 assignments by arm. H95 is
only 3/120 triplets. Until the frozen release transactions produce effect sizes,
randomization intervals, missingness bounds, and heterogeneity checks, the focal
claim is a design rather than a result.

### 2. The temporal pricing conclusion is still unopened

Only 10 completed dates exist, so the new PM1 module correctly exposes no event
count, fit, AUC, or holdout loss. Its implementation fixes the earlier leakage
problem, but it cannot yet upgrade the nine-day descriptive ladder.

### 3. Transport remains the binding empirical issue

H81's eligibility support remains two repeated models. H95 now clears its
minimum breadth target in an assignment-only sense, but three triplets cannot
establish model-robust policy effects. The paper must preserve the distinction
between H81 internal validity and H95 transport rather than combining them.

## Required next release

1. Release H81 only at the unchanged 40-per-arm gate, excluding the terminal
   block, with the two registered component contrasts, exact conditioned
   randomization inference, simultaneous uncertainty, and worst-case treatment
   and outcome missingness bounds.
2. Continue H95 to its fixed 120-triplet horizon and report its blocked
   randomization contrasts, support concentration, and leave-one-model-out
   results separately from H81.
3. At 30 completed dates, run the frozen PM1 15/15 holdout and both registered
   nine-day/30-day vintages at one immutable revision. Report a null or failed
   support gate as prominently as a positive result.

## Decision

The structural objection from round 18 is resolved. The remaining rejection is
empirical and preregistered: the decisive data do not yet exist at their release
thresholds. No further prose expansion should occur before those gates open.
