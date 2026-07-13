# Public router-enforcement monitor (H68)

## Purpose

H68 promotes already-captured public frontend enforcement fields into an
explicit, auditable panel:

- `rate_limited_5m` and `success_5m` form a five-minute rate-limit incidence
  measure;
- `is_deranked` yields exact observed derank-onset and release transitions;
- `derankable_error_30m`, `capacity_ceiling_rpm`, and `recent_peak_rpm` provide
  public context for an enforcement observation.

It is deliberately a router-enforcement monitor, not a request-flow or
front-running monitor.  The data have no request identifier, customer identity,
selected-provider fill, enforcement reason, or within-window ordering.

## Construction

The input is the public `congestion_intraday` table, with targeted
`event_bursts_congestion` rows preferred when both observed the same endpoint
and timestamp.  Exact duplicate artifact rows are removed.  Each endpoint path
is contiguous only when consecutive observations are at most ten minutes
apart; a workflow gap does not create a state transition.

| Derived field | Definition |
|---|---|
| `rate_limit_incidence` | `rate_limited_5m > 0` |
| `rate_limit_share_5m` | `rate_limited_5m / (success_5m + rate_limited_5m)` where the denominator is positive |
| `rate_limit_onset` | a contiguous transition from zero to positive `rate_limited_5m` |
| `derank_onset` | a contiguous `is_deranked: false -> true` transition |
| `derank_release` | a contiguous `is_deranked: true -> false` transition |
| `at_risk_derank` | a contiguous transition whose preceding state was not deranked |

The derank-hazard output splits at-risk observations by whether the preceding
five-minute rate-limit count was positive.  It is descriptive only.  If no
derank onset is observed, H68 reports the hazard as not identified rather than
manufacturing a zero effect.

## Outputs

| Artifact | Grain | Use |
|---|---|---|
| `h68_router_enforcement_panel` | endpoint × retained timestamp | incidence, state, and contiguous-transition ledger |
| `h68_derank_events` | observed onset or release | exact public state transitions |
| `h68_rate_limit_events` | rate-limit onset | public pressure-event candidates |
| `h68_derank_hazard` | prior-rate-limit stratum | descriptive transition incidence |
| `h68_summary` | run | coverage and claim boundary |

Run it against hydrated public data:

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h68 --out analysis
```

## Relation to routing-capture hypotheses

H68 supplies an independent enforcement layer to H42/H67.  A future
quote-and-ration analysis can ask whether a pre-registered quote-cut cohort is
followed by an observed rate-limit onset or derank transition.  It must still
show independent realized or balanced aggregate flow before claiming capture,
and it cannot call a public enforcement event front-running.
