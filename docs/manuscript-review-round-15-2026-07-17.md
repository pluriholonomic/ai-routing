# Independent-style review, round 15

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7/10, borderline reject.** The revision now reads as one paper
rather than a collection of marketplace diagnostics. It has a well-defined
economic object, unusually credible evidence governance, a mechanism-matched
randomized design, and a prospectively launched independent replication. The
remaining obstacle is substantive rather than editorial: neither randomized
study has released an outcome. I would encourage resubmission after the frozen
gates open, but I would not accept an empirical paper whose headline treatment
effects are still unobserved.

## Improvements since round 14

1. **The main-text sprawl is largely fixed.** The steering, Brown--MacKay,
   revenue-share, cross-router, entry, retry, and conduct exercises now occupy a
   compact falsification section. Full plots, the replication ladder, theorem
   statements, and proofs sit in the appendix. The main argument stays centered
   on displayed menus versus hidden clearing.
2. **The external-support problem now has a real prospective response.** H95 was
   frozen in commit `00351dd` before its first request. It uses a fixed horizon
   of 120 three-model plans, exact 120-per-arm first-position balance, ranks
   7--30, pre-request eligibility records, within-triplet randomization, and
   conservative treatment of missing attempts. It is explicitly never pooled
   with H81.
3. **Prospective operation is verified.** GitHub Actions run `29555584388`
   completed after the H95 freeze and preserved telemetry. The authors did not
   inspect workflow logs or outcomes before the 120-triplet gate. This is a
   meaningful improvement over merely proposing a replication.
4. **The cross-router design is no longer ambiguously retrospective.** H94 has a
   precise future-only activation at 2026-07-17 04:30:20 UTC; the known 03:30
   discovery cross-section is excluded from every event and gate calculation.
5. **The stopped-design simulation now meets its declared scale.** The sharp-null
   test rejects 5.05% of 2,000 experiments, with Monte Carlo standard error 0.49
   percentage points. The earlier 500-experiment qualification is resolved.
6. **The paper and evidence genealogy agree.** The LaTeX, amendment ledger,
   validation matrix, machine-readable registry, remote workflow state, and
   release manifest now distinguish prospective activation from released
   empirical evidence.

## Remaining reasons for rejection

### 1. There is still no focal treatment-effect result

H81 remains at 29, 22, and 25 assignments at the pinned release, below its
original 40-per-arm gate. H95 has launched but is far below its fixed 120-triplet
horizon. The paper can validate assignment, treatment metadata, stopping-rule
inference, transport gates, and remote collection, but it cannot yet report the
fallback-option or hidden-selection effect. This is decisive for a title and
abstract centered on fallback and selection.

### 2. H81 transport remains two-model transport

The H95 design is the correct fix, but a protocol is not a result. Until H95
reaches at least eight audited models, effective model count five, and its other
declared transport gates, the only randomized support is the two repeated H81
models. A narrow effect may still be publishable, but the prose must continue to
say owned-account model--time-block effect rather than market mechanism.

### 3. The public evidence remains primarily measurement and falsification

H82 fails pretrends; H84 has a backward placebo; H94 has no eligible dynamic
result; and five-minute coarsening leaves literal front-running with a zero lower
bound. The paper treats these facts correctly. They nevertheless cannot substitute
for the randomized execution result.

### 4. Welfare remains deliberately unestimated

The generalized procurement score is economically sensible, but values, fidelity,
provider cost, private rebates, capacity response, and congestion externalities
are absent. The design can estimate completion/spend/delay policy effects for one
account, not social surplus. This is an acceptable boundary if the randomized
execution effects are strong; without them, the mechanism-design contribution is
still mostly an estimand and data-contract agenda.

### 5. Confirmatory release independence should be stronger

The authors disclose the two legacy H81 launch-block aggregates and raw-source
access risk. At the gate, the analysis should run once in a clean remote job that
pins the immutable prefix, queries outcomes only after checking assignment-only
support, logs the first access, and publishes input/output hashes regardless of
sign. A second person or independent runner should reproduce the release bundle.

## Acceptance conditions

1. Release H81 exactly once at the original gate under the corrected preterminal
   fixed-count design; report both primary contrasts, uncertainty, Holm-adjusted
   randomization tests, missingness bounds, spend/latency observation rates, and
   leave-one-model-out estimates regardless of sign.
2. Reach the fixed H95 horizon and report it separately. State explicitly which
   model-support and temporal-concentration gates pass; do not broaden the claim
   if they fail.
3. Keep H94 dynamic language suppressed until every prospective gate passes.
4. Run the confirmatory release from a clean immutable environment and archive
   the first outcome-access event, code commit, dataset hash, environment lock,
   and output hashes.
5. Rewrite the abstract's result sentence after H81 releases. If both H81 and H95
   are null or imprecise, make that the result rather than reverting to the public
   proxies.

## Decision

**Borderline reject because the decisive data are still gated.** The manuscript
itself is materially improved and the previously missing replication is genuinely
running. The remaining rejection is not a request for more narrative or another
proxy regression. It is a request to execute the already frozen experiments and
report their outcomes without changing the rules.
