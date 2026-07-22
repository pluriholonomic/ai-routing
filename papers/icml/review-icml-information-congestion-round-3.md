# Adversarial ICML review: critical memory and information congestion

## Summary

The paper studies a stateful pricing learner whose profitable low-price action
requires a persistent path. It separates a rational memory boundary from a
finite-time learning boundary, proves an exponential fresh-path bound after an
arbitrary readiness stopping time, and shows that a path-equivalent option
preserves optimal value while reducing proposal time to linear. It then lifts
the path bound to a finite-horizon responsive-provider count and a local routed-
share bound, and combines that count with a conditional information-congestion
planner. Controlled Q-learning, exact dynamic programming, trace replay, a
fixed-\(n\) bandit falsification, and frozen public-market property tests support
and delimit the theory.

## Strengths

1. **The rational and computational boundaries are genuinely distinct.** The
   paper shows both when persistent cutting is optimal and when a bounded
   learner is unlikely to obtain fresh support. This is a clear contribution to
   learning in economic environments.
2. **The stopping-time formulation is strong.** The \(Tq^M\) bound applies after
   any declared readiness checkpoint and separates temporal support from reward
   SNR. It does not rely on iid behavior for the upper bound.
3. **The responsive-set and local flow bounds connect the single-agent theorem
   to a market quantity without overclaiming.** The Jacobian argument makes the
   multiplicative role of mechanical elasticity and finite-time learning
   probability explicit.
4. **The intervention has an exact representation theorem.** The commitment
   option creates no new primitive path and preserves optimal value. Its failure
   beyond the rational boundary is reported, avoiding a monotone-benefit story.
5. **The trace diagnosis is unusually convincing.** All seeds cover every
   state-action pair and reach the terminal state early; failed online learners
   stop revisiting deep states, while ordered batch Bellman sweeps on the same
   transitions recover the optimum in 20/20 seeds.
6. **Negative transport is treated as a result.** The fixed-\(n\) bandit changes
   action correlation but not allocation. Public data reject the proposed
   GLM-minority/non-GLM-linear split. This makes the paper more credible.
7. **Reproducibility is excellent.** Frozen artifacts, exact replay checks,
   simulation seeds, immutable public revision, and explicit non-entry of public
   data into the MDP are all documented.

## Weaknesses

1. **The information-congestion planner is less fundamental than the temporal
   result.** Its loss is assumed, and the scaling theorem is a straightforward
   optimizer. This section risks making the paper look broader but shallower.
2. **The probability cap \(q_i\) is exogenous.** In a strategic learner it may
   depend on score feedback, rival actions, and the same memory state. The bound
   remains valid conditionally, but its operational estimation is unclear.
3. **The routed-share result is local.** Large GLM discounts are not infinitesimal,
   and simultaneous finite moves can leave the first-order region. A finite-move
   Lipschitz or path-integrated counterpart would strengthen the bridge.
4. **The controlled learner class is narrow.** Tabular Q-learning, an explicit
   option, and batch Bellman sweeps do not cover recurrent function
   approximation, model-based planning, or prioritized replay.
5. **No live memory parameter is identified.** The public and paid panels are
   legitimate falsification screens, but they do not show that any production
   router implements the finite-memory transition.

## Questions for the authors

1. Can a recurrent or model-based agent synthesize the option, and what retained
   state or replay capacity replaces the \(q^{-M}\) term?
2. Is there a finite-price-move version of the routed-share bound that remains
   useful for 20--40% discounts?
3. How should \(q_i\) be estimated or bounded from an adaptive policy without
   conditioning on post-treatment behavior?
4. Does stochastic memory decay produce an analogous spectral or hitting-time
   threshold?
5. Can covariance-aware exposure caps and temporal options be optimized jointly
   without the reduced-form planner loss?

## Recommended revisions

- Keep the late-credit theorem and option result visibly primary; label the
  cross-sectional planner as a conditional benchmark.
- Add a finite-move share sensitivity result or explicitly quantify the local
  approximation range.
- Add at least one recurrent or replay-based learner as an adversarial transport
  experiment.
- Preserve the current empirical language. The negative GLM/non-GLM result is
  more informative than an underpowered positive claim.

## Scores

- Technical quality: 9/10
- Novelty: 8/10
- Empirical grounding: 7/10
- Reproducibility: 9/10
- Overall: **7/10, Accept**

## Decision

**Accept.** The finite-time memory boundary, exact path-equivalent intervention,
and late-credit diagnosis form a strong ICML contribution. The new market-level
bounds are useful when read conditionally, and the paper's negative transport
tests prevent them from becoming an unsupported live-market story.
