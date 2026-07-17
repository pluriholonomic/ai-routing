# Independent-style review, round 24

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7.6/10, weak reject pending the registered H81 release.**

## Summary judgment

This revision closes the main remaining avoidable prerelease mismatch between
the focal H81 theorem and its reported uncertainty. The paper previously paired
a conditional finite-population randomization argument with Newcombe intervals
whose interpretation is binomial and descriptive. It now keeps those intervals
for readability but adds a simultaneous Hoeffding--Serfling confidence set over
the three fixed potential-outcome means, propagates it to both registered
contrasts, and proves conditional coverage under the stopped design.

The revision also replaces marginal Bonferroni power as the only multiplicity
calculation with an exact joint enumeration of the registered two-test Holm
family. Fixed-schedule simulations audit interval implementation, while mixed-
null scenarios verify strong familywise behavior. All specifications were frozen
after an exact-head remote preflight reported H81 counts 32/24/28 at immutable
revision `42334a840dc8088cc8cde441ebe3649cfa041b5e` and
`outcomes_queried=false`.

This is a meaningful methodological improvement, but it is not the missing
empirical result. H81 remains below its unchanged 40-per-arm gate, H95 is only
5/120 triplets, and the PM1 holdout remains unopened. The paper is now unusually
clear about what its randomized design will and will not identify. Acceptance
still depends on releasing the registered experiment without specification
drift and rewriting the empirical narrative around the realized magnitude and
uncertainty.

## Evidence reviewed in this round

- The dated, outcome-blind H81 design-interval amendment at immutable input
  revision `42334a840dc8088cc8cde441ebe3649cfa041b5e`.
- The conditional finite-population interval implementation and appendix proof.
- Five fixed binary potential-outcome schedules, each evaluated over 3,000
  stopped assignments.
- Exact joint-Holm power and mixed-null false-rejection calculations for every
  possible minimum-count terminal-arm identity.
- The updated theorem, release protocol, evidence registry, amendment ledger,
  reproducibility text, and two new figures.
- The full repository test suite: 557 passing tests.
- The rebuilt 37-page PDF, with no undefined citations or references, LaTeX
  errors, overfull boxes, clipped figures, or trailing near-empty page.
- The machine-readable audit: eight manuscript theorems, 15 registered claims,
  and 17 gate events.

## Material improvements

### 1. The confidence claim now matches the randomized design

Conditional on the stopped prefix, terminal policy, and policy counts, each
arm's observed blocks form a simple random sample without replacement from its
fixed potential-outcome schedule. The revision applies the finite-population
Hoeffding--Serfling radius to each policy mean, union-bounds the three means, and
propagates the resulting simultaneous set to the two primary contrasts. The
argument requires only bounded outcomes and valid assignment replay; it does
not silently assume independent Bernoulli outcomes or constant effects.

The Newcombe and Bonferroni--Newcombe intervals remain in the release as
descriptive binomial companions. This dual reporting is appropriate: one layer
is easier to compare to conventional power calculations, while the other states
what the randomization design alone guarantees.

### 2. The revision exposes rather than hides the precision cost

Across five adversarial fixed schedules, the worst marginal Newcombe coverage
is 94.67%, worst Bonferroni--Newcombe two-contrast family coverage is 95.13%,
and worst design-family coverage is 99.93%. The last number is only an
implementation audit; the theorem, not the simulation, supplies the guarantee.

The important substantive fact is width. Mean design-valid contrast width is
about 0.76, compared with roughly 0.29--0.45 for the descriptive intervals in
these schedules. This makes plain that the 40-per-arm experiment can establish
a large randomized wedge but cannot tightly estimate moderate effects without
additional assumptions or more observations.

### 3. Joint multiplicity power is now calculated directly

The exact enumeration applies both pairwise Fisher tests and the registered Holm
step-down rule to every triple of success counts under the stated Bernoulli
planning scenarios. Minimizing over the identity of the terminal arm, the fixed
five-point grid requires a 35-percentage-point component wedge for at least 80%
power in the fallback-only, selection-only, and equal-components cases. In the
mixed-null checks, the largest false-rejection probability for the remaining
true null is 3.23%.

These are planning calculations, not H81 outcomes. They improve the future
interpretation because a null release cannot be described as equivalence, and a
single rejected component cannot be promoted into evidence for the other.

### 4. The amendment remains outcome-blind and operationally auditable

The exact-head preflight pins the paper commit, immutable data revision, arm
counts, and `outcomes_queried=false` state. The amendment changes no treatment,
assignment, stopping rule, estimand, directional hypothesis, multiplicity
family, or outcome coding. Its additions are reporting and validation rules that
apply regardless of sign.

### 5. The figures now separate validity, coverage, precision, and power

The original stopped-design figure tests bias, global-null size, nuisance-arm
size, and marginal planning power. The two new figures separately show
fixed-schedule interval coverage and width, then exact Holm rejection
probabilities. Their captions explicitly label all quantities as outcome-blind
validation or planning calculations.

## Remaining reasons for rejection

### 1. The focal randomized outcome is still unavailable

H81 has 32 delegated-default, 24 no-fallback, and 28 explicit-price-order
blocks. The 40-per-arm gate is closed. The manuscript therefore still has no
realized H81 effect size, confidence interval, exact p-value, missingness
pattern, provider-selection result, or decomposition estimate. A valid release
procedure is not a substitute for the release.

### 2. H81 has narrow support and low precision for moderate effects

The two repeatedly probed models do not support market-wide transport. Even at
the gate, the design-only interval is broad and the exact joint-Holm power
surface is favorable only for large wedges. The eventual paper must report this
limitation next to the result, not only in an appendix.

### 3. H95 remains an early replication scaffold

Five of 120 triplets supply deployment evidence only. The frozen exact
within-triplet analysis, missingness rules, metadata controls, time and model
transport gates, and position diagnostic are credible, but H95 must continue to
its registered horizon and remain separate from H81.

### 4. Welfare and literal front-running remain unidentified

Public quotes and owned one-token probes do not reveal user value, provider
cost, task quality, cross-user request ordering, or whether a provider observed
a specific request before changing a quote. The paper can identify displayed-
price regularities and causal policy effects over owned traffic. It still cannot
estimate market-wide welfare loss or literal front-running.

### 5. The final empirical narrative remains contingent

The abstract and conclusion correctly avoid predicting H81's sign. They require
one final rewrite after release around magnitude, both uncertainty layers,
familywise inference, missingness bounds, support, and power. Null, reversed,
fragile, or imprecise results must remain headline outcomes if realized.

## Required acceptance package

1. Let H81 reach the unchanged 40-per-arm gate and execute the marker-first,
   immutable, one-shot release.
2. Lead with effect magnitudes; report descriptive and design-valid intervals,
   corrected exact pairwise Fisher tails, Holm adjustment, decomposition,
   missingness bounds, deviations, and model support.
3. Preserve a null, reversal, failed audit, or wide identified set without
   changing the registered estimand, gate, or reporting hierarchy.
4. Interpret nonsignificance against the 35-point joint-Holm boundary and broad
   design-only interval; do not claim equivalence.
5. Continue H95 to exactly 120 triplets and report all frozen diagnostics without
   pooling it with H81.
6. Rewrite the abstract and conclusion once around the released H81 result and
   keep welfare, market-share, intent, and literal front-running outside the
   identified set.

## Decision

The score rises from 7.4 to 7.6 because the paper now matches its confidence
claim to the stopped finite-population design, validates the implementation
against fixed schedules, directly computes joint Holm power, and discloses the
large precision cost. I find no remaining avoidable prerelease defect in the
H81 analysis. The recommendation remains weak reject because the central
randomized outcome is still unopened. A clean, sign-agnostic H81 release remains
the shortest path to an acceptance-level empirical paper.
