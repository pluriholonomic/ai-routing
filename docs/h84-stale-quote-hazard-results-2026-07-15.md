# H84 result: stale cheap quotes do not predict the next capacity event

Frozen discovery cutoff: `2026-07-15T11:33:02Z`

Evidence class: retrospectively preregistered discovery. The design was frozen
before computing any H84 stale-quote/onset contrast or conditional-logit
coefficient, but after H82 and the Brown--MacKay cadence results motivated the
question. H85 applies the unchanged design to a disjoint future-only sample.

## Bottom line

H84 rejects its preregistered directional hypothesis. Among providers offering
the same model at the same five-minute snapshot, the endpoint that records a
high-intensity rate-limit event next is not older and cheaper in interaction
than its rivals. The case-minus-rival `stale_cheap` contrast is **-0.118** with
a model-day cluster-bootstrap 95% interval **[-0.181, -0.056]** across 1,227
choice sets. The one-sided within-choice-set permutation reference for the
preregistered positive direction is `p = 1.000`.

The backward temporal placebo is also negative, **-0.083** with interval
**[-0.140, -0.031]**. The forward contrast therefore does not exceed the
backward contrast. Adding quote age and its interaction with cheapness also
slightly worsens held-out prediction relative to the price-and-capacity-surface
baseline.

The strongest supported interpretation is negative: this public panel does not
support the inference-market analogue of cheap stale liquidity being picked
off into a capacity event. The cases instead look like relatively expensive,
smaller-capacity endpoints already operating at a higher utilization ratio.
That pattern is more consistent with a queueing or thin-capacity margin than a
stale-price adverse-selection channel. Because H84 is observational and the
backward placebo is nonzero, it does not identify the cause of that pattern.

## Sample and frozen estimand

- 503,321 canonical endpoint snapshots over 7.66 days;
- 277,179 at-risk endpoint rows;
- 1,227 valid forward same-model choice sets;
- 1,144 backward-placebo choice sets;
- 24 models and 44 case providers;
- 144 model-day clusters in the primary forward interval; and
- exactly one next-snapshot high-intensity rate-limit case in every retained
  forward choice set.

The primary feature is

`stale_cheap = log1p(observed quote age in hours) * cheapness`,

where cheapness is minus the endpoint's log completion-price deviation from the
same-model snapshot median. Positive values mean an older, relatively cheaper
quote. Every covariate is observed at `t`; the case is the endpoint that first
meets the frozen high-rate-limit threshold at the next contiguous observation.

## Pre-onset contrasts

All values below are case minus the mean of contemporaneous same-model rivals.

| Pre-onset state | Contrast | 95% model-day cluster CI | Interpretation |
|---|---:|---:|---|
| stale x cheap | -0.118 | [-0.181, -0.056] | opposite the preregistered direction |
| log quote age | 0.0001 | [-0.0041, 0.0035] | no resolved age difference |
| cheapness | -0.147 | [-0.222, -0.076] | the next case is relatively more expensive |
| log1p current successes | -0.954 | [-1.173, -0.718] | the next case already has lower successful volume |
| endpoint successful share | -0.0619 | [-0.0847, -0.0407] | the next case is a smaller current flow destination |
| prior success-share change | 0.0024 | [-0.0010, 0.0056] | no resolved one-step loading trend |
| displayed capacity load | 0.422 | [0.126, 0.875] | the next case has higher utilization when observed |

Displayed capacity load is `recent_peak_rpm / capacity_ceiling_rpm`; its
contrast uses 869 choice sets with complete public fields. It is a diagnostic,
not a causal mediator estimate. Completion price remains unchanged into the
next snapshot for 99.92% of cases.

## Prediction and conditional choice

The frozen temporal split trains on the first 70% of eligible choice sets and
tests on the final 30% (609 training and 261 test sets after complete-case
restrictions).

| Conditional-logit score | Held-out log loss | Top-one accuracy | Mean reciprocal rank |
|---|---:|---:|---:|
| surface: cheapness + capacity ceiling | 1.42536 | 0.4368 | 0.6313 |
| surface + quote age + stale x cheap | 1.42594 | 0.4291 | 0.6277 |
| operational complete-case model | 1.43119 | 0.4176 | 0.6231 |

The stale-quote model worsens log loss by 0.00058 and worsens both ranking
metrics. Its standardized `stale_cheap` coefficient is -0.050 (standard error
0.098; odds ratio 0.951 per training-sample standard deviation). By contrast,
the surface model's standardized log capacity-ceiling coefficient is -1.327
(standard error 0.082; odds ratio 0.265), indicating that smaller displayed
capacity ceilings are a strong within-sample predictor of the next onset. This
is a predictive comparison, not a structural capacity estimate.

## Robustness and adverse evidence

- Winsorizing quote age and price leaves the primary contrast negative:
  -0.091, interval [-0.143, -0.041].
- Equal-model weighting gives -0.044.
- Every leave-one-provider-out estimate is negative, ranging from -0.140 to
  -0.072.
- Every leave-one-model-out estimate is negative, ranging from -0.137 to
  -0.061.
- Removing left-censored quote spells leaves only six choice sets in three
  clusters; the resulting +0.139 contrast has an interval crossing zero. This
  is too little support to overturn the main result and documents the panel's
  inability to observe the true birth of most long-lived quotes.
- Only 274 case sets map to a frozen Brown--MacKay cadence class. Within that
  restricted bridge, the case-minus-rival slow-or-unobserved share is zero, so
  the public cadence taxonomy does not explain the onset result.

## Claim boundary

H84 supports a one-step-ahead public-state association and a rejection of its
specified positive stale-cheap hypothesis in this discovery sample. It does
not establish that providers strategically choose stale quotes, that a router
causes rate limiting, that expensive or small providers are intrinsically
worse, or that any actor front-runs, colludes, or loses welfare. The nonzero
backward placebo and short seven-day sample are important limitations.

H85 remains the confirmatory test. Its code, estimands, directional hypothesis,
sample gates, and forced first-release rule are unchanged after observing H84.
The currently published source bundle ends before H85's `2026-07-15T12:00:00Z`
start, so H85 exposes zero post-cutoff rows and no outcome.

## Reproducibility

Run:

```bash
MPLCONFIGDIR=/tmp/mpl .venv/bin/orcap analyze --hypothesis h84 --out /tmp/h84
MPLCONFIGDIR=/tmp/mpl .venv/bin/orcap analyze --hypothesis h85 --out /tmp/h85
```

The authoritative summary is `h84_summary.json`; the analyzer also writes the
risk panel, forward and backward choice rows and contrasts, and PDF/PNG figure.

