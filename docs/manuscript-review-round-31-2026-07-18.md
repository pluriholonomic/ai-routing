# Independent-style review, round 31

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **8.8/10, borderline / weak reject pending independent transport
and a formally testable replication.**

## Summary judgment

The manuscript now contains the first marker-bound H81 result rather than a
prospective design. The registered gate opened at 134 intended assignments; the
gate-hitting price-order-fallback block was removed, leaving 133 preterminal
assignments: 45 no fallback, 39 price-order fallback, and 49 delegated default.
All 39 fallback and all 49 delegated assignments succeeded. No fallback has 44
observed binary outcomes and one unknown outcome, with 42 observed successes.
The immutable missing-outcome identified sets are 4.4--6.7 percentage points for
the fallback option, zero for hidden delegated selection, and 4.4--6.7 points for
total delegation.

The release transaction is unusually credible. Workflow `29634812245` pinned
dataset revision `b31f9aa298bfcad020a8751c625c51a7c88fa1ac`, committed marker
`f66fb7fb557305a2fc492653afb97b32a5202ee2` before first outcome access, and
published an immutable bundle whose manifest SHA-256 is
`8150c182d455edc0c97662fcfe141bf369026246358c4415b5a55f49dab9b925`. Every
recorded payload hash validates.

One unknown no-fallback outcome caused the strict complete-data renderer to fail
closed. The authors did not re-query the source or fill the missing value. A dated
post-release recovery reads only the immutable bundle, reports the registered
worst-case sets, leaves the two primary randomization and Holm fields unreleased,
and labels the zero hidden-selection contrast as nonequivalence evidence. The
paper, table, plot, paragraph, and claim ledger all preserve those boundaries.
The full repository suite passes 577 tests, and the rebuilt 43-page PDF is
legible.

This is the paper's most important empirical advance. It shows that, in this
owned-account prefix, explicit price-ordered fallback closes a small but nonzero
realized completion gap, whereas full delegation adds no further realized
success. It does not support a conventional causal rejection because the frozen
primary family is unavailable, and it transports across only two repeatedly
eligible models. I therefore move the paper materially closer to acceptance but
do not yet recommend acceptance at ACM EC or TEAC.

## Evidence reviewed

- Immutable H81 release bundle from workflow `29634812245`.
- Release manifest, first-access marker, summary, arm panel, contrast panel,
  intended-assignment ledger, and renderer-failure record.
- Dated missing-outcome recovery rule and its hash, identity, terminal-exclusion,
  no-partial-Holm, and no-requery validators.
- H81 table, neutral paragraph, identified-set PDF/PNG, and machine-readable audit.
- H95 assignment-only support: 26 of 120 triplets, 78 blocks, ten models, 66
  auditable control rows passing, and 12 legacy-unverified rows.
- Focused 29-test H81 suite and full 577-test repository suite.
- Rebuilt manuscript PDF, including the abstract, result pages, limitations,
  claim ledger, and release provenance.

## What is now strong

### 1. The manuscript has a realized randomized decomposition

The released sample obeys the stopped-prefix design. Assignment integrity passes,
the terminal block is excluded, and the treatment decomposition is algebraically
coherent at both missing-outcome endpoints. The empirical object is no longer a
promise about future data.

### 2. Missingness is handled without analyst-selected imputation

The one unknown outcome is assigned to both binary endpoints. No complete-data
point estimate, Fisher tail, or partial Holm family is reconstructed. This is
more conservative than silently coding an infrastructure failure as a failed
request and preserves the frozen analysis boundary.

### 3. The economic decomposition is interpretable within support

The realized success gain lies entirely in `F-N`; `D-F` is zero. For the two
repeated models and owned account, the relevant hidden-clearing margin is the
option to try additional publicly ordered providers, not an observed incremental
benefit from delegating provider choice. This is a sharper result than a pooled
default-versus-pinned comparison.

### 4. Presentation and provenance are auditable

The main text leads with the realized arm counts and identified sets, labels the
plot correctly, states that the sets are not confidence intervals, and carries
the same boundary into the abstract and conclusion. The recovery artifacts are
deterministically generated from a content-hashed release rather than copied by
hand.

### 5. The welfare and conduct boundaries remain disciplined

The paper does not infer market-wide routed share, provider intent, collusion,
literal front-running, marginal cost, or welfare from the owned probes. The
mechanism results are presented as conditional design benchmarks.

## Remaining reasons for rejection

### 1. The primary causal family has no released decision

The 4.4--6.7 point fallback set excludes zero as a realized estimator set, but it
is not a randomization confidence set. The registered Fisher tails and Holm
decision are suppressed because the binary prefix is incomplete. The manuscript
correctly says “no formal rejection”; that also means the headline randomized
claim remains statistically descriptive.

### 2. Transport is too narrow for the present headline

H81 covers two models at stable adjacent ranks, one account, one minimal prompt,
and roughly 66 hours. This is adequate for a mechanism audit of those blocks, not
for a general statement about AI inference marketplaces. The public panels
broaden institutional context but do not transport the randomized effect.

### 3. H95 is the necessary independent replication and is incomplete

H95 has advanced to 26/120 written triplets across ten models. Its effective
model count is adequate, but six triplets occupy the largest six-hour bin and the
time-concentration gate fails. The first 12 control rows remain legacy-unverified.
No outcome has been queried, correctly, and H95 cannot be pooled with H81. A
clean H95 release is the shortest route to a formally testable, multi-model
claim.

### 4. Market-wide welfare and conduct remain unidentified

The paper has no cross-user allocation, private capacity, provider cost, user
value, or router surplus. The current mechanism model is useful for organizing
future measurement, but the empirical result cannot validate a welfare optimum,
collusion, or front-running.

## Acceptance path

1. Continue H95 at the unchanged preregistered cadence to the first 120 written
   triplets. Do not query outcomes, pool with H81, or stop on model/time balance.
2. Preserve the fixed nuisance-conditioned Fisher family, simultaneous bounded-
   outcome intervals, position-zero sensitivity, whole-triplet leave-one-model-
   out audit, and transport gates.
3. At the immutable H95 horizon, execute its marker-first release exactly once
   and report every primary result regardless of sign.
4. If H95 confirms a positive fallback component with a released familywise
   decision and stable model/time diagnostics, promote the result as evidence
   that fallback is a general clearing margin. If not, retain H81 as a narrow
   owned-account case study and recast the paper around measurement and negative
   transport evidence.
5. Do not revisit or re-query H81. Its current table, figure, paragraph, and claim
   boundary should remain frozen.

## Decision

The score rises from 8.6 to 8.8 because the focal release is real, immutable,
sign-agnostic, and economically interpretable. The result favors fallback over
hidden delegated selection in the realized prefix, while the paper is unusually
clear about missingness and transport. The remaining obstacle is now scientific
rather than operational: H81 has no formal primary decision and only two-model
support. I would recommend acceptance after a clean, independent H95 release
provides a formally testable multi-model result, or after a venue-appropriate
reframing that no longer treats broad randomized evidence as the headline.
