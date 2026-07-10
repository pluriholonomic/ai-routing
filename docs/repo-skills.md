# Repo operating skills

These are version-controlled operating specifications for work in this repo.
They are deliberately short enough to be followed during an incident or an
analysis run. The corresponding formal repo-local Codex skills live in
[`../skills/orcap-market-monitoring`](../skills/orcap-market-monitoring) and
[`../skills/orcap-defi-compute-comparison`](../skills/orcap-defi-compute-comparison).

## 1. Operate the market capture

Use for: collector changes, missed captures, source-endpoint changes, or data
freshness incidents.

1. Identify the owning workflow and collector before changing an analysis.
2. Run the smallest safe collector locally into a disposable `ORCAP_DATA_DIR`.
3. Check raw JSONL response status and body before inspecting normalized
   parquet.  A successful HTTP response with an empty or shifted body is a
   source failure, not zero market activity.
4. Verify the expected table, partition, row count, uniqueness grain, and
   newest `run_ts`.
5. Add a source-contract test and a monitor assertion before scheduling a new
   source.  Preserve the raw payload even when normalization intentionally
   drops a field.
6. For production changes, validate the GitHub workflow's artifact/push path;
   a local collector success alone is insufficient.

Completion check: raw capture, normalized rows, compaction, and a local
analysis read all agree on the new timestamp and expected grain.

## 2. Extend a market data source

Use for: a provider, DeFi venue, compute marketplace, or demand proxy.

1. Write the source contract first: owner, endpoint, authentication, cadence,
   response grain, canonical identifiers, historical availability, rate and
   cost limits, and failure semantics.
2. Prefer a canonical event/state source over a dashboard aggregate.  Use
   aggregates only for universe coverage or a clearly labelled macro control.
3. Map vendor identifiers to a stable canonical key; preserve both the source
   identifier and the mapping version.
4. Put raw data under `raw/<source>/dt=...` and normalized rows in one named
   curated table.  Include `run_ts`, `dt`, `source`, `source_id`, and
   `record_json` unless payload size makes that impractical.
5. Make the collector idempotent at the source timestamp/block height and
   tolerate replay.  Never silently overwrite an earlier observation.
6. Add freshness, schema, coverage, and duplicate alarms.  Failure must be
   distinguishable from a valid zero-row market state.

Completion check: one backfill slice and two live runs produce stable,
deduplicated rows and a documented source-quality status.

## 3. Run a defensible comparative analysis

Use for: DeFi, RFQ, AMM, GPU rental, or inference-market comparisons.

1. State the economic object, unit, clock, and executable action before
   selecting a comparator.  Do not compare a protocol aggregate to a quote
   book as though they were the same object.
2. Define one matched cohort: asset/model/GPU class, quality tier, region,
   execution-or-reliability tier, and observation window.
3. Separate posted from executable prices, available from utilized capacity,
   and token-denominated from USD-denominated costs.
4. Use identical estimands across markets when possible: quote dispersion,
   depth/impact, update hazard, fill/reject probability, concentration,
   entry/exit, utilization, and fee/take rate.
5. Treat endogenous price, flow, and capacity as a joint system.  Use event
   windows, market-wide shocks, and pre-specified controls rather than a
   cross-sectional correlation as a causal result.
6. Report exact coverage and data-quality flags with each number.  Mark
   horizons that lack power as gated rather than filling with a proxy claim.

Completion check: another researcher can reproduce every metric from a raw
source, a mapping table, and a recorded configuration hash.

## 4. Test public-quote routing before buying inference

Use for: route-preview questions, quote-based allocation simulations, and
deciding whether an authorized synthetic request panel is warranted.

1. Use saved endpoint snapshots; do not send a completion merely to infer a
   route unless a user has explicitly approved a key and spend budget.
2. Fix the model panel and workload shapes before the observation window. Treat
   prompt text as absent unless it changes a documented routing field; model
   token budgets and requested API capabilities are the relevant public
   inputs.
3. Apply the documented price weighting only to strictly positive public
   quotes. Record free/zero-price, single-provider, and missing-capability
   exclusions rather than assigning a made-up route probability.
4. Label output as simulated provider share, never routed flow. The public
   feed does not reveal the live eligibility filter, retries, or selected
   provider.
5. Require both time coverage and contiguous transitions before declaring the
   quote surface stable or changing. A wide cross-section is not a substitute
   for a 24-hour series.
6. Escalate to an account-level controlled probe or a privacy-preserving
   route-decision export only after the public simulation has meaningful
   movement and a specific validation question.

Completion check: `routing_simulation_runs` explains all absent groups,
`h43_routing_simulation_summary` passes its coverage gate, and the conclusion
states the simulated-versus-realized boundary.

## 5. Publish and operate a live monitor

Use for: dashboards, alerts, memo deployment, and scheduled research.

1. Maintain a source registry with freshness SLA, expected cadence, owner,
   backfill policy, and severity of failure.
2. Publish a run manifest for every pipeline run: code SHA, source watermark,
   row counts, schema hash, quality checks, and failures.
3. Fail the workflow for required-source failure, stale data, malformed
   schema, or an analysis exception; allow explicit optional sources only with
   a visible degraded-status flag.
4. Alert on data health first (missed snapshots, zero/coverage drops,
   timestamp lag), then on market events.  Events are not reliable when the
   collector is not reliable.
5. Keep raw data immutable and derived tables reproducible from a dated
   configuration.  Never auto-overwrite a published historical signal without
   recording a revision reason.

Completion check: a deliberately malformed source response fails or degrades
the monitor in the intended way, produces an actionable alert, and does not
publish a falsely healthy memo.
