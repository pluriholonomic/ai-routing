# Independent panel review — complete empirical paper

Artifact reviewed: `output/pdf/inference-market-microstructure.pdf` (16 pages,
including appendices), together with the frozen v3 estimate manifest and the
registered promotion gates. This review supersedes the manuscript-completeness
concern in the v3 review. It does not waive the data-accrual gates.

## Referee A — ACM EC / empirical IO

### Assessment

The paper now makes a coherent and plausibly novel empirical contribution. Its
central object is not model routing in the usual sense, but the provider layer
conditional on a model: providers post sticky token-price menus, minimum prices
cluster at the model author's first-party quote, and a router manufactures a
firm delivered service by substituting among individually revocable endpoints.
That combination is new enough for EC and is stated with unusually careful
observability boundaries.

The strongest evidence is the randomized crossover. The fixed-order pilot is
properly demoted after its rank gradient fails under randomized order. The
surviving result — a roughly 19 percentage-point default-versus-pinned success
gap with no meaningful cheapest/second/random gradient — distinguishes
platform-level substitution from rank-specific stale-quote refusal. The paper
also correctly avoids interpreting the public inverse-square display as
realized demand.

The focal-price result is now inferentially stronger. The 45.9%
minimum-tie rate is much larger than both the 13.4% cent-grid null and the 27.6%
dime-grid sensitivity, and 65 of 72 author-observable ties match the author
price. A post-freeze 1,456-model-day refresh retains a 32.2 percentage-point
cent-grid excess with model-cluster 95% interval [25.8, 37.8] and an 18.0-point
dime-grid excess with interval [9.7, 25.1]. Whole models are resampled and the
null is re-simulated inside each bootstrap draw.
The steering result has the right sign in the eligibility-confirmed subset, but
that subset is only 11 versus one provider-model cells and cannot yet support a
causal negative-memory claim.

### Required promotion checks

1. Reach at least 500 valid attempts in each pinned arm and report the registered
   Holm-adjusted randomization tests, assignment replay, first-position
   estimands, and the cheapest/second/random rank-gradient test.
2. Re-estimate pricing duration, gap hazard, conduct screens, and Brown–MacKay
   diagnostics after at least 30 days, showing both the frozen nine-day vintage
   and the registered 30-day vintage.
3. Keep steering as an audit statistic unless the eligibility-complete panel
   becomes large enough or an exogenous visibility/eligibility instrument fires.

### Recommendation

**CONDITIONAL ACCEPT.** The novelty and manuscript are adequate. The remaining
requirements are pre-registered inference and accrual, not a request to search
for a better specification. A sign reversal in the randomized firmness or
30-day administered-menu result reopens the decision.

## Referee B — operations research / platform systems

### Assessment

The manuscript now connects the empirical objects to an OR-relevant design
problem. The planner chooses admission, routing, capacity, and quality subject
to queues and retry feedback; providers, router, harness, and users solve
different decentralized problems. The measured wedge is precise: a visible
money quote is an eligibility advertisement, while the platform sells a
reliable composite through fallback. This supports the design implication that
best execution needs expected money cost, fill probability, delay, and fidelity,
not posted price alone.

The data architecture and reproducibility account are credible. Five-minute
public panels, owned realized probes, preregistered assignment rows, frozen
estimate manifests, and an outcome-masked transparent-compute comparator form
a strong measurement stack. The paper is appropriately conservative about the
retry IV, literal front-running, collusion, and global welfare.

The chief limitation is that the queueing and capacity terms in the planner's
problem are not structurally estimated. This is acceptable for an empirical
microstructure paper, but a top OR venue would regard the current optimization
model as an organizing framework rather than a solved operational model. The
Akash comparator is correctly relegated to the appendix because no eligible
post-cutoff observation has matured.

### Recommendation

**ACCEPT, MINOR REVISION** for an empirical market-design track, conditional on
the same randomized and 30-day promotion gates. For a theory/optimization track,
the paper would need a separately identified capacity or queueing model; that is
not necessary for the present submission framing.

## Meta-review

### Decision

**CONDITIONAL ACCEPT — two calendar-accrual gates remain.** The previous blocking issue
that the paper was an outline is resolved: the submission is complete,
self-contained, visually checked, and explicit about negative and power-gated
results. The remote capture and full-analysis workflows also complete without
this laptop.

Acceptance converts mechanically when all of the following are present in one
versioned release:

- at least 500 valid observations per pinned arm with the default-firmness level
  and flat rank gradient retained under registered randomization inference;
- at least 30 days of five-minute data with nine-day and 30-day estimates shown;
- no widening of the front-running, collusion, steering-causality, or welfare
  claims beyond the paper's current ledger.

Both remaining quantitative gates are calendar/data-accrual gates. The
model-cluster grid-null interval has now been completed. If all signs persist,
the paper is submission-ready for ACM EC or an empirical marketplace/operations
venue. If the randomized default advantage disappears, Fact 3 must be rewritten;
if the 30-day price process ceases to look sticky and gap-dependent, Fact 1 must
be narrowed.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 90% | Provider-level inference microstructure is sharply distinguished from model routing. |
| Manuscript completeness | 95% | Full paper, figures, appendices, claim ledger, and reproducibility account exist. |
| Pipeline/operations | 95% | Remote capture and full analysis both complete successfully. |
| Core causal evidence | 72% | Randomized direction is strong but only 76 observations per pinned arm; focal-anchor inference is now cluster-aware. |
| Dynamic pricing inference | 55% | Nine observed days versus the registered 30-day gate. |
| Submission readiness | 80% | The bounded inference addition is complete; two mechanical accrual gates remain. |

The correct bottom line is therefore: the project has succeeded at producing a
novel, defensible paper and a working empirical system, but has not yet earned
the final top-venue acceptance stop condition.
