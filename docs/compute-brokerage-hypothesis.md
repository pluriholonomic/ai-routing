# The Compute Brokerage Hypothesis: a pre-registered structural forecast

Registered 2026-07-12. Builds on the layered analogy in
`marketplace-comparison-plan.md` and the empirical base in the memo (H1–H68).
This document states ONE unified hypothesis about where the open AI inference
market's structure converges, decomposed into dated, falsifiable predictions,
and the plan for testing each. Predictions are stated before the tests run.

## The hypothesis in one paragraph

The open AI inference market is converging to the structure of **retail
financial brokerage layered over commodity dealing** — not to a DeFi-style
disintermediated exchange. Concretely: (O) demand-side *origination* (harnesses,
agent platforms) captures and keeps the persistent fee margin by monetizing
captive, price-insensitive flow, PFOF-style; (R) the *routing* layer's take
compresses toward zero under multi-homing and zero-markup entry, forcing
routers to monetize via origination services, data, or vertical integration;
(Q) the *quoting* layer becomes a two-speed dealer market — thin-spread,
high-volume algorithmic repricers coexisting with slow posted-price dealers
who retain elevated prices on pinned flow — with adverse selection managed by
rationing rather than spreads; (P) the *physical* layer is an energy-only
capacity market whose missing-money problem resolves through explicit capacity
products (provisioned throughput, priority tiers), a maturing GPU
forward/futures complex, and vertical integration; and (I) an *integrity*
layer (signed weight/quantization attestation) emerges only after a
quality-misrepresentation scandal, on the adtech ads.txt path. Across layers,
an **integration ratchet** operates: firms combining captive order flow with
execution and capacity gain share against pure-plays, driving M&A across
layer boundaries.

Two invariants make this "brokerage over dealing" rather than any exchange
analogy: (i) the **elasticity wedge** — intermediary price-sensitivity (routing
elasticity ≈ −1.15) exceeds end-user price-sensitivity (≈ −0.05) by an order
of magnitude or more, permanently, because that wedge *is* the origination
rent; (ii) **quantity clears, price administers** — demand shocks are absorbed
by queues, throttles, and deranking at all horizons under ~1 month, with
posted prices repricing on strategic (rival/lifecycle) events, not load.

## Layer predictions (each dated, with kill criteria)

### O — Origination keeps the margin

- **O1.** Harness-layer effective markup (subscription + per-token markup over
  provider list) does NOT compress below ~15% on retail flow through 2027,
  even as router fees fall. Benchmarks: MetaMask 0.875% (5+ yrs uncompressed),
  Robinhood PFOF, Uber take 25→30%.
- **O2.** Explicit PFOF appears: providers or routers paying harnesses for
  flow (revenue shares, exclusive default-model deals, "recommended provider"
  placements) within 18 months. Signature: harness default-model choices
  decouple from price/quality frontier.
- **O3.** Harness flow is measurably less price-elastic than API-key flow
  (routing elasticity on app-attributed traffic < half of aggregate H4).
- **Kill:** harness markups compress alongside router fees (→ the whole stack
  is a commodity pipe and the PFOF mapping is wrong).

### R — Routing take compresses

- **R1.** OpenRouter's effective take (posted fee + any hidden spread) falls
  below 3% OR volume share migrates ≥15 points to zero/low-markup routers
  (HF Inference Providers, Cloudflare, Vercel) by end-2027. Benchmark: SSP
  takes 20-25% → 10-15% within 4 years of header bidding.
- **R2.** Hidden spread stays ≈ 0 (H13 venue basis) — the router cannot build
  an ISBA-delta because quotes are publicly auditable. Any detected hidden
  spread > 1% falsifies the "transparent procurement" reading and flips the
  adtech mapping from loose to tight.
- **R3.** Routing mechanism evolves toward auctions: within 24 months at least
  one major router introduces per-request provider bidding or an OFA-like
  mechanism; providers publicly lobby for quality-scored (opaque) rather than
  cheapest-first routing (the format-lobbying signature, mirror of FPA).
- **R4.** Router concentration follows the solver/builder curve: 2–4 routers
  ≥85% of routed-marketplace volume within 24 months, regardless of low take.
- **Kill:** take holds ≥5% for 3 years while zero-markup rivals stay <5%
  share → routers possess origination power themselves; re-map router as
  platform (Booking.com), not exchange.

### Q — Two-speed dealer market

- **Q1.** Repricing cadence bifurcates: an identifiable set of algorithmic
  repricers (structural breaks in repricing markers) emerges; slow dealers
  sit persistently +10–30% above fast dealers on identical open-weight models
  (Brown-MacKay), sustained by pinned flow.
- **Q2.** Margins rise with algorithmic saturation, not fall: in model-markets
  where ALL major providers are algorithmic, margin proxies are HIGHER than
  mixed markets (Assad +28% analog). This is the collusion-risk prediction;
  its inverse (margins fall everywhere with adoption) is the commoditization
  reading — either outcome is informative, and we pre-commit to reporting
  whichever obtains.
- **Q3.** Dispersion never converges to zero: quality-adjusted gap between two
  cheapest providers stays within Baye-Morgan bounds (≥3% even at N≥15),
  because pinned/loyal flow funds it.
- **Q4.** Adverse selection stays quantity-managed: toxicity→rationing (H23)
  strengthens; no provider moves to toxicity-priced spreads (no per-customer
  pricing) before attestation exists.
- **Q5.** Per-model provider counts follow entry-then-consolidation: k* grows
  ~√demand on listing, then active (routed-share>1%) provider count per
  mature model-market shrinks toward 2–5 within 12–24 months of listing
  (UniswapX/builder curve), even as listed counts stay high.

### P — Physical layer grows a capacity market

- **P1.** Provisioned/priority capacity products' share of provider revenue
  rises materially (directional: from single digits toward the PJM-like
  15–20% range) by 2028; new capacity-product launches accelerate (count of
  providers offering PTU-analogs grows monotonically).
- **P2.** Diurnal/peak pricing appears: at least one major provider introduces
  time-varying or load-varying posted prices within 24 months (RM adoption —
  the "1975 airlines discover yield management" moment). Until then, price
  loads ≈0 on diurnal harmonics while latency/429s load fully.
- **P3.** GPU futures viability: cross-index basis (CME/Silicon Data vs
  ICE/Ornn vs SemiAnalysis vs OpenRouter-implied) converges to <5% dispersion
  and open interest grows with both neocloud shorts and lab longs; kill
  criteria per bandwidth-trading failure (persistent wide basis, one-sided
  participation, trade counts in the hundreds).
- **P4.** Forward premium is signed by conditional skewness of spot (B-L),
  and aggregate provider overcapacity (ED buffer) compresses it
  (Douglas-Popova translated).
- **P5.** Exit of pure per-token providers: provider exit hazard is decreasing
  in provisioned-contract share, increasing in per-token-only exposure
  (missing-money selection).

### I — Integrity layer arrives late, after scandal

- **I1.** Quantization/weight misrepresentation is present now and increasing
  in price competition: P(endpoint diverges from reference) rises with
  discount-to-median (MFA logic).
- **I2.** No attestation standard emerges until a public scandal; after one,
  adoption is fast but unenforced-downstream (ads.txt path: >90% adoption,
  ~10pt fraud reduction, fraud migrates).
- **Kill for I1:** divergence uncorrelated or negatively correlated with
  discount → quality competition is honest; drop the MFA mapping.

### X — Cross-layer integration ratchet

- **X1.** Integrated players (own model + serving, or own harness + routing)
  gain routed share faster than pure-plays (Gupta-Pai-Resnick
  complementarity).
- **X2.** ≥3 cross-layer acquisitions among (router, harness, provider, lab)
  categories within 24 months.

## Testing plan

Numbering note: modules H70+ to avoid collision with the parallel session's
H-series (≤H67 as of registration; H68 competition ranking taken).

### Phase 1 — now, existing capture (target: 2 weeks)

| Module | Tests | Prediction(s) |
|---|---|---|
| H70 repricer census | Assad markers, adoption breaks, both-adopt margin regression | Q1, Q2 |
| H71 gap(N) curve | Baye-Morgan benchmark + quality-adjusted residual → pinned-share estimate | Q3, O3 (input) |
| H72 price-vs-queue | shock-loading variance decomposition, diurnal-harmonics RM test | invariant (ii), P2 baseline |
| H73 reaction typing | classify rival responses: match-stick / punish-revert / Edgeworth | Q2 mechanism |
| H74 cadence hierarchy | Brown-MacKay price-level vs cadence class; fast-follower rule estimation | Q1 |
| H7v2 pass-through | rockets-and-feathers asymmetric ECM through the 2025-26 GPU cycle | P-layer cost linkage |
| H75 price forensics | Ben-Yehuda battery: round numbers, synchrony, calendar timing | administers Q interpretation |
| H35/36v2 | B-L skewness+variance premium; ED-buffer as storability regressor | P4 |
| H76 wedge | formal routing-vs-end-user elasticity wedge with CIs (H4 + repricing DiDs vs published end-user estimates) | invariant (i), O3 |

### Phase 2 — probe extensions (target: 4–8 weeks)

1. **Firmness probes** (extend capture_probes): measure reject/timeout/latency
   degradation vs quote staleness and aggressiveness → last-look test (Q
   layer, upgrades H10). Requires: probe variants pinned to specific providers
   (`provider.order`, `allow_fallbacks:false`).
2. **Fingerprint probes**: logprob/eval divergence vs reference weights,
   regressed on discount-to-median (I1). Requires new probe type (logprobs
   where supported; small eval battery elsewhere); budget ~$20/mo.
3. **Neutrality audit**: routing choice model on accumulated
   router_route_attempts; provider fixed-effect residuals (R2 companion).
4. **App-attributed elasticity split** (O3): repricing-event DiDs interacted
   with app-leaderboard demand composition.
5. **First-outage reputation event study** (Cabral-Hortaçsu) + pre-exit
   shirking test, from uptime history + fingerprint drift.

### Phase 3 — structural trackers (quarterly re-runs, pre-registered here)

1. **Fee-migration panel** (O1, R1): quarterly scrape of harness pricing pages
   (Cursor, Cline ecosystem, Janitor etc.), router fee schedules, BYOK terms;
   compute per-layer take. New capture: harness pricing pages (Wayback
   backfill where possible).
2. **PFOF watch** (O2): harness default-model/provider changes vs
   price-quality frontier; disclosure scraping of revenue-share deals.
3. **Capacity-product tracker** (P1, P5): census of provisioned/priority SKUs
   and prices (Azure PTU, Bedrock PT, OpenAI/Anthropic priority, neocloud
   reserved), Wayback-backfilled; provider exit hazards vs contract mix.
4. **Futures viability tracker** (P3): cross-index basis panel as CME/ICE
   products go live; open-interest and participation once published.
5. **Concentration curves** (R4, Q5, X1): monthly router-share estimates
   (public disclosures + relative growth proxies), per-model active-provider
   HHI, integrated-vs-pure-play share growth.
6. **Auction-format watch** (R3): router mechanism announcements; provider
   public comments on routing policy (format-lobbying signature).

### Scorecard and reporting

Each prediction gets a row in a `hypothesis_scorecard` table (prediction id,
status ∈ {untested, consistent, inconsistent, killed, confirmed-dated},
last-updated, evidence pointer). The nightly memo gains a "Compute Brokerage
Hypothesis" section rendering the scorecard. Predictions are graded only by
their pre-registered criteria above; revisions require a new dated section
appended here, never edits to this one.

## What would make us abandon the whole hypothesis (not just a layer)

1. Router take persists ≥5% for 3+ years with no share migration AND harness
   markups compress — margins living at the routing layer inverts the
   brokerage structure.
2. Prices begin clearing load at high frequency (price-load loading > 0.5 at
   hourly horizons across the panel) — the dealer/administered reading fails
   and a spot-exchange analogy becomes primary.
3. The elasticity wedge closes (routing elasticity magnitude falls toward
   end-user elasticity) — no origination rent exists to sustain the brokerage
   layer.
