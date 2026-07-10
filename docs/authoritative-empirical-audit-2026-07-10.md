# Authoritative empirical audit — 2026-07-10

## Scope and method

This audit queried the authoritative `t4run/openrouter-market-history` Hugging
Face dataset directly on 2026-07-10. It wrote diagnostic outputs only to a
temporary local directory and did not upload, modify, or hydrate the dataset.
It is therefore the current evidence boundary for the panels below, rather
than a forecast from local staging files.

## Current evidence

| Gate | Authoritative result | Interpretation |
|---|---|---|
| H13 routed-versus-direct basis | 191 matched daily price pairs across 4 days, all DeepInfra; every basis is numerically zero (maximum absolute percentage basis `2.22e-14`) and maximum routed/direct quote gap is 12.8 minutes | Power-gated: only 4/7 days and 1/3 providers. Exact zero is consistent with posted-quote passthrough, not executable fills, allocation, or market-wide routing. |
| H41 DeFi/open-compute comparison | Akash, Chutes, CoW, DefiLlama, GeckoTerminal, and Uniswap rows are present. Uniswap and CoW each have three overlapping finalized windows with zero uncovered blocks between them (1,806 and 1,810 covered blocks respectively). | Still power-gated: one observation day only; full finalized USD depth and a market-wide CoW execution/auction panel are absent. State-derived Uniswap impact lower bounds remain distinct from depth. |
| H52 CoW-versus-AMM parent-block basis | 24 exact finalized USDC-to-WETH CoW fills, each simulated at the same pre-settlement input through both registered Uniswap pools (48 counterfactuals). The median gross and fee-adjusted CoW-over-AMM basis are both `-0.0910%`; all 24 [`Trade.feeAmount`](https://cowswap.mintlify.app/cow-protocol/reference/contracts/core/settlement) fields are present and zero. | Power-gated: 24/500 fills and 1/7 days. The CoW contract documents `feeAmount` as a fee in the sell token, but the AMM simulation remains at the pre-fee stated CoW input; this is not same-all-in-notional best execution, gas-inclusive cost, surplus, or adverse selection. |
| H55 Akash open GPU bid book | No complete canonical bid snapshot has published. The provider-filtered, block-pinned collector remains fail-closed after incomplete public bid-page responses. | Not identified. An empty canonical table is not a zero-demand, zero-bid, or price result. |
| H56 Uniswap initialized tick state | 4,476 initialized-tick rows across two ledger-certified complete snapshots for the registered pools. | Power-gated at 1/7 days and 4/20 snapshots; virtual-liquidity state is not dollar depth, a firm quote, or a realized fill. |
| H58 Nosana registry | 38 NodeAccount rows across two source-ledger-certified complete snapshots. | Power-gated at 1/7 days and 2/20 snapshots. These remain declared registration fields, not availability, price, GPU count/model, utilization, or delivery. |
| H59 Nosana aggregate activity | 184 aggregate-only rows across two captures, including 25 completed-job buckets, 25 duration buckets, and running-market aggregates; the source-reported running count equals their sum. | Power-gated at 2/7 source-bucket days and 25/100 buckets per series. It is not LLM routing, token flow, verified GPU-hours, capacity, utilization, payment, revenue, welfare, or causal demand. |
| H47 exact GPU quote basis | All three versioned Akash/Vast cohorts exist in the authoritative store: three positive Akash quote snapshots per cohort and 46–49 Vast on-demand snapshots. Yet no pair falls within the 90-minute rule; the nearest cohort-specific published snapshot is 355.55–407.75 minutes away. | Not an economic zero. The current GPU workflow buffers hourly captures as GitHub artifacts for the nightly compact/upload job, while the market workflow publishes Akash quotes directly. H47 is therefore blocked by a publication-clock mismatch rather than an absent GPU mapping or quote. |

## Why H13 has only one provider today

The latest published `direct_prices_daily` run is `20260710T045016Z` and
contains 197 DeepInfra rows. This is not yet evidence that the newer adapters
failed: the Cerebras, SambaNova, Novita, Chutes, and BaseTen adapter commits
landed after that daily scrape began at 04:37 UTC. The next scheduled scrape is
the first normal publication opportunity for those adapters.

The next source-health check must therefore distinguish two outcomes:

- **Pass:** the source-run ledger records the newly merged adapters and
  `direct_prices_daily` contains their qualified rows; H13 then re-evaluates
  exact mapped pairs and still applies its three-provider gate.
- **Fail/degraded:** an adapter records zero rows or a schema/identity failure;
  preserve its raw response and diagnose its source contract rather than
  treating the absent provider as a zero-price or zero-demand observation.

## Evidence-backed next gates

1. Let the scheduled monitor accumulate at least three more daily direct-price
   observations **and** publish qualified pairs for at least two additional
   providers before interpreting H13 as cross-venue evidence.
2. Accumulate at least six more days of contiguous, finalized Uniswap/CoW
   windows. Preserve the zero-uncovered-block diagnostic; do not substitute
   indexed or state-derived values for finalized depth or market-wide CoW flow.
   H52 additionally needs 476 more exact USDC-to-WETH fills before reporting
   even its tightly bounded fee-adjusted parent-block basis.
3. Let H58 reach seven days and 20 ledger-verified registry snapshots; let H59
   reach seven source-bucket days and 100 latest buckets for both source
   series. These are descriptive source-panel gates, not welfare gates.
4. Before treating H47 as a basis result, make the two source series queryable
   on a common clock at the existing 90-minute threshold, then accumulate at
   least seven days, 50 matched pairs, and two exact GPU cohorts. Widening the
   match window without a validated intraday-staleness model would create a
   stale-quote comparison, not repair the panel.
5. A central empirical/theory paper remains blocked on a controlled, redacted
   routing study and independently scheduled reliability audit. Public panels
   can validate regime and context but cannot identify realized allocation,
   quality-adjusted cost, or welfare.

## Reproduction

The authoritative checks were run with the repository's default analysis data
source (the Hugging Face dataset), not `ORCAP_ANALYSIS_SOURCE=local`:

```bash
PYTHONPATH=. .venv/bin/python -c \
  'from pathlib import Path; from orcap.analysis.h13_venue_basis import run; run(Path("/tmp/h13"))'
PYTHONPATH=. .venv/bin/python -c \
  'from pathlib import Path; from orcap.analysis.h41_market_comparison import run; run(Path("/tmp/h41"))'
PYTHONPATH=. .venv/bin/python -c \
  'from pathlib import Path; from orcap.analysis.h52_cow_amm_basis import run; run(Path("/tmp/h52"))'
PYTHONPATH=. .venv/bin/python -c \
  'from pathlib import Path; from orcap.analysis.h58_nosana_node_registry import run; run(Path("/tmp/h58"))'
PYTHONPATH=. .venv/bin/python -c \
  'from pathlib import Path; from orcap.analysis.h59_nosana_job_activity import run; run(Path("/tmp/h59"))'
PYTHONPATH=. .venv/bin/python -c \
  'from pathlib import Path; from orcap.analysis.h47_gpu_venue_basis import run; run(Path("/tmp/h47"))'
```

The omitted output directory should be an explicit temporary directory for a
read-only audit, as it was for this run. H47 now records source-read status
separately from coverage: a failed remote read cannot silently masquerade as
an empty quote panel.
