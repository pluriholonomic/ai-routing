# H86/H87 preregistration: public capacity state and realized execution

Frozen: 2026-07-15T14:15:00Z

Status: frozen before joining any individual legacy probe outcome to public
capacity state, fitting any H86 model, or collecting any H87 request. The
policy-level H80 pilot rates, H82 enforcement paths, and H84 stale-quote result
were already known and motivate the studies. H86 is retrospective discovery.
H87 is a disjoint prospective randomized policy experiment.

## Question

Does the public capacity state that predicts a router-side rate-limit event
also predict whether a provider-pinned request is executable? If so, does a
routing policy that avoids the publicly riskier provider improve realized
delivery relative to selecting that provider or delegating to the default
router?

H84 rejected the proposed stale-cheap channel. Its cases instead had smaller
displayed capacity ceilings and higher displayed utilization. H86 tests whether
that public state transports from aggregate router enforcement to owned
execution. H87 randomizes the policy that acts on the state. Neither study
randomizes a provider's physical capacity, cost, quote, or intent.

## Public provider state

The source is the canonical public endpoint panel used by H84, deduplicated on
`run_ts, model_permaslug, endpoint_uuid, provider_name`. At a model-snapshot,
aggregate exact-name rows to the provider level:

- `provider_price` is the minimum finite positive completion price;
- `provider_capacity_ceiling_rpm` is the sum of finite positive endpoint
  ceilings;
- `provider_recent_peak_rpm` is the sum of recent peaks only across endpoints
  entering the capacity-ceiling sum; and
- `provider_capacity_load` is the summed peak divided by the summed ceiling.

An endpoint with a missing or nonpositive ceiling does not enter either sum.
Providers require a finite positive provider ceiling and finite nonnegative
load. No outcome, post-request public state, latency, or error count enters the
risk score.

Within each model-snapshot, compute average percentile ranks with larger values
meaning larger state. Define the frozen public capacity-risk score

`capacity_risk = percentile_rank(capacity_load) - percentile_rank(log1p(capacity_ceiling_rpm))`.

Higher values mean more utilized and smaller displayed capacity. The signs are
fixed from H84; no H86 coefficient is used to alter the score.

## H86: retrospective execution bridge

### Sample and isolation

- Include only `study_id = openrouter-default-probes-v1`.
- Include provider-pinned policies `pinned_cheapest`, `pinned_second`, and
  `pinned_random`; exclude every default-router attempt.
- Exclude the prospective H80 v2 study and every H81/H87 row. H80/H81 outcome
  masking is therefore unchanged.
- Use H80's deduplication and conservative legacy-block construction. Retain
  complete four-policy blocks whose span is at most 120 seconds, but analyze
  only their three pinned rows.
- For each attempt, select the latest public model snapshot at or before the
  attempt and no more than ten minutes old. Require exact model identifier and
  exact requested-provider name. No future snapshot or fuzzy provider alias is
  permitted.
- Retain a block only when at least two pinned providers have complete public
  capacity risk. If a provider name maps to no public state, record the failed
  join and exclude it from the risk contrast.

The individual probe outcomes and aggregate policy rates already exist, so H86
is explicitly discovery evidence even though the state join is frozen here.

### Outcomes and primary contrast

The primary outcome is request failure, defined before the join as
`outcome != succeeded`. HTTP 429 is secondary. Missing generation accounting
does not make an otherwise successful request fail.

Within each retained block, select the pinned provider with highest capacity
risk and the provider with lowest capacity risk. Ties at either extreme make
the block ineligible. The primary estimand is

`mean(failure_high_risk - failure_low_risk)`.

The directional hypothesis is positive. Report a 95% model-day cluster
bootstrap interval using 10,000 draws and seed `86870715`, plus an exact
one-sided paired sign test on discordant blocks. Report the analogous 429
contrast as secondary.

### Calibration and diagnostics

1. Report join coverage by policy, model, provider, date, and outcome without
   imputing missing public state.
2. Report high-minus-low differences in log price, capacity load, log capacity
   ceiling, quoted rank, and temporal order.
3. Repeat the primary contrast on pairs whose prices differ by at most 25%.
4. Report leave-one-provider-out and leave-one-model-out contrasts.
5. Permute risk labels among the capacity-observed pinned providers inside each
   block using 10,000 deterministic draws. This is a predictive association
   reference, not randomization inference.
6. Train on the earliest 70% of blocks and test on the latest 30%. Compare a
   baseline score using quoted rank and relative log price with the baseline
   plus capacity risk. Report held-out log loss, AUC when both classes occur,
   and Brier score. All preprocessing is fit on training blocks only.
7. Report successful-request latency by risk arm as a selected secondary
   outcome, with no causal interpretation.

H86 supports at most transport of a public capacity score to this account's
legacy pinned requests. The endpoints were not randomized and legacy within-
block order was fixed, so it cannot identify the causal effect of capacity.

## H87: prospective randomized capacity-policy trial

### Candidate construction

H87 starts only after this freeze. Immediately before each block, fetch the
public quote list and frontend operational endpoint state for a hot model.
Build provider aggregates exactly as above and exclude deranked providers.

Generate every provider pair satisfying all of:

1. both providers have finite public capacity risk and positive quote;
2. their completion prices differ by at most 25% multiplicatively;
3. one provider has strictly higher capacity risk; and
4. the pair has distinct provider identities.

Choose the pair with the largest capacity-risk gap. Break exact ties by the
lexicographic tuple of provider names. Label the lower-risk member
`capacity_safe` and the higher-risk member `capacity_risky`. Candidate
construction occurs before treatment assignment and is persisted even if the
request fails.

If a model has no eligible pair, record an outcome-free candidate-funnel row
and send no request. The model universe is the first eight non-variant models
in the public weekly ranking, resolved before randomizing evaluation order.

### Assignment and treatment

Each eligible model-run is one block. Uniformly randomize exactly one of three
policies using a cryptographic run seed and a separately recorded block seed:

- `capacity_safe`: pin the lower-risk provider and disable fallback;
- `capacity_risky`: pin the higher-risk provider and disable fallback; or
- `openrouter_default`: send no provider preference.

Send exactly one one-token request per block. This makes treatment the first
and only exposure, eliminating within-block carryover. Persist the assignment
probability, seed, candidate-state hash, provider identities, public fields,
quote timestamp, request timestamp, and the redacted standard route-attempt
record. Never retain prompt or completion content.

### Estimands

The primary family contains two intention-to-treat contrasts:

1. success(`capacity_safe`) minus success(`capacity_risky`); and
2. success(`openrouter_default`) minus success(`capacity_safe`).

Use difference in means with inverse assignment-probability weighting (all
probabilities are 1/3), model-day cluster-bootstrap 95% intervals, and blocked
randomization inference. Apply Holm correction across the two primary tests.
The first contrast identifies the delivery effect of acting on the frozen
public capacity score for the eligible candidate-pair population. The second
tests whether hidden default-router information adds value beyond that public
policy.

Secondary outcomes are HTTP 429, observed billed spend with failures assigned
zero spend, selected provider, latency conditional on success, and the value
frontier `delta spend / delta success`. Missing successful-request accounting
remains missing; design-based support bounds accompany spend and latency.

### Masking, release, and stopping

Before every sample gate passes, H87 may expose only candidate and assignment
support:

- eligible and ineligible blocks and reason codes;
- assignments by arm, model, UTC date, and provider;
- seed replay and treatment-compliance checks;
- pre-treatment price and capacity-state coverage without outcome splits; and
- cumulative spend cap computed from public quotes, not realized outcomes.

No arm outcome, contrast, coefficient, interval, p-value, selected-provider
rate, latency, spend, or sign may be released early.

The first release requires all of:

- 28 complete UTC days after the first eligible block;
- at least 150 valid assignments to each arm;
- at least ten models and twenty distinct candidate providers;
- no requested provider supplies more than 20% of pinned assignments;
- at least 90% exact treatment compliance in each pinned arm;
- all published seeds replay exactly; and
- no cross-study probe overlap within five minutes.

Freeze the earliest chronological prefix satisfying every gate and publish it
regardless of sign. Later data cannot replace the first eligible cut. There is
no significance-based stopping.

### Cost and safety

Every request uses the existing fixed prompt, `max_tokens = 1`, temperature
zero, a 60-second timeout, and generation-metadata polling. At most eight
requests are sent per run. A run must abort if the public quote-implied cost cap
for any assigned pinned request exceeds `$0.01` or if the monthly pre-request
quote cap would exceed `$10`. Default-arm spend is monitored separately because
its hidden selected provider may not belong to the candidate pair.

## Claim boundary

H87 randomizes a routing policy for small owned probes in public-state-eligible
model-times. It can identify the policy effect for that population. It cannot
identify a provider's physical capacity, marginal cost, strategic intent,
front-running, other users' welfare, or the effect of a collateralized capacity
commitment. A positive result would validate public capacity state as a useful
routing input; a null result would reject the proposed operational use at the
frozen detectable scale.

## Execution log

- `2026-07-15T14:17Z`: the first authoritative H86 invocation stopped while
  constructing public provider aggregates because a nullable missing
  `recent_peak_rpm` coverage flag could not be cast to integer. It produced no
  state join, risk pair, contrast, model, plot, or outcome summary. The repair
  explicitly maps missing public coverage flags to false and adds a regression
  test. No sample, score, match, outcome, estimand, interval, or interpretation
  rule changed before the rerun.
- `2026-07-15T14:19Z`: the second authoritative invocation completed the exact
  backward match construction but found no block with two distinct complete
  provider risk scores. The empty pair table then raised a missing-schema error
  before producing a summary, contrast, coefficient, plot, or outcome result.
  The repair declares the frozen pair-table schema even when it has zero rows
  and adds an empty-support regression test. It does not relax the ten-minute
  window, exact provider match, risk-field completeness, or any other gate.
