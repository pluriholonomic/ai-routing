# Router shadow execution

This repository uses one policy engine for five routing surfaces. It is a
zero-spend counterfactual tool until an operator separately enables a controlled
telemetry study. It is not a universal route-decision tape.

| router | input now | route policy represented | realized-route requirement |
|---|---|---|---|
| OpenRouter | public endpoint snapshots | documented inverse-square public quote allocation | study key and generation metadata |
| Hugging Face Inference Providers | public `/v1/models` snapshots | public cheapest quote and reported-fastest throughput | account-controlled response telemetry |
| Cloudflare AI Gateway | owner-imported config | configured ordered failover or weights | Logpush/analytics export from an owned account |
| Portkey | owner-imported config | configured ordered failover or weights | redacted account log export |
| LiteLLM | owner-imported proxy config | configured ordered failover or weights | redacted proxy callbacks/logs |

The versioned registry is [`config/router_registry.toml`](../config/router_registry.toml).
It deliberately separates public market policy, account configuration, and
realized controlled-study attempts.

## Run the public and configured-policy screen

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h45 --out analysis
```

H45 produces:

| output | meaning |
|---|---|
| `h45_shadow_candidates` | normalized eligible providers and source snapshot id |
| `h45_shadow_base_routes` | base first-route allocation under its disclosed policy |
| `h45_shadow_route_states` | base, each provider-down state, top-two-down, and public-low-uptime state when available |
| `h45_shadow_flip_conditions` | quote cut needed for a provider to tie the lowest public quote |
| `h45_shadow_summary` | winner share, entropy, and winner robustness across stress states |

For inverse-square policies, a price cut changes a provider's simulated share
continuously. For cheapest, fastest, and ordered failover policies, it can
instead create a discrete winner change. A configured weighted policy has no
price-flip result unless the owner also imports corresponding quoted costs.

## Import a configured router policy

Cloudflare, Portkey, and LiteLLM do not have a common public default routing
policy. Export a redacted configuration to the portable schema below, then
import it:

```json
{
  "router": "cloudflare_ai_gateway",
  "config_id": "research-router-v1",
  "observed_at": "2026-07-10T00:00:00Z",
  "policies": [
    {
      "model_id": "open-model-route",
      "policy_type": "ordered_failover",
      "allow_fallbacks": true,
      "config_version": "2026-07-10",
      "providers": [
        {"name": "provider-a", "order": 1},
        {"name": "provider-b", "order": 2}
      ]
    }
  ]
}
```

```bash
uv run orcap import-router-policy --input redacted-router-policy.json
```

Allowed policies are `ordered_failover`, `weighted`,
`inverse_square_price`, `lowest_cost`, and `highest_throughput`. Provider
`weight` is meaningful for `weighted`; `order` is meaningful for ordered
failover. The importer rejects API keys, authorization headers, tokens,
prompts, messages, completions, and raw request/response fields recursively.
It writes `router_policy_snapshots`; it does not modify a gateway.

## Import redacted realized attempts

Use canonical JSONL if the source is already mapped to the
`router_route_attempts` contract. Otherwise use the narrow source adapter:

```bash
uv run orcap ingest-route-attempts \
  --input redacted-cloudflare-events.jsonl \
  --format cloudflare-ai-gateway --study-id routing-calibration-v1
```

Supported formats are `openrouter-generation`,
`huggingface-inference-providers`, `cloudflare-ai-gateway`, `portkey`, and
`litellm`. Each needs a redacted event id, time, model, and enough information
to determine an outcome; optional values are provider, retry index, cost,
tokens, latency, and policy. If an export contains raw prompt/completion or
credential fields, the adapter fails instead of persisting it.

## Import redacted capacity commitments

For a controlled capacity study, collect a provider/model/study/epoch
commitment separately from request attempts. The importer accepts only request
counts and non-payload metadata; it recursively rejects prompts, completions,
raw requests/responses, credentials, and tokens.

```bash
uv run orcap ingest-capacity-commitments --input redacted-capacity-commitments.jsonl
```

Each JSONL object requires `commitment_id`, `observed_at`, `study_id`,
`provider`, `model_id`, `epoch_start`, `epoch_end`, and
`committed_requests`. `verification_method`,
`marginal_cost_usd_per_request`,
`capacity_linear_cost_usd_per_request`,
`capacity_cost_curvature_usd_per_request_sq`, and a non-payload `metadata`
object are optional. The capacity linear cost must be non-negative and the
curvature positive when supplied. H48 joins a record to a route attempt only for the same study,
provider, model, and half-open time interval `[epoch_start, epoch_end)`.
This records controlled-study declarations; it does not send traffic, reserve
capacity, contact a provider, or make a public capacity claim.

For a correlated-outage study, an owner may additionally supply
`failure_domains` as a de-duplicated list of non-payload labels such as
`["cloud:example", "region:us-east"]`. These are declared exposure labels,
not inferred uptime or proof of common ownership. They make a later
joint-outage model auditable without collecting request content.

## Import redacted capacity outcomes

After the same controlled epoch closes, import its aggregate allocation and
delivery result without exporting prompts or per-request responses:

```bash
uv run orcap ingest-capacity-outcomes --input redacted-capacity-outcomes.jsonl
```

Each JSONL object requires `outcome_id`, `observed_at`, `study_id`, `provider`,
`model_id`, `epoch_start`, `epoch_end`, `allocated_requests`, and
`served_requests`. The importer derives shortfall as allocated minus served;
optional `realized_cost_usd`, `realized_revenue_usd`, `verification_method`,
`declared_value_usd_per_served_request`, and non-payload `metadata` are
permitted. The value field is an owner-declared controlled-study proxy, not
consumer surplus or revenue. H48 only uses an outcome when its
provider/model/study/epoch exactly matches a commitment, and only treats
selected attempts in that same half-open epoch as controlled-study coverage.
This is not global routing flow or a capacity proof.

An outcome may also state `availability_status` (`available`, `unavailable`,
or `unknown`). An `unavailable` record must include a shared, non-payload
`outage_event_id`; all providers affected by the same observed incident use
the same identifier. This permits a controlled study to construct joint
availability states. It does not establish an outage cause, a failure
probability, or global router health.

## What H45 can and cannot establish

H45 can identify which public/configured policy is concentrated, which
providers are pivotal under synthetic outages, whether a documented public
quote change is sufficient to flip a lowest-cost winner, and how those facts
change over time as snapshots accumulate.

It cannot infer a platform's global routed volume, exact live health filters,
private provider capacity, or an actual selected provider. `router_route_attempts`
can support the last claim only for a controlled account study, and only after
the operator provides credentials, a private redacted destination, and an
approved hard spend cap. No command in this repository sends inference traffic
or configures a third-party account.
