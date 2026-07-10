# Phase 2b — Inference routing as an RFQ / quote-driven OTC market

Screen v1 rejected the AMM analogy and left "intent/solver market" standing.
This phase tests the sharper hypothesis: **OpenRouter is structurally an
aggregated RFQ market** — providers are PMM-style quoters with last look,
the router is an RFQ aggregator with an internal reliability posterior, and
harness flow is preferenced order flow.

## Structural mapping

| Inference market (observable) | RFQ / OTC quote-driven analog |
|---|---|
| Provider listed price (`endpoints_snapshots.price_*`) | Streamed firm-ish quote |
| Rate-limit / derankable error (`status_heuristics`) | Last-look reject / quote fade |
| `fortuna` Beta posterior, `is_deranked` | Aggregator's MM scorecard (fill-quality tiering) |
| `capacity_ceiling_rpm`, `capacity_tpm`, throughput | MM inventory / risk limits |
| Router default (inverse-price weighting) | RFQ aggregator best-quote selection |
| Variants `:floor` / `:nitro` / default | Order types: market-at-best / speed-priority / smart |
| BYOK traffic | Direct bilateral (disclosed) dealing |
| Quantization tiers (fp4/fp8/bf16) | Quality-differentiated instruments (wrapped-asset basis) |
| OpenRouter 5.5% take | Aggregator/venue take rate |
| Direct-provider APIs vs OpenRouter | On-venue vs off-venue (CEX/DEX) basis |
| GPU on-demand vs interruptible (vast.ai) | Spot vs funding/perp basis for the input |

## Hypotheses (H10–H15), pre-registered

**H10 — Last look / phantom liquidity.** *Data: `endpoint_stats_daily.record_json`
(status_heuristics_1d, fortuna, is_deranked) joined to listed prices.*
- Reject rate = (rateLimited + derankableError) / total, per endpoint-day.
- Tests: (a) within-model regression of reject rate on relative price (cheaper
  ⇒ more rejects = phantom-liquidity equilibrium); (b) recompute H2 dispersion
  on *executable* quotes (reject-weighted); LOOP verdict revisited — deep if
  executable-quote dispersion collapses toward the Uniswap 14 bps benchmark,
  retail-like if it doesn't move; (c) reject-rate distribution vs FX last-look
  norms (2–10%) and RFQ fill rates.
- Threshold: price–reject slope negative at p<0.05 with model FE ⇒ last-look
  equilibrium confirmed.

**H11 — Execution-quality-adjusted pricing.** *Data: `perf_comparisons_daily`
(tool-call & structured-output error rates, throughput, latency) + prices.*
- Tests: (a) hedonic extended with delivered-quality metrics — how much
  dispersion is a quality frontier vs a lemons discount; (b) 2×2 lemons test:
  are below-median-price × above-median-error cells overrepresented (χ²);
  (c) quantization discount curve (fp4 vs fp8 vs bf16 within model) as the
  wrapped-asset-basis analog.
- Threshold: quality metrics moving hedonic within-model R² above ~50% ⇒
  frontier market ("you get what you pay for"); staying <15% ⇒ H2's
  search-friction verdict stands even quality-adjusted.

**H12 — Compute basis term structure.** *Data: `gpu_offers_snapshots`
(on-demand vs bid per class, hourly; `duration` field).*
- Tests: (a) basis = on-demand median / bid median per class per day — level,
  vol, mean reversion half-life; (b) term structure: dph vs offer duration
  buckets; (c) comparator: perp funding / spot-futures basis stylized facts
  (mean-reverting, positively skewed spikes). Optional: Binance BTCUSDT
  funding history (public REST) as the quantitative comparator series.
- Feeds H7: which leg (spot or on-demand) do token prices cointegrate with?

**H13 — Venue basis (daily panel; coverage still limited).**
*`capture_direct.py` now captures DeepInfra's structured public model API and
Together's public serverless catalog table.*
- Both adapters preserve the exact provider API model ID and raw source.
  DeepInfra is labeled `structured_public_api`; Together is labeled
  `published_docs_table`, so it is a posted list quote—not an executable API
  quote or a fill. Their model IDs join to OpenRouter only by exact equality.
- Groq, Novita, Fireworks, Cerebras, Lambda, Hyperbolic, Parasail, and others
  remain raw-archived until a stable, source-specific normalizer is validated.
  Do not use the raw pages as observations or fuzzy-map names into H13.
- Test: basis = OpenRouter listed − direct listed, per provider×model×day.
  CEX/DEX basis is arb'd to bps; a persistent nonzero inference venue basis
  measures the aggregator's convenience premium / take pass-through.
- Threshold: |basis| median <1% ⇒ pure-broker (quote passthrough) — matches
  how RFQ aggregators display maker quotes; systematically positive ⇒
  venue-rent, unlike RFQ.

**H14 — Order-type mix.** *Data: `model_activity_daily` by variant.*
- Shares of `:floor` (price-priority), `:nitro` (speed-priority), default,
  `:free` over time and across models; test whether floor share rises with
  within-model dispersion (price-sensitive flow activates when quotes diverge,
  like limit-order usage rising with spreads).

**H15 — Inventory-based repricing (mechanism behind H1; needs 4–8 wk panel).**
- Hazard of a `pricing_changes` event on lagged endpoint stress (uptime dips,
  reject spikes, throughput drops), GPU cost shocks, and competitor moves.
- Distinguish cost-driven (retail) vs inventory-driven (Avellaneda–Stoikov MM)
  vs strategic-reaction repricing. RFQ verdict requires inventory/stress terms
  to dominate cost terms.

## Implementation

1. `analysis/h10_lastlook.py` — parse status_heuristics/fortuna out of
   `endpoint_stats_daily.record_json`; reject-rate table + tests (a)–(c).
2. `analysis/h11_quality.py` — quality-extended hedonic + lemons χ² +
   quantization discount curve.
3. `analysis/h12_basis.py` — GPU basis level/vol/term structure.
4. `analysis/h14_ordertypes.py` — variant shares (dispersion interaction needs
   a few weeks of variance; ship shares now).
5. `capture_direct.py` is wired into `scrape.yml` daily.  It writes raw
   evidence, typed `direct_prices_daily` rows, and distinct DeepInfra/Together
   source-run health records.  Expand only with per-provider source-schema
   tests; H13 remains a narrow venue test until several more structured or
   explicitly labeled published-price sources accumulate.
6. Synthetic-data tests per module (planted slopes/frontiers) in tests/.
7. Memo v2: RFQ section with H10–H14 results, updated verdict table +
   pre-registration (H13 basis, H15 mechanism).
8. Theory positioning for the eventual paper: Duffie–Gârleanu–Pedersen search,
   last-look/quote-fade models (Oomen; Cartea–Jaimungal), Grossman–Miller,
   PFOF/preferencing — target claim: "aggregated RFQ with a monopolist router
   and posted (not streamed) quotes."

## Verification
- `uv run pytest` green incl. new synthetic tests.
- `uv run orcap analyze --hypothesis h10` (…h11/h12/h14) produce parquet+JSON
  under analysis/, pushed to HF.
- `capture_direct` dispatched once on CI; `direct_prices_daily` partitions in HF;
  source-health confirms both `direct_deepinfra_api` and
  `direct_together_docs`; spot-check an exact-ID quote from each source.
- Memo redeployed at the same artifact URL; every new number traceable.
