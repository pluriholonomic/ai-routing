# H81 post-release missing-outcome presentation recovery

Date: 2026-07-18

Status: post-outcome, presentation-only recovery. This document is not a
preregistration and changes no assignment, stopping, outcome, estimand, or
inference rule.

## Immutable source and failure

The first H81 outcome access occurred remotely at
`2026-07-18T06:54:53.263432+00:00`, after the 40-intended-assignments-per-arm
and assignment-integrity gates passed. The marker commit is
`f66fb7fb557305a2fc492653afb97b32a5202ee2`; the pinned dataset revision is
`b31f9aa298bfcad020a8751c625c51a7c88fa1ac`; and the downloaded release
manifest has SHA-256
`8150c182d455edc0c97662fcfe141bf369026246358c4415b5a55f49dab9b925`.

The strict outcome-blind presentation template then failed closed with
`H81 complete-data report cannot mask missing binary outcomes`. This is the
registered behavior: the raw marker-bound policy panel, contrast panel, model
panel, intended-assignment ledger, support tables, summary, and manifest were
preserved; the source outcomes cannot be queried again; and the failed
complete-data table, figure, paragraph, exact p-values, and Holm decisions are
not paper-promotable.

## Recovery rule

The recovery reads only the downloaded immutable bundle and validates every
payload hash in its release manifest. It does not read the Hugging Face source,
the capture store, request logs, or any later H81 block. It reports:

1. each policy arm's released success-mean identified set, assigning every
   unknown binary outcome once to zero and once to one;
2. the released treatment/outcome identified set for each of the three frozen
   contrasts;
3. a design interval only when the raw release contains that interval;
4. `not released` for the two registered primary tests and no Holm decision;
5. the terminal-block exclusion, observed/missing counts, two-model support,
   owned-account boundary, and no-requery provenance; and
6. the algebraic identity at both endpoints of the released contrast sets.

The recovery must fail if a source hash changes, the marker or terminal
exclusion is absent, an arm or contrast is missing, the identified-set ordering
fails, the endpoint decomposition fails, a partial Holm value is present, or
the raw presentation did not fail closed. It cannot be used when all binary
outcomes are complete; that case remains governed by the original frozen
renderer.

## Released interpretation

The terminal price-order-fallback block is excluded, leaving 133 preterminal
assignments: 45 no-fallback, 39 price-order-fallback, and 49 delegated default.
No-fallback has 44 observed binary outcomes and one unknown outcome; the other
two arms have complete binary outcomes. The immutable identified sets are:

- no-fallback success: `[0.9333, 0.9556]`;
- price-order-fallback success: `1.0000`;
- delegated-default success: `1.0000`;
- fallback option, F minus N: `[0.0444, 0.0667]`;
- hidden selection, D minus F: `0.0000`; and
- total delegation, D minus N: `[0.0444, 0.0667]`.

These are bounds on the realized intended-assignment estimators for the frozen
prefix. The complete-data Fisher tails and two-test Holm family remain
suppressed under the frozen rule, so the paper makes no formal primary
rejection. The zero hidden-selection contrast is not evidence of equivalence;
its released simultaneous finite-population design interval is
`[-0.3861, 0.3861]`. The positive fallback and total identified sets are not a
license to invent missing-data p-values.

The empirical claim remains an owned-account, two-model, finite-prefix result.
It does not identify market-wide routed share, router intent, provider cost,
collusion, front-running, or welfare.
