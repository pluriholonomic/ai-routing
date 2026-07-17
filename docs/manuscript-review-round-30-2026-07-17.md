# Independent-style review, round 30

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **8.6/10, borderline / weak reject pending the registered H81
outcome release.**

## Summary judgment

This revision closes a narrow but consequential failure mode in the one-time
H81 release. The irreversible first-outcome-access marker necessarily precedes
the analyzer. The strict paper-facing renderer also ran inside that analyzer,
so a missing outcome, algebraic validation error, or plotting failure could
strand the first result after the marker but before immutable publication. The
new wrapper leaves every presentation invariant unchanged and still prohibits
paper promotion, but preserves the already-written raw analysis bundle and
forbids a second outcome query.

The correction was made while the gate remained closed. Commit `d4d2b19` passes
a planted decomposition-identity failure, the 26-test focused release suite,
and the full 574-test repository suite. Exact-head workflow `29575626677`
checked out that commit, pinned immutable revision `df74e296828b`, reproduced
H81 counts 34/31/29 and H95 support 7/120, and reported
`outcomes_queried=false` for both studies. Its artifact contains only release
status and assignment-only gates.

This improves the credibility of the eventual release but does not create the
missing empirical result. H81 still lacks a realized fallback effect, hidden-
selection effect, simultaneous design interval, and registered Holm decision.
I therefore remain below acceptance.

## What is now strong

1. **The estimand matches the assignment design.** The primary comparison is
   finite-prefix assigned-policy ITT, with no post-assignment compliance filter.
2. **The stopped design has a valid reference experiment.** The gate-hitting
   terminal block is removed and inference conditions on preterminal arm counts.
3. **The primary tests match the pairwise nulls.** Nuisance-arm assignment is
   fixed, exact hypergeometric tails replace the invalid global permutation,
   and the two directional tests receive Holm adjustment.
4. **Uncertainty and missingness are explicit.** The release includes
   simultaneous finite-population intervals, descriptive intervals, binary-
   outcome bounds, and treatment/outcome sensitivity bounds.
5. **The presentation is sign-agnostic and transaction-safe.** The table,
   forest plot, neutral paragraph, and algebra validator were frozen before
   outcomes. A renderer failure cannot be promoted and can no longer destroy
   the only automatically accessible raw result.
6. **Remote provenance is exact.** The deployed commit and immutable dataset
   revision are linked by an outcome-free workflow artifact rather than a local
   timestamp or retrospective assertion.

## Remaining reasons for rejection

### 1. The focal randomized outcome is absent

No amount of release governance substitutes for the actual H81 estimate. The
current paper establishes a careful design and an informative market taxonomy,
but its central empirical clearing claim remains prospective.

### 2. Precision is adequate only for large wedges

At the minimum gate, worst-terminal-policy 80% Holm power requires roughly a
35-percentage-point component effect on the frozen planning grid. A null result
will be imprecise, not evidence of equivalence.

### 3. Transport remains narrow

H81 contains two repeatedly eligible models with no support turnover. H95 is a
proper independent transport design, but it remains 7/120 triplets and fails
the six-hour concentration gate. Its outcome cannot be pooled with H81.

### 4. Welfare and conduct remain unobserved

The study does not identify provider marginal cost, router surplus, user value,
market-wide allocation, collusion, or literal front-running. The manuscript is
appropriately explicit about these boundaries.

## Acceptance path

1. Continue the unchanged hourly H81 cadence until every intended arm reaches
   40; do not burst-accelerate or stop on a favorable assignment sequence.
2. Execute the marker-first release once at the first qualifying immutable
   revision.
3. Publish the frozen table, figure, neutral paragraph, raw tables, summary,
   code hashes, and release manifest regardless of sign.
4. Report both primary directional estimates, exact and Holm p-values,
   simultaneous design intervals, fidelity, and missingness. Treat
   nonsignificance as imprecision.
5. Update the abstract and conclusion once, preserving the owned-account,
   finite-prefix, two-model boundary.
6. Continue H95 independently to its written horizon.

## Decision

The score rises from 8.5 to 8.6 because the first-access transaction now
preserves the only result it is permitted to read, even when the presentation
layer correctly fails closed. The remaining rejection reason is unchanged and
substantive: the focal randomized outcome has not yet been released. A clean,
sign-agnostic H81 release is still the shortest path to acceptance.
