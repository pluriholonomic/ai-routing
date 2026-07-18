# Adversarial review — "The Router Is the Demand Curve"

*Round 4, 2026-07-18. Venue lens: ACM EC main track, with a secondary
NeurIPS economics-and-learning lens. This review supersedes round 3 and
evaluates the ten-page PDF after the LiteLLM executable-router conformance
addition. Reviewed evidence includes E-SIM5--9, the SM4 conformance release,
the source/result manifests, and the complete repository test suite.*

## Recommendation

**Weak accept (6/10), confidence 5/5.**

I would accept this as a focused ACM EC paper about marketplace-induced
delayed credit and a path-equivalent learning interface. The exact theory,
registered falsifications, negative transport result, and executable selection
check make the narrow claim unusually auditable. I would not accept a broader
claim about live provider behavior, welfare optimality, collusion, or the
closed OpenRouter implementation. The paper does not make those claims.

## Central contribution

The paper identifies an economically meaningful distinction between rational
incentives and bounded-algorithm implementation:

1. A finite allocation penalty after a price cut can make every penalized
   period less profitable than remaining high while leaving the permanent cut
   optimal once the unpenalized continuation is counted.
2. The boundary between cut and stay is exact:
   gamma raised to M exceeds
   (u_H minus u_thetaL) divided by (u_L minus u_thetaL).
3. Adding a commitment option changes no feasible primitive price path and no
   exact provider value, but materially changes which path the frozen
   tabular-Q learner discovers.
4. The intervention is nonmonotone. It helps inside the delayed-credit region
   and overcommits after the rational optimum changes.

This is not a welfare theorem and not an equilibrium-selection result. It is a
finite-MDP mechanism result about how a router-imposed delay interacts with a
bounded provider algorithm.

## Evidence assessment

### Exact theory

The rational memory theorem is correct under the stated binary-price,
fixed-rival assumptions. Before reaching the all-low state, a high action
resets progress. Any eventual-cut policy is weakly improved to a sequence of
high actions followed by low forever, so immediate cut and never cut exhaust
the optimal choices. The resulting scalar comparison yields the claimed
boundary.

The option theorem is also exact. Every option is a finite sequence of
primitive low actions. Unrolling any augmented policy gives a primitive policy
with identical states and discounted rewards, while the augmented problem
retains every primitive action. Therefore the optimal values coincide.

The static markup statements are correctly limited to symmetric pure-strategy
equilibria, except for the provider-level interior markup floor. They are
classical differentiated-products economics and should remain supporting
structure rather than the novelty claim.

### Main simulation and falsifications

At the calibrated memory M=7, exact optimization cuts. Primitive Q achieves
the exact action with at most five percent normalized regret in 1/20 seeds;
the commitment-option learner does so in 18/20. The option-minus-primitive
regret contrast is -0.0643 with paired simulator interval
[-0.0755, -0.0493].

The important credibility checks are retained:

- the learned high-price path fails a persistent-deviation audit and is not
  labeled an equilibrium;
- full Markov-state observability does not repair the learning failure;
- the strict four-market transport gate fails and is reported as failed;
- all nine local Q-learning cells favor the option, but only seven satisfy the
  complete severity conjunction;
- an eight-step TD target does not improve on one-step Q, preventing a generic
  multi-step-credit claim.

These are strong research practices. The negative results materially narrow
the paper rather than being hidden.

### Executable-router conformance

The new SM4 suite addresses a previous implementation-validity objection.
Five stochastic states receive 10,000 selections each, 10,000 trials generate
complete three-provider fallback orders through sequential exclusion, and five
states test deterministic lowest-cost choice. All 25 rows pass. Every exact
probability lies inside a Clopper-Pearson interval Bonferroni-adjusted over the
20 stochastic cells. The maximum absolute discrepancy is 0.732 percentage
points, below the two-point gate.

The claim boundary is correct and necessary. Inverse-price scores are mapped
to LiteLLM deployment weights. Therefore SM4 validates that the surrogate
agrees with LiteLLM 1.92.0's executable filtering, weighted sampling,
sequential exclusion, and scalar lowest-cost selection under the adapter. It
does not show that LiteLLM or OpenRouter natively uses inverse-price weights.
Because no inference request is sent, it also does not validate queueing,
latency, failure recovery, or service-path fallback.

The source/result relationship is auditable: the conformance runner is frozen
at source commit 1e62de3, the report records LiteLLM 1.92.0, hashes both
executed selector functions, and hashes all release artifacts.

## Remaining weaknesses

1. The cut multiplier is a conditional owned-probe association from one buyer
   tier. Treating it as a router penalty is calibration, not randomized
   identification.
2. The main provider problem has two prices and fixed rivals. Endogenous
   multi-provider learning may alter the payoff ordering, memory boundary, and
   effect of commitment.
3. Twenty seeds identify Monte Carlo variation under one frozen simulator, not
   uncertainty in costs, capacity, demand, or the cut penalty.
4. The strict transport gate fails. The four-market sign pattern is
   descriptive and cannot carry a broad external-validity claim.
5. The successful algorithmic effect is specific to a semi-Markov commitment
   option. The failed eight-step target makes the boundary credible but leaves
   eligibility traces, recurrent function approximation, and deep RL open.
6. SM4 validates selection semantics, not the hidden production router or the
   serving system.
7. The paper derives provider value and regret, not global welfare. Demand,
   congestion, quality, and capacity are not identified tightly enough for a
   welfare-optimal-router conclusion.

These weaknesses limit scope; they do not contradict the theorem or the
reported finite-MDP effect.

## Venue judgment

For ACM EC, the paper now has the right shape: a public allocation rule as an
economic primitive, an exact dynamic boundary, a mechanism-preserving
intervention, explicit falsifications, immutable computational evidence, and
an executable open-source selection check. Its limitations are visible in the
abstract and main text.

For a standard NeurIPS main-track submission, the tabular algorithm and small
transport set remain borderline. A stronger NeurIPS version would need
endogenous multi-agent learning, at least one additional learner family, and
calibration-uncertainty transport. Those are not necessary to accept the
current EC contribution.

**Final recommendation: weak accept.** The paper is publishable as a narrow
mechanism-and-learning result. It should not be expanded into a claim about
market-wide welfare, provider conduct, collusion, or live-router causality
without new evidence.

