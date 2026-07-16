# Author-focality identification audit — 2026-07-16

> **Superseded later on 2026-07-16.** The adjacent-grid comparison below proves
> an exact price atom but is not an identity null. The price-multiplicity-preserving
> endpoint-label audit finds 54.3% observed versus 53.5% for a random endpoint
> (`p=0.466`) and an author excess of 0.79 points with interval [-9.0, 16.1].
> Do not cite the 53.3-point adjacent-grid contrast as author-specific evidence;
> use `price-atom-hard-null-audit-2026-07-16.md`.

## Why the old statistic was insufficient

The manuscript previously emphasized that 65 of 72 selected tied models with an
author-operated endpoint had the author at the tied minimum. That conditioning
event makes a high match rate partly mechanical. If a model has `n` providers,
`t` of them are tied at the minimum, and `r` author-operated labels are assigned
exchangeably to provider slots, the conditional probability that at least one
author label is in the tied set is

`1 - choose(n - t, r) / choose(n, r)`.

It equals one whenever every provider is tied. On the frozen panel's final public
snapshot (`20260715T040226Z`), the robust author-family crosswalk yields 48
author-at-minimum matches among 54 selected tied models. The conditional
random-label benchmark expects 47.95 matches, or 88.8%; the exact
Poisson-binomial upper-tail probability is 0.625. The selected-tie statistic is
therefore non-discriminating and has been demoted. The old name-substring
crosswalk was also overinclusive; the corrected mapping uses explicit provider
families and author aliases.

## Corrected all-market estimand

The replacement starts from every multi-provider model containing at least one
author-operated endpoint and one third-party endpoint. For each model it records
whether any third party quotes exactly at the author's lowest first-party price.
It compares that indicator with the average match indicator at 40 symmetric
placebo levels around the author price. The primary spacing is $0.10 per million
tokens; $0.01, $0.50, and $1.00 grids are fixed sensitivities.

On the same public snapshot:

- 52 of 95 models, or 54.7%, have an exact third-party match at the author price;
- the adjacent dime-grid placebo match rate is 1.4%;
- the paired excess is 53.3 percentage points;
- the 20,000-draw author-cluster bootstrap interval is [31.0, 80.4] points;
- 10 of 12 author clusters have positive mean excess, giving a one-sided sign
  test `p = 0.0193`;
- leave-one-author-out estimates range from 47.8 to 64.8 points;
- the excess is 53.3--54.4 points across all four fixed placebo grids.

The result identifies a cross-sectional atom at the author's price relative to
adjacent equally spaced focal levels. It does not show that the author caused the
match, distinguish common cost from salience or convention, or transport beyond
the twelve observed author families.

## Status and confirmatory gate

This specification was written after inspecting the post-freeze snapshot and is
therefore exploratory. It is now frozen in code and machine-readable output. The
confirmatory release recomputes it without changes on the earliest 30-date
prefixes of both manuscript quote vintages, retains all four placebo grids, and
clusters by author. No owned-probe outcomes or private route records enter this
audit.
