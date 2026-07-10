# orcap repository guide

`orcap` is a capture-and-analysis system for the OpenRouter inference market.
Its primary asset is not the Python package; it is the append-only historical
dataset at `t4run/openrouter-market-history`.  This repository contains the
collectors, normalizers, analysis code, CI schedules, tests, and the rendered
memo template.  It intentionally does not contain the source dataset.

## System map

```text
OpenRouter API / frontend APIs ─┐
Vast + Fabryka + Ornn GPU APIs  ├─> raw JSONL.gz (source of truth)
Direct-provider / HF / devrel   ┘          │
                                             v
                                      curated parquet tables
                                             │
          Wayback + LiteLLM backfill ────────┼─> derived pricing changes
                                             │
                                             v
                                      H1–H40 analysis tables
                                             │
                                             v
                                      private HF dataset + memo Space
```

The local `data/` directory is staging.  The Hugging Face dataset is the
authoritative store during normal analysis; set `ORCAP_ANALYSIS_SOURCE=local`
only for an already-hydrated local mirror or test fixture.

## Capture contracts

| Collector | Primary output | Frequency in CI | Notes |
|---|---|---:|---|
| `capture` | `models_snapshots`, `endpoints_snapshots`, `providers_snapshots`, `congestion_intraday` | 5-minute samples inside an hourly job | Captures all OpenRouter endpoint quotes; hot-40 models also get live 30-minute congestion. |
| `scrape` | activity, app, endpoint-stat, uptime, effective-price, comparison, ranking tables | daily | Depends on undocumented frontend endpoints; preserve raw responses and treat schema or zero-count changes as source incidents. |
| `capture-gpu` | `gpu_offers_snapshots`, `gpu_price_indices`, `ornn_gpu_index_history`, `gpu_published_prices` | hourly | Vast is the active spot-book source; Fabryka is a short-history H100-equivalent index; Ornn supplies public daily GPU compute-index history; Lambda supplies strict, server-rendered per-GPU-hour instance list quotes by GPU family and instance size. Lambda quotes are posted commercial prices, not offer depth, utilization, or fills. |
| `capture-direct` | `direct_prices_daily` | daily | DeepInfra, Cerebras, SambaNova, and Chutes structured public model APIs; Groq and Together exact-ID docs tables; strict Novita and BaseTen public SSR catalogs; and two exact-ID Fireworks serverless model pages. Cerebras retains both its API ID and a first-party canonical Hugging Face key when supplied; SambaNova uses versioned one-to-one maps; Chutes verifies a public root and quantization pair; BaseTen retains its literal publisher/library slug and requires a current versioned router pair. Rows retain source type; published pages/catalogs are posted quotes, not API quotes or fills. Other provider pages remain raw evidence only. |
| `capture-hf` | `hf_model_stats_daily` | daily | Leading demand signals for listed Hugging Face models. |
| `capture-devrel` | `devrel_daily` | daily | NPM, PyPI, GitHub, and HN adoption proxies. |
| `backfill` | Wayback and LiteLLM history | manual | Historical model-level only; it cannot recover historical per-provider endpoint prices. |
| `defi` | `external/*.parquet` | **manual only** | Current comparators are gas, two Uniswap pools, CoW settlement counts, BTC funding/hashprice, and PyPI history. |
| `market-capture` | `market_quotes`, `market_counterfactual_quotes`, `akash_market_open_bids` | hourly workflow | Includes GeckoTerminal indexed state as a reserve/volume control, six-point Uniswap QuoterV2 price-impact curves plus 100/500-bps sparse-ladder capacity lower bounds, exact-input parent-block AMM counterfactuals for observed CoW USDC sells, and block-pinned open GPU bids from the current Akash live-GPU-provider universe. The lower bounds are not full tick-book depth; neither simulation nor an Akash bid is a fill guarantee or best-execution result. |

Every collector must preserve the raw response before producing a normalized
row.  `record_json` in curated tables makes schema evolution recoverable.  Do
not use a derived table as the sole evidence for a new claim when raw evidence
is available.

## Lifecycle and storage

1. `capture.yml` and `gpu.yml` write short-lived GitHub workflow artifacts.
2. `scrape.yml` pushes its daily tables directly to the private HF dataset.
3. `compact.yml` downloads recent buffered artifacts, pushes once, compacts
   endpoint snapshots, and folds SCD-2 `pricing_changes`.
4. `memo.yml` hydrates the HF mirror, overlays fresh artifacts, runs all
   analysis modules, renders the memo, then uploads results and the memo.

The capture workflow deliberately runs 11 five-minute samples within each
hour because GitHub Actions cron is not reliable below hourly cadence.  Use
`run_ts`, not the nominal cron time, when computing panel intervals.

## Local setup

```bash
uv sync
uv run pytest -q
uv run ruff check .
```

Common local commands:

```bash
uv run orcap capture --samples 3 --interval-seconds 300
uv run orcap scrape --limit 10
uv run orcap capture-gpu
uv run orcap analyze --hypothesis h34
uv run orcap memo
# Only ingests an already-redacted local controlled-study export; no API calls.
uv run orcap ingest-capacity-commitments --input redacted-capacity-commitments.jsonl
uv run orcap ingest-capacity-outcomes --input redacted-capacity-outcomes.jsonl
```

Writes to the dataset need an authenticated Hugging Face token (`HF_TOKEN` or
cached HF login).  `orcap defi` additionally needs Application Default
Credentials and a BigQuery billing/quota project.  Proposed Dune and The
Graph collectors should use environment-only `DUNE_API_KEY` and
`GRAPH_API_KEY`; no credential belongs in code, raw payload, generated memo,
or git history.

The hourly market workflow defaults to dRPC's documented public Ethereum RPC
for a **bounded recent-finality** window over the two registered USDC/WETH
pools and GPv2Settlement. Set `ORCAP_ETHEREUM_RPC_URL` to override it with an
operator-selected archive-capable endpoint for stronger uptime and historical
coverage. The public fallback is never an archive/backfill source; Graph and
GeckoTerminal remain indexed-state controls. The collector records public and
configured RPC provenance separately and redacts configured URLs that may
contain API keys.

## Analysis conventions

- `src/orcap/analysis/data.py` is the shared access boundary.  Add an access
  helper there before scattering hard-coded parquet paths through analyses.
- Each hypothesis module exports `run(out_dir)`, writes named parquet results
  and a JSON summary, and should be independently executable with
  `orcap analyze --hypothesis <name>`.
- H13 writes both match-level `h13_basis` and daily provider/source coverage in
  `h13_provider_day`. Its summary is explicitly `power_gated` until the
  multi-provider and repeated-observation threshold is met; do not promote a
  zero basis from a single catalog into a market-wide result.
- The rendered memo reports `core`, `direct`, and `comparison` source-health
  profiles. A missing direct-provider run must appear as degraded rather than
  allowing H13 to look current by default.
- Tests are synthetic recovery tests: plant a known signal, then assert the
  estimator recovers it.  Add source-schema and failure-mode tests alongside
  them for every new collector.
- Keep claims separated into measured, provisional/power-gated, and proposed.
  The existing live quote panel is young; do not turn a power-gated analysis
  into a structural conclusion.
- H41's finalized Ethereum windows are a panel only after their successful
  query ranges overlap without uncovered blocks. The default 1,024-block
  window creates the needed hourly overlap, but dynamic work remains gated
  until seven observed days. QuoterV2 prices must remain split by AMM pool and
  USDC input bucket; exact-pair CoW prices remain split by trade direction.

## Current claim boundary

The repository can already support a study of OpenRouter's provider quote
microstructure, a single live open-GPU marketplace, and a limited set of
stylized DeFi comparators.  It cannot yet support a full DeFi-versus-open
compute market comparison because it lacks matched DeFi microstructure,
multi-venue compute coverage, a common instrument definition, and a
production DeFi monitoring workflow.  The completion design is in
[`defi-open-compute-completion-plan.md`](defi-open-compute-completion-plan.md).
