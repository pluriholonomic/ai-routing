# H94 prospective cross-router pass-through design

Frozen: 2026-07-17, after one simultaneous catalog cross-section and before the
first observed longitudinal price transition in the new three-router panel.
The future-only activation cutoff is `2026-07-17T04:30:20Z`, the timestamp of
commit `6017dae`. The earlier 03:30 UTC discovery cross-section is excluded from
every H94 event, elapsed-time, and promotion-gate calculation.

## Question

Do inference routers merely display a shared upstream provider price book, or
do router-specific update policies create temporary price and allocation
wedges?

The initial H93 cross-section found identical input and output prices for 28 of
29 Hugging-Face-linked same-provider/model pairs. That fact motivates H94 but
does not answer the dynamic question.

## Primary population

The unit is a provider-model commodity observed on at least two of Glama,
NemoRouter, and Requesty. The model must have a unique literal suffix match to
the official OpenRouter catalog and a non-null Hugging Face identifier. Provider
normalization removes punctuation only; no hand-authored provider aliases or
fuzzy model matches enter the primary analysis.

## Events and estimands

1. A price transition occurs when either posted input or output price changes
   between consecutive successful capture vintages for the same
   router/provider/model. Reappearances after a missing product vintage and
   gaps above 2.5 hours are not transitions.
2. A common shock is a one-to-one pair of cross-router transitions for the same
   provider/model that reaches the same input-output price vector within 90
   minutes. A difference of at most one minute is coded as simultaneous; larger
   signed differences identify the observed leader, subject to interval
   censoring at the capture cadence.
3. The primary estimands are the share of eligible transition events covered by
   a matched common shock, the router-pair lead probabilities, and the median
   absolute update lag.
4. A price-wedge spell begins when a simultaneous same-provider/model pair
   differs by more than 1% for the registered 1,000-input/500-output-token
   workload. Spell duration is interval-censored between the last divergent
   capture and the first converged capture; unresolved spells are explicitly
   right-censored.
5. The allocation consequence is whether a price transition is followed within
   90 minutes by a change in the simulated cheapest-provider set for that
   router/model. This remains a public-shadow outcome, not realized routing.

## Inference and falsification

- Confidence intervals resample provider-model commodities, not quote rows.
- A circular-time-shift placebo preserves every router's event identities,
  prices, and cadence while breaking contemporaneous alignment. Its exact
  finite-window randomization p-value asks whether observed synchronization is
  stronger than chance alignment of the same event streams.
- Same-model/different-provider and same-provider/different-model target-price
  coincidences are negative-control families. They distinguish commodity-level
  propagation from router-wide batch refreshes or provider-wide menu updates.
- Router-pair tests are adjusted as one family with Holm's method. Lead-lag
  claims require a non-simultaneous matched-shock sample and reject a 50/50
  leader null after adjustment.
- Contract-field agreement is audited separately. Matching labels and prices do
  not establish identical region, SLA, rate limits, capacity, fallback rules,
  caching terms, or billing semantics.

## Promotion gates

The primary dynamic result is not promoted until all of the following hold:

- at least seven elapsed days;
- at least 48 successful snapshots per router;
- at least 30 adjacent price transitions;
- at least 15 matched common shocks; and
- at least 10 independent provider-model commodities with transitions.

The allocation-consequence result has a separate gate of 15 linked simulated
route switches. A null dynamic result after the primary gates pass is released
and interpreted as evidence for common upstream menu administration, not as
proof of perfect competition.

## Claim boundary

H94 measures public posted-menu synchronization. It cannot identify private
eligibility, actual order flow, fill firmness, provider profit, user welfare, or
literal front-running. Realized-routing validation requires budget-capped owned
requests with selected provider, retries, cost, latency, and completion status.
