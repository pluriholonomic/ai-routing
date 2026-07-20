# H96 operational sharding and checkpoint amendment

Status: frozen before the first successfully retained paid H96 outcome.

Date: 2026-07-20 UTC

## Motivation

The first seven scheduled H96 jobs did not complete. Each job attempted to run
all eligible model-shape blocks sequentially under a 20-minute Actions timeout,
and route attempts were written only after the full loop returned. The durable
dataset therefore contains zero paid H96 route attempts as of this amendment.
The manual run contains assignments only and is marked preflight.

## Prospective operational change

- Each remaining scheduled run retains at most three complete randomized
  model-shape blocks. Selection is a deterministic circular shard of the
  outcome-free eligible block list using the recorded run seed.
- Every policy assignment within a selected block is retained. In particular,
  the sticky seed/repeat ordering and every exact-pin arm remain intact.
- The collector rewrites one cumulative redacted attempt checkpoint after every
  completed request. The workflow's `always()` artifact therefore preserves
  completed requests even if a later request or the job itself times out.
- The Actions timeout increases from 20 to 50 minutes. The per-run quote cap
  remains $0.35 and the campaign stop loss remains $4.20.

The campaign start, campaign end, cron cadence, policies, request shapes,
privacy contract, and estimands are unchanged. No failed scheduled start is
replaced and the campaign is not extended. Results remain a bounded pilot and
are not promoted as a confirmatory estimate merely because this amendment
allows observations to survive operational failure.
