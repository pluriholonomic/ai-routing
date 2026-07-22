# GLM-5.2 market-share HMP data dictionary

Study ID: `openrouter-glm52-market-share-hmp-v1`.

The tables below are private inputs unless explicitly described as aggregate.
No prompt, response text, authorization header, API key, or request payload is
retained.

## Event and queue tables

### `glm52_hmp_run_ledger`

One outcome-free heartbeat per detector run. It records the code protocol hash,
source health, event and wave writes, due-wave count, and planned task count.
It is the immutable clock for the 28-complete-day gate; wall-clock time alone
does not accrue support.

### `glm52_hmp_events`

Append-only versions of public GLM-5.2 price events. `event_id` is stable across
versions. `event_status` is `provisional`, `multiplicity_finalized`, or `final`.
`preliminary_eligible` permits time-sensitive early waves; `clean_event` becomes
true only after the complete 60-minute provider-set, author-price, endpoint
health, derank, rate-limit, derankable-error, snapshot-gap, and capacity-change
screen. Analysis uses the latest version of each event.

### `glm52_hmp_wave_plans`

Immutable event-time waves keyed by event and horizon. The provisional event can
create only `m0`; a finalized multiplicity can create `m15`; `m60`, `m240`, and
`m1440` require a final clean event. A missed tolerance is not silently retried.
Hourly `mshmp-background-*` waves are separate pre-event measurements with two
replicates per arm and a focal provider rotated over currently public active
providers. Natural-event waves have queue priority.

### `glm52_hmp_candidates`

The redacted, request-shaped OpenRouter endpoint menu frozen before assignment.
It contains public provider identity, endpoint tag, quote components,
compatibility, quote caps, and a snapshot hash. It contains no routing outcome.

### `glm52_hmp_public_panel`

Prospective public GLM-5.2 provider quotes, author-relative request-shaped
prices, frozen provider group, and price-only shadow shares at the five-minute
source cadence. It powers the public time-series diagnostic and contains no
paid outcome.

### `glm52_hmp_assignments`

The immutable randomized assignment written before a paid call. Primary key is
`task_id = study | event | wave | model | shape | arm | replicate`. It includes
the exact provider allowlist/order controls, price caps, seed, manifest hash, and
protocol hash. Presence of an assignment reserves the task even if execution
crashes, which gives at-most-once rather than retry-until-observed semantics.
The outcome-free plan and an outcome-free execution receipt may be retained as
GitHub Actions artifacts. They never contain a selected provider, request
reference, attempt row, cost, latency, fallback, or spend-ledger row.

## Outcome and budget tables

### `glm52_hmp_attempts`

Redacted outcomes for this study only. It stores requested policy, selected and
completion provider metadata returned for the project's own request, success or
error status, fallback, cost, token counts, latency, and manifest identifiers.
It does not identify market-wide OpenRouter flow or request ordering.
These rows are checkpointed directly to the access-controlled Hugging Face
dataset and are never retained as artifacts by the public GitHub repository.

### `paid_spend_ledger`

The shared append-only paid-study spend checkpoint. HMP rows are isolated by
study ID and task ID. CI applies per-run, per-day, and campaign quote-cap gates
before execution.
The ledger follows the same private-Hugging-Face-only storage boundary as
attempt rows.

## Published aggregate tables

### `support_by_multiplicity.parquet`

Counts final clean events and covered choices for singleton, pair, and multiple
strata, plus whether each frozen support threshold is reached.

### `arm_summary.parquet`

Attempt counts by randomized menu arm. Selection, cost, latency, and fallback
outcomes are replaced with nulls until the complete support gate passes.

### `event_aggregate.parquet`

Public multiplicity exposure and covered-choice counts by event. Realized
active/anchor rates are null until the complete support gate passes.

### Simulation tables

`controlled_router_factorial.parquet` contains exact declared-rule
counterfactuals. `multiagent_factorial.parquet` contains simulated agent/world
rows. `paired_signal_interventions.parquet` contains coupled-minus-shuffled
paired-seed contrasts. These tables cannot identify a deployed provider's
algorithm, costs, communication, intent, or live collusion.

The weekly ten-seed bundle lives under `simulation/`. The daily one-seed smoke
test lives under `simulation-monitor/`; it supplies only the MS1 implementation
check and cannot overwrite or promote the full bundle.

## Keys and joins

- Event versions: `event_id`; retain the highest event-status stage and latest
  append within a stage.
- Wave: `(event_id, wave_id)`.
- Assignment/attempt/spend: `task_id`.
- Exact menu block: `block_id`.
- Protocol provenance: `protocol_sha256`.
- Public source provenance: immutable Hugging Face dataset revision plus event
  source-run fields.

## Confirmatory release gate

Release of outcomes requires all of: 28 complete healthy-source days, 30 clean
events and 800 covered choices in each multiplicity stratum, 10 provider-pair
clusters, three selected active providers, at least 90% exact-menu coverage,
100% assignment-to-attempt integrity, no duplicate task IDs, one protocol hash,
and no event-cluster configuration contributing more than 20% of support.
