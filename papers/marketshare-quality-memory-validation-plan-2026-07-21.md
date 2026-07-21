# Validation plan: connecting routed share and quality to score memory

## 1. The missing empirical object

The current price-score paper is contemporaneous. For provider `i`, model `m`,
and block `t`, it writes owned first-choice probability as

\[
\Pr(Y_{mt}=i\mid \mathcal M_{mt})
\propto p_{imt}^{-\eta}\exp(a_{imt}),
\]

where the exact candidate menu is `M`, `p` is the public request-shaped quote,
and `a` is a reduced-form routing residual. The public panel identifies the
price-rule counterfactual with `a=0`; owned choices can estimate a current
relative `a`. Neither identifies a transition law for `a`.

The memory hypothesis begins only with a dynamic state equation such as

\[
a_{im,t+1}=\mu_{im}+\lambda_t+\rho a_{imt}
 +B_p z^p_{imt}+B_q z^q_{imt}+B_e z^e_{imt}+\xi_{imt},
\]

where `z^p` is lagged price history, `z^q` is lagged delivered quality, and
`z^e` is observable enforcement or eligibility state. This equation must be
estimated jointly with choices; a fitted contemporaneous provider fixed effect
cannot be relabeled as memory.

Three kinds of memory must remain distinct:

1. **Router-score memory:** past price, failure, latency, or fidelity changes a
   future routing score.
2. **Provider-learning memory:** providers use past rewards or rivals' prices
   when choosing future quotes.
3. **Harness or user memory:** an application persists with, or avoids, a
   provider after prior outcomes.

The critical-memory theorem concerns the first object conditional on a declared
state rule. The public quote panel is primarily informative about the second.
Owned account choices may mix the first and third unless the harness policy is
held fixed.

## 2. Outcomes

### Routed-share outcomes

- default-route first choice;
- attempted-provider order when available;
- completion provider and fallback indicator;
- owned token and request share by provider-model;
- price-only predicted share and score-adjusted predicted share;
- cumulative undercutter gain over horizons from 15 minutes through seven days.

These are owned-workload shares, not market-wide share.

### Quality outcomes

- success and fallback;
- time to first token, total latency, and throughput;
- tool-call and schema validity;
- exact or rubric-scored benchmark fidelity;
- truncation, refusal, and malformed-output rates;
- cost per successful, fidelity-qualified completion.

Latency and throughput must not stand in for fidelity. Minimal one-token probes
measure routing and availability; a lower-frequency prompt bank measures
delivered quality.

## 3. Frozen model classes

Compare four state models before looking at outcomes:

1. **No memory:** current menu, current enforcement, provider-model effects,
   block effects, and current observable quality only.
2. **Geometric memory:** EWMA state with half-life selected from a frozen grid.
3. **Finite-run memory:** state changes after `M` consecutive price or quality
   events, matching the critical-memory theory.
4. **Regime memory:** a small hidden Markov state with transition probabilities
   independent of the current choice error.

Use a frozen multiscale lag grid of 1, 4, 16, 48, 96, 288, and 672 fifteen-minute
blocks. Do not choose the memory family from in-sample fit. Primary comparison
is whole-day, whole-block out-of-sample log loss; secondary comparisons are
Brier score and calibration error.

## 4. Hypotheses and tests

### M0: no detectable score memory

**Hypothesis.** Conditional on the current exact menu, enforcement state,
provider-model effects, and current quality, lagged price and quality do not
improve future provider-choice prediction.

**Test.** Cross-fitted difference in log loss between the no-memory model and
the prespecified dynamic family. Cluster uncertainty by UTC day and model.
Require improvement in a held-out future week, not merely a likelihood-ratio
test on the training window.

### M1: quality memory

**Hypothesis.** A provider-specific failure, latency spike, or fidelity failure
reduces its future relative score and the penalty decays monotonically.

**Test.** Distributed-lag event study around owned quality shocks, with current
price/menu controls, provider-model and block effects, pre-trend leads, and an
unrelated-provider negative control. A public derank transition is a separate
event class. Observational events support prediction, not causality.

### M2: price-history memory

**Hypothesis.** Run length or cumulative depth of benchmark undercutting changes
future relative score after holding the current quote fixed.

**Test.** Match blocks with the same current quote and menu but different prior
undercut histories. Estimate the dynamic conditional-logit contrast and require
future-history leads to be null. Repeat within provider-model and around price
reversions. This is still observational unless a router exposes or randomizes
the history rule.

### M3: dynamic share-quality interaction

**Hypothesis.** The share gained from a contemporaneous cut is subsequently
attenuated after poor quality and sustained after good quality.

**Estimand.** For horizon `h`,

\[
\Gamma_{i,t,h}=\Delta_{i,t,h}(a_{t:t+h})-\Delta_{i,t,h}(0),
\]

where `Delta(0)` is the public price-only benchmark reset and `Delta(a)` uses
the dynamically predicted score. Report the cumulative owned-choice difference,
quality-qualified completions, and user cost. A negative `Gamma` is discipline;
a positive `Gamma` is amplification.

### M4: critical-memory transport

**Hypothesis.** The empirically supported score state has a finite effective
memory long enough to create the late-path gap in the theory.

**Test.** Map the fitted transition to an identified set for `(theta, M)` or an
EWMA half-life; construct provider-specific payoff triples from owned outcomes;
propagate uncertainty into `M*` and `M_c`. The transport claim passes only if
the empirical memory interval overlaps a theoretically consequential region
and the result survives whole-provider and whole-model leave-outs.

### M5: mechanism improvement

**Hypothesis.** A disclosed, quality-aware state rule improves quality-qualified
completion or user utility without increasing manipulation or provider
exploitability.

**Test.** Randomize only in an owned router or proxy among no memory, EWMA
quality memory, and finite-window quality memory. Compare user cost, fidelity,
fallback, concentration, and deviation gain with common random numbers. This
supports the designed router, not a claim about OpenRouter's hidden rule.

## 5. Data collection

### Layer A: high-frequency public state

Continue five-minute menu, enforcement, capacity-ceiling, derank, and rate-limit
captures. Materialize exact request-shaped quotes and provider eligibility at
each paid-probe block. Preserve provider-model identities and public state
transitions.

### Layer B: high-frequency owned routing

For each selected paid open-weight model, run 15-minute blocks containing:

- two default-route requests;
- one explicit price-sort request;
- provider pins and exclusion controls needed to recover eligibility and
  fallback;
- fresh session identifiers and fixed request shape.

The default and price-sort comparison identifies the contemporaneous score
layer. Pins and exclusions provide quality observations outside the endogenous
default-choice path. They do not manipulate OpenRouter's global memory.

### Layer C: lower-frequency quality bank

Every six hours, run a versioned prompt bank stratified across deterministic
reasoning, structured output, tool calls, long context, and ordinary chat.
Repeat the same prompts across eligible providers for a fixed model. Store only
redacted task IDs, hashes, scores, and telemetry in public artifacts; retain any
payload-bearing rows privately. Freeze evaluator rubrics and judge versions.

### Layer D: controlled-router experiment

Route the same request stream through an owned LiteLLM, Portkey, or Cloudflare
gateway implementation with randomized state rules. The arms are no memory,
EWMA quality memory at frozen half-lives, and finite-window quality memory at
frozen `M`. Provider prices remain those publicly offered. This is the causal
test of the proposed mechanism.

### Layer E: partner-log transport

Request anonymized router-side fields: request time, exact eligible endpoint
set, pre-choice score components, attempted order, completion/fallback, price,
quality/health update, enforcement transition, and score-update timestamp. No
prompt or user identifier is required. Partner logs are the only route to a
causal claim about an existing router's memory rule.

## 6. Identification and negative controls

- Hold the harness policy, model, prompt bank, and request shape fixed within
  randomized blocks.
- Condition on the exact candidate menu; never treat a public catalog entry as
  eligible merely because it exists.
- Use provider-model effects and UTC block effects; test provider-wide
  cross-model spillovers separately as a capacity mechanism.
- Include future price and quality leads. Predictive leads invalidate temporal
  ordering.
- Circularly shift histories within provider-model-day as a clock-preserving
  placebo.
- Use unrelated providers and unrelated models as negative controls.
- Report results with and without derank/rate-limit transitions; these may be
  mechanisms or confounders.
- Correct the frozen hypothesis family with Holm; do not promote a later lag
  after an earlier gate fails.
- Treat exact randomized-arm inference as causal. Label distributed-lag and
  natural-event estimates predictive or descriptive.

## 7. Support and release gates

### Contemporaneous score gate

Per model: at least 800 covered default choices, 100 blocks, seven days, three
selected providers, and 90% exact-menu coverage. Require positive held-out bits
per choice beyond price before fitting memory.

### Memory gate

Per model: at least 28 days, 30 independent price-history events, 30 quality or
enforcement shocks, three supported providers, and overlap in current price
across different histories. Require improvement over no-memory in a future-week
holdout and sign stability under whole-day and whole-provider leave-outs.

### Quality gate

At least 100 completed scored tasks per supported provider-model-task stratum,
with rubric reliability reported. Power simulation on the accumulated menu and
variance structure must precede any expansion of the prompt budget.

### Causal mechanism gate

At least 100 randomized blocks per memory arm, exact assignment integrity,
balanced model/task composition, and no cross-arm state leakage. Primary outcome
is quality-qualified completion per dollar; manipulation gain, fallback,
latency, concentration, and provider profit are mandatory secondary outcomes.

### Theory-entry gate

The memory result may enter the EC or ICML empirical spine only if:

1. a current score exists out of sample;
2. lagged history improves future score prediction;
3. the quality or price pathway has correct temporal ordering;
4. a randomized owned-router or partner-log design supports the transition;
5. the identified memory region changes a prespecified theoretical decision.

Failure at any gate is a result: it supports a contemporaneous score model or a
broader identified set, not a zero-memory point estimate.

## 8. Analysis and artifact architecture

- `score_memory_assignments`: assignment-only plans and randomized arm.
- `score_memory_attempts`: private request-level outcomes.
- `score_memory_menu_state`: exact public menu joined backward in time.
- `score_memory_quality`: redacted quality telemetry and rubric scores.
- `score_memory_panel`: private block-level analysis table.
- `score_memory_aggregate`: public coefficients, intervals, gates, and
  leave-out diagnostics.
- `score_memory_preregistration.json`: estimands, lag grid, model classes,
  families, seeds, and stop rule.

GitHub Actions should plan first, execute within a fixed budget, validate spend
and redaction, publish only aggregates to Hugging Face, and render a private
dashboard. Immutable dataset revisions and code commits must be stored in every
summary. The existing score monitor remains untouched until a separate protocol
and start timestamp are frozen.

## 9. Manuscript re-entry rules

- **EC:** add memory only as an empirically estimated dynamic score extension to
  the price-manipulation mechanism after the theory-entry gate.
- **ICML:** add a routing experiment only if the inferred memory interval maps
  into the critical region and a randomized or partner-log transition test
  passes. Otherwise the paper remains a standalone learning result.
- **NeurIPS:** implement all four memory families as transport tasks regardless
  of sign; the environment paper can report a failed connection without
  weakening its methodological contribution.

