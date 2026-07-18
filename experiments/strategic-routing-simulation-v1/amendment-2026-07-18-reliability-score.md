# SM2 reliability-score extension

**Written:** 2026-07-18 after the amended three-router screening
**Scope:** new mechanism treatment; original contrasts remain unchanged

The revised SM2 screen found that deterministic lowest-price routing won only
under spare homogeneous service. Uniform routing beat inverse-square routing
when the cheap endpoint was capacity-scarce or unreliable. This is consistent
with price-only over-allocation to a weak endpoint, but the registered
three-router screen did not contain a mechanism that directly uses reliability.

Before running a reliability-aware treatment, add:

    score_i = quote_i^(-2) reliability_i^4.

The exponent four is fixed before viewing this treatment. It is chosen because
it reverses the first-route score ordering in the frozen synthetic unreliable
fixture while leaving equal-reliability fixtures identical to inverse-square.
It is not fitted to maximize the observed screening outcome.

All seeds, provider states, demand paths, outcomes, common-random-number
construction, and evidence boundaries remain unchanged. The new comparison is
an optimization extension and is reported separately from the original
three-router screen.
