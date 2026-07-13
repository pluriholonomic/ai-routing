# Execution plan: public marketplace comparison

**Companion:** [market-design research memo](public-marketplace-comparison-research-2026-07-13.md)
**Decision:** build an empirical comparison of *allocation mechanisms*, not a
dashboard that places unrelated DeFi, GPU, and LLM price charts beside one
another.

## 1. Objective and decision criteria

### Primary research question

When price, quality, reliability, and capacity move, how does allocation react
in (a) a centralized open-model router, (b) an observable decentralized
compute procurement market, and (c) transparent DeFi execution markets?

The primary inference-market description to test is:

> A router is a dynamic scoring-procurement and dispatch platform for
> differentiated services sold from reusable, capacity-constrained resources.

RFQ/DEX, rideshare, cloud, and online-reputation markets are comparison
modules—not claims of common market identity.

### Claims that can be supported at each evidence level

| Evidence level | Permitted conclusion | Explicitly not permitted |
|---|---|---|
| Public quote/health surface | price competition, observable quality/health correlation, quote-change timing | realized provider selection, cost, profit, or private-flow knowledge |
| Public aggregate demand | model-level concentration, substitution/expansion patterns, visible-app concentration | individual app routing, provider allocation, consumer welfare |
| Public transparent procurement | bid-set-to-accepted-contract selection, public scoring/reward allocation | LLM delivery quality or an OpenRouter-equivalent policy |
| Public on-chain execution | state/quote-to-settlement behavior and estimator validation | inference economics or a common welfare coefficient |
| Controlled own traffic | behavior of our requests, quote-to-selection, fallback/firmness | other users' flow or literal front-running |
| Partner router telemetry | request-level eligibility, selection, retries, and quote/execution relation | provider private profitability unless separately supplied |

### Program-level success conditions

The program is successful only when it produces all of the following:

1. A reproducible, raw-retained, source-qualified panel for each market;
2. a pre-registered event and estimator registry before results are viewed;
3. one or more transparent-market benchmarks on which the shared estimator
   recovers an observable selection/execution fact;
4. a published comparison table that keeps proxy, aggregate-allocation, and
   realized-selection evidence separate; and
5. a decision memo that states whether price-only, score-augmented, or
   capacity-constrained explanations have the best out-of-sample support.

## 2. Workstream sequence

```text
W0 governance and source contracts
        |
        +-- W1 OpenRouter historical aggregate demand -------+
        +-- W2 Router enforcement and quote/health history --+-- W6 unified
        +-- W3 Transparent compute selection ----------------+   analysis
        +-- W4 Transparent DeFi execution controls ----------+        |
        +-- W5 Capacity, quality, and rideshare controls ----+        v
                                                       W7 dashboard/paper
```

The first four workstreams can collect independently.  W6 must not start its
cross-market causal comparisons until the source-specific coverage gates pass.

## 3. Phase 0 — governance, schemas, and preregistration (days 0–3)

### 3.1 Freeze the unit of comparison

Use a different physical unit for each market and compare *mechanisms* at the
cohort level.  Do not construct a universal price index.

| Market | Analysis unit | Required matching dimensions |
|---|---|---|
| Inference | model × endpoint/provider × five-minute observation; model × UTC day for demand | canonical model/version, context/feature tier, price basis, provider, health state |
| Akash | order × contemporaneous bid set × accepted lease | deployment/GPU specification, region if observed, bid denomination, block height |
| Bittensor | subnet × validator × miner × epoch | subnet task, epoch, score/weight, stake/trust, emission |
| DeFi | asset pair × venue/pool × finalized block/order | pair, direction, fee tier, notional bucket, finality watermark |
| Rideshare | city zone × time bucket × completed trip | local time, geography/redaction level, service tier, weather/event control |
| GPU input | exact GPU SKU × region × contract type × time | accelerator, count/RAM, on-demand/spot/bid/reserved, geography, interruption terms |

### 3.2 Create the source and event contracts

Extend the existing source-run ledger rather than adding an untracked notebook
per source.  Every normalized row must contain:

```text
source, source_id, raw_payload_pointer, source_event_time, observed_at,
ingested_at, run_ts, source_version/schema_hash, coverage_status,
mapping_version, claim_level
```

Every event must have an immutable source reference and a separate eligibility
decision:

```text
event_id, event_type, event_time, declaration_time, source_reference,
eligible, exclusion_reason, treatment_unit, control_pool_version,
window_specification, placebo_rule
```

Add these reference tables (do not overwrite previous mappings):

- `model_family_map`: canonical model, release/version interval, open-weight
  status, family, vendor, architecture/size where known;
- `endpoint_offer_map`: endpoint ID, provider, model mapping interval, pricing
  unit and supported features;
- `compute_resource_map`: provider resource strings to exact GPU cohort,
  region and contract terms;
- `market_instrument_map`: DeFi pair/pool/fee tier and compute/inference
  comparability cohorts; and
- `event_registry`: immutable events and pre-analysis eligibility.

### 3.3 Pre-register the analysis

For every eventual headline result, version a YAML/JSON specification under a
new `analysis_registry/` directory.  It must include the sample window, exact
outcome, exposure/treatment definition, control selection, estimator, fixed
effects, clustering, multiple-testing family, minimum-data gate, and claim
language.  Results run on data before the spec timestamp are labelled
exploratory.

### 3.4 Gates before collection is called complete

| Dataset | Minimum completeness condition |
|---|---|
| OpenRouter rankings | raw response and source metadata for every requested UTC date; no unlabelled top-N/`other` ambiguity |
| Enforcement | a contiguous five-minute endpoint path with explicit source gaps; no imputed state transitions |
| Akash | full paginated bid coverage for the declared provider/block universe, plus accepted-lease linkage |
| Bittensor | a finalized epoch sequence with snapshot height/hash and complete weight/incentive fields for the chosen subnet |
| DeFi | finality-buffered event coverage with overlap accounting and no silent uncovered blocks |
| GPU | exact SKU/region/contract mapping; otherwise contextual-only |

**Deliverables:** source qualification checklist; schemas/mapping contracts;
event-registry template; preregistration template; an initial coverage board.

## 4. Phase 1 — build the OpenRouter public-demand and enforcement panels (days 1–10)

### W1. Historical model and app demand

**Why first.** This directly fixes the present gap between rich five-minute
quote observations and coarse/short demand evidence.  It is a read-only
authenticated aggregate-data backfill, not an inference probe.

**Existing base.** `capture_openrouter_datasets.py` already captures documented
daily model rankings to `openrouter_rankings_daily`, preserves raw payloads,
and fails closed on malformed top-50/`other` rows.  H64 already provides a
30-complete-day aggregate-demand gate.

**Implementation tasks.**

1. Add an explicit, opt-in app-ranking collector with bounded date windows,
   category, sort, page/offset, response version, and rate-limit ledger.
   It must preserve the API's attribution and ranking semantics rather than
   infer absent apps as zeros.
2. Add `openrouter_app_rankings_daily` at app × date × category × retrieval
   scope grain.  Keep `rank_scope`, rank, reported tokens/usage metric,
   `is_top_n`, pagination position, and source response hash.
3. Backfill daily model rankings from 2025-01-01 to the latest *closed* UTC
   day.  Backfill app windows in bounded chunks while respecting documented
   request limits.  A retry is a new source run, never an overwrite.
4. Reconcile models through `model_family_map`; preserve all unmapped IDs and
   count them in the coverage report.  Attach open-weight status only when
   source/version evidence is retained.
5. Build `public_model_daily` and `public_app_daily` views that select the
   latest valid API revision but retain historical revisions for audit.
6. Update H64 for rolling concentration, entry/exit, aggregate growth, and
   `other` share.  Add H72 for app concentration/category change, explicitly
   labelled aggregate/attributed rather than app-by-model routing.

**Data-quality tests.** Missing days, duplicate model-day rows, multiple
`other` rows, an API interval mismatch, rank discontinuity caused by a changed
scope, and unidentified model mappings all fail the relevant aggregate.

**Initial analyses.**

- Model token share, top-1/top-5/top-50 share, HHI, entropy, entry/exit;
- visible-app HHI, persistence, category concentration, and rank turnover;
- release event study of model-family share and top-50-plus-other aggregate
  tokens; and
- app/model movement only where the source itself gives that relation, with
  censoring flags retained.

**Decision gate.** Do not claim substitution or expansion until there are at
least 90 complete days spanning pre- and post-event observations for a
pre-registered release cohort.  Do not call app concentration a routing share.

### W2. Enforcement and score-proxy panel

**Existing base.** H68 creates a contiguous endpoint-level enforcement panel
from public five-minute `rate_limited`, `derankable_error`, `is_deranked`, and
capacity fields.  Its current evidence is too short for an onset study; state
gaps must remain gaps.

**Implementation tasks.**

1. Hydrate and append all retained `congestion_intraday` and targeted burst
   observations to a canonical, deduplicated panel.  Keep source priority but
   retain source provenance.
2. Produce daily coverage diagnostics: endpoints observed, median interval,
   missingness, contiguous-path hours, rate-limit onsets, derank onsets and
   releases.
3. Build an `endpoint_event_registry` before looking at demand outcomes:
   pre-specify a derank onset and a high-rate-limit definition, then record
   all excluded events and why.
4. Create matched controls within model family, price bucket, pre-event health,
   capacity, and pre-event public model share.  Controls cannot be selected on
   future outcomes.
5. Estimate onset/recovery event studies for quote, public availability,
   capacity, and model-level aggregate share.  Include pre-trends, pseudo-event
   dates, leave-one-provider-out, and overlapping-event exclusions.
6. Estimate a strictly forward price-only versus price+performance+health
   allocation model.  Call its remainder a **score proxy** only; no result
   identifies a private router score or a selected endpoint.

**Decision gate.** Require 50 non-overlapping derank onsets or 100
pre-registered high-rate-limit events, at least 28 days of pre/post window
coverage, and no material differential pre-trend before using causal wording.
Otherwise report descriptive hazards only.

**Deliverables:** H68 coverage report; H73 score-proxy prediction analysis;
H74 enforcement event-study analysis; an endpoint event ledger.

## 5. Phase 2 — transparent selection and execution comparators (days 4–30)

### W3. Akash: public reverse-procurement comparator

**Question.** Conditional on a public order and bid set, how do price,
resource characteristics, and provider state predict the accepted lease?

**Existing base.** The repository has an H55 block-pinned open-GPU bid contract
but its current canonical panel is coverage-gated.  Treat this as a collection
repair, not a zero-demand finding.

**Implementation tasks.**

1. Pin each collection run to a chain height/hash and enumerate the declared
   order/bid pagination universe; log page count and expected/received counts.
2. Ingest the order, all contemporaneous eligible bids, accepted bid/lease,
   provider, resource requirements, lifecycle state, and close event.  Store
   native price and USD conversion separately.
3. Create an order-choice-set table with one row per observed bid and a
   `selected_contract` flag.  Do not manufacture missing bids as losses.
4. Join only literal resource attributes (GPU class/count, deployment terms,
   region when observed).  Omit incomparable bids rather than use a generic
   GPU price adjustment.
5. Estimate conditional logit with order fixed effects; price-rank/non-price
   decomposition; bid expiry/withdrawal hazard after rival bids; provider
   concentration and entry after demand shocks.
6. Hold out entire days/orders for validation.  Publish choice-set coverage
   ahead of coefficient tables.

**Decision gate.** At least 1,000 fully observed order-choice sets, 10 or more
bid options in a meaningful subset, 30 days, and less than 1% unresolved
pagination failures in the declared universe.  Below that, publish only source
coverage and descriptive bid/lease counts.

### W4. Bittensor: transparent scoring-allocation comparator

**Question.** How do publicly visible scoring weights become rewards, and what
patterns distinguish ordinary score response from concentrated/coordinated
weight shifts?

**Implementation tasks.**

1. Select one or two subnets with a documented task and sustained activity;
   freeze the subnet IDs and selection rule before capture.
2. Add a block/epoch-pinned collector for metagraph state: validator/miner IDs,
   weights, incentives/emissions, stake, trust, active status, and source
   metadata.  Pseudonymize only in derived public releases if necessary; raw
   chain identity remains immutable evidence.
3. Normalize to `bittensor_epoch_weights`, `bittensor_epoch_rewards`, and
   `bittensor_epoch_participants`; track validator/miner entry and exit.
4. Pre-register concentration (HHI/Gini), weight-to-emission pass-through,
   rank-change, validator-similarity, and lead-lag specifications.  Construct
   null distributions that preserve validator activity and epoch size.
5. Test candidate coordination only after a persistent, pre-specified
   similarity/lead-lag threshold is crossed and a permutation test rejects the
   null.  Label it coordinated weight behavior, not malicious conduct.

**Decision gate.** At least 90 finalized epochs, five active validators, 20
active miners, and a complete field-coverage ledger.  This is an allocation
and scoring comparator, not a user-routing experiment.

### W5. CoW/Uniswap: transparent execution calibration

**Question.** Do our staleness, price-impact, concentration, and event-study
estimators behave correctly in a market where state and execution can be seen?

**Existing base.** H41/H52/H56/H57/H65 maintain finality-pinned state and
bounded CoW/Uniswap evidence.  They are currently power-gated rather than a
full historical execution panel.

**Implementation tasks.**

1. Maintain finality-buffered, overlapping finalized windows; report uncovered
   block intervals and source watermark daily.
2. Add a market-wide CoW execution/auction source only after validating solver
   identity and coverage.  Retain order/fill/settlement semantics separately.
3. Compute fixed-notional quote curves at the parent block and compare to
   actual settlement in matched pair/direction/size buckets.  Keep fees, gas,
   surplus, and intra-block movement as separate unobserved components.
4. Run identical event-time and concentration code as the inference analysis;
   measure recovery of known selection/execution outcomes and false-positive
   rates under randomized event times.
5. Create `estimator_validation_report` that lists which estimators passed in
   transparent markets before they appear in inference claims.

**Decision gate.** At least 500 matched CoW fills, seven contiguous days, two
pre-specified pools, zero unexplained finality gaps, and passing unit tests for
parent-state alignment.  If the estimator fails here, remove it from the
inference headline analysis.

## 6. Phase 3 — external capacity, quality, and dispatch controls (days 10–45)

### W6. Exact GPU-input pass-through

1. Build `compute_resource_map` only from independently documented provider
   deployment claims: exact accelerator, region, cloud/contract, model/version,
   and validity interval.
2. Collect matched spot/on-demand/offer-book series for those exact cohorts;
   retain their native terms (preemptible, reserved, bid, verified host) rather
   than blending them.
3. Estimate local projections of provider price, availability, and rate-limit
   state on *matched* input shocks, with provider/calendar effects and
   unmatched-SKU placebo series.
4. Report generic GPU indexes as context only.  A shortage of exact mappings
   is a valid negative result, not a reason to regress on an arbitrary H100
   index.

**Gate:** five independently documented provider-deployment mappings with 60
days of aligned data and lead/lag placebo tests.

### W7. Quality-information shocks and open-model diffusion

1. Construct a timestamped registry of benchmark/preference releases, model
   revisions, and canonical release announcements; retain the source revision.
2. Match open-weight models to closed/vertically integrated controls by
   pre-event price tier, popularity, capability family, and release age.
3. Run stacked event studies for share, provider entry, price, and visible-app
   concentration; separate quality information from contemporaneous price
   changes.
4. Require pre-trends, no-new-model placebo dates, and leave-family-out tests.

**Gate:** at least 20 pre-registered events with 30 days on each side.  The
result is market response to public information, not a causal quality estimate
unless timing is demonstrably external.

### W8. Rideshare reusable-capacity method control

1. Ingest a frozen extract of Chicago TNC records and preserve official
   redaction/version metadata.
2. Build zone-time completed-service, duration, fare, and trip-count panels
   with weather/transit/event controls.
3. Use it solely to test whether our event-study pipeline mistakes ordinary
   demand surges for strategic capacity withholding.  Use unknown dispatch
   rules as a known hidden-state problem.
4. Promote a method only if it recovers obvious completed-service changes
   without creating false supply-withholding findings in placebo windows.

**Gate:** one complete, versioned historical extract and a pre-specified
placebo/calibration report.  Do not mix trip fares into the inference price
panel.

## 7. Phase 4 — unified analysis and decision protocol (after data gates)

### 7.1 Analysis table

Produce one row per hypothesis with this fixed structure:

| Field | Requirement |
|---|---|
| Economic mechanism | scoring procurement, quote firmness, reusable capacity, concentration, or quality screening |
| Market and dataset | exact source/version/window, not a generic label |
| Observable outcome | quote, aggregate allocation, selected contract, reward, or settlement |
| Estimator and validation | preregistration ID, comparator pass/fail, clusters and placebo result |
| Effect and uncertainty | point estimate, confidence interval, sample, event count, coverage |
| Claim level | descriptive / predictive / quasi-causal / realized-selection |
| Negative boundary | the nearest stronger claim that data cannot establish |

### 7.2 Shared estimators

Use only estimators that pass their source-specific diagnostics:

- **Concentration:** HHI, entropy, top-k; bootstrap by time block, never treat
  repeated five-minute snapshots as independent demand draws.
- **Quote response:** endpoint/model fixed effects, time controls, clustered
  uncertainty by endpoint and date; exclude overlapping shock windows.
- **Event study:** stacked cohort design, pre-trends, event-specific windows,
  treatment timing frozen before outcomes, randomized event-time placebo.
- **Choice/score:** conditional logit within a fully observed choice set;
  forward holdout and calibration, not in-sample pseudo-share fit.
- **Lead-lag:** distributed lags and block/bootstrap inference; test reverse
  lead first.  It is not causality by itself.
- **Coordination:** null preserving activity and concentration; persistent,
  pre-registered criteria; describe patterns, never intent.

### 7.3 Model tournament

For the centralized inference surface compare, in strict forward evaluation:

1. price-only;
2. price + public performance;
3. price + performance + health/capacity;
4. model/provider fixed-effect baseline;
5. full score-proxy specification.

Report log score, calibration, share-weighted error, leave-model-family-out
performance, and confidence intervals over time blocks.  The preferred
explanation is the simplest model whose forward performance is not materially
worse; a residual is not a discovered router policy.

### 7.4 Cross-market comparison card

For each comparison, publish a compact card:

```text
Mechanism:     e.g., price-plus-quality selection
Inference:     public quote/health proxy; no selected endpoint
Comparator:    Akash accepted lease / Bittensor epoch reward / CoW settlement
Shared metric: pre-registered rank, concentration, or event-time response
Validation:    result on transparent comparator
Conclusion:    exact supported sentence
Non-conclusion: strongest excluded sentence
```

This prevents the paper and dashboard from visually implying common units or
common causal identification.

## 8. Phase 5 — dashboard, paper, and operations (after analysis starts)

### Dashboard

Add five panels, each with a persistent claim-boundary banner:

1. **Inference demand:** model share, `other` share, HHI/entropy, entries,
   source coverage;
2. **Quote and enforcement:** price/performance/health, rate-limit and derank
   event ledger, contiguous-coverage map;
3. **Transparent compute:** Akash bid-to-lease choice and Bittensor
   weight-to-reward allocation, separately selectable;
4. **Transparent execution control:** finalized CoW/Uniswap coverage,
   parent-state quote-to-settlement calibration, estimator pass/fail; and
5. **Evidence board:** all hypotheses ranked by claim level, sample/event
   counts, effect/interval, preregistration state, and explicit next gate.

No panel may show a provider's “routed share” unless that field comes from a
verified realized-selection source.  Public model share must be labelled
model-level aggregate demand.

### Paper structure

1. Market-design problem and identification boundary;
2. layered market comparison and theory;
3. data contracts and coverage;
4. centralized-router public-surface evidence;
5. transparent-comparator validation;
6. cross-market mechanism cards;
7. mechanism proposal / policy implications; and
8. limits, telemetry design, and reproducibility package.

### Operations

- Daily: OpenRouter latest closed day; source-run/coverage alerting.
- Five-minute: existing quote/health and targeted burst collection.
- Hourly: Akash/DeFi/GPU comparators, finality check, source health.
- Epoch/block: Bittensor and finalized chain data.
- Weekly: mapping review, event-registry freeze, dashboard evidence audit.
- Monthly: pre-registration review, data-retention verification, and external
  source terms/revision audit.

Use environment-only credentials and skip-with-ledger behavior.  Do not expose
API tokens in raw payloads, dashboards, notebooks, or git history.

## 9. Prioritized backlog

| Priority | Task | Dependency | Completion evidence |
|---|---|---|---|
| P0 | Run and archive model-rankings historical backfill | authorized dataset credential in job environment | every requested closed UTC day has a valid raw and curated response |
| P0 | Add app-rankings collector and coverage semantics | source-contract review | pagination/rate-limit tests and raw-revision archive |
| P0 | Hydrate enforcement history and event registry | retained five-minute raw data | coverage report plus frozen eligible-event ledger |
| P0 | Repair Akash full bid-universe capture | source pagination/coverage validation | pinned block ledger and resolved bid/lease linkage |
| P1 | Add Bittensor epoch collector | subnet selection rule | 90 finalized epochs and source tests |
| P1 | Establish CoW market-wide historical execution feed | validated source and finality policy | 500 matched executions and estimator-validation report |
| P1 | Build mapping/version tables | source contracts | explicit unmapped rate and mapping change log |
| P1 | Add quality/release event registry | model release and benchmark source policy | preregistered event cohort before outcomes |
| P2 | Exact GPU deployment mapping and pass-through study | independently documented mappings | mapping coverage and aligned-input placebo tests |
| P2 | Chicago rideshare calibration extract | versioned public extract | method-control report and placebo results |
| P2 | Dashboard/paper evidence cards | first passed analyses | static reproducible build with claim labels |

## 10. Stop rules and escalation path

Stop or downgrade an experiment when its central observable remains absent:

| Condition | Action |
|---|---|
| App/model or provider routing relation is top-N/censored | Report aggregate demand only; do not fit app-routing allocation claims. |
| Derank events do not accumulate | Continue descriptive H68 monitoring; do not extrapolate a hazard. |
| Akash bid pagination cannot be made complete | Retain capacity/quote context, remove accepted-choice model. |
| GPU deployment mapping is missing | Keep GPU series contextual, not a cost-shock instrument. |
| DeFi coverage is partial or unfinalized | Keep it as estimator-development evidence, not a matched execution comparison. |
| Shared estimator fails transparent-control validation | Withdraw it from the inference result rather than tune it on inference data. |
| Stronger claim needs request ordering or fill outcome | Escalate to controlled own-traffic probes or a router data partnership. |

The minimum partner export for the final escalation is deliberately small:
anonymous request ID, arrival time, eligible endpoints, decision and retry
sequence, selected endpoint, quote/billed price, terminal status, and
contemporaneous provider quote-update ID.  Payload content, end-user identity,
and provider cost are not needed for the initial analysis.

## 11. Definition of done

The comparison is ready for an empirical paper only when:

1. P0 public-demand and enforcement panels pass coverage gates;
2. at least one transparent-compute selection panel and one DeFi execution
   panel pass their respective gates;
3. one shared estimator has a documented transparent-market validation result;
4. all market cards separate public allocation from realized selection;
5. every headline estimate has a confidence interval, placebo, and pre-trend
   result where applicable; and
6. the conclusion remains valid after removing any market/source whose data
   source is incomplete.

Until then, the correct deliverable is a high-quality measurement and
identification framework—not an assertion that open-model routing is DeFi or
that public evidence reveals MEV.
