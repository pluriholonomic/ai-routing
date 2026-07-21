# Within-type collusion screens v1

## Estimand and conditioning

WF-16 freezes four provider-model-period pricing regimes using only its first
60% of dates. This study uses only the subsequent WF-16 holdout and estimates
collusive-looking behavior separately inside each regime. A regime is never a
claim about immutable provider type or intent.

## Tests

1. Same-regime response timing: after a strictly observed same-regime rival
   move, measure whether the target reprices within 24 hours. Pair every event
   with the same target at a frozen +48-hour placebo time. Inference reports an
   exact paired event test and a provider-model cluster bootstrap. Anchor-adopter
   events that land on the public author price are excluded from the primary
   anchor response test.
2. Price clustering: measure mean pairwise holdout log-price distance within
   model-day-regime cells. Shuffle frozen regime labels within model-day 2,000
   times while preserving type counts. Anchor clustering is reported but never
   scored because a shared public author price creates it mechanically.
3. Typed memory: on the first half of holdout dates, fit a regularized daily
   repricing model using own lagged state and aggregate rival activity. Compare
   its later-date log loss with a model that separates same-regime from
   other-regime rival activity. Bootstrap the improvement by model. A regime
   requires at least ten repricing events in both fit and test periods.
4. Repeated leadership: report which same-regime initiators attract subsequent
   repricing, the follower-response HHI, and top-leader share. This is
   descriptive because leader opportunities are endogenous.
5. Punishment and reversion: after a cut, classify no response, persistent
   competitive following, initiator withdrawal, or a candidate episode in
   which same-regime rivals cut and restore at least 99% of their pre-cut price
   while the initiator holds its cut. Candidate initiations are thinned to one
   per provider-model every 96 hours so overlapping repricing bursts are not
   counted as independent episodes. The last class is a Green-Porter-style
   pattern, not collusion proof.

## Multiplicity and promotion

Response and clustering p-values are Holm-adjusted across all four regimes.
A regime is a `multi_proxy_candidate_not_identified` only if at least two of
three independent legs survive: excess response with a positive cluster
interval, non-anchor excess clustering, and positive typed-memory predictive
value with a positive cluster interval. At least one surviving leg must be the
dynamic response or typed-memory test; clustering cannot promote a regime by
itself. Leadership and event taxonomy cannot promote a regime by themselves.

## Identification boundary

Common costs, public information, common pricing software, capacity shocks,
and asynchronous competition can generate the same observables. We do not see
communications, agreements, marginal costs, profits, private rebates, or
intent. Consequently `collusion_identified` is frozen to false in v1.
