# Independent-style review, round 16

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7/10, borderline reject.** The paper is now internally
consistent at dataset revision `08a2a183`: the randomized support counts, the
prospective replication launch, and the cross-router cutoff all agree across the
LaTeX, analyzers, registry, and amendment ledger. The revision also demonstrates
an unusually useful red-team property: a prospective-summary bug was found and
repaired before any eligible H94 event existed. The empirical acceptance barrier
is unchanged, however, because neither randomized policy experiment has reached
its frozen outcome gate.

## New evidence and corrections

1. **H81 continues to accrue without outcome access.** There are now 78 verified
   first-position blocks with arm counts 30, 23, and 25. Assignment replay and
   treatment-metadata compliance are 78/78. The minimum arm still needs 17
   assignments, so no completion, fallback, spend, latency, or provider outcome
   is reportable.
2. **H95 is no longer merely operationally launched.** Its first written triplet
   is present in the immutable dataset: three first-position blocks, three
   distinct selected models, perfect plan compliance and replay, ten candidates,
   and nine eligible candidates. This is good transport-design evidence, but one
   of 120 triplets is not an effect estimate.
3. **The acquisition panel is genuinely refreshed.** The pinned endpoint panel
   now contains 3,344,470 rows and 2,116 runs on 11 UTC dates. The one discovery
   cross-router snapshot remains 784 rows; the next successful workflow had not
   yet entered the pinned dataset.
4. **The H94 cutoff audit found a real bug.** Primary quote transitions already
   filtered out the 03:30 discovery cross-section, but elapsed days, snapshot
   counts, and simulated routes were computed from the unfiltered input panel.
   This could have credited discovery support toward prospective gates. A shared
   fail-closed filter now governs every gate and derived frame. Regression tests
   verify that an all-discovery panel contributes zero support and that the first
   future snapshot cannot form a transition against discovery.
5. **No result was contaminated.** The pinned cut contains zero post-activation
   H94 snapshots and zero prospective events. The correction therefore changes
   a support counter from one to zero, not an estimate, sign, or inference.

## Why this is still not an accept

### 1. The title's empirical object remains outcome-gated

The paper is about the fallback option and hidden provider selection, but H81 has
not reached 40 assignments in every arm and H95 has reached only one of 120
triplets. Design validity, blinding, and support accounting cannot substitute for
the treatment-effect table.

### 2. Broad transport is only beginning

H81 still spans two repeated models with no support turnover. H95's first triplet
shows that the broader frontier can produce three distinct models, but the
predeclared transport gates require at least eight audited models, effective
model count five, temporal dispersion, and leave-one-model-out sign stability.

### 3. Public-data claims remain deliberately bounded

The Brown--MacKay association does not identify reactions, named-rival behavior
has a zero lower bound, and H94 has no prospective snapshot. These are credible
falsification results, not substitutes for realized owned-request evidence.

### 4. Confirmatory release execution is still outstanding

When H81 opens, the paper needs a one-shot clean-run release that records the
first outcome access, immutable input revision, code commit, environment lock,
masked-to-released transition, and output hashes. H95 must later receive the same
treatment at its fixed horizon and remain separate from H81.

## Acceptance conditions

1. Release H81 at its unchanged original gate with the preterminal fixed-count
   estimator, both primary contrasts, Holm adjustment, missingness bounds,
   observation rates, and two-model sensitivity.
2. Complete H95's fixed 120-triplet horizon and report every transport gate,
   regardless of whether the effects agree with H81.
3. Preserve H94's corrected future-only filtering and suppress dynamic language
   until all event and support gates pass.
4. Replace the abstract's design-language result sentence with the actual H81
   and H95 estimates after release, including a null or sign disagreement if that
   is what the data show.

## Decision

**Borderline reject pending the frozen randomized outcomes.** The red-team cycle
improved credibility and removed a prospective-support accounting error before it
could affect a claim. The next acceptance-relevant information is not another
specification: it is the sign, magnitude, precision, and transport of the already
registered policy contrasts.
