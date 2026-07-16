# H80 outcome-free accrual audit — 2026-07-16 08:27 UTC

## Scope and isolation

This audit reconstructs the randomized first-position assignment ledger from
54 retained successful `probes.yml` artifacts created on or after 2026-07-14.
The audit projected only the following columns before loading the frame:
`source`, `event_id`, `run_ts`, `policy`, `observed_at`, `model_id`, `study_id`,
and `metadata_json`. Response, provider-selection, latency, cost, token, retry,
and HTTP-status fields were not loaded.

The existing H80 assignment parser deduplicated event identifiers, restricted
the sample to `openrouter-routing-crossover-v2`, and replayed the published
block seed. The 500-per-arm outcome gate was not changed.

## Current assignment support

| Policy | First-position assignments | Remaining to 500 |
|---|---:|---:|
| OpenRouter default | 22 | 478 |
| Pinned cheapest | 24 | 476 |
| Pinned second | 22 | 478 |
| Pinned random | 24 | 476 |

- 92 of 92 candidate first-position assignments replay exactly.
- The sample contains 92 blocks in 22 hour clusters.
- Four models contribute exactly 23 blocks each, giving normalized model
  entropy 1.0 and model-support dominance 0.25.
- The observed first-position rate is 4.063 blocks per hour.
- The assignment-only projection is 470.6 hours to the gate at the pooled rate
  and 492.0 hours at the slowest observed arm rate.
- Outcomes remain masked and the confirmatory cutoff remains unset.

## Claim boundary

This is a collection-integrity result, not a treatment-effect estimate. The
forecast extrapolates the observed assignment cadence only; GitHub scheduling,
model eligibility, random arm imbalance, and provider availability can delay
the gate. The four dynamically selected hot models and one owned account do not
identify effects for all OpenRouter models, accounts, or user traffic.

The audit was performed independently of the Hugging Face mirror while its
repository revision endpoint returned HTTP 504. The source artifacts remain in
GitHub Actions retention and are also included in the daily compaction path.
