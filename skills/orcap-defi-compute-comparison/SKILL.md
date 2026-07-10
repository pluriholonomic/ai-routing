---
name: orcap-defi-compute-comparison
description: Build or assess the ORCAP DeFi-versus-open-compute market comparison. Use when selecting DeFi, GPU, decentralized-compute, RFQ, AMM, or inference data; defining matched cohorts and estimands; extending `market_*` tables; running H41; or reviewing whether a cross-market claim is supported rather than a proxy comparison.
---

# ORCAP DeFi and Compute Comparison

Use a matched microstructure design. Do not compare an aggregate token, TVL,
or hashprice series to a quote book as though they measure the same object.

## Start with the comparison contract

1. Read `docs/defi-open-compute-completion-plan.md`.
2. Define the executable economic object, unit, clock, and quality tier.
3. Select a strict cohort: model/quantization/SLO; GPU/region/commitment;
   AMM pair/fee/notional; or solver pair/order-size/settlement interval.
4. State whether the source measures posted price, executable price, capacity,
   utilization, fill, or aggregate activity.

## Extend the data layer

1. Collect raw source evidence through `orcap market-capture` or a dedicated
   source adapter; use key-gated Uniswap/Akash configuration only from
   environment variables.
2. Normalize to the appropriate canonical table: `market_quotes`,
   `market_executions`, `market_capacity`, `market_participants`, or
   `market_events`.
3. Retain source/native values and USD conversions separately. Keep source
   identifiers, finality/block information, quality dimensions, and mapping
   version.
4. Mark incomplete data as degraded or provisional. Do not infer market-wide
   CoW activity from a user-scoped endpoint, or a GPU index from unlike
   hardware/regions.

## Analyze and report

1. Run `uv run orcap analyze --hypothesis h41` to build the common-metric
   coverage panel.
2. Compare executable dispersion, depth/impact, update hazard, fill/reject,
   concentration, entry/exit, and all-in cost only within matched cohorts.
3. Use pre-specified shocks, controls, placebo dates, and event windows for
   dynamic claims. Cross-sectional price-flow correlations are descriptive.
4. Label every conclusion measured, provisional, or not identified; report
   source coverage and health alongside the metric.

## References

Read `references/comparison-contract.md` before adding a new cross-market
metric.
