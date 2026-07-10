# orcap — OpenRouter market-history capture

Continuous capture of OpenRouter's inference marketplace: **per-provider pricing for
every model** (what the `#providers` tab shows), plus models, providers, per-model
usage/activity, app/harness leaderboards (Cline, Hermes Agent, Kilo Code, …), uptime,
and performance comparisons.

**Why this exists:** OpenRouter's APIs are point-in-time only — per-provider pricing
history exists nowhere publicly. This repo snapshots it forward from 2026-07-07 and
backfills what little model-level history the Wayback Machine has (back to 2023-07).

- **Code**: this (public) GitHub repo. Contains no data.
- **Data**: private HF dataset repo [`t4run/openrouter-market-history`](https://huggingface.co/datasets/t4run/openrouter-market-history).

## Documentation

- [`docs/repo-guide.md`](docs/repo-guide.md) — architecture, data contracts, local setup, workflows, and claim boundaries.
- [`docs/repo-skills.md`](docs/repo-skills.md) — concise operating skills for capture, source extensions, comparative analysis, and monitoring.
- [`docs/defi-open-compute-completion-plan.md`](docs/defi-open-compute-completion-plan.md) — the source, schema, method, monitoring, and prioritized fix plan for a complete DeFi-versus-open-compute comparison.
- [`docs/routing-mev-research-plan.md`](docs/routing-mev-research-plan.md) — falsifiable routing-volume-capture hypotheses, event-study designs, data gates, and the boundary between quote competition and MEV-like claims.
- [`docs/routing-simulation-monitor.md`](docs/routing-simulation-monitor.md) — zero-spend 15-minute public-quote route-surface assay, its 24-hour decision rule, and the boundary from realized routing.
- [`docs/cross-router-data.md`](docs/cross-router-data.md) — Hugging Face public-router comparator, cross-router policy analysis, and the redacted contract for controlled route telemetry.
- [`docs/router-shadow-execution.md`](docs/router-shadow-execution.md) — one shadow-execution interface for OpenRouter, Hugging Face, Cloudflare AI Gateway, Portkey, and LiteLLM.

## Cadence

| workflow | schedule | what |
|---|---|---|
| `capture` | every 15 min, 3 samples at 5-min spacing | `/api/v1` models + providers + per-model endpoints (per-provider pricing, uptime/latency/throughput rolling windows). 5 min is the finest granularity OpenRouter exposes (`uptime_last_5m`), so sampling faster buys nothing. |
| `scrape` | daily 03:17 UTC | undocumented `/api/frontend/v1` chart APIs: model activity (31-day trailing), app leaderboards, endpoint stats, daily uptime, effective (transacted) pricing, perf comparisons, weekly rankings |
| `compact` | nightly 01:43 UTC | consolidates pricing-critical endpoint snapshots and derives SCD-2 `pricing_changes` + `pricing_current` |
| `route-simulation-monitor` | hourly | evaluates the latest 26 hours of 15-minute public-quote routing simulations; publishes only after its coverage gate |
| `hf-router` | hourly, 4 samples at 15-min spacing | public Hugging Face Inference Providers model/provider price and performance surface; no inference requests |

## Data layout (HF dataset repo)

```
raw/{api_v1,frontend_v1,wayback}/dt=YYYY-MM-DD/{run_ts}.jsonl.gz   # verbatim responses (source of truth)
curated/{table}/dt=YYYY-MM-DD/*.parquet                            # normalized, hive-partitioned
derived/pricing_current.parquet                                    # latest price per endpoint
derived/pricing_changes/dt=YYYY-MM-DD/part-0.parquet               # SCD-2 change events
backfill/models_snapshots_wayback/dt=YYYY-MM-DD/*.parquet          # 2023-07 → present, model-level
```

Curated tables (all carry `run_ts`, `dt`, and a `record_json` column with the full
source record, so OpenRouter schema drift never loses data):

| table | grain | notes |
|---|---|---|
| `endpoints_snapshots` | run × model × provider-endpoint | **the core table**: per-provider pricing (`price_*` as float64 + original string), quantization, context, uptime 5m/30m/1d, latency/throughput 30m. `endpoint_fingerprint` disambiguates same-tag SKUs. |
| `models_snapshots` | run × model | aggregate pricing + metadata |
| `providers_snapshots` | run × provider | provider directory |
| `model_activity_daily` | day × model × variant | daily prompt/completion/reasoning/cached tokens, requests, tool calls |
| `apps_leaderboards` | day × (global-section \| model) × app | app/harness rankings by tokens (Hermes Agent, Cline, …) |
| `endpoint_stats_daily` | day × endpoint | frontend endpoint detail incl. UUID (joins to comparisons/uptime) |
| `uptime_daily` | day × endpoint UUID | 3-day trailing daily uptime |
| `effective_pricing_daily` | day × model × provider | **transacted** effective $/Mtok + cache-hit rates (vs. listed prices) |
| `perf_comparisons_daily` | day × endpoint × metric | throughput, latency (TTFT + e2e), tool-call/structured-output error rates, cache-hit-rate |
| `rankings_weekly` | week × model | global weekly token totals, history back to 2025-07 |
| `pricing_changes` | change event | SCD-2: field, old/new value, when; `__endpoint_added__`/`__endpoint_removed__` markers |
| `routing_simulation` | run × fixed model × workload shape × provider | **simulated** first-route share from public endpoint quotes and documented inverse-square price weighting; never actual fills |
| `routing_simulation_runs` | run | simulation coverage plus free/zero-cost/single-provider exclusion ledger |
| `hf_router_endpoint_snapshots` | run × HF model × provider | public cross-router price, context, performance, and capability metadata; not routed volume |
| `hf_router_policy_simulation` | run × HF model × workload shape × provider × policy | simulated cheapest and reported-fastest selection surfaces; never actual route fills |
| `router_policy_snapshots` | owned config × model × provider | redacted Cloudflare AI Gateway, Portkey, or LiteLLM routing configuration; not a traffic log |
| `router_route_attempts` | owned request attempt | redacted controlled-study provider outcomes/retries; private telemetry, not public market flow |
| `open_model_usage_daily` | day × source × open model | public HF rolling downloads and Ollama cumulative pulls; adoption proxies, never inference tokens |
| `oss_runtime_adoption_daily` | day × serving runtime image | public Docker Hub cumulative pulls for Ollama/vLLM/SGLang; deployment proxy, not model consumption |

## Querying

```python
import duckdb
con = duckdb.connect()
con.sql("CREATE SECRET hf (TYPE huggingface, TOKEN '<your HF token>')")
con.sql("""
  SELECT dt, provider_name, any_value(price_completion) * 1e6 AS out_per_mtok
  FROM read_parquet('hf://datasets/t4run/openrouter-market-history/curated/endpoints_snapshots/*/*.parquet')
  WHERE model_id = 'z-ai/glm-4.6'
  GROUP BY dt, provider_name ORDER BY dt
""")
```

Price-change event log:

```sql
SELECT * FROM read_parquet('hf://datasets/.../derived/pricing_changes/*/*.parquet')
WHERE field NOT LIKE '\_\_%' ESCAPE '\' ORDER BY changed_at_run_ts;
```

## Running locally

```bash
uv sync
uv run orcap capture                  # one snapshot -> data/
uv run orcap capture --samples 3      # 15-min-slot behavior
uv run orcap scrape --limit 10        # frontend charts for 10 model×variant combos
uv run orcap capture-open-usage       # broad open-model download/pull and runtime-adoption proxies
uv run orcap capture-gpu              # Vast offer book + public Ornn GPU index history
uv run orcap market-capture --with-uniswap --with-akash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h31  # GPU rent/utilization screen
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h47  # exact-spec GPU quote basis
uv run orcap analyze --hypothesis h42 # routing-volume-capture event audit (MEV-like hypotheses)
ORCAP_ANALYSIS_SOURCE=local uv run orcap route-sim-report --out analysis  # 24h public-quote route-surface test
uv run orcap capture-hf-router --samples 4 --interval-seconds 900  # public HF router surface, no orders
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h44  # public cross-router quote/policy screen
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h45  # cross-router shadow routing + outage stress
uv run orcap import-router-policy --input redacted-router-policy.json
uv run orcap ingest-route-attempts --input redacted-gateway-events.jsonl --format portkey --study-id routing-v1
uv run orcap quality --profile core
uv run orcap push                     # -> HF dataset repo (uses cached HF login)
uv run orcap compact                  # compacts yesterday in the HF repo
uv run orcap backfill                 # wayback backfill of model-level pricing
uv run orcap discover                 # Playwright sniff to re-find moved endpoints
```

`HF_TOKEN` (GitHub Actions secret) needs write access to the dataset repo.

## Caveats

- Listed prices are provider list prices per token; OpenRouter adds platform fees
  (~5.5% credit fee) on top — `effective_pricing_daily` reflects what was actually
  paid per token including cache effects.
- Wayback backfill preserves the old `-1` sentinel prices (auto-router); filter
  negatives for analysis.
- The `/api/frontend/v1/*` endpoints are undocumented and move without notice; when
  the daily scrape starts returning zeros, run `orcap discover` and update paths in
  `scrape_charts.py`.
- GitHub cron can lag minutes under load; `run_ts` in the data is authoritative,
  gaps are by design tolerable.
