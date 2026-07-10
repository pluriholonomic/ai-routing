# Public source discovery — 2026-07-10

## Decision

The strongest newly qualified public source is the [Akash Console Network Data
API](https://akash.network/docs/api-documentation/rest-api/), specifically its
unauthenticated `GET /v1/dashboard-data` and `GET /v1/network-capacity`
endpoints. It complements the existing provider-level Akash capture with
network-level active leases, GPU capacity states, and source-reported payment
aggregates. It does **not** identify individual workloads, GPU-hours,
per-provider revenue, realized resource prices, or welfare.

The source is captured through the existing `market-capture --with-akash`
path, which retains its raw JSON, writes an aggregate-only normalized table,
and records an optional source-health row beside the other Akash observations.
H61 exposes the retained aggregate snapshot panel and is power-gated until it
has seven source-observation days and 20 source timestamps.

## Provider aggregate extension

The same public API also exposes unauthenticated, aggregate-only endpoints for
a provider: `GET /v1/providers/{provider}/active-leases-graph-data` and
`GET /v1/provider-dashboard/{provider}`. The collector queries those endpoints
only for the current live-GPU-provider universe already returned by the public
provider endpoint. It records source-defined active-lease history, current
active GPU and lease counts, and the literal source-unit earning-card fields.
It does not query tenant, deployment, workload, or order records.

The resulting `akash_provider_aggregates` table is designed for a once-daily
run, retaining an eight-day rolling overlap so that source revisions can be
deduplicated. It fails closed: if either aggregate endpoint is malformed or
unavailable for any current universe member, it writes no canonical provider
panel and emits a degraded source-health row. H62 converts the retained source
history into descriptive daily totals and concentration measures only after a
30-day / 10-provider coverage gate. Its universe is explicitly current rather
than a historical census, and an active lease is not a completed workload,
GPU-hour, utilization, price, demand, delivery, revenue, profit, allocation,
or welfare measure.

## Read-only schema validation

On 2026-07-10, both endpoints returned JSON without credentials. The dashboard
response contains a `now` observation with a source timestamp and chain height,
a 24-hour `compare` observation, current network-capacity totals, and chain
statistics. The `now` object included:

- `activeLeaseCount`, `totalLeaseCount`, and `dailyLeaseCount`;
- `activeGPU` alongside CPU, memory, and storage resource states;
- cumulative and daily `uakt`, `uact`, `uusdc`, and `uusd` spend fields; and
- a source timestamp and block height.

The capacity endpoint separately reports active, pending, available, and total
resources plus `activeProviderCount`. This matches the official API's
description of public, indexed provider/GPU availability data, rather than an
Akash node or a settlement ledger.

## Proposed normalized panel

One source response at each capture time should yield a narrow
`akash_dashboard` aggregate table. Every row retains the raw response pointer,
source URL, source timestamp, source block height where supplied, and the
literal metric name/unit.

| Metric family | Examples to retain | Boundary |
|---|---|---|
| Lease activity | active, total, and source-day lease counts | Lease contracts/states, not completed workloads or customer demand. |
| GPU state | active, pending, available, total GPU counts; active-provider count | Source-indexed resource state, not model-specific capacity, physical-GPU audit, or utilization. |
| Payment aggregates | source-reported daily and cumulative USDC/USD/AKT spend | Aggregate protocol spend, not provider revenue, a GPU-hour clearing price, buyer surplus, or audited financial reporting. |
| Chain reference | source `now`/`compare` timestamps and heights | Query provenance and a 24-hour control only; do not expand the repeatedly returned `compare` point into a manufactured history. |

Only the source's current `now` values become new time-series observations. The
embedded `compare` values are retained to audit the source's stated comparison
window, not duplicated as a second daily sample.

## Health and inference rules

1. Require a parseable `now.date`, positive or zero integer resource counts,
   and a positive source height. A malformed response emits a degraded
   source-run rather than zero capacity or zero spend.
2. Store `daily*Spent` fields as source-reported daily aggregates. Do not
   difference cumulative spend across collector gaps and call it a daily
   value; counter resets and source revisions must remain explicit.
3. Cross-check the dashboard GPU totals against the existing provider-panel
   aggregation only as a coverage diagnostic. Different update clocks and
   inclusion policies are expected, so a difference is neither an error nor a
   market imbalance without source documentation.
4. Never divide spend by active GPUs, leases, or containers to construct a
   price, revenue-per-GPU, or utilization estimate. Those denominators are not
   joined at the workload or provider level.

## Empirical use

After at least six to eight weeks of complete, source-ledger-certified
snapshots, this panel can support descriptive aggregate controls such as
changes in active GPU supply, active lease count, and source-reported protocol
spend around documented supply shocks. It can help validate whether a
provider-level Akash capacity movement is network-wide or local. It cannot
identify routing allocation, price elasticity, adverse selection, delivery
probability, or causal welfare on its own.

## Other search results

- CoW Protocol's [currently documented paginated trade
  endpoint](https://cowswap.mintlify.app/api-reference/get-existing-trades-paginated)
  still rejects a request without exactly one `owner` or `orderUid`
  (`InvalidTradeFilter`), so it is not a public market-wide CoW execution
  feed. The existing finalized `GPv2Settlement` log monitor remains the
  defensible public execution source.
- The daily direct-provider capture has not yet published a run after the
  newer adapters merged. Its current one-provider H13 result is a scheduling
  boundary, not evidence that the adapters or providers are absent.
