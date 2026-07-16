# Frozen-vintage Brown--MacKay audit — 2026-07-16

## Why the earlier screen needed correction

The original cadence screen divided a provider's number of price changes by the
elapsed time between its own first and last observed changes. That denominator is
endogenous to activity and overstates the rate of sparse repricers. The corrected
screen divides by each provider's observed quote days in the frozen panel.

The original reaction linker also sorted rows that shared a five-minute capture
timestamp. Because the public data interval-censor quote updates, that row order
is not economic time. The corrected implementation:

1. does not assign an initiating provider to a simultaneous multi-provider batch;
2. uses only strictly earlier rival timestamps;
3. excludes a response when several rivals tie for the most recent prior timestamp;
4. freezes cadence classes on the first 70% of events; and
5. evaluates state-only and Brown--MacKay reaction rules on the same temporal holdout.

Two independent reruns now give identical publication metrics. Published vintage
tables are row-canonicalized, numerically stabilized, and SHA-256 hashed.

## Frozen nine-day results

The fixed window is 2026-07-07 through 2026-07-15.

- 69 providers are exposed: 50 inactive or left-censored, 9 intraday, 7 daily,
  and 3 weekly. Sixteen of the 19 observed repricers are classified fast.
- The within-model-day fast-provider coefficient is -0.09637 with 95% interval
  [-0.15147, -0.04127] over 5,501 observations and 127 models. This implies a
  descriptive slow-over-fast quote premium of 10.1%.
- On the delivered-quality overlap, the coefficient is -0.38925 with interval
  [-0.63737, -0.14113] over 423 observations and 23 models. Selection into this
  overlap prevents a causal comparison with the larger estimate.
- The frozen temporal reaction design has 19 unambiguous waves and zero
  slow-initiator risk pairs.
- Coarsened linking retains 188 reactions. The temporal holdout contains 46
  observations in seven model clusters. State-only RMSE is 0.23835 and the
  Brown--MacKay RMSE is 0.23760.
- The paired MSE improvement is 0.000355 with model-cluster bootstrap interval
  [-0.000972, 0.008033]. An exact seven-cluster sign-flip sensitivity gives
  one-sided p=0.0234. Because the few-cluster bootstrap interval crosses zero,
  the preregistered verdict is `predictively_indistinguishable`.

## Interpretation

The pricing-technology association survives the corrected exposure denominator,
but the distinctive slow-initiator/fast-responder mechanism does not currently
have identified support. The exact sign-flip sensitivity is suggestive, while the
zero slow-initiator risk set and wide few-cluster interval prevent promotion.

This is a sharper market comparison than labeling every correlated response as
algorithmic interaction: sticky administered menus and cadence-related price
dispersion are visible, but the Brown--MacKay reaction rule does not yet beat a
state-dependent menu-cost benchmark robustly.

## Confirmatory contract

The `manuscript_vintages` analyzer now runs PM1 and BM1--BM4 on the earliest nine
and earliest 30 observed dates using identical code. The 30-day release is not
computed early. Its comparison table is restricted to metrics fixed in code
before the confirmatory data exist. A sign reversal, a state-only predictive
advantage, or continued absence of slow-initiator support is reported as such and
cannot be replaced by an alternative post hoc reaction definition.
