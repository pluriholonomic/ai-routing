# Owned realized-routing probe activation

## What this unlocks

The public quote panel can show that public quotes alter a documented shadow
allocation.  It cannot reveal the provider actually selected for a request.
For traffic controlled by this project, OpenRouter generation metadata can
provide the selected provider, completion time, latency, throughput, and cost;
the resulting redacted records land in the private `router_route_attempts`
contract.

This is a calibration and stale-quote-fill study on the controlled account. It
is not a measurement of global OpenRouter flow and cannot identify private
order-flow access.

## Fixed design before any request is sent

The study manifest must register:

1. a dedicated low-privilege study key and a hard spend cap;
2. a payload-free workload profile identifier, model list, and fixed output
   cap; the request text is never persisted in this repository or telemetry;
3. randomized probe timing and model order, with no sticky session key;
4. an OpenRouter `auto`/default-policy arm for selected-provider calibration;
5. provider-pinned and ordered-fallback arms only when needed to test
   eligibility or fallback; they are not market-share measurements;
6. stop conditions for spend, errors, rate limits, and provider-level failure;
7. the exact quote-snapshot join rule and a private destination for redacted
   attempt data.

The existing H50 registration and `router_route_attempts` schema enforce
pre-registration and reject payloads.  The repository must not issue a probe
until the operator separately authorizes paid collection.

## Metadata retained per completed attempt

```text
generation_id or salted request reference
observed_at, model_id, policy, requested_provider, selected_provider
outcome, attempt_index, fallback_triggered, retry_reason
input_tokens, output_tokens, cost_usd, latency_ms, quote_snapshot_id
```

Prompts, completions, raw request/response bodies, API keys, and authorization
headers are prohibited by `route_telemetry.py`.

## Analyses unlocked

| Question | Required comparison | Permitted conclusion |
|---|---|---|
| H43 calibration | shadow share vs. selected provider on randomized controlled probes | controlled-account calibration of the public shadow |
| H42 stale quote | an unchanged cheap endpoint after a competitor shock vs. matched endpoints | controlled-account fill/fallback behavior |
| H14 phantom liquidity | quote eligibility vs. actual success/fallback after a probe | controlled-account quote-to-admission reliability |
| H67 pulse candidates | selected share after a pre-registered public cut event | provisional controlled-account allocation capture, subject to pre-trends and controls |

None establishes platform-wide selection, a provider's profit, or literal
front-running.  The latter requires a router-side decision log that records
whether the provider had information before route commitment.

## Safe activation sequence

1. Register the study and assignment schedule with no traffic sent.
2. Store the study key outside the repository and configure a hard platform
   spending limit.
3. Begin with one model and the minimum pre-registered sample; retrieve
   generation metadata only after completion.
4. Redact and ingest records through `orcap ingest-route-attempts`.
5. Audit cost, selected-provider coverage, retry/fallback rate, and payload
   rejection before expanding the study.

Cloudflare AI Gateway, Portkey, or LiteLLM may provide controlled outer-route
logs, but a gateway placed in front of OpenRouter sees OpenRouter as its
immediate upstream.  OpenRouter generation metadata remains the source of
truth for OpenRouter's final provider selection.
