# H95 pairwise reference law and design-interval amendment

Status: outcome-blind amendment written on 2026-07-17 after exact-paper-head
remote audit `29568434722` checked commit `973f900` against immutable dataset
revision `30b430e2a095d069015f45dbf9b3fca9a4f7e1ce`. The audit reported five of
120 prospectively written H95 triplets, 15 first-position assignments, perfect
assignment replay and plan compliance, and `outcomes_queried=false`.

This amendment changes no treatment, candidate frontier, triplet construction,
assignment probability, fixed 120-triplet horizon, estimand, directional
hypothesis, Holm family, missingness rule, or rule that H95 is never pooled with
H81. It corrects the reference experiment for each elementary pairwise null and
adds a bounded-outcome interval justified by the randomized design.

## Pairwise conditional Fisher law

The earlier prerelease analyzer permuted all three policy labels within every
triplet. That six-assignment law is exact under the global sharp null that all
three policies have identical potential outcomes. It is not generally exact for
an elementary pairwise null when the nuisance third policy has an effect. Holm's
strong familywise guarantee requires a valid p-value for each elementary null,
so the six-assignment law is superseded for confirmatory testing.

For a contrast between policies `p` and `q`, condition in each triplet on the
model block assigned the nuisance policy `r`. Under the pairwise sharp null
`Y_jm(p)=Y_jm(q)` for every model block, the two remaining observed outcomes are
fixed and the focal labels are a fair swap. If their observed difference is
`d_j`, the exact local law is

```text
G_j,pq = 0.5 delta(d_j) + 0.5 delta(-d_j).
```

Independent assignment across written triplets makes the exact law of the
unnormalized contrast the convolution of these two-point laws. The release uses
its upper tail for each registered directional hypothesis and then applies the
unchanged two-test Holm step-down rule. The global six-assignment law remains
available only as a superseded adversarial comparison.

## Design-valid simultaneous interval

For triplet `j`, let `D_j,pq` be its observed policy-`p` outcome minus its
observed policy-`q` outcome. Conditional on the first `J=120` written plans and
their sampled models,

```text
D_j,pq in [-1,1]
E[D_j,pq] = (1/3) sum_m (Y_jm(p) - Y_jm(q)).
```

Assignments are independent across triplets. Hoeffding's inequality therefore
gives

```text
Pr(abs(mean_j D_j,pq - tau_pq) > h) <= 2 exp(-J h^2 / 2).
```

For the two primary contrasts and familywise level `alpha=0.05`, the frozen
radius is

```text
h = sqrt(2 log(2 * 2 / alpha) / J) = 0.2702476221 at J=120.
```

A union bound gives simultaneous coverage of at least 95% for both primary
contrasts. Each interval is clipped to `[-1,1]`. The secondary total-delegation
contrast receives a marginal 95% interval using family size one. These intervals
require bounded outcomes, independent logged triplet assignments, consistency,
and no treatment-dependent cross-model interference. They require no iid
triplet sampling model, homoskedasticity, normality, or constant treatment
effect.

Paired Student-t and Bonferroni paired-t intervals remain descriptive companions
under a superpopulation-of-triplets interpretation. They are not described as
randomization inversions.

## Outcome-blind adversarial validation

The frozen validation uses five fixed binary potential-outcome schedules and
5,000 independently randomized 120-triplet experiments per schedule. Two mixed-
null schedules keep one registered focal pair exactly at its sharp null while
giving the nuisance policy a large heterogeneous effect.

- Worst elementary true-null rejection is 4.06% for the corrected pairwise law
  and 8.12% for the superseded all-policy law.
- Worst Holm false rejection of the remaining true null is also 4.06% for the
  corrected law and 8.12% for the superseded law in these mixed-null schedules.
- Maximum absolute Monte Carlo estimator bias over the fixed schedules is
  0.00167.
- Worst Bonferroni paired-t two-contrast family coverage is 95.52%.
- Worst design-Hoeffding family coverage is 99.90% in the simulations. The
  inequality, not the observed simulation rate, supplies its guarantee.
- Mean interval width is about 0.290 for the descriptive paired-t family and
  0.540 for the design-valid family.

These are implementation and planning facts, not H95 outcomes. The release must
retain the corrected pairwise law, both interval layers, and every registered
missingness and transport diagnostic regardless of the realized sign.
