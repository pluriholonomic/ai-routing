# Adversarial ICML review: critical-memory price-score revision

## Summary

The paper analyzes a learner facing a routing score with finite memory. A
persistent low-price path can become optimal only after enough consecutive cuts
erase a score penalty. The paper separates a rational memory boundary from a
learning boundary: after exploration has decayed, proposing a fresh length-\(M\)
path has probability at most \(Tq^M\). A length-\((M+1)\) commitment option
preserves feasible primitive paths while changing discovery time from
exponential to linear in the relevant horizon. A calibrated finite MDP and
trace diagnostics test the mechanism. New public-menu time series calibrate the
economic size and duration of price regimes but are explicitly not used as a
live estimate of latent score memory.

## Strengths

1. **The paper isolates a genuinely different failure mode from low reward
   SNR.** Delayed path proposal and late temporal credit are not reducible to
   noisy one-step rewards. The stopping-time bound is clean and memorable.
2. **Rationality and learnability are separated.** The option can improve
   learning below the rational boundary and induce overcutting above it. This
   prevents the paper from making the usual claim that more exploration or
   temporal abstraction is uniformly beneficial.
3. **The diagnostic stack is excellent.** Exact dynamic programming, primitive
   Q-learning, option Q-learning, batch Bellman recovery, and fixed-trace credit
   tests distinguish optimization, discovery, and credit assignment.
4. **The price-score formulation improves external meaning.** A remembered
   score is now an effective-price penalty rather than an arbitrary state
   variable. The public time series shows realistic piecewise regimes and a
   highly dynamic GLM-5.2 case without pretending to estimate \(M\).
5. **Negative results are useful.** State observability, cross-market severity,
   and a conventional multi-step return do not pass the frozen screens. Those
   failures sharpen the claimed mechanism.

## Weaknesses

1. **The calibrated MDP is still small.** Exact control is a virtue for
   diagnosis, but the main theorem-to-practice bridge may change with continuous
   price actions, recurrent function approximation, or partial observability.
2. **The commitment option is a strong interface intervention.** In a live
   market it may create capacity or price commitments that are costly to cancel.
   The theory preserves action paths, not operational feasibility.
3. **No live memory parameter is identified.** The empirical time series
   calibrates regime durations and payoff magnitudes only. The prospective score
   panel is still empty at the freeze, so the temporal score mechanism remains
   a theoretically motivated simulator claim.
4. **The lower bound is on path proposal under a bounded cut probability.** It
   is not a general computational-complexity lower bound for all history-aware
   algorithms. The paper is careful about this, but the distinction should stay
   prominent.

## Questions for the authors

1. Does the result extend when the score memory is stochastic or exponentially
   weighted rather than a finite counter?
2. Can a recurrent policy learn an option-like representation without the
   explicit action interface, and what sample complexity would that require?
3. How sensitive is the rational boundary to state-dependent demand and
   capacity costs?
4. Could a router expose a cancellable commitment schedule that preserves the
   learning benefit while limiting overcutting above \(M^*\)?

## Requested improvements

- Add a continuous-action or recurrent-policy transport experiment.
- Report option value under stochastic memory resets and misspecified \(M\).
- When the live score panel matures, estimate only a bounded range of compatible
  memory lengths rather than a point estimate unless stronger instruments exist.
- Clarify which deployment costs would invalidate path-preservation as the
  relevant interface criterion.

## Score

- Technical quality: 9/10
- Empirical grounding: 7/10
- Novelty: 8/10
- Reproducibility: 9/10
- Overall: **8/10, Strong Accept**

## Decision

**Strong Accept.** The core contribution is the rational-versus-learning
boundary and the exponential late-path mechanism. The empirical panel is
properly used as calibration, so the still-pending live score estimate does not
undermine the central ICML claim.

