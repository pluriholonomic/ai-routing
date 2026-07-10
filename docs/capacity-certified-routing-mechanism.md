# Capacity-certified routing: mechanism and empirical bridge

## Research question

Can an inference router obtain the price competition benefits of a
reliability-weighted RFQ aggregator without rewarding a provider for a cheap
quote that it cannot serve? The proposed mechanism adds a verifiable capacity
commitment and a deferred shortfall bond to the router's allocation rule.

This is the paper's mechanism-design core. It uses the DeFi comparison as a
discipline for what the router must internalize: RFQ last look and AMM adverse
selection both distinguish displayed liquidity from delivered liquidity.
Inference has the same issue when a low-priced provider captures allocation
and then rate-limits, deranks, or fails requests.

## Model

For provider `i`, let `p_i` be a posted per-request quote, `c_i` marginal
serving cost, `k_i` a committed request capacity for the epoch, and `q_i` a
router reliability score fixed before allocation. The router assigns a
first-route probability

`s_i = q_i p_i^{-eta} / sum_j q_j p_j^{-eta}`,

with `eta > 0`. Under OpenRouter's documented public proxy, `eta = 2` after
conditioning on public eligibility. Let `x_i` denote allocated requests and
`y_i <= x_i` requests actually served. Payment is made only for `y_i`; the
provider also loses `b_i (x_i-y_i)` from a deferred bond/holdback.

Provider payoff is

`(p_i-c_i)y_i - b_i(x_i-y_i)`.

The proposal does not assume that OpenRouter, Hugging Face, or another router
currently runs this mechanism.

## Propositions to prove under the stated reduced-form assumptions

1. **Price incentive.** Holding eligibility and reliability fixed,
   `d log(s_i) / d log(p_i) = -eta(1-s_i)`. H48 computes this algebraic
   benchmark from public simulated shares; it is not a realized elasticity.
2. **No deliberate quote-and-ration.** If a provider receives payment only for
   delivered requests and `b_i > max(0, p_i-c_i)`, deliberately refusing an
   otherwise serviceable allocated request is strictly dominated in the
   one-period model. This does not cover private costs, correlated outages,
   or a provider that cannot serve the request.
3. **Capacity feasibility.** A provider that commits `k_i >= x_i` can serve
   the allocation without bond loss. The practical design question is how to
   verify or insure `k_i`; the model makes that missing object observable
   rather than assuming it away.

The next theory step is to extend this one-period result to private capacity
and a stochastic health process, then prove an individually rational
reliability-adjusted scoring rule. It must compare welfare with (a) pure
cheapest routing and (b) a reliability-only rule.

## Empirical mapping and gates

| model object | measurement | current status |
|---|---|---|
| `p_i` | public provider quote for a fixed workload | observed every 5 minutes on OpenRouter; public Akash/Vast GPU quote panels now added |
| `s_i` | public inverse-square simulated share | observed proxy; H43/H45/H48 explicitly label it non-realized |
| `q_i` | uptime, error, latency, throughput, router scorecard | public proxy only; private live eligibility remains unobserved |
| `x_i, y_i` | allocated and served controlled-study requests | not identified until redacted `router_route_attempts` accumulate |
| `k_i` | provider/model/time commitment | not observed for inference; Akash/Vast capacity is an external supply comparator |
| `c_i` | realized GPU-seconds times cost | not observed; no profit or optimal-bond claim is permitted |

H48 is a calibration sheet rather than a fitted structural model. The bond
calibration gate requires per-provider/model/time capacity, allocated/served
counts, selected-provider telemetry, and serving cost or contribution margin.
Without all four, the paper may state a design proposal and reduced-form
comparative statics, but not an empirically calibrated optimal mechanism.

## EC paper path

The defensible contribution is a capacity-aware RFQ-routing mechanism with an
empirical test of its failure mode—not a claim that inference is an AMM. The
paper needs, at minimum:

1. four to eight weeks of endpoint quote, quality, and demand data, plus the
   H42/H43 event and route-surface power gates;
2. the matched Akash/Vast price-capacity panel and finalized DeFi execution
   comparator, both with strict instrument mapping;
3. a controlled redacted routing study sufficient to estimate shortfall and
   capacity-bond primitives; and
4. formal proofs of the proposition assumptions and welfare comparison,
   followed by out-of-sample counterfactuals that are visibly separate from
   the public-data screens.

Until those gates clear, label the result as a **pre-registered mechanism
proposal with partial public calibration**.
