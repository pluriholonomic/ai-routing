# Independent-style review, round 25

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7.8/10, weak reject pending the registered H81 release.**

## Summary judgment

This revision catches and repairs a second consequential prerelease inference
problem, this time in the independent H95 replication. The previous H95
implementation permuted all three policies within each triplet. That law is exact
under the global three-policy sharp null, but the registered family contains two
elementary pairwise nulls, each of which permits the nuisance third policy to
have arbitrary effects. The amended test conditions on the model assigned the
nuisance policy and swaps only the two focal labels. This produces a valid
pairwise Fisher p-value for each elementary null and restores the premise needed
for Holm's strong familywise guarantee.

The amendment also adds a simultaneous bounded-outcome confidence set that
matches the fixed-horizon randomized design. The existing paired-t intervals are
retained as descriptive superpopulation companions, but are no longer the only
uncertainty statement. Fixed-schedule simulations expose both the statistical
importance of the reference-law correction and the precision cost of relying on
the design alone. These changes were frozen after exact-head remote audit
`29568434722` reported five of 120 H95 triplets and
`outcomes_queried=false` at immutable revision
`30b430e2a095d069015f45dbf9b3fca9a4f7e1ce`.

The paper's prerelease methods are now substantially stronger. The central
empirical limitation is unchanged: H81 has not reached 40 assignments per arm,
H95 has only five triplets, and the PM1 temporal holdout remains unopened. I do
not recommend acceptance for an empirical EC/TEAC paper whose focal randomized
effect is still unavailable. I also find no remaining obvious prerelease defect
in either H81 or H95's stated randomization law.

## Evidence reviewed in this round

- The dated H95 pairwise-reference-law and design-interval amendment.
- The production nuisance-conditioned convolution and matching Monte Carlo
  discrepancy audit.
- Two 5,000-experiment mixed-null stress tests with an active nuisance policy.
- Five fixed binary potential-outcome schedules with 5,000 assignments each.
- The blocked-design confidence theorem and full appendix proof.
- The updated release protocol, evidence registry, amendment ledger, claim
  table, and reproducibility history.
- The new four-panel H95 validation figure.
- The full repository suite: 561 passing tests.
- The rebuilt 38-page PDF, with no undefined references or citations, LaTeX
  errors, overfull boxes, clipped figures, or trailing near-empty page.

## Material improvements

### 1. H95's p-values now test the hypotheses the paper actually registers

For a pair of focal policies, conditioning on the nuisance-policy assignment
leaves a fair swap of the two focal labels within each triplet. Under the
pairwise sharp null, the two focal outcomes are fixed, so the local contrast law
places one-half mass on the observed difference and one-half on its negative.
Independence across triplets makes the convolution exact.

This is not a cosmetic reformulation. It permits the nuisance policy to affect
outcomes, which the elementary null is supposed to allow. The superseded
six-assignment law implicitly imposed equality across all three policies and
could not support strong familywise interpretation of the two Holm-adjusted
tests.

### 2. The adversarial audit demonstrates material rather than hypothetical size distortion

The two mixed-null schedules hold one focal pair exactly at its sharp null and
give the nuisance policy a large heterogeneous effect. Worst elementary
true-null rejection is 4.06% under the corrected law and 8.12% under the
superseded law. The corresponding false rejection of the remaining true null
after Holm is also 4.06% versus 8.12% in these schedules.

The simulation is not the proof of validity; the conditional randomization
argument is. Its value is to demonstrate that the implementation choice can
change the paper's error rate by an economically meaningful amount.

### 3. H95 now reports uncertainty justified by the design itself

Each observed triplet contrast lies in `[-1,1]`, is unbiased for its fixed
triplet-average contrast, and is independent across written triplets. A
Hoeffding bound plus a union bound therefore gives simultaneous 95% coverage for
the two primary finite-population contrasts. At 120 triplets the radius is
0.27025 per contrast.

Across the five fixed schedules, worst observed design-family coverage is
99.90% and mean width is 0.540. The descriptive Bonferroni paired-t family has
worst coverage 95.52% and mean width 0.290. Reporting both layers is the correct
choice: the paired-t intervals are more familiar and narrower, while the
Hoeffding intervals state what boundedness and randomization alone guarantee.

### 4. The paper discloses the precision cost in the main limitations

The design-valid radius is now stated next to H95's prospective support claim.
This prevents the broader multi-model replication from being mistaken for a
high-precision equivalence design. Even at 120 triplets, moderate component
effects may remain unresolved without a superpopulation interpretation.

### 5. The correction remains outcome-blind and sign-invariant

The exact-head audit pins the paper commit, immutable input, support counts, and
closed outcome gate. The amendment changes no treatment, candidate frontier,
assignment probability, fixed horizon, estimand, directional hypothesis,
missingness rule, or multiplicity family. The corrected test and both interval
layers apply regardless of the realized sign.

## Remaining reasons for rejection

### 1. H81 still lacks its focal randomized outcome

H81 remains at 32 delegated-default, 24 no-fallback, and 28 explicit-price-order
blocks. There is no released effect magnitude, confidence interval, exact
p-value, decomposition estimate, missingness pattern, or provider-selection
result. Methodological readiness cannot replace the empirical result.

### 2. H81's two-model support remains narrow

The original randomized statement will be causally interpretable over its
realized design but not broadly transportable to the inference market. Its
design-valid interval is wide and its joint-Holm power is favorable only for
large component wedges.

### 3. H95 is still a deployment scaffold rather than a replication result

Five of 120 triplets establish prospective operation only. The current support
has nine models and good effective count, but fails the registered six-hour
concentration gate because three of five triplets fall in one bin. That failure
should naturally disappear with continued hourly accrual, but it cannot be
assumed. The fixed horizon must remain unchanged.

### 4. Sequential cross-model interference remains an assumption

Randomized policy and position absorb position-only drift, but a policy applied
to an earlier model block could in principle affect a later block. The
position-by-policy panel and position-zero sensitivity are useful diagnostics,
not proofs of no interference. Direct-policy language must remain conditional
on this assumption.

### 5. Welfare and literal front-running remain unidentified

Owned probes reveal the selected provider and completion behavior for one
account. They do not reveal user values, provider costs, task fidelity,
cross-user request ordering, or whether a provider observed a particular request
before repricing. The market-design interpretation remains appropriate, but
market-wide welfare loss and literal front-running remain outside the identified
set.

## Required acceptance package

1. Let H81 reach its unchanged 40-per-arm gate and execute the immutable,
   marker-first release exactly once.
2. Lead with realized effect magnitudes and both uncertainty layers; report the
   corrected pairwise Fisher tails, Holm adjustment, decomposition, missingness
   and treatment bounds, model support, and power boundary.
3. Preserve a null, reversal, wide confidence set, failed audit, or incomplete
   outcome without changing the estimand or reporting hierarchy.
4. Continue H95 at the frozen hourly cadence to exactly 120 written triplets;
   do not accelerate it with extra manual probes, pool it with H81, or stop on a
   favorable sign.
5. Report H95's conditional pairwise tests, design and paired-t intervals,
   metadata coverage, time concentration, whole-triplet leave-one-model-out,
   position diagnostic, and missingness bounds exactly as frozen.
6. Open PM1 only at its fixed 30-completed-date gate and preserve its locked
   train/holdout specification.
7. Rewrite the abstract and conclusion once around the released H81 result,
   keeping welfare, market share, intent, and literal front-running outside the
   identified set.

## Decision

The score rises from 7.6 to 7.8 because the H95 elementary tests now match their
registered nulls, the amendment demonstrates and repairs an 8.12% mixed-null
false-rejection problem, and the confidence claim now matches the fixed-horizon
randomization design. This is the second instance in which outcome-blind red
teaming prevented an invalid confirmatory interpretation before release. The
recommendation remains weak reject because the manuscript still lacks its focal
randomized empirical result. A clean H81 release remains the shortest path to an
acceptance-level paper.
