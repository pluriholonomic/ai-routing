# Livepeer Gateway aggregate routing control

## What is collected

Livepeer publishes a public Loki endpoint for Gateway introspection. The
collector queries only aggregate `count_over_time` metrics grouped by the two
public regions. Each five-minute observation contains counts of Gateway log
messages for:

- swapping an orchestrator;
- reusing an orchestrator; and
- reusing while segments are in flight.

The raw provenance file contains only these aggregate query responses. It never
requests or stores log-stream lines, manifest IDs, session IDs, client IPs, or
orchestrator identities.

## Historical aggregate backfill

The same public Loki API exposes `query_range` for aggregate counters. The
manual historical command requests only the existing `sum by (region)` LogQL
counters, never raw stream lines or additional labels:

```bash
uv run orcap capture-livepeer-history --lookback-hours 24 --step-minutes 5
```

The command accepts a maximum 168-hour lookback to bound load on the public
endpoint. Its rows retain the capture time separately from each source window
end, so H51 clusters and deduplicates on the source observation timestamp. It
does not add the collector to a scheduled workflow or upload captured data.

The public API had non-empty aggregate regional windows when checked at one
hour, seven days, and 30 days back on 2026-07-10. That establishes accessible
retention at those sampled points only; it does not promise a fixed retention
period or complete coverage between them.

## Economic use and boundary

This is the first public source in the project that observes an actual
decentralized Gateway's routing-adjustment messages rather than a simulated
route surface. It is an external control for the proposed capacity-certified
routing mechanism: it can show how a real decentralized Gateway changes route
choices as a public in-flight state varies.

It is not evidence about OpenRouter, LLM model routing, a provider's allocated
share, user demand, execution price, serving cost, capacity, successful
completion, or welfare. A `Swapping Orchestrator` message does not identify the
before/after provider or prove a failed delivery.

## H51 pre-specified screen

H51 constructs a region-window panel with
`switch_share = swaps / (swaps + reuses)` and an in-flight reuse share. Only
after 1,000 distinct five-minute snapshots, seven days, and two regions does it
estimate a weighted, region-fixed-effect descriptive association, clustering
standard errors by snapshot. The test is two-sided and non-causal; it is
designed as an external mechanism control, not a routing-performance claim.

Run locally against a hydrated dataset:

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h51 --out analysis
```
