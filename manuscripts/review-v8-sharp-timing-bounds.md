# Independent panel review — v8 sharp timing bounds

Artifacts reviewed: the 18-page rendered manuscript, Proposition 1 and its
constructive proof, Corollary 2 and the executable timing-identification audit,
the corrected frozen Brown--MacKay comparison, the dual-vintage release contract,
and the 2026-07-16 09:30 UTC outcome-free H80 accrual audit. This review supersedes v7.

## Referee A — ACM EC / empirical IO

The revision makes a meaningful advance over the earlier generic
non-identification statement. The paper now defines a causal named-rival response
estimand, derives its sharp nonparametric identified set under the public
observation clock, and computes the set using the same candidate construction as
the reaction-rule experiment. In the frozen panel, 188 of 274 repricing events
have a unique strictly prior rival candidate within 72 hours, so the sharp set is
`[0, 68.6%]`. The endpoints have constructive economic interpretations and are
attainable under the proposition's unrestricted scheduled and reactive paths.

This is a useful result: the data contain abundant apparently ordered rival moves,
yet even those moves supply no positive lower bound on causal response. The result
turns a common empirical temptation—calling the most recent rival a leader—into a
measurable identification failure. It should travel to other administered-menu
platforms with coarse public clocks.

The interval is nevertheless very wide. It does not provide positive evidence of
front-running, algorithmic response, or leader-follower pricing. Its lower endpoint
is zero, and the upper endpoint is driven by candidate availability rather than an
exclusion restriction. The theorem remains a disciplined measurement boundary,
not a standalone deep theory contribution. The paper presents it at the right
level and does not overclaim.

The main empirical gates remain unsatisfied. The quote panel has 10 of the earliest
30 dates. The randomized first-position ledger has only 22, 24, 25, and 25 of 500
assignments per arm. Outcomes remain masked, which is the correct procedure.

**Recommendation: REVISE AND RESUBMIT.** The new bound is publishable supporting
theory, but the paper still needs the preregistered confirmatory release.

## Referee B — operations research / platform systems

The executable audit is well aligned with the theorem. It counts capture batches,
same-bin ambiguity, unique strictly prior candidates, tied prior candidates, and
events without a prior rival; an invariant requires the upper-bound candidate set
to equal the reaction-panel link set. Synthetic tests cover simultaneous updates
and an empty panel. This is substantially better than a prose-only caveat.

The release design is also credible: the pricing and Brown--MacKay analyses are
frozen for the earliest 30-date prefixes, and the randomized study releases only
after 500 assignment-verified first positions per arm. However, the transport
problem remains. Four hot models and one account do not represent the full market,
and more repeated blocks increase temporal precision rather than target-population
breadth. The registered model-cluster diagnostics and explicit one-account claim
boundary should remain prominent at release.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** The machinery is ready;
the confirmatory support is not.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** Corollary 2 and the `[0, 68.6%]`
application raise the paper above a generic warning about coarse timestamps. The
paper now has a precise, executable partial-identification contribution. That
improves novelty and claim discipline, but it cannot replace the two mechanical
sample gates.

### What would change the decision

1. Reach the earliest 30-date prefix for both frozen quote vintages and run PM1
   and BM1--BM4 without changing the estimands.
2. Reach 500 assignment-verified first positions in every H80 arm, then release
   the masked Holm-adjusted family, rank-gradient test, and model-cluster support
   diagnostics.
3. Update the manifest, estimates, figures, PDF, and reviewer audit in one
   synchronized release commit.
4. Retain the negative causal boundary if the new data do not narrow it; do not
   turn candidate ordering into a front-running claim.

### Mechanical distance to the gates

- H80: 22, 24, 25, and 25 of 500 per arm, or 4.4%--5.0% complete. At the observed
  assignment cadence, the outcome-free projection is roughly 472 hours at the
  pooled rate and 515 hours at the slowest observed arm rate. Assignment replay
  is 96/96 and outcomes remain masked.
- Quote panel: 10 of 30 required dates, or 33.3% complete at the last complete
  audit.
- Release execution: implemented but not triggerable until both chronological
  gates are met.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 93% | Dealer-and-dispatcher microstructure plus focal anchoring remains distinctive. |
| Timing-identification contribution | 90% | The non-identification result is now sharp, executable, and quantitatively linked to the data. |
| Manuscript completeness | 99% | Complete paper, proofs, figures, claim ledger, and reproducibility contract. |
| Pipeline and release integrity | 99% | Frozen vintages, masking, replay, and synchronized release code are in place. |
| Focal-anchor inference | 90% | Both model-cluster grid sensitivities exclude zero. |
| Pricing-technology discrimination | 73% | Candidate abundance is measured, but the causal response lower bound remains zero. |
| Firmness causal evidence | 37% | Assignment integrity is perfect, but only 22--25 of 500 observations per arm have accrued. |
| Submission readiness | 79% | The conceptual paper is close; confirmatory sample support is the dominant remaining gap. |

The user-defined acceptance stop rule is not met. Continue the registered remote
collection and execute the synchronized release when the mechanical gates open;
do not start a new outcome-dependent specification search.
