# Adversarial review — "The Router Is the Demand Curve"

*Round 3, 2026-07-18. Venue lens: ACM EC main track, with a secondary
NeurIPS economics-and-learning lens. This report supersedes the earlier review,
which evaluated a materially different paper. Reviewed artifacts: nine-page PDF,
source freeze `4f9007be9e1ffdaea2cfce2a5ecc421d58b80f45`, and clean E-SIM5--9
bundles `3e5a55405e`, `93265b9b03`, `bd74ab2eb7`, `4d84b9b3a2`, and
`179eca0f9d`.*

## Recommendation

**Weak accept (6/10), confidence 4/5.** I would accept this as a narrow EC
paper about a marketplace-induced delayed-credit problem and a
path-equivalent interface intervention. I would not accept the broader claim
that inference providers actually use these learners, that the live router
causes elevated prices, or that the paper identifies collusion. The submitted
version no longer makes those claims.

## What the paper establishes

The paper separates three objects that prior drafts conflated.

1. A documented inverse-power routing rule induces a provider residual-demand
   system. The share derivative, single-crossing best response, symmetric
   pure-strategy price, and provider-level markup floor follow exactly.
2. In a binary-price, fixed-rival reduction, a finite penalty on recent cuts
   creates a closed-form region in which a persistent cut is dynamically
   optimal even though every penalized cut period is worse than remaining
   high. The calibrated memory boundary is `9.240`; the chosen `M=7` lies
   inside that region.
3. A semi-Markov commitment option unrolls to an already-feasible sequence of
   primitive actions, so it preserves the exact optimal provider value and
   every primitive price path. It nevertheless changes learnability for the
   frozen tabular-Q algorithm.

The main numerical result is unusually clean for a simulation paper. At
`M=7`, the exact optimizer cuts, primitive Q succeeds in 1/20 seeds, and the
option learner succeeds in 18/20. The option-minus-primitive normalized-regret
contrast is `-0.0643`, with paired seed-bootstrap interval
`[-0.0755,-0.0493]`. These intervals quantify simulator randomness, not market
parameter uncertainty, which the paper states explicitly.

## Adversarial checks

### 1. Is the high-price path an equilibrium?

No. The paper's own persistent-deviation audit finds an `8.17%` discounted
gain. This invalidates the old equilibrium/collusion interpretation, and the
current manuscript retains that rejection. The remaining result concerns a
bounded learner's implementation gap, not equilibrium selection.

### 2. Is the result merely state aliasing?

No under the registered test. E-SIM5 exposes the complete `2^7=128`-state
history, yet the full-history learner still fails in 19/20 seeds. The
state-aliasing gate fails and is reported as a negative result.

### 3. Does the option secretly expand the economic opportunity set?

No in the stated finite MDP. The option is exactly `M+1` existing low actions.
Unrolling maps every augmented policy to a primitive policy with identical
states and discounted rewards. Exact primitive and option values agree at
every state within `10^-10`. This proves value equivalence for the provider;
it does not prove welfare equivalence in a multi-provider game, and the paper
does not say that it does.

### 4. Is the learning effect a single hyperparameter accident?

Not locally. E-SIM8 passes its preregistered conjunction in 7/9 cells. All nine
regret intervals favor the option, while the two failed cells fail because
primitive learning improves enough to violate the registered severity gate.
This is the correct interpretation: the intervention effect is locally robust,
but the primitive failure's severity is algorithm dependent.

### 5. Does the mechanism transport across calibrated markets?

Only partially. E-SIM7's strict transport gate fails: only two of four books
are eligible and their primitive success rates are 12/20 and 14/20. The
prespecified rational-boundary classification aligns with all four effect
signs, which is useful descriptive evidence but not a passed confirmatory
transport result. The manuscript now uses exactly that claim boundary.

### 6. Would an ordinary multi-step target obtain the same result?

No in the registered falsification. E-SIM9's eight-step Q target succeeds in
0/20 seeds and has regret `+0.0038` relative to one-step Q, interval
`[0,0.0113]`; the option benchmark remains 18/20. This is a valuable negative
result because it prevents the paper from selling a generic delayed-return
claim. The evidence instead supports option-specific temporal abstraction.
The experiment does not rule out eligibility traces, Retrace, distributional
returns, or other multi-step operators.

### 7. Are the computations auditable?

Yes. Each final bundle records the same source commit, result and input hashes,
and equality between executed market-environment source and that commit. The
full repository test suite passes. The paper-number evidence test locks the
positive and negative claims to the final JSON artifacts.

## Theory assessment

The economic core is rigorous at the level needed for this claim. The static
results follow from a one-dimensional single-crossing argument. The dynamic
boundary follows by reducing any eventual-cut path to `k` high actions followed
by permanent low; the difference from remaining high is a discounted scalar
multiple, so immediate cut or never cut exhausts the optimum. The option-value
theorem is a standard but exact path-unrolling argument.

Two scope restrictions are essential and are now present. First, the static
equilibrium statements are about symmetric pure strategies; they do not
characterize asymmetric or mixed equilibria. Second, the option theorem is a
provider-value statement in the fixed-rival MDP, not a theorem about global
welfare, full-game equilibrium, or collusion.

## Remaining weaknesses

- The empirical cut multiplier is a conditional association from one buyer
  tier, not a randomized estimate of a proprietary router rule. The dynamic
  environment is therefore calibrated, not structurally identified.
- The main mechanism fixes rivals and reduces the subject's action space to two
  audited quotes. Endogenous multi-provider learning could change both the
  rational boundary and the intervention effect.
- Twenty seeds support the frozen-simulator contrast but do not measure
  calibration uncertainty. The four-book transport panel is small and its
  confirmatory gate fails.
- The positive result is specific to tabular Q and an explicit commitment
  option. E-SIM9 makes this limitation more credible, but it also narrows the
  NeurIPS learning contribution.
- The paper derives provider incentives, not a welfare theorem. The static
  markup floor is relevant to market design, but total surplus would require
  demand, quality, congestion, and capacity primitives not identified here.

These are limits on external validity, not internal contradictions. They are
visible in the abstract, results, and limitations rather than being deferred to
an appendix.

## Venue judgment

For ACM EC, the combination of a public routing rule as a demand primitive, an
exact marketplace-induced delayed-credit boundary, a path-equivalent interface
intervention, registered negative tests, and immutable computational evidence
is sufficient for acceptance as a focused paper. For a standard NeurIPS main
track, the tabular learner and small calibrated transport set make the case
more borderline; acceptance would depend on valuing economic mechanism
identification over algorithmic novelty.

**Final recommendation: weak accept.** The result is publishable because its
narrow claim is new, theoretically exact, falsifiable, and survives the tests
that should have killed it. The paper should not broaden its causal, welfare,
equilibrium, or collusion language without new evidence.
