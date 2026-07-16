# Independent panel review — v13 held-out protocol

Artifacts reviewed: the v12 manuscript and release; preregistration commit
`7709446`; the outcome-guarded MM1/MR1 implementation; synthetic end-to-end tests;
the live 10/30-date gate response at immutable dataset revision
`6e987d68fb5aff3a664c41503d8fba08018f01e6`; and current GitHub Actions health.

## Referee A — ACM EC / empirical IO

The new protocol is a sensible response to SIM2's calibration failure. Matching
whole markets rather than pooled endpoints preserves endpoint multiplicity and
within-market price dependence, while the chronological 15/15 split prevents the
single excess-landing parameter from being estimated on its evaluation period.
The joint promotion rule is demanding in the right dimensions: support,
model-cluster uncertainty, leave-one-model-out sign stability, sign-flip
robustness, and out-of-sample scoring must all agree.

The main limitation is correctly disclosed. MM1 conditions on the realized event
and the mover's new price; it is a conditional benchmark, not a generative model
of refresh timing or price choice. Unobserved model-specific public focal points
can violate cross-market exchangeability without strategic response. Therefore a
future rejection supports a persistent same-model landing increment, not intent,
collusion, or front-running.

No empirical conclusion changes today because the holdout does not exist. This is
preferable to splitting the extremely concentrated nine-day sample after seeing
it. The protocol should remain frozen until its automatic gate opens.

**Recommendation: REVISE AND RESUBMIT.** Stronger prospective identification; no
new mature result yet.

## Referee B — operations research / platform systems

The implementation provides an unusually strong outcome guard. Before 30 dates,
it queries only the date ledger, does not call the quote loader, and cannot emit a
panel containing outcomes. Unit tests verify the 15/15 split, whole-market
hypergeometric calculation, training-only response fit, exact/fixed-Monte-Carlo
sign-flip branch, and a complete synthetic release. A live run returned 10/30,
`outcomes_loaded=false`, and no outcome table.

The remote system is operating. The hourly quote capture and randomized OpenRouter
probe workflows completed successfully, and the independent watchdog reports the
critical workflows and Hugging Face sink healthy. Thus the bottleneck is calendar
and randomized support rather than dependence on the local machine.

The support thresholds are important. At the frozen nine-date audit one model
supplies 144/196 events, so an early positive estimate would not generalize. The
future rule correctly requires no model above 50% and at least ten clusters.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** The prospective artifact
is ready; evidence must accrue.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** The new protocol removes the temptation
to retune the failed structural simulation and provides a legitimate prospective
route to discriminate mechanisms. It cannot satisfy the acceptance stop rule
before the holdout and randomized gates mature.

### Readiness update

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 94% | Dealer-and-dispatcher market remains distinctive. |
| Identification contribution | 98% | Existing equivalence/detection results plus a frozen predictive discriminator. |
| Prospective test integrity | 100% | Commit-pinned 15/15 split and enforced no-outcome gate. |
| Positive empirical discrimination | 61% | No new holdout outcome exists. |
| Pipeline and release integrity | 100% | Remote accrual healthy; local machine not required. |
| Submission readiness | 85% | Complete protocol and paper; top-venue empirical gate still pending. |

The correct next action remains accrual. Do not inspect, simulate toward, or
redefine the future holdout outcome while the date and H80 gates are closed.
