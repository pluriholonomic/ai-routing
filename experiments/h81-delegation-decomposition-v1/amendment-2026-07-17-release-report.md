# H81 outcome-blind amendment: frozen release presentation

Date frozen: 2026-07-17

Status: frozen before the first H81 outcome query. Automatic assignment-only
audit `29574322884` checked out commit `5633f1d687c6ad51a6a367cd40bdc0ea39a7b7f4`,
pinned immutable dataset revision
`60d5a02005d553b956c903c1a8bd0b30df2d1636`, reported arm counts 34/31/29,
and recorded `outcomes_queried=false`.

The implemented template was then committed as
`65e142526962a61a3101edacb16af61caa21d46d`. Exact-head assignment-only audit
`29574825052` checked out that commit against the same immutable revision,
reproduced counts 34/31/29 and the passing assignment-integrity gate, and again
recorded `outcomes_queried=false`. This is the provenance point that ties the
code below, its tests, and this amendment to the pre-outcome state.

Post-marker preservation was committed as
`d4d2b19d07d03c19573de7f58c67c1e3e0dd7f31`. Exact-head assignment-only
audit `29575626677` checked out that commit, pinned immutable revision
`df74e296828b5d1d8f80e6925f1260e09a8c0fb3`, reproduced counts 34/31/29 with
100% reconstruction, replay, first-row observation, and treatment fidelity,
and again recorded `outcomes_queried=false`. The artifact contained only the
two assignment-only gates and release status.

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

## Post-marker preservation rule

A further outcome-blind transaction audit found that the strict renderer runs
after the irreversible remote first-outcome-access marker.  Under the original
implementation, a missing binary outcome, algebraic validation failure, or
plotting error could raise after the raw tables had been written but before the
immutable release bundle was published.  That would leave an orphan marker and
make automatic re-access correctly impossible, while needlessly stranding the
first result in a temporary workflow artifact.

The strict validator and its paper-promotion rule are unchanged.  The one-time
analyzer now wraps only the presentation step: a validation or rendering error
writes `h81_release_report_error.json`, marks paper promotion false, preserves
the already-written policy panel, model panel, contrasts, intended-assignment
ledger, support diagnostics, and summary, and allows those raw artifacts to be
published in the immutable marker-bound bundle.  Recovery must use that bundle
and a dated amendment; the source outcomes may not be queried again.  Direct
calls to the strict renderer still raise, and no failed presentation can produce
the table, figure, or neutral paragraph used in the paper.

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
