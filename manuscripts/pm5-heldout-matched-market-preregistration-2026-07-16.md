# PM5 held-out matched-market calibration preregistration — 2026-07-16

## Status and purpose

This specification is frozen after the nine-date PM5 audit but before the
earliest-30-date panel exists. It answers the remaining reviewer criticism without
retuning SIM2: can a nonreactive public-menu benchmark calibrated to whole market
states, rather than a pooled endpoint menu, predict exact lagged-rival landings out
of time? The experiment is a future-gated validation design. It must not execute
or inspect a holdout landing outcome until 30 distinct quote dates are available.

The existing factor-1.25 global-menu statistic remains the confirmatory PM5
primary. This experiment is a separately labeled held-out mechanism comparison;
it cannot replace an unfavorable registered result.

## Immutable data split

1. Resolve one immutable Hugging Face dataset revision at run start.
2. Sort distinct observed quote dates and retain the earliest 30 only.
3. Dates 1--15 are the training period; dates 16--30 are the holdout period.
4. Later dates are continuation data and cannot enter this release.
5. Before date 30 exists, the analyzer may report only date counts, the future
   split rule, code version, and readiness. It may not load quote prices, construct
   PM5 events, fit a response parameter, or emit an outcome-bearing table.

The PM5 event definition is unchanged: consecutive snapshots at most 15 minutes
apart, exactly one observed mover, strictly prior same-model rival quotes, and
exact equality at the existing numerical tolerances.

## MM1: whole-market matched-menu probability

For every training or holdout event at prior timestamp `t-`, construct the focal
market's lagged state from its same-model rival endpoints. Construct candidate
decoy states from every other model observed at exactly `t-`. A candidate must
have at least as many endpoints as the focal rival-set size. No future snapshot,
model-family alias, interpolation, or nearest timestamp is admissible.

Each market state has five predeclared features, all computed before the mover's
new quote is used:

1. log endpoint count;
2. log median completion price;
3. log one plus interquartile-range divided by the median;
4. share of endpoints whose price is shared by another endpoint in that market;
5. indicator that at least two endpoints tie at the minimum.

Feature means and standard deviations are estimated from all model-timestamp
states in training dates 1--15 only. Zero-variance features receive scale one.
For each event, rank candidate markets by Euclidean distance in this standardized
feature vector, breaking ties by model ID, and retain the closest 20. If fewer than
20 are eligible, use all; fewer than five makes the event incomparable.

Within decoy market `j`, let `N_j` be its endpoint count, `H_j` the number of
endpoints exactly equal to the mover's realized new price, and `r_e` the focal
rival-set size. Its chance match probability is the hypergeometric probability of
at least one hit when drawing `r_e` endpoints without replacement from `N_j`.
The MM1 probability `q_e^MM` is the unweighted mean of this probability across
the retained decoy markets. Thus matching operates on whole market states;
endpoint multiplicity and within-market dependence are not destroyed by pooling.

Primary `k=20` is immutable. Fixed sensitivities use `k=10` and `k=50`, the same
minimum of five, and no feature or distance change. Sensitivities cannot promote a
claim when the primary fails.

## MR1: training-fitted excess-landing model

The nonreactive model is

`M0: Pr(Y_e=1) = q_e^MM`,

where `Y_e` is exact landing on any strictly prior same-model rival quote. The
nested persistent-excess model is

`M1: Pr(Y_e=1) = q_e^MM + rho * (1-q_e^MM)`.

Estimate the single `rho in [0,1]` by maximum likelihood using comparable training
events only. Neither the matching metric nor `rho` may be refit on the holdout.
Clip probabilities only for numerical log scoring at `1e-12`; do not alter the
reported probability or residual.

On dates 16--30 report:

- comparable events, models, providers, and largest model event/landing shares;
- observed exact-landing share, mean `q_e^MM`, and mean `Y_e-q_e^MM`;
- event-weighted Brier and log scores for M0 and the training-fitted M1;
- mean holdout log-score gain M1-minus-M0;
- model-cluster percentile bootstrap intervals with 20,000 draws and seed
  `20260718`, plus the full leave-one-model-out ranges, for both the residual and
  log-score gain;
- model-cluster sign-flip robustness. Enumerate every assignment if there are at
  most 22 clusters; otherwise use exactly 1,000,000 Rademacher draws with seed
  `20260718` and report Monte Carlo standard error.

The fixed predictive promotion rule requires all of:

1. at least 100 comparable holdout events, at least 10 model clusters, and no
   model contributing more than 50% of comparable events;
2. the model-cluster 95% interval for `Y-q^MM` has a positive lower endpoint;
3. every leave-one-model-out residual is positive;
4. the model-cluster 95% interval for M1-minus-M0 log-score gain has a positive
   lower endpoint;
5. every leave-one-model-out log-score gain is positive; and
6. the one-sided cluster sign-flip p-value for each statistic is at most 0.05.

If support fails item 1, report the estimates as power-gated regardless of their
signs. If M1 fails predictive promotion, the training-fitted response increment
does not generalize. If it promotes, the result rejects this declared
matched-market exchangeability model in favor of a persistent same-model landing
increment; it does not prove strategic response.

## Calibration and comparison disclosures

Report MM1 beside the unchanged factor-1.25 global-menu benchmark on the exact
same holdout events. Compare Brier score, log score, calibration intercept
`mean(Y-q)`, and the 5th/median/95th percentiles of predicted probabilities. A
better held-out score makes MM1 a more empirically adequate conditional benchmark;
it does not validate its economic exclusion restriction.

No bandwidth, match count, feature set, minimum support, response form, seed,
cluster unit, or promotion threshold may be changed after the 30-date outcomes are
read. Implementation bugs must be documented and corrected without changing the
economic specification.

## Claim boundary

MM1 conditions on the realized event and mover's new price, so it is not a full
model of refresh timing, price choice, costs, or equilibrium. Whole-market decoys
can still differ from the focal model through unobserved demand, hardware,
provider specialization, or a model-specific public focal point. A promoted MR1
result identifies persistent same-model excess landing relative to a declared
exchangeability class. It cannot reveal private request order, provider intent,
literal front-running, communication, collusion, profit, or welfare loss. H80's
outcome mask and 500-per-arm gate remain unchanged.
