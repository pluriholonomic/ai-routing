# Source qualification audit — 2026-07-10

This is a source-level audit, not a market result.  A source is added to an
empirical panel only when its identity, pricing/transaction fields, cadence,
and failure semantics are known.  A public page or RPC hostname alone is not
enough.

## Qualified in this run: Fireworks serverless model pages

Fireworks' public model pages expose all fields needed for a narrow H13 direct
price observation:

- the literal provider API ID, for example
  `accounts/fireworks/models/gpt-oss-20b`;
- a labeled `Available Serverless` block with input, cached-input, and output
  prices per one million tokens; and
- a stable first-party page URL retained in the raw layer.

The direct collector now polls two bounded GPT-OSS pages.  It accepts a row
only if the expected literal provider ID and the labeled three-price block are
both present.  It does not crawl Fireworks' historical sitemap or infer a
model identity from a display name.  A live OpenRouter endpoint check confirmed
that its Fireworks GPT-OSS-20B record uses the same literal provider ID and
the same posted input/output price.  GPT-OSS-120B is captured as a direct
price but had no current Fireworks endpoint in the public OpenRouter response,
so it produces no H13 pair until that changes.

This is still posted-price evidence, not a firm quote, request outcome, or
fill.  The collector records it as `published_model_page` and gives it its own
source-health record.

## Qualified in this run: Groq public model table

Groq's public supported-models page provides literal API model IDs and a
two-sided input/output price cell per one million tokens. The direct collector
accepts a row only when the table has the exact `Model ID` and `Price Per 1M
Tokens` headers and the price cell has explicit input and output dollars; it
does not infer a price from rate limits or a display name. The live capture
produced ten rows.

A public OpenRouter endpoint check confirmed the identity and current prices
for `meta-llama/llama-4-scout-17b-16e-instruct`: both surfaces listed
`$0.11/M` input and `$0.34/M` output. This is a posted-price source check,
not evidence of a fill or a claim that every Groq route is passed through.

## Qualified in this run: Cerebras public model API

Cerebras documents and serves `https://api.cerebras.ai/public/v1/models`
without credentials. The response contains a literal Cerebras API ID and
separate per-token `pricing.prompt` and `pricing.completion` fields. When
present, it also contains a literal `hugging_face_id`; the collector retains
both fields and labels that first-party canonical key separately from the
provider API ID.

On the live source check, Cerebras reported `gpt-oss-120b` with first-party
canonical key `openai/gpt-oss-120b` and `$0.35/M` input / `$0.75/M` output.
OpenRouter's current Cerebras endpoint for that same exact canonical key showed
the same posted prices. This supports one source-qualified H13 pair, not a
market-wide passthrough or fill claim. Preview status remains in provenance;
the collector does not silently treat preview availability as a production SLA.

## Qualified in this run: SambaNova public model API

SambaNova's unauthenticated `https://api.sambanova.ai/v1/models` response
provides literal model IDs and separate `pricing.prompt` and
`pricing.completion` values per token. The current live response contained six
models. It is therefore a structured public list-price source, not an account
usage feed or fill record.

Most SambaNova IDs remain in the raw direct catalog without an H13 crosswalk.
The sole initial map, in [`direct_model_maps.toml`](../config/direct_model_maps.toml),
is deliberately one-to-one and versioned: SambaNova `gpt-oss-120b` maps to
OpenRouter `openai/gpt-oss-120b`. The direct catalog and current OpenRouter
SambaNova endpoint are both retained as verification URLs, although the
OpenRouter endpoint currently omits a provider-specific model ID. This is not
a fuzzy name match.

The live check found a posted difference for that mapped model: SambaNova
listed `$0.22/M` input and `$0.59/M` output, while OpenRouter listed its
SambaNova route at `$0.14/M` and `$0.95/M`. It is one current posted-price
observation, not evidence of a fee, execution price, route selection, or
market-wide basis. H13 remains power-gated until repeated and broad coverage
accumulates.

## Rejected for automatic collection: credential-free Ethereum RPC

The candidate `https://ethereum-rpc.publicnode.com` answered
`eth_blockNumber`, but rejected a finalized `eth_getLogs` request for the
registered Uniswap V3 USDC/WETH pool with an archive-access error.  The
candidate `https://eth.llamarpc.com` returned a browser challenge rather than
JSON-RPC.  Neither is suitable as a production no-auth source.

Do not silently fall back to a current-block-only query or treat an empty
response as zero Uniswap activity.  For historical or paper-grade collection,
the needed collector must use one of:

1. an archive-capable `ORCAP_ETHEREUM_RPC_URL` with an explicit cost/rate
   policy, then ingest finalized `Swap`, `Mint`, and `Burn` logs with a reorg
   buffer; or
2. a pinned, key-backed Uniswap subgraph or Dune query with block watermark,
   query/deployment identity, and independent log validation.

That remains a Tier-1 blocker for the DeFi versus open-compute paper: public
dashboard price/TVL data cannot replace event-level swaps or liquidity changes.

## Rejected for market-wide execution: unscoped CoW trades endpoint

CoW's official OpenAPI advertises a paginated `GET /api/v2/trades` route, but
the live public request to
`https://api.cow.fi/mainnet/api/v2/trades?limit=10` returned HTTP 400 and an
`InvalidTradeFilter` response: the request must identify either one owner or
one order UID. That is useful for an account- or order-specific lookup, but it
is not a market-wide execution census.

Do not point `ORCAP_COW_TRADES_URL` at that bare public endpoint, paginate over
known owners, or concatenate order-level responses and call the result market
coverage. The existing live solver-competition monitor remains a bounded
snapshot only. The Tier-1 path is still an archive-capable GPv2Settlement log
index or a properly scoped official/Dune execution feed with a documented
watermark and coverage universe.

An archive-capable `ORCAP_ETHEREUM_RPC_URL` now has a bounded implementation
path for this blocker: it queries verified `GPv2Settlement` `Trade` and
`Settlement` logs after a reorg buffer. The collector keeps only a solver
emitted by the same transaction's `Settlement` event, never the transaction
sender. The archive/historical path is **not yet source-qualified in
production**: no configured archive endpoint has accumulated rows, and raw
token amounts still need an explicit decimal/price mapping before they can
support USD execution comparisons. The separately qualified dRPC monitor below
only supplies recent bounded observations.

One deliberately narrow exception is now normalized: exact mainnet
USDC/WETH `Trade` events have registered token addresses and decimal metadata.
Those fills are emitted as `ethereum:USDC/WETH`, split by sell direction, and
priced in the explicit `usdc_per_weth` quote unit. They are **not** USD prices,
stablecoin-peg-adjusted costs, gas-inclusive costs, surplus estimates, or a
market-wide CoW execution panel; every other GPv2 pair retains raw amounts.

## Qualified with a bounded scope: dRPC public Ethereum log monitor

dRPC documents `https://eth.drpc.org` as a public Ethereum RPC endpoint. In
this run it served `eth_blockNumber` and bounded `eth_getLogs` requests for the
two registered Uniswap pools and GPv2Settlement. After a 64-block finality
buffer, the collector observed 75 Uniswap swaps and six liquidity events in a
128-block window. dRPC added explicit `blockTimestamp` values to logs; the
collector uses them only when its canonical block-header lookup is unavailable
and records that fallback in the source ledger.

This qualifies a live, bounded recent-finality monitor, not archival or
market-wide coverage. It cannot repair missed periods, establish USD executable
depth, or turn GPv2 Trade events into market-wide order/fill/surplus coverage.
An operator-selected archive RPC remains the preferred source for a paper-grade
historical panel.

The original 128-block default was too short for an hourly workflow at observed
Ethereum block cadence. A live dRPC validation of a 1,024-block window returned
650 registered-pool Uniswap logs (615 swaps) and 780 GPv2Settlement logs (398
trades), with no Quoter errors. The default now uses that validated overlap;
H41 records gaps between query windows instead of assuming snapshots form a
continuous panel.

## Qualified with a bounded scope: Livepeer aggregate Gateway routing control

Livepeer's documented Gateway Introspection API exposes a public Loki endpoint
for observing Gateway activity. The collector requests only three aggregate
LogQL count queries by public region: swap messages, reuse messages, and reuse
messages while segments are in flight. A live validation returned two regional
rows with non-zero decision-message counts; the raw provenance contained four
aggregate responses and no manifest, session, or client identifiers.

This qualifies a privacy-preserving external routing-adjustment control. It
does not identify an orchestrator, stream, selected provider, LLM model, price,
request volume, capacity, successful delivery, or welfare. H51 is therefore
power-gated and may only report a region-window association after its declared
seven-day and snapshot-count thresholds.

## Qualified with a bounded scope: Uniswap QuoterV2 price-impact curve

Uniswap's official Ethereum deployment list identifies QuoterV2 at
`0x61fFE014bA17989E743c5F6cB21bF9697530B21e`, and its official interface says
that exact-input calls calculate expected swap amounts without executing a
swap. The collector calls that contract through the same RPC at the
finality-buffered block for USDC inputs of 100, 1,000, 10,000, and 100,000 on
each registered USDC/WETH pool. The live probe returned eight finalized-block
simulation rows, with non-zero outputs and explicit ticks-crossed fields.

This is a fixed-notional state-simulation curve, not an executed fill, a firm
RFQ, or a market-wide depth measure. It can measure a repeatable price impact
at the registered buckets, but it does not account for a subsequent block,
transaction ordering, wallet approvals, gas, cross-pool routing, or wider
market liquidity. H41 continues to keep the full Uniswap depth gate closed.

## Qualified in this run: Novita public SSR pricing catalog

Novita's public pricing page embeds a named `initialFullLLMModels` catalog in
its React-flight response. Each qualifying entry has a literal provider API ID,
an active chat-completions endpoint, and explicit rendered input/output
USD-per-million-token fields. The collector decodes that named JSON payload
without executing page JavaScript; it does not scrape model display names or
guess an identifier. It rejects inactive, non-chat, zero-priced, missing-price,
and schema-mismatched records.

The live catalog yielded 91 active, positive-price chat records on 2026-07-10.
An independent OpenRouter endpoint lookup confirmed that `openai/gpt-oss-20b`
and `openai/gpt-oss-120b` use the same literal IDs at provider `Novita`, with
the same displayed list prices. This supports only exact-ID direct-versus-routed
posted-quote comparisons. It does not identify executions, provider cost,
route-selection probability, or realized consumer spend.

## Qualified in this run: Chutes public model catalog

Chutes exposes an unauthenticated `GET https://llm.chutes.ai/v1/models`
catalog with literal API IDs, model roots, quantization, and USD-per-million
input/output prices. The collector admits only positive numeric fields in that
structured response. Chutes's direct IDs carry a `-TEE` product suffix while
OpenRouter's provider endpoints use canonical IDs, so the H13 join does **not**
strip or normalize strings. It uses only a versioned one-to-one map whose
expected catalog root and quantization must both match at capture time.

The live catalog had 13 priceable entries on 2026-07-10. Eight had an active
current Chutes OpenRouter endpoint covered by the configuration-verified map.
This provides a model-configuration posted-quote comparison only. The public
TEE flag is not an availability, execution, fill, or cryptographic-attestation
claim, and the panel does not establish Chutes's routed share or cost.

## Qualified in this run: Chutes public deployment configuration

For each public catalog `chute_id`, `GET https://api.chutes.ai/chutes/{id}`
returns the live public NodeSelector, active instance records, configured
concurrency, cumulative invocation count, and a source-defined estimated hourly
deployment price. The market collector records active instances times the
configured GPUs per instance as `active_configured_gpu` alongside the raw
fields and source definition.

This is useful as a repeated decentralized-inference supply-state control. It
is **not** available capacity, queue depth, throughput, tokens served, realized
utilization, allocation, or a provider profit measure. In particular, a count
of active configured GPUs must not be converted into an inference capacity or
used to calibrate the routing mechanism's delivery constraint.

## Not qualified: Hyperbolic public inference pricing

On 2026-07-10, an unauthenticated request to Hyperbolic's documented
OpenAI-compatible `GET https://api.hyperbolic.xyz/v1/models` returned HTTP 401
with `Not authenticated`. Its older public pricing/inference documentation URLs
also now redirect to the generic platform overview, rather than a stable,
model-level price catalog. The existing raw archive remains useful for future
manual evidence review, but there is no unauthenticated, exact-ID direct-price
source to add to H13 at present. Do not substitute an account-specific billing
view or inference request for market-wide public price evidence.

## Qualified in this run: Lambda public GPU instance list prices

Lambda's public instances page server-renders four labeled instance-size tables
(`1x`, `2x`, `4x`, and `8x`). The collector requires the literal headers
`Plan`, `VRAM/GPU`, and `PRICE/GPU/HR*`; each retained row preserves the exact
GPU plan, VRAM, instance size, and USD-per-GPU-hour list price. The live page
yielded 21 valid rows on 2026-07-10, including a `1x` NVIDIA H100 SXM quote of
$4.29 per GPU-hour.

This is a commercial posted-price control only. It has no offer-book depth,
availability, utilization, region, realized workload, discount, or execution
fields. It must not be merged with Vast individual offers or used as evidence
of Lambda's token inference price; Lambda's public page states that its
Inference API is winding down.
