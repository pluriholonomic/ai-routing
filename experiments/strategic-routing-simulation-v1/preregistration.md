# Strategic routing simulation v1 preregistration

**Frozen:** 2026-07-18, before reading any strategic-simulation result
**Status:** protocol and theorem benchmark frozen; no learned-policy result exists
**Scenario schema:** config/strategic_routing_v1.toml
**Execution plan:** docs/strategic-routing-simulation-execution-plan-2026-07-18.md

## Question

How do provider pricing and capacity incentives change when a router allocates
same-model requests using public price, reliability, and capacity signals?

The initial study separates:

1. an analytical fixed-demand pricing game;
2. a deterministic request-level simulation with capacity and failure;
3. later calibrated and learned-provider counterfactuals;
4. later executable-router conformance.

None is interpreted as realized market-wide OpenRouter flow.

## Analytical benchmark SM1

There are n >= 2 providers with identical positive marginal cost c. Demand is
one inelastic unit. Provider i posts p_i >= c. Its routing share is

    s_i = p_i^(-eta) / sum_j p_j^(-eta),

and profit is

    pi_i = (p_i - c) s_i.

Prices are bounded above by a common, exogenous cap P. The primary analytical
object is the symmetric pure-strategy equilibrium as a function of n, eta, c,
and P.

### Frozen claims to test

1. A finite unconstrained symmetric interior stationary price exists exactly
   when eta > n/(n-1).
2. Where it exists,

       p* = eta (n-1)c / [eta(n-1) - n].

3. With a common price cap, the symmetric equilibrium is the smaller of p* and
   the cap when p* exists, and the cap otherwise.
4. Under inverse-square routing, duopoly is the knife edge and binds the cap;
   three or more symmetric providers have a finite interior price when the cap
   is sufficiently high.
5. As entry grows without bound, p*/c approaches eta/(eta-1), not one.
6. With identical cost, quality, and inelastic demand, prices are transfers and
   the router rule has no allocative welfare content. Welfare conclusions
   require elastic demand, heterogeneous cost/quality, capacity, failure, or
   latency.

### Primary outputs

- equilibrium price and markup;
- cap-binding indicator;
- Lerner index;
- provider profit and consumer payment;
- numerical best-response error.

This is a mechanism result, not evidence of collusion.

## Deterministic vertical slice SM2

### Units

- one epoch is five minutes;
- one episode is 2,016 epochs;
- one market fixes model and workload;
- demand is an integer request count generated outside the kernel.

### Providers

The frozen fixture has two providers with heterogeneous cost, latency,
reliability, and capacity. These are synthetic types, not named firms.

### Router treatments

1. inverse price with eta = 2;
2. deterministic lowest cost;
3. uniform random.

### Provider strategies

1. static price;
2. cost plus;
3. author-reference anchor;
4. one-tick undercut with a margin floor.

### Primary outcomes

- transfer-free welfare per request;
- user utility;
- provider profit;
- success, failure, and fallback rates;
- latency;
- payment;
- concentration and served share;
- capacity rejections.

### Invariants and gates

- every request terminates once;
- no attempted service exceeds admitted capacity;
- route probabilities sum to one;
- fallback has no duplicate provider;
- user utility plus provider profit equals transfer-free welfare;
- inverse-square probabilities match orcap.routing_simulation fixtures;
- seeded replay is exact;
- focused tests and lint pass.

Any invariant failure blocks economic analysis.

## Initial mechanism experiments

### E1: exponent and entry

Provider count is 2 through 10. Eta is in {0.5, 1, 1.5, 2, 3, 4, 8}. Cost is
normalized to one. Caps are {2, 4, 10, 100}. The primary result is the
equilibrium markup surface and the cap-binding boundary.

### E2: capacity and reliability

Holding cost and demand draws fixed, compare inverse-square, lowest-cost, and
uniform routing under:

- spare versus scarce capacity;
- homogeneous versus heterogeneous reliability;
- low versus high failure loss.

Primary estimand: paired welfare difference under common random numbers.

### E3: Brown-MacKay clock asymmetry

This experiment is not run until the transparent fast-reaction strategy and
strict-prior information audit exist. One provider's update clock is varied
while cost, capacity, demand, and information are fixed.

Primary pattern: fast provider price lower and profit higher while slow-rival
prices rise. This is competitive commitment unless separate deviation and
coordination diagnostics support a stronger interpretation.

## Statistical protocol

Screening uses 10 simulation seeds and common random numbers. Promoted
simulation contrasts use at least 30 seeds and 50 held-out evaluation seeds.
The independent unit is a seed/calibration draw, never an epoch or request.
Paired intervals and sign-flip tests are reported; Holm correction is applied
within each experiment family.

Results must survive the declared cost, capacity, and demand bands. A sign that
changes inside the band is reported as an identified-set boundary.

## Claim boundary

The analytical result characterizes the stated game. The deterministic
simulation verifies accounting and mechanism behavior. Calibrated simulations
will be type-conditioned counterfactuals. Named-provider costs, capacity,
strategy, profit, collusion, front-running, and market-wide routing remain
unidentified without additional data.
