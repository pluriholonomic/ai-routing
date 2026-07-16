# Independent panel review — v9 author-identity correction

Artifacts reviewed: the 19-page rendered manuscript, the frozen nine-date PM5
rerun, the author-price identity audit and machine-readable output, the exact
selected-tie random-label benchmark, the all-market adjacent-level placebo design,
the six-program dual-vintage release, and the outcome-free H80 ledger. This review
supersedes v8.

## Referee A — ACM EC / empirical IO

This revision corrects what had been the paper's most attractive but least
disciplined statistic. Conditioning on a model already having a tied minimum
makes the event “the author is at that minimum” mechanically likely. The new
combinatorial benchmark is exact conditional on market thickness, tie size, and
the number of author-operated labels. On the frozen endpoint snapshot, the robust
crosswalk observes 48 matches among 54 selected tied models while the random-label
benchmark expects 47.95. The upper-tail probability is 0.625. The old selected-tie
result is therefore correctly demoted.

The replacement is economically better. It starts from every author-observable
multi-provider market rather than selecting ties and asks whether any third-party
quote lies exactly at the author's price. The adjacent-level placebo preserves the
author's price, the provider set, and the displayed price grid while moving only
the candidate focal level. Exact matches occur in 54.7% of 95 models versus 1.4%
at adjacent dime-grid levels. The 53.3-point excess has an author-cluster bootstrap
interval of [31.0, 80.4] points, remains 53.3--54.4 points over four fixed grids,
and stays above 47.8 points after deleting any one author. Ten of twelve author
clusters are positive, with one-sided sign-test p=0.019.

This is a credible descriptive focal-atom result and a useful empirical-design
lesson. It does not identify causal salience. A common cost convention, public
reference pricing, or copying at listing can all create the atom. Moreover, the
corrected specification was chosen after inspecting the frozen panel. The paper
labels it post-freeze, freezes the code and grids, and adds PM5 to the earliest
30-date dual-vintage release. That is the right remedy, but it means the result is
not yet confirmatory.

**Recommendation: REVISE AND RESUBMIT.** The correction raises my confidence in
the authors and improves the estimand, but the 30-date replication is now even
more important because a former headline fact was selected incorrectly.

## Referee B — operations research / platform systems

The implementation is unusually auditable. Provider-author identity now uses the
shared provider-family crosswalk rather than substring matching. The code emits
the selected-tie benchmark, the all-market panel, four placebo-grid sensitivities,
author-cluster bootstrap inference, a sign test, and leave-one-author-out bounds.
Synthetic tests cover aliases, fully tied markets, deterministic bootstrap output,
and empty panels. The manuscript-vintage runner executes PM1, PM5, and BM1--BM4
under both calendar cutoffs and places the focal-atom metrics in the fixed
comparison registry.

The main systems concern is transport. Twelve author families are not the universe
of open-weight model authors, and the cross-section does not establish that the
same endpoint identity or convention operates on other routers. The 30-date gate
tests temporal stability, not cross-platform transport. The paper states this
boundary correctly.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** The release machinery
is ready; the confirmatory calendar and randomized firmness samples are not.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** The revision is a net improvement
despite invalidating the old 65-of-72 interpretation. The new all-market atom is
both more demanding and more informative, and the explicit failure of the
selected-tie null is itself a reusable marketplace-measurement result. The paper
now distinguishes three claims that were previously blurred:

1. minimum-price ties exceed independent grid formation;
2. third-party prices have excess cross-sectional mass at the author price; and
3. active author leadership remains unidentified until an author reprices.

Only the first is already promoted. The second is frozen for the 30-date
replication. The third remains unfired.

### Mechanical gates

- Quote panel: 10 of 30 required dates at the last complete remote audit. The
  six-program release now includes the corrected PM5 estimand.
- H80: 22, 24, 25, and 25 of 500 first-position assignments per arm; 96/96
  assignment replays; outcomes masked.
- Timing/front-running: the sharp named-rival response set remains [0, 68.6%], so
  no positive causal lower bound is available from public snapshots.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 94% | Dealer-and-dispatcher microstructure plus two distinct focal atoms is unusual and well motivated. |
| Author-identity estimand | 84% | Corrected all-market design is strong descriptively but post-freeze and noncausal. |
| Timing-identification contribution | 90% | Sharp and executable measurement boundary. |
| Manuscript completeness | 99% | Full paper, proofs, corrected tables, claim ledger, and release contract. |
| Pipeline and release integrity | 99% | PM5 is now part of the same immutable dual-vintage comparison as PM1 and BM1--BM4. |
| Pricing-technology discrimination | 75% | Tie and author-price atoms are sharp; active following and rival response remain unidentified. |
| Firmness causal evidence | 37% | Only 22--25 of 500 first-position observations per arm have accrued. |
| Submission readiness | 80% | The conceptual and measurement contribution is close; confirmatory support remains the dominant gap. |

The user-defined acceptance stop rule is not met. Continue the registered remote
collection. Do not revise the PM5 placebo grids or author mapping after seeing new
dates; the next legitimate change is the synchronized 30-date release.
