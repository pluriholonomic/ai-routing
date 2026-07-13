# Public-data comparison of inference routing and other marketplaces

**Date:** 2026-07-13
**Purpose:** sharpen the market-design comparison, identify what public data can
and cannot establish, and prioritize the next experiments.

## Bottom line

The useful primary model is **not an AMM and not a literal DEX**.  An
open-model inference router is best treated as a **repeated, multi-attribute
reverse/scoring procurement market embedded in online matching of reusable,
perishable capacity**:

1. A request is a buyer's demand for a differentiated service, not a swap of
   fungible assets.
2. Providers offer a menu of price, context window, modalities, latency,
   availability, and (partly latent) reliability.
3. The router dispatches among eligible offers using a partly private score and
   fallback policy, while facing capacity that is reusable after a request but
   perishable while it is idle.
4. The buyer observes the delivered answer only after non-atomic execution;
   failure, retry, and quality are economically important.

That is closest operationally to rideshare dispatch and cloud revenue
management; closest strategically to a scoring/RFQ procurement auction; and
closest in public observability to decentralized compute procurement.  The
DeFi/RFQ comparison still has an important, narrower role: it gives us a
language for displayed versus delivered liquidity, quote freshness, quote
firmness, and order-flow information.  AMM loss-versus-rebalancing is a useful
*negative control*, not a welfare formula to transfer.

The immediate public-data unlock is a historical OpenRouter panel.  Its
documented daily model-ranking and app-ranking APIs permit date-windowed
backfill from 2025 onward without submitting inference requests.  This should
replace the current coarse frontend-counter snapshots for market-wide model
demand and app concentration.  It does **not** reveal a complete historical
app-by-model matrix: public app attribution remains top-N/censored and
public-attributed only.

## A corrected mapping

| Current shorthand | Better mapping | Why the change matters |
|---|---|---|
| Harness = wallet/front end | **Demand-side multihoming agent / merchant / order-flow originator** | A harness chooses defaults, pins, fallbacks, budgets, batching, and sometimes transforms a task into several model calls.  It owns the customer relationship rather than merely displaying a wallet. |
| Router = DEX aggregator | **Two-sided broker, dispatcher, and scoring procurement platform** | It may rank offers by private quality/reliability signals and may retry or fail over.  Those actions make it more than best-price path finding. |
| Open-source model = protocol | **Differentiated production technology and compatibility standard** | An open-weight model can be replicated by many providers and behaves partly like an interoperable standard.  A closed model is a vertically integrated product, not a protocol. |
| Inference provider = LP | **Capacity-constrained service seller / market maker** | The provider sells an exhaustible-in-the-moment service with queues, failures, and quality.  It generally has no pooled inventory invariant or on-chain settlement obligation. |
| User request = swap | **Procurement job / passenger trip / cloud serving job** | Completion is non-atomic and its quality is initially uncertain.  Tokens are metering units, not the homogeneous asset being exchanged. |
| GPU market = external price oracle | **Upstream input and capacity market** | GPU prices affect cost only after matching hardware, geography, utilization, model, and contract type.  A generic GPU quote is not provider marginal cost. |

The resulting stack has four layers:

```text
End user / task owner
        |
Harness, app, agent, or gateway  <-- demand shaping, multihoming, defaults
        |
Router / broker / dispatcher     <-- eligibility, scoring, retries, settlement
        |
Provider offer + service         <-- price, capacity, latency, reliability
        |
Model technology + GPU/cloud input
```

This distinction also makes the empirical terminology more honest.  What has
occasionally been called "front-running" here is normally **rank gaming,
quote shading, or information-rent capture after public competitor moves**.
Literal MEV/front-running requires an actor to see a specific non-public order
before execution.  No current public inference dataset supplies that ordering
or visibility.

## What each outside market contributes

| Comparison market | Mechanism that transfers | Best public-data use | What does *not* transfer |
|---|---|---|---|
| RFQ / intent DEX aggregator | Quote freshness, displayed versus delivered liquidity, maker eligibility, fallbacks, fragmented supply | Event studies around quote changes; response/failure conditional on a displayed quote; CoW solver outcomes as a transparent method control | Atomic settlement, public order intents, and actual maker fill choice are not observed in public inference data. |
| AMM / on-chain DEX | Transparent state, executable-price curves, adverse-selection benchmark, causal event-time methods | Validate event-study and concentration estimators against CoW/Uniswap where execution is observable | No constant-product inventory, block ordering, or deterministic on-chain quote here.  Do not translate LVR into inference-provider profit. |
| Rideshare | Online matching with reusable capacity, time-varying supply/demand, dispatch, wait/latency, driver/rider multihoming | Use completed-trip data as a method control for demand shocks, capacity imbalance, and service-level outcomes | Public trip data do not expose dispatch scores, the full driver choice set, or a direct provider-quality analogue. |
| Cloud spot / revenue management | Perishable capacity, interruption/preemption, utilization, advance versus on-demand commitments | Test whether upstream capacity interruptions precede inference availability, throughput, or repricing | A spot offer is not a model-specific provider cost absent a hardware-region-deployment match. |
| Sponsored search / scoring auction | Price plus quality score determines rank/eligibility; platform can create a private score | Estimate an implicit router quality score from price, observed performance, capacity, and aggregate share | Ad impressions/clicks and LLM requests have different consumer learning and payment rules. |
| Reputation marketplace | Latent quality, screening, reputation accumulation, adverse selection | Link benchmark/reliability shocks to subsequent market share and price | Review systems and slow reputation do not reproduce real-time router health scoring. |
| Decentralized compute (Akash, Bittensor, Livepeer) | More transparent supply, bidding, assignment/scoring/reward state | Use as an observable laboratory for accepted bids, leases, weights, rewards, and concentration | On-chain assignment/reward is not the same as centralized router selection or delivered LLM quality. |

The theory support is unusually direct.  Scoring-auction work treats price and
quality jointly in procurement; reusable-resource work treats the exact
capacity feature missing from financial-market metaphors.  Two-sided-platform
theory helps separate the router's demand-side and supply-side incentives.
Relevant foundations include [Che's multi-dimensional procurement
auction](https://ideas.repec.org/a/rje/randje/v24y1993iwinterp668-680.html),
[Asker and Cantillon on scoring auctions](https://ideas.repec.org/a/bla/randje/v39y2008i1p69-85.html),
[Rochet and Tirole on two-sided price allocation](https://onlinelibrary.wiley.com/doi/pdf/10.1162/154247603322493212),
[Dickerson et al. on ride-sharing with offline reusable resources](https://ojs.aaai.org/index.php/AAAI/article/view/11477),
and the ACM EC paper [*Power of Static Pricing for Reusable Resources*](https://doi.org/10.1145/3736252.3742552).

For the controlled DeFi contrast, [Milionis et al.'s LVR analysis](https://arxiv.org/abs/2208.06046)
is valuable precisely because it shows the state/inventory and informed-flow
conditions that must be observed before an adverse-selection claim is made.
The closest LLM-demand empirical predecessor is [Fradkin's OpenRouter study](https://arxiv.org/abs/2504.15440),
which documents substitution, market expansion, and app multihoming but is
appropriately descriptive given public data censoring.

## Public source ladder

The following sources add genuine new observables rather than merely more
copies of the current quote surface.

| Priority | Source and retrieval | Unit observed | New measurement enabled | Boundary |
|---|---|---|---|---|
| P0 | [OpenRouter daily rankings](https://openrouter.ai/docs/api/api-reference/datasets/get-rankings-daily) and [app rankings](https://openrouter.ai/docs/api/api-reference/datasets/get-app-rankings) | model-day and app-day token share/rank, category, trend | Reconstruct demand, concentration, entry, app-level multihoming proxies, and release event windows since 2025 | Daily rankings have top-50 plus other; app values are attributed/public only and are not a full app-model ledger.  Respect API limits and archive raw responses. |
| P0 | [OpenRouter models endpoint](https://openrouter.ai/docs/api/api-reference/models/get-models) and public route-health fields already captured | endpoint-time quote, performance, health, capacity, model metadata | Price-performance frontier, score residuals, health and derank shocks | No realized provider selection or request ordering. |
| P0 | [Akash market lifecycle and API](https://akash.network/docs/node-operators/architecture/application-layer/) | order, bids, accepted lease, provider, contract state | Bid-set-to-lease selection, quote firmness, capacity and entry/exit comparator | Lease acceptance is not successful inference delivery or a model-specific workload. |
| P0 | [Bittensor metagraph](https://docs.learnbittensor.org/python-api/html/autoapi/bittensor/core/metagraph/) and [weight/emission mechanics](https://www.bittensor.com/docs/concepts/emissions) | validator weights, miner incentive/emission, stake/trust | Transparent scoring-allocation concentration and rank-gaming laboratory | Reward allocation is not a per-user route or price quote. |
| P1 | [CoW Protocol](https://docs.cow.fi/) settlement/auction data and finalized Uniswap state | public order/auction/settlement or state/execution | Validate quote-to-execution, event-time, and concentration estimators where outcomes are observed | Batch auctions and atomic chain execution differ from sequential inference. |
| P1 | Chicago [TNC trip records](https://data.cityofchicago.org/Transportation/Transportation-Network-Providers-Trips/m6dm-c72p) | completed trip/time/fare/duration/geography bins | Method control for reusable-capacity shocks, platform competition, and demand peaks | Redaction and no dispatch choice set prevent structural identification of dispatch. |
| P1 | [AWS Spot price history](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSpotPriceHistory.html), public cloud price sheets, existing Vast/Akash captures | hardware-region-time price/availability/interruption proxy | Upstream input/capacity shock instrument candidates | Requires an exact deployment map; do not call it a cost shock otherwise. |
| P1 | [LMArena public datasets](https://huggingface.co/lmarena-ai/datasets), Hugging Face Hub model metadata | benchmark/preference or model-update time | Exogenous-ish quality-information shocks and open-model diffusion controls | Preferences/downloads do not equal paid router usage or delivered quality. |
| P2 | Livepeer on-chain operator metrics | stake, fee, reward, service URI | Service-market operator concentration and stake-performance comparisons | No per-job route assignment. |

## Pre-registered experiment queue

Every experiment below includes a falsification condition.  A new panel should
be retained in long form with source URL, capture time, source event time,
coverage, and a `claim_level` field; no chart should silently turn a proxy into
execution evidence.

### P0-A — Historical demand, entry, and multihoming reconstruction

**Question.** Does an open-model release expand total routed demand, substitute
for existing models, or merely reallocate traffic among providers?

**Data.** Backfill each UTC day from 2025-01-01 using OpenRouter's daily
rankings; paginate daily app rankings by category and `popular`/`trending`.
Keep the raw responses and a coverage table.  Join canonical model families,
open-weight status, provider count, price/latency/throughput, and release dates.

**Outcomes.** Model token share; total top-50 token volume; HHI and entropy;
entry/exit; app rank and app-category concentration; number and persistence of
models used by a visible app when a top-N model-app relation is available.

**Estimator.** Stacked event study around pre-registered open-model releases,
with event-specific fixed effects and matched closed/open control models.  For
substitution, estimate distributed-lag changes in incumbent-family shares and
test whether the aggregate `other`/top-50 total rises.  Use leave-one-app-out
and no-new-release placebo dates.

**Falsification and boundary.** A fall in incumbents with no rise in aggregate
demand is substitution, not market expansion.  A public-app panel cannot prove
an individual application's routing rule, because attribution is censored and
opt-in.  This is the highest-value no-order data collection task.

### P0-B — Score-augmented reverse-auction model of router allocation

**Question.** Is public price sufficient for aggregate allocation, or is a
router quality/eligibility score economically material?

**Data.** Five-minute provider-model quotes, routing-health and performance
fields, provider capacity ceilings, derank/rate-limit state, and the rebuilt
daily model-demand panel.  Split by model family and time window.

**Model.** Estimate a nested/logit or softmax share equation in which an
endpoint's utility is

```text
score(i,m,t) = -alpha * effective_price + beta * observed_performance
               + gamma * health/capacity + provider/model fixed effects.
```

Compare price-only, public-performance, and health/capacity versions with
strict forward prediction.  Interpret the residual only as an *implicit
router-score proxy*, not proof of a private score.  Test whether a derank or
rate-limit spike changes the residual allocation after conditioning on price.

**Falsification and boundary.** If public terms do not improve forward
prediction beyond price and fixed effects, there is no public evidence for a
time-varying score.  Even a strong model does not identify realized
provider-level selection; it explains the public allocation surface.

### P0-C — Reliability enforcement as a quasi-experimental quality shock

**Question.** Does router policing reallocate market share after a provider's
health deteriorates, and are cheap quotes insulated from that penalty?

**Data.** Existing `rate_limited`, `derankable_error`, `is_deranked`, and
capacity-ceiling fields at five-minute cadence; daily rankings and historical
app panel from P0-A.

**Estimator.** Event-time difference-in-differences around the first
pre-specified derank onset or large rate-limit spike, matching untreated
provider-model endpoints on model, price decile, pre-event share, and time.
Use an onset/recovery symmetry test, randomized pseudo-onsets, and a test for
pre-trends.  Estimate changes in price, public availability, model share, and
competitor shares.

**Falsification and boundary.** No pre-trend plus a post-onset relative share
drop supports enforcement being economically consequential.  It does not say
which request was rerouted, whether the router saw private demand, or whether
the shock was exogenous to latent demand.

### P0-D — Akash transparent procurement comparator

**Question.** When the bid set is public, how much selection is explained by
price, capacity, provider history, and non-price attributes?

**Data.** Block-pinned Akash orders, all bids, accepted lease, lease lifecycle,
provider capacity, hardware attributes, and native-to-USD conversion retained
separately.  Expand coverage before estimating anything; current H55 remains
coverage-gated.

**Estimator.** Conditional logit of accepted provider over the contemporaneous
bid set; decomposition of price versus non-price attributes; bid withdrawal/
expiry hazard after rival bids; concentration and bidder entry around demand
shocks.  Use within-order choice-set fixed effects.

**Falsification and boundary.** If price nearly fully predicts winning bids,
the procurement channel is price-led.  If non-price state remains predictive,
the scoring-auction analogy has an observable comparator.  A lease only proves
contract selection, not utilization, execution quality, or an LLM route.

### P0-E — Bittensor transparent scoring-allocation comparator

**Question.** What do dynamic scoring and reward allocation look like when
weights and rewards are public, and do rapid rank changes follow measurable
quality/stake changes or coordinated weighting?

**Data.** Per-epoch validator-to-miner weights, miner incentives/emissions,
stake/trust, connectivity, subnet metadata, and any public benchmark score.

**Estimator.** Weight-to-emission pass-through; Herfindahl/Gini evolution;
event studies around score/weight shocks; validator similarity and lead-lag
tests; permutation tests that preserve validator activity.  Pre-register a
coordination threshold and require persistence across epochs.

**Falsification and boundary.** This produces a transparent benchmark for
score-driven allocation and potential rank gaming.  It is not evidence that an
OpenRouter provider is selected in the same way, nor evidence of user harm.

### P1-F — Quote-to-execution benchmark on CoW and Uniswap

**Question.** How much can the same estimators recover when both the displayed
state and execution are visible?

**Data.** Finalized CoW auction/settlement records, solver outcome where
available, Uniswap state and swaps, fixed-size executable quote curves.

**Estimator.** Apply the identical quote-staleness, adverse-selection,
concentration, and event-time code used for inference.  Report sensitivity and
false-positive rates for known quote-to-execution transitions.

**Falsification and boundary.** The comparator passes only if known execution
facts are recovered and the inference analysis is reported as a proxy where
its outcome is absent.  Different settlement design precludes a common profit
or welfare coefficient.

### P1-G — Reusable-capacity dispatch control in rideshare

**Question.** Do the inference time-series methods distinguish demand peaks
from supply/quality shocks in a completed-service setting?

**Data.** Chicago TNC trip records by time/geography, weather, transit events,
and public congestion controls.  Retain the official redaction and revision
rules.

**Estimator.** Time-by-area panel with demand-shock and capacity-proxy event
studies; compare observed wait/duration/fare adjustments to a price-only
model.  Use this only as an estimator-validation exercise, not a claim that
inference users behave like passengers.

**Falsification and boundary.** If the method mechanically labels ordinary
demand peaks as strategic supply withholding, it is not safe for inference.

### P1-H — Upstream GPU shock pass-through with exact deployment mapping

**Question.** Are model-provider repricings/availability changes explained by
input capacity shocks or by competitive quote responses?

**Data.** Exact GPU SKU, region, cloud/contract type, model deployment and
provider mapping; then spot/on-demand/Vast/Akash price and availability series.
Only include a provider when this mapping is independently documented.

**Estimator.** Local projections of quote, capacity, rate-limit, and share on
matched input shocks; rival-price controls; provider and calendar fixed effects.
Use lead tests and un-matched-SKU placebo shocks.

**Falsification and boundary.** A generic GPU index is a descriptive control,
not an instrument for cost.  Without the mapping, this experiment must stay
unreported as causal evidence.

### P1-I — Quality-information and vertical-integration shocks

**Question.** Does externally revealed quality move usage differently for
open-weight, multi-provider models than for vertically integrated models?

**Data.** Timestamped LMArena/benchmark releases, Hugging Face model revision
metadata, OpenRouter historical rankings, provider entry, and public price
surface.

**Estimator.** Matched event study with release/revision-time windows;
heterogeneity by open-weight status, provider count, and pre-event price tier.
Require no contemporaneous major price change in the cleanest specification;
estimate a joint quality/price specification separately.

**Falsification and boundary.** Benchmark information is endogenous to model
release and publicity.  It supports a market-response description only unless
the event timing is externally fixed and pre-trends pass.

### P2-J — Two-sided platform and app-concentration panel

**Question.** Does growth on the app side increase model/provider variety and
reduce concentration, or does it entrench a few default models?

**Data.** P0-A app rankings and model rankings, app categories, model/provider
entry, public routing/model metadata.

**Estimator.** Rolling cross-side regressions and event studies around app
category growth, with HHI/entropy and entry outcomes.  Split by category,
open-weight status, and default-eligible models; run reverse-causality lead
tests.

**Falsification and boundary.** This measures public attributed traffic and
network-correlated evolution, not a causal platform fee or user surplus.

## Data engineering order

1. **Qualify and backfill OpenRouter datasets first.** Build a dedicated raw
   archive plus normalized `public_model_daily` and `public_app_daily` tables;
   include source date, retrieval date, endpoint parameters, page/cursor, and
   `is_top_n`/`is_other` fields.  This is read-only API retrieval, not an
   inference order.
2. **Hydrate existing five-minute observations and enforcement histories.**
   The current local panels have inadequate contiguous history for H43/H66 and
   derank onset analysis.  Retain all source snapshots, not only derived
   summaries.
3. **Build an event registry before estimating.** Each release, derank, rate
   limit, benchmark revision, Akash order, and external capacity event needs an
   immutable event timestamp, source, eligibility rule, and placebo rule.
4. **Add transparent comparator collectors separately.** Akash bid pages,
   Bittensor epochs, CoW settlement/auction data, and Chicago TNC data should
   use source-specific schemas; never force them into a false common notion of
   a fill.
5. **Run estimator validation before cross-market conclusions.** A result is
   strongest when the same code recovers a visible selection/execution outcome
   in Akash/CoW and remains explicitly partial for OpenRouter.

## What public data cannot settle

Public data can support the following bounded claims: quote competition,
public allocation/concentration, policy-enforcement response, transparent
procurement selection, and comparisons of state observability.  It cannot
identify an individual request's eligibility set, selected provider, retry
sequence, provider cost, delivered answer quality, profit, or private
order-flow knowledge.

Therefore neither a public quote move nor a subsequent share move is proof of
front-running.  The minimum data for that stronger claim are privacy-preserving
router event logs containing: request arrival time and anonymized request ID,
eligible endpoints, decision/attempt sequence, selected provider, quoted and
billed price, terminal outcome, retry/fallback, and contemporaneous provider
quote update identifiers.  Controlled own-traffic probes can validate
quote-to-selection and fallback behavior cheaply, but they still cannot reveal
whether a provider observed other users' flow.  The existing redacted
`route_telemetry.py` / RouteScope contract is the appropriate partner-data
path.

## Recommended research narrative

The paper should present a **comparison framework rather than a claim of
market identity**:

> Inference routing is a two-sided, dynamic scoring-procurement platform for
> differentiated, capacity-constrained services.  RFQ/DEX markets illuminate
> quote quality and information rents; rideshare and cloud markets illuminate
> reusable capacity and dispatch; transparent decentralized compute markets
> provide the observable-selection laboratory.  The centralized public router
> surface identifies only the first layer until controlled or partner telemetry
> reveals actual dispatch.

That framing is sharper than “harness = wallet, model = protocol, provider =
LP,” remains compatible with the existing RFQ mechanism manuscript, and makes
the negative result on literal MEV a contribution in identification rather
than a missing analysis.
