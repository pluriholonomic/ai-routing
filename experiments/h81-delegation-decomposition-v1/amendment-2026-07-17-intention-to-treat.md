# H81 outcome-blind amendment: intended-assignment ITT ledger

Date frozen: 2026-07-17

Status: frozen before the first H81 outcome query.

## Provenance point

Exact-head remote audit `29570676475` checked out commit
`406a47810e269e11bff72c70db60d0097b041cba`, pinned immutable dataset
revision `f5b822812a8266200c9b277e88578c8829338e83`, and reported H81 arm
counts 32/24/28 with `outcomes_queried=false`. All 84 recorded first requests
passed assignment replay and treatment-metadata checks at that revision. The
audit artifact contained only `assignment_only_gate.json` for H81 and H95 plus
the release-status summary.

## Defect being corrected

The prior analyzer defined both the 40-per-arm balance gate and the primary
sample using requests that passed a post-assignment treatment-metadata check.
That rule is harmless on the currently observed support because treatment
fidelity is 100%, but it is not a valid general reference experiment. If
treatment fidelity depends on the randomized policy, request realization, or a
potential outcome, filtering before the Fisher test can destroy the uniform
fixed-count assignment law and turn the reported contrast into a selected
per-protocol comparison.

This is a design correction, not a response to an observed H81 effect. No H81
outcome field had been queried when it was made.

## Frozen correction

1. The stopping gate counts intended first-position assignments, not only
   treatment-compliant requests.
2. A prospective `router_decomposition_plans` row is written after the public
   provider set and policy permutation are fixed but before the first request is
   sent. It records the block seed, intended first policy, assignment
   probability, model, time, ranking position, and provider-order hash, but no
   prompt, completion, outcome, cost, latency, or selected provider.
3. Historical eligibility rows without this plan table replay the ranked-
   candidate shuffle from `run_seed`, verify the recorded evaluation order, and
   consume the original 64-bit block seed for every eligible candidate. This
   recovers an intended assignment even if no attempt row exists. Still older
   recorded blocks fall back to their block seed. Prospective plan rows must
   themselves replay to the recorded intended policy.
4. A missing first request, duplicated first record, recorded-policy mismatch,
   or failed provider-control metadata check remains in its intended randomized
   arm. These are treatment-realization or measurement facts, not assignment
   eligibility conditions.
5. A unique binary request outcome is attributed to the intended arm even when
   the implementation metadata are noncompliant. This is the intention-to-treat
   outcome of assigning the policy code path.
6. Missing, duplicated, unknown, or malformed outcomes suppress the complete-
   data point estimate and exact test and enter the existing bounded-outcome
   sensitivity.
7. First-row observation, assignment replay, and treatment-metadata fidelity
   are reported by arm and in the gate audit. A second sensitivity treats
   noncompliant implementations as untrusted outcomes in `[0,1]`; it is not a
   complier or per-protocol effect.
8. Any plan mismatch, failed historical run replay, missing eligible block id,
   or unreconstructable recorded block closes the assignment-integrity gate. It
   is not repaired by accruing additional compliant requests.

The gate-hitting terminal block is still excluded. The target remains 40
intended assignments per arm. The two directional contrasts, signs, Holm
family, exact nuisance-conditioned Fisher laws, design intervals, missing-
outcome rule, and one-shot release mechanism are unchanged.

## Estimand and claim boundary

For preterminal block `b`, `Y_b(p)` is the binary deliverability outcome under
assignment to policy `p`, including any effect of the software successfully or
unsuccessfully realizing the requested controls. Conditional on the stopped
intended-assignment counts, the arm labels are a uniform fixed-count
randomization. Arm means and their differences therefore identify finite-
population ITT effects of assigned policy for the owned account.

If treatment fidelity is below one, these effects must not be described as the
effect of controls actually delivered or as a complier-average effect. The
study still does not identify router intent, private scores, market-wide flow,
provider cost, or welfare.

## Outcome-blind adversarial validation

A fixed-schedule sharp-null simulation uses 3,000 stopped assignments at each
of five strengths of outcome-dependent treatment fidelity. The intended-
assignment estimator remains within 0.0022 of zero and its one-sided Fisher
rejection rate ranges from 2.83% to 3.70%. The superseded filtered estimator
reaches bias 1.0 and false rejection 100% while retaining approximately the
same 50% request share. The construction shows that retention rate alone cannot
validate per-protocol filtering; which outcomes are retained matters.

These simulations demonstrate the failure mode and validate the correction.
They are not H81 outcome evidence and do not assert that real treatment
fidelity is outcome-dependent.
