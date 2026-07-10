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

## 5. Add a cross-router comparator or owned-route telemetry

Use for: Hugging Face Inference Providers, an AI gateway, or a controlled
provider-selection calibration study.

1. Separate public quote/performance data from owned request telemetry. Neither
   is a substitute for market-wide routed-volume data.
2. Match models through an explicit, versioned alias map. Never infer that two
   similarly named listings represent the same model revision.
3. Keep router-policy simulations separate by policy and disclose all missing
   health/capability fields. A public fastest/cheapest reconstruction is not a
   route-decision log.
4. Land owned attempts in `router_route_attempts` only after removing prompts,
   completions, and raw request/response bodies. Link a salted request reference
   to quote snapshot, policy, and study id.
5. Before paid probes, pre-register workload shapes, randomization, rate and
   spend limits, retry handling, and a stop condition. Do not use a gateway's
   outer upstream label as the final provider inside another router.
6. For a causal policy comparison, register a `model_epoch` manifest through
   `register-routing-study`, retain a private seed commitment, and ingest the
   complete pre-assigned epoch ledger before reading H50. Treat a policy-field
   mismatch, overlap, post-start assignment, or failed negative control as a
   design failure rather than a usable treatment observation.

Completion check: public source health is green, quote/policy output joins only
through the versioned alias map, and owned telemetry contains no payload fields.

### Shadow-routing extension

Use `config/router_registry.toml` to add a router only after identifying whether
its policy is publicly documented or account configured. Put public quote or
performance feeds into a labeled simulation; import configured Cloudflare,
Portkey, and LiteLLM policies through `orcap import-router-policy`; and run H45
for base shares, outage states, and quote-flip conditions. Do not label any of
those outputs as realized selection without a redacted controlled attempt in
`router_route_attempts`.

## 6. Publish and operate a live monitor

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

## 7. Audit a block-pinned Uniswap V3 tick book

Use for: V3 depth research, concentration diagnostics, or changes to the
TickLens/Multicall2 collector.

1. Treat `uniswap_tick_book` as virtual-liquidity state for the two registered
   pools—not an order book, dollar depth, route, or fill log.
2. Require the corresponding `uniswap_tick_book` source-run ledger row to be
   `success`, `coverage_complete=true`, and complete for every registered pool
   before using a snapshot. H56 also requires its certified tick-row total to
   match the curated rows, and rejects unverified or truncated snapshots.
3. Keep the state block finality-buffered and require Multicall2's returned
   block number to equal the requested block. A current-state call mixed with
   historical state is an invalid snapshot.
4. Scan every usable bitmap word from the on-chain `tickSpacing`; a partial
   range, malformed word, duplicate tick, or row-cap breach invalidates that
   pool's entire snapshot.
5. Preserve raw signed liquidity net and gross values exactly. The zero sum of
   signed net liquidity across initialized ticks is a bookkeeping check, not a
   dollar-depth estimator.
6. Before reporting depth, pre-register trade direction, token decimals,
   notional grid, fee treatment, tick-crossing traversal, and a same-block
   QuoterV2 validation. H57 implements the USDC-to-WETH post-spot-impact
   version and retains its Quoter error panel; keep it distinct from H56's
   state audit and from a realized execution claim.

Completion check: a source-ledger-verified H56 snapshot has one final block per
pool, every usable word was scanned, every tick maps back to its bitmap word,
and any executable-depth conclusion is supported by a separately documented
traversal rather than by the raw tick table alone.

## 8. Monitor a public on-chain declared-node registry

Use for: qualifying a decentralized-compute registry without an API key or
mistaking a registration record for available capacity.

1. Query the documented Nosana Nodes program through canonical public Solana
   JSON-RPC with `getProgramAccounts`, `withContext=true`, the NodeAccount
   discriminator filter, and only the 54-byte fixed header. Do not use a
   frontend credential, browser session, or the authenticated Markets API.
2. Retain the returned context slot and parse only the documented header
   fields. The collector must fail closed if a returned record is malformed,
   has the wrong discriminator, or produces a raw-account/parsed-row mismatch.
3. Require the `nosana` source-run ledger row to be `success`,
   `query_succeeded=true`, and `registry_complete=true` before using H58. H58
   independently repeats the expected-row and unique-node checks.
4. Label every output as a *declared registration profile*. The audited flag
   and declared resource fields do not establish liveness, free capacity, GPU
   count/model, availability, price, utilization, queue, job completion, or
   delivered compute. Do not merge them into H41 or a cross-venue price panel.

Completion check: the source ledger certifies that every returned header
parsed once, the snapshot slot is retained, malformed fixtures degrade the
source, and outputs remain separate from capacity and utilization claims.

## 9. Monitor public aggregate compute-job activity without collecting jobs

Use for: tracking a public decentralized-compute activity control while
excluding individual job definitions and participant-level metadata.

1. Use only the documented public Explore aggregate endpoints: `/jobs/stats`,
   `/jobs/count`, `/jobs/running`, and the aggregate timestamp endpoints. Do
   not call `/jobs`, `/jobs/:address`, or a browser-authenticated endpoint.
2. Retain the rolling source bucket timestamp and the collector timestamp.
   The API may revise a historical bucket, so H59 keeps only the latest
   captured revision per metric and bucket and retains a revision count.
3. Require the aggregate count of running jobs to equal the sum of public
   market-level running counts in the same capture. A mismatch degrades the
   source rather than presenting a mixed-time snapshot as coherent.
4. Label duration exactly as source-defined job duration. The public UI's GPU
   compute-hours presentation does not independently prove GPU-hours,
   completed useful work, LLM traffic, capacity, utilization, payment, or
   routing allocation.

Completion check: raw evidence contains aggregate responses only, no job
definition or payer identifier is retained, the running-count identity holds,
and H59 remains power-gated until seven bucket days and 100 latest buckets per
series are present.
