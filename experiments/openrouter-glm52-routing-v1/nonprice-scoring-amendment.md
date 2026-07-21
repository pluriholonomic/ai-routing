# Prospective non-price scoring amendment

Frozen analysis start: 2026-07-21T22:00:00Z.

This amendment was written after the original GLM-5.2 campaign began and after
operational outcomes and aggregate selected-provider identities from its first
few blocks were available. It is therefore not part of the original
preregistration. Estimates using choices before the timestamp above are
descriptive only. The prospective scoring analysis, rule contrast, support
gates, and counterfactuals below use only requests completed at or after the
frozen timestamp.

## Joint price and score model

For provider (i) in the frozen public menu for owned default-route request
(t), the secondary choice model is

\[
  \Pr(i\mid\mathcal M_t)
  = \frac{p_{it}^{-\eta}\exp(\alpha_i)}
  {\sum_{j\in\mathcal M_t}p_{jt}^{-\eta}\exp(\alpha_j)},
  \qquad \eta=1.6482780609377246.
\]

The price exponent remains frozen at the original campaign value. Provider
effects use a fixed L2 penalty of 1.0 and are reported relative to Z.AI. They
are reduced-form score wedges, not structural quality parameters. They bundle
router scoring, health, capacity, eligibility mismatch, and persistent router
preferences. They do not identify the router's proprietary score.

Three aggregate quantities are fixed:

1. mean total-variation distance between the price-only and score-adjusted
   choice distributions, interpreted as the mean routing probability mass
   reallocated beyond observable price;
2. whole-block five-fold out-of-sample log-loss improvement, in bits per
   choice, over the frozen price-only model; and
3. a conditional Monte Carlo test of provider selection shares under the exact
   frozen menus and price-only probabilities.

Inference for relative provider scores uses whole-block cluster-robust
curvature intervals. Provider rows are marked stable only after 20 menu
appearances and either five realized or five price-expected selections.

## Manipulation interaction

For each below-benchmark provider and block, set that provider's quote to the
Z.AI benchmark while holding the other menu quotes fixed. Compute its routing
share gain from the actual undercut once under the price-only rule and once
under the fitted score-adjusted rule. Their difference is the scoring
interaction. A negative interaction means scoring attenuates the unilateral
share gain from undercutting; a positive interaction means it amplifies the
gain. These are one-provider-at-a-time counterfactuals and are not additive
when several providers undercut simultaneously.

## Direct rule contrast

Within complete blocks, compare cheapest-provider selection under the fresh
`price_sorted` request with the two fresh `default_broad` requests. The fixed
estimand is the price-sorted minus default cheapest-selection rate with a
whole-block bootstrap interval. This is an owned-request rule contrast. It is
not a direct estimate of the latent provider scores and assumes no carryover
between randomized tasks in the same block.

## Support and reporting

The score model, conditional null, and manipulation interaction remain
`accruing` until there are at least 40 covered prospective default choices, 20
prospective blocks, and three selected providers. The direct rule contrast
requires 20 complete prospective blocks. These early gates permit diagnostic
estimation only. Publication-strength interpretation remains subject to the
original campaign's stricter 800-choice, 100-block, seven-day, and 90-percent
coverage gates. The fixed calendar horizon is unchanged, and no missed runs
are replaced or accelerated.
