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

### Capacity-certified allocation

For epoch demand `D`, define the score weight `w_i=q_i p_i^{-eta}`. Instead of
first assigning `D s_i` and checking capacity afterward, the proposed rule
chooses

`x_i = min(k_i, tau w_i)`,

where `tau` makes `sum_i x_i = D` whenever total eligible commitment covers
demand. This is capped score water-filling. If `sum_i k_i < D`, it allocates
all committed capacity and reports `D-sum_i x_i` as unfilled demand; it never
creates a fictional assignment above a commitment.

For `D <= sum_i k_i`, the allocation is the unique solution of the strictly
concave entropy-regularized score problem

`max_x sum_i x_i log(w_i) - sum_i x_i log(x_i)`

subject to `sum_i x_i=D` and `0 <= x_i <= k_i`. The KKT conditions give the
water-fill form above. This is a mathematical link to score-based liquidity
allocation, not a claim that inference routing is an AMM or that it inherits
AMM welfare results.

## Propositions to prove under the stated reduced-form assumptions

1. **Price incentive.** Holding eligibility and reliability fixed,
   `d log(s_i) / d log(p_i) = -eta(1-s_i)`. H48 computes this algebraic
   benchmark from public simulated shares; it is not a realized elasticity.
2. **No deliberate quote-and-ration.** For a feasible assigned request,
   delivering rather than deliberately refusing it changes provider payoff by
   `p_i-c_i+b_i`. The exact strict condition is `b_i > c_i-p_i`; with
   non-negative bonds, `b_i > max(0, c_i-p_i)` is a simple sufficient rule.
   If `p_i>c_i`, a zero bond already strictly prefers delivery; if `p_i=c_i`,
   an arbitrarily small positive bond breaks the tie. The bond must be posted
   in enforceable collateral before allocation. This one-period result does
   not cover private costs, limited liability, correlated outages, or a
   provider that cannot physically serve the request.
3. **Capacity feasibility.** A provider that commits `k_i >= x_i` can serve
   the allocation without bond loss. The practical design question is how to
   verify or insure `k_i`; the model makes that missing object observable
   rather than assuming it away.
4. **No commitment over-allocation.** Under capacity-certified water-filling,
   `x_i <= k_i` for every eligible provider. If aggregate commitment covers
   demand, all demand is allocated; otherwise the residual is measured as
   unfilled instead of attributed to a provider. The code-level
   `allocation_counterfactual` reports the mechanical shortfall that an
   uncapped inverse-price rule would have assigned beyond commitments.
5. **Deliverable-count dominance over uncapped allocation.** With hard
   commitments, equal value per request, and delivery whenever an allocation
   is within commitment, an uncapped score rule delivers
   `sum_i min(D s_i, k_i)`. Capacity-certified water-filling delivers
   `min(D, sum_i k_i)`, which is weakly larger because no allocation is wasted
   above a commitment. `allocation_counterfactual` reports the resulting
   mechanical delivery gain. This is not a general welfare theorem: it does
   not value latency, quality, heterogeneous requests, strategic prices, or
   capacity-acquisition cost.
6. **Cost-reporting menu, conditional DSIC and IR.** As an alternative to a
   posted-price surface, fix hard committed capacity and the pre-allocation
   reliability score, and let a provider directly report positive marginal
   cost `r_i` in `(0,cbar]`. Apply the same capped score rule with
   `w_i=q_i r_i^{-eta}`. Its own allocation `x_i(r_i)` is weakly decreasing in
   its report. The procurement transfer
   `T_i(r_i)=r_i x_i(r_i)+integral_{r_i}^{cbar} x_i(z) dz` makes truthful cost
   reporting dominant and gives the `cbar` type zero utility, conditional on
   delivery. `procurement_payment` numerically evaluates the transfer and
   `procurement_report_diagnostic` audits the envelope on a report grid. This
   is a direct-revelation benchmark, not a claim that public router quotes are
   private costs, a budget-balanced mechanism, or a solution to private
   capacity.

The next theory step is to extend this one-period result to private capacity
and a stochastic health process, then prove an individually rational
reliability-adjusted scoring rule. It must compare welfare with (a) pure
cheapest routing and (b) a reliability-only rule.

### Proof details and assumptions

The reduced form makes four assumptions that the empirical section must test
or maintain as explicit design requirements: (i) payment `p_i` is due only for
delivery, (ii) a feasible delivery has incremental cost `c_i`, (iii) the
shortfall bond is fully collateralized and collectible, and (iv) the provider
does not obtain an external benefit from refusing an otherwise feasible
request. For one assigned feasible request, delivery yields `p_i-c_i` and
deliberate refusal yields `-b_i`; their difference is `p_i-c_i+b_i`. This
proves the condition above. It is a delivery-incentive proposition, not a
truthful-capacity-reporting theorem.

For the allocation proposition, set `w_i=q_i p_i^{-eta}` and consider
positive-weight providers. The derivative of the entropy-regularized objective
is `log(w_i)-log(x_i)-1`. KKT stationarity therefore gives
`x_i=tau w_i` for an uncapped provider and `x_i=k_i` for a capped one, hence
`x_i=min(k_i,tau w_i)`. The left side is continuous and nondecreasing in
`tau`, so there is a unique allocation when `D <= sum_i k_i`; if aggregate
commitment is lower, allocating each `k_i` leaves the residual explicitly
unfilled. This proves feasibility conditional on verified commitments, not
truthful commitment revelation or optimality under private information.

For the deliverable-count result, an uncapped allocation has feasible delivery
`min(Ds_i,k_i)` at each provider. Any allocation has at most both total demand
`D` and total hard capacity `sum_i k_i`, while the water-fill rule attains that
upper bound by assigning no unit above `k_i`. It therefore weakly maximizes
delivered request count in this equal-value reduced form. The result stops at
request count; a welfare comparison needs observed quality and cost terms.

There is one narrower reporting result. Suppose a provider's physical capacity
is a hard `K_i`, it reports `k_i`, price and reliability are held fixed, and a
fully collectible `b_i>0` applies to every unserved assigned request. If it
reports `k_i>K_i`, it cannot increase served quantity above `K_i`: when the
truthful cap is slack, raising it does not change the water-fill allocation;
when it binds, any additional allocation is unserved and loses the bond.
Thus over-reporting is weakly unprofitable and strictly worse whenever it
creates extra unserved allocation. The code-level `declared_capacity_payoff`
checks this counterfactual. This is **not** full truthful-reporting
implementation: endogenous capacity investment, limited collateral, private
reliability, correlated outages, and price/reliability manipulation still need
a Bayesian mechanism and empirical inputs.

For the cost-only menu, hold the provider's certified capacity, all other
reports, and reliability scores fixed. Reducing `r_i` raises only its positive
score `q_i r_i^{-eta}`. The capped water-fill allocation is weakly increasing
in that score (a cap can flatten the response but cannot reverse it), hence
`x_i(r_i)` is weakly decreasing in the cost report. For a true cost `c_i`,
the utility from report `r_i` under the stated delivery assumption is

`U_i(r_i;c_i) = (r_i-c_i)x_i(r_i) + integral_{r_i}^{cbar} x_i(z) dz`.

Where differentiable, its derivative is `(r_i-c_i)x_i'(r_i)`: nonnegative
below `c_i` and nonpositive above it. The same conclusion follows from the
monotonicity inequality at kinks. Thus `r_i=c_i` maximizes utility. At the
upper type the transfer is `cbar x_i(cbar)`, so utility is zero; truthful types
obtain `integral_{c_i}^{cbar}x_i(z)dz >= 0`. This is a dominant-strategy
cost-screening lemma, stronger than a Bayesian statement in that one narrow
dimension, but its assumptions are deliberately strict: capacity is hard and
held fixed, the transfer may require a subsidy, delivery is assumed, and
quality/reliability cannot be privately manipulated. The separate shortfall
bond is still required to make delivery incentives credible.

## Empirical mapping and gates

| model object | measurement | current status |
|---|---|---|
| `p_i` | public provider quote for a fixed workload | observed every 5 minutes on OpenRouter; public Akash/Vast GPU quote panels now added |
| `s_i` | public inverse-square simulated share | observed proxy; H43/H45/H48 explicitly label it non-realized |
| `q_i` | uptime, error, latency, throughput, router scorecard | public proxy only; private live eligibility remains unobserved |
| `x_i, y_i` | allocated and served controlled-study requests | public panels do not identify them; payload-free `router_capacity_epoch_outcomes` can record controlled provider/model/epoch aggregates, but has no published rows yet |
| `k_i` | provider/model/time commitment | public inference capacity remains unobserved; `router_capacity_commitments` can record a redacted controlled-study declaration, but has no published rows yet; Akash/Vast capacity is an external supply comparator |
| `c_i` | realized GPU-seconds times cost | not observed; no profit or optimal-bond claim is permitted |

H48 is a calibration sheet rather than a fitted structural model. The bond
calibration gate requires per-provider/model/time capacity, allocated/served
counts, selected-provider telemetry, and serving cost or contribution margin.
The payload-free `ingest-capacity-commitments` contract records only an
owner-supplied provider/model/study/epoch declaration, a request count, an
optional verification label, and an optional marginal-cost proxy. H48 matches
it to selected route attempts only when provider, model, study, and time epoch
all agree. A match is controlled-study coverage—not proof of capacity delivery,
market-wide demand, a causal routing effect, or an optimal bond. Without all
four primitives, the paper may state a design proposal and reduced-form
comparative statics, but not an empirically calibrated optimal mechanism.

The companion `ingest-capacity-outcomes` contract records only an aggregate
allocated count, served count, optional realized cost/revenue, and non-payload
metadata for the same provider/model/study/epoch key. H48 requires a
three-way match: selected route attempts, a capacity commitment, and an epoch
outcome. It keeps attempt outcomes and epoch aggregates distinct, so the
contract supports controlled-study calibration rather than a claim about a
router's global allocation or a provider's total delivered capacity.

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
