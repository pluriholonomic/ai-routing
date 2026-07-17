# H95 position-zero carryover sensitivity amendment

Status: outcome-blind amendment written on 2026-07-17 after exact-paper-head
audit `29569590704` checked commit `4860015` against immutable dataset revision
`f5b822812a8266200c9b277e88578c8829338e83`. The audit reported five of 120 H95
triplets, 15 first-position requests, perfect assignment replay and plan
compliance, and `outcomes_queried=false`.

This amendment changes no treatment, candidate frontier, model sampling,
triplet construction, primary estimator, fixed 120-triplet horizon, primary
Holm family, missingness rule, or reporting gate. It freezes a secondary
position-zero sensitivity that trades precision for immunity to
treatment-dependent carryover from an earlier H95 model block.

## Design and estimand

The collector samples and orders three eligible models before shuffling the
three policies across those positions. Let `M_j0` be the model scheduled at
triplet position zero and let `A_j0` be its assigned first policy. Conditional
on the written triplets and realized position-zero models, `A_j0` is uniform
over the three policies and independent across triplets.

For policy `p`, define

```text
mu_p_zero = (1/J) sum_j Y_j,M_j0(p).
```

Conditional on the position-zero arm-count vector, the units assigned each
policy are a simple random sample without replacement from the `J=120` fixed
position-zero units. Their arm mean is therefore design-unbiased for
`mu_p_zero`. Averaging additionally over the randomized model order maps this
estimand back to the mean over the three selected models in each triplet.

Position zero is both the first model block in the triplet and its first policy
request. No earlier H95 request in that triplet can affect it. The sensitivity
does not exclude interference from unrelated traffic before the triplet.

## Exact tests and intervals

For each pairwise sharp null, condition on the nuisance-policy membership and
the realized two focal arm counts. Conditional on their pooled binary outcomes,
the positive-arm success count is hypergeometric. The two secondary directional
tests receive Holm adjustment within their own secondary two-test family; they
do not change or replace the primary family.

For familywise level `alpha=0.05`, each policy mean receives the
Hoeffding--Serfling radius

```text
h_p = sqrt((1 - (n_p - 1)/J) log(6/alpha) / (2 n_p)).
```

A union bound over the three policy means gives simultaneous coverage at least
95%; contrast intervals add the two relevant radii and clip to `[-1,1]`.
Unknown or malformed position-zero outcomes suppress its complete-data point
and test output and enter `[0,1]` bounds. Missing or noncompliant planned first
requests retain the primary protocol's structural intent-to-treat zero.

## Planted-interference audit

The outcome-blind validation holds all direct policy effects at zero and plants
carryover that can improve a later model block after delegated policy appeared
earlier in the triplet. It runs 5,000 independent 120-triplet assignments at
five spillover strengths.

- Maximum absolute bias of the primary three-block hidden-selection estimator
  is 0.2437.
- Maximum absolute bias of the position-zero estimator is 0.00103.
- Worst observed position-zero design-family coverage is 100% in the fixed
  schedules. The inequality, not the simulation, supplies the guarantee.
- Mean position-zero contrast interval width is 0.810.
- Position zero has larger variance than the primary estimator when planted
  spillover is weak; its RMSE becomes lower only as interference dominates the
  primary estimator's precision advantage.

This audit proves neither that actual carryover exists nor that it is absent.
At release, agreement supports but does not prove the no-interference
interpretation; disagreement narrows the defensible conclusion to the
carryover-free position-zero estimand.
