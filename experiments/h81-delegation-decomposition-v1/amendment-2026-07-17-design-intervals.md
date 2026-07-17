# H81 finite-population intervals and joint-Holm power audit

Status: outcome-blind amendment written on 2026-07-17 after exact-head remote
preflight run `29566914482` checked commit `244c384` against immutable dataset
revision `42334a840dc8088cc8cde441ebe3649cfa041b5e`. The preflight reported 84
verified H81 first-position blocks with counts 32/24/28 and
`outcomes_queried=false`. This amendment was therefore fixed without inspecting
an H81 outcome.

This amendment does not change the treatments, assignment, eligibility,
stopping rule, estimands, directional hypotheses, two-test Holm family, or
outcome coding. It adds a conservative interval that matches the conditional
finite-population theorem and an exact joint power audit for the already
registered Holm procedure.

## Design-valid simultaneous interval

The registered Newcombe and Bonferroni--Newcombe intervals remain descriptive
two-sample binomial companions. They are not randomization inversions. To add an
interval justified by the actual stopped design, condition on the terminal
policy and preterminal count vector as in the pairwise-Fisher amendment. For
each policy `p`, the `n_p` assigned blocks are then a simple random sample
without replacement from the fixed `B`-block schedule of bounded potential
outcomes `Y_b(p) in [0,1]`.

For familywise level `alpha=0.05`, let `B=sum_p n_p` and define

```text
rho_p = 1 - (n_p - 1) / B,
h_p = sqrt(rho_p * log(2 * 3 / alpha) / (2 n_p)).
```

The Hoeffding--Serfling sampling-without-replacement inequality gives

```text
Pr(|mu_hat_p - mu_p| > h_p | T, terminal policy, counts) <= alpha / 3.
```

A union bound over the three policy means therefore gives simultaneous coverage
at least 95%. Each contrast `p-q` receives the clipped interval

```text
[mu_hat_p - mu_hat_q - h_p - h_q,
 mu_hat_p - mu_hat_q + h_p + h_q] intersect [-1,1].
```

This interval is finite-population and design-valid conditional on the stopped
prefix. It requires bounded outcomes and correct assignment replay, but no
binomial superpopulation model, arm independence, monotonicity, or constant
treatment effect. It is intentionally conservative.

## Coverage stress test

The implementation runs 3,000 stopped experiments for each of five fixed binary
potential-outcome schedules: heterogeneous sharp null, monotone midrange,
time-varying sign heterogeneity, rare success, and near-ceiling success. This is
an adversarial implementation audit, not an empirical result or a proof.

- The worst marginal Newcombe coverage is 94.67%; its Monte Carlo standard
  error at 95% coverage is about 0.40 percentage points.
- The worst two-contrast Bonferroni--Newcombe family coverage is 95.13%.
- The worst design-Hoeffding--Serfling family coverage is 99.93% in these simulations. Its guarantee
  comes from the inequality above, not from this observed simulation rate.
- The precision cost is material: mean design-Hoeffding--Serfling contrast width is about
  0.76, versus roughly 0.29--0.45 for the descriptive intervals across these
  schedules.

The release must show both layers. The Newcombe interval conveys model-based
precision; the Hoeffding--Serfling interval states what the randomization design alone can
guarantee. Neither may be suppressed based on the realized sign or width.

## Exact joint Holm power

The previous marginal power grid used a 2.5% Bonferroni threshold as a
conservative lower bound for a single Holm-adjusted contrast. The new audit
enumerates every triple of success counts under independent Bernoulli planning
scenarios, computes both exact pairwise Fisher tails, applies the registered
two-test Holm step-down rule, and integrates the joint rejection event exactly.
It repeats the calculation for each possible terminal policy at minimum
preterminal counts 39/40/40.

On the preregistered 5-percentage-point grid:

- a fallback-only wedge needs 35 points for at least 80% fallback-rejection
  probability under the worst terminal-policy identity;
- a selection-only wedge also needs 35 points;
- when both components are equal, each needs 35 points for at least 80% power to
  reject both nulls; and
- the largest false-rejection probability for the remaining true null in the
  two mixed-null scenarios is 3.23%.

These are model-based planning scenarios, not H81 outcomes. They strengthen the
existing conclusion: the original gate can detect large component wedges but is
not an equivalence design and is weak for modest economically relevant effects.

## Frozen release consequence

At first release, the analyzer must report effect magnitudes, descriptive
Newcombe intervals, Bonferroni--Newcombe family intervals, design-Hoeffding--Serfling
simultaneous intervals, exact pairwise Fisher tails, and Holm-adjusted one-sided
p-values. A wide design interval, null, sign reversal, failed audit, or missing
outcome remains reportable and may not trigger an alternative specification.
