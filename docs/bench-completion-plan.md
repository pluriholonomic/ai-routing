# Bench completion plan: data collection + analysis for CBH-15..19

Registered 2026-07-14. Covers the five remaining bench experiments. Analysis
specs are pre-registered here BEFORE the data arrives; event-dependent tests
state their triggers so the analyses are mechanical when events fire.
Numbering continues the cbh namespace (collision-free with the h-series).

| # | Bench item | Module | Blocking need |
|---|---|---|---|
| 9 | JIT-capacity share | CBH-15 | none — labels exist (H19) |
| 6 | Thickness backfire | CBH-16 | cross-section now; event version waits for a provider-count jump |
| 2 | Waterbed fee incidence | CBH-17 | fee-schedule watcher (build now), then a fee event |
| 4 | Peer supply when capacity binds | CBH-18 | lab-status collector + incident backfill (build now) |
| 7 | Fee salience / shrouding | CBH-19 | pinned-provider probe variants (build now), ~2wk accumulation |

## 1. New data collection

### 1a. `watchers.yml` workflow (daily, cron "47 6 * * *", artifact-buffered)

One new workflow so no parallel-session file is touched; added to
`assemble_artifacts.sh`. Two collectors:

**`capture_fees.py` → curated/fee_pages/**
- URL registry (config/fee_pages.toml): OpenRouter docs/FAQ + terms (credit
  fee 5.5%, BYOK fee), HF Inference Providers pricing docs, Cloudflare AI
  Gateway pricing, Vercel AI Gateway pricing, and the top harness pricing
  pages (Cursor, Windsurf, Cline docs, Janitor premium, OpenWebUI hosted).
  Each entry: url, page_kind ∈ {router_fee, harness_price, capacity_product}.
- Row per page per day: {dt, url, page_kind, http_status, content_sha256,
  parsed_json} where parsed_json extracts fee numbers via per-page regex
  (e.g. `(\d+(\.\d+)?)%` near "fee"); raw HTML gz to raw/ for reparsing.
- Change detection = content_sha delta → a `fee_page_changes` derived row;
  this is the CBH-17 event trigger and the O1/R1 tracker feed.
- One-time Wayback CDX backfill of the same URLs (reuse backfill.py Fetcher):
  pins any 2023-2026 fee changes we already missed.

**`capture_labstatus.py` → curated/lab_incidents/ + lab_status_snapshots/**
- statuspage.io JSON APIs (config/lab_status.toml): status.openai.com,
  status.anthropic.com, and statuspage-based provider pages (together, groq,
  fireworks, deepinfra where present; registry tolerates 404 → source-run
  'skipped').
- Per run: /api/v2/summary.json (current indicator per component) and
  /api/v2/incidents.json (recent incident objects: id, impact,
  created/updated/resolved, component names, shortlink). Incidents are
  upserted by id (immutable rows keyed run_ts; dedup at analysis time).
- Backfill: incidents.json typically returns the trailing ~50 incidents
  (weeks-to-months of history) — captured on first run; note actual depth in
  the source-run detail.
- "Bind window" definition (pre-registered for CBH-18): an incident with
  impact ∈ {major, critical} OR any incident whose affected components match
  /api|inference|chat/i, from created_at to resolved_at (+2h cool-down);
  release weeks: 7 days from a frontier-family model's first models_snapshots
  appearance (families: gpt, claude, gemini, grok).

### 1b. Probe extension (edit `capture_probes.py`, my module)

After each default-routed probe, for the top ORCAP_PROBE_PINNED_MODELS
(default 4) models, send up to 3 pinned probes with
`provider: {order: [name], allow_fallbacks: false}` to: (i) the cheapest
quoted provider, (ii) the 2nd cheapest, (iii) one uniformly random other
quoting provider. Record requested_provider, HTTP status, and generation
metadata as usual. Budget: +12 one-token probes/hour ≈ +$1-3/month, capped by
env. This single extension feeds THREE analyses: CBH-19a (same fixed prompt →
per-provider native token counts = tokenizer inflation), the firmness/
last-look test (reject/timeout vs quote staleness & aggressiveness on pinned
requests), and the router-neutrality audit (default choices vs pinned
availability).

## 2. Analyses (specs pre-registered)

### CBH-15 — JIT-capacity share (#9) — runnable immediately
- Label serverless/on-spike providers: H19 text keyword flag (kw_serverless)
  ∪ behavioral criterion (capacity ceiling present <50% of ticks while listed).
- Outcomes: (a) steady-state token share of JIT-class providers (benchmark:
  Uniswap JIT ≈0.3% of volume vs 40% folklore); (b) spike differential —
  JIT-class share during top-decile model-demand ticks vs median ticks.
- Read: large spike differential + small steady share = burst-absorption
  niche (Lambda-style premium role); flat = labels don't capture a real
  capacity strategy.

### CBH-16 — Thickness backfire (#6) — cross-section now, event version gated
- Now: model-level delivered quality (request-weighted p90 latency,
  rate-limit share, min and share-weighted price) vs provider count N,
  cross-section with demand controls.
- Event version (trigger: any model whose quoting-provider count rises ≥5
  within 14 days while in the top-50 by tokens): event study of delivered
  quality pre/post entry wave vs synthetic control (3 nearest models by
  pre-period demand). Li-Netessine predicts degradation past some N in
  human-search markets; algorithmic-routing null predicts monotone
  improvement (or flat).
- Gate: ≥3 qualifying entry waves.

### CBH-17 — Waterbed fee incidence (#2) — instrument now, wait
- Trigger: any fee_page_changes row on a router_fee page (or an announced
  fee change caught by the watcher's sha delta).
- Spec: interrupted time series on weekly platform tokens, split by exposure:
  BYOK-exposed vs credit-fee-exposed flow (fee kind determines which side of
  the market the change hits); secondary outcomes: provider quote levels
  (pass-through into posted prices within 30d), rival-router relative growth,
  new-provider listing rate.
- Two-sided-platform prediction: volume responds to the fee SPLIT (waterbed:
  a cut on one side partially recouped on the other); reseller null: only the
  total matters, no cross-side response.
- Gate: first fee event; power note: one event yields a case study, not an
  estimate — report as such.

### CBH-18 — Peer supply when capacity binds (#4) — data now, analysis in ~2wk
- Join bind windows (1a) to the demand-share panel: outcome = daily token
  share and relative effective price of open-weights/neocloud providers vs
  first-party-lab models, inside vs outside bind windows, diff-in-diff with
  model-family fixed effects.
- Farronato-Fradkin prediction: peer supply's share and premium spike
  precisely when incumbent capacity binds; null: substitution is driven by
  price/capability only, insensitive to incident windows.
- Gate: ≥5 bind windows overlapping our demand panel (incident backfill may
  satisfy this immediately for the trailing weeks; otherwise accumulates).

### CBH-19 — Fee salience / shrouding (#7) — probes accumulate ~2wk
- (a) Tokenizer-inflation panel: for the fixed probe prompt, inflation factor
  per provider×model = native_tokens_prompt / min across providers of the
  same model. Outcomes: inflation dispersion; Ellison-Ellison prediction —
  inflation rises as posted-price rank falls (cheap quotes hide cost in the
  meter). Gate: ≥5 providers × ≥8 models with ≥20 probes each.
- (b) Salience elasticity: H4-style share regressions with the price change
  decomposed into salient (completion/prompt list price) vs shrouded
  components (cache-read/write, request fees) using pricing_changes field
  granularity. Prediction: share responds to salient component changes at a
  multiple of equally-sized shrouded changes. Runnable on existing data once
  enough cache-price change events accrue (gate: ≥30 shrouded-component
  events; currently accumulating).

## 3. Sequencing

- **Day 0 (build):** watchers.yml + capture_fees + capture_labstatus (+ toml
  registries, tests), probe extension, assemble-list update; run CBH-15 and
  CBH-16 cross-section; Wayback fee-page backfill.
- **Day 1-3 (verify):** watcher artifacts land; incident backfill depth
  checked; pinned probes visible in router_route_attempts.
- **Week 2:** first CBH-19a run; CBH-18 first run if backfill covers ≥5 bind
  windows.
- **Trigger-based:** CBH-16 event version (next entry wave), CBH-17 (first
  fee event) — both mechanical once triggered.
- **Scorecard:** CBH-15/16/18/19 rows added on first run; CBH-17 row added as
  'instrumented, awaiting event'.

## 4. Risks / boundaries

- Fee-page parsing is brittle → raw HTML always archived; sha-delta (not
  parse success) is the event trigger.
- statuspage APIs differ in incident-history depth; the plan records actual
  depth rather than assuming it.
- Pinned probes measure OUR requests' admission, not market flow; firmness
  conclusions are per-request evidence about quote revocability, not fill
  rates for customers at scale.
- Tokenizer inflation on a single fixed prompt may not represent workload
  mix; CBH-19a reports prompt-specific inflation and gates any general claim
  on a second prompt shape being added.
