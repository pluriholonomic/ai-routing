# H82 preregistration: capacity enforcement and within-model substitution

Version: 1.0  
Frozen: 2026-07-15 before inspecting any H82 post-event outcome path

## Question and claim boundary

Does a public, endpoint-specific rate-limit shock coincide with successful
request volume moving away from the constrained endpoint while its posted
price remains unchanged? This is the observable implication of short-run
capacity rationing that motivates capacity-certified routing.

H82 cannot identify the router's private score, request ordering, customer
identity, provider intent, front-running, welfare, or the effect of a capacity
certificate that has not been randomized. Rate limits are endogenous to load.
The primary result is therefore a within-model substitution event study. It
earns causal language only after every release gate below passes.

## Design-stage information already inspected

Before freezing this document, the treatment-side H68 audit showed 503,321
endpoint snapshots over 183.8 hours, 16,421 zero-to-positive rate-limit onsets,
and no contiguous derank onset or release. We inspected onset counts and the
distributions of the contemporaneous rate-limit count, rate-limit share, and
attempt proxy solely to choose a non-degenerate treatment threshold. We did
not inspect any lead, lag, successful-share, rival-volume, price, or capacity
outcome around those events. Threshold choice is consequently design-stage and
power-informed, not outcome-blind in the stronger randomized-trial sense.

## Observation and treatment

An observation is an endpoint snapshot keyed by canonical model, endpoint,
provider, and router timestamp. Targeted burst observations take precedence
over the regular congestion collector on exact key ties. Consecutive endpoint
observations are contiguous only when separated by at most ten minutes.

A **high-intensity enforcement onset** at time zero satisfies all of:

1. the preceding contiguous snapshot has zero recorded five-minute
   rate-limited requests;
2. the current snapshot has at least five rate-limited requests;
3. `rate_limited_5m / (success_5m + rate_limited_5m) >= 0.20`;
4. `success_5m + rate_limited_5m >= 10`;
5. the endpoint is not already displayed as deranked;
6. no other high-intensity onset for the same model lies within 60 minutes on
   either side; and
7. exactly one endpoint for the model crosses the high-intensity threshold at
   the event timestamp.

The negative-control onset uses the same contiguity, attempt, and non-deranked
requirements but has a positive rate-limit count and a rate-limit share no
greater than 0.05. A control is ineligible if a high-intensity model event lies
within 60 minutes. Control events are greedily thinned to one per model per
60-minute neighborhood without using outcomes.

## Event window and target population

The fixed grid is every five minutes from -30 through +60 minutes. The nearest
snapshot may fill a grid cell only when it lies within 2.5 minutes. The primary
pre-period is -30 through -5 minutes and the primary post-period is +5 through
+30 minutes; time zero is never an outcome. An event is complete with at least
four observed pre cells and four observed post cells.

The finite-sample estimand covers isolated, complete, high-intensity events on
the hot-model public panel. It does not cover low-volume models, private
eligibility, other accounts, or persistent derank spells.

## Outcomes

All outcomes are constructed before viewing estimates.

Primary outcomes:

1. focal endpoint successful-request share within model;
2. focal provider successful-request share within model; and
3. other-provider successful requests, measured as `log1p` volume.

Mechanism and accounting outcomes:

- focal endpoint, same-provider-other-endpoint, rival-provider, and total-model
  successful-request counts;
- focal attempted-request and successful-request shares;
- `log1p` model successful volume;
- log focal completion price; and
- `log1p` displayed capacity ceiling.

The additive raw-count decomposition must hold at every retained snapshot:

`model success = focal endpoint success + same-provider other-endpoint success
+ other-provider success`.

The mechanism-consistent signature is a focal endpoint or provider share
decline, an other-provider increase, approximately stable total-model volume,
and no contemporaneous focal price change. This signature is evidence of
observed substitution around enforcement, not proof that enforcement caused
the underlying demand shock.

## Estimation and falsification

For each outcome and event, subtract the mean of the six primary pre cells from
the mean of the six primary post cells. Report the event-weighted mean and a
95% cluster bootstrap interval, resampling model-day clusters with a fixed
seed. Report model-equal-weighted estimates as a support sensitivity.

Falsification and support diagnostics precede the primary estimates:

1. early-pre (-30 to -20) versus late-pre (-15 to -5) placebo contrast;
2. event-time coverage and missingness by relative time;
3. high-versus-low intensity comparison after nearest-neighbor matching within
   model using only pre-event log attempt volume, UTC hour, and calendar time;
4. leave-one-provider-out estimates;
5. winsorized raw-volume sensitivity at the event-level 1st and 99th
   percentiles; and
6. the exact additive flow-accounting residual.

No p-value is interpreted as randomization-based. Confidence intervals address
sampling variation under clustered resampling, not unobserved confounding.

## Gates and stopping rule

The descriptive analysis always reports. Causal wording is forbidden unless:

- at least 100 complete, non-overlapping high-intensity events remain;
- the panel spans at least 28 complete days;
- at least 20 models and 20 providers contribute events;
- no single provider supplies more than 20% of high-intensity events;
- the primary share outcomes have no material differential pretrend, defined
  as an absolute placebo contrast below 20% of the corresponding post
  contrast and a cluster interval containing zero;
- the high-minus-low matched contrast agrees in sign with the high-event
  estimate; and
- the accounting residual is below `1e-9` up to floating-point precision.

There is no significance-based stopping. The first analysis snapshot meeting
all gates is the confirmatory cut. Earlier snapshots remain explicitly
descriptive and power-gated. Thresholds, windows, outcomes, and gates do not
change after outcome inspection; any amendment is versioned and disclosed.

## Execution log and non-design corrections

- The first authoritative execution stopped before producing an estimate
  because DuckDB materialized large counts as Decimal-backed objects. Commit
  `72e5254` adds explicit numeric coercion and a Decimal regression test. No
  treatment, outcome, window, matching, or gate changed.
- The next local execution exposed a reporting defect in the raw additive
  decomposition. The identity held exactly at every jointly observed snapshot,
  but independently averaged components used different relative-time cells
  when the focal public count was missing. Commit `ebc4578` first restricted
  the event sample; this amendment completes the correction by computing every
  additive component on the same jointly observed pre and post cells. Primary
  share outcomes, matches, intervals, and release gates are unchanged.
