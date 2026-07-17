# H95 prerelease inference and telemetry amendment

Date: 2026-07-17 UTC

Implementation commit: `f170d89`

Outcome state: fixed 120-triplet gate closed; no H95 outcome field queried.

This amendment was written after four prospectively planned triplets had been
collected but before the first confirmatory outcome access. It does not change
the candidate population, randomization, treatments, two primary estimands,
fixed 120-triplet horizon, multiplicity family, or rule that H95 is never pooled
with H81. It resolves ambiguities and implementation gaps found in a prerelease
red-team audit.

## Exact randomization inference

The original protocol required at least 100,000 within-triplet permutations.
The release now computes the Fisher sharp-null tails exactly. For each triplet,
the three fixed binary unit outcomes admit six equiprobable policy assignments.
For each contrast, the analyzer forms the local distribution on `{-1, 0, 1}`
and convolves those distributions across the 120 independent triplets. The
one-sided tail is the probability of a contrast sum at least as large as the
observed sum; the two-sided tail uses absolute sums.

The prespecified 100,000-draw permutation remains as an implementation audit,
not the published p-value. Exact support mass must equal one within `1e-12`, and
the release fails closed if any exact-versus-simulated tail discrepancy exceeds
0.01. A two-triplet fixture agrees with brute-force enumeration of all 36 joint
assignments.

## Outcome and protocol-deviation coding

The original intent-to-treat rule is unchanged for structural failures:

- a missing planned first request is zero;
- an observed first policy different from its planned assignment is zero;
- a duplicate first-request record is zero; and
- an auditable provider-control record inconsistent with its policy is zero.

A recorded, structurally compliant outcome is binary only when its normalized
value is `succeeded`, `failed`, or `cancelled`. `Unknown`, missing, or malformed
recorded outcomes are measurement missing, not failures. Any such value
suppresses the complete-data point estimates, paired intervals, and
randomization tests and enters arm-level `[0,1]` bounds. The release separately
reports sensitivity bounds that relax the original missing-request-as-zero rule.
No row, model, or triplet is excluded based on an outcome.

## Treatment metadata

Future collector rows record `requested_order_length`, `provider_only_count`,
`public_provider_count`, and `allow_fallbacks`. Together these fields verify the
actual provider controls for each policy. The first four triplets predate the
two order-length fields. Their 12 first-position rows remain in the fixed
horizon and are labeled `legacy_treatment_metadata_unverified`; they are neither
silently passed nor discarded. The release reports row-level audit coverage,
pass rates among auditable rows, and treatment-verification sensitivity bounds.

The outcome-blind preflight at dataset revision
`4fd167d674f6b227b766df00505fe02da1325e63` found four valid triplets, 12
recorded first requests, perfect plan compliance and assignment replay, zero
missing first records, and 0/12 rows with the newly added order-length fields.

Post-deployment assignment-only audit `29565268475` pinned revision
`3efd953a98108381732684508991bab2f5ee28b4` after the first hardened collector
run. The fixed horizon advanced to 5/120 with 15/15 first records, perfect replay
and plan compliance, the same 12 legacy rows, and 3/3 newly auditable rows
passing. Metadata coverage therefore rose to 20% exactly as intended; no outcome
field was queried.

## Descriptive uncertainty and transport

The paired normal intervals named in the original protocol are replaced by
paired Student-t intervals over realized triplets. The two primary contrasts
also receive Bonferroni 95% familywise paired-t intervals. These are descriptive
superpopulation-triplet intervals, not inverted randomization confidence sets.
Wilson arm intervals remain descriptive and are suppressed under measurement
missingness.

The analyzer now implements every registered transport diagnostic. Six-hour
concentration is computed from distinct planned triplets, not their three block
rows. Leave-one-model-out estimates drop every triplet containing the omitted
model so the randomized three-policy block remains intact. Broad multi-model
language requires all structural support gates and sign stability for both
primary contrasts. Open-source language remains unavailable without the
separate license/model-card audit required by the original protocol.

The three model blocks in a triplet are executed sequentially. Random assignment
of policy to model and triplet position protects against position-only drift,
but a direct-policy interpretation additionally assumes that the treatment used
for an earlier model does not change the later model's outcome. The release now
writes a position-by-policy panel; its position-zero cells have no earlier H95
model block in the same triplet and provide a diagnostic for this cross-model
interference risk. The diagnostic does not prove the no-interference assumption,
and a broad claim must state this boundary.

## Released artifacts and verification

In addition to the assignment, arm, model, contrast, and summary outputs, the
release writes a row-level redacted primary-outcome audit, a whole-triplet
leave-one-model-out panel, and a triplet-position-by-policy panel. Adversarial
tests cover unknown outcomes, missing and
noncompliant first requests, corrupted provider controls, exact enumeration,
the production Monte Carlo discrepancy guard, time concentration, and transport
stability. The full repository suite after this amendment reports 551 passes.
