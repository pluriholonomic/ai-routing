# Privacy-preserving router-decision export request

## Objective

Measure whether a public quote or capacity action precedes excess realized
allocation after controlling for the public quote surface and enforcement
state.  The design is intended for a research partnership with a router and,
where possible, a provider.  It does not request prompts, completions, user
identifiers, IP addresses, account identifiers, API keys, or raw payloads.

## Minimum router-side export: seven fields

One row per attempted route, or an equivalent fixed five-minute aggregate with
an auditable join key:

| Field | Purpose |
|---|---|
| `request_ref` | router-salted opaque correlation identifier; never a user identifier |
| `arrival_at` | establish the request's arrival ordering |
| `route_committed_at` | establish the selection boundary |
| `candidate_set_version` | hash/version of eligible endpoints and public quote snapshot |
| `selected_endpoint` | realized selected provider endpoint or a salted endpoint key |
| `retry_outcome` | terminal success/failure plus retry/fallback count and typed reason |
| `quote_or_capacity_action_at` | endpoint's versioned quote/capacity-change timestamp, with a coarse reason class if available |

The router may replace `selected_endpoint` with a stable salted key and map it
locally to the public provider label.  Timestamps should be UTC with a stated
clock source and precision.  For an aggregate-only export, the provider/model
bucket, candidate-set version, and interval boundary are required so that rows
cannot be silently mixed across a quote change.

## Complementary provider-side export

For a participating provider, retain the same public endpoint key and
five-minute buckets for offered quote/capacity version, allocated attempts,
accepted attempts, rejected/rate-limited attempts, and server-side update time.
No request payload, user identifier, or customer routing context is required.

## Pre-registered tests

1. **H43 calibration:** does the public shadow predict selected provider after
   conditioning on candidate-set version?
2. **R2 undercut-capture:** does a rank-improving cut raise selected share with
   flat pre-trends and matched non-moving competitors?
3. **R3 stale-quote capture:** does an unchanged endpoint gain allocation after
   a competitor-only shock?
4. **R4 quote-and-ration:** does an allocation gain coincide with a higher
   rejection/fallback incidence or a later quote/capacity reversal?
5. **Pre-selection information test:** is a provider action ordered strictly
   after `arrival_at` but before `route_committed_at`, and does a blinded or
   placebo control remove the effect?

Only the fifth test, with evidence that the provider could observe the
pre-selection signal, can support a literal front-running allegation.  The
first four are allocation and reliability evidence, not intent evidence.

## Governance

- Retain data in a separate private store; publish only reviewed aggregates.
- Apply a minimum-cell threshold and suppress low-volume provider/model cells.
- Retain an immutable data dictionary, versioned extraction query, and
  exclusion ledger.
- Do not send this request or any data externally without a separately
  authorized partnership conversation.
