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
response as zero Uniswap activity.  The needed collector must use one of:

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
sender. It is code-ready but **not yet source-qualified in production**: no
configured archive endpoint has accumulated rows, and raw token amounts still
need an explicit decimal/price mapping before they can support USD execution
comparisons.
