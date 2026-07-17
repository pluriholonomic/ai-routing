# H81 pairwise Fisher correction and pre-outcome power audit

Status: written on 2026-07-17 while the original 40-per-arm release gate was
closed. The assignment-only audit at immutable dataset revision
`3efd953a98108381732684508991bab2f5ee28b4` reported counts 32/24/28 and
`outcomes_queried=false`. This amendment was motivated by a proof and
implementation audit, not by an H81 outcome estimate. The treatments, estimands,
assignment, eligible support, earliest-balanced-prefix rule, release threshold,
directional hypotheses, and two-test Holm family are unchanged.

## Problem found

After removing the gate-hitting block, the first `T-1` labels are a uniform
three-arm fixed-count randomization. The previous exact Fisher implementation
tested a two-policy contrast by permuting all three labels and summing the
multivariate-hypergeometric distribution of all three arm-success counts. That
reference law is exact for the global sharp null that all three policies have
the same outcome on every block. It is not generally exact for either registered
pairwise null when the untested third policy has an arbitrary effect.

For example, the fallback null concerns `price_order_fallback` versus
`price_only_no_fallback`; it does not assert that `delegated_default` has the
same potential outcome. Permuting delegated outcomes into the two focal arms
therefore imposes a stronger, unregistered nuisance-arm null and can distort
size.

## Corrected reference experiment

For each registered contrast, condition on:

1. the stopping time, terminal policy, and preterminal arm counts;
2. the realized set of blocks assigned to the nuisance third policy; and
3. the combined binary outcomes in the two contrasted arms.

Conditional on the nuisance-arm set, the two focal labels are uniformly
distributed over all assignments with their observed counts. If their counts
are `n_a,n_b`, their combined success count is `K_ab`, and `X_a` is the number
of successes assigned to policy `a`, then under the pairwise Fisher sharp null

`Pr(X_a=x | K_ab,n_a,n_b,Z_c) = C(n_a,x) C(n_b,K_ab-x) / C(n_a+n_b,K_ab)`.

The analyzer sums this finite two-arm hypergeometric support exactly for
one-sided and absolute tails. Its 100,000-draw audit now permutes only the two
contrasted labels and holds the nuisance assignment fixed. A discrepancy above
one percentage point still fails closed. Holm adjustment across the two
registered directional p-values remains valid without a dependence assumption
because each marginal p-value is valid under its own pairwise null.

## Adversarial validation

The audit adds 2,000 stopped experiments for each primary contrast. In each
experiment the two focal policies share exactly the same fixed binary potential-
outcome path, while the untested policy has a large, time-varying effect. The
corrected pairwise test rejects at 3.45% for the fallback null and 3.60% for the
selection null. The superseded all-arm law rejects at 5.65% and 6.70%,
respectively. The corrected rates are conservatively below 5% because the exact
binary support is discrete. A four-block 2/2 pair fixture also agrees with all
six unique pairwise assignments to machine precision.

## Pre-outcome power boundary

The audit additionally enumerates exact Bernoulli scenario power at the
conservative minimum preterminal pair counts 39 and 40. This is a model-based
planning calculation, not an empirical H81 result. Across negative-arm baseline
success probabilities 25%, 50%, and 75%, the smallest 2.5-percentage-point-grid
effect reaching 80% power is 30, 30, and 22.5 percentage points at an
unadjusted 5% threshold. At the Bonferroni 2.5% threshold, which lower-bounds
the marginal power of the two-test Holm procedure, the corresponding effects
are 35, 32.5, and 25 percentage points.

Accordingly, H81 is capable of detecting large policy wedges but is not powered
to rule out economically relevant modest effects. A nonsignificant H81 result
must be reported with its confidence interval and cannot be interpreted as
evidence of equivalence. The separately frozen 120-triplet H95 replication is
the precision and transport extension; it is never pooled with H81.
