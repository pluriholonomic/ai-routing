# H81 outcome-blind amendment: frozen release presentation

Date frozen: 2026-07-17

Status: frozen before the first H81 outcome query. Automatic assignment-only
audit `29574322884` checked out commit `5633f1d687c6ad51a6a367cd40bdc0ea39a7b7f4`,
pinned immutable dataset revision
`60d5a02005d553b956c903c1a8bd0b30df2d1636`, reported arm counts 34/31/29,
and recorded `outcomes_queried=false`.

## Motivation

The analysis code already freezes the estimands, stopped prefix, exact tests,
Holm family, design intervals, descriptive intervals, and missingness bounds.
The one-time release bundle did not yet freeze how those outputs enter the
paper. Choosing a table, figure, or narrative emphasis after observing the
result would create avoidable presentation discretion even if no estimator
changed.

## Frozen release package

When, and only when, the 40-intended-assignments-per-arm balance gate and the
assignment-integrity gate both pass, the analyzer will emit:

1. a policy-arm panel of preterminal intended-assignment success means with the
   simultaneous finite-population design intervals;
2. a three-row contrast table containing fallback, hidden selection, and total
   delegation ITT estimates; preterminal pair counts; design intervals; exact
   one-sided Fisher tails; and Holm-adjusted primary tails;
3. a two-panel figure showing arm means and the decomposition forest plot, with
   the conservative treatment/outcome sensitivity bounds behind the design
   intervals;
4. a neutral LaTeX paragraph that reports every component regardless of sign,
   records the terminal-block exclusion and treatment/outcome completeness, and
   repeats the finite-prefix claim boundary; and
5. a machine-readable validation manifest.

The report fails closed unless all binary outcomes needed for the complete-data
point estimates are present, the ITT and conditional Horvitz--Thompson
estimates agree, the total contrast equals the sum of the two components to
`1e-12`, both registered primary Holm values exist, the arm counts sum to the
preterminal prefix, exactly one gate-hitting block is excluded, and the
treatment/outcome sensitivity fields are complete.

## Interpretation rule

Every estimate, interval, and registered p-value is reported regardless of
sign. A nonsignificant result is described as imprecise at the registered
horizon, never as equivalence. The total contrast is an algebraic summary, not
a third primary test. Conditional selected-provider, latency, spend, and
fallback fields remain secondary diagnostics with their existing missingness
boundaries; they are not promoted by the report template.

This amendment changes presentation and release validation only. It does not
change treatment assignment, eligible support, the 40-per-arm stopping rule,
terminal-block exclusion, outcome definition, estimands, directional
hypotheses, exact reference laws, Holm family, interval construction, or claim
boundary. The result remains a finite-prefix owned-account intention-to-treat
effect and does not identify market-wide routing, provider intent, equivalence,
or welfare.
