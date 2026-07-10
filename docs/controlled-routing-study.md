# Controlled capacity-routing study

## Purpose

H50 is the empirical bridge from the proposed capacity-certified routing
mechanism to an identifiable result. Public router quotes, simulated shares,
and decentralized-compute supply panels do not reveal actual selection or
delivery. An H50 study uses only an owned router account, redacted telemetry,
and pre-assigned **model × epoch** policy arms.

It does not send traffic, change a router configuration, reserve provider
capacity, or expose prompts/completions. An operator must separately authorize
the owned-account experiment and configure its hard spend, rate, and safety
limits.

## Design

The randomization unit is one non-overlapping `(study_id, model_id, epoch)`.
An epoch is normally 15 minutes. Block assignments by observable workload,
region, and time-of-day conditions; the H50 estimator standardizes treatment
effects within these registered strata and clusters inference at the epoch.

The minimum two-arm comparison is:

| arm | policy | purpose |
|---|---|---|
| `inverse_square_price` | disclosed reliability-weighted inverse-price proxy | public-policy baseline |
| `capacity_certified` | capped water-fill using an externally recorded commitment | proposed mechanism |

`lowest_cost` and `reliability_only` are optional additional baselines. Do not
randomize a policy that has not been implemented identically for all study
units, and never relabel a fallback path as the assigned treatment.

The primary outcomes should be fixed before study start:

- `attempt_success_rate`: successful divided by completed redacted attempts;
- `mean_cost_usd`: recorded owned-account cost per matching attempt;
- `capacity_shortfall_rate`: epoch-level `shortfall / allocated` from the
  separate capacity-outcome ledger; and
- `registered_value_net_cost`: an optional, explicitly declared value proxy,
  `value_per_success × success_rate − mean_cost`. It is not general welfare.

Choose one distinct negative control outcome, normally `mean_latency_ms` when
the study does not change a latency policy. A material negative-control effect
is a design warning, not proof of a mechanism effect.

## Pre-register before the first epoch

Generate a private random seed and retain it outside this repository. Commit
only its SHA-256 digest in the manifest. The manifest enforces at least 20
epochs and 100 attempts per arm; use higher thresholds if the expected effect
or success-rate variance requires it.

```json
{
  "manifest_id": "routing-rct-2026-07-15-v1",
  "study_id": "routing-rct-2026-07-15",
  "registered_at": "2026-07-14T12:00:00Z",
  "planned_start_at": "2026-07-15T00:00:00Z",
  "planned_end_at": "2026-07-22T00:00:00Z",
  "randomization_unit": "model_epoch",
  "randomization_seed_commitment": "<lowercase-sha256-of-private-seed>",
  "baseline_arm": "inverse_square_price",
  "arms": [
    {"name": "inverse_square_price", "policy": "inverse_square_price", "assignment_probability": 0.5},
    {"name": "capacity_certified", "policy": "capacity_certified", "assignment_probability": 0.5}
  ],
  "primary_outcomes": ["attempt_success_rate", "mean_cost_usd", "capacity_shortfall_rate"],
  "negative_control_outcome": "mean_latency_ms",
  "min_clusters_per_arm": 20,
  "min_attempts_per_arm": 100,
  "stopping_rule": "Stop only after both arms meet their registered coverage; do not stop on interim effects.",
  "metadata": {"workload_class": "fixed-short-chat", "epoch_minutes": 15}
}
```

```bash
uv run orcap register-routing-study --input redacted-study-manifest.json
```

The command rejects payloads, credentials, post-start registration, unsupported
arms, probability totals other than one, a non-model-epoch unit, and weak
minimums. It writes an immutable `router_study_manifests` row.

## Record pre-assigned epochs

Create the whole assignment schedule before the first assigned epoch, from the
private seed and the registered arm probabilities. Preserve the schedule and
the seed separately so an auditor can later verify the seed commitment and
assignment procedure. Each row is payload-free:

```json
{"assignment_id":"routing-rct-2026-07-15-a0001","manifest_id":"routing-rct-2026-07-15-v1","study_id":"routing-rct-2026-07-15","model_id":"meta-llama/llama-3.3-70b-instruct","epoch_start":"2026-07-15T00:00:00Z","epoch_end":"2026-07-15T00:15:00Z","assigned_at":"2026-07-14T12:05:00Z","treatment_arm":"capacity_certified","randomization_stratum":"short-chat-us-utc00","assignment_probability":0.5}
```

```bash
uv run orcap ingest-routing-assignments --input redacted-study-assignments.jsonl
```

An assignment must be recorded no later than its epoch start. H50 rejects
overlapping model-epoch assignments, unknown manifests/arms, probability
mismatches, assignments outside the registered window, and route attempts
whose recorded `policy` differs from their assigned arm.

## Record delivery separately from policy

Continue to import redacted attempts, commitments, and epoch outcomes through
the existing payload-free contracts:

```bash
uv run orcap ingest-route-attempts --input redacted-attempts.jsonl --format canonical
uv run orcap ingest-capacity-commitments --input redacted-commitments.jsonl
uv run orcap ingest-capacity-outcomes --input redacted-outcomes.jsonl
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h50 --out analysis
```

For capacity-certified epochs, the commitment and outcome keys must agree on
`study_id`, provider, model, and the half-open epoch interval. Keep a policy
field equal to the registered treatment-arm name on every attempt. Do not
backfill a different policy name after seeing outcomes.

## H50 outputs and decision rule

| output | meaning |
|---|---|
| `h50_routing_design_audit` | assignment-level pre-registration, window, arm, probability, and overlap checks |
| `h50_routing_epoch_panel` | one redacted aggregate outcome vector per assigned model epoch |
| `h50_routing_effects` | stratum-standardized treatment-minus-baseline cluster contrasts, standard errors, intervals, and normal approximations |
| `h50_summary` | study power/validity status and the claim boundary |

H50 reports `not_identified` without a manifest/assignment ledger,
`invalid_design` for a pre-registration or policy-consistency failure, and
`power_gated` until every registered arm reaches its own minimum epoch and
attempt count. Only `randomized_estimate_ready` means the owned-study contrast
is estimable. `randomized_estimate_ready_with_falsification_alert` means the
negative control has a nominal two-sided normal-approximation p-value below
0.05; qualify the result and investigate the design before presenting a
mechanism effect. H50 still does **not** show market-wide router behavior,
provider profit, a general welfare optimum, truthful private capacity reports,
or an optimal collateral bond.

Treat unexpected effects in the negative control, imbalance in pre-treatment
strata, missing cost records, or capacity outcomes that do not match their
commitments as falsifiers or qualification failures. Preserve all registered
outcomes and all completed epochs, including failures and cancelled attempts.
