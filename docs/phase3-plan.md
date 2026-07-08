# Phase 3 — Microstructure of the inference market

Three pillars: (A) predict future pricing from demand signals, (B) measure
quoter adaptiveness, (C) adverse selection / flow toxicity / competition's
effect on prices. Everything below is pre-registered: estimators and
thresholds stated before the panels mature. Hypothesis labels H20-H27.

---

## Pillar A — Predicting prices from demand signals (H20)

**Target upgrade over H18 (layer 2 + demand):** discrete-time hazard of
repricing at hourly buckets per endpoint, plus direction/magnitude conditional
models, with *demand-state* covariates rather than only lifecycle/history.

**Demand signals — captured already:**
- `congestion_intraday`: recent_peak_rpm / capacity_ceiling_rpm (utilization),
  p50–p99 latency & throughput, request_count (5-min, top-40 models)
- `model_activity_daily`: tokens, requests, reasoning-token share,
  cache-token share, tool-call errors (daily, ALL models)
- `apps_leaderboards`: per-model order-flow composition (which harnesses)
- `rankings_weekly`: model-level demand trends; `endpoint_stats_daily`:
  reject rates (excess demand indicator)

**Demand signals — NEW capture (wired with this plan):**
- `hf_model_stats_daily`: HF Hub downloads / likes / trendingScore for every
  model with an hf_slug — a *leading* indicator (hype precedes routed volume,
  esp. pre-listing and at launch, where 73% of repricing happens)
- app momentum: day-over-day app token growth from apps_leaderboards (no new
  capture; derived) — order-flow shocks orthogonal to model quality

**Models:** discrete-time logit hazard with provider-type interactions (H19
types) + HistGBM ceiling; features strictly lagged. Evaluation: out-of-time
AUC/PR-AUC (weekly folds), calibration, and an *economic backtest* — a buyer
policy that delays purchases/switches on predicted cuts; report realized
savings per Mtok vs naive. Thresholds: hazard AUC ≥ 0.75 out-of-time at
endpoint level; demand covariates must add ≥ 0.05 AUC over H18's
lifecycle/history features to declare "prices are demand-predictable."
Feasible: first fit at ~4 weeks of panel; full at 12 weeks.

## Pillar B — Quoter adaptiveness (H21-H22)

**H21 — Reaction functions & latency.** From event bursts + pricing_changes:
per provider (and per H19 type), the distribution of reaction lag to (i)
competitor moves on the same model, (ii) demand/utilization shocks, (iii) GPU
index moves. Deliverable: an adaptiveness league table — median reaction lag,
share of shocks reacted to within 24h/7d. Comparators: RFQ quote-update
latencies; Uniswap LP position-update frequencies (JIT vs passive LPs — same
mover/stayer structure, BigQuery-able).

**H22 — Ss bands (state- vs time-dependent pricing).** For each managed-price
provider: estimate the inaction band — reprice when |log(price/attractor)| >
s, where the attractor is peer median (competition) or cost index (GPU).
Band width = inverse adaptiveness; also identifies WHAT providers track
(peers vs costs — H17 says peers). Quantity margin too: stayers may adapt via
capacity_ceiling/limit_rpm instead of price; measure both margins so
"unadaptive" isn't just "adapts in quantity."
Feasible: needs ~8-12 weeks of events (≥200 events at current ~11/day).

## Pillar C — Adverse selection, toxicity, competition (H23-H27)

**H23 — Flow-toxicity index.** Per model-day (extendable to app), a
flow-quality factor from observables: cache-hit rate, tokens/request
(long-context share), reasoning-token share, tool-call error rate, free-tier
share. Toxic flow = high realized serving cost per billed token (long-context
low-cache agentic retry loops; subsidized free flow). Validation: the index
must predict provider defenses — rejects/deranks/capacity cuts — on the same
model-days (that's what a toxicity measure IS: flow the quoter rations).

**H24 — Toxicity targeting (last look, reframed).** H10 found rejection is
uncorrelated with *price*; H24 tests whether it's correlated with *flow
quality*: within provider, reject rate rising in the toxicity index ⇒
rejection is adverse-selection defense (exactly FX last-look's stated
purpose). Free-variant rationing is the clean subcase (pure loss-leader flow).

**H25 — Winner's curse of undercutting (LVR analog).** After a price cut, the
*marginal* flow that arrives is selected on price-sensitivity: measure the
post-cut shift in flow composition (cache rate ↓, tokens/request ↑, free-share
↑?) around events, diff-in-diff vs non-moving providers on the same model.
If undercutting attracts systematically worse flow, there is an adverse-
selection cost to aggressive quoting — the inference-market LVR, and a
candidate explanation for why dispersion persists (H2) and quotes are sticky
(H1): narrow spreads are subsidized to toxic flow.

**H26 — Entry pass-through (causal version of H3).** Staggered event study
(Callaway–Sant'Anna) on `__endpoint_added__` events: incumbent listed and
effective prices around entry, by entrant count and entrant type (H19).
Deliverable: "the Nth entrant cuts incumbent prices by X% within Y weeks."
Exit symmetric. The litellm archive + wayback extend this historically at
model level; our panel does it at endpoint level going forward.

**H27 — Competition's value to buyers.** Quantify "how much does competition
improve pricing": (i) matched-model gap between N=1 and N≥4 models over time
(panel Bresnahan-Reiss with model FE); (ii) routing surplus — realized paid
price vs volume-weighted counterfactual of pinned-to-top-provider flow, using
H4's elasticity; (iii) entry pass-through (H26) aggregated to a consumer-
savings estimate in $/Mtok and % of spend.

## New capture (implemented with this plan)

1. `capture_hf_stats` — daily HF Hub stats (downloads, likes, trendingScore)
   for all listed models with hf_slug (~1 call/model, joins on hf_slug),
   wired into scrape.yml. Table: `hf_model_stats_daily`.
2. App momentum + toxicity index are derived tables in analysis (no capture).
3. Optional (needs key): Prime Intellect GPU offers as second GPU venue.

## Timeline & power

- Now: H23 index construction + validation on existing daily panels; H26
  historical (wayback/litellm); H20 feature pipeline dry-run.
- ~4 weeks: H20 first fit; H21 reaction-lag table (first ~300 events);
  H24 first pass.
- ~8-12 weeks: H22 Ss bands; H25 event diff-in-diff (needs enough cuts with
  post-windows); H20 full; H26 prospective arm.
- Everything runs inside the nightly reanalysis; results appear in the memo
  as panels cross their power thresholds.

## Falsification discipline

Each pillar has a kill condition: (A) demand features add <0.05 AUC ⇒ prices
are not demand-predictable at this horizon — report it; (B) reaction lags
indistinguishable from random repricing ⇒ "adaptiveness" is illusory;
(C) toxicity index fails to predict provider defenses ⇒ our observables
don't capture adverse selection and we say so rather than torturing proxies.
