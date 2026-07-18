---
name: orcap-strategic-experiments
description: Use when designing, running, or interpreting strategic-routing simulation experiments E0-E10 — router mechanism benchmarks, Brown-MacKay clock asymmetry, provider-type and anchoring studies, stale-quote/phantom-liquidity tests, emergent-coordination diagnostics, welfare-optimizing-router Stackelberg runs, and entry/fragmentation studies. Covers treatment design, seed/statistical protocol, claim gates, and the screening-to-confirmatory promotion path.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orcap, simulation, experiments, marl, mechanism-design, statistics]
    related_skills: [orcap-market-env-kernel, orcap-simulation-calibration, orcap-router-conformance, orcap-experiment-audit]
---

# ORCAP Strategic Experiments

## Overview

The experiment suite (execution plan §12) compares theoretical models of the
inference marketplace as *router treatments x provider-strategy treatments*
inside one seeded kernel. Every experiment is a paired design under common
random numbers; the independent unit is the training seed or calibration draw,
never an epoch or request.

Protocol: experiments/strategic-routing-simulation-v1/preregistration.md
(frozen 2026-07-18). Amendments live beside it (e.g. the attempt-limit
amendment) and must state scope, reason, and that prior results stay
screening-only.

## Experiment map

| ID | Question | Treatments | Primary outcomes | Falsification / control |
|---|---|---|---|---|
| E0 | Does the env recover known benchmarks? | MC pricing, static Nash, joint-profit oracle, tabular learners | deviation regret | regret <= 0.05 in >=90% promoted seeds |
| E1 | Router mechanism benchmark | inverse-square, eta grid, lowest-cost, weighted-random, least-busy, P2C, capacity-certified, welfare oracle | welfare, payment, failure, latency, profit, HHI, PoA | low/base/high load x homo/hetero cost/capacity/reliability |
| E2 | Brown-MacKay clock asymmetry | vary one provider's observation/update clock, all else fixed | own price/profit/share, rivals' prices, consumer surplus | shuffle clocks; remove rival-price observability; simultaneous-only info |
| E3 | Price sensitivity / tick size | eta in {0,.5,1,2,4,8}; empirical + counterfactual ticks; deterministic vs stochastic | pass-through, markup, volatility, HHI, failure, welfare | where competition becomes winner-take-most capacity race |
| E4 | Reserved-capacity types | reserved-low-MC, elastic cloud, small fixed, mixed | price gap, utilization, peak markup, shortfall, entry/exit | bridge: held-out H19/capital-strata gaps = model fit, not causal proof |
| E5 | Author-price anchoring | anchor, cost-plus, undercut, fast reactor, mixtures | profit, survival, dispersion, response to reference shock | placebo reference prices; post-epoch reference changes |
| E6 | Stale quotes / phantom liquidity | quote TTL, delayed refresh, post-route admission prob, fallback policy, derank | quoted vs attempted vs served share, fallback cost, adverse selection | owned route attempts + enforcement aggregates; no market-wide-flow claim |
| E7 | Emergent coordination | independent PPO/SAC sellers x router rules | collusion index, deviation gain, exploitability, impulse response, punishment depth | see claim gate below |
| E8 | Welfare-optimizing router | Stackelberg: router commits weights, providers respond | held-out user welfare s.t. participation/reliability/latency/capacity constraints | test against unseen strategies, costs, capacities, demand regimes |
| E9 | Entry and fragmentation | provider count, setup cost, reserved capacity, cache fragmentation | welfare, price, concentration, cache hit rate, survival | region where entry stops helping |
| E10 | Model-provider interaction | fixed model demand; RouteLLM-style quality-cost routing; joint routing | quality-adjusted utility, model concentration, provider competition | model routing vs provider procurement reported separately |

## Statistical protocol

**Screening** (implementation check only — never publish p-values):
10 training seeds, 20 evaluation seeds/policy, 5 calibration draws, common
demand/failure draws across router treatments.

**Confirmatory** (promoted contrasts):
30 training seeds, 50 held-out evaluation seeds, 20 calibration
posterior/bootstrap draws, >=3 demand regimes, 2 model-family holdouts.

Report: mean and median paired effect; percentile + studentized bootstrap
intervals over independent seeds; randomization/sign-flip p-values where the
paired design supports them; Holm correction within each preregistered
experiment family; full distribution and sign stability, not only a p-value.

Uncertainty decomposition: demand/process, RL training, calibration,
private-cost/capacity identified set, executable-router approximation error.
A result is robust only if its sign survives the prespecified cost/capacity
band; otherwise report the sign-change boundary.

## Learning gates (WP4)

Training ladder: (1) 2 providers, price only, tabular Q; (2) 2 providers,
price+capacity, independent tabular/Q-net; (3) 4 providers, discrete grid,
independent PPO; (4) continuous quote/capacity, PPO+SAC; (5) recurrent only
if delayed/noisy state improves held-out reward; (6) router-as-leader only
after provider best-response tests pass.

Reward is discounted economic profit. Routed share is logged, never the
default reward; run a separate intentionally misspecified share-reward
treatment to measure reward hacking.

Sanity gates: learned beats static init on validation profit; tabular recovers
2-provider benchmarks; scripted one-step best response improves reward when
regret is positive; random provider relabeling leaves symmetric scenarios
invariant; conclusions survive >=2 learning algorithms.

## E7 coordination claim gate (all required)

High prices alone never count. A coordination claim requires: supra-competitive
prices, low equilibrium regret, profitable-deviation dynamics consistent with
punishment/restoration, replication across algorithms, and survival under
provider relabeling. The joint-profit oracle never appears in a decentralized
treatment.

## Claim boundaries (apply to every experiment)

- Simulation outputs are synthetic evidence: conditional mechanism
  counterfactuals, not realized OpenRouter flow, not proof of observed
  collusion or front-running, not named-provider private costs/strategies.
- E2 support patterns are labeled competitive commitment, not collusion.
- Empirical bridges (E4, E6) are model-fit statements, not causal proof.
- Amendments after a first run keep prior outputs screening-only; never
  silently overwrite generated files outside the working analysis directory.

## Stop/go rules

Stop and repair: accounting/capacity invariant failure; held-out calibration
worse than transparent nulls; learned results vanish under relabeling; adapter
disagreement beyond conformance threshold; apparent collusion with large
profitable unilateral deviations; conclusions depending on one seed,
algorithm, model, or unreported cost point.

Promote: invariant + calibration + conformance + equilibrium + robustness
gates pass; frozen holdouts and private-primitive sensitivity survive; effect
has economic magnitude; paper language matches the actual evidence object.
