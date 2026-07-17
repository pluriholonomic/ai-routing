# Independent-style review, round 17

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7/10, borderline reject.** The revision has now satisfied the
previous review's release-governance condition in executable, remotely tested
form. That is a meaningful credibility improvement, but it does not change the
substantive decision: H81 and H95 remain below their frozen gates, so the paper
still has no focal treatment-effect estimate.

## Improvement since round 16

1. **The one-shot release is implemented, not promised.** Commit `7c7c279`
   installs a clean GitHub Actions runner that executes after successful data
   compaction, pins one immutable dataset revision, and checks H81/H95 using
   assignment and plan fields only.
2. **First access is externally ordered.** At an open gate, the job must commit a
   timestamped marker to the private dataset repository before the dedicated
   analyzer can issue a full outcome query. The marker contains the dataset
   revision, code commit, lock hash, analyzer and preregistration hashes, and the
   complete assignment-only gate audit.
3. **The release is idempotent and fail-closed.** A published manifest skips all
   later analyzer calls. A marker without a completed manifest blocks a second
   access and requires forensic recovery from the original retained workflow
   artifact rather than an automatic rerun.
4. **The remote path was exercised.** Run `29556911017` completed from commit
   `7c7c279`, pinned revision `08a2a183`, reproduced H81 counts 30/23/25 and H95
   support 1/120, and recorded `outcomes_queried=false` for both studies.
5. **Red-team tests found and fixed two edge cases.** Empty H81 and H95 support
   tables previously raised while constructing gate audits. Both now return a
   closed gate, preventing a new or temporarily empty dataset from producing an
   ambiguous scheduled-release failure. The focused release and blinding suite
   passes 22 tests.

## Remaining reasons for rejection

### 1. No focal causal result is released

H81 still needs 10, 17, and 15 assignments by arm. H95 still needs 119 written
triplets. Release integrity is now strong, but a design and a release mechanism
cannot replace the sign, magnitude, uncertainty, and missingness bounds of the
actual policy effects.

### 2. Transport remains unresolved

H81 covers two repeatedly eligible models. H95 is the correct prospective
response and its first triplet spans three distinct models, but one triplet
cannot establish effective support, temporal dispersion, or leave-one-model-out
stability.

### 3. The displayed-layer evidence remains descriptive

The cross-router equality fact is still one discovery cross-section; H94 has no
eligible prospective snapshot in the pinned cut. H82 fails pretrends and H84 has
a nonzero backward placebo. The paper appropriately bounds those claims, but
they are not substitutes for realized randomized execution.

## Acceptance conditions

1. Let H81 reach its unchanged 40-per-arm gate and publish the preterminal
   fixed-count bundle through the now-tested clean runner, regardless of sign.
2. Report both H81 primary contrasts, Holm adjustment, missingness bounds,
   observation rates, and model sensitivity in the paper.
3. Complete H95's first 120 plans, publish it separately, and report every
   transport gate even if the result is null or disagrees with H81.
4. Keep H94 dynamic claims suppressed until its prospective event and support
   gates pass.

## Decision

**Borderline reject pending the registered outcomes.** The confirmatory release
path is now acceptance-grade. The remaining barrier is empirical rather than
editorial or operational.
