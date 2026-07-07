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

## Cadence

| workflow | schedule | what |
|---|---|---|
| `capture` | every 15 min, 3 samples at 5-min spacing | `/api/v1` models + providers + per-model endpoints (per-provider pricing, uptime/latency/throughput rolling windows). 5 min is the finest granularity OpenRouter exposes (`uptime_last_5m`), so sampling faster buys nothing. |
| `scrape` | daily 03:17 UTC | undocumented `/api/frontend/v1` chart APIs: model activity (31-day trailing), app leaderboards, endpoint stats, daily uptime, effective (transacted) pricing, perf comparisons, weekly rankings |
| `compact` | nightly 01:43 UTC | consolidates the day's ~300 small parquet files to one per table/day; derives SCD-2 `pricing_changes` + `pricing_current` |

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
