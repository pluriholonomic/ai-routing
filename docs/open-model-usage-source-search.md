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
| What decentralized compute capacity, posted GPU quotes, and contract lifecycle are publicly observable? | [Akash Console Network Data API](https://akash.network/docs/api-documentation/rest-api/) plus official [RPC](https://akash.network/docs/node-operators/architecture/api-layer/) block headers | `market_capacity` contains only live, version-valid provider-level GPU totals; `market_quotes` contains public model-level USD/hour aggregates; `market_executions` contains timestamped lease lifecycle contracts | GPU-model mix is not allocated to provider capacity counts. A lease close is not a successful workload, GPU-hours consumed, or USD execution price. |
| Are decentralized Gateway routing adjustments publicly observable? | [Livepeer Gateway Introspection](https://docs.livepeer.org/v1/orchestrators/guides/gateway-introspection) | `livepeer_gateway_metrics`: aggregate regional swap/reuse counters over rolling five-minute windows | External routing control only. The collector requests aggregate LogQL counts and excludes stream/session/client/orchestrator IDs; it does not identify LLM routing, prices, capacity, or delivery. |
| Is any decentralized inference consumption counter publicly available? | Chutes public chute-detail API | H53 first-differences the public per-chute cumulative invocation counter across adjacent hourly snapshots and keeps active configured GPUs as a separate deployment-state denominator | This is a source-defined public counter delta, not successful completions, tokens, unique users, revenue, market-wide demand, GPU utilization, available capacity, or a causal estimate. |

## Sources rejected or held behind explicit gates

| Source | Finding | Decision |
|---|---|---|
| CoW Protocol trade endpoint | The public trade endpoint requires an owner or order UID, so it cannot supply a market-wide execution feed. The separate public `solver_competition/latest` endpoint is captured as a bounded live snapshot, including candidate-solver metadata and the current auction's opaque candidate-order count. | H49 may report sampled auction-state counts only; keep the market-wide CoW execution/fill and order-flow gates closed until a bounded official aggregate/subgraph feed is configured. |
| Uniswap historical tick/position depth | A complete historical panel still needs accumulated live H56 snapshots or an archive source/pinned subgraph. | The hourly monitor now captures full current initialized-tick state, finalized swaps, QuoterV2 fixed-notional simulations, sparse impact lower bounds, and H57 virtual traversal. Keep market-wide and realized-depth gates closed: H56/H57 are registered-pool state, not historic execution or a firm fill. |
| Golem Stats | The documented public API exposes provider and utilization series, but the live API hostname failed DNS resolution from the collector environment. | Keep `golem` degraded and monitor; do not create zero-capacity records. |
| io.net Explorer API | The official Explorer API requires a JWT obtained from an authenticated browser session. | Do not extract a browser token or use account-derived telemetry as a public market data feed. |
| Runpod Serverless pricing | The indexed documentation showed a detailed public GPU rate table, but the live documentation HTML no longer contains it and the live marketing page exposes only broad ranges. | Do not scrape unstable prose or use account-keyed availability/billing APIs; retry only if a stable literal table or unauthenticated feed returns. |
| GitHub repository traffic | GitHub traffic endpoints require repository write/admin access and only retain 14 days of clone history. | Do not treat public stars/forks as model consumption. Existing devrel metrics remain adoption proxies only. |
| Ollama local API | The documented API operates on a user's local server. | Do not probe third-party servers or infer user behavior. Only aggregate Library pulls are collected. |

## Execution plan and gates

1. Run `orcap capture-open-usage` daily. The first run produced 500 Hugging
   Face rows, 236 Ollama rows, and 3 runtime-image rows. The `usage` health
   profile validates row minima and freshness before publication.
2. Run `market-capture --with-akash` hourly. On the 2026-07-10 live probe the
   public Akash registry had 1,780 providers, of which 62 were online and 34
   reported live, version-valid GPU capacity: 258 GPUs total, 133 available,
   and 115 active. The same probe captured 50 newest lease contracts and
   matched every one to an official RPC block timestamp. These are source
   observations, not a historical estimate.
3. Preserve source identity. Do not merge Hugging Face repository ids, Ollama
   family slugs, and OpenRouter permaslugs without an explicit versioned map.
4. Use cross-source rank correlation and family-level event studies only after
   at least four weekly snapshots; use levels only within a source.
5. Treat new source counters as covariates for H20/H40 and as validation for
   routing-share shifts, never as a replacement for OpenRouter token counts.
6. H53 requires 250 adjacent counter deltas across seven days and five chutes
   before reporting even a source-bounded descriptive time series. Counter
   decreases are explicit reset diagnostics and snapshot gaps longer than three
   hours are discarded rather than bridged.

## Remaining data work

- Backfill and publish the already captured 2026-07-08/09 price-change and HF
  stats derivations (performed from the verified local mirror in this run).
- Replace broad historical compaction hydration with a resumable,
  table-scoped fold; the old all-table hydration exhausts the Hub API quota.
- Configure a finalized Uniswap source and a market-wide CoW execution feed
  before claiming a full DeFi liquidity/execution comparison. The live CoW
  solver-competition snapshots are not substitutes for either one.
- H31 now records the Vast on-demand rented-share/rent association with a
  seven-day, three-GPU-class power gate. It remains descriptive until an
  exogenous supply or demand instrument is added.
- H47 compares only versioned, exact consumer-GPU specifications between
  Akash's aggregate USD/hour quotes and Vast on-demand offers. It requires
  seven days, two cohorts, and 50 synchronized quote pairs; H100-class
  matches remain excluded pending a verifiable interface-equivalence map.
- Accumulate at least 6–8 weeks of daily public adoption snapshots before
  estimating cross-source lead/lag relationships.
