# Independent panel review — v6 coarsened-reaction audit

Artifacts reviewed: the corrected manuscript and rendered PDF, the executable
dual-vintage pipeline, the frozen Brown--MacKay audit and figure, the H80
outcome-blind gate, and the v5 identification correction. This review supersedes
v5 for the current code and paper state.

## Referee A — ACM EC / empirical IO

The new revision fixes two economically meaningful sources of endogenous timing.
Repricing frequency now uses market exposure rather than a provider's event span,
and changes first observed in the same five-minute snapshot are not assigned a
fictional leader--follower order. The latter correction is especially important
for any claim about algorithmic response or front-running.

The revised Brown--MacKay comparison is appropriately negative. A cadence-price
association remains precise, including on the selected public-quality overlap,
but the frozen reaction design has no slow-initiator risk pairs. The richer rule
barely improves point RMSE; the seven-cluster bootstrap interval crosses zero.
Reporting the exact sign-flip p-value alongside the incompatible few-cluster
uncertainty, and choosing the conservative verdict, is good practice.

The executable nine-day/30-day machinery is a real improvement over a prose
promise. It fixes the calendar prefixes without outcomes, reuses identical
programs, restricts the comparison metric set, canonicalizes outputs, and records
artifact hashes. This substantially lowers researcher degrees of freedom at the
next release.

The focal-anchor result remains the strongest novel fact. The Brown--MacKay audit
now sharpens the interpretation: cadence heterogeneity is not enough to infer a
strategic reaction technology. H80 remains an unfinished causal experiment.

**Recommendation: REVISE AND RESUBMIT.** I would reconsider favorably after the
earliest 30-day comparison and the preregistered 500-per-arm H80 release. No new
specification search is requested.

## Referee B — operations research / platform systems

The paper now has a credible time-coarsening contract. This matters for routing
markets because the observation clock is much slower than the hidden dispatch
clock. Excluding ambiguous same-snapshot order is preferable to converting file
order into a pseudo-event stream. The dual-vintage release program and remote
nightly integration are also strong systems-reproducibility contributions.

The mechanism contribution remains incomplete. The state-only versus
Brown--MacKay comparison is predictive, not structural; only seven test clusters
are present; provider costs, internal update times, and private eligibility remain
unobserved. The H80 first-position experiment has excellent assignment integrity
but only 15--22 observations per arm against a target of 500.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** The manuscript is now
methodologically safer and more interesting, but the top-OR empirical threshold
still requires the two registered releases.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** The revision makes genuine progress:
it removes artificial reaction ordering, corrects cadence exposure, produces a
new falsifiable structural-twin comparison, and automates the confirmatory
vintages. These improvements do not substitute for the outstanding sample gates.

Current mechanical gates remain:

- H80 first-position assignments: 15, 20, 19, and 22 of 500 per arm, with 100%
  assignment replay and pre-gate outcomes masked.
- Quote panel: 10 observed dates, with 20 more needed for the earliest 30-date
  prefix. The nine-day vintage is fixed to 2026-07-07 through 2026-07-15.
- At release, PM1 and BM1--BM4 must run on both prefixes; H80 must publish the
  Holm-adjusted first-position tests and rank gradient; the source manifest,
  paper, and reviewer audit must update in the same commit.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 92% | Dealer-and-dispatcher microstructure plus focal anchoring remains distinctive. |
| Manuscript completeness | 97% | Complete paper, two audit corrections, figures, theory, and claim ledger. |
| Pipeline and release integrity | 99% | Outcome-blind H80 and executable hashed dual vintages are wired into the remote nightly job. |
| Focal-anchor inference | 90% | Both model-cluster grid sensitivities exclude zero. |
| Pricing-technology discrimination | 68% | Corrected frozen test is sharp but has seven holdout clusters and no slow-risk pairs. |
| Firmness causal evidence | 35% | Only 15--22 of 500 first-position observations per arm. |
| Submission readiness | 74% | One synchronized confirmatory release cycle remains. |

The correct stopping decision remains to continue the registered collection and
analysis. The paper has not met the user's acceptance stop rule.
