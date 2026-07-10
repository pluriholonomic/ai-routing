# Open-model, routing, and consumption-source search — 2026-07-10

## Decision rule

A source is added only when it is public or user-configured, can be captured
with a stable identifier and raw response, has a clear metric definition, and
does not invite an unsupported conversion into inference tokens or revenue.

## Sources searched and executed

| Question | Source | Capture | Metric boundary |
|---|---|---|---|
| Which public open text-generation weights are being acquired? | [Hugging Face Hub model API](https://huggingface.co/docs/huggingface_hub/en/guides/search) | `open_model_usage_daily`, top 500 public text-generation repositories ranked by Hub downloads | `downloads` is a Hub download counter, not unique users or inference volume. Hub documents its query-file counting method at [Models Download Stats](https://huggingface.co/docs/hub/models-download-stats). |
| Which local-model families are being acquired? | [Ollama Library](https://ollama.com/library) | `open_model_usage_daily`, 236 ranked families and cumulative pulls | Pulls are model acquisition, not completions, active installs, or distinct users. The public page is HTML rather than a documented aggregate API, so the parser has a row-count health gate and raw HTML retention. |
| Is self-hosted serving adoption growing? | [Docker Hub API](https://docs.docker.com/reference/api/hub/latest/) | `oss_runtime_adoption_daily` for Ollama, vLLM, and SGLang images | Image pulls are a deployment proxy, not model usage. Docker notes that pulls include some version checks in its [pull definition](https://docs.docker.com/docker-hub/usage/pulls/). |
| What is actual routed demand? | OpenRouter frontend model activity, rankings, effective-pricing, and endpoint-stat captures | Existing `model_activity_daily`, `rankings_weekly`, `effective_pricing_daily`, and `congestion_intraday` | These are the only captured token/request measures. They cover the OpenRouter marketplace, not all model consumption. |
| What decentralized compute capacity is publicly observable? | [Akash Console API](https://akash.network/docs/api-documentation/rest-api/) | `market_capacity` provider rows from `/v1/providers` | Indexed provider GPU availability/capacity, not proof of completed workloads or GPU-hours consumed. |

## Sources rejected or held behind explicit gates

| Source | Finding | Decision |
|---|---|---|
| CoW Protocol trade endpoint | The public endpoint requires an owner or order UID, so it cannot supply a market-wide execution feed. | Keep `cow` degraded until a bounded official aggregate/subgraph feed is configured. |
| Uniswap depth and swaps | The configured Graph path requires a subgraph id and API key. | Keep credential-gated; do not substitute an undocumented third-party feed. |
| Golem Stats | The documented public API exposes provider and utilization series, but the live API hostname failed DNS resolution from the collector environment. | Keep `golem` degraded and monitor; do not create zero-capacity records. |
| GitHub repository traffic | GitHub traffic endpoints require repository write/admin access and only retain 14 days of clone history. | Do not treat public stars/forks as model consumption. Existing devrel metrics remain adoption proxies only. |
| Ollama local API | The documented API operates on a user's local server. | Do not probe third-party servers or infer user behavior. Only aggregate Library pulls are collected. |

## Execution plan and gates

1. Run `orcap capture-open-usage` daily. The first run produced 500 Hugging
   Face rows, 236 Ollama rows, and 3 runtime-image rows. The `usage` health
   profile validates row minima and freshness before publication.
2. Run `market-capture --with-akash` hourly. The first public run produced
   1,780 Akash capacity rows and 7,812 DefiLlama participant rows.
3. Preserve source identity. Do not merge Hugging Face repository ids, Ollama
   family slugs, and OpenRouter permaslugs without an explicit versioned map.
4. Use cross-source rank correlation and family-level event studies only after
   at least four weekly snapshots; use levels only within a source.
5. Treat new source counters as covariates for H20/H40 and as validation for
   routing-share shifts, never as a replacement for OpenRouter token counts.

## Remaining data work

- Backfill and publish the already captured 2026-07-08/09 price-change and HF
  stats derivations (performed from the verified local mirror in this run).
- Replace broad historical compaction hydration with a resumable,
  table-scoped fold; the old all-table hydration exhausts the Hub API quota.
- Configure a finalized Uniswap source and a market-wide CoW feed before
  claiming a full DeFi liquidity/execution comparison.
- Accumulate at least 6–8 weeks of daily public adoption snapshots before
  estimating cross-source lead/lag relationships.
