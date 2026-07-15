# H89 preregistration: randomized Hugging Face routing-policy frontier

Status: frozen before confirmatory enrollment. Study ID:
`huggingface-policy-frontier-v1`.

## Question and claim boundary

H89 asks whether routing delegation creates a causal cost--speed--reliability
tradeoff when the workload and model are held fixed. Hugging Face documents
three relevant controls on its OpenAI-compatible endpoint: `:fastest`,
`:cheapest`, and an explicit provider suffix. Its public `/v1/models` surface
also exposes provider price and throughput metadata. The response header
`x-inference-provider` makes realized provider selection auditable for our own
requests.

The experiment identifies policy effects only for our fixed one-token probes
on the frozen model population. It does not reveal other users' routing,
provider queues, physical capacity, provider intent, a direct-provider
contract, or collateralized liability. Hugging Face remains in the request and
billing path even in the explicit-provider arm.

Primary documentation:

- [Hugging Face Inference Providers and provider selection](https://huggingface.co/docs/inference-providers/en/index)
- [Hugging Face pricing and routed billing](https://huggingface.co/docs/inference-providers/en/pricing)
- [InferenceClient provider semantics](https://huggingface.co/docs/huggingface_hub/package_reference/inference_client)

## Pre-confirmatory feasibility pilot

On 2026-07-15 UTC, before this protocol was frozen, one non-randomized
`meta-llama/Llama-3.1-8B-Instruct:cheapest` request with `max_tokens=1` was
sent solely to verify telemetry. It returned HTTP 200, a selected-provider
header, token usage, estimated cost, and a request ID. That request was not
written to the study tables and is permanently excluded from H89.

## Population and workload

The model list is a literal constant in
`src/orcap/capture_hf_policy_probes.py`. It contains twelve public chat models
that had at least two live providers with price and throughput metadata at
design time. A model/run is eligible only if, before assignment:

1. at least two providers are live and report non-negative input and output
   prices plus positive throughput;
2. the public lowest-output-price provider differs from the public
   highest-throughput provider; and
3. the arm's conservative quote cap is at most $0.001.

The fixed request is temperature zero, `max_tokens=1`, and the short instruction
"Reply with the single word: pong." Prompts and completions are never retained.
Quote caps assume 64 input tokens and one output token, intentionally above the
pilot's observed prompt length.

## Treatments and assignment

The unit is a model x hourly run. Model evaluation order is randomized once per
run. For every eligible model, a separate 64-bit block seed assigns exactly
one arm with probability 1/3:

- `hf_fastest`: request `<model>:fastest`;
- `hf_cheapest`: request `<model>:cheapest`;
- `public_cost_caliper`: among providers whose total 64-input/one-output quote
  is within 1.25x of the minimum, pin the provider with highest public
  throughput, breaking ties by quote and provider ID.

There is one request, no client retry, and a 60-second timeout. The candidate
state, assignment, public predicted provider, randomization seeds, and SHA-256
state hash are written before the attempt outcome is analyzed. The collector's
console summary contains assignment support but no outcomes.

## Telemetry and design validity

The redacted attempt records HTTP success, wall-clock latency, selected
provider header, input/output token counts, and the response's
`usage.estimated_cost` when present. It never stores payload text or
credentials.

An assignment is valid only if the block seed replays, a linked attempt exists,
the policy and state hash match, and the requested suffix matches. A successful
request must expose a selected-provider header. A successful pinned-caliper
request must also select its assigned provider. The two server-side arms do
not assert that the selected provider equals the public prediction: hidden
health and failover are part of the treatment.

## Frozen outcomes and estimands

Outcomes remain absent from support exports until the first qualifying prefix.
At release, the intention-to-treat panel reports:

1. success rate;
2. failure-penalized latency, equal to observed latency capped at 60 seconds
   for successes and 60 seconds for failures or missing latency;
3. logged estimated cost and cost-telemetry completeness; and
4. generalized loss

   `cost + 0.0001 USD/second x failure-penalized latency + 0.01 USD x failure`,

   substituting the contemporaneous public assigned quote cap when response
   cost is missing.

The four preregistered two-sided contrasts are:

1. fastest minus cheapest on failure-penalized latency;
2. cheapest minus fastest on cost penalty;
3. public cost-caliper minus fastest on generalized loss; and
4. public cost-caliper minus cheapest on generalized loss.

Inference uses model-day cluster bootstrap 95% intervals and Monte Carlo
randomization tests under the recorded equal-probability assignment. Holm
adjustment covers the four tests. Generalized loss is an owner objective under
stated values, not social welfare or revealed willingness to pay.

## Fixed release and stopping rule

The analyzer releases outcomes at the earliest chronological prefix satisfying
all conditions:

- at least 72 elapsed hours from the first valid assignment;
- at least 120 valid assignments per arm;
- at least eight distinct models;
- at least five public candidate providers;
- no public predicted provider exceeds 75% of valid assignments;
- treatment compliance is at least 95%; and
- seed replay is 100%.

The release prefix is immutable. Additional observations after that prefix are
follow-up monitoring and cannot alter the confirmatory estimate. If a gate
never passes, H89 remains power-gated; no outcome-dependent extension,
substitution of models, or threshold change is allowed under this study ID.

## Cost and operations

The conservative public-quote budget is $5 per 31-day month, implemented as a
per-run cap of `5 / (31 x 24)` dollars plus the $0.001 per-request cap. Actual
one-token requests are expected to cost far less. Collection runs remotely in
GitHub Actions and is consolidated into the private Hugging Face dataset by
the existing nightly artifact pipeline; it does not depend on a laptop being
online.
