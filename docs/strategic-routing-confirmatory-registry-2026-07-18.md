# Strategic-routing confirmatory experiment registry

Registered 2026-07-18 after E-SIM1 passed its descriptive-moment gate and
before any confirmatory E-SIM2--E-SIM4 run. A two-seed E-SIM3 engineering
screen had already been inspected; its values are disclosed below and it is
not confirmatory evidence.

## Frozen environment

- Calibration bundle: `e292f3ed41c5`.
- Router baseline: allocation weight proportional to `price^-eta`.
- Provider action grid: 15 log-spaced prices from 0.4 to 1.6, including 1.0.
- Marginal cost: 0.2 in normalized units.
- Confirmatory seeds: integers 0 through 19, transformed only by the frozen
  experiment code.
- Learner: memory-one tabular Q-learning, alpha 0.15, gamma 0.95,
  exploration `exp(-2e-5 t)`, at most 300,000 training epochs.
- No LLM-agent result is confirmatory in this round.

All confirmatory manifests must report the market-environment source hash.
Any code correction after outcomes are inspected requires a dated amendment
and a complete rerun under a new experiment ID.

## E-SIM2: learner substitution

One Q-learner replaces, in turn, the adopter, static discounter, active
undercutter, and premium-provider slot in the calibrated five-species world.
The other strategies remain scripted. Demand is stationary because replay
demand is not a valid learning environment.

Primary outcomes:

1. distribution of learned behavioral class across 20 seeds;
2. median price relative to the author anchor;
3. changes per evaluation epoch over a frozen 56-epoch evaluation.

This experiment is descriptive. There is no directional significance claim;
its role is to test whether fitted species are plausible attractors for a
profit learner.

## E-SIM3: router price-sensitivity sweep

Three symmetric Q-learners interact under `eta` in `{0,1,2,4,8,32}`.

Primary hypothesis: the paired mean terminal price is weakly decreasing in
`eta`; report all adjacent paired differences with percentile bootstrap 95%
intervals and the Spearman rank correlation across the six arm means.

Secondary outcome: Calvano's collusion index where the grid Nash and cartel
benchmarks differ. An arm is interpretable only if at least 16 of 20 seeds
meet the frozen policy-stability criterion. Nonconverged seeds remain in the
intention-to-simulate price estimate and are separately flagged.

Engineering screen already seen: two seeds gave mean prices 1.475, 1.300,
0.867, 0.590, 0.400, and 0.400 as `eta` increased. Only two seeds had defined
collusion indices at `eta` 2--32. These values motivated no change in the arm
set, thresholds, learner, or primary outcome.

## E-SIM4: empirically calibrated cut penalty

The active-undercutter slot is replaced by a learner. Compare the baseline
inverse-square router with a stateful router that multiplies a recent cutter's
allocation weight by 0.17 for seven epochs. The 0.17 value is fixed from the
public-probe ratio `0.039/0.233`; it is not tuned in simulation.

Primary estimand:

    mean_seed[median learner price with penalty
              - median learner price without penalty].

Secondary estimands are the paired change in learner repricing rate and mean
market price. Report paired bootstrap 95% intervals over the 20 common seeds.

Directional hypothesis: penalizing recent cuts weakly raises the learned
price and weakly lowers repricing. A publishable causal statement is limited
to the simulated mechanism. The live-market implication remains a calibrated
counterfactual because the public data do not identify the proprietary
router's full state or assignment rule.

## Required equilibrium and collusion audits

For every learned terminal profile:

- compute the best one-shot unilateral deviation on the full price grid;
- report the fraction with deviation gain below 5% of mean profit;
- run a forced 20% rival-cut response and classify match, ignore, or
  punish-and-revert;
- never label elevated prices as collusion unless both the deviation and
  off-path punishment conditions hold.

## Stop/go rule

Proceed to an executable-router experiment only if E-SIM3 has adequate
convergence and E-SIM4's primary interval excludes zero. Otherwise report the
result as a simulator/method contribution and redesign the learner or steering
rule in a dated exploratory branch; do not relabel a null result.

## Post-result audit amendment 2026-07-18

E-SIM4 put the learner at the upper price-grid boundary in every penalty-on
seed. Before interpreting that result, a restricted multi-period deviation was
added: cut permanently to each lower grid price, bear the frozen seven-period
allocation penalty, then receive the unpenalized allocation forever. This is
an equilibrium falsification audit, not a new outcome or threshold change.
A positive gain requires the high-price state to be labeled a learning trap,
not equilibrium behavior. The original E-SIM4 bundle remains archived; the
audited rerun uses the same seeds, learner, arms, and horizon.

## E-SIM5 preregistration: observable router state versus state aliasing

Registered 2026-07-18 after the E-SIM4 permanent-cut audit and before any
E-SIM5 outcome was generated. E-SIM5 is a new mechanistic experiment, not a
post-hoc reinterpretation of E-SIM4.

### Question and controlled environment

E-SIM4's learner observes `(own price, cheapest-rival price)`, but the cut
router conditions allocation on the preceding seven own quotes. The learner's
state is therefore non-Markov. E-SIM5 isolates that state-information channel
with one provider facing fixed rival quotes and the same inverse-square router,
cut multiplier `theta=0.17`, memory `L=7`, marginal costs, and discount factor
`gamma=0.95` used in E-SIM4.

For each E-SIM4 penalty-on seed, freeze its terminal quote profile. Let `H` be
the learner's terminal high quote and let `l* < H` be the best permanent cut
from the already specified permanent-cut audit. The controlled action set is
exactly `{l*, H}`. This restriction makes the router state the last seven
binary actions, so all `2^7=128` histories can be enumerated without an
approximation.

### Frozen arms and seeds

The confirmatory seeds are integers 0 through 19. Each frozen terminal profile
is evaluated in three arms:

1. `exact_markov`: value iteration on the 128-state discounted MDP;
2. `history_aware_q`: tabular Q-learning observes the full seven-action
   history;
3. `aliased_q`: tabular Q-learning observes only the most recent own action.

Both learning arms use identical common random numbers, `alpha=0.15`,
`gamma=0.95`, exploration `exp(-2e-5 t)`, 300,000 training steps, the same
initial all-high history, and a 10,000-step greedy evaluation. No reward,
action, state, or seed tuning is permitted after inspection.

### Estimands and hypotheses

The primary estimand is the paired seed mean

    median_price(history_aware_q) - median_price(aliased_q).

Report a paired percentile-bootstrap 95% interval. The directional hypothesis
is negative: observing the penalty history lowers the learned price. Secondary
estimands are low-action share, discounted regret from the initial all-high
history relative to `exact_markov`, policy-stability convergence, and the
fraction of seeds in which the learned first action agrees with the exact
optimum.

The exact benchmark must report the Bellman residual and its deterministic
policy from every history. An implementation is valid only if the residual is
at most `1e-10` and an independently enumerated permanent-low value agrees with
the closed-form restricted deviation value to `1e-10`.

The state-aliasing mechanism gate passes only if all of the following hold:

1. the exact optimum cuts from the all-high history in all 20 profiles;
2. the upper endpoint of the primary paired interval is below zero;
3. at least 16 of 20 history-aware learners choose the exact first action;
4. at least 16 of 20 history-aware learners have normalized discounted regret
   at most 5%; and
5. at least 16 of 20 aliased learners choose high initially and choose low in
   at most 10% of greedy evaluation periods.

These thresholds are frozen before E-SIM5 execution. Failure of any component
must be reported; components may not be silently replaced by a composite score.

### Interpretation gates

- If the exact optimum cuts but both learners stay high, the evidence supports
  bounded-learning failure but not a state-aliasing mechanism.
- If the exact optimum and history-aware learner cut while the aliased learner
  stays high, the evidence supports a router-state-aliasing mechanism in this
  controlled MDP.
- If both learners cut, E-SIM4's trap is not attributable to missing router
  history alone; interaction with the 15-action grid or nonstationary rivals
  remains the leading explanation.
- A price difference without low regret and first-action agreement is not
  sufficient for the state-awareness claim.
- No outcome licenses the words collusion, equilibrium, causal live-router
  effect, or provider conduct. The estimand concerns bounded learners in a
  calibrated counterfactual mechanism.

## E-SIM5 frozen result

Run `6c2a3b6a52` executed the registered 20-seed design. The exact optimizer
cuts in 20/20 profiles and has Bellman residual below `9.4e-14`. The aliased
learner remains high in 20/20 profiles. Crucially, the full-history learner
also remains high in 19/20 profiles: its exact-first-action and low-regret gates
are each 1/20. The primary history-aware-minus-aliased median-price contrast is
`-0.0472`, paired bootstrap 95% interval `[-0.1416, 0]`.

The state-aliasing gate therefore fails. Missing router history is neither a
necessary nor sufficient explanation of the E-SIM4 high-price path in this
controlled reduction. The surviving mechanism is a delayed-credit problem:
even with the Markov state, primitive one-step exploration rarely learns to
bear seven low-payoff cut periods to reach the higher steady low-price reward.
This is a new hypothesis and requires a separately registered intervention.

## E-SIM6 preregistration: temporal abstraction and delayed price cuts

Registered 2026-07-18 after E-SIM5 was frozen and before any E-SIM6 outcome was
generated. E-SIM6 retains the exact E-SIM5 profiles, rewards, discount factor,
binary primitive actions, initial all-high history, seeds 0--19, 300,000
environment transitions, and 10,000-transition greedy evaluation.

### Arms

1. `primitive_q`: the E-SIM5 full-history Q-learner, rerun from scratch;
2. `commit_option_q`: the same full-history learner with one additional
   temporally extended action, `commit_low`, which executes `L+1` consecutive
   low quotes and receives the exact discounted semi-Markov return.

Exploration in both arms is `exp(-2e-5 t)` indexed by environment transition,
not by decision, so a macro action does not receive an artificially slower
exploration schedule. Both use `alpha=0.15` and `gamma=0.95`. Training stops
only after exactly 300,000 environment transitions. A final macro action may
be truncated to the remaining transition budget, in which case its update uses
the executed duration and rewards only.

The option does not change the feasible primitive price paths. The exact
semi-Markov value with the option must equal the primitive-action exact value
at every one of the 128 histories to `1e-10`; otherwise the implementation gate
fails and no learning result is reportable.

### Primary and secondary estimands

The primary estimand at the calibrated `L=7` is the paired seed mean

    normalized_regret(commit_option_q) - normalized_regret(primitive_q),

with a paired percentile-bootstrap 95% interval. The directional hypothesis
is negative. Secondary outcomes are median price, low-action share, first-action
agreement with the exact optimizer, policy stability, and commit-option use.

A frozen memory sweep uses `L in {1, 3, 5, 7, 9, 12}` with the same 20 seeds,
prices, rewards, transition budget, and learning parameters. It is descriptive
mechanism evidence. Report escape rates and normalized regret for every arm and
memory; do not fit or select a breakpoint.

### Mechanism gate and interpretation

The delayed-credit intervention gate passes only if, at `L=7`:

1. exact primitive and option values agree everywhere to `1e-10`;
2. the primary interval's upper endpoint is below zero;
3. at least 16/20 option learners choose the exact initial cut;
4. at least 16/20 option learners have normalized regret at most 5%; and
5. at most 4/20 primitive learners meet both conditions 3 and 4.

Passing supports this statement only: in the controlled calibrated MDP, a
history-dependent allocation penalty creates a delayed-credit barrier for a
primitive-action Q-learner, and a payoff-equivalent commitment option removes
that barrier. It does not show collusion, rational equilibrium pricing, a live
router effect, or actual provider learning. If the gate fails, report that
temporal abstraction is insufficient and do not tune the option or horizon.

## E-SIM6 frozen result

Run `4ab122a67d` passes all five registered gates. At calibrated memory `L=7`,
the option-minus-primitive normalized-regret contrast is `-0.0643`, paired
bootstrap 95% interval `[-0.0755,-0.0493]`. Exact primitive and option values
agree at every state within `1e-10`; 18/20 option learners meet the exact-action
and low-regret criterion versus 1/20 primitive learners.

The frozen memory sweep is nonmonotone in the economically predicted way.
Primitive and option learners both succeed at `L=1,3,5`. At `L=7`, exact
optimization still cuts, primitive learning fails in 19/20 seeds, and the
option succeeds in 18/20. At `L=9`, exact optimization still cuts; primitive
learning fails in 20/20 and the option succeeds in 16/20, although its mean
regret advantage is no longer positive because its failures are costly. At
`L=12`, the exact optimizer stays high; primitive learning agrees in 20/20,
whereas the option often overcommits and raises normalized regret by `0.0942`
on average, 95% interval `[0.0735,0.1160]`.

Thus the result is not "options always improve learning." It identifies an
intermediate implementation gap: a rational provider pays the finite penalty
and cuts, while a primitive-action learner does not. Temporal abstraction
closes that gap at the calibrated memory but can worsen behavior after the
rational cut threshold. That nonmonotonicity is part of the result and must
remain in every manuscript presentation.

## E-SIM7 preregistration: cross-market payoff transport

Registered 2026-07-18 after E-SIM6 was frozen and before any E-SIM7 outcome was
generated. E-SIM7 asks whether the delayed-credit intervention transports from
the stylized E-SIM4 profile to all four markets in the frozen calibration
bundle `e292f3ed41c5`.

For each market, take the most-undercutting provider slot already fixed by
E-SIM4b. Set the high action to the archived broad-penalty terminal quote
(`1.6` times that market's author anchor), hold every rival at its frozen
calibration-bundle quote, and use the slot's frozen marginal-cost rule. On the
15-point price grid, define the low action as the lower quote with the greatest
seven-period permanent-cut value. This selection uses exact payoffs only and
occurs before either E-SIM7 learner runs. All four markets remain in the panel
regardless of their rational action or effect sign.

Each market receives the E-SIM6 primitive and commit-option arms with seeds
0--19, `theta=0.17`, `M=7`, `gamma=0.95`, 300,000 environment transitions,
10,000-transition evaluation, and unchanged learning parameters. Exact
primitive and semi-Markov values must agree at every history to `1e-10`.

A market is *delayed-credit eligible* when `u_L>u_H>u_theta_L` and the exact
initial action is low. Report eligibility before learned outcomes. For every
market report the paired option-minus-primitive normalized-regret interval,
exact-action/low-regret success counts, prices, and the theoretical `M*`. There
is no four-market pooled p-value.

The transport gate passes only if at least three of four markets are eligible
and, in every eligible market: (i) the regret interval is strictly negative;
(ii) at least 16/20 option learners match the exact first action with at most 5%
regret; and (iii) at most 4/20 primitive learners do both. Ineligible markets
are retained as negative controls but do not enter that conjunction. Failure
must narrow the paper to the stylized calibrated profile; no market may be
dropped or reweighted after inspection.

## E-SIM7 frozen result

Run `621bfcd40c` fails the registered transport gate. Only two of four markets
are delayed-credit eligible, below the required three. In the eligible Kimi
and GLM-5.1 books, the option lowers normalized regret by `0.1777` (95%
interval `[0.0805,0.2749]`) and `0.1179` (`[0.0319,0.2152]`) respectively,
with option success 19/20 in both. But primitive success is 12/20 and 14/20,
well above the preregistered at-most-4 severity threshold.

The two ineligible books are informative negative controls. Their rational
memory boundaries are 2.586 and 2.670, below the imposed memory seven; exact
optimization stays high, primitive learning agrees in 20/20, and the option
*increases* regret by `0.1552` and `0.1520` with intervals strictly above zero.
In the two eligible books the boundaries are 26.307 and 27.906, exact
optimization cuts, and the option effect reverses sign. Thus all four effect
signs align with the ex ante rational-boundary classification, but the severe
primitive-learning failure does not transport. The paper may report this as
descriptive theory-aligned sign transport and must state that the confirmatory
transport gate failed.

## E-SIM8 preregistration: learning-hyperparameter robustness

Registered 2026-07-18 after E-SIM7 was frozen and before any E-SIM8 outcome was
generated. E-SIM8 returns to the audited E-SIM6 profile at `M=7` and varies the
two Q-learning parameters that directly govern credit propagation and
exploration: `alpha in {0.05,0.15,0.30}` and exponential exploration decay
`beta in {1e-5,2e-5,4e-5}`. Every one of the nine cells runs both primitive and
commit-option arms with seeds 0--19, `gamma=0.95`, 300,000 environment
transitions, and 10,000-transition evaluation. The reward, state, option,
initial history, and exact benchmark are unchanged.

For each cell report the paired option-minus-primitive normalized-regret
interval and both exact-action/low-regret success counts. The robustness gate
passes only if at least seven of nine cells have: (i) a strictly negative regret
interval, (ii) option success at least 16/20, and (iii) primitive success at
most 4/20. Report the complete 3-by-3 grid even if the gate fails. This is a
local algorithmic-robustness test around tabular Q-learning, not evidence for
deep RL, LLM agents, or actual provider algorithms.

## E-SIM8 frozen result

Run `4d84b9b3a2` passes the registered robustness gate in seven of nine cells.
All nine option-minus-primitive regret intervals are strictly negative; mean
improvements range from `0.0264` to `0.0680` normalized-regret units. Option
success is 18/20 or 19/20 in every cell. The two failed cells are
`alpha=0.30` with `beta=1e-5` and `2e-5`: primitive success rises to 12/20 and
6/20, above the at-most-4 severity threshold, while the option remains 19/20
and its regret interval remains negative. Thus the intervention effect is
locally robust across the full grid, while the severity of primitive delayed
credit depends on learning rate as expected.
