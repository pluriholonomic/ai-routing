# H95 fixed-horizon delegation replication

Status: prospective protocol. This document must be committed before the first
H95 inference request. H95 is a separate replication of H81 and is never pooled
with it.

Study id: `openrouter-delegation-replication-v1`

## Question and estimands

For an owned one-token OpenRouter request, how much first-position completion
probability is created by:

1. allowing fallback while holding the public cheapest provider first; and
2. delegating provider selection to the router rather than supplying the full
   public cheapest-first provider order?

The two primary intent-to-treat contrasts are:

- `price_order_fallback - price_only_no_fallback` (fallback option value);
- `delegated_default - price_order_fallback` (hidden-selection value).

`delegated_default - price_only_no_fallback` is the secondary accounting sum.
The estimand is an owned-account policy effect for the sampled eligible models,
not market-wide routed share, provider intent, profit, or welfare.

## Candidate population and open-weight boundary

At each run, the collector obtains the public weekly OpenRouter model ranking and
model catalog. It considers ranking positions 7 through 30, excluding ranks 1-4
used by H80 and ranks 5-6 used by H81. A candidate must have:

- a nonempty OpenRouter `hugging_face_id`;
- a successfully fetched public endpoint list; and
- at least two distinct providers with positive completion prices.

The Hugging Face link is an operational open-weight screen, not a verified
license. The release reports the exact Hugging Face ids and performs a separate
license/model-card audit. Broad "open-source" language additionally requires an
identified permissive or open-use license; otherwise the paper says
"Hugging Face-linked open-weight candidate."

Every candidate and exclusion is written to
`router_replication_eligibility` before an outcome is requested. If fewer than
three candidates are eligible, no triplet is planned and no request is sent.

## Randomization and treatments

For a run with at least three eligible candidates:

1. a 64-bit operating-system random seed is logged;
2. three eligible models are sampled uniformly without replacement;
3. the three policies are uniformly permuted across those models, assigning
   exactly one policy to first position per model; and
4. within each model, the two remaining policies are uniformly ordered using a
   logged block seed.

The policies are:

- `price_only_no_fallback`: public cheapest provider in `order` and `only`,
  `allow_fallbacks=false`;
- `price_order_fallback`: all public providers in increasing completion-price
  order in `order` and `only`, `allow_fallbacks=true`;
- `delegated_default`: no provider restriction, fallback permitted.

Each accepted triplet therefore has three selected models, nine total requests,
and exactly one first-position request per arm. The marginal first-position
assignment probability is 1/3. Only first-position requests are confirmatory;
later requests are carryover-sensitive diagnostics.

## Fixed horizon and missing runs

The confirmatory horizon is the first 120 valid, prospectively written triplet
plans ordered by plan timestamp and stable triplet id. This is 360 planned
first-position blocks and exactly 120 assignments per arm. It is not an
arm-balance stopping rule.

The collector may continue after the horizon until the workflow is disabled,
but later triplets are excluded from the confirmatory result. A planned block
whose request record is missing remains in the horizon. Primary success is one
only for a recorded, assignment-compliant successful first request; a missing
record, failed request, or noncompliant first policy is coded zero. Separate
best/worst missing-record bounds are reported. This conservative rule prevents
workflow completion from selecting the analysis sample.

## Outcomes

Primary outcome:

- binary first-request completion under the assigned policy, with missing or
  noncompliant records coded as failure.

Secondary outcomes, reported only with their observation rates and protocol
bounds:

- rate-limit rejection;
- selected-provider observation and fallback occurrence;
- total cost;
- successful-request latency;
- provider identity and public-price rank.

Prompt and completion payloads are never retained.

## Inference

The primary analysis averages within-triplet binary policy differences. Under
the sharp null, the three observed first-position outcomes in each triplet are
held fixed and policy labels are independently permuted over the six assignments
allowed by the design. Randomization p-values use at least 100,000 draws.

The two directional primary p-values are Holm-adjusted as one family. Two-sided
randomization p-values, paired standard errors, normal descriptive intervals,
Wilson arm intervals, and protocol-valid missing-record bounds are also shown.
The total-delegation contrast is secondary and is not part of the primary
multiplicity family.

No observation, arm, model, or triplet is excluded based on an outcome. Duplicate
telemetry is resolved by immutable source/event id and latest ingestion time.
Assignment replay, treatment metadata, and plan compliance are reported before
any effect estimate.

## Transport and model-support gates

A broad multi-model statement requires all of:

- at least eight selected model ids;
- effective model count at least five;
- no selected model above 35% of planned blocks;
- at least eight audited Hugging Face ids;
- both primary effect directions stable under leave-one-model-out analysis; and
- no single six-hour UTC bin supplies more than 20% of triplets.

Failure of a transport gate does not invalidate the blocked randomized effect;
it narrows the claim to the realized support. H95 is reported separately from
H81 even if both estimates have the same sign.

## Operational safeguards and budget

H95 shares the non-cancelling `randomized-routing-probes` workflow lock with H80
and H81. It runs at a separate hourly offset. Every request uses the fixed short
prompt, `max_tokens=1`, temperature zero, and usage accounting. There are nine
requests per planned triplet and at most 1,080 requests in the confirmatory
horizon. Eligibility records are uploaded even if the request step fails.

## Promotion rule

No outcome query or effect estimate is permitted before 120 valid planned
triplets exist. At the gate, a clean release job pins one immutable dataset
revision before querying inputs, analyzes exactly the first 120 plans, and
publishes the result regardless of sign or precision. Any protocol change is
recorded as a dated amendment without rewriting this document.
