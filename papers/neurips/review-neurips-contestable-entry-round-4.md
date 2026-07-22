# Adversarial NeurIPS review: property-tested routing with costly participation

## Summary

This paper presents a deterministic multi-agent environment for inference
provider competition, with exact request settlement, capacity and fallback,
provider-private feedback, stable random substreams, pluggable routers, and
strategic deviation tests. A property ladder separates kernel invariants,
intervention validity, held-out market properties, strategic robustness, and
live transport. The revision adds an outer-stage costly-entry task: candidates
pay integration and capacity cost before repeated pricing, bilateral contribution
can finance entry, and a closed-form reference compares free entry with a
reliability-based planner count. Entry is kept outside the episode action space,
so agents cannot create costless identities during training.

## Strengths

1. The environment enforces a credible information boundary and exact transfer
   reconciliation.
2. Stable common-random-number substreams make strategic comparisons auditable.
3. The property ladder is a reusable contribution: failed transport tests block
   live-market claims without invalidating controlled mechanism results.
4. The adversarial suite covers unilateral and pair deviations, identity
   splitting, capacity withdrawal, quality shading, quote fading, and multiple
   learner classes.
5. Costly entry is now represented at the right temporal layer. The distinction
   between entrant count, adaptive subset, and correlated exposure prevents
   endpoint labels from being treated as firms.
6. The objective frontier correctly shows that welfare, user cost, router
   revenue, quality, and viability need not select the same mechanism.
7. Negative results remain prominent: signal coupling changes correlation but
   not allocation, hardening fails a learning gate, and the public asymptotic
   contrast does not transport.
8. Documentation and reproducibility are excellent.

## Weaknesses

1. Entry profiles are enumerated in an outer task rather than learned jointly
   with continuous capacity investment and pricing.
2. The benchmark assumes independent delivered-capacity probability; correlated
   failure domains are likely important in real inference supply.
3. The suite still lacks recurrent, model-based, continuous-action, and
   population-based adversaries.
4. There is no independent settlement implementation or demonstrated
   PettingZoo/OpenSpiel reconciliation.
5. Public entry cost, bilateral contribution, capacity, and user value remain
   uncalibrated; the 21-versus-5 entry scenario is illustrative only.
6. The number of tasks risks diffusing the property-ladder message.

## Questions

1. Can an entry/capacity agent be trained against repeated pricing agents without
   destroying the exact common-random-number comparison?
2. How should common failure domains or shared upstream clouds enter the entry
   benchmark?
3. Can a second implementation reproduce settlement and outer-entry equilibria?
4. Which deviation families remain fully held out until final router selection?

## Overall assessment

**Score: 7/10 — Accept.**

The outer-stage entry task closes an important realism gap while preserving the
paper's strongest contribution: an executable standard for refusing unsupported
mechanism claims. It does not make the simulator a fitted replica, and the paper
says so. The information boundary, settlement invariants, adversarial suite,
negative transport evidence, and explicit entry layer together merit acceptance.

## Path to strong accept

- Train entry/capacity and pricing policies jointly in a two-timescale benchmark.
- Add correlated failure domains and capacity certificates.
- Reconcile one frozen scenario with an independent implementation.
- Add recurrent and continuous-action held-out agents.
- Calibrate entry-cost and reliability bounds from a provider-facing trial.
