# Cross-router data and controlled telemetry

## What is live now

The `hf-router` workflow samples the public Hugging Face Inference Providers
`/v1/models` surface four times per hour, at 15-minute spacing. It does not
send inference traffic or require an account credential.

It writes three tables:

| table | grain | claim boundary |
|---|---|---|
| `hf_router_models_snapshots` | run × HF model | public catalog and provider-count state |
| `hf_router_endpoint_snapshots` | run × model × provider | listed input/output price, context, latency, throughput, and capability metadata; never usage or fills |
| `hf_router_policy_simulation` | run × model × scenario × provider × policy | public cheapest-quote and reported-throughput allocation proxies; never a realized HF route |

The four workload shapes are shared with the OpenRouter route-simulation panel:
short chat, long context, tool chat, and structured chat.  Hugging Face's
`cheapest` surface selects the minimum public request cost. Its `fastest`
surface ranks only endpoints which disclose a positive throughput value, so it
is explicitly a public throughput proxy rather than a view into private router
health.

`config/router_model_map.toml` is the sole matching authority between the two
routers. It uses explicit aliases and a mapping version; unlisted models must
not be matched by fuzzy naming.

## Public analysis

Run H44 after both sources have at least one snapshot:

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h44 --out analysis
```

It writes matched provider quote pairs and aligned policy-share proxies. H44
can answer whether quoted providers are available and priced differently across
routers, or whether price- and throughput-prioritized policies disagree. It
cannot answer either router's global routed share, actual route selection, or
provider profit.

## Owned request telemetry contract

`router_route_attempts` is intentionally a separate, private table for traffic
we control. It supports redacted records from OpenRouter generation metadata,
Portkey, Cloudflare AI Gateway, and LiteLLM. Required fields are an immutable
source event id, observation time, router, source, study id, model, and outcome.
Optional fields include selected provider, attempt index, fallback/retry flag,
tokens, cost, latency, policy, and a quote-snapshot id.

The importer rejects `prompt`, `messages`, `completion`, `response`, and raw
payload fields. Use a salted request reference and scenario label rather than
customer content.

```bash
uv run orcap ingest-route-attempts --input redacted-route-attempts.jsonl
```

## Activation sequence for paid controlled probes

The repository contains no provider credentials and does not submit paid
requests. Activation requires all of the following from the operator:

1. Choose the account telemetry layer: Portkey for retry/fallback tracing, or
   Cloudflare for managed logs and Logpush export. Do not deploy both first.
2. Supply a least-privilege gateway token and private destination for redacted
   logs. Keep raw payload capture disabled.
3. Supply a dedicated OpenRouter study key and a hard daily spend cap.
4. Approve the fixed probe specification: non-sensitive deterministic prompt,
   four workload shapes, no sticky sessions, randomized order, rate limit, and
   automatic failure/cost stop.
5. Start with event-triggered states only: 100–200 requests per material state
   for a large route-shift test; around 400 per state for ±5 percentage-point
   provider-probability calibration.

For OpenRouter calibration, make the request directly to OpenRouter and attach
the resulting generation metadata to the route-attempt record. A gateway wrapped
around an OpenRouter call may only see OpenRouter as its immediate upstream; it
does not by itself reveal OpenRouter's final provider.

## Publication and safety

Public quote tables are pushed to the existing private dataset repository by
the nightly artifact assembly. Owned route telemetry should stay in a separate
private store with restricted access; only de-identified aggregates belong in
the research dataset or dashboard. Never backfill prompt bodies from a gateway
export.
