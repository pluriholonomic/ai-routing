# Remote empirical program for paid routing, online price tests, and live elasticity

Status: implementation plan. This document is not itself a preregistration and
does not authorize spending.

Date: 2026-07-18

## 1. Objective and current boundary

The program has three linked objectives:

1. use owned, budget-capped OpenRouter requests to measure realized provider
   selection, quote firmness, substitution, latency, failure, and routing
   persistence;
2. continuously join those outcomes to the five-minute public quote and router
   enforcement panel so price-response, synchronization, stale-quote, and
   benchmark-relative hypotheses can be evaluated online; and
3. estimate the router's live price exponent, including its uncertainty and
   temporal drift, without assuming that the documented inverse-square shadow
   is the realized selection rule.

All collection, compaction, analysis, and monitoring must run on GitHub Actions
and Hugging Face. A workstation may be used for development and audit, but it
must not be required for data continuity.

The frozen H96 campaign, `openrouter-route-calibration-v1`, is already running.
Do not amend its models, arms, dates, budgets, estimands, or output tables.
Treat it as the pilot for this program. H81 remains immutable and H95 remains a
separate fixed-horizon blinded study. None of the new work may query, pool, or
alter H95 outcomes.

The strongest possible claim from the proposed public-plus-owned data is about
the routing of this project's requests under observed menus. The program will
not identify market-wide flow, provider marginal cost, provider profit, a
provider's learning algorithm, collusive intent, or literal front-running.

## 2. Remote architecture

The existing repository pattern should remain the system architecture:

```text
OpenRouter public menus and owned requests
        |
        v
GitHub Actions collector
  1. freeze candidate menu
  2. commit assignment-only artifact
  3. execute bounded paid tasks
  4. upload redacted outcome artifact even on failure
        |
        v
Actions artifacts (intraday buffer, 14-day retention)
        |
        v
nightly compact.yml + assemble_artifacts.sh
        |
        v
private t4run/openrouter-market-history dataset on Hugging Face
        |
        +--> revision-pinned analysis and immutable releases
        |
        +--> aggregate price/exponent dashboard in a private HF Space
```

GitHub artifacts are the short-lived transport buffer. The private Hugging Face
dataset is the durable source of truth. Every formal analysis resolves one
immutable HF revision at its start and records that revision, the Git commit,
the environment-lock hash, and the analysis-spec version.

## 3. Study registry

Use descriptive study IDs in the schemas. Hypothesis numbers can change without
changing a data contract.

| Program | Study ID | Role | Outcome access |
|---|---|---|---|
| frozen pilot | `openrouter-route-calibration-v1` | H96 baseline | ordinary owned-study analysis |
| repeated paid choice study | `openrouter-price-response-v1` | scheduled router calibration and eligibility interventions | ordinary owned-study analysis after plan integrity passes |
| event-triggered paid study | `openrouter-price-event-v1` | cut, raise, rank-crossing, and quote-fading waves | discovery release, followed by a separately versioned confirmation |
| live exponent | `openrouter-live-price-exponent-v1` | rolling and expanding price-sensitivity estimates | aggregate analysis only |
| public price monitor | `openrouter-price-tests-online-v1` | recurring public/owned hypothesis panel | monitoring estimates only; no significance stopping |

The repeated choice and event studies need their own preregistration directories
under `experiments/` before their first paid request. A future confirmatory
event study must use a new study ID such as `openrouter-price-event-v2`; it must
not silently reuse discovery observations.

## 4. Program A: paid experiments

### 4.1 Activation order

1. Allow H96 to finish and audit its assignment coverage, realized cost,
   runtime, candidate coverage, and generation-metadata latency.
2. Do not activate another recurring paid workflow while H95 is collecting on
   the shared `randomized-routing-probes` concurrency group. This avoids delayed
   event waves and cross-study carryover.
3. Build and run a no-spend remote preflight for the new studies.
4. Run a one-model, one-shape canary with a maximum quote cap of `$1.00` and a
   platform-enforced key limit.
5. Expand to a seven-day discovery campaign only if every deployment gate in
   Section 12 passes.
6. Freeze a separate confirmatory specification after discovery and before
   viewing confirmatory outcomes.

If timely event probes are needed before H95 completes, provision a separate
OpenRouter project/account key and use a separate concurrency group. A second
key on the same account is not assumed to provide account-state isolation.

### 4.2 Dedicated key and budget controls

Create a low-privilege GitHub Actions secret named
`OPENROUTER_PRICE_EXPERIMENT_KEY`. Do not reuse a key stored in a repository
file. Configure a hard OpenRouter project limit below the available credit.

Freeze these initial budget envelopes:

| Stage | Maximum spend |
|---|---:|
| H96 frozen pilot | `$4.20` |
| new canary and failure audit | `$5.00` |
| seven-day repeated-choice discovery | `$35.00` |
| event-triggered discovery reserve | `$60.00` |
| fixed confirmatory campaign | `$150.00` |
| robustness and replacement reserve | `$100.00` |
| unallocated safety reserve | at least `$145.80` |

The implementation must enforce four independent limits:

- conservative quote cap for every task;
- per-run cap, initially `$1.00` for the canary and at most `$5.00` later;
- rolling UTC-day cap, initially `$10.00`; and
- campaign cap fixed in the preregistration and in code.

The collector must fail closed if it cannot reconstruct the last 24 hours of
spend from the HF ledger plus not-yet-compacted successful Actions artifacts.
The platform key limit is the final stop loss; the local accounting is not a
substitute for it.

### 4.3 Model and provider universe

Select the universe using only information available before paid outcomes for
that run. Each UTC day, freeze a candidate table from the previous seven complete
days of public data.

A primary model is eligible when it has:

- at least three distinct compatible provider names;
- exact endpoint tags for the providers used in pin/order arms;
- positive prompt and completion prices;
- at least 95% public source continuity over the prior six hours;
- no current model-wide source-health failure;
- at least one economically meaningful relative-price difference; and
- a request-shape all-in quote below the frozen task cap.

Stratify rather than pool the following provider types:

- author/model-provider quote;
- exact author-price follower;
- persistent discounter;
- fast repricer;
- slow or unobserved repricer;
- large/reserved-capacity provider where the classification has a dated public
  source; and
- smaller inference specialist.

The provider taxonomy is descriptive. Funding and capacity classifications
must include source URL, observation date, and a confidence/missingness flag.
Do not infer reserved capacity from company size alone.

For HMP-style comparisons, oversample the observed Novita--StreamLake pair on
their shared models, but require matched nonsynchronized provider pairs and
report pair concentration. No single pair may supply more than 25% of a
confirmatory sample.

### 4.4 Request shapes

The core price-response study should use two low-cost shapes:

1. `short_chat`: approximately 64 input tokens and at most 8 output tokens;
2. `output_heavy`: approximately 128 input tokens and at most 128 output
   tokens.

Retain H96's input-heavy and tool-call shapes as secondary calibration strata,
not as requirements for every recurring run. Every request has temperature
zero, a payload-free workload ID, a unique nonce, and no persisted prompt or
completion. Exact input/output counts and billed cost come from generation
metadata.

### 4.5 Repeated-choice block

For each eligible model-shape block, freeze the public menu before any request.
Collapse multiple exact endpoints to the cheapest compatible endpoint within a
provider when only provider-name outcomes are observable. Retain the endpoint
ambiguity flag.

The discovery block contains the following assignments:

| Arm | Count | Intervention | Main use |
|---|---:|---|---|
| `default_loose_fresh` | 6 | fresh session, broad preregistered max-price menu | realized default choice and exponent |
| `default_top2_cap` | 2 | component-wise cap admitting exactly the cheapest two providers | causal substitution/eligibility |
| `default_top1_cap` | 2 | component-wise cap admitting only the cheapest provider | admission and failure outside option |
| `sort_price_loose` | 2 | `sort: price` in broad menu | documented price-policy validation |
| `ordered_ab` | 1 | `[A,B]`, fallback allowed | order/fallback effect |
| `ordered_ba` | 1 | `[B,A]`, fallback allowed | order/fallback effect |
| `pinned_a` | 1 | exact tag, no fallback | provider A firmness/performance |
| `pinned_b` | 1 | exact tag, no fallback | provider B firmness/performance |

A cap arm is eligible only when a component-wise rectangular price cap truly
admits the intended provider set. Otherwise record `cap_not_separating` and do
not issue that task. Do not pretend that a prompt-price ordering also orders
output-heavy all-in cost.

Randomize all non-history task positions within the block. Use new session IDs
and prompt nonces. Retain task and block seed commitments, assignment
probabilities, intended order, and actual start times.

### 4.6 Routing-memory subexperiment

On a prespecified subset of blocks, replace the ordered pair arms with four
history arms:

- four fresh sessions;
- a same-session sequence of length four;
- same session but new prompt nonce and changed request shape;
- same session after the initially selected provider is excluded by a valid
  price cap.

The estimand is provider-repeat probability and the change in selection after
exclusion, by history length. This measures owned-session routing persistence.
It is not evidence of provider pricing memory or market-wide router state.

### 4.7 Event-triggered paid experiment

The public capture process should create an outcome-free trigger when two
contiguous snapshots, no more than ten minutes apart, contain at least one of:

- an all-in quote cut of at least 5%;
- an all-in quote increase of at least 5%;
- a crossing of the cheapest compatible-provider rank;
- entry or exit of the cheapest compatible provider; or
- a derank/rate-limit transition, placed in a separate enforcement cohort.

Require at least two compatible providers before and after the event. The clean
price cohort excludes a simultaneous derank, rate-limit spike, capability
change, or source-health failure. Those events remain in explicitly labeled
mixed/enforcement cohorts.

At trigger time, freeze all intended waves:

| Wave | Target time from public event | Maximum tolerated lateness |
|---|---:|---:|
| W0 | immediately | 20 minutes |
| W1 | 15 minutes | 20 minutes |
| W2 | 1 hour | 30 minutes |
| W3 | 3 hours | 45 minutes |
| W4 | 6 hours | 60 minutes |
| W5 | 24 hours | 120 minutes |

If Actions delay exceeds the tolerance, retain the assignment with
`attempt_status=missed_window` and send no replacement request. Never move a
late observation into an earlier wave.

Each wave contains:

- four fresh-session default requests;
- one price-sorted request;
- one pin to the moving provider;
- one pin to the pre-event cheapest provider when distinct; and
- one valid randomized eligibility-cap request.

Create matched no-change controls using only pre-event variables: model,
request shape, provider count, price dispersion, clock hour, public health, and
pre-event selection support. Price increases are a prespecified sign placebo
for cuts, not substitutes for no-change controls.

### 4.8 Paid-study outcomes

All outcomes use the existing redacted `router_route_attempts` contract:

- selected provider;
- success/failure/unknown;
- requested provider and fallback;
- input and output tokens;
- billed cost;
- latency and, where generation metadata supports it, throughput;
- public quote snapshot ID;
- task, block, wave, event, policy, and preregistration version in metadata.

Prompts, completions, raw bodies, authorization headers, unhashed session IDs,
and customer identifiers are prohibited.

Primary paid estimands are:

1. default-provider choice probabilities under contemporaneous menus;
2. average treatment effects of eligibility caps on provider choice, failure,
   latency, and cost;
3. paired cheapest-versus-second-provider firmness and performance;
4. event-time change in moving-provider selection probability;
5. event-time selection followed by latency/failure deterioration, the
   controlled-account stale-quote/adverse-selection diagnostic; and
6. routing-history effects from the memory subexperiment.

Use intention-to-treat for failed/missing assigned tasks. Conditional-on-success
choice calibration is secondary and must be accompanied by assignment-level
missingness bounds.

## 5. Program B: recurring online price tests

### 5.1 Monitoring versus confirmation

Continuous dashboards are exploratory monitoring. Repeatedly displaying a
rolling p-value does not create a confirmatory result.

For every hypothesis, maintain two outputs:

- `monitoring`: rolling estimates, support, and diagnostics, never used for a
  significance-based stopping rule; and
- `release`: the first immutable chronological prefix satisfying a frozen
  sample-only gate, analyzed once and released regardless of sign.

Use confidence sequences or a prespecified alpha-spending schedule only where
the implementation and tests validate sequential coverage. Otherwise omit a
live significance label and reserve inference for prespecified weekly or final
looks.

### 5.2 Online tests

| Test | Estimand | Inference | Promotion gate | Claim boundary |
|---|---|---|---|---|
| P1 correlated experimentation | same-direction, same-model, same-five-minute provider pairs | provider-level circular day shifts preserving clock time | 28 complete days, at least 20 models, concentration audit | excess quote synchronization, not HMP algorithm use |
| P2 HMP SNR gradient | synchronization and benchmark premium versus preperiod routing-information SNR | model-day clustered regression; leave-one-pair-out | at least 30 independent price experiments and 1,000 covered default choices | HMP comparative-static consistency only |
| P3 omitted-rival-price bias | own-price coefficient without rival quote minus coefficient with rival quote | pair/model-day block bootstrap | at least 20 price-changing pairs, 200 choices per focal cohort | misspecification diagnostic, not provider beliefs |
| P4 price-cut selection response | event-time moving-provider choice share relative to matched controls | randomization inference for paid arms; event-study bootstrap for natural cuts | at least 60 clean cut events, 60 controls, 10 models, 10 movers | controlled-account routing response |
| P5 quote fading/adverse selection | initial selection gain followed by failure, latency, rate-limit, or derank deterioration | event-wave contrasts and same-model controls | at least 40 initially selected cut events and 80% wave completion | stale-quote fill/fade, not strategic intent |
| P6 benchmark-relative pricing | choice and update hazard versus distance from author quote and current cheapest quote | model-time fixed effects; author-label hard null | at least 20 author-linked models and 10 author families | benchmark association only |
| P7 cadence and provider type | elasticity, premium, and firmness for fast/slow and provider-type strata | provider/model block bootstrap; leave-one-provider-out | no type supplies more than 40% of observations | heterogeneity, not causal capital structure |
| P8 routing memory | repeat probability and exclusion response by history length | randomized history-arm contrasts | 200 complete history blocks | session routing memory only |
| P9 quote-surface response after routing shifts | next quote change after measured owned-selection or public-flow change | lead/lag with backward and decoy windows | at least 50 independent changes and flat pretrends | quote-surface timing; no literal front-running |

### 5.3 HMP-specific measurement

HMP's empirically accessible implications should be tested as a joint ladder:

1. price experiments are more correlated than a clock-preserving independent
   null;
2. preperiod routing feedback has a measurable signal-to-noise ratio;
3. higher preperiod SNR predicts more correlated subsequent price experiments;
4. correlated pairs have a larger omitted-rival-price elasticity wedge; and
5. the wedge predicts persistent benchmark-relative premiums.

Define the preperiod routing-information SNR before the outcome window:

`abs(mean selection response to a quote change) / residual standard deviation`.

Use sample splitting or cross-fitting so the same observations do not define
SNR and test its consequences. Report the continuous interaction first; any
high/low visualization uses a threshold frozen from the training sample.

The pairwise choice comparison is:

```text
omitted:    logit Pr(i over j) = pair/model/time controls + beta_o * log(p_i)
controlled: logit Pr(i over j) = pair/model/time controls + beta_r * log(p_i / p_j)
wedge:      beta_o - beta_r
```

Provider prices are not randomized. The cap experiment identifies the causal
effect of eligibility on this project's routing, not the causal effect of a
provider changing its posted price or the learning process that generated it.

### 5.4 Brown--MacKay and benchmark segmentation

Estimate price levels, price-response hazards, routing elasticity, and quote
firmness separately by:

- quote distance from author/model-provider price;
- quote distance from the cheapest current compatible provider;
- fast versus slow update cadence measured strictly in the preperiod;
- public provider type; and
- request shape.

The main specification includes model-by-time fixed effects. A provider's
cadence classification must be frozen using an earlier window and may not be
updated using the event being explained. Report continuous update intensity in
addition to fast/slow labels.

## 6. Program C: live router price-exponent measurement

### 6.1 Parameter

For a fresh-session default request with compatible provider menu `C`, define
the primary price-only choice model

`Pr(Y=i | C,x,t) = exp(-eta * log q_i(x,t)) / sum_j exp(-eta * log q_j(x,t))`,

where `q_i(x,t)` is the frozen request-shape all-in public quote. Estimate
`eta`, rather than treating `eta=2` as known.

Only fresh-session default assignments enter the primary fit. Exclude sorted,
pinned, ordered, cap-restricted, sticky, and outcome-blinded study rows.
Candidate-menu coverage is a first-class outcome. Provider-name outcomes are
joined to the minimum compatible provider-level quote and marked endpoint
ambiguous when necessary.

### 6.2 Models and benchmarks

Score the following on a chronological holdout:

- uniform routing, `eta=0`;
- inverse-price routing, `eta=1`;
- documented shadow benchmark, `eta=2`;
- fitted global `eta`;
- fitted request-shape-specific exponents; and
- a secondary quality-adjusted conditional logit with lagged public latency,
  reliability, rate limiting, and provider effects.

The price-only model is the interpretable router-price exponent. The
quality-adjusted model is a predictive decomposition, not a replacement
definition.

### 6.3 Live windows

Publish estimates for:

- trailing 24 hours, only when support gates pass;
- trailing 7 complete days;
- trailing 28 complete days;
- expanding history since the study start; and
- a secondary exponentially weighted estimate with a frozen 48-hour half-life.

For each window report:

- `eta_hat` and profile-likelihood 95% interval;
- model-day block-bootstrap interval;
- number of assignments, successes, covered choices, models, providers, and
  independent blocks;
- candidate coverage and failure rates;
- price-dispersion and selected-provider concentration diagnostics;
- held-out log loss, multiclass Brier score, top-one accuracy, and cost regret;
- loss differences versus `eta=0`, `eta=1`, and `eta=2`; and
- the exact HF revision and Git commit.

### 6.4 Support gates

Do not display a numeric live exponent unless the window has:

- at least 200 covered independent default choices for an aggregate estimate;
- at least five models and five selected providers;
- at least 100 independent model-shape blocks;
- at least 90% candidate-menu coverage;
- an interquartile range of within-menu log quote ratios of at least 0.05; and
- no selected provider contributing more than 60% of covered choices.

A provider-, model-, or shape-specific exponent needs at least 200 covered
choices in that stratum and 30 independent blocks. Otherwise publish
`status=insufficient_support`, not a point estimate.

### 6.5 Uncertainty and drift alerts

The profile-likelihood interval is primary. The block bootstrap clusters the
entire randomized model-shape block and is the dependence-robust audit. Never
treat individual requests from one block as independent.

A live drift alert requires all of:

- absolute difference of at least 0.5 between adjacent nonoverlapping seven-day
  estimates;
- a block-bootstrap interval for the difference excluding zero;
- support gates passing in both windows; and
- the condition appearing in two consecutive remote analyses.

The alert says the owned-account price sensitivity changed. It is not a router
policy announcement or causal attribution.

### 6.6 Critical-memory link

The empirical input to the critical-memory theory is a time-varying exploration
or low-price selection probability, not the price exponent alone. For each live
window publish both:

- fitted `eta`; and
- implied selection probability of the cheapest provider for fixed reference
  menus with two, three, and five providers and frozen price ratios.

Feed those probabilities into the critical-memory frontier as a sensitivity
analysis. Do not substitute a provider's observed cut share for the router's
exploration probability.

## 7. GitHub Actions design

### 7.1 Workflows

Add these workflows after their collectors and tests exist:

| Workflow | Trigger | Concurrency | Purpose |
|---|---|---|---|
| `paid-price-response.yml` | scheduled every four hours during a fixed campaign; manual dispatch is preflight-only | `randomized-routing-probes`, no cancellation | repeated-choice and memory blocks |
| `price-event-probes.yml` | trusted dispatch from public capture plus hourly recovery poll; manual dispatch is preflight-only | `randomized-routing-probes`, no cancellation | event-wave planning and paid execution |
| `price-tests-online.yml` | every six hours and successful `compact` completion | `price-tests-online`, cancel stale runs | monitoring tables and figures |
| `live-router-exponent.yml` | every six hours and successful `compact` completion | `live-router-exponent`, cancel stale runs | rolling exponent and predictive scores |
| `price-experiment-release.yml` | successful `compact` completion plus sample-only gate | one group per study, no cancellation | marker-first immutable confirmatory release |

Do not enable the paid schedules merely by merging the files. Require repository
variable `ORCAP_PAID_PRICE_STUDIES_ENABLED=true`, a code-enforced campaign
window, and the dedicated secret. A skipped disabled workflow should not count
as a remote-health failure until activation.

### 7.2 Plan-first jobs

Every paid workflow has separate `plan` and `execute` jobs.

The `plan` job:

1. checks out an exact commit;
2. fetches/fixes the public candidate menu;
3. applies eligibility and budget rules;
4. materializes all intended assignments before outcomes;
5. computes a SHA-256 manifest over candidates and assignments;
6. uploads an assignment-only artifact with at least 90-day retention; and
7. exposes only the manifest hash and total conservative cap to the next job.

The `execute` job runs only after successful remote upload of the plan. It
downloads and verifies the artifact, rechecks the campaign/daily spend cap,
sends exactly the planned tasks, and uploads redacted attempts with `if:
always()`. It may not regenerate assignments.

For a multiwave event, the trigger plan freezes wave times and randomization.
Each wave separately freezes its current menu before requests and appends a
hash-linked wave plan. A menu change can make a wave ineligible; it cannot
change its assigned arm or target time.

### 7.3 Scheduling and overlap

All owned OpenRouter studies using the same account share
`group: randomized-routing-probes` and `cancel-in-progress: false`.

Before activating recurring price studies:

- H96 must be complete;
- H95 must have reached and released its fixed horizon or use a separate
  isolated account;
- obsolete/default-only paid monitoring must be disabled or folded into the
  new repeated-choice study; and
- remote preflight runtime must show the job fits inside a 45-minute timeout
  with at least 50% margin.

Record scheduled, queued, job-start, plan-upload, request-start, and
request-finish timestamps. GitHub cron time is not the observation time.

### 7.4 Intraday data assembly

Add both paid workflows to `scripts/assemble_artifacts.sh`. Increase their
artifact retention to 14 days. Nightly `compact.yml` remains the only writer of
raw/curated study tables to the authoritative HF dataset.

The online-analysis workflows may hydrate the pinned HF revision and overlay
successful artifacts from the previous 48 hours in a local directory. They
must record `source_mode=hf_plus_intraday_artifacts` and the contributing
GitHub run IDs. Formal releases use only a compacted immutable HF revision.

### 7.5 Secrets and permissions

Required secrets and tokens:

- `OPENROUTER_PRICE_EXPERIMENT_KEY`: paid requests only;
- `HF_TOKEN`: private dataset and private Space;
- built-in `GITHUB_TOKEN`: artifact/run reads and trusted workflow dispatch.

Collectors get `contents: read` and the minimum Actions permission needed to
download or dispatch. No workflow logs a request body, secret, raw response, or
full generation record.

## 8. Hugging Face data and publication design

### 8.1 Durable tables

Add or extend these partitioned tables:

| Table | Layer | Primary key | Contains outcomes? |
|---|---|---|---|
| `price_experiment_candidates` | curated | `study_id, block_id, provider_key` | no |
| `price_experiment_assignments` | curated | `study_id, task_id` | no |
| `price_event_registry` | curated | `event_id` | no paid outcomes |
| `price_event_wave_plans` | curated | `event_id, wave_id, task_id` | no |
| `router_route_attempts` | curated, existing | `source, event_id` | yes, redacted |
| `online_price_test_snapshots` | analysis | `analysis_run_id, test_id, window_id` | aggregates |
| `router_exponent_estimates` | analysis | `analysis_run_id, window_id, stratum_id` | aggregates |
| `router_exponent_scores` | analysis | `analysis_run_id, window_id, model_spec` | aggregates |
| `paid_spend_ledger` | curated | `study_id, task_id` | cost only |

Partition by UTC `dt`. Use immutable run files before compaction and deterministic
deduplication keys during compaction. A duplicate task ID with inconsistent
assignment or cost is a hard integrity failure.

### 8.2 Analysis outputs

Every online run writes:

- Parquet estimates and support diagnostics;
- a compact JSON status file;
- PNG/PDF figures generated from the same aggregate table;
- `analysis_source.json` with HF revision and intraday run IDs; and
- a claim-boundary string.

Formal releases additionally contain the frozen input manifest, row counts,
hashes, test configuration, tables, figures, manuscript-ready paragraph, and a
machine-readable promotion decision. A release must be immutable and
idempotent.

### 8.3 Dashboard

Publish aggregate-only HTML to a private HF Space, preferably a dedicated
`t4run/openrouter-price-monitor` Space rather than overloading the paper memo.
Show:

- data freshness and workflow health;
- cumulative and last-24-hour spend;
- candidate coverage, failures, and selected-provider concentration;
- live exponent with support status and intervals;
- `eta=0/1/2/fitted` held-out loss comparison;
- event-time selection, latency, and failure curves;
- synchronization and provider-pair concentration;
- benchmark/cadence segmentation; and
- explicit monitoring-versus-confirmatory badges.

Never publish request references, task-level selected providers, exact session
hashes, prompts, completions, or API metadata to a public Space.

## 9. Analysis modules

Implement shared logic rather than duplicating H96 functions:

- `src/orcap/experiments/price_response.py`: eligibility, deterministic
  assignments, budget, and request execution;
- `src/orcap/experiments/price_events.py`: trigger detection, event registry,
  and wave planning;
- `src/orcap/analysis/router_exponent.py`: common choice-model fitting,
  intervals, windows, and scoring;
- `src/orcap/analysis/price_tests_online.py`: P1--P9 monitoring panel;
- `src/orcap/analysis/price_experiment_release.py`: fixed-horizon release and
  manifest generation; and
- `src/orcap/price_monitor.py`: aggregate HTML rendering.

Refactor the tested H96 `fit_eta`, probability, chronological split, and policy
audit into the common exponent module without changing H96's frozen result.
Keep a compatibility wrapper so the original H96 analyzer reproduces its
existing outputs byte-for-byte where formatting permits.

## 10. Inference and multiplicity

Predeclare one primary outcome and one primary inference method per study.

- Repeated-choice primary: covered default-choice log loss and fitted global
  exponent; profile likelihood with block-bootstrap audit.
- Eligibility primary: selected-provider indicator under top-two versus loose
  cap; finite-population randomization inference within blocks.
- Event primary: moving-provider default selection in W0--W2 relative to
  matched controls; model-day clustered event-study interval.
- HMP primary: preperiod-SNR interaction with subsequent synchronization;
  model-day clustered coefficient with leave-one-provider-pair-out audit.
- Memory primary: same-provider repeat probability for repeated versus fresh
  histories; within-block randomization inference.

Use Holm correction within each frozen confirmatory family. Secondary outcomes
are labeled and do not rescue a failed primary. The live monitor reports effect
sizes and support, not a continuously refreshed confirmatory verdict.

## 11. CI and validation

### 11.1 Unit and property tests

Add tests for:

- deterministic candidate selection and seed replay;
- exact arm counts and assignment probabilities;
- cap arms admitting exactly the intended provider set;
- no assignment construction after any outcome access;
- plan hash verification and plan/attempt one-to-one joins;
- duplicate task rejection and idempotent retry behavior;
- campaign, per-run, daily, and total budget failures before a request;
- late-wave suppression and no time-bin reassignment;
- privacy rejection for prompts, content, raw bodies, and secrets;
- correct exclusion of all blinded study IDs;
- synthetic recovery of known exponents and profile intervals;
- chronological split and block-bootstrap clustering;
- omitted-rival-price bias under a planted correlated-price DGP;
- null calibration for circular shifts and randomized eligibility arms;
- H96 backward compatibility; and
- empty/thin/support-failure behavior returning status rather than a number.

### 11.2 Workflow tests

Extend `tests/test_remote_pipeline_health.py` to assert:

- every paid workflow shares the paid concurrency lock;
- manual dispatch is no-spend preflight only;
- plan artifacts upload before the execution job;
- outcome artifacts upload with `if: always()`;
- all paid workflows are in `assemble_artifacts.sh`;
- per-run and campaign caps are passed explicitly;
- the remote watchdog includes every enabled workflow; and
- analysis workflows use pinned HF revisions for formal releases.

### 11.3 Synthetic end-to-end fixture

Build a small two-model fixture with:

- a known inverse-price exponent;
- one correlated provider pair;
- a known cut event and delayed selection response;
- one stale cheap provider with elevated failure;
- one provider absent from the public menu; and
- one delayed/missing assignment.

The end-to-end test must recover the exponent within tolerance, preserve the
event-time bins, flag missing coverage, and reproduce the release manifest.

### 11.4 No-spend remote acceptance

Before paid activation, a manual Actions run must demonstrate:

- candidates and assignments written and uploaded;
- zero `router_route_attempts` rows;
- no OpenRouter generation calls;
- budget and privacy checks pass;
- artifact assembly finds the new workflow;
- nightly compaction publishes the assignment tables to HF; and
- the watchdog sees a fresh success and table-level HF freshness.

## 12. Deployment and promotion gates

### Phase 0: finish H96

Deliverables:

- immutable H96 artifact set;
- runtime and spend audit;
- selected-provider menu coverage;
- explanation for every failed or missing task; and
- decision on request count per future job.

Gate: no frozen H96 protocol deviation and no unresolved privacy or billing
discrepancy.

### Phase 1: common contracts and CI

Deliverables:

- shared exponent module;
- paid candidate/assignment/event schemas;
- deterministic planners;
- budget ledger; and
- unit, workflow, and synthetic end-to-end tests.

Gate: full repository tests pass and H96 compatibility passes.

### Phase 2: remote no-spend preflight

Deliverables:

- disabled-by-default workflows;
- remote assignment-only artifacts;
- nightly HF compaction; and
- health/dashboard dry run.

Gate: two consecutive remote preflights and one compaction succeed without a
paid call.

### Phase 3: canary

Deliverables:

- one-model, one-shape plan-first paid block;
- cost and privacy audit; and
- generation metadata/quote join audit.

Gate:

- realized spend no greater than `$1.00`;
- 100% assignment-plan integrity;
- at least 90% public-menu provider coverage;
- no payload leakage;
- no unexplained duplicate or unplanned request; and
- at least 90% of successful generation records resolve selected provider,
  cost, and token counts.

### Phase 4: seven-day discovery

Deliverables:

- repeated-choice, cap, pin, and history panels;
- first live exponent dashboard; and
- first event-wave feasibility report.

Gate:

- at least 1,000 covered fresh default choices;
- at least 20 price-changing provider pairs;
- all budget and source-health checks remain green;
- no provider exceeds 60% of selected choices; and
- event timing is adequate for at least 80% of intended W0--W2 waves.

### Phase 5: fixed confirmation

Freeze sample horizon, primary family, covariates, matching, and release code
before outcomes. Recommended first horizon:

- 3,000 covered fresh default choices;
- 60 clean cut events and 60 matched controls;
- at least 20 models and 20 moving providers;
- no provider pair above 25% of synchronization events; and
- at least 28 complete calendar days.

Stop at the first chronological prefix satisfying all sample-only gates. Release
once regardless of sign. Do not stop on a live exponent, p-value, or favorable
event path.

## 13. Remote health and failure recovery

Extend `remote_health.py` beyond dataset-head freshness. Check:

- latest actionable run for each enabled workflow;
- table-level latest `run_ts` on HF;
- expected versus observed assignment and attempt counts;
- last-24-hour and campaign spend;
- missing selected-provider/cost/token metadata;
- candidate coverage;
- artifact age relative to nightly compaction;
- event-wave lateness; and
- latest dashboard revision.

Failure policy:

- source-health failure: write candidate/support rows, send no paid requests;
- plan-upload failure: send no requests;
- budget-ledger failure: send no requests;
- partial request execution: retain ITT assignments, do not backfill unless a
  replacement rule was preregistered;
- missing generation metadata: mark unknown and never infer selected provider
  from the requested provider;
- compaction failure: retain Actions artifacts and retry idempotently the next
  night;
- dashboard failure: preserve analysis tables and fail publication without
  rerunning the statistical result; and
- HF outage: buffer artifacts, send no new event wave if the daily spend ledger
  cannot be reconstructed.

## 14. Definition of done

The program is operationally complete when:

1. no workstation process is required;
2. paid plans are committed remotely before requests;
3. secrets and payloads never enter artifacts or logs;
4. per-task, per-run, daily, campaign, and platform caps all exist;
5. public menus, assignments, attempts, and spend compact nightly to the private
   HF dataset;
6. online price tests and live exponent estimates run on schedule with explicit
   support and claim boundaries;
7. a private HF dashboard shows freshness, spend, exponent, predictive loss,
   event paths, and synchronization concentration;
8. remote health detects workflow and table-level staleness;
9. the discovery and confirmatory samples are disjoint and revision-pinned;
10. formal releases occur once at sample-only gates regardless of sign; and
11. H81/H95/H96 frozen estimands and outcome boundaries remain unchanged.

## 15. Implementation checklist

1. Audit the completed H96 run and determine a safe requests-per-job limit.
2. Write preregistrations for `openrouter-price-response-v1` and
   `openrouter-price-event-v1`.
3. Add candidate, assignment, event, wave, and spend schemas.
4. Refactor the H96 exponent code into a backward-compatible common module.
5. Implement deterministic repeated-choice and event-wave planners.
6. Implement daily/campaign ledger reconstruction from HF plus intraday
   artifacts.
7. Add plan-first and execution jobs with disabled-by-default workflows.
8. Add workflows to artifact assembly and remote health.
9. Implement P1--P9 online analyses and support-only status outputs.
10. Implement rolling/expanding exponent estimation and drift diagnostics.
11. Add private HF Space rendering from aggregate outputs.
12. Run full local CI and the synthetic end-to-end fixture.
13. Run two remote no-spend preflights and confirm nightly HF publication.
14. Run the `$1.00` canary and audit privacy, cost, timing, and coverage.
15. Activate the seven-day discovery only after H95/H96 isolation gates pass.
16. Freeze, execute, and release the disjoint confirmatory campaign.

## 16. Deployment status (2026-07-19 UTC)

Implemented on `agent/paid-price-monitor`:

- deterministic, hashed response and event-wave planners;
- exact rectangular-cap validation with explicit nonseparability;
- plan, candidate, assignment, event, wave, attempt, and spend contracts;
- fail-closed source-health, dedicated-key, campaign-window, duplicate-task,
  manifest, and run/day/campaign budget checks;
- rolling/expanding inverse-price exponent estimation with profile and
  whole-block bootstrap intervals, predictive scores, and publication support
  gates;
- revision-pinned P1--P9 online registry using the existing H2, H13, BM1, H42,
  H46, H93, H94, and H97 analyses;
- plan-first GitHub Actions for response and event experiments, with manual
  dispatch guaranteed no-spend and schedule execution behind separate response
  and event feature flags;
- six-hour online-analysis and live-exponent workflows, artifact assembly,
  private HF dataset publication, private HF Space dashboard publication, and
  workflow/table-level remote health;
- preregistrations and unit, randomized-property, workflow, privacy,
  fail-closed, and synthetic end-to-end tests.

The local live-menu preflight observed 14 eligible endpoint rows for
`deepseek/deepseek-v3.2`, produced 16 deterministic assignments, and placed a
conservative total cap of `$0.000772764` on the full block. It sent no inference
request.

Paid activation remains intentionally closed. H95 is still collecting under
the shared `randomized-routing-probes` concurrency channel, the dedicated
`OPENROUTER_PRICE_EXPERIMENT_KEY` secret has not been provisioned from the
existing non-exportable GitHub secret, and the response/event campaign dates
remain unset. These are promotion gates rather than missing implementation.
The release workflow remains the existing marker-first confirmatory machinery;
the discovery v1 studies cannot be inserted into it. A new v2 study ID,
preregistration, and frozen gate are required before confirmatory release code
is registered.
