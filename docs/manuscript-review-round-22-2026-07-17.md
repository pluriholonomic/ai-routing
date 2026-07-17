# Independent-style review, round 22

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7.2/10, weak reject pending the registered H81 release.**

## Summary judgment

The revision materially improves the independent-replication design rather than
adding another observational result. H95 now has a finite-population theorem and
proof matched to its blocked assignment, exact rather than simulated Fisher
tails, explicit structural and measurement missingness, row-level treatment-
control coverage, registered transport diagnostics, and a release manifest that
hashes dated protocol amendments. The manuscript also identifies a sequential-
block interference assumption that the earlier version left implicit.

These changes make the prospective H95 release auditable. They do not change the
decision. The title contribution is still the H81 clearing decomposition, and
H81 remains outcome-blind below its original gate. The paper has an unusually
strong protocol and identification package but not yet the focal empirical
result required for an EC/TEAC empirical acceptance.

## Evidence reviewed in this round

- Commit `f170d89`, pushed while H95 remained 4/120 and before any H95 outcome
  query.
- Scheduled workflow `29564165459`, which checked out `f170d89` and completed
  successfully; its artifact was not yet compacted, so it is deployment evidence
  rather than a fifth counted triplet.
- The dated H95 amendment, clean release protocol, evidence ledger, and theorem-
  validation matrix.
- The H95 exact-convolution implementation, collector metadata additions,
  position-by-policy diagnostic, whole-triplet leave-one-model-out code, and
  adversarial tests.
- The full 551-test repository suite and focused lint/format checks.
- Outcome-blind preflight at dataset revision `4fd167d674f6b227b766df00505fe02da1325e63`:
  four valid triplets, 12 recorded first requests, perfect plan compliance and
  replay, zero missing first records, 12 legacy-unverified treatment-metadata
  rows, and no outcome query.
- The rebuilt 33-page PDF. The H95 main-text discussion, proposition, proof,
  claim ledger, and reproducibility pages render without clipping, undefined
  references, or overfull boxes.

## Material improvements

### 1. H95 now has a theorem that matches its actual assignment

Conditional on the first 120 valid triplets and realized model support, each
policy is assigned once per triplet by a uniform bijection. Under consistency
and no treatment-dependent cross-model interference, the observed one-per-
triplet arm mean is design-unbiased for the finite-population policy mean. The
fallback and hidden-selection contrasts are therefore unbiased over realized
support, and their accounting sum equals total delegation pathwise.

Under the Fisher sharp null, each triplet contributes a six-assignment local
contrast law supported on `{-1,0,1}`. Independence across triplet assignments
makes the full reference law their convolution. This is a clean, finite exact
test and is more appropriate than calling 100,000 simulated permutations the
published result.

### 2. The implementation is independently checkable and fail-closed

A two-triplet fixture enumerates all 36 joint assignments and agrees with the
convolution. Exact mass must equal one within `1e-12`. The retained 100,000-draw
audit stops release when any tail differs by more than 0.01. A deliberately
corrupted simulated audit triggers that guard. This is strong engineering for a
one-shot confirmatory release.

### 3. Missingness and treatment deviations are no longer conflated

The original structural intent-to-treat rule remains intact: an absent planned
request or noncompliant first policy is zero. Duplicate primary telemetry and an
auditable provider-control mismatch are also structural zeros. A compliant
record with an `unknown` or malformed outcome is instead measurement missing;
it suppresses complete-data point and randomization inference and enters
`[0,1]` bounds. The distinction is statistically and economically meaningful.

### 4. The legacy telemetry gap is disclosed rather than backfilled

The first four triplets lack the newly added requested-order and provider-only
lengths. They remain in the fixed horizon as 12 legacy-unverified rows. Future
rows record the full provider-control contract, and the release reports coverage,
pass rates among auditable rows, and sensitivity to unverified rows. This is the
right response to a pre-outcome instrumentation improvement; silently certifying
or dropping the early rows would be worse.

### 5. The transport gates now exist in code

Six-hour concentration is computed from distinct triplets, not three replicated
block rows. Leave-one-model-out drops every triplet containing the model, thereby
preserving the randomized three-policy block. The current 4/120 sample already
passes model-count, effective-count, and dominance screens but fails the time
gate because three triplets lie in one six-hour bin. The paper correctly treats
this as early-accrual support, not an effect or a permanent failure.

### 6. The sequential-interference limitation is now explicit

The three model blocks in an H95 triplet execute sequentially. Random assignment
across models and positions handles position-only drift, but a direct-policy
interpretation requires that an earlier model's treatment not change a later
model's outcome. The new position-by-policy panel and position-zero cells are
useful diagnostics. They cannot prove the assumption. Stating this makes the
paper stronger and prevents H95 from being oversold as automatic transport.

## Remaining reasons for rejection

### 1. H81 still has no released outcome

The authoritative counts remain 32 delegated-default, 23 no-fallback, and 27
explicit-price-order-with-fallback assignments. The 40-per-arm gate is closed.
There is still no focal effect magnitude, interval, exact p-value, realized
missingness pattern, or provider-selection result. The paper cannot be accepted
for its proposed central empirical contribution before this object exists.

### 2. H95 is not a substitute for H81 and is only 4/120

H95 cannot be pooled with H81, stopped when its sign looks favorable, or used to
retroactively broaden H81. Its exact inference currently validates code only.
At release, the 12 legacy-unverified rows must remain visible, and a failed
metadata, transport, or position diagnostic must narrow the claim regardless of
the estimated sign.

### 3. Direct-effect language for H95 is assumption-sensitive

Randomization protects against fixed position effects, not arbitrary exposure
mapping across sequential blocks. If completion differs sharply by position or
the position-zero diagnostic conflicts with the full blocked estimate, the paper
should describe H95 as an effect of the randomized execution schedule over the
observed sequence, not a clean model-block direct effect. The current theorem
states the needed assumption correctly; the future results section must enforce
it.

### 4. Fisher tests and paired-t intervals answer different questions

The exact p-values test a Fisher sharp null. The paired-t intervals are
descriptive across realized triplets and the Bonferroni versions provide the
reported familywise companion. Neither is an exact randomization interval for a
heterogeneous finite-population average effect. The release should lead with
effect magnitude and bounds, then explain these inferential objects separately.

### 5. Broader market and welfare claims remain unidentified

Owned one-token probes do not measure market-wide routed share, user value,
provider cost, task fidelity, cross-user ordering, or literal front-running.
The H95 theorem strengthens a policy-effect design; it does not identify welfare
or collusion. The manuscript currently respects this boundary and must keep it
after a potentially large randomized result.

## Required acceptance package

1. Let H81 reach its unchanged 40-per-arm gate and execute the marker-first,
   immutable one-shot release.
2. Report the frozen preterminal effect magnitudes, marginal and familywise
   intervals, exact Fisher tails, Holm family, Monte Carlo discrepancy audit,
   decomposition identity, missingness and treatment bounds, and model support
   regardless of sign.
3. Preserve a null, sign reversal, failed audit, or wide identified set as the
   central result if that is what the release produces.
4. Continue H95 to exactly 120 plans. At its release, report treatment-metadata
   coverage, the 12-row legacy sensitivity, time concentration, whole-triplet
   leave-one-model-out, and position-by-policy diagnostics. Do not pool H95 with
   H81.
5. If H95 shows cross-position instability, narrow its interpretation to the
   randomized sequential execution schedule or add a separately preregistered
   noninterfering replication; do not repair the current horizon after viewing
   outcomes.
6. Rewrite the abstract and conclusion around the realized H81 sign, magnitude,
   uncertainty, and finite-support boundary. Newer public-data vintages still
   require the completed-day provenance audit before promotion.

## Decision

The paper's design, proof, prerelease governance, and claim discipline are now
strong enough that I find no additional avoidable methodological defect in H81
or H95. The score rises from 7.1 to 7.2 because H95 is now a credible independent
replication design and because the manuscript exposes rather than conceals its
interference assumption. The recommendation remains weak reject solely because
the central randomized evidence is unopened. A clean H81 release, reported
without sign-dependent revision, remains the shortest path to an accept.
