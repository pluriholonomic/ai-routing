# Adversarial NeurIPS review: price-score environment revision

## Summary

The submission presents a deterministic request-level multi-agent environment
for strategic inference routing. Providers choose price, admitted capacity, and
availability; routers order providers under several scoring rules; settlement
tracks fallback, cost, latency, user utility, provider profit, and welfare. The
paper requires property tests and transport gates before treating simulator
results as live-market claims. Its new focal task studies the interaction
between displayed-price manipulation and latent router scores. Evaluation
combines public price counterfactuals, a focal signal-coupling experiment,
one-step adversarial hardening, and learning-based deviation audits.

## Strengths

1. **The environment has a scientific refusal mechanism.** Private-information
   boundaries, stable common-random-number streams, transfer reconciliation,
   and explicit transport gates are enforced rather than described informally.
2. **The price-score task is economically meaningful.** The seven-model time
   series supplies real menu regimes; the simulator must separately match the
   sign and magnitude of the score-price interaction once owned-choice support
   exists. This is much sharper than fitting price histograms.
3. **Adversarial evaluation is broad.** Quote deviations, identity splitting,
   fading, unilateral grids, coalitions, and sequential learning attacks expose
   different vulnerabilities.
4. **The negative hardening result is important.** Reducing one-step quote gain
   from 0.226 to 0.030 and eliminating measured identity gain does not imply a
   robust market: normalized post-UCB exploitability becomes much worse. This
   is a valuable warning for learned mechanism design.
5. **The HMP-style intervention has exact nuisance preservation.** The positive
   focal UCB result and negative heterogeneous transport screen are both
   reported, avoiding a universal algorithmic-collusion claim.
6. **The environment card is unusually complete.** Agent observations, reward
   ownership, termination, randomness, known failures, and minimum reporting
   requirements are specified.

## Weaknesses

1. **The benchmark suite is not yet broad enough for a platform claim.** The
   most elaborate strategic results use a small set of learner families and
   stylized games. More continuous-action, policy-gradient, recurrent, and
   model-based agents would strengthen the NeurIPS case.
2. **The live latent score is not calibrated.** At the freeze the prospective
   panel has zero eligible choices. The environment therefore has a
   price-informed task but no score-informed live parameterization yet.
3. **The focal signal-coupling result uses only two seeds per factorial cell.**
   Pairing creates precision for the specified contrast, but it gives limited
   information about training instability and algorithm-seed interactions.
4. **The environment is custom rather than independently cross-implemented.**
   Strong internal invariants help, but an independent settlement implementation
   or interoperability benchmark would reduce correlated code-and-test risk.
5. **The welfare quantities are simulator primitives.** They are appropriate
   for mechanism comparison inside the environment but cannot be called
   externally calibrated while costs, delivered quality, and market-wide
   demand remain hidden.

## Questions for the authors

1. Which observation and action schema is minimally sufficient to reproduce the
   price-score task in PettingZoo or OpenSpiel?
2. Can the hardened router be optimized against a population of adversaries
   without overfitting to the exact deviation oracle used for training?
3. How will score uncertainty propagate into mechanism rankings once the paid
   panel crosses its gates?
4. Does the environment support provider entry, investment, and multi-model
   capacity coupling, or only within-episode operational choices?

## Requested improvements

- Add recurrent and continuous-action adversaries plus held-out deviation
  families.
- Cross-implement settlement for a frozen scenario and require byte- or
  tolerance-level reconciliation.
- Increase independent training seeds for the focal and heterogeneous learner
  screens.
- Treat the future score estimate as a distribution in simulator transport,
  not a plug-in point estimate.
- Add an outer-stage capacity-investment benchmark to connect provider
  technology to price behavior.

## Score

- Technical quality: 8/10
- Empirical grounding: 7/10
- Novelty: 8/10
- Reproducibility: 9/10
- Overall: **7/10, Accept**

## Decision

**Accept.** The combination of an inference-specific strategic environment,
property-tested accounting, adversarial mechanism audits, and explicit negative
transport results is a credible NeurIPS contribution. Strong accept would
require broader learner coverage and a mature live score calibration.

