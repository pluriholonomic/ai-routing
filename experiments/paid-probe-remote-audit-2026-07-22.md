# Paid probe and Hugging Face audit — 2026-07-22

Audit time: 2026-07-22 20:13 UTC. This audit used GitHub run/job metadata,
redacted execution receipts, and aggregate private-Hub table checks. It did not
open blinded H95 request-level outcomes.

## Verdict

The remote paid-probe system is executing and persisting data, but the audit
found two ingestion/integrity defects that must be deployed before calling the
pipeline fully healthy:

1. Immutable execution artifacts carry prior checkpoints. Reassembling several
   artifacts produced exact physical row copies in current-day Hub buffers.
   Task-deduplicated budget reconstruction prevented double-counting spend, but
   physical tables and the IC assignment audit were inflated.
2. Twenty-two `openrouter-price-event-v1` task IDs had two non-identical spend
   records from different runs. Planning could finish before a serialized
   execution job ahead of it, then execute from a stale ledger after acquiring
   the shared lock. No other paid study had a conflicting task ID.

The patch collapses only completely identical rows during paid-table bundling
and compaction, while preserving conflicting identifiers for audit. Price-event
jobs now refresh the authoritative Hub plus in-progress artifact ledger after
acquiring the execution lease; execution remains fail-closed if any frozen task
is already present.

## Live execution evidence

| Study | Latest inspected paid execution | Receipt |
|---|---:|---|
| Adaptive router | `29947848926` | 15 attempted, 13 succeeded, $0.000503401 |
| GLM-5.2 HMP | `29950908064` | 12 planned; private checkpoint succeeded |
| GLM-5.2 routing | `29952761213` | 10 attempted/succeeded, $0.000597681 |
| Market measurement | `29928068098` | 43 attempted, 41 succeeded, $0.002196553808 |
| Score-memory quality | `29949617087` | 11 attempted/succeeded and graded, $0.00142166846 |

The latest HMP schedule run `29951984691` planned successfully and
cadence-skipped execution. Information-congestion routing and quality are
deliberately disabled while the 24-hour public-capture continuity gate is
closed. Score-memory routing is enabled but prospectively starts on
2026-08-04 21:15 UTC.

## Hugging Face evidence

Private dataset: `t4run/openrouter-market-history`.

- Inspected revision: `bf4fd421751da4894e1ee11dc571b203cda77f7e`
- Revision time: 2026-07-22 20:03:34 UTC
- Total files in manifest: 22,378
- Required secrets were present: `HF_TOKEN`, `OPENROUTER_API_KEY`, and
  `OPENROUTER_PRICE_EXPERIMENT_KEY` (values were not read).
- All inspected paid rows had `payload_retained = false`.

Task-deduplicated private-Hub totals at the inspected revision:

| Study | Unique tasks | Realized cost | Latest observation (UTC) |
|---|---:|---:|---|
| Adaptive router | 75 | $0.00850919444 | 2026-07-22 18:47:00 |
| GLM-5.2 HMP | 192 | $0.013764666 | 2026-07-22 19:29:32 |
| GLM-5.2 routing | 280 | $0.023061768022 | 2026-07-22 19:20:14 |
| Market measurement | 603 | $0.022197910976 | 2026-07-22 14:32:06 |
| Price-event probes | 775 | $0.11743882432 | 2026-07-22 16:40:00 |
| Price-response probes | 630 | $0.02270621146 | 2026-07-22 16:52:30 |
| Score-memory quality | 55 | $0.00723212629 | 2026-07-22 19:07:58 |

The successful 19:52 UTC GLM-5.2 routing execution was newer than the 19:41 UTC
artifact-to-Hub compaction that produced this snapshot. Its redacted remote
artifact is intact and is expected in the next compaction; it is not represented
as already persisted in the table totals above.

## Validation

- Focused regression suite: 54 passed.
- Full suite: 930 passed, 1 skipped.
- Scoped Ruff checks, shell syntax, YAML parsing, and `git diff --check`: passed.
- Repository-wide Ruff remains red because of 34 pre-existing findings outside
  this patch; none are in the changed Python files.
- Reproduced the IC Hub-plus-artifact overlap locally: 64 physical assignments,
  64 unique task IDs, zero conflicting duplicates after exact-row collapse.
