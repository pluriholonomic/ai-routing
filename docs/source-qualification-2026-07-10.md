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
