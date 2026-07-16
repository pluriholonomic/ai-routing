# Independent panel review — v10 common-menu hard null

Artifacts reviewed: the revised LaTeX manuscript, the frozen nine-date PM5
release, the endpoint-label symmetry panel, the 196-event lagged-price landing
panel, the matched common-menu hypergeometric null, the constructive
asynchronous-menu proposition, the dual-vintage release contract, and the
outcome-free H80 ledger. This review supersedes v9.

## Referee A — ACM EC / empirical IO

The revision invalidates the result that v9 regarded as the paper's most
promising descriptive fact. That invalidation is correct. Empty adjacent grid
points are not an identity counterfactual in a market where providers may select
from a shared discrete menu. Preserving the complete within-model price multiset
and randomizing the unique author endpoint changes the benchmark from 1.5% to
53.5%. The observed 54.3% author-shared rate is then unexceptional: the exact
upper-tail probability is 0.466, the author effect is 0.79 points with interval
[-9.0, 16.1], and the pair-density contrast is -0.94 points [-8.8, 12.0]. The
paper now states plainly that author identity is unsupported.

The temporal falsification is also valuable. The weak adjacent-grid null makes
20.4% exact landing on a lagged rival look like a 19.5-point response atom. The
tight common-menu null, matched on timestamp, risk-set size, and a factor-1.25
price band, predicts 13.4%. The residual 7.0 points has model-cluster interval
[-23.1, 12.2], provider-cluster interval [-22.4, 18.2], and turns negative after
deleting the dominant model. A strategic-copying claim is therefore not supported.
The past-only same-model sensitivity is more encouraging (14.4-point excess,
model-cluster interval [-0.1, 17.5], positive leave-one-model-out range), but the
interval still touches zero and effective support is concentrated in three model
clusters. Treating it as secondary is appropriate.

The asynchronous-menu proposition turns these empirical corrections into a
general identification contribution. A scheduled provider-specific refresh rule
and a rival-response rule can generate the same exact cross-sectional atoms and
strictly ordered lagged landings. The identified set [0, L/N] for exact strategic
landings is sharp under the declared unrestricted class. This is more useful than
another underpowered Hawkes screen because it says which additional restriction or
experiment is logically necessary.

My remaining concern is that the proposition obtains generality by allowing a
very flexible public menu and provider selector. The matched-menu null is the
substantive restriction, but its factor-1.25 band was selected after examining the
nine-date panel. The same-model historical sensitivity mitigates the SKU objection
but cannot absorb contemporaneous common model shocks. The earliest 30-date
replication is therefore essential. A stronger paper would also report a
predeclared same-provider/across-model control and show how the test behaves under
simulated asynchronous menus with known refresh clocks.

**Recommendation: REVISE AND RESUBMIT.** The identification correction is a
substantial intellectual improvement. It also removes the only current positive
identity result, so acceptance now depends on confirmatory evidence or a more
developed restricted-menu test.

## Referee B — operations research / platform systems

The implementation is strong. The release runner now resolves and pins one
immutable Hugging Face dataset revision before its first query; a second run at
commit `600bb41fd15189c70f8f78fce8cf0a519fb8dd61` reproduced all 16 artifact
hashes. Dynamic events require actual continuity of at most
15 minutes, exactly one observed mover, and a strictly prior rival set; gaps are
not silently bridged. The common-menu probability is exact hypergeometric rather
than Monte Carlo. Model- and provider-cluster bootstraps, leave-one-cluster-out
ranges, band sensitivities, continuity sensitivities, and concentration measures
are emitted in machine-readable output. The release runner now publishes the
author-symmetry and lagged-landing panels alongside PM1 and BM1--BM4.

The systems limitation is support, not code. Eighteen models and fifteen movers
produce 196 events, but one model supplies 73% of events and 85% of exact
landings. The tight null correctly refuses to convert this into a broad behavior
claim. H80 remains the only randomized route to a causal statement about realized
firmness, and it is only 33--37 of 500 assignments per arm.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** The artifact is
submission-grade; the confirmatory sample is not.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** The paper loses a visually striking
author-anchor headline but gains a more original and reusable contribution: a
falsification ladder showing that three increasingly plausible signatures have
different identifying content.

1. Excess ties relative to independent grid draws identify cross-provider
   dependence at exact price levels.
2. Adjacent-grid mass does not identify author salience because it ignores the
   realized price multiset.
3. Strictly lagged exact landing does not identify strategic response because an
   asynchronous common menu can reproduce it.

The first is supported. The second and third are negative hard-null results. The
theorem explains why the failures are structural rather than merely low power;
the matched-menu interval additionally shows that current finite-sample support is
weak.

### Mechanical gates

- Quote panel: 10 of 30 local outcome-free calendar dates; 20 additional dates are
  required before the locked comparison runs.
- H80: 33, 37, 34, and 36 of 500 first-position assignments per arm; 140/140
  assignments replay exactly; outcomes remain masked.
- H80 cadence forecast: approximately 456 hours at the pooled rate and 484 hours
  at the slowest-arm rate, subject to scheduler and eligibility failures.
- Price-atom promotion: the 30-date release must retain the factor-1.25 common-menu
  null and endpoint-label null without tuning to continuation data.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 93% | Dealer-and-dispatcher clearing remains distinctive. |
| Identification contribution | 95% | Two constructive equivalence results plus executable hard nulls are reusable. |
| Positive empirical discrimination | 61% | The tie atom survives; author identity and strategic landing do not. |
| Manuscript completeness | 99% | Full paper, proofs, corrected tables, claim ledger, and release contract. |
| Pipeline and release integrity | 99% | Hard-null panels and metrics are included in the dual-vintage release. |
| External validity | 66% | Dynamic events cover 18 models but are highly concentrated. |
| Firmness causal evidence | 40% | Assignment integrity is perfect but the minimum arm is only 6.6% complete. |
| Submission readiness | 78% | Conceptually strong; confirmatory and randomized evidence remain the bottleneck. |

The user-defined acceptance stop rule is not met. Keep the goal active. Do not
tune the endpoint-label, continuity, or factor-1.25 menu specifications after
observing continuation dates. The next legitimate empirical promotion is the
locked 30-date/H80 release; theory and simulation may be strengthened without
reading masked outcomes.
