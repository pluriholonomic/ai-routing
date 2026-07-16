# H80 identification correction — 2026-07-16

## What was wrong

The v3 manuscript described the randomized crossover as 152 default attempts
versus 76 attempts in each pinned arm and reported default success as 151/152.
That denominator pooled two different samples:

- 76 default attempts inside 76 complete randomized-order four-policy blocks;
- 76 default-only monitoring attempts on four additional hot models that were
  not eligible for a complete pinned comparison.

The resulting 151/152 rate is a valid monitoring rate but not a valid policy
contrast because model support differs between default and pinned rows.

## Corrected empirical object

The matched all-position screen contains 76 complete blocks and 304 attempts:

| Policy | Successes | Attempts | Rate |
|---|---:|---:|---:|
| Default | 75 | 76 | 98.7% |
| Pinned cheapest | 61 | 76 | 80.3% |
| Pinned second | 62 | 76 | 81.6% |
| Pinned random | 64 | 76 | 84.2% |

The correction changes the default point estimate by -0.6 percentage points
and materially widens its marginal interval. It does not reverse the secondary
all-position level or the flat cheapest/second/random ranking. Those rates are
not the confirmatory causal estimand: randomized order balances clock position,
but an earlier policy can affect a later request.

The carryover-robust primary estimand uses only assignment-verified position-zero
rows. At the authoritative 2026-07-16 snapshot, outcome-free arm counts were
15, 20, 19, and 22, with 100% assignment replay. Their outcomes are now masked
until every arm reaches 500.

## Preventive changes

The correction is enforced in code rather than documentation alone:

1. `MIN_FIRST_POSITION_PER_POLICY` is 500, matching the reviewed manuscript.
2. The pre-gate path can run on an assignment-only frame with all outcome fields
   physically absent.
3. `h80_probe_blocks.parquet` masks randomized response, cost, latency,
   provider-selection, token, and status-derived fields before the gate.
4. When the gate opens, only the earliest chronological balanced prefix is
   released; later rows remain a masked continuation sample.
5. `manuscript_promotion_gate_summary.json` publishes the outcome-free H80 and
   30-day quote-panel accrual state nightly.

## Claim consequence

The paper now has two promoted price-surface facts—administered menus and an
excess minimum-price tie atom—and a power-gated router-firmness design. The later
author-identity correction demotes the selected-tie anchor statistic and freezes
an all-market adjacent-level audit for the 30-date release. Router-manufactured firmness is
an interim mechanism hypothesis, not a promoted causal fact, until the registered
first-position release.
