# Router expansion priority (2026-07-16)

## Decision

Add **Glama** and **Requesty** to the market-comparison panel first. Add
**NemoRouter** as the next managed-router comparator. Treat **TrueFoundry** and
**TokenRouter** as controlled mechanism laboratories rather than as independent
public provider markets.

The distinction is important. A new gateway is useful for the provider-market
question only if it exposes at least two of the following:

1. a timestamped provider/model quote surface;
2. the upstream selected for a request, including fallbacks;
3. an independently varying routing rule;
4. request-level cost, token, latency, and error telemetry.

Adding a second OpenAI-compatible URL without these objects would increase
integration count without improving identification.

## Source audit

| Priority | Router | Public no-key surface verified | Owned-traffic observability | Research role | Limitation |
|---|---|---|---|---|---|
| P0 | Glama | `GET https://gateway.glama.ai/v1/models`; public model pages report provider prices and describe automatic provider choice | Request logs include provider, tokens, cost, duration, and status; JSON export is advertised | Closest same-model, multi-provider comparator to OpenRouter; estimate route switching as price, reliability, and latency change | Full provider menu is page-oriented rather than documented as one structured public endpoint; realized logs require an account |
| P0 | Requesty | `GET https://router.requesty.ai/v1/models` returns a large provider-prefixed catalog with input/output prices and capabilities | Analytics exposes selected model, failures, fallback use, tokens, cost, and latency; CSV export and policy filters are documented | Cross-router quote panel plus randomized operator-defined fallback, weighted, and latency policies | Policies generally choose across explicitly configured endpoints; this is not market-wide flow |
| P1 | NemoRouter | `GET https://nemorouter.ai/api/public/models` returns provider, mode, and per-token prices | `x-nemo-routed-by` plus request logs for strategy, primary, fallback, retries, cost, and latency; external callbacks are documented | Transparent managed-router benchmark and fee/pass-through comparison | Current catalog is concentrated in a few upstream provider families and routing is operator-controlled |
| P1-lab | TrueFoundry | No common managed marketplace quote surface; customers attach provider accounts | Self-hosted or managed traces, upstream-provider response field, OpenTelemetry export, and weight/latency/priority policies | Best controlled laboratory for testing a known allocation rule and validating estimators | It measures our configured procurement mechanism, not an independent two-sided marketplace |
| P2-lab | TokenRouter | No public `GET /v1/models` endpoint was found; docs expose four routing modes and their score weights | Response metadata reports provider, routing mode, and routing confidence; console has per-request trails | Query-level model-choice and score-sensitivity experiment | Primarily routes across model/provider families; no public provider quote history and no documented pre-trade candidate scores |

## Experiments unlocked

### R1. Cross-router quote and menu panel

Canonicalize exact model versions across OpenRouter, Hugging Face, Glama,
Requesty, and NemoRouter. Capture provider, input/output/cache price, context,
capabilities, and availability at the native public cadence. Estimate:

- within-model price dispersion and cheapest-provider persistence;
- tie and price-atom rates;
- direct-versus-router basis by provider;
- quote-update synchronization across routers; and
- whether the same upstream changes price everywhere or only on one venue.

This panel separates provider-wide repricing from router-specific menu
administration.

### R2. Realized-route crossover

For exact overlapping open-weight models, send payload-safe one-token probes in
randomized blocks through OpenRouter, Glama, Requesty, and NemoRouter. Record the
declared policy, candidate set where controlled, selected upstream, attempt
order, success, latency, tokens, and cost. The primary estimand is the change in
selection probability for an upstream after its relative price changes, with
router-by-price interactions.

The most informative comparison is not the raw selected share. It is whether
the same public price shock reallocates traffic differently under different
router rules.

### R3. Revenue-stationarity replication

For router `r`, provider `i`, model `m`, and block `t`, construct owned-probe
quantity share `s_rimt` and public revenue-proxy share
`e_rimt = p_rimt s_rimt / sum_j(p_rjmt s_rjmt)`. The exact identity

`log(s_rimt) = log(e_rimt) - log(p_rimt) + market price index`

must hold router by router. Estimate the provider/model fixed-effect price
coefficient and its corresponding revenue-gradient coefficient. Cross-router
agreement would support a provider-market pricing law; large router interactions
would instead locate the result in allocation policy.

### R4. Policy frontier and estimator validation

Use Requesty, NemoRouter, and TrueFoundry to randomize known cost-, latency-,
weighted-, and priority-routing rules over the same endpoint set. This creates a
ground-truth laboratory for testing whether the public shadow router recovers:

- route probabilities;
- fallback order;
- price elasticity;
- stale-quote capture; and
- welfare regret under declared quality/latency weights.

OpenRouter and Glama then supply the externally administered policies whose
rules are not fully observed.

## Minimum viable rollout

1. Add secret-free daily catalog collectors for Glama, Requesty, and NemoRouter.
2. Preserve raw responses and normalize to a common `router_quote_snapshots`
   table without fuzzy model joins.
3. Extend `router_route_attempts` and its redacted import formats to the three
   managed routers.
4. Start with one canonical open-weight overlap set and 24 randomized blocks per
   router-day; do not expand model count until selected-upstream fields are
   verified end to end.
5. Run all collectors remotely and publish only payload-free normalized records.

No key is required for the three public catalog collectors. Realized-route
experiments require dedicated study keys and explicit spend caps. None of these
owned panels measures another user's flow or literal cross-user front-running.
