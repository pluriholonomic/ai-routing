# Independent panel review — v7 timing-identification revision

Artifacts reviewed: the 18-page rendered manuscript, Proposition 1 and its
constructive proof, the corrected frozen Brown--MacKay comparison, the executable
dual-vintage release, the outcome-blind H80 gate, and the 2026-07-16 08:27 UTC
assignment-only accrual audit. This review supersedes v6 for the current paper.

## Referee A — ACM EC / empirical IO

The coarsened-timing proposition is correct and relevant. It formalizes a point
that the empirical implementation now respects: an arbitrary row order inside a
five-minute snapshot has no economic content. The construction also clarifies why
more observations at the same frequency cannot reveal a latent leader, and why
strictly earlier links remain temporal candidates rather than causal responses.
This is a useful mechanism-identification result for marketplaces with public
menus but private, asynchronous update clocks.

The proposition is deliberately nonparametric and therefore not deep theory. With
unrestricted latent public state and unrestricted response maps, observational
equivalence is close to definitional. The paper handles that limitation honestly
and lists the restrictions or additional data that would restore identification.
I would treat the result as a rigorous measurement boundary, not as a standalone
EC theorem contribution. Its value comes from disciplining the empirical claims
and explaining the corrected Brown--MacKay design.

The updated assignment audit is clean: it projects only assignment fields, replays
92 of 92 first-position assignments, and leaves outcomes masked. Counts of 22,
24, 22, and 24 remain far below the registered 500-per-arm release. The pricing
panel has not reached its 30-date prefix.

**Recommendation: REVISE AND RESUBMIT.** The identification proposition raises
the manuscript's conceptual coherence, but it cannot substitute for either
confirmatory empirical gate.

## Referee B — operations research / platform systems

The theorem-and-audit pairing is a genuine systems contribution: it separates
what an observation clock can recover from what the dispatch system knows. The
last-complete snapshot-cache design is also sensible because it fails closed on
partial hydration while allowing a verified stale base to be combined with fresh
workflow artifacts. The current cache could not be seeded during the upstream
Hub outage, but probe collection and daily compaction remained remote and healthy.

I remain concerned about transport. The randomized study currently represents
four dynamically selected hot models and one account. Even at 500 per arm, the
paper should report model-cluster heterogeneity and state clearly that repeated
model-hour blocks increase temporal support rather than target-population breadth.
Those diagnostics are already in the registered release contract, so I do not
request a new specification.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** The paper is ready for
the registered release, not yet for acceptance.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** Proposition 1 converts an important
negative empirical lesson into a precise identification statement and strengthens
the paper without changing a frozen estimand. It does not resolve the missing
sample support.

Mechanical gates:

- H80 first-position assignments: 22, 24, 22, and 24 of 500 per arm; 92/92 seed
  replays; outcomes masked; projected gate in approximately 471--492 hours at
  the observed assignment cadence.
- Quote panel: 10 of the earliest 30 observed dates at the last complete audit.
- The release must still run PM1 and BM1--BM4 on both calendar prefixes, publish
  the registered H80 family and support diagnostics, update the source manifest
  and paper, and undergo a new review in the same release cycle.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 93% | Dealer-and-dispatcher microstructure plus focal anchoring remains distinctive. |
| Timing-identification contribution | 82% | Correct and useful, but intentionally nonparametric and not deep standalone theory. |
| Manuscript completeness | 98% | Complete paper, proof, figures, claim ledger, and reproducibility contract. |
| Pipeline and release integrity | 99% | Frozen vintages and outcome masking are executable; remote base hydration is resilient once a complete cache seeds. |
| Focal-anchor inference | 90% | Both model-cluster grid sensitivities exclude zero. |
| Pricing-technology discrimination | 70% | The non-identification boundary is now formal, but positive slow-initiator support remains absent. |
| Firmness causal evidence | 37% | Assignment integrity is perfect, but only 22--24 of 500 observations per arm have accrued. |
| Submission readiness | 76% | One synchronized confirmatory release cycle remains. |

The user-defined acceptance stop rule is not met. Continue the registered
collection; do not open a new outcome-dependent specification search.
