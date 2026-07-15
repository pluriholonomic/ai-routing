# H81 fallback-versus-selection decomposition: pre-outcome protocol

Status: written before the first H81 request. H81 is a distinct experiment and
does not alter, pool with, or change the stopping rule of H80 v2.

## Economic question

The default-versus-pinned effect combines two mechanisms: fallback after a
failed first provider and information or scoring used to choose the provider
order. H81 separately identifies these components using one public quote
snapshot and three policies:

1. `price_only_no_fallback`: request only the cheapest displayed provider and
   disable fallback.
2. `price_order_fallback`: submit every displayed provider in cheapest-first
   order, restrict eligibility to that same list with the provider `only`
   field, and allow fallback within the list.
3. `delegated_default`: submit no provider restriction and allow the router to
   select and fall back under its default policy.

Let success under these policies be respectively `S_N`, `S_F`, and `S_D`.
The two primary estimands are

- fallback option value: `Delta_F = E[S_F - S_N]`; and
- hidden-selection value: `Delta_I = E[S_D - S_F]`.

The total delegation effect `E[S_D-S_N] = Delta_I + Delta_F` is secondary.
This is an accounting decomposition of policy effects, not a claim that the
router literally observes capacity or that either component is nonnegative.

## Assignment and support

Each eligible model-hour block uses the same fetched public provider list for
all policies. The three policies are uniformly permuted from a fresh recorded
64-bit block seed. Only position zero is confirmatory, permitting arbitrary
effects of that request on later requests.

To avoid changing H80's treatment support, H81 uses ranking positions five and
six while H80 uses the top four models for its crossover. H81 runs at minute 52;
the next H80 run occurs 45 minutes later. Model order is randomized. A model is
eligible only when at least two distinct positive-price providers are displayed.

The collector records the full public provider order, its SHA-256 digest, the
cheapest price and identity, policy order, block and run seeds, fallback
permission, provider `only` count, first-position probability, final selected provider, success,
HTTP status, latency, token accounting, and billed cost. It never stores prompt
or completion payloads.

## Inference

The primary outcome is request success. HTTP and network failures are retained
as intention-to-treat outcomes. For both primary contrasts we report:

- model-stratified and pooled Horvitz--Thompson estimates using the logged
  first-position probability;
- unadjusted Hájek differences and Newcombe 95% intervals;
- one-sided randomization p-values for positive effects under the logged
  uniform assignment; and
- Holm adjustment across the two primary directional tests.

The total-delegation contrast is secondary and excluded from the Holm family.
Secondary outcomes are HTTP 429 incidence, observed billed spend per attempt,
successful-request latency, final selected-provider missingness, and observed
fallback incidence. Spend effects are released only when accounting is complete
in both compared arms; otherwise no point estimate is imputed and only the
prespecified support bounds are reported.

## Stopping and exclusions

The first confirmatory cut occurs after every policy has at least 40 verified
first-position assignments and at least 120 verified blocks, no earlier. The
planned collection window is seven days. If the balance gate is not reached,
the study is reported as power-gated. Collection failures do not extend or
change the stopping rule based on observed outcomes.

Before that gate, the public analyzer releases assignment counts and replay
diagnostics but blinds every outcome estimate and p-value. At the gate it
deterministically freezes the earliest chronological prefix satisfying all
three arm counts; later observations cannot replace or enlarge the first
confirmatory cut.

A first-position observation is invalid only when its block ID or assignment
metadata is absent, position zero is missing or duplicated, or replaying the
recorded seed does not reproduce its policy. Before outcomes are read, the
analyzer also requires the recorded `order` length, `only` length, and fallback
flag to match that policy's prespecified controls. Later-position absence or
failure does not invalidate position zero. Assignment balance and normalized
order entropy are design audits rather than outcome-based exclusions.

## Interpretation boundary

`Delta_F` is the effect of enabling fallback behind the same cheapest first
provider and explicit public order. `Delta_I` is the effect of replacing that
public order with default delegation while preserving fallback permission.
The latter can reflect private eligibility, performance scoring, contractual
rules, or other undocumented state; H81 cannot distinguish those channels.
Neither effect measures routed market share, other users' welfare, provider
cost, strategic intent, front-running, or literal capacity certification.

## Operational amendment after launch audit

On 2026-07-15, after two complete H81 blocks and before any outcome was
released, H80 and H81 were assigned one shared non-cancelling GitHub Actions
concurrency group. Cron offsets alone do not guarantee actual start-time
separation when scheduled jobs are delayed. The amendment prevents cross-study
probe overlap; it changes no assignment, treatment, eligibility rule, outcome,
estimand, exclusion, multiplicity family, or stopping threshold.

Later on 2026-07-15, a legacy cross-study descriptive audit (`WCV4`) printed
outcome aggregates for all three H81 labels from the first two blocks, bypassing
the dedicated H81 analyzer's power gate. WCV4 was then changed to exclude H80
and H81 study IDs entirely, with a regression test requiring this isolation.
No assignment, treatment, eligibility, exclusion, multiplicity, or stopping
decision was changed after this inadvertent disclosure. The incident means the
analyst was not fully outcome-blind for those two launch blocks; the fixed
first-position estimator, earliest-balanced-prefix rule, and 40-per-arm gate
remain unchanged and will be reported with this limitation.

After four verified blocks, an outcome-free eligibility table was added for
resolved public ranking positions five and six. It records every candidate's
endpoint-fetch status, positive-quote and distinct-provider counts, eligibility
decision and reason, public quote digest, ranking position, and evaluation
order. Candidate and eligible model counts, exclusion reasons, dominance,
effective support, entropy, and adjacent-run support turnover are public before
the outcome gate. The first four blocks predate this table and are explicitly
left-truncated: their successful block formation proves eligibility but cannot
recover excluded candidates.

The same amendment prespecifies distribution-free missingness bounds for
secondary outcomes. Explicit public-order arms receive a finite spend cap only
when the captured public quotes cover at most 64 input tokens plus the fixed
one output token; delegated default may leave that provider set and is not
assigned the public-set cap. Successful-request latency is bounded by the
fixed 60-second HTTP timeout, and selected-provider observation is reported by
arm. No primary outcome, treatment, assignment, exclusion, multiplicity, or
stopping rule changed, and these outcome-derived bounds remain blinded until
the fixed 40-per-arm gate.
