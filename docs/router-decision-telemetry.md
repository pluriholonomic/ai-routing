# Private router-decision telemetry contract

This contract implements the redacted data request in
[`router-decision-export-request.md`](router-decision-export-request.md).
It is an opt-in local ingestion interface.  It sends no requests, contacts no
partner, and stores no raw payloads.

## Per-decision events

One JSONL object per attempted route must include:

```text
event_id, study_id, router, arrival_at, route_committed_at,
candidate_set_version, retry_outcome
```

Optional non-payload fields are `request_ref` (a router-salted opaque key),
`selected_endpoint`, `retry_count`, `quote_or_capacity_action_at`,
`provider_signal_at`, `action_class`, `experiment_arm`, and `assignment_id`.
The allowed experiment arms are `observational`, `provider_visible`,
`provider_blinded`, and `decoy_signal`.  Every non-observational record needs
an `assignment_id`; retain the corresponding immutable randomization manifest
with the private study material.

```bash
uv run orcap ingest-router-decisions --input redacted-router-decisions.jsonl
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h70 --out analysis
```

H70 preserves quote actions that occurred before a request as background
actions.  It only labels an action an ordered pre-selection action if it is
after recorded provider signal, after router arrival, and before route
commitment.  Timing alone is not a literal front-running conclusion.

## Fixed-interval aggregate flow

One JSONL object per provider-model interval must include:

```text
aggregate_id, study_id, router, model_id, endpoint, candidate_set_version,
interval_start, interval_end, attempted_routes, selected_routes,
succeeded_routes
```

Optional fields are `fallback_routes`, `public_quote_snapshot_id`, and
`quote_or_capacity_action_at`.

```bash
uv run orcap ingest-router-flow-aggregates --input redacted-router-flow.jsonl
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h69 --out analysis
```

This aggregate is sufficient for a public-state-adjusted residual-flow study
once it covers the registered interval and repricing gates.  It is not a
substitute for the randomized signal contrast needed to identify pre-selection
access.

## Privacy and retention

The validators reject prompts, completions, user/account fields, IPs, emails,
phone numbers, credentials, and raw request/response objects, including when
they are nested.  Keep these tables in the private controlled-study store and
release only reviewed, thresholded aggregates.
