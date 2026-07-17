# H81 prospective plan-ledger deployment evidence

Date: 2026-07-17

Status: end-to-end collector, durable compaction, and assignment-only release
audit verified.

## Why this audit is separate

H81 request artifacts contain restricted account-level execution records. They
are needed by the eventual marker-first analyzer, but they are broader than the
evidence required to verify prospective assignment persistence. The collector
therefore publishes a second artifact containing only an aggregate commitment
to the outcome-free plan rows. It contains no request record, selected provider,
cost, latency, generation identifier, retry reason, or outcome.

The earlier deployment run `29572291675` successfully executed the plan-first
collector at paper head `66f50fd`, but its mixed request artifact was not used as
audit evidence. Commit `c37fc6b` added log redaction and the independently
downloadable plan-only manifest before the next run.

## Prospective production run

- Collector workflow: `29572631254`
- Job: `87859742136`
- Source head: `c37fc6b6bca7521cda56d2765b8b144070392da7`
- Assignment run: `20260717T101151Z`
- Workflow result: success in 1 minute 13 seconds
- Plan-only manifest SHA-256:
  `1a4c45c1a79db3de5c9212a4fb88bd8743ad7a383c75eb649cd8eb10b3b0f714`
- Commitment to the two plan Parquet objects:
  `641a6766ed8da387c3effc6acb65a653e235236796bbf9504bfac5baff9cb221`

The manifest reports two plan files and two plan rows. Both carry the registered
study and run identifiers, randomized order, one-third first-policy assignment
probability, and `payload_retained=false`. The forbidden-field intersection is
empty; `outcomes_included=false` and `request_records_included=false` are
explicit. The checked-in copy is
`analysis/h81_plan_deployment_audit_29572631254.json`.

## Why the plan is genuinely pre-request

For each eligible block, the production control flow draws the block seed and
policy permutation, writes and closes the plan Parquet object, and only then
enters the request loop containing `_send_probe`. A failed write raises before
the first request call. The manifest hashes the objects returned by those
successful writes and is tied to the exact source commit through `GITHUB_SHA`.
This proves program-order persistence for this run; it does not use request
outcomes or infer timing from successful responses.

## Durable compaction and assignment-only gate

Compaction workflow `29572789506` checked out `c37fc6b`, passed all 571 tests on
its clean runner, assembled and published the buffered artifacts, and completed
all eight deterministic table shards. Its automatic confirmatory child workflow
`29573258132` pinned immutable dataset revision
`18ea5aa245cc931d5f49b452785a175f358db240`.

The H81 artifact contains only `assignment_only_gate.json`; its SHA-256 is
`a1d8c9f5955873d280ff6f018c89b8a36324eab0bbb0b18530f86d0e29e4cdd9`.
The checked-in copy is `analysis/h81_assignment_only_gate_29573258132.json`.
It reports:

- 92 intended first-position blocks with arm counts 33, 31, and 28;
- four explicit prospective pre-request plans;
- 88 combined unique plan/reconstruction rows over 44 historical runs;
- 95.65% plan-ledger coverage, with the four earliest recorded blocks retaining
  their direct block-seed fallback;
- 100% intended-assignment reconstruction, assignment replay, first-row
  observation, and treatment-metadata fidelity;
- a passing assignment-integrity gate; and
- `outcomes_queried=false`, `release_ready=false`, and remaining arm deficits
  7, 9, and 12.

This closes the operational deployment item from review round 27. It does not
open the outcome gate or strengthen transport beyond the two repeated H81
models.

## Latest accrual and frozen release presentation

Scheduled collector run `29573436177` added two more prospectively planned
blocks. Compaction `29573860829` checked out paper head `5633f1d`, passed
the then-current full suite, published the buffered artifacts, and completed all
eight shards. Automatic audit `29574322884` pinned immutable revision
`60d5a02005d553b956c903c1a8bd0b30df2d1636` and advanced H81 to 94 intended
blocks with counts 34/31/29, six explicit plans, 90 combined plan/reconstruction
rows, and all integrity and fidelity rates equal to one.

Commit `65e142526962a61a3101edacb16af61caa21d46d` then froze a deterministic
release table, two-panel figure, neutral LaTeX paragraph, and fail-closed
algebraic validator. The synthetic package compiles and renders, and the full
suite now has 573 passes. Exact-head audit `29574825052` checked out that
commit against the same immutable revision and again recorded
`outcomes_queried=false`. Its checked-in H81 gate artifact is
`analysis/h81_assignment_only_gate_29574825052.json`, with SHA-256
`de9a2fd9a5db6c752868f3caca6ae66246649bf821cd469f8ee3153cc07f9e90`.
The remaining arm deficits are 6, 9, and 11.
