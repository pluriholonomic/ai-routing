# Adversarial ICML review: critical memory with endogenous market participation

## Summary

The paper proves a finite-time support barrier for stateful pricing learners,
separates that computational boundary from a rational payoff boundary, and gives
a path-equivalent commitment option that preserves primitive paths and optimal
value. It then bounds the responsive-provider set and local routed-share
reallocation, combines the result with a conditional information-congestion
planner, and subjects the mechanism to controlled simulations and frozen public
property tests. The revision clarifies that the provider population is produced
by a prior costly-entry stage: bilateral profit can change entry without
changing the memory action comparison when capacity is slack, while a binding
capacity shadow cost moves the rational and learning boundaries.

## Strengths

1. The rational, computational, entry, and social-exposure margins are now
   cleanly separated.
2. The stopping-time \(Tq^M\) result remains the paper's strongest contribution:
   it is simple, non-asymptotic, and operational.
3. The exact path-equivalent option is an unusually clean intervention because
   it preserves the economic primitive rather than changing rewards.
4. Trace replay distinguishes exploration failure from failure to revisit deep
   states after discovery.
5. The costly-entry clarification prevents the responsive-count theorem from
   being misread as a theorem about all potential firms or endpoint labels.
6. Negative transport results and the absence of a live memory claim are
   handled correctly.
7. Artifacts, seeds, frozen revisions, and claim boundaries remain strong.

## Weaknesses

1. The controlled learner class is still narrow relative to modern recurrent,
   model-based, and prioritized-replay agents.
2. The market-share result is local, whereas observed discounts can be large.
3. Costly entry is conditioned on rather than learned in the environment; no
   agent jointly chooses capacity, entry, and memory-aware pricing.
4. The information-congestion loss remains reduced form and is weaker than the
   temporal result.
5. No production router memory parameter, entry cost, bilateral contribution,
   or capacity shadow cost is identified.

## Questions

1. Does the support barrier survive with learned state compression or a
   recurrent world model?
2. Can a finite-move routed-share bound replace the local Jacobian calculation?
3. What happens when an agent jointly chooses entry and replay/memory capacity?
4. Can execution-contingent capacity contracts make the capacity shadow price
   observable enough to transport the rational boundary?

## Overall assessment

**Score: 7/10 — Accept.**

The costly-entry addition improves economic interpretation without diluting the
core ML contribution. The paper does not solve endogenous entry and stateful
learning jointly, but it no longer silently treats the provider population as
costless or fixed by nature. The finite-time theorem, exact interface
intervention, strong trace diagnosis, and honest negative transport evidence
remain sufficient for acceptance.

## Path to strong accept

- Add recurrent/model-based and prioritized-replay adversaries.
- Prove a finite-move share bound.
- Extend the environment so agents choose entry or capacity before pricing.
- Randomize a disclosed memory or commitment rule in an owned routing test.
