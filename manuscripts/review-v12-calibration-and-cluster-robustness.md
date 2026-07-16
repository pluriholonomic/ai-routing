# Independent panel review — v12 calibration and cluster robustness

Artifacts reviewed: the revised LaTeX manuscript; preregistration commits
`adc09cd` and `dc90d02`; the pinned 196-event panel; the 163-event
own-menu-novel panel; 5,000 conditional-design replications; 1,250 known-clock
panels; exact enumeration of 262,144 and 16,384 model-cluster sign assignments;
the empirical-versus-SIM2 calibration table; two deterministic pinned release
replays; and the still-masked H80 assignment ledger.

## Referee A — ACM EC / empirical IO

The revision resolves my principal reporting objection. The authors do not tune
the structural simulation toward the data after observing its failure. Instead,
they show directly that the empirical event count, exact-landing probability,
menu probability, and matched-menu residual all lie outside the registered
SIM2 null's 5th--95th percentile ranges. SIM2 is now correctly labeled a
stress-test counterexample: it proves that a correctly sized global-menu test can
have no power in a declared asynchronous-menu family, but it is not evidence that
this family generated the market data.

The new exact sign-flip calculations are also informative. The full-panel
one-sided p-value is 0.425 and the own-menu-novel value is 0.214. These checks do
not overturn the positive point estimates, but they make the concentration
problem unmistakable: the apparent response atom is event-weighted evidence from
too few effective model clusters. The authors appropriately retain the bootstrap
primary and do not reinterpret sign symmetry as random assignment.

The methodological contribution is now coherent and, in my view, publishable in
principle: weak adjacent-level placebos overattribute discrete-menu mass, while a
dominating hard null can underattribute strategic response. The observational-
equivalence theorem, detection threshold, independently timestamped provider-menu
control, finite-sample power curve, and calibration failure jointly define a
useful falsification ladder for platform microstructure.

The paper still lacks a positive behavioral result that separates rival response
from asynchronous administered menus. The earliest-30-date replication is not
available, and the only randomized route to an operational causal claim remains
well short of its preregistered gate. For ACM EC, I would encourage resubmission
with one of those two samples matured rather than asking the current negative
identification result to carry the full empirical paper.

**Recommendation: REVISE AND RESUBMIT.** The methodology is substantially stronger
than v11; the decisive empirical discrimination is still pending.

## Referee B — operations research / platform systems

The computational artifact is strong. The control and simulation parameters were
committed before estimation; the robustness addendum was committed before its
statistics; all sign assignments were enumerated rather than Monte Carlo sampled;
the registered simulation was not retuned; and two independent runs of the pinned
revision reproduce all 16 canonical artifact hashes and the fixed metric vector.

The new calibration table changes the interpretation of SIM2 in the correct
direction. It should not be used to quantify power in the observed market because
its event intensity and exact support are far from the data. Its value is a
constructive OR counterexample demonstrating benchmark dominance. A future
structural paper would need a held-out calibrated clock/menu family, preferably
fit on pre-period endpoint multiplicities and evaluated on post-period event and
support distributions.

The remaining bottleneck is data, not another asymptotic correction. With 18 full
and 14 control-surviving model clusters—and one model responsible for most
events—neither bootstrap nor sign-flip inference can manufacture external support.
The randomized routing design is the right operational experiment, but outcomes
must remain masked until 500 first-position assignments per arm.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** Excellent reproducibility
and honest stress testing; insufficient confirmatory and randomized support.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** V12 removes the last material
overstatement around the known-clock simulation. It does not meet the user's
acceptance stop rule because both legitimate promotion paths remain incomplete.

### Ranked conclusions

1. **Strong:** posted inference prices are sticky administered menus and exact
   price atoms greatly exceed independent grid-constrained pricing.
2. **Strong methodological result:** adjacent-level and dominating-menu tests fail
   in opposite directions; identification requires an explicit null class and
   detection region.
3. **Moderate association:** slower repricers charge a conditional premium, in the
   Brown--MacKay direction, but reaction-rule prediction is indistinguishable from
   state dependence.
4. **Suggestive but unsupported:** removing own-provider menu reuse raises the
   lagged-rival residual to 13.4 points, yet bootstrap and exact sign-flip inference
   do not promote it.
5. **Stress-test only:** known-clock asynchronous menus can eliminate power, but
   the registered family is empirically rejected as a calibration.
6. **Pending:** causal firmness and front-running-style discrimination await H80
   and the 30-date release; literal request front-running remains unobserved.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 94% | Dealer-and-dispatcher market remains distinctive. |
| Identification contribution | 98% | Equivalence, detection threshold, controls, and power form a reusable ladder. |
| Test calibration | 95% | Size, power, sign-flip sensitivity, and failed structural calibration are disclosed. |
| Positive empirical discrimination | 61% | Positive residuals lack cluster support. |
| Manuscript completeness | 99% | Full paper, proofs, tables, figures, and claim ledger. |
| Pipeline and release integrity | 99% | Timestamped specs and 16/16 deterministic replay. |
| External validity | 70% | Structural mismatch is measured rather than hidden; effective support remains narrow. |
| Firmness causal evidence | 40% | Randomized first-position gate remains immature and masked. |
| Submission readiness | 84% | Strong methods paper, but top empirical venue still wants a matured promotion path. |

### Mechanical gates

- Quote panel: 10/30 outcome-free calendar dates at the last pinned audit; 20 remain.
- H80: 33, 37, 34, and 36 of 500 first-position assignments per arm at the last
  outcome-free audit; all 140 assignments replayed exactly and outcomes remain masked.
- PM5: rerun the unchanged endpoint-label, factor-1.25, same-provider, and
  own-menu-novel estimands on the earliest 30-date revision.
- Interpretation: SIM2 remains frozen and may only be called a stress-test
  counterexample in this release.

The next useful work is accrual, not specification search: preserve the outcome
mask, collect the remaining calendar support and randomized assignments, then run
the already frozen promotion tests.
