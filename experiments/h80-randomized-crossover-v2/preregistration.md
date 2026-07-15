# H80 randomized routing crossover v2: pre-outcome protocol

Status: armed for remote collection after this protocol and the collector are
merged. This protocol was written after inspecting the fixed-order v1 pilot;
all v2 observations are a prospective holdout.

## Question and treatment arms

For a hot model with at least three public provider quotes, does delegating
provider selection to OpenRouter change execution success and observed spend
relative to pinning a provider shown on the public quote surface?

The model-hour block contains four one-token policies:

1. `openrouter_default`: no provider restriction; router fallback is allowed.
2. `pinned_cheapest`: public cheapest completion quote; fallback disabled.
3. `pinned_second`: public second-cheapest completion quote; fallback disabled.
4. `pinned_random`: a random remaining public quote; fallback disabled.

The four policies are uniformly permuted before any request in the block. The
assignment unit is policy position within model-hour block. The collector logs
the block ID, random seed, position, block size, and first-position probability
without retaining prompts or completions. The top four eligible models at each
run receive the crossover; their execution order is also randomized.

## Identification and estimands

The primary sample contains the position-zero request from every v2 block with
a valid recorded assignment. Let `S(p)` be success and `C(p)` observed billed
cost when policy `p` is assigned first. Uniform randomization identifies

`Delta S_p = E[S(default) - S(p)]` and
`Delta C_p = E[C(default) - C(p)]`.

This first-position contrast permits arbitrary effects of a probe on later
requests in its block. Full-block crossover estimates are secondary and will
not be called causal without rejecting meaningful position and carryover
effects.

For a user value `v` per successful response, the value-indexed policy contrast
is `Delta U_p(v) = v Delta S_p - Delta C_p`. If `Delta S_p > 0`, the break-even
value is `v*_p = Delta C_p / Delta S_p`. A negative `v*_p` with positive
`Delta S_p` means default weakly dominates for every nonnegative value under
the observed-spend accounting convention.

## Outcomes and tests

Primary outcome: request success. Secondary outcomes: HTTP 429 incidence,
observed billed cost per attempted request, and successful-request latency.

The three primary comparisons are default versus cheapest, second, and random.
We will report model-stratified inverse-probability estimates, randomization
inference under the logged assignment, 95% confidence intervals, and Holm
adjustment across the three success tests. Unadjusted estimates and the full
value-indexed utility frontier will also be reported.

The v1 pilot suggests a success gap, so no v1 observation enters a confirmatory
v2 p-value. The null is `Delta S_p = 0`; the directional alternative formed
from the pilot is `Delta S_p > 0`.

## Validity, exclusions, and stopping

- ITT: HTTP and network failures are outcomes, not exclusions.
- Position-zero rows do not require the later three requests to complete.
- A block is invalid only if its position-zero assignment is absent, duplicated,
  or inconsistent with the published seed and permutation algorithm.
- Models are time-varying by design; inference stratifies by canonical model and
  reports the support represented by the hot-model selection rule.
- Assignment balance and normalized position entropy are design audits, not
  outcome-based exclusions.
- The first confirmatory cut occurs after every policy has at least 40 valid
  first-position assignments, and no earlier than 160 valid blocks. Collection
  may continue, but later analyses must label their cut and may not replace the
  first confirmatory result.
- The planned collection window is seven days. If the sample gate is not met,
  the result is reported as power-gated rather than extending the stopping rule
  based on observed effects.

## Claim boundary

This experiment identifies the behavior of one owned API account, a one-token
probe workload, the dynamically selected hot-model support, and the policies
above. It does not observe other users' order flow, provider intent, private
router scores, or literal front-running. A rejection of equal success measures
an execution-firmness difference between delegated and pinned routing; it is
not by itself evidence of strategic quote manipulation.

## Implementation note after launch

On 2026-07-15, after eight valid blocks but before any arm approached the
40-observation gate, the analyzer was amended to blind all outcome estimates
while power-gated and to freeze the earliest chronological prefix satisfying
the prespecified balance rule. This changes no treatment, estimand, exclusion,
multiplicity family, or stopping threshold. Outcomes from the first four blocks
had been inspected as a collector smoke test before blinding; no treatment or
stopping decision was changed in response to their direction. The seed replay
and arm-count audit remains visible before the gate.

Also on 2026-07-15, after eight valid H80 blocks and while H80 outcomes were
blinded, the H80 and H81 workflows were assigned one shared non-cancelling
concurrency group. GitHub cron times are nominal and delayed starts could
otherwise overlap the two studies despite their 15-minute schedule offset.
This operational amendment serializes runs but does not change assignment,
treatment, support, outcomes, estimands, or stopping rules.

Later on 2026-07-15, a legacy cross-study descriptive audit (`WCV4`) printed
policy-level outcome aggregates that pooled prospective H80 rows with earlier
rows sharing the same labels. The dedicated H80 analyzer remained blinded, but
the pooled totals made some full-block prospective information indirectly
recoverable. WCV4 was then changed to exclude H80 and H81 study IDs entirely;
their outcomes can now be released only by their dedicated frozen-gate
analyzers. No assignment, treatment, exclusion, multiplicity, or stopping
decision was changed after seeing the pooled aggregates. This incident limits
analyst blinding but does not change the prespecified first-position estimator
or deterministic stopping rule.

After 12 verified first-position blocks, the reporting code was extended with
outcome-free repeated-support diagnostics and prespecified missingness bounds
for secondary outcomes. The support audit reports model block counts, model
dominance, effective model count, normalized entropy, hourly clusters, and
calendar span. For spend, a pinned arm receives a finite upper support only
when its captured public prompt and completion quotes imply a cap for at most
64 input tokens and the fixed one output token; default routing and rows
without that captured cap remain upper-unbounded when accounting is missing.
Successful-request latency uses the collector's fixed 60-second HTTP timeout
as its upper support. Selected-provider observation rates and missing counts
are reported directly. Spend bounds are reported both as arm-specific sample
bounds and with the logged first-position probabilities in the
Horvitz--Thompson estimator. These additions do not change the primary outcome,
treatments, assignment, exclusion rule, multiplicity family, or 40-per-arm
stopping gate, and every outcome-derived bound remains hidden before that gate.
