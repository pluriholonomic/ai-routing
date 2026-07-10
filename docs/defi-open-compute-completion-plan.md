# Completing the DeFi vs. open-compute market comparison and live monitor

## Decision

Build a **matched market-microstructure comparison**, not a collection of
crypto price series beside GPU rental prices.  The target is to measure how a
buyer acquires a unit of capacity or execution in each market:

| Common economic object | Inference / open compute | DeFi comparator |
|---|---|---|
| Quote | OpenRouter provider endpoint price; Vast/Akash/Golem resource offer | AMM marginal executable quote; CoW solver/auction quote |
| Available capacity | Remaining endpoint RPM/TPM; rentable GPU inventory | AMM depth near mid; solver/auction executable liquidity |
| Execution quality | latency, throughput, error/reject rate, uptime, region/GPU | gas-inclusive output, fill/settlement probability, latency/finality |
| Flow | tokens, requests, routed provider share | swaps, auction orders/trades, volume, order flow |
| Friction/risk | interruption, provision time, SLA, router derank | gas, price impact, MEV/LVR, failed/reverted transactions |
| Market structure | provider concentration, entries/exits, quote revisions | LP/solver concentration, liquidity changes, price revisions |

This is the appropriate level for testing the repo's existing RFQ/AMM
analogies.  Aggregate TVL, token prices, base fee, and hashprice remain useful
controls, but are not the primary comparison dataset.

## What exists and what is missing

| Area | Existing evidence | Gap that prevents a full claim |
|---|---|---|
| OpenRouter quotes | all endpoints sampled at five-minute resolution, plus provider price changes | young live panel; posted list prices are not guaranteed executable fills |
| OpenRouter execution | daily frontend effective pricing, uptime, comparisons; hot-model congestion | no client-level fills, no request timestamps, and only router-estimated capacity |
| Direct inference basis | structured daily DeepInfra, Cerebras, SambaNova, and Chutes catalogs; Groq/Together exact-ID docs tables; Novita and BaseTen literal public SSR catalogs; and two Fireworks exact-ID serverless pages | Groq, Together, Novita, BaseTen, and Fireworks are posted quotes. Chutes's TEE-suffixed IDs and BaseTen's publisher/library slugs require versioned one-to-one maps before joining OpenRouter canonical IDs. Coverage remains too narrow for a market-wide conclusion. |
| Open GPU supply | hourly Vast offer books (on-demand and bid) plus Lambda's published per-GPU-hour instance tables | Vast is the only offer book; Lambda list prices carry no availability, utilization, or execution evidence, and there is no region/quality-normalized cross-venue index |
| Forward/carry | Vast duration buckets plus static anchors | heterogeneous, sparse forward anchors; no tradable same-venue curve |
| DeFi macro controls | base fee, two Uniswap V3 pool prices, CoW sender counts, BTC funding/hashprice | no event-level depth, volume, gas-inclusive execution, solver identity, or time-aligned cross-venue universe |
| DeFi monitoring | manual `orcap defi` fetch and cached parquet | no workflow, freshness SLO, source status, raw archive, or downstream analysis integration |
| Reproducibility | raw capture, source registry/run ledger, and synthetic estimator tests for core collectors | DeFi feeds still lack complete production schemas and freshness coverage; analyses need final matched-data gates before any full-market claim |

## Source plan

Use sources in tiers.  Tier 1 is necessary for the central claim and must be
production monitored.  Tier 2 measures external validity.  Tier 3 is useful
context and must never substitute for Tier 1.

### Tier 1: matched transaction and capacity data

| Source | Why it is needed | Capture grain / cadence | Access and caveat |
|---|---|---|---|
| Ethereum logs or a dedicated [Uniswap V3/V4 subgraph](https://thegraph.com/docs/en/subgraphs/querying/introduction/) | swap, mint, burn, collect, tick/liquidity events for a fixed ETH/USDC universe | block/event; ingest hourly and finalize after a reorg buffer | Prefer canonical logs from an RPC/archive provider for production; a Graph subgraph is a fast query layer but has an indexing lag and requires an API key. |
| CoW Protocol order/trade/auction data plus settlement logs | RFQ/solver comparator: orders, fills, solver outcomes, settlement prices, surplus and auction cadence | auction/trade; ingest every 5–15 minutes | The public `solver_competition/latest` endpoint now yields a bounded live competition snapshot (auction block range, candidate-solver ranks, and winner flag). It is not historical trade history or a fill feed. For Tier 1, index GPv2Settlement or use a properly scoped official/Dune feed; transaction sender alone is not a solver identity. |
| [Akash public Network Data API and chain REST/RPC](https://akash.network/docs/api-documentation/getting-started/) | decentralized compute provider-level GPU availability, aggregate model USD/hour quotes, lease-contract lifecycle, and block-pinned open GPU bids from the current live-GPU-provider universe | hourly availability/quotes, newest lease contracts, and provider-filtered bid snapshots | Implemented without credentials. Provider GPU totals are not allocated across advertised models; lease state/native rate is not a workload-success. The bid panel is coverage-restricted, native per-block price only, and not an all-network demand/fill book. H47 only compares explicit exact GPU specifications to Vast offers. |
| [Golem Stats API](https://docs.stats.golem.network/) | independent decentralized-compute provider availability, requestor activity, agreement outcomes, and provider hardware | hourly network/provider snapshots | Free public JSON API.  It is a distinct, lower-capability network, so analyze separately instead of blending its prices with GPU cloud rates. |
| [Chutes public model and chute-detail APIs](https://llm.chutes.ai/v1/models) | independent decentralized serverless-inference supply configuration plus a source-defined cumulative invocation counter | hourly catalog plus one public detail response per current chute; H53 differences only adjacent counter observations | Implemented. Active instances × configured GPUs is a deployment-configuration proxy. H53's counter delta is not successful completions, tokens, unique users, revenue, utilization, available capacity, or realized routing allocation. |
| [Vast offer book](https://docs.vast.ai/api-reference/search/search-offers) (existing) | high-frequency open GPU supply, interruption premium, hardware and host attributes | hourly full-book snapshots | Keep on-demand and bid offers separate; add region, reliability, GPU RAM, verification, duration, and rentable/rented status to the canonical index. |

### Tier 2: market-wide controls and validation

| Source | Use | Cadence / access |
|---|---|---|
| [DefiLlama](https://docs.llama.fi/) TVL, DEX volume, fees/revenue, yields, stablecoin supply | universe controls, market-regime controls, and coverage validation | hourly/daily API series; aggregate data only, never a substitute for execution data |
| [Dune](https://docs.dune.com/api-reference/api-overview) saved parameterized queries | cross-checks, rapid historical backfill, complex multi-protocol aggregates | API key and credit budget; cache each execution result with query ID, SQL hash, execution ID, and block/time watermark |
| [The Graph](https://thegraph.com/docs/en/subgraphs/querying/introduction/) | queryable subgraphs for protocol-specific state and historical entities | API key; pin subgraph deployment ID and record indexed block so a query is reproducible |
| [GeckoTerminal pool API](https://api.geckoterminal.com/docs/index.html) | public live price, reserve proxy, and volume control for the registered Uniswap pools | Implemented as an optional indexed-state control; it is not a finalized-log, executable-depth, or fill source |
| OpenRouter direct providers | direct vs routed venue basis | DeepInfra, Cerebras, SambaNova, and Chutes structured APIs plus Together, Groq, Fireworks, Novita, and BaseTen typed adapters are implemented. Chutes maps its TEE-suffixed direct IDs only when a versioned literal root and quantization pair agrees with a current Chutes OpenRouter endpoint. Novita accepts only active chat models with exact API IDs and displayed USD-per-million prices. BaseTen accepts only literal public publisher/library slugs and price fields, then uses a separately versioned current router pair. Lambda's token Inference API is winding down; qualify any other provider with a public structured model/pricing endpoint next. Hyperbolic's unauthenticated model API returned 401 and its older pricing pages now redirect, so it requires a provider-approved public feed rather than an account-specific billing workaround. Archive HTML only as fallback evidence. |
| [Lambda public instances page](https://lambda.ai/instances) | commercial on-demand GPU list-price control | Implemented as a strict parser for literal 1x/2x/4x/8x instance tables with plan, VRAM, and per-GPU-hour USD fields. It is a posted commercial price panel, separate from Lambda's winding-down token inference API and from offer-book availability or utilization. |
| [Runpod public posted pricing](https://docs.runpod.io/serverless/pricing) | commercial/serverless price control | daily page/table extractor; account-scoped usage and billing endpoints are not market-wide data and must not be used as such |

The implementation records public DefiLlama data immediately. Configure the
other feeds through environment-only settings: `ORCAP_COW_TRADES_URL` for a
properly scoped market-wide CoW feed (not the identity-scoped public
`/api/v2/trades` route), `ORCAP_GOLEM_STATS_URL` for
the current Golem endpoint, `ORCAP_AKASH_NETWORK_URL` and optional
`AKASH_API_KEY` for the chosen Akash network-data feed, and `GRAPH_API_KEY`,
`ORCAP_UNISWAP_SUBGRAPH_ID`, and `ORCAP_UNISWAP_POOLS` for the pinned Uniswap
subgraph/cohort. Until configured and producing data, they remain visibly
degraded rather than being treated as a complete comparison.

For finalized Uniswap event collection, the monitor defaults to dRPC's
documented public Ethereum RPC for a bounded recent window and a 64-block
reorg buffer. Set `ORCAP_ETHEREUM_RPC_URL` to an archive-capable endpoint to
override this fallback for stronger uptime and historical coverage. Operators
may set `ORCAP_ETHEREUM_FINALITY_BLOCKS` and
`ORCAP_UNISWAP_LOG_WINDOW_BLOCKS` within the documented 1--10,000 bounds. It
normalizes `Swap`, `Mint`, and `Burn` logs with an immutable
transaction-hash/log-index identity. The public fallback is strictly a
recent-finality monitor, never an archive/backfill source; configured endpoints
are redacted from raw evidence. Swap logs identify finalized execution and
liquidity-event incidence, not USD executable depth; depth still needs a
position/tick construction at explicit notional buckets.

The default finalized log window is 1,024 blocks, deliberately overlapping the
hourly workflow by roughly an hour or more at observed Ethereum cadence. H41
now computes the union and uncovered blocks across recorded Uniswap and CoW
query windows. A single valid window is not treated as a continuous panel;
dynamic estimates require repeated overlap and explicit zero uncovered blocks.
For the registered USDC/WETH pools, H41 keeps QuoterV2 prices separate by pool
and input-USDC bucket, while CoW's exact-pair fills are reported separately by
direction in the explicit `usdc_per_weth` quote unit. Neither object is silently
converted to USD or treated as executable depth.

H52 additionally simulates each observed exact USDC-to-WETH CoW sell through
each registered pool at the settlement block's parent state, for the identical
USDC input. This yields a reproducible **pre-block gross venue basis** by pool.
It excludes CoW fees, gas, surplus, intra-block ordering, and price movement in
the settlement block; it is not a best-execution, adverse-selection, depth, or
market-wide CoW claim. The analysis stays power-gated until it has 500 fills,
seven days, and both registered pools.

The monitor additionally calls the official mainnet
[Uniswap V3 QuoterV2](https://developers.uniswap.org/docs/protocols/v3/deployments/v3-ethereum-deployments)
with six exact-USDC input buckets (100 through 10 million USDC) for each
registered pool, pinned to the same finality-buffered block. These rows are a
reproducible fixed-notional price-impact curve (amount out, post-quote price
state, initialized ticks crossed, and quoted gas), not a transaction, firm
quote, fill guarantee, or market-wide executable depth. They strengthen the
AMM comparison but do not clear the depth gate on their own.

Across a sparse fixed USDC ladder, the monitor also records the largest
successful input point within 100 and 500 basis points of the smallest
same-block all-in simulation. These are explicitly **state-derived,
discrete lower bounds** on local price-impact capacity: they do not reconstruct
the complete tick book, represent total or market-wide liquidity, or guarantee
a subsequent fill. They are retained separately from both the fixed-notional
curve and the finalized-depth gate.

The same archive-capable RPC path also queries the verified mainnet
`GPv2Settlement` contract for `Trade` and `Settlement` events in a separate
bounded window (`ORCAP_COW_LOG_WINDOW_BLOCKS`, with the same finality buffer).
A `Trade` is an executed order with exact raw token quantities; a solver is
recorded only when the contract emits a `Settlement` event in that same
transaction. Transaction sender is never substituted for solver identity.
Token decimals, USD price, gas-inclusive cost, surplus, and global order
coverage remain separate missing inputs rather than being inferred from this
event pair.

### Tier 3: contextual series

Keep Ethereum base fee, BTC funding, BTC hashprice, and static forward anchors
as background comparators.  Label them contextual.  They cannot identify
inference quote formation, DeFi liquidity depth, or a compute-market
clearing price.

## Canonical data model

Create `src/orcap/sources/` with one adapter per source and normalize to these
tables.  Each table carries `source`, `source_id`, `observed_at`,
`finalized_at`/`block_number` where applicable, `ingested_at`, raw-payload
pointer, schema version, and mapping version.

| Table | Grain | Essential columns |
|---|---|---|
| `market_quotes` | source × instrument × venue × timestamp | bid/ask or marginal price, USD and native denomination, size/depth, quote type, quality tier |
| `market_executions` | source × execution/trade/order × timestamp | side, requested/filled size, gross/net price, fees, gas, success/revert, latency, counterparty/solver where observable |
| `market_capacity` | source × provider/pool × resource × timestamp | available, utilized, total, resource/GPU/config, region, reliability/quality flags |
| `akash_market_open_bids` | pinned block × live GPU provider × bid resource | provider-filtered open GPU bid resources, native per-block amount/denom, resource attributes, and declared coverage universe; neither fills nor capacity |
| `market_participants` | source × provider/LP/solver × day | inventory/liquidity proxy, entries/exits, volume, share, uptime/fill metrics |
| `market_events` | source × immutable event ID | add/remove/reprice/depth change/incident, event time and finalized block/time |
| `instrument_map` | canonical instrument × source identifier × validity interval | model or GPU compatibility cohort; pool/pair/fee tier; precision and quality mapping |
| `source_runs` | collector run | code SHA, source watermark, rows, checks, schema hash, outcome, degradation reason |

Do not force all markets into the same physical unit.  Build comparison
cohorts first:

- inference: exact model plus quantization/context/throughput and SLO tier;
- GPU compute: GPU class, GPU count, RAM, region, commitment/interruption
  type, and reliability tier;
- AMM: exact asset pair, fee tier, chain, and notional-size bucket;
- solver/RFQ: exact pair, order-size bucket, chain, and settlement interval.

## Analysis program

### A. Descriptive microstructure (runnable after 2–4 weeks)

Measure the same objects at matched frequency and size buckets:

1. executable quote dispersion and best-to-second-best gap;
2. depth and price impact at 0.1×, 1×, and 2× median demand;
3. quote/liquidity update hazard, duration, and jump-size distribution;
4. concentration (HHI), turnover, entry/exit, and participation persistence;
5. rejection/fill/settlement success conditioned on the apparently best price;
6. gross price, explicit fee, gas, and quality-risk-adjusted all-in price.

Report distributions by cohort rather than a single cross-market average.
The hard boundary: the inference book is an ask-only *implied* book, while
AMM depth is on-chain and CoW clearing is batch-auction based.  Compare the
same economic metric, but retain market-mechanism labels.

### B. Dynamic tests (after sufficient event power)

- **Shock transmission:** local projections/event studies around exogenous
  compute supply changes, DeFi gas/volatility shocks, and provider/LP/solver
  entries.  Estimate quote, depth, and fill responses at common horizons.
- **Inventory response:** model capacity/depth changes as a function of lagged
  demand and adverse-selection proxies.  For AMMs use realized volatility,
  order-flow imbalance, and LVR proxies; for inference use congestion,
  rejection, throughput, and toxicity.  Do not claim common inventory control
  unless common specifications fit.
- **Entry pass-through:** staggered event study of provider/LP/solver entry,
  with cohort and time fixed effects, and pre-trend checks.  Treat endpoint
  addition as exposure, not proof of available capacity.
- **Router/aggregator welfare:** calculate price improvement only from
  executable counterfactuals.  For inference, the counterfactual must include
  routing/failover quality; for DeFi, it must include gas and price impact.

### C. Identification safeguards

- Freeze cohorts, event definitions, horizons, and minimum sample gates before
  fitting the cross-market comparison.
- Use finalized chain data and a declared reorg window; retain provisional and
  final rows separately.
- Cluster uncertainty by the unit receiving the shock and use block/time
  bootstrap where event overlap is material.
- Use a negative-control pair/model/GPU cohort and placebo event dates.
- Maintain an explicit `measured` / `provisional` / `not identified` label in
  every summary.  Cross-sectional price-flow correlations remain descriptive.

## Live monitoring design

### Source registry and health gates

Add a checked-in `config/sources.toml` with source owner, required/optional
classification, cadence, freshness SLO, expected row floor, stable key,
schema fingerprint, auth variable, reorg/finality policy, and backfill
window.  A collector emits `source_runs` for every attempt.

Required source failure, stale watermark, response-schema change, zero rows
where the source should be active, duplicate event IDs, or a failed required
analysis must make the workflow fail and stop a clean publication.  Optional
source failure may publish only with a visible degraded-status panel.

### Schedules

| Job | Cadence | Required output |
|---|---:|---|
| `defi-live` | 15 minutes for quote/auction snapshots; hourly finalized logs | raw + normalized quote, execution, event, and source-run records |
| `compute-live` | hourly | Vast, Akash, Golem, and direct-provider price/capacity snapshots |
| `defi-backfill` | manual/date-range | idempotent finalized event partitions; never mixed with live provisional rows |
| `quality` | after each collection and before publication | source health, row/coverage drift, schema and duplicate checks |
| `cross-market-analysis` | daily after finalization | metric panels, gated summaries, and comparison status |
| `memo` | daily | refuses “healthy” publication when a required input is red |

### Alerts

Alert on missing five-minute/hourly/daily watermarks, row-count or universe
collapse, stale block height, mapping coverage decline, source schema hash
change, and compute/deFi market events.  Deliver a small run manifest beside
the memo so a reader can see whether an apparent quiet market is actually an
unhealthy collector.

## Fix plan

### P0 — make the existing monitor truthful (first)

1. Make `orcap analyze` return non-zero for required-module exceptions and
   write a structured failure manifest; retain explicit optional modules only
   through a registry.  Today it logs an exception and publishes a partial
   result as a successful command.
2. Add collector source-health assertions: non-empty expected sources,
   latest `run_ts`, endpoint-model coverage, raw HTTP status, parser/schema
   checks, and price sanity bounds.  Fail instead of producing a successful
   zero-row partition.
3. Add workflow-level `quality` and `source_runs` outputs before the HF push
   and before memo publication.  Show red/degraded status in the memo.
4. Fix `capture_devrel` so the constructed GitHub authorization header is
   actually supplied to its GitHub requests; currently it is unused.
5. Schedule the current `orcap defi` or deliberately remove it from the live
   monitor claim.  The immediate schedule should include only safe existing
   sources and a BigQuery cost cap/required credentials check.

Acceptance: inject a malformed payload, an empty required response, and an
analysis exception; each must block clean publication and write a diagnostic
manifest.  A genuine optional-source failure must publish as degraded, not
healthy.

### P1 — construct the comparable data layer (next)

1. Add source adapters plus raw/curated schemas for finalized Uniswap
   events, CoW executions/auctions, Akash orders/bids/leases, and Golem
   network/provider snapshots. The bounded, provider-filtered Akash GPU-bid
   slice is implemented; it does not replace an all-network order book.
2. Replace the `univ3_pool_daily` last-price proxy with pool state plus
   swap/mint/burn events for a pre-registered liquid ETH/USDC cohort.  Compute
   gas-inclusive executable depth and impact.
3. Replace CoW transaction-sender settlement counts with canonical
   settlement/auction data and a solver-address registry.  Version the
   registry and preserve unknown identities.
4. Normalize Vast, Akash, and Golem into `market_capacity`, preserving
   interruption/commitment type and quality dimensions.  Publish venue
   indices by strict cohort; never average unlike resources.
5. Implement typed adapters for at least three additional direct inference
   providers before treating H13 as a market-wide venue-basis test.  Unmapped
   page text is fallback evidence, not a price observation.

Acceptance: backfill 30 finalized days and collect seven live days; every
row has raw provenance, a stable identity, a source watermark, and an
instrument-map coverage report above a pre-declared threshold.

### P2 — fit and pre-register the comparative study (then)

1. Add A/B descriptive panels and the common size/quality cohort builder.
2. Add transaction-cost, fill/reject, depth/impact, and update-hazard metrics
with synthetic recovery tests and known-event fixtures.
3. Pre-register event definitions, shocks, outcomes, controls, minimum
events, and stopping rule for dynamic tests.
4. Add daily finalized analyses and a comparison-status page that distinguishes
observed facts from power-gated results.

Acceptance: a one-command daily run produces comparable metric tables with
coverage, confidence intervals, provenance, and no unlabelled cross-market
causal claims.

## Explicit non-goals

- Do not claim an executable compute cash-and-carry trade until same-venue
  forward quotes and deliverable capacity are captured.
- Do not convert OpenRouter listed prices, router-estimated capacity, or
  CoW transaction senders into fills, inventory, or solver identity without
  the supporting source.
- Do not blend public open networks and commercial GPU clouds into one price
  index without a quality/region/commitment cohort.
- Do not let a dashboard aggregate replace canonical chain/event data for
  a microstructure conclusion.
