# Independent-style review, round 27

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **8.2/10, borderline / weak reject pending the registered H81
release.**

## Summary judgment

This revision finds and repairs a consequential remaining defect in H81 before
outcome access. The previous balance gate and primary point sample retained only
first requests whose post-assignment provider-control metadata passed. That rule
produced a clean per-protocol-looking sample on the current data, but the paper's
exact Fisher and finite-population claims require the analyzed labels to remain
a uniform fixed-count randomization. If treatment fidelity depends on assigned
policy or potential outcome, filtering on it can destroy that reference
experiment.

The amended design is explicitly intention-to-treat. Every planned or
seed-replayed intended first assignment enters the gate and its randomized arm.
A future request plan is persisted before the request. Historical eligibility
telemetry replays the run-seed candidate shuffle and block-seed draws, including
eligible blocks with no attempt row; still older recorded blocks replay their
block seed. Missing, duplicate, mismatched, and noncompliant requests stay in the
intended arm. Treatment fidelity is reported by arm and enters a separate
worst-case sensitivity, but never determines assignment eligibility.

The correction is outcome-blind and leaves the current sample unchanged: exact-
head audit `29570676475` recorded H81 at 32/24/28, with all 84 first rows
observed, replayed, and treatment-compliant, and both focal outcome gates closed.
The new adversarial validation nevertheless shows that the distinction is not
semantic. Under an exact sharp null, the ITT estimate remains within 0.0022 of
zero and rejects at 2.83--3.70%, whereas the superseded filtered comparison
reaches bias one and 100% false rejection with the same approximate 50%
retention rate.

This is the strongest prerelease methodological version of the paper so far. I
still cannot recommend acceptance because no focal H81 causal magnitude has
been released, H95 has five of 120 triplets, and the PM1 temporal holdout is
unopened.

## Evidence reviewed in this round

- The dated H81 intended-assignment ITT amendment.
- The prospective privacy-safe plan schema written before each first request.
- Historical eligibility-run RNG reconstruction and its fail-closed integrity
  gate.
- H81 policy panels reporting intended counts, first-row observation, assignment
  replay, and treatment fidelity separately.
- A 15,000-experiment outcome-dependent compliance-selection stress test.
- The three-panel bias, false-rejection, and retained-share figure.
- Updated theorem statement, proof, claim ledger, release protocol, evidence
  registry, and reproducibility history.
- Plan-only, noncompliance, corrupt-plan, legacy-reconstruction, and closed-query
  adversarial tests.
- The full repository suite: 570 passing tests.

## Material improvements

### 1. H81 now tests an estimand actually justified by its randomization

The intended label is fixed before treatment realization. Conditional on the
stopping time, terminal arm, and preterminal intended counts, those labels are a
uniform fixed-count assignment. The observed binary response is therefore the
outcome of assigning the policy code path, including any effect of that code
path failing to realize the requested controls. Arm means are design-unbiased
for finite-population assigned-policy ITT means.

No monotonicity or arm-invariant compliance assumption is needed. If fidelity is
below one, the interpretation narrows to assignment policy; the paper no longer
silently calls the estimate an effect among successfully implemented controls.

### 2. The plan ledger covers prospective and historical request failures

Future plans record the block seed, intended first policy, assignment
probability, model, time, ranking position, and provider-order hash before any
request. They retain no payload or outcome field. For historical runs, the
eligibility table already records enough state to replay the original RNG:
ranked candidates are shuffled from `run_seed`, checked against evaluation
order, and one block seed is consumed for each eligible candidate. This can
recover an assignment even if no attempt row exists.

Explicit plan mismatches, failed historical run replay, and unreconstructable
eligible blocks close the assignment-integrity gate. Additional successful
requests cannot wash out a corrupted ledger.

### 3. The adversary demonstrates severe, not hypothetical, post-treatment bias

The simulation holds direct policy outcomes equal and changes only the
relationship between treatment fidelity, policy, and that fixed outcome. At
selection strength 0.25, the filtered contrast is already biased by 0.250 and
rejects 39.5% of true nulls. At strength 0.5, bias is 0.505 and false rejection
94.2%; at maximum strength both reach one. The ITT analysis stays centered and
conservative throughout.

Panel C is especially useful: mean fidelity remains approximately 50% at every
strength. A balanced retained fraction cannot diagnose selection when the
retained arm--outcome cells differ.

### 4. Missingness and treatment fidelity now have distinct roles

A unique binary outcome from a noncompliant implementation is observed for the
ITT estimand. Unknown, malformed, absent, or duplicate outcomes remain
measurement missing and suppress complete-data inference. A secondary fidelity
sensitivity treats noncompliant implementations as untrusted in `[0,1]`. It is
not described as a complier or per-protocol effect.

### 5. The amendment is transparent about changing the original analysis rule

This correction changes the original compliant-request sample definition and
therefore is not disguised as a cosmetic implementation detail. It is dated,
hashed into the release manifest, motivated by a concrete invalidity, frozen
with outcomes inaccessible, and sign-invariant. Because current fidelity is
100%, it changes no current count or hidden empirical contrast.

## Remaining reasons for rejection

### 1. The focal randomized outcome still does not exist

H81 remains at 32 delegated-default, 24 no-fallback, and 28 explicit-price-order
intended assignments. There is no released effect, confidence set, Fisher
p-value, decomposition, selected-provider result, or missingness realization.
Design correctness is necessary but is not an empirical contribution by itself.

### 2. H81 transport and precision remain narrow

The original study covers two repeatedly eligible models. The design-valid
contrast interval is about 0.76 wide in fixed schedules, and worst-terminal-arm
80% Holm power requires a 35-point component effect on the frozen grid. A null
result will not establish practical equivalence.

### 3. The amendment history is now substantial

The prerelease red team has corrected terminal-block inclusion, global-versus-
pairwise Fisher laws, confidence-set interpretation, and compliance filtering.
All corrections were outcome-blind, which is a strength, but the manuscript
must present one final coherent design rather than narrating every correction in
the main text. The full genealogy belongs in the appendix and release ledger.

### 4. Prospective plan persistence still needs remote deployment evidence

The code and tests show that the plan write precedes the request and that
compaction discovers new curated tables automatically. Acceptance packaging
should include a successful remote collector artifact and subsequent immutable
dataset revision containing `router_decomposition_plans`, followed by an
assignment-only audit showing plan coverage and replay. This is an operational
gate, not permission to inspect outcomes.

### 5. H95, PM1, welfare, and conduct remain incomplete

H95 is 5/120 and fails its current time-concentration gate. PM1's 30-date holdout
is unopened. Owned probes do not identify cross-user ordering, provider intent,
private cost, or market-wide welfare. Literal front-running and welfare loss
must remain outside the identified set.

## Required acceptance package

1. Deploy the H81 plan-first collector remotely and verify one compacted plan
   row plus exact plan replay without querying outcomes.
2. Let H81 reach its unchanged 40 intended assignments per arm and execute the
   immutable marker-first release exactly once.
3. Lead with released ITT effect sizes, both uncertainty layers, pairwise Fisher
   tails, Holm adjustment, treatment-fidelity rates, measurement-missing bounds,
   and the two-model transport boundary.
4. If fidelity is imperfect, use assigned-policy language and show the fidelity
   sensitivity; do not substitute a per-protocol point estimate.
5. Continue H95 at the frozen hourly cadence to 120 triplets, preserving its
   primary and position-zero estimands and separate multiplicity families.
6. Open PM1 only at its fixed 30-completed-date gate.
7. Compress the main-text amendment history after H81 release and keep the full
   audit genealogy in the appendix.

## Decision

The score rises from 8.0 to 8.2 because H81's primary estimator and exact test
now use a reference experiment preserved against treatment-realization failure,
the historical ledger can recover requestless eligible blocks, and the
adversarial simulation demonstrates a very large error avoided by the change.
The recommendation remains borderline / weak reject because the paper still
lacks the focal randomized outcome. A clean H81 release remains the shortest
path to acceptance.
