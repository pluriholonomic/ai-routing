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
7. **Limited liability.** If at most `L_i` of a nominal per-missed-request
   bond `b_i` is collectible, the payoff gain from serving a feasible assigned
   request is `p_i-c_i+min(b_i,L_i)`. Thus a nominal bond larger than
   collectible collateral does not strengthen the delivery incentive. This is
   a strict-condition extension of the one-period delivery lemma, not a
   capacity-reporting or physical-outage solution.
8. **Correlated outages.** With a joint outage state `omega` and fixed
   allocation `x`, expected delivery is `sum_omega pi(omega) sum_i
   1{i available in omega} x_i`. The deterministic water-fill result does not
   establish a reliability or welfare ranking under correlated physical
   outages. `OutageScenario` therefore requires a joint availability law;
   marginal uptime cannot be substituted for it.
9. **Robust correlated-outage feasibility.** Given an externally declared
   joint-outage support with positive probability, choose the non-replicated
   allocation that solves `max_{x,z} z` subject to `sum_i x_i <= D`,
   `0 <= x_i <= k_i`, and `sum_{i available in omega} x_i >= z` for every
   supported state `omega`. `robust_outage_allocation` implements this linear
   program and uses inverse-price/reliability scores only to break max-min
   ties. The resulting delivery floor weakly exceeds that of capped
   score-water-filling on the same hard capacities and outage support. This is
   a conditional resilience guarantee, not an estimate of outage risk,
   expected welfare, insurance value, or a reason to infer independence from
   marginal uptime.
10. **Convex capacity procurement, conditional DSIC and IR.** Before routing,
    suppose provider `i` has a certified physical ceiling `K_i`, a known
    positive capacity-cost curvature `b_i`, and one private linear reservation
    cost `a_i`. Procuring `k_i` costs `a_i k_i+b_i k_i^2/2`. The router buys
    the minimum-cost certified portfolio for demand `D`, then pays
    `T_i(r_i)=r_i k_i(r_i)+b_i k_i(r_i)^2/2+integral_{r_i}^{abar}k_i(z)dz`.
    Since `k_i(r_i)` is weakly decreasing in the report, truthful `a_i`
    reporting is dominant and the upper type has zero utility. The code-level
    `capacity_procurement_allocation` and `capacity_procurement_payment`
    implement the allocation and envelope diagnostic. This brings
    capacity-acquisition cost inside a narrow single-parameter procurement
    model; it does not elicit a privately chosen ceiling, a private curvature,
    reliability, correlated physical availability, or a budget-balanced
    mechanism.
11. **Known-primitive welfare benchmark.** With equal request value `v`, known
    reliability `q_i`, known marginal serving cost `c_i`, and hard capacity
    `k_i`, expected net welfare from allocation `x` is
    `sum_i x_i(v q_i-c_i)`. `welfare_capacity_allocation` assigns positive-
    surplus capacity in descending `v q_i-c_i` order, so it weakly maximizes
    this objective and weakly beats feasible pure-cheapest and
    reliability-only allocations under the same primitives. Payments are
    transfers and do not enter this calculation. This is an equal-value,
    known-primitive planner benchmark—not a welfare estimate, a private-
    information mechanism, or an assertion that any public price reveals
    cost or request value.

The next theory step is to extend these single-parameter results to jointly
private capacity, curvature, and reliability under a stochastic health process,
then extend the welfare benchmark to heterogeneous request value and controlled
observations.

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

For convex capacity procurement, hold certified ceilings `K_i` and positive
curvatures `b_i` fixed and let only `a_i` be private. The capacity allocation
minimizes `sum_i r_i k_i+b_i k_i^2/2` subject to the stated demand and ceiling
constraints. KKT stationarity gives
`k_i(r_i)=clip((lambda-r_i)/b_i,0,K_i)`, where the multiplier adjusts to the
required total. Raising `r_i` therefore weakly lowers its allocation. For a
report `r_i`, define the stated transfer. Its derivative is
`(r_i+b_i k_i(r_i)) k_i'(r_i)`, while the derivative of true utility is
`(r_i-a_i)k_i'(r_i)`. Because `k_i'<=0`, utility weakly rises up to the true
type and weakly falls afterward; the same envelope inequality applies at
kinks. At `abar`, the integral is zero and payment exactly covers the declared
convex cost, so IR binds. This is a DSIC/IR theorem only for a certified
ceiling, known curvature, one-dimensional linear reservation cost, and
feasible delivery. A provider able to choose or lie about `K_i` or `b_i`, or
to manipulate reliability, has a multi-dimensional type outside this result.

For the welfare benchmark, each assigned request to provider `i` succeeds with
probability `q_i`, produces common value `v` on success, and incurs marginal
cost `c_i` when assigned. The marginal objective coefficient is
`v q_i-c_i`; the feasible set is a box plus an aggregate demand constraint.
A linear program over that set assigns positive-capacity providers in descending
coefficient order and omits negative-coefficient units, exactly as
`welfare_capacity_allocation` does. Lowest-cost and reliability-only rules are
feasible members of the same set, so the maximum weakly dominates their
expected net welfare. This result does not select a distributional weight,
measure consumer willingness to pay, incorporate heterogeneous quality or
latency, or survive private/manipulable cost and reliability inputs.

The limited-liability calculation is immediate: under a feasible deliberate
refusal, the provider can lose no more than `min(b_i,L_i)`, so delivery minus
refusal is exactly `p_i-c_i+min(b_i,L_i)`. A design requiring a positive
delivery incentive must therefore verify collateral above the negative-margin
gap; increasing a merely nominal bond past the cap has no effect. Physical
outages remain distinct. For any recorded joint availability scenarios,
expected delivered requests are the probability-weighted available allocation.
The function `expected_delivered_under_outage_scenarios` records that quantity,
but it intentionally does not infer independent failures or choose a robust
portfolio without an empirical joint-outage panel.

For the robust correlated-outage proposition, fix a finite, declared set of
joint states with positive probability. The linear program's feasible set is
nonempty (`x=0,z=0`) and bounded by demand and hard commitments, so it has an
optimizer. Capped score water-filling is one feasible allocation in this set;
set its `z` to its minimum delivered count across the same support. The robust
optimizer therefore has a delivery floor weakly at least as high. The second
linear program changes only the objective among allocations attaining that
floor, so it cannot weaken the guarantee. Probability weights enter the
reported expected-delivery diagnostic but not the max-min objective; a
zero-probability state is deliberately excluded. This is not a distributionally
robust result, does not permit replicated delivery, and is only as credible as
the observed or declared joint-outage support.

## Empirical mapping and gates

| model object | measurement | current status |
|---|---|---|
| `p_i` | public provider quote for a fixed workload | observed every 5 minutes on OpenRouter; public Akash/Vast GPU quote panels now added |
| `s_i` | public inverse-square simulated share | observed proxy; H43/H45/H48 explicitly label it non-realized |
| `q_i` | uptime, error, latency, throughput, router scorecard | public proxy only; private live eligibility remains unobserved |
| `x_i, y_i` | allocated and served controlled-study requests | public panels do not identify them; payload-free `router_capacity_epoch_outcomes` can record controlled provider/model/epoch aggregates, but has no published rows yet |
| `k_i` | provider/model/time commitment | public inference capacity remains unobserved; `router_capacity_commitments` can record a redacted controlled-study declaration, but has no published rows yet; Akash/Vast capacity is an external supply comparator |
| `a_i, b_i` | declared linear reservation cost and positive capacity-cost curvature | optional redacted controlled-study fields exist on `router_capacity_commitments`; no published or independently verified observations yet |
| `v` | pre-registered owner-declared value per served request | optional redacted `declared_value_usd_per_served_request` on controlled epoch outcomes; a study proxy, not consumer surplus or market-wide welfare |
| joint outage support | named shared failure domains plus provider/epoch availability | `router_capacity_commitments` can record declared failure domains and `router_capacity_epoch_outcomes` can record an aggregate availability state and common outage identifier; neither creates joint-outage observations on its own |
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

The same commitment contract can optionally record a non-negative linear
capacity-reservation cost and a positive capacity-cost curvature. Those fields
are inputs to the single-parameter convex procurement theorem, not evidence
that costs, curvature, or capacity are privately truthful or independently
verified. A future calibration needs a pre-specified method for measuring them
and outcomes for the corresponding reservation epoch.

The companion `ingest-capacity-outcomes` contract records only an aggregate
allocated count, served count, optional realized cost/revenue, and non-payload
metadata for the same provider/model/study/epoch key. H48 requires a
three-way match: selected route attempts, a capacity commitment, and an epoch
outcome. It keeps attempt outcomes and epoch aggregates distinct, so the
contract supports controlled-study calibration rather than a claim about a
router's global allocation or a provider's total delivered capacity.

An outcome can also carry a non-negative owner-declared value per served
request. H48 calls it a controlled-study value proxy and reports it through a
separate welfare gate only with realized cost. It is not inferred from payment
or revenue and cannot support a market-wide or consumer-surplus claim.

For a correlated-outage extension, commitments may include declared named
failure domains and outcomes may include an aggregate availability status plus
a common non-payload outage identifier. A shared identifier is required when
the status is `unavailable`, so a controlled study can recover a declared joint
state across providers. These fields do not establish causality, common cloud
ownership, a complete outage distribution, or a live router's private health
filter.

`docs/controlled-routing-study.md` adds the necessary causal layer: a
pre-outcome manifest and non-overlapping randomized model-epoch assignment
ledger. H50 estimates registered policy contrasts only after its validity and
power gates clear. This upgrades the empirical path from a matched accounting
panel to an owned-study design; it does not create observed commitments,
delivery, or a welfare result by itself.

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
