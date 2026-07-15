# H84/H85 preregistration: stale-quote adverse selection and capacity enforcement

Frozen: 2026-07-15T13:54:48Z

Status: design frozen before computing any H84 stale-quote/onset contrast or
model coefficient. The H82 event paths, Brown--MacKay cadence results, and
their limitations were already observed and motivated this study. H84 is
therefore a retrospectively preregistered discovery analysis, not a pristine
confirmatory test. H85 applies the same code and estimands to a disjoint
future-only holdout and is the confirmatory study.

## Question and mechanism

Does an old, relatively cheap public quote predict which same-model endpoint
will become capacity constrained at the next public router snapshot?

The mechanism is quote-surface adverse selection. A provider posts a money
price that changes more slowly than hidden capacity. If the quote becomes cheap
relative to contemporaneous rivals, routing can load onto it until the router
records rate limiting. This is the inference-routing analogue of stale
liquidity: the displayed quote remains visible, but deliverability deteriorates
before the money price adjusts.

This is sharper than asking whether a rate-limit event coincides with lower
successful share. Every predictor is measured before the onset, and every case
is compared only with endpoints for the same model at the same public
snapshot. The design therefore absorbs model demand and common clock shocks.
It still does not randomize prices, demand, capacity, or router selection.

## Samples and separation

- **H84 discovery:** public endpoint observations no later than
  `2026-07-15T11:33:02Z`, the immutable H82 discovery endpoint.
- **H85 confirmation:** observations at or after `2026-07-15T12:00:00Z`.
- The 26 minute 58 second gap between samples is unused.
- H84 observations never enter H85 estimates, standardization, model fitting,
  intervals, or plots.
- H85 reveals sample counts and support diagnostics before release, but no
  case/control outcome contrast, coefficient, predictive score, or event path.

## Canonical public panel

Deduplicate `congestion_intraday` and `event_bursts_congestion` on
`run_ts, model_permaslug, endpoint_uuid, provider_name`, preferring the burst
row on an exact tie. Parse `run_ts` in UTC. Within each endpoint, two
observations are contiguous only when separated by more than zero and at most
10 minutes.

The endpoint is at risk at snapshot `t` only when:

1. its current rate-limited count is zero;
2. it is not currently deranked;
3. its current completion price is finite and strictly positive;
4. current successes are observed;
5. the next endpoint observation is contiguous; and
6. the next observation has a finite success and rate-limit count.

The next-snapshot high-capacity event uses the H82 threshold without change:

- next rate-limited count at least five;
- next rate-limit share at least 20%;
- next success plus rate-limited count at least ten; and
- next state not displayed as deranked.

## Pre-onset quote state

All covariates use snapshot `t` or earlier.

### Observed quote age

For each endpoint, start a new quote spell on first observation, after any gap
above 10 minutes, or when the completion price changes beyond absolute
tolerance `1e-12` and relative tolerance `1e-9`. `quote_age_hours` is elapsed
time since the start of the current continuously observed spell. It is a lower
bound on true quote age because the panel begins after some quotes were posted.
Record `spell_left_censored = 1` for spells beginning at the endpoint's first
panel observation and zero after an observed price change.

The age feature is `log_quote_age = log1p(quote_age_hours)`.

### Relative cheapness

Within each model-snapshot risk set, compute

`relative_log_price = log(endpoint completion price) - median(log price)`

and define `cheapness = -relative_log_price`, so positive values mean cheaper
than the contemporaneous model median.

The primary adverse-selection feature is

`stale_cheap = log_quote_age * cheapness`.

This continuous interaction was chosen before inspecting its case/control
distribution. No quantile, threshold, or sign-dependent recoding is allowed.

### Secondary pre-onset state

- `log1p_success = log1p(current successful requests)`;
- current displayed capacity load, `recent_peak_rpm / capacity_ceiling_rpm`,
  when both fields make it finite;
- `log1p_capacity_ceiling_rpm`;
- current within-model successful-request share; and
- an indicator for a left-censored quote spell.

Provider cadence class is a secondary bridge to Brown--MacKay. Freeze it using
only positive completion-price changes in the first 70% of the H84 discovery
price-event timeline. Intraday and daily are `fast`; weekly, episodic, and
inactive are `slow_or_unobserved`. Cadence is never used to construct the
primary stale-quote feature and its coefficient is not a causal technology
effect.

## Forward same-model choice sets

At each model and snapshot `t`, retain all at-risk endpoints with complete
`log_quote_age`, `cheapness`, and `stale_cheap`. A forward choice set is valid
only when:

1. at least two endpoints remain;
2. exactly one endpoint has a high-capacity event at its next contiguous
   snapshot; and
3. no second endpoint for that model has a high event within the same next
   snapshot.

The unique endpoint that binds next is the case. Every other at-risk endpoint
is a contemporaneous control. The choice-set identifier is a hash-stable string
of model and current `run_ts`. The cluster is model by UTC date.

## Frozen estimands

### H84/H85 primary descriptive contrast

For each valid choice set, subtract the mean rival `stale_cheap` from the case
value. Report the equal-choice-set mean and a 95% model-day cluster-bootstrap
interval using 10,000 deterministic draws and seed `84850715`.

The directional hypothesis is positive: the endpoint that binds next is older
and cheaper in interaction than its same-model rivals.

Also report the case-minus-rival contrasts for `log_quote_age`, `cheapness`,
`log1p_success`, capacity load, and relative successful share. These are
mechanism diagnostics, not co-primary outcomes.

### Conditional hazard model

Within valid choice sets, standardize continuous covariates using the training
choice sets only. Fit conditional logits with one case per set:

- **surface baseline:** `cheapness + log1p_capacity_ceiling_rpm`;
- **stale-quote model:** baseline plus `log_quote_age + stale_cheap +
  spell_left_censored`;
- **operational model:** stale-quote model plus `log1p_success + capacity_load`.

The stale-quote coefficient and odds ratio in the middle model are secondary.
The operational model tests whether observed load attenuates the stale-quote
association; conditioning on load may block the proposed mechanism and is not
the headline specification.

### Frozen temporal prediction test

Order valid choice sets by their current timestamp. Train on the first 70% and
evaluate on the final 30%, with all rows from a choice set kept together. For
each fitted conditional logit, convert linear scores to a softmax probability
within the held-out choice set. Report:

- mean negative log probability assigned to the true case;
- top-one case accuracy; and
- mean reciprocal rank of the case.

The predictive hypothesis is that the stale-quote model has lower held-out log
loss than the surface baseline. The operational model is diagnostic.

## Falsification and sensitivity

1. **Backward temporal placebo.** On the same at-risk rows, form otherwise
   identical same-model choice sets in which exactly one endpoint had a high
   event at the immediately previous contiguous snapshot. Report its
   case-minus-rival `stale_cheap` contrast. The forward contrast must exceed
   the backward contrast for a directional one-step-ahead interpretation.
2. **Label permutation reference.** Within each choice set, uniformly permute
   the case label using 10,000 deterministic draws. This is an association
   reference, not randomization-based causal inference.
3. **Loading diagnostic.** Report case-minus-rival current successful volume,
   successful share, and the prior one-step change in successful share. A
   positive loading difference supports the proposed adverse-selection path
   but also documents endogeneity.
4. **Price-stickiness diagnostic.** Report the share of cases whose completion
   price is unchanged from `t` to the next snapshot.
5. **Support sensitivity.** Report equal-model weighting and leave-one-provider
   and leave-one-model-out primary contrasts.
6. **Age sensitivity.** Repeat the primary contrast after removing
   left-censored spells and after winsorizing `quote_age_hours` and cheapness at
   their choice-row 1st and 99th percentiles.
7. **Cadence bridge.** Report case versus rival slow-or-unobserved cadence share
   only on provider names present in the frozen cadence table. This is a
   secondary descriptive bridge, not a test of algorithm adoption.

## H84 interpretation

H84 is released regardless of sign once the code and tests implement this
document. It may support a one-step-ahead stale-quote hazard association. It
cannot support a causal adverse-selection, router-intent, front-running,
collusion, or welfare claim because it reuses a discovery panel that motivated
the hypothesis and because latent endpoint quality and capacity remain
unobserved.

## H85 release and stopping rule

Before all sample-only gates pass, H85 may publish only:

- source span and latest timestamp;
- counts of at-risk rows, forward candidate sets, valid choice sets, and
  backward-placebo sets;
- complete days, models, providers, and provider concentration;
- missingness and choice-set size distributions; and
- deterministic data/assignment integrity checks.

It must not publish feature distributions split by case status, contrasts,
coefficients, odds ratios, predictive metrics, paths, intervals, p-values, or
signs.

H85's first release requires all of:

- at least 28 complete future days;
- at least 500 valid forward choice sets;
- at least 20 models and 20 case providers;
- no provider contributes more than 20% of cases;
- at least 150 valid backward-placebo sets;
- at least 70% of forward rows have finite capacity load;
- at least 70% of case providers map to the frozen cadence table; and
- exact one-case-per-set and future/discovery separation checks pass.

At the earliest chronological prefix satisfying every sample-only gate, freeze
the release cutoff and publish all frozen estimates whether they confirm or
reject the hypotheses. Later data cannot replace that first confirmatory cut.
There is no significance-based stopping.

## Claim boundary

The strongest permitted claim is: conditional on a model and public snapshot,
pre-onset quote age and relative price predict which displayed endpoint records
high rate limiting next. Even a successful H85 result does not show that a
provider strategically left a stale quote, observed incoming flow, traded
ahead of it, or caused the router to allocate inefficiently. Those stronger
claims require randomized quote/capacity commitments or private router logs.
