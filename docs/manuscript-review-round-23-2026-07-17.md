# Independent-style review, round 23

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7.4/10, weak reject pending the registered H81 release.**

## Summary judgment

This revision repairs a real prerelease inference defect in the focal H81
experiment. The previous implementation permuted all three randomized policies
when testing each two-policy contrast. That reference law is exact under a
global sharp null, but not under a pairwise null that leaves the third policy's
potential outcomes unrestricted. The amended analysis conditions on the
nuisance-arm assignment and uses the exact two-arm hypergeometric law. It adds a
full proof, adversarial size simulations, a retained fail-closed Monte Carlo
audit, and exact minimum-count power calculations. All changes were made while
H81 outcomes remained unopened.

This is a material improvement. It prevents a potentially invalid confirmatory
p-value from becoming the paper's focal result and clarifies that the original
40-per-arm design is powered for large wedges, not equivalence or small effects.
It does not yet supply the central empirical result. H81 remains below its
unchanged gate, H95 is only 5/120, and the PM1 temporal holdout remains unopened.
The paper is now methodologically more credible but still lacks the released
randomized evidence needed for an empirical EC/TEAC acceptance.

## Evidence reviewed in this round

- The outcome-blind H81 amendment at immutable input revision
  `3efd953a98108381732684508991bab2f5ee28b4`, with 84 verified blocks and arm
  counts 32/24/28.
- The corrected pairwise randomization implementation and exact
  hypergeometric reference law.
- New tests that enumerate the finite assignment support, hold the nuisance arm
  fixed, verify power monotonicity, and retain the 100,000-draw fail-closed
  simulation audit.
- A global-null stopping audit and two nuisance-arm stress tests, each based on
  2,000 stopped experiments.
- Exact Bernoulli-scenario power calculations at the minimum 39-versus-40
  pairwise counts implied by the 40-per-arm gate.
- The updated theorem, appendix proof, claim ledger, release protocol, evidence
  registry, and four-panel validation figure.
- The full repository test suite: 554 passing tests.
- The rebuilt 34-page PDF, with no undefined references, LaTeX errors, overfull
  boxes, clipped figures, or trailing near-empty page.
- The machine-readable audit: eight manuscript theorems, 15 registered claims,
  and 17 gate events.

## Material improvements

### 1. H81's confirmatory tests now match the registered pairwise nulls

For a contrast between policies (a) and (b), the amendment conditions on the
realized membership of the third policy and reassigns only the units in the
focal pair. Conditional on their pooled binary outcomes, the number of
successes assigned to (a) is hypergeometric. The reported two-sided Fisher
tail is therefore exact for the pairwise sharp null even when the nuisance arm
has arbitrary effects. Holm adjustment retains strong familywise error control
because each elementary p-value is valid under its own null.

The proof in the appendix now states this logic directly. This is preferable to
describing a three-arm permutation as pairwise-exact or relying on simulated
randomizations as the published test.

### 2. The repair was triggered by an adversarial test, not by outcomes

Under the global sharp null, the fixed-count stopping simulation rejects 5.05%
of the time, with a Monte Carlo standard error of 0.49 percentage points. More
importantly, under pairwise nulls with a strongly affected nuisance arm, the
corrected tests reject 3.45% and 3.60% of the time. The superseded all-arm law
rejects 5.65% and 6.70%, respectively. The second number shows that the old
implementation could be materially anti-conservative for the claim it was
intended to test.

Because no H81 outcome field had been queried when this was found and amended,
the correction does not create a sign-dependent specification choice. The dated
amendment, immutable revision, counts, and outcome-query state make that timing
auditable.

### 3. The power boundary is now explicit

At 39 versus 40 observations, the exact Bernoulli scenarios require absolute
completion-rate wedges of roughly 22.5--30 percentage points for 80% power
without multiplicity adjustment and 25--35 points with the conservative
Bonferroni threshold, depending on a 25%, 50%, or 75% baseline. These are large
effects. A nonsignificant H81 release will not establish economic equivalence,
absence of selection, or efficient clearing.

This disclosure materially improves the future interpretation. The design can
identify a large decomposition wedge; it cannot sharply exclude moderate
wedge sizes at the original stopping threshold.

### 4. The validation figure now answers four distinct design questions

The four panels separate stopping behavior, global-null size, nuisance-arm size,
and minimum-count power. This is an interpretable theorem-validation figure
rather than a decorative simulation. It also makes the superseded reference law
visibly distinguishable from the production method.

### 5. The prerelease governance remains unusually strong

The release still pins an immutable dataset revision, queries assignments only
while the gate is closed, requires a marker before the first outcome read, and
refuses automatic re-access. The evidence registry now includes the H81
amendment and H95 theorem. The manuscript distinguishes the focal H81 study,
the separate H80 replication, the fixed-horizon H95 replication, observational
enforcement evidence, and future-only H94 events.

## Remaining reasons for rejection

### 1. The focal randomized outcome is still unavailable

H81 has 32 delegated-default, 24 no-fallback, and 28 explicit-price-order blocks.
The 40-per-arm gate is closed. Consequently, the paper still has no H81 effect
magnitude, confidence interval, exact p-value, realized missingness pattern,
provider-selection result, or decomposition estimate. A theorem proving that a
future estimator is valid is not a substitute for its empirical result.

### 2. H81 is a large-effect design over narrow support

Even after release, 40 observations per arm across two repeatedly probed models
will support a finite-sample causal statement over that design, not a broad
equivalence claim about inference markets. The manuscript now states this. An
acceptance case will require leading with magnitude and uncertainty, preserving
wide intervals or a null result, and keeping transport claims narrow.

### 3. H95 remains an early replication scaffold

Five of 120 triplets cannot provide a confirmatory result. Its exact blocked
randomization law, missingness rules, metadata coverage, time-concentration
gate, whole-triplet leave-one-model-out analysis, and position diagnostic are
credible. They become empirical evidence only at the frozen horizon. H95 must
not be pooled with H81 or stopped on a favorable sign.

### 4. Welfare and literal front-running remain unidentified

The public quote panel and owned one-token probes do not identify user value,
provider cost, task quality, cross-user order flow, or whether a provider saw a
particular request before changing a quote. The manuscript can establish
displayed-price regularities, router policy effects over owned traffic, and
bounded mechanism implications. It cannot yet estimate market-wide welfare loss
or literal front-running.

### 5. The final empirical narrative cannot be written before release

The abstract and conclusion appropriately avoid fabricating the H81 sign. They
will need one final rewrite around the realized estimate, exact and familywise
inference, missingness bounds, model support, and power boundary. If the result
is null, reversed, fragile, or imprecise, that must remain the headline.

## Required acceptance package

1. Let H81 reach its unchanged 40-per-arm gate and execute the marker-first,
   immutable, one-shot release.
2. Report effect magnitudes before p-values; include marginal and familywise
   intervals, corrected exact pairwise Fisher tails, Holm adjustment, Monte
   Carlo audit discrepancies, decomposition identity, missingness, treatment-
   deviation bounds, and model support.
3. Preserve a null, reversal, failed audit, or wide identified set without
   changing the registered estimand or gate.
4. Interpret nonsignificance against the disclosed 25--35-point familywise
   power boundary; do not translate it into equivalence.
5. Continue H95 to exactly 120 triplets and report all frozen transport,
   metadata, missingness, position, and leave-one-model-out diagnostics without
   pooling it with H81.
6. Rewrite the abstract and conclusion once around the realized H81 result and
   keep welfare, market-share, intent, and literal front-running claims outside
   the identified set.

## Decision

The score rises from 7.2 to 7.4 because the focal estimator and test are now
matched to the actual elementary hypotheses, the repair was outcome-blind, and
the paper discloses a consequential power limit. I find no remaining avoidable
prerelease defect in the H81 randomization analysis. The recommendation remains
weak reject because the central randomized outcome is still unopened. A clean,
sign-agnostic H81 release is the remaining shortest path to an acceptance-level
empirical paper.
