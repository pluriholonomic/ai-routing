# Independent-style review, round 13

Manuscript: *Administered Menus and Hidden Clearing: The Microstructure of the
Market for Machine Intelligence*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **6.5/10, weak reject.** The paper now contains a credible new
cross-router measurement result and a functioning prospective data pipeline.
The result is not yet an acceptance-level dynamic or causal contribution.

## What is successful

1. **The measurement pipeline is real and remote.** Credential-free catalogs
   from Glama, NemoRouter, and Requesty are normalized, source-health checked,
   archived, and collected by a successful hourly GitHub Actions workflow. The
   collection no longer depends on the local computer.
2. **The static posted-price fact is credible as a pilot.** In one simultaneous
   cross-section, 28 of 29 Hugging-Face-linked same-provider/model pairs have
   exactly equal input and output prices across routers. The exact-match share
   is 96.6%, with a Wilson 95% confidence interval of [82.8%, 99.4%].
3. **The accounting result is exact.** The quantity-share and revenue-share
   elasticity specifications differ mechanically by one when they use common
   weights and fixed effects. This is a useful correction to an otherwise
   tempting revenue-maximization interpretation.
4. **The claim boundaries are unusually disciplined.** The paper distinguishes
   posted quotes from firm fills, simulated allocation from realized routing,
   revenue from profit, and bounded proxy calculations from welfare.

## What is not successful

### 1. The new headline is static, not behavioral

The 28/29 result is a single simultaneous cross-section. H93 currently has zero
observed price events, zero coincident cross-router events, and zero simulated
route switches. It therefore cannot show pass-through speed, leadership,
staleness, strategic response, quote fading, or routing effects. Six of the
seven preregistered promotion conditions remain closed: seven elapsed days,
three repeatedly observed routers, 48 snapshots per router, 30 price events, 15
common shocks, and 15 simulated switches.

### 2. The natural null makes the static result less novel than it first appears

The relevant null is not that independent routers draw prices randomly. If
routers relay provider-authored public menus, equality is mechanically expected.
The static result establishes a common upstream price-book interpretation; it
does not yet establish competitive price convergence or router discipline. The
novel result would be the dynamics of the exceptions: which venue leads, how
long wedges survive, whether eligibility or capacity differs, and whether the
wedge changes simulated or realized allocation.

### 3. Economic comparability of matched rows is not established

The same normalized provider and model labels need not imply the same contract,
region, service-level agreement, context limit, rate limit, capacity, fallback
policy, prompt caching, or billing convention. The single material DeepSeek
exception—a 296.6% workload-price wedge—could be economically meaningful, but
it could also be stale metadata, a model-version mismatch, or a different
direct-provider contract. The current public fields do not distinguish these
explanations.

### 4. Posted-price differences are not linked to realized routing

H93 simulates cheapest-provider choices but observes no selected provider, retry
chain, admission decision, fill price, latency, or completion status. It cannot
yet show that a temporary quote wedge reallocates demand. Small owned-traffic
probes on matched provider/model cells are needed to validate the public shadow
against realized selection and to detect phantom liquidity or stale-quote
capture.

### 5. The revenue result remains unpromoted

The current revenue analysis covers ten days and 50 listed-price moves, below
its own 30-day and 200-event gates. The exact provider-model fixed-effects
coefficient is imprecise, and the event study has a positive pretrend. Very
little raw price variation survives the entity and time fixed effects. The
pooled near-minus-one elasticity is largely an accounting/revenue-share fact,
not an identified provider demand curve.

### 6. The randomized firmness experiment is not a primary result

The first-position prefix remains below the preregistered 500 assignments per
arm. Until that prefix opens, the visible-versus-blinded result cannot support
the strongest front-running-style interpretation. Larger aggregate counts do
not repair a masked primary endpoint.

### 7. Profit, welfare, and the mechanism-design conjecture remain unidentified

The data omit provider billing details, marginal cost, capacity opportunity
cost, router take rates, user value, and quality-adjusted completion utility.
Consequently the paper can estimate bounded gross-revenue proxies, but not
profit maximization, allocative efficiency, consumer surplus, or global welfare.
The welfare mechanism remains a model calibrated by public observables, not a
validated empirical conclusion.

### 8. The empirical paper is still too broad relative to its strongest result

The manuscript combines sticky menus, exact price atoms, revocability, public
shadow routing, randomized quote visibility, revenue stationarity, welfare, and
cross-router price pass-through. A top reviewer can reasonably see a catalog of
careful but individually bounded findings rather than one decisive mechanism.
The current best organizing claim is narrower: **routers mostly distribute
common upstream price books, while asynchronous channel updates may create
temporary routing wedges.** The longitudinal data must establish the second
half.

## Required evidence for acceptance

1. Freeze at least seven days with 48 or more observations per router, 30 price
   events, 15 matched common shocks, and 15 simulated switches; publish the
   result even if the dynamic effect is null.
2. Estimate event-time pass-through and lead-lag hazards with router and
   provider-model fixed effects, pretrend diagnostics, multiple-testing control,
   decoy updates, and noncompetitive-model negative controls.
3. Run budget-capped owned probes on matched cells to observe selected provider,
   cost, latency, failure, and fallback; evaluate on future time and held-out
   provider/model groups.
4. Audit whether matched offers have comparable region, context, capacity,
   caching, fallback, and billing semantics. Treat unmatched contract terms as
   a separate product rather than a price wedge.
5. Either clear the H91 30-day/200-event and randomized 500-per-arm gates or
   move those claims out of the abstract and main contribution list.
6. Freeze one immutable data revision, preregistration, code commit, and held-out
   analysis date before opening the primary longitudinal results.

## Decision

**Weak reject, but closer than round 12.** The paper now has a defensible pilot
fact and a credible route to a novel contribution. It does not yet demonstrate
the behavior that would make the result economically sharp: asynchronous
repricing, temporary stale quotes, and measurable allocation consequences.
