# Adaptive monotone router: counterfactual and live design

Date: 2026-07-20
Endpoint-history revision: `7189386a9c14f35ce539ce1088cf3021dddf17f5`

## Result

The historical replay uses one menu per model-hour, collapses duplicate endpoints to
the cheapest endpoint per provider, and requires at least three providers with positive
prices and public 30-minute uptime. It covers 18,947 menus, 71 models, 48 providers,
and 14 calendar dates from 2026-07-07 through 2026-07-20 04:28 UTC.

The first 70% of dates select a rule from a frozen grid. Every candidate rule has shares

`s_i = (1 - epsilon) q_i p_i^(-eta) / sum_j q_j p_j^(-eta) + epsilon / n`,

where `p_i` is the quoted short-request cost and `q_i` is public 30-minute uptime. The
training constraint permits at most a 2% expected-quote premium and at most a 0.2
percentage-point public-uptime loss relative to `eta=2, epsilon=0`. The selected global
rule is `eta=1.25, epsilon=0.10`.

Equal-weighting model-day clusters on the 2026-07-16 through 2026-07-20 temporal
holdout gives:

| Quantity | Holdout effect | 95% model-day cluster bootstrap interval |
|---|---:|---:|
| Expected quote premium | +2.076% | [+1.510%, +2.934%] |
| Public uptime | +0.0059 pp | [-0.0017, +0.0147] pp |
| HHI | -0.0302 | [-0.0352, -0.0260] |
| Local cross-provider price gain | -49.30% | [-49.97%, -48.64%] |

The last row is the spectral norm of the off-diagonal part of the router's local
log-share/log-price Jacobian. It measures how strongly one provider's quote changes the
other providers' allocations under the rule. It is a policy-created feedback/coupling
index, not an estimate of collusion, provider response, or welfare.

The main conclusion is feasibility with a caveat. Lower price gain and lower
concentration are mechanically available at a small quote premium with no detectable
public-uptime loss. But the global rule's quote premium drifts just above the training
constraint on the holdout. A fixed rule therefore does not transport the 2% constraint
perfectly.

## Prospective paid test

The separate `openrouter-adaptive-monotone-v1` study starts no earlier than 2026-07-21
00:00 UTC. OpenRouter does not expose arbitrary routing weights, so each arm is emulated:
freeze a public menu, compute a probability vector, draw a provider with a recorded
seed and exact propensity, and pin the paid owned request to that exact endpoint with
fallbacks disabled.

Each launched model/shape block contains five arms:

1. `baseline_eta2`;
2. `calibrated_eta145`;
3. `independent_explore_eta2_eps10`;
4. `historical_cone_eta125_eps10`, the direct paid test of the replay result;
5. `cone_projected_menu_adaptive`, which re-solves the quote and uptime constraints on
   every public menu.

The no-spend 2026-07-20 preflight found 12 eligible blocks from 152 candidate endpoint
rows. It froze three blocks, 15 requests, and $0.00214 of conservative quote caps without
source failures. It also showed why both cone arms are necessary: the per-menu safety
projection bound at the eta-2 baseline on all three sampled menus, while the fixed
historical arm continued to provide a nontrivial allocation contrast.

The fixed horizon is the first 120 launched blocks (600 assignments). With three blocks
per scheduled run and four runs per day, the nominal duration is ten days. Assignment-
only preflights do not count. The live monitor withholds arm-specific outcomes until the
fixed horizon. Its final analysis is intention-to-treat: missing attempts inside a
launched block are failures with the preregistered 90-second bounded-latency penalty.

## What this can and cannot establish

The historical replay identifies mechanical quote, public-uptime, concentration, and
allocation-derivative effects holding provider behavior fixed. The paid study adds
realized success, latency, and cost for owned pinned requests. A favorable paid result
would support a feasible improvement for the sampled menus and loads.

Neither layer identifies user value, provider marginal cost, total demand, endogenous
repricing, dynamic equilibrium, collusion, or scalar social welfare. A welfare claim
still requires values/costs; a strategic-response claim requires a longer randomized
deployment in which providers can observe and respond to the allocation rule.
