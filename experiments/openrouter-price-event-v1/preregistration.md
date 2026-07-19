# OpenRouter public-price event study v1

Status: discovery design frozen; event-wave paid execution disabled pending
H95 isolation, source-health validation, and response-study canary acceptance.

## Event definition

Events are detected using public endpoint menus only. A provider-model-endpoint
event is a prompt/completion quote-index change of at least 5%, or a provider
rank crossing at unchanged aggregate quote. Price cuts, raises, and pure rank
crossings are labeled separately. The detector must observe the same endpoint
before and after, at least two eligible providers, and a healthy source. Menu
removals, source failures, ambiguous identity changes, and simultaneous schema
changes are recorded as exclusions and send no paid requests.

## Frozen waves and assignments

The event registry and all target times are hashed before outcomes. Target
waves are event time, +15 minutes, +1 hour, +6 hours, and +24 hours, with fixed
maximum lateness of 10, 10, 20, 45, and 120 minutes. Each wave contains four
fresh bounded-default assignments, one documented price-sort assignment, and
one exact moving-provider pin. Arm order is deterministic from the event ID and
recorded seed. A missed wave remains missed; it is not backfilled or moved.

At each wave the current public menu is frozen and hash-linked to the event
plan. A menu change can make the wave ineligible but cannot alter the original
arm or target time. Price increases are a prespecified sign placebo. Matched
no-change controls use only pre-event model, provider count, quote rank,
dispersion, time-of-week, and prior owned-selection support.

Operationally, a successful 11-snapshot public-capture job triggers W0 planning.
Bounded remote jobs wait to the already-frozen W1 and W2 target times, freeze a
new contemporaneous menu, upload its hash-linked plan before any request, and
then execute only if the paid gates are open. Hourly recovery handles the wider
W3 and W4 windows. A job that starts after `latest_at` records the wave as
missed and sends nothing; it never relabels or backfills the wave.

## Outcomes and claim boundary

Primary discovery estimands are the change in moving-provider selection
probability relative to matched controls and the difference between default and
documented price sorting. The quote-fading diagnostic is an initial selection
gain followed by higher failure, latency, rate limiting, derank, or quote
reversal. It is an adverse-selection signature, not evidence of strategic
intent or literal front-running. This study cannot observe request order across
users, private flow, or whether a provider saw a particular request before a
quote change.

Discovery requires at least 80% complete W0-W2 waves for timing feasibility.
Any confirmatory study receives a new ID, frozen sample horizon, disjoint
events, 60 clean cuts plus 60 controls, at least ten models and ten movers, and
a marker-first one-time release regardless of sign.
