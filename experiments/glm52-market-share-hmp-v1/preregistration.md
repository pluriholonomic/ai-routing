# GLM-5.2 market-share HMP experiment v1

Status: frozen prospectively before the first study-specific paid request.

Protocol source: `config/glm52_market_share_hmp_v1.toml`. The implementation
must write its SHA-256 digest into every assignment, aggregate, and release.
The detailed derivation and experimental rationale are in
`papers/glm52-market-share-hmp-validation-plan-2026-07-21.md`.

## Question

Do multiple active GLM-5.2 price experimenters generate a market-share path
elasticity distinct from unilateral elasticity, and does lagged common price
experimentation make that path response easier to learn in a way consistent
with the Hansen--Misra--Pai signal-coupling mechanism?

The study does not identify market-wide OpenRouter flow, provider algorithms,
provider costs, communication, agreement, intent, or collusion. Those fields
are frozen to false in the protocol.

## Ordered property chain

1. **MS1, exact identity.** The declared inverse-power router recovers the
   unilateral and group-path elasticity identities to numerical tolerance. The
   singleton wedge is zero.
2. **MS2, public multiplicity.** Prospective natural cuts show a response
   ordered by co-cutter share mass relative to clock-preserving shifts.
3. **MS3, owned routing.** Realized first-choice shares for the project's
   requests show the corresponding singleton/pair/multiple ordering.
4. **MS4, incidence.** Active-group gains displace passive groups, with buyer
   cost, success, latency, fallback, and fidelity reported separately.
5. **MS5, memory.** Lagged co-cutter exposure improves future quote or routing
   prediction beyond current state and passes lead, shift, and leave-out tests.
6. **MS6, mechanism.** A marginal-preserving break in common exogenous-shock
   ordering attenuates the gradient and any critical-memory learning-time
   boundary in calibrated simulation, including a heterogeneous learner class.

Promotion is sequential. A later property cannot rescue an earlier failure.

## Events

The focal market, provider types, 2% material-cut threshold, 15-minute primary
co-move window, sensitivity windows, active and anchor lists, request shape,
price exponent, and campaign dates are frozen in the TOML file. Only positive
request-shaped prices enter the paid panel. A candidate event is written before
outcomes, after two unchanged pre-event captures. It is provisional at the cut,
gets a final multiplicity after its co-move window and two post-event public
captures, and becomes confirmatory-clean only after a frozen 60-minute
contamination window. Events overlapping provider-set, author-price, derank,
rate-limit, derankable-error, capacity-ceiling, snapshot-gap, or public-health
changes remain in the ledger but are excluded from the clean confirmatory
panel.

Multiplicity is singleton, pair, or multiple, but the primary treatment is the
pre-event share-weighted co-cutter exposure. Co-mover labels never use paid
outcomes.

## Paid blocks

At each due event horizon, the exact public menu is frozen before requests.
Identical one-token tasks are assigned in randomized complete blocks to broad
default, broad price-sort, focal-plus-anchors, focal-plus-one-seeded-co-cutter
plus anchors, all active providers plus anchors, and anchors only. Every arm
uses fresh session material. Provider pins are operational diagnostics and do
not enter delegated-share estimands.

The causal paid contrast is the effect of this project's randomized eligible
menu at fixed public quotes. The pre/post natural-price contrast is
observational. A separate HMP-specific hourly background block runs the same
six arms with two replicates and a deterministically rotating focal provider.
It supplies a genuinely pre-event owned-routing measurement for later events;
it is not pooled with the pre-existing GLM campaign. Natural-event waves have
queue priority over a background block.

## Inference and support

MS2 uses provider-clock circular shifts. Randomized paid arms use exact
within-block randomization inference. Natural-event realized responses use
whole-event intervals and provider-pair/model-day clustering. Simulation uses
paired seeds. Holm correction is applied to MS2--MS5 in order.

The seven-day pilot is operational and variance-estimation only. Confirmatory
analysis requires at least 28 complete days, 30 clean events and 800 covered
choices in each multiplicity stratum, 10 provider-pair clusters, three selected
active providers, 90% exact-menu coverage, exact assignment integrity, and no pair
above 20% of the primary statistic. If a cell accrues slowly, time is extended;
definitions are not relaxed.

## Stop and release rules

Paid execution stops only for a frozen budget, secret/redaction failure,
malformed telemetry, persistent API failure, or policy issue. It never stops on
an outcome. Request-level records remain private. Aggregate support and results
are released at an immutable revision regardless of sign, with the strongest
permitted language determined by the first failed property in MS1--MS6.
