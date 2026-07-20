# Adaptive-router future-only adversarial validation v3

**Study ID:** `adaptive-router-adversarial-v3`  
**Configuration:** `config/adaptive_adversarial_v3.toml`

## Pre-release correction

The version-2 protocol was frozen before the large version-1 screen, but that screen
revealed that nominal UCB seeds were exact duplicates: rewards were deterministic and
the seeded within-epoch provider permutation could not change simultaneous actions.
Version 2 was therefore superseded before any eligible outcome was released. No
version-2 marker exists and it must never be run.

Version 3 makes the smallest scientific correction: UCB agents observe realized routed
quantities from a seeded multinomial draw, clipped at admitted capacity. Final
exploitability is still evaluated in expectation. The mechanism, deviation grids,
cost/capacity bands, learner horizons, and all materiality thresholds are unchanged.
The support minimum is 4,500 menus because the completed 14-day assignment-only
screen contained 4,878 eligible menus; this is a completeness rule, not an outcome
threshold.

## Future-only boundary

Only endpoint menus dated 2026-07-22 through 2026-08-04 UTC are eligible. Release is
forbidden before 2026-08-05 UTC. The workflow verifies all 14 partition names without
opening row-level data, writes one immutable HF marker for an exact dataset revision,
then reads eligible rows and publishes the release regardless of sign. A marker can be
written only once.

Every gate from v2 remains fixed. In particular, the post-UCB mean exploitability ratio
must be at most 0.60; the adverse v1 screen did not relax this threshold.

Passing remains bounded to the observed future menus, declared cost/capacity bands,
finite deviation grids, two-provider coalition class, and seeded UCB/Q-learning
families. It is not strategy-proofness, equilibrium, causal provider response,
collusion identification, or welfare identification.

