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
| H41 DeFi/open-compute comparison | Akash, Chutes, CoW, DefiLlama, GeckoTerminal, and Uniswap rows are present. Uniswap and CoW each have two overlapping finalized windows with zero uncovered blocks between them (1,536 and 1,539 covered blocks respectively). | Still power-gated: one observation day only; full finalized USD depth and a market-wide CoW execution/auction panel are absent. State-derived Uniswap impact lower bounds remain distinct from depth. |
| H58 Nosana registry | 19 NodeAccount rows and one source-ledger-certified complete snapshot | Power-gated at 1/7 days and 1/20 snapshots. These remain declared registration fields, not availability, price, GPU count/model, utilization, or delivery. |
| H59 Nosana aggregate activity | 93 aggregate-only rows, including 25 completed-job buckets, 25 duration buckets, and 34 market running totals; the source-reported running count equals their sum | Power-gated at 2/7 source-bucket days and 25/100 buckets per series. It is not LLM routing, token flow, verified GPU-hours, capacity, utilization, payment, revenue, welfare, or causal demand. |

## Evidence-backed next gates

1. Let the scheduled monitor accumulate at least three more daily direct-price
   observations **and** publish qualified pairs for at least two additional
   providers before interpreting H13 as cross-venue evidence.
2. Accumulate at least six more days of contiguous, finalized Uniswap/CoW
   windows. Preserve the zero-uncovered-block diagnostic; do not substitute
   indexed or state-derived values for finalized depth or market-wide CoW flow.
3. Let H58 reach seven days and 20 ledger-verified registry snapshots; let H59
   reach seven source-bucket days and 100 latest buckets for both source
   series. These are descriptive source-panel gates, not welfare gates.
4. A central empirical/theory paper remains blocked on a controlled, redacted
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
  'from pathlib import Path; from orcap.analysis.h58_nosana_node_registry import run; run(Path("/tmp/h58"))'
PYTHONPATH=. .venv/bin/python -c \
  'from pathlib import Path; from orcap.analysis.h59_nosana_job_activity import run; run(Path("/tmp/h59"))'
```

The omitted output directory should be an explicit temporary directory for a
read-only audit, as it was for this run.
