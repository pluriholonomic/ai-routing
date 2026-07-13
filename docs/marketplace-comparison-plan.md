# Sharpening the marketplace comparison: literature synthesis and experiment slate

Five parallel literature sweeps (platform economics/ACM EC, DeFi microstructure,
ridesharing/gig operations, adtech/ad exchanges, electricity/cloud/commodity
markets) conducted 2026-07-12. This file distills the improved analogy and the
unified experiment slate. Full agent reports archived in session transcripts.

## The upgraded analogy: one market, five layers, five different analogs

The single mapping (harness=wallet, router=DEX aggregator, model=protocol,
provider=LP) forces one analogy onto a stack whose layers behave like
*different* markets. The literature supports a layered mapping:

| Layer | AI element | Best analog | Evidence anchor | Old DeFi analog breaks because |
|---|---|---|---|---|
| Origination | Harness / agent app | **PFOF broker (Robinhood) / agency-DSP** | $3.8B PFOF 2021; Robinhood PFOF = fixed % of spread; MetaMask Swaps 0.875% uncompressed 5+ yrs | Wallets don't monetize captive flow; brokers do. Fees stick at origination, not routing |
| Routing | OpenRouter etc. | **FX aggregator / SOR over last-look dealer streams; ad exchange running procurement** | DEX router fees → 0 while wallet fees held; SSP takes 20-25% → 10-15% under header bidding | DEX aggregators route over *firm* on-chain liquidity; providers can reject/degrade (revocable quotes) |
| Quoting | Inference provider | **Last-look dealer / retail electricity supplier** (menu-cost administered prices) | Texas retail passes through 43-47% of wholesale; post-2017 AWS spot = administered price + preemption clearing | LPs are passive pooled capital, always firm at curve price; providers actively quote, ration, reprice discretely |
| Asset | Open-weights model | **Listed instrument / commodity spec**; model author = **issuer without a fee switch** | OSS model earns 0 of secondary flow (= Uniswap-Labs fee-switch debate) | "Protocol" implies fee accrual; the model is what gets *priced*, not what earns |
| Physical | GPU capacity | **Energy-only electricity market** (missing money → capacity contracts) | PJM capacity $2.2B→$16.4B in 3 auctions; PTU/provisioned-throughput = bilateral capacity market genesis | Pool TVL is locked per-pool; GPU inventory redeploys across models like dealer balance sheet |
| Integrity | (missing) weight attestation | **ads.txt / sellers.json gap** | MFA = 21% of impressions/15% of spend; ~1/3 of third-party endpoints diverge from reference weights (Model Equality Testing) | DeFi tokens are fungible-by-construction; model endpoints are spoofable |
| First-party APIs | OpenAI/Anthropic direct | **Internalizer (Citadel Securities)** | Internalized vs exchange volume split in US equities | CEX analogy misses that internalizers execute *their own* captive flow |

Net: replace "DeFi/AMM" with **"a quote-driven dealer market (FX/adtech-shaped)
sitting on an energy-only commodity layer, financed by a PFOF-shaped
origination layer."** The intent-market verdict from screen v1 survives — it
applies to the routing layer specifically.

## Benchmark constants imported from other markets

| Statistic | Value | Source market | Our comparator |
|---|---|---|---|
| Gap between 2 lowest prices, N=2 → N=17 | 22% → 3.5% | Shopper.com electronics (Baye-Morgan-Scholten 2004) | gap(N) per model from 5-min quotes |
| Algorithmic-pricing margin lift, both-adopt duopoly | +28% (0 if one adopts) | German gasoline (Assad et al. JPE 2024) | repricer census × margin proxy |
| Slow-repricer price premium over fast, identical SKU | +10-30% | Online retail (Brown-MacKay 2023) | cadence classes × price levels |
| Retail pass-through of wholesale cost | 43-47% | Texas electricity (Zarnikau-Woo 2020) | token price on GPU rental index ECM |
| Reputation premium, established vs fresh identity | 8.1% | eBay (Resnick et al. 2006) | uptime-history hedonic |
| First negative feedback: sales growth | +7% → −7% | eBay (Cabral-Hortaçsu 2010) | first-outage event study |
| SSP take under multi-homing pressure | 20-25% → 10-15% in ~4yr | Header bidding 2015-18 | router take under HF/CF/Vercel zero-markup entry |
| Unattributable intermediary "delta" | 15% → 3% after log standardization | ISBA/PwC programmatic | hidden spread (H13 venue basis; currently ≈ 0) |
| Solver/filler concentration trajectory | fragmented → 2-5 firms in 12-24 mo | UniswapX (2000+ → 12 fillers), builders (HHI ~3900) | provider HHI per model over time |
| End-user demand elasticity | 10% price cut → +0.5-0.7% usage | OpenRouter 100T-token study | vs routing elasticity −1.15 (H4): the broker wedge |
| Fill-rate collapse when price can't clear | ~100% → ~25% completion | Uber NYE 2014-15 surge outage | demand shocks → price vs 429/latency loading |
| Fee-shrouding revenue effect | +21% | StubHub RCT (Blake et al. 2021) | posted per-token vs effective per-request cost elasticity |
| Capacity payments share of generator revenue | ~3% → 15-20% in 2 yrs | PJM 2024-2027 | PTU/provisioned share of provider revenue |
| JIT liquidity steady-state share | ~0.3% of volume (vs 40% perception) | Uniswap v3 | serverless/on-spike capacity share |

## Unified experiment slate (deduplicated, ranked)

### Tier A — runnable now on existing capture

1. **Algorithmic-repricer census + both-adopt margin test** (Assad method). Detect
   repricer adoption per provider via structural breaks in repricing markers;
   regress model-market margin proxy (price − GPU-index cost/token) on
   {none, some, all} adopter counts. Signs differ under collusion vs
   commoditization. *Most decisive single test in the slate.*
2. **Shock-loading decomposition: price vs queue** (Uber surge-outage logic,
   continuous version; = electricity quantity-rationing test). Demand shocks →
   fraction loading on Δprice vs Δ(429, p95, derank) at 5min→1wk horizons.
   Extends H37/H38 congestion panel.
3. **Gap(N) dispersion curve** vs Baye-Morgan 22%→3.5%; residual quality-adjusted
   gap estimates the pinned/loyal-flow share. Extends H2.
4. **Impulse-response classification of rival reactions**: match-and-stick
   (competitive) vs punish-and-revert (Calvano) vs sawtooth/reset
   (Musolff-Edgeworth). Extends H21 with typed dynamics.
5. **Brown-MacKay cadence hierarchy**: do slow repricers sit +10-30% above fast
   ones on identical models, with a stable fast-follower undercut rule?
6. **Rockets-and-feathers asymmetric ECM**: token prices on GPU rental index
   through the Oct-2025 spike → May-2026 slide; β⁺ vs β⁻ at daily+weekly
   frequency (Bachmeier-Griffin caution). Upgrades H7.
7. **Ben-Yehuda administered-price forensics**: round-number clustering,
   calendar/competitor-timed repricing, cross-provider synchrony, band
   structure. Interprets tests 1-6.
8. **Bessembinder-Lemmon extension**: GPU forward premium on conditional
   variance AND skewness of spot; idle-capacity (ED-buffer) as the
   Douglas-Popova storability regressor; date the backwardation→contango flip
   against the skewness sign change. Upgrades H35/H36.

### Tier B — needs probe extensions (harness exists: capture_probes.py)

9. **Quote-firmness / last-look test**: reject/timeout/degraded-latency rate vs
   quote staleness and aggressiveness. No DeFi RFQ paper has this; upgrades H10
   from status aggregates to request-level evidence.
10. **Model-equality fingerprinting vs price discount** (MFA/obfuscation test):
    P(endpoint diverges from reference weights) as a function of
    discount-to-median. Needs logprob/eval probes (new probe type; Gao et al.
    method). The Ellison-Ellison twin: posted-price vs quality-adjusted-price
    elasticity gap.
11. **Routing-vs-end-user elasticity wedge**: H4 (−1.15) vs published end-user
    elasticity (≈−0.05..−0.07) — the defining broker-market statistic;
    sharpen with repricing-event diff-in-diffs (eBay tax-elasticity design).
12. **Router-neutrality (Bernanke) audit**: choice model on realized probes;
    provider fixed effects unexplained by price/latency/uptime = the
    self-preferencing residual. Cheap falsifiable null.
13. **First-outage reputation event study** (Cabral-Hortaçsu discontinuity) +
    pre-exit shirking (quality drift before delisting).

### Tier C — slow-moving structural trackers (pre-register now)

14. **Missing-money watch**: share of capacity migrating to provisioned/priority
    contracts (PTU etc.); per-token-only provider exit hazard vs utilization.
    The electricity analogy's dated structural prediction.
15. **Fee-migration panel**: take rates by layer (provider spread, router take,
    harness markup) against the SSP-compression and MetaMask-persistence
    templates; event studies on zero-markup router entry (header-bidding
    replication).
16. **Forward-market viability tracker**: cross-index basis dispersion
    (CME/Silicon Data vs ICE/Ornn vs SemiAnalysis vs OpenRouter-implied);
    bandwidth-failure kill criteria vs weather-derivatives success path.
17. **Chao-Wilson menu calibration**: implied delay costs from tier spreads
    (priority premium vs batch discount) consistent across providers; throttle
    ordering by tier during bursts.
18. **Entry-law and concentration trajectory**: log(providers per model) on
    log(demand) — k*=O(√n) slope test; provider HHI per model vs the
    builder/filler convergence curves; integration test (do providers owning
    models/harnesses concentrate faster — Gupta-Pai-Resnick complementarity).

## Competitive positioning

Closest prior art: Demirer-Fradkin-Tadelis-Peng (NBER w34608), Fradkin
(arXiv:2504.15440), the 100T-token study (arXiv:2601.10088), and Du
(arXiv:2603.28576). All use OpenRouter *usage/price-list* data. None have:
the 5-minute per-provider quote panel, the repricing-event stream, burst
sampling, realized-routing probes, or the GPU-cost joins. Tier A experiments
1-5 and Tier B 9-12 are infeasible with their data and unclaimed.
