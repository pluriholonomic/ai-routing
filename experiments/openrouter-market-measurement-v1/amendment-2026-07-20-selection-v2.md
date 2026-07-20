# Market-measurement seeded top-pool selection v2

Status: frozen before the first v2 paid request.

Date: 2026-07-20 UTC

## Motivation

The v1 information-maximizing rule repeatedly selected
`deepseek/deepseek-v4-pro`. Those completed runs remain valid for the controlled
policies that were executed, but they cannot support model-level transport or
the planned routing-SNR comparison.

## Prospective design

The plan version becomes `market-measurement-plan-v2`. Every run still selects
exactly one model-shape block using only the frozen public candidate menu.
Eligible blocks remain ranked by the registered public information score. The
selected block is now a deterministic, seed-indexed member of the top five
eligible blocks, or of the full eligible set when fewer than five exist.

The immutable plan records the selection rule, pool size, selected information
rank, seed, and scores. All policy, memory, liquidity, quality, budget, privacy,
and exact-once execution rules are unchanged.

V1 runs remain in health and spend accounting and may be reported as bounded
descriptive pilots. Confirmatory policy, liquidity, memory, and quality panels
after this amendment admit only complete v2 runs. V1 and v2 are not silently
pooled for provider- or model-ranking claims.
