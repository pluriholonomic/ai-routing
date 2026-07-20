# Adaptive-router adversarial screening protocol

**Drafted:** 2026-07-20 before the first local screening run. Because the protocol
was not yet in an immutable commit when screening began, this is not claimed as a
confirmatory preregistration. Iterative attack results were used to repair the
operator-cap, dimensional-price-response, trust-region, and quote-lock semantics.

**Study ID:** `adaptive-router-adversarial-v1`  
**Configuration:** `config/adaptive_adversarial_v1.toml`  
**Full design:** `docs/adaptive-router-adversarial-validation-plan-2026-07-20.md`

## Question

Does the adaptive monotone router reduce its sensitivity to strategic quote,
capacity, and identity manipulation relative to inverse-square routing while
preserving its mechanical diversification benefit?

This first release is explicitly **screening**, not confirmatory. It may select one
hardened policy for a later fixed test, but its intervals and adversarial rankings
cannot be promoted as preregistered confirmatory evidence.

## Historical population

Use one immutable revision of `t4run/openrouter-market-history`. Construct one
menu per model-hour with the existing adaptive-counterfactual inclusion rules:
successful endpoints, positive prompt and completion prices, positive public
30-minute uptime, the cheapest exact endpoint per provider, and at least three
providers.

The screening replay uses a deterministic hash-ordered prefix of at most 5,000
menus. The later confirmatory protocol must use a new, untouched temporal and
model-family split rather than recycling the screening menus as a test sample.

## Router treatments

1. inverse-square baseline;
2. fixed `eta=1.25`, ten-percent exploration;
3. contemporaneous per-menu constraint projection;
4. hardened projection using leave-one-provider-out parameters, ten-percent
   exploration floor, a one-sided 1.5x allocation-gain trust region, 60%
   operator cap, and a quote lock within each commitment epoch.

The hardened historical replay tests a one-epoch perturbation relative to the
unattacked allocation. The strategic simulator additionally advances lagged and
committed state.

## Historical attacks

For at most the four highest-baseline-share providers on each menu, multiply one
quote by each value in
`{0.60,0.75,0.90,1.00,1.01,1.05,1.10,1.25,1.50}`. Report maximum
allocation gain and maximum profit gain when marginal cost is 25%, 50%, or 75%
of the incumbent quote. Also report:

- traffic captured by a cheapest-provider 25% quote-fading attack;
- combined allocation gain when that provider creates a second endpoint identity;
- model-day cluster-bootstrap paired differences from inverse-square routing.

Profit is a cost-band sensitivity, not a named-provider estimate.

## Strategic simulation

Sample up to 200 historical menus. Retain at most four providers. Cross the three
cost fractions with scarce, balanced, and spare capacity. On every cell and
router treatment, run:

- a complete declared unilateral quote/capacity grid;
- a complete declared two-provider joint quote grid;
- forty rounds of sequential global grid best responses on the first eight menus;
- independent UCB pricing agents for ten seeds and 2,000 epochs on those menus;
- a three-provider Calvano-style tabular-Q benchmark for ten seeds and at most
  100,000 epochs.

The deviation grid is global only relative to its declared finite actions. A
nonpositive deviation gain does not prove equilibrium outside that class.

## Primary screening quantities

- mean and 95th-percentile normalized unilateral exploitability;
- mean and 95th-percentile normalized two-provider exploitability;
- post-UCB unilateral exploitability;
- Q-learning convergence and the bounded Calvano delta;
- historical maximum allocation and cost-band profit gains;
- quote-fading captured share and sybil combined-share gain.

All intended policies and cells are published. Nonconvergent learner runs remain
in the denominator.

## Claim boundary

This protocol measures mechanical attacks on public historical menus and bounded
strategic behavior inside an explicit simulator. It does not identify actual
provider costs, strategies, market-wide flow, causal provider response,
equilibrium, collusion, or scalar welfare. The existing 120-block paid adaptive
study remains separate and unchanged.
