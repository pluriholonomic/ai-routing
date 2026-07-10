# Routing-MEV research plan

## Purpose and claim boundary

This plan tests whether inference providers use fast quote or capacity changes
to capture a disproportionate amount of router allocation.  It calls the
behavior **MEV-like** only as an economic analogy: a participant changes a
publicly observable state just in time to capture flow produced by a routing
rule.

It is **not** literal blockchain MEV or front-running.  The public dataset has
no mempool, customer intent, request-level ordering, or provider cost ledger.
Consequently it cannot establish that a provider saw a specific request and
traded ahead of it.  Claims must use the following labels:

| Label | Permitted conclusion |
|---|---|
| `measured` | A quote/rank change preceded excess routed requests or token share under the stated event-study design. |
| `provisional` | The timing and signature match a routing-volume-capture mechanism, but an alternative capacity, launch, or demand explanation remains. |
| `not identified` | Profit, private order-flow knowledge, a specific router implementation detail, or customer harm cannot be recovered from public data. |

The current evidence is a useful starting point, not a result on MEV:

- H4 finds that lower effective price is associated with higher routed share.
- H17/H21 find a small, young set of quote reactions.
- H10 rejects the cross-sectional version of phantom liquidity: cheap quotes
  do not have significantly higher reject rates.
- H8 has not yet captured a high-frequency event window.

The goal is therefore to measure **routing-volume capture first**, then
separate normal price competition, router-rule gaming, and harmful
quote-and-ration behavior.  Profit is a third, separately gated step.

## Economic object and common clock

The unit is one endpoint `i` serving a fixed `(model m, variant v)` market at
event time `t0`.  Let `p_imt` be its listed completion-token quote, `q_imt`
an endpoint request/flow proxy, `s_imt` its routed share, `c_imt` capacity and
quality state, and `r_imt` its rejection rate.  For each event create a
balanced panel from `t0 - 60 minutes` to `t0 + 24 hours`.

Use three time scales rather than mixing them:

| Horizon | Outcome | Current source | Correct use |
|---|---|---|---|
| 5 minutes | quote, relative rank, quality/capacity state | `endpoints_snapshots` | Event definition and pre-event controls. |
| 30 minutes | endpoint request count, success/reject rate, utilization | `congestion_intraday` / `event_bursts_congestion` | Short-run allocation and quality response for covered hot models. These are rolling windows, not independent one-minute fills. |
| day | provider token share and effective paid price | `effective_pricing_daily` | Durable allocation and revenue-proxy response. |

Only compare endpoints that were simultaneously available, non-free, and
healthy before `t0`.  Keep the full competitor set in every event window,
including endpoints that did not change price.  Use `run_ts`, never workflow
schedule time.

## New derived contract: `routing_event_panel`

Build one auditable event table before fitting any hypothesis.  One row is
`event_id × endpoint × relative bucket`, with a raw-payload pointer and these
fields:

```text
event_id, model_id, variant, event_ts, endpoint_uuid, provider_name,
event_type, old_price, new_price, dlog_price, relative_price,
best_other_price, rank_before, rank_after, newly_best,
price_tick_bps, provider_wave, launch_event, competitor_event,
capacity_ceiling_rpm, recent_peak_rpm, utilization, latency, throughput,
request_count_30m, success_30m, rate_limited_30m, deranked,
lead_minutes, lag_minutes, outcome_window, source_run_id, quality_status
```

`relative_price = log(p_imt / min_{j != i} p_jmt)` is the shared running
variable.  Write a companion `routing_event_cohort` table with inclusion and
exclusion reasons; never silently drop a failed or unavailable endpoint.

The first module should construct the table from the existing sources and
report coverage only.  It must flag, rather than infer, missing intraday flow,
rolling-window overlap, quote gaps, and source-health failures.

## Hypotheses and tests

### R1 — Router-rule threshold gaming

**Mechanism.** A provider chooses a quote just below the best competitor, or
just below a router-relevant price boundary, to receive discontinuously more
routing volume.  This is the cleanest analogue to priority-gas or
liquidity-position gaming because the gain comes from a known allocation rule,
not from serving a better product.

**Predictions.** There is excess density immediately below relative price
zero, price cuts disproportionately cross from rank >1 to rank 1, and
endpoint flow jumps at that crossing more than it changes for similarly sized
non-crossing cuts.

**Estimator.** First run a bunching test on the post-change
`relative_price`; report the density on both sides of zero and placebo
thresholds at +/-5%, +/-10%, and +/-25%.  Then estimate a local event-study
or regression discontinuity:

\[
y_{i,m,t_0+h}=\tau_h\,1[relative\_price_{i,m,t_0}<0]
+ f(relative\_price_{i,m,t_0}) + \alpha_i + \gamma_{m,t_0} + X'\beta + \epsilon,
\]

where `y` is endpoint request-share at 30 minutes and provider token-share at
one day.  `X` includes pre-event utilization, capacity, latency, throughput,
quality tier, and quote age.  Cluster by model-event and use a block bootstrap
over events.

**Decision rule.** Call it `measured router-rule capture` only if (1) the
price density bunches below zero, (2) post-event flow has a positive jump,
(3) leads are flat, and (4) the effect is absent at placebo thresholds.  A
smooth flow response is normal price competition, not threshold gaming.

**Power gate.** At least 150 rank-crossing events across 40 markets, with 30
minutes of pre/post coverage for a balanced competitor set.  Report the
eligible-event fraction and all exclusions.

### R2 — Undercut-and-capture

**Mechanism.** A provider makes a discrete cut, becomes uniquely best or
materially improves rank, and captures routing volume before competitors can
respond.

**Treatment and controls.** Treatment is a >=5 bp cut that improves rank by
at least one position; the preferred cohort becomes uniquely best.  Controls
are non-moving endpoints in the same `(model, variant)` at the same event.
Exclude launches, provider-wide price waves, endpoint additions/removals, and
events with a preceding capacity change.  Preserve them as separate cohorts.

**Estimator.** Estimate relative shares in an event-time difference in
differences with endpoint and model-time fixed effects.  Show coefficients
for `-60, -30, +30, +60, +180 minutes` and `+1, +3, +7 days`.  The short-run
effect is request share; the daily effect is token share and effective price.
Report the impulse-response elasticity:

\[
\varepsilon_h = \frac{\Delta \log s_{i,m,t_0+h}}
{-\Delta \log p_{i,m,t_0}}.
\]

**Falsifiers.** A rising pre-trend, a contemporaneous capacity expansion, or
an equal effect for non-moving competitors rejects the volume-capture
interpretation.  A post-cut effect that survives only at one day is compatible
with customer switching rather than fast router allocation.

**Power gate.** 50 clean cuts for a daily result; 20 with balanced intraday
coverage for a short-run result.  The existing H4 coefficient is only a
cross-sectional prior, never a substitute for this test.

### R3 — Stale-quote / competitor-shock capture

**Mechanism.** Provider `i` does not move, but another provider raises its
price, exits, or becomes unhealthy.  `i` inherits best-price status and gains
flow before updating its own quote.  This is the strongest public-data
analogue to a latency-arbitrage test because the focal provider did not choose
the initial price event.

**Treatment.** A competitor-only event causes `i` to become uniquely best;
`i` has no price, capacity, or quality change in the preceding hour.

**Estimator.** Use the same event-time share panel as R2, anchored on the
competitor event.  Match each treated endpoint to endpoints that nearly became
best but did not, within model liquidity/number-of-provider strata.  Estimate
the temporary flow gain and the focal endpoint's subsequent repricing hazard.

**Interpretation.** A temporary gain followed by `i` raising its own price is
evidence of valuable stale quotes, not front-running.  Calling it
front-running would require proof that `i` knew the competitor event or a
specific customer intent beforehand; public data cannot provide that proof.

**Power gate.** 100 competitor-only best-price transitions and successful
placebo tests at unrelated event times.

### R4 — Quote-and-ration (dynamic phantom liquidity)

**Mechanism.** A provider cuts to receive router flow, then rations it through
rate limits, deranking, capacity reductions, or a rapid price reversal.  This
is the inference analogue of a quote that is attractive but not reliably
executable.

**Why a dynamic test is necessary.** H10's cross-sectional price-versus-
rejection result is not significant; it rules out neither short-lived behavior
nor a strategy used only after a large rank gain.

**Joint outcomes.** For treated R2 events, estimate changes in successful
requests, reject rate, `capacity_ceiling_rpm`, utilization, derank state, and
quote reversal within 24 hours.  Classify an event only when its pre-committed
signature is met:

1. becomes best and receives excess requests;
2. success does not increase proportionally;
3. reject rate rises, capacity falls, or the quote reverses; and
4. the same sequence is rare in matched non-cut events.

Use a stacked event study with separate outcomes instead of multiplying them
into an opaque score.  For rolling 30-minute status fields, use non-overlapping
post windows or a window-overlap robust covariance estimator.

**Decision rule.** A price cut plus a rejection increase alone is not enough:
capacity pressure may be genuine.  Report `quote-and-ration` only with the
full sequence and a quality-adjusted successful-flow result.  Otherwise label
it a capacity response.

**Power gate.** 50 clean rank-improving cuts and at least 20 events with an
observable post-event capacity or reject response.

### R5 — Selection into costly flow (inference LVR analogue)

**Mechanism.** Aggressive quotes attract a mix of requests that is more costly
to serve per billed token: low cache use, longer requests, higher reasoning
load, more tool-error loops, or subsidized free traffic.  The economic loss is
analogous to adverse-selection/LVR only if the new flow is both selected by
the quote and costly relative to revenue.

**Current screen.** H23 constructs a model-day toxicity factor from those
five components and relates it to aggregate reject rates.  This is a
plausibility screen, not endpoint-level causal evidence: the flow mix is not
currently observed by provider.

**Public-data test.** Around R2 price cuts, estimate model-level changes in
the toxicity components against matched non-moving markets.  Require no
pre-trend and show each component; do not rely on a composite alone.  This
can establish that a price war changes market-level flow composition, but not
that the cutting provider received the costly requests.

**Required upgrade for a provider-specific claim.** Obtain provider/end-point
telemetry at a fixed, privacy-preserving grain: request counts, billed input
and output tokens, cached/reasoning tokens, latency, error class, and realized
GPU-seconds or contribution margin, in five-minute buckets.  With that data,
estimate a binomial rejection model and a cost/margin event study with
provider-model and time fixed effects.

\[
margin_{i,m,t} = revenue_{i,m,t} - gpu\_seconds_{i,m,t}\times gpu\_cost_{i,t}.
\]

Without the right-hand cost data, say **high-cost-flow selection**, never
provider loss or profitable MEV.

### R6 — Reaction cascades and quote following

**Mechanism.** Automated providers monitor peers and rapidly match or
undercut quotes.  The potential harm is not a single front-run; it is a
self-exciting price/routing cascade that rewards the fastest repricer.

**Estimator.** Strengthen H21 by pairing each leader event with a matched
non-event time for the same `(follower, model)`.  Estimate (a) the follower's
hazard of changing price, (b) direction and magnitude of its response, and
(c) its share gain after the response.  Generate a directed reaction graph
only after comparing its edges with a time-permuted null and excluding
provider-wide waves.

**Decision rule.** A fast same-direction reaction is evidence of strategic
complementarity.  An undercut followed by R2 volume capture is evidence of
competitive quote chasing.  Neither by itself proves coordination or MEV.

**Power gate.** 100 follow pairs for aggregate reaction functions; 30
leader-follower events with usable flow outcomes for the volume leg.

### R7 — Privileged-flow or informed-capacity anticipation

**Mechanism.** A provider changes price/capacity before an otherwise
unforecastable routing surge, perhaps because it has private booking,
capacity, or order-flow information.

**Public-data test.** Fit a strictly out-of-sample model of future flow using
all public state available at `t-`: quotes, rank, capacity, utilization,
latency, model age, competitor moves, and time effects.  Test whether an
endpoint's own action predicts the residual future-flow surprise.  Use only
actions that precede the surprise and report lead coefficients and placebo
future-action tests.

**Hard boundary.** Predictive lead-lag is compatible with superior forecasting
or private capacity information.  It is not evidence of front-running.
Identifying private customer order-flow use requires router/provider audit
logs with request arrival, routing decision, quote version seen, and execution
timestamps.

## Implementation sequence

### P0 — Preserve the identifying data (implemented 2026-07-09)

1. [x] Add an event extractor (`h42_routing_mev.py`) that reads
   `pricing_changes`, `endpoints_snapshots`, and congestion tables into the
   `routing_event_panel` contract.  Its first run reports coverage and does
   not fit effects.
2. [x] Add a permanent 5-minute competitor-set snapshot for every detected price
   event, plus a 60-minute pre-event and 180-minute post-event manifest.  The
   existing burst sampler only begins after detection; do not misrepresent it
   as pre-event one-minute data.
3. [x] Expand hot-model congestion coverage dynamically to all models with a
   price event for the event window, not only the static top-40.  Keep source
   run IDs and raw responses.  The H42 loader now prefers targeted burst rows
   when they overlap a regular congestion sample, preventing double counts.
4. [x] Store event eligibility and the precise observed pre/post coverage in a
   `routing_event_quality` table.  An unavailable flow source makes an event
   ineligible rather than zero-flow.
5. [x] Add synthetic tests for rank crossings, event-time flow response, and
   the post-only burst-manifest boundary.  Test event alignment and rolling-
   window aggregation explicitly.

### P1 — Descriptive screen and dashboard (after the first eligible events)

1. Produce a quote-rank timeline for each event: all providers' prices,
   availability, capacity, and flow proxy.
2. Report R1 bunching and R2/R3 pre-trends before any post-event conclusion.
3. Surface an event card only as a `candidate`, with raw-source links and a
   reason code.  Do not trigger an “MEV” alert from a single event.
4. Maintain an event ledger with cohort counts, exclusions, and power against
   each gate.  The research dashboard should show `eligible / observed`, not
   merely the most striking examples.

### P2 — Causal comparisons (once gates are met)

1. Run stacked event studies for R2–R5 with endpoint/model/time fixed effects
   and clustered or block-bootstrapped uncertainty.
2. Run R1 density and threshold tests with pre-registered bandwidths and
   placebo boundaries.
3. Run R6 against time-permuted and provider-wave nulls.
4. Freeze cohort definition, horizons, controls, and minimum effect size in a
   small TOML specification before examining final outcome coefficients.
5. Publish both the full result and the negative/failed hypotheses in the
   memo; a lack of post-event share response is an informative result.

### P3 — Margin and customer-harm upgrade (partner data required)

1. Negotiate a privacy-preserving provider/router telemetry export at
   endpoint × five-minute grain; no prompts, customer identities, or raw
   request content are needed.
2. Add contribution margin and successful completion outcomes to R4/R5.
3. Create a quote-version-to-routing-decision audit: quote visible at request
   arrival, routing choice, fallback/retry chain, final success, and realized
   serving cost.
4. Only at this stage quantify captured gross revenue, incremental margin,
   customer latency/failure harm, and any privileged-information advantage.

## Optimising the research program

Here “optimise” means maximise credible detection and identification, not
help a provider exploit routing.

1. **Prioritise natural rank transitions over more correlations.** R3 is
   higher value than a larger H4 regression because a competitor's move changes
   the focal provider's relative price without a focal quote decision.
2. **Spend capture budget around events.** Keep universal five-minute quotes,
   then allocate finer event coverage to markets with two or more healthy
   providers, a close best/second-best gap, and observed intraday flow.  This
   raises identification value per request without silently selecting only
   spectacular events.
3. **Optimise for successful flow, not posted price.** Every result should
   place requested flow, successful flow, rejection, capacity, and quality
   side by side.  A cheap quote without successful completions is not a gain
   to routing users.
4. **Use an explicit candidate score only for sampling.** Rank events by a
   pre-outcome score: rank improvement, quote-size change, number of healthy
   competitors, and data completeness.  Exclude future flow, rejects, or
   revenue from the score to avoid selecting on the dependent variable.
5. **Separate frequency from harm.** Frequent price following may be ordinary
   competition.  Require an excess-flow effect for volume capture, and a
   subsequent quality/margin effect for harmful MEV-like behavior.
6. **Protect against self-deception.** Use frozen event rules, placebo dates,
   negative-control models, unreported-withheld outcome windows, raw response
   retention, and a visible power ledger.  The first publishable result may
   correctly be “no evidence of routing-rule gaming.”

## Deliverables and stop conditions

| Deliverable | Definition of done |
|---|---|
| Event panel | Schema-valid parquet plus raw pointers, coverage/exclusion report, and synthetic alignment test. |
| Candidate dashboard | Timeline and cohort ledger; every card labeled candidate/measured/provisional/not identified. |
| R1/R2/R3 report | Pre-registered estimators, pre-trends, placebo results, power denominator, and all outcome horizons. |
| R4/R5 report | Successful-flow and quality sequence; provider-cost boundary stated prominently. |
| Partner-data upgrade | Signed data contract and reproducible, privacy-preserving margin calculation. |

Stop a hypothesis when its falsifier is met: no bunching or discontinuity for
R1; no post-event share shift for R2/R3; no quality sequence for R4; no
post-cut flow-composition change for R5; no excess reaction over the null for
R6.  Preserve those negative results in the memo rather than expanding the
specification until a signal appears.
