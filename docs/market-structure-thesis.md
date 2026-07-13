# The Market Structure of Open AI Inference: Thesis, Experiments, Results

*Working synthesis, 2026-07-12. Data: the orcap capture pipeline (5-minute
per-provider quotes across ~300 models × ~70 providers on OpenRouter,
repricing-event stream, demand/congestion panels, GPU rental markets, realized-
routing probes) plus a 2023–2026 backfill. Companion documents:
`marketplace-comparison-plan.md` (literature map), `compute-brokerage-
hypothesis.md` (pre-registration), `analysis/hypothesis_scorecard.json` (live
status). Statuses reflect the panel as of this date; several results are
labeled preliminary by their own power gates.*

---

## 1. The question

Open-weights models turned inference into a commodity anyone can serve. A
marketplace formed around that fact — providers quoting per-token prices on
identical models, routers allocating requests across them, harnesses and
agents originating demand. The research question: **what kind of market is
this, and what will it become?** The method: empirics first, against explicit
comparator markets with published benchmark constants, so that every claim of
analogy is a falsifiable quantitative statement rather than a metaphor.

The original conjecture mapped the stack onto DeFi: harness↔wallet,
router↔DEX aggregator, open model↔protocol, provider↔liquidity provider. The
empirical screen broke that mapping in instructive ways, and a five-literature
sweep (platform economics, DeFi microstructure, ridesharing/gig operations,
ad exchanges, electricity/cloud/commodity markets) produced a sharper one.

## 2. The empirical base: what kind of market it is *today*

Forty-plus hypotheses have been run against the capture (H1–H68). The
established results, in order of evidential strength:

**Price formation is menu-cost dealing, not continuous clearing.** Only 2.8%
of endpoint-days reprice; the median change is 25.6% and 78% exceed 10% (H1;
replicated on a 3-year, 56k-pair LiteLLM backfill). Repricing is predictable
out-of-sample (AUC 0.87, H18), lifecycle-driven (cut-share falls from 65% in a
model's first month to 39% after a year, H17), and reactive (1,513 follower
pairs, median lag ~21h, 56% within 24h, H21). Prices are administered on cent
gridpoints (93% of quotes, CBH-6); demand shocks land on queues — over one
six-day window 7% of hot endpoints ever moved price while 80% experienced
rate-limit variation (CBH-3).

**Quotes are firm and pass through intermediaries unchanged.** Cheap quotes do
not reject more (the phantom-liquidity/last-look prediction is rejected,
p=0.02, H10); router-displayed prices equal provider-direct prices essentially
always (96.6% exact-zero basis across 326 pairs and 8 providers, H13; median
cross-router basis 0.0%, H44). There is no hidden spread — the adtech "delta"
extraction mechanism is absent.

**Routing is partially algorithmic, demand is not.** Within-model share-price
elasticity is −1.15 (se 0.09, H4) — between the router's documented
inverse-square default (−2) and pinned flow (0). End-user demand elasticity
is ~−0.05 (external estimates on the same platform). The wedge, ~20×, is the
defining signature of a brokered market: the intermediary shops, the customer
doesn't (CBH-7).

**Competition is entry and entrenchment, not price wars.** Prices fall
monotonically with provider count (−0.50 log points at N=2 to −1.13 at N=5+,
H3) and provider counts track demand (ρ=0.63, H20), but incumbents do not cut
on entry (precise null, 532 events, H26), dispersion does not shrink with N
(H2), and the cheapest-provider identity is sticky (H68: competition loads on
crowded dispersed quote boards behind stable price leaders; internally
consistent latent factor, α=0.81, split-half ρ=0.90). The gap between the two
cheapest quotes is bimodal: 48% exact ties (price-matching) and otherwise
large (median 8.3% at N≥10) — not Baye-Morgan's smooth decline and not
Bertrand ε-undercutting (CBH-2).

**The physical layer is an energy-only capacity market under bursty load.**
Demand has Fano factors ~10³, Hurst 0.84, INGARCH persistence 0.79 (H38/39);
providers hold proportional overcapacity (ED-staffing slope 0.83) consistent
with Erlang loss and no congestion-pricing regime (H37); output is non-storable
and non-resalable, carry strategies are unprofitable after the no-resale drag
(H35/36), and token prices deflated −54% over three years against GPU rents
−19/−24% — deflation is competition/efficiency, not cost pass-through (H7).

**The two sides are decoupled.** Harness-usage structure (count, concentration,
category mix) is uncorrelated with supply-side competition (all |ρ|<0.06);
only aggregate volume weakly correlates (+0.17). The router insulates each
side from the other's structure — what a functioning aggregator does.

**Where the DeFi analogy is quantitatively wrong.** Cross-venue dispersion is
~200× DeFi's (27.5% CV vs 14.2bps); repricing cadence ~10³× slower than base
fee; the take rate is ~100× aggregator levels (5.5% vs bps); and there is no
mempool — "front-running" can only mean quote-surface front-running, which is
measurable but different in kind.

## 3. The thesis: what it will become

**The Compute Brokerage Hypothesis** (pre-registered 2026-07-12): the market
converges to **retail financial brokerage layered over commodity dealing**.
Each layer inherits the equilibrium of its true analog:

| Layer | Analog | Converges to |
|---|---|---|
| Origination (harnesses, agents) | PFOF broker / agency-DSP | Keeps the persistent margin (≥15%); explicit pay-for-flow deals emerge; captive flow is measurably price-insensitive |
| Routing (OpenRouter, HF, gateways) | FX aggregator over dealer streams / ad exchange | Take compresses toward zero under multi-homing (SSP path: 20–25%→10–15% in ~4yrs); mechanism evolves toward per-request auctions; 2–4 routers regardless of low take |
| Quoting (providers) | Last-look dealer / retail electricity supplier | Two-speed dealer market: fast algorithmic repricers with thin spreads vs slow posted-price dealers +10–30% above them on pinned flow; adverse selection managed by rationing |
| Asset (open models) | Listed instrument; author = issuer without a fee switch | Commodity specs enabling cross-venue competition; author monetization migrates to first-party serving or certification |
| Physical (GPU capacity) | Energy-only electricity market | Missing money resolves via capacity products (PTU/priority = bilateral capacity markets), maturing GPU futures, vertical integration; a first mover adopts time-varying pricing (the yield-management moment) |
| Integrity | ads.txt gap | Quantization/weight misrepresentation grows with price competition until a scandal forces attestation, which then under-enforces |

Two invariants distinguish brokerage-over-dealing from any exchange story:
**(i)** the elasticity wedge persists (it *is* the origination rent), and
**(ii)** quantity clears while price administers at horizons under ~a month.
Cross-layer, an **integration ratchet** (order flow × execution × capacity
complementarity) drives share toward integrated players and M&A across layer
boundaries. Full dated predictions and kill criteria:
`compute-brokerage-hypothesis.md` §"Layer predictions".

Historical trajectories imported as quantitative priors: header bidding
compressed non-Google SSP takes 20–25%→10–15% in four years while MetaMask's
0.875% wallet fee survived five years untouched; every DeFi allocation layer
(solvers, fillers, builders) converged to 2–5 firms within ~18–24 months;
PJM capacity payments went from ~3% to 15–20% of generator revenue in two
years once scarcity arrived; post-2017 AWS spot settled into administered
prices with preemption clearing.

## 4. The experiments

**Phase 1 — run now on existing capture (CBH-1..9, executed 2026-07-12):**

| Module | Test | Imported benchmark |
|---|---|---|
| CBH-1 | Algorithmic-repricer census + saturation-margin test | Assad et al. 2024: +28% margins when all adopt |
| CBH-2 | Gap(N) between two cheapest quotes | Baye-Morgan 2004: 22%→3.5%, never 0 |
| CBH-3 | Demand-shock loading: price vs queue; diurnal harmonics | Uber surge outage; post-2017 AWS; pre-RM airlines |
| CBH-4 | Typed rival reactions to cuts | Calvano 2020 punish-revert vs match-stick vs Edgeworth |
| CBH-5 | Cadence hierarchy: slow-over-fast price premium | Brown-MacKay 2023: +10–30% |
| CBH-6 | Administered-price forensics | Ben-Yehuda 2013 AWS spot battery |
| CBH-7 | Routing vs end-user elasticity wedge | PFOF logic; kill threshold 3× |
| CBH-8 | Rockets-and-feathers GPU pass-through ECM | BCG 1997; Texas retail 43–47% | 
| CBH-9 | Skewness-signed forward premium | Bessembinder-Lemmon; Longstaff-Wang |

**Phase 2 — probe extensions (harness live, variants to build):** quote
firmness/last-look (reject-vs-staleness on pinned-provider probes), weight
fingerprinting vs price discount (the MFA/obfuscation test), router-neutrality
audit (choice-model residuals on realized probes), app-attributed elasticity
split, first-outage reputation event studies.

**Phase 3 — quarterly structural trackers (pre-registered, to instrument):**
per-layer fee-migration panel, PFOF watch, capacity-product census, futures
cross-index basis with bandwidth-failure kill criteria, concentration curves
and the integration test.

## 5. Results to date

Scorecard (17 graded predictions): **5 consistent, 0 inconsistent**, 2
accumulating, 10 awaiting trackers/windows.

| Prediction | Status | Evidence |
|---|---|---|
| Invariant (i): elasticity wedge | **consistent** | 19.9× [17.3–21.7], kill threshold 3 |
| Invariant (ii): quantity clears, price administers | **consistent** | price ever-moved 7% vs rate-limit 80% of endpoints (6d); latency loads ~30× price at 30-min |
| Q1: slow-over-fast premium 10–30% | **consistent** | +13.8% [7.8–19.6] within model-day |
| Q3: dispersion floor ≥3% at high N | **consistent** | 8.3% median gap at N≥10; 48% exact ties |
| R2: hidden router spread = 0 | **consistent** | 96.6% exact-zero venue basis |
| Q2: Assad saturation test | accumulating | 13/68 active repricers; markets with repricers show *lower* markups (rank β −0.71) — commoditization branch so far; no all-algorithmic market yet |
| Q: collusion-signature watch | accumulating | 72% of 18 typed cuts show punish-and-revert — nominally the Calvano signature, currently confounded with launch experimentation; the single most important statistic to re-estimate at n≥100 |
| CBH-8/9 | gated | 6/90 and 6/60 required daily observations; self-activate |
| O1–O2, R1, R3–R4, P1–P3, I1, X2 | untested | trackers/windows open through 2027–28 |

Interpretation discipline: "consistent" means the pre-registered criterion is
met on the current panel, not confirmation — most tests are on days-to-weeks
of data and re-run nightly. The hypothesis dies, per its own terms, if the
router take persists ≥5% for 3 years without share migration while harness
margins compress, if prices begin clearing load at high frequency, or if the
elasticity wedge closes.

## 6. Positioning

Closest prior art — Demirer-Fradkin-Tadelis-Peng (NBER w34608), Fradkin
(arXiv:2504.15440), the OpenRouter 100T-token study (arXiv:2601.10088), Du
(arXiv:2603.28576) — works from usage and list-price data and reaches the
demand-side conclusions (competitive, differentiated, elastic-ish at the
model level). None observes the quote panel at 5-minute resolution, the
repricing-event stream, realized routing, or the GPU-cost joins; the
microstructure results (firmness, venue basis, reaction dynamics, cadence
hierarchy, the wedge) and the CBH structural forecast are, to our knowledge,
unclaimed territory.
