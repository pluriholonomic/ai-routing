# Independent-style review, round 26

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **8.0/10, borderline / weak reject pending the registered H81
release.**

## Summary judgment

This revision closes the most important remaining design ambiguity in the
independent H95 replication before outcome access. H95 executes three model
blocks sequentially within each randomized triplet, so an earlier policy could
affect a later block. The paper now separates the frozen primary three-block
estimator from a secondary position-zero estimator. Because the first position
precedes every other block in its triplet and policy labels are randomized over
positions, this secondary estimator is design-unbiased for the conditional
finite population of first-position models even under arbitrary carryover from
earlier blocks to later blocks.

The revision provides the corresponding exact nuisance-conditioned pairwise
randomization tests, a separate two-test Holm family, and simultaneous
Hoeffding--Serfling confidence sets. A planted-interference simulation shows why
the distinction matters: the full three-block estimator reaches 0.244 maximum
absolute bias as carryover increases, while the position-zero estimator remains
within 0.0011. The price is substantial imprecision: the position-zero design
interval has mean width 0.810 at the frozen 120-triplet horizon.

This is a real methodological improvement, not new empirical evidence. Exact-head
remote audit `29569590704` recorded H95 support at five of 120 triplets and H81
at 32/24/28 blocks, with both outcome gates closed, on commit `4860015` and
immutable data revision `f5b822812a8266200c9b277e88578c8829338e83`. The main
reason for rejection therefore remains unchanged: the focal H81 causal result
does not yet exist, H95 remains far from its horizon, and the PM1 temporal
holdout is unopened.

## Evidence reviewed in this round

- The dated H95 position-zero protocol amendment.
- Production position-zero policy and contrast panels with fail-closed outcome
  handling.
- Exact conditional pairwise Fisher tests and the secondary Holm family.
- Simultaneous finite-population policy-mean intervals propagated to contrasts.
- A 25,000-experiment planted-interference audit across five carryover strengths.
- The new position-zero corollary and full proof.
- Updated release protocol, evidence registry, amendment ledger, theorem
  inventory, claim table, limitations, and reproducibility history.
- The new three-panel interference-bias, precision, and coverage figure.
- The full repository suite: 563 passing tests.

## Material improvements

### 1. Sequential interference is now an estimand distinction rather than a caveat alone

The primary H95 estimator still uses all three randomized model blocks and
therefore requires the registered no-cross-block-interference assumption for a
direct-policy interpretation. The secondary estimator uses only triplet
position zero. Conditional on the realized first-position model and treatment
counts, arm labels are a complete randomization across triplets. Earlier blocks
within the same triplet cannot contaminate that outcome because none exist.

The paper correctly does not silently replace the primary estimand. The new
analysis is a sensitivity with its own multiplicity family and lower precision.
Agreement between the two estimators would support robustness; disagreement
would narrow the defensible claim to position zero.

### 2. The secondary inference matches the randomized design

For each focal pair, conditioning on nuisance-arm membership leaves the focal
labels uniformly distributed over the observed focal units. The resulting
hypergeometric Fisher tail is exact under the pairwise sharp null. Holm controls
the two-test secondary family. Hoeffding--Serfling policy-mean intervals use
finite-population correction and are propagated conservatively to the pairwise
contrasts.

This preserves the paper's recent discipline: exact inference is tied to the
actual reference experiment, while descriptive superpopulation intervals are
kept distinct from design-valid uncertainty.

### 3. The adversarial validation demonstrates both robustness and cost

The simulation fixes direct policy effects at zero and plants increasingly
strong carryover into later positions after delegated routing appears earlier
in the triplet. Across 5,000 assignments at each of five strengths, the full
three-block estimator's maximum absolute bias is 0.2437; the position-zero
estimator's is 0.00102. Worst observed simultaneous position-zero design
coverage is 100%, while mean interval width is 0.8105.

The simulation is not the source of the validity claim. Its role is to show
that the sequential-interference concern can be consequential and that the
identified remedy is much less precise.

### 4. Missingness and claim boundaries remain fail-closed

An unknown position-zero outcome suppresses the secondary complete-data point
estimate and test. Missingness confined to later positions can suppress the
primary complete-data analysis without erasing the separately observed
position-zero analysis. The paper also states that position zero removes only
earlier *within-triplet* carryover; it does not eliminate contamination from
unrelated traffic before the triplet begins.

## Remaining reasons for rejection

### 1. H81 still has no released focal randomized outcome

The outcome-blind support is 32 delegated-default, 24 no-fallback, and 28
explicit-price-order blocks. There is no released effect magnitude, confidence
set, exact p-value, decomposition, missingness result, or selected-provider
distribution. This remains the decisive missing piece.

### 2. H81's transport support and design precision remain narrow

The study covers two models. Its design-valid interval is necessarily wide,
and the preregistered Holm family has useful power only for large component
wedges. A null result cannot establish practical equivalence.

### 3. H95 remains a prerelease scaffold

Five of 120 triplets are enough to audit operation, not estimate the registered
replication. The current schedule also fails its six-hour concentration gate.
The fixed hourly cadence and horizon must remain unchanged.

### 4. Position zero does not solve all interference

It removes earlier blocks inside the current triplet. It does not rule out
queueing, rate-limit, cache, provider, or account state inherited from unrelated
requests before position zero. Its design interval is also about 0.81 wide at
the fixed horizon, so it is a robustness diagnostic rather than an equivalence
test.

### 5. PM1, welfare, and literal front-running remain unidentified

The leakage-resistant PM1 holdout is unopened. Owned probes do not reveal user
values, provider costs, task fidelity, cross-user ordering, or provider intent.
The manuscript still cannot identify market-wide welfare loss or literal
front-running, and appropriately says so.

## Required acceptance package

1. Let H81 reach the unchanged 40-per-arm gate and execute its immutable,
   marker-first release exactly once.
2. Lead the paper with the released H81 effect sizes, both uncertainty layers,
   corrected pairwise Fisher tails, Holm adjustment, decomposition, missingness
   bounds, model support, and power boundary.
3. Continue H95 at the frozen hourly cadence to exactly 120 written triplets;
   do not accelerate, pool it with H81, or stop on a favorable sign.
4. Report the primary and position-zero H95 estimators side by side, preserving
   their separate estimands and multiplicity families.
5. Open PM1 only at its fixed 30-completed-date gate and retain the locked
   train/holdout specification.
6. Rewrite the abstract and conclusion around the released causal magnitude,
   while keeping welfare, market share, intent, and literal front-running
   outside the identified set.

## Decision

The score rises from 7.8 to 8.0 because the paper no longer asks the reader to
accept sequential no-interference on faith: it now supplies a lower-precision
randomized estimator that is immune to earlier within-triplet carryover, exact
inference for that estimator, and a stress test showing when the distinction is
material. The recommendation remains borderline / weak reject because this is
still prerelease methodological readiness. A clean H81 release is the shortest
path to an acceptance-level empirical paper.
