# Source contract checklist

Record these fields before adding a source:

- Owner, endpoint, authentication environment variable, and rate/cost limit.
- Economic object, source grain, stable identifier, and timestamp/finality.
- Raw path, curated table/grain, mapping version, and expected minimum rows.
- Cadence/freshness SLO, required versus optional policy, and backfill window.
- Schema sentinel, zero-row interpretation, retry policy, and alert action.

Validate raw response status/body, normalized row count, uniqueness key, and
freshness. A missing credential or vendor outage must write `skipped` or
`degraded`, never a successful zero-row run.
