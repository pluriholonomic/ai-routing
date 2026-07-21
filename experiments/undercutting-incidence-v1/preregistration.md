# Undercutting incidence under inverse-square shadow routing

## Question and frozen estimands

This experiment asks which nonmoving provider-model regimes absorb the routed-share and
fixed-demand quote-revenue displacement when a frozen `active_undercutter` lowers its public
quote. The primary window begins at the WF-16 holdout date. Provider types are learned only
from the earlier WF-16 training window and are not updated using WF-19 outcomes.

For request shape \(x\), public quote \(p_{itx}\), and publicly unruled-out candidate set
\(E_{mtx}\), the shadow allocation is

\[
s_{itx}=\frac{p_{itx}^{-2}}{\sum_{j\in E_{mtx}}p_{jtx}^{-2}}.
\]

For a unilateral price cut by provider \(k\), the primary type-level outcomes are:

1. absolute shadow-share loss, \(\sum_{j\in g}(s_{jt^-x}-s_{jt^+x})\);
2. share-loss burden, dividing that quantity by total nonmover share loss;
3. fixed-demand quote-revenue loss,
   \(\sum_{j\in g}(p_{jt^-x}s_{jt^-x}-p_{jt^+x}s_{jt^+x})\);
4. quote-revenue-loss burden, dividing that quantity by total nonmover quote-revenue loss;
5. the mover's shadow-share and quote-revenue-index changes.

The four fixed request shapes are averaged to one observation per public quote shock. Shocks,
not request shapes or providers, are the observational unit.

## Inclusion and exclusion rules

The primary panel includes adjacent snapshots at most 30 minutes apart, after the frozen
WF-16 holdout boundary, with the same public provider set and exactly one changed workload
quote. The mover must carry a frozen `active_undercutter` label and its quote must fall.
Transitions crossing an observed public status or 99-percent uptime threshold are excluded.

Simultaneous moves, provider-set changes, raises, pre-holdout observations, free quotes, and
single-provider markets are excluded from the primary panel. Simultaneous moves may be studied
later with a separately labeled Shapley decomposition but cannot enter the primary estimate.

## Tests and support gates

The inverse-square accounting identity predicts identical proportional share loss for every
nonmover. Absolute burden should therefore equal the type's normalized pre-event nonmover
share. A type-specific residual in *realized* routing, but not this shadow calculation, would
be evidence that eligibility, health, capacity, or another router mechanism loads differently
on that type.

Descriptive type means and model-mover cluster-bootstrap intervals are reported. Provider-type
inference remains gated until the panel has at least 10 models, 10 movers, 30 model-mover
clusters, and no cluster contributes more than 20 percent of shocks. All leave-one-model and
leave-one-mover conclusions must then agree in sign before manuscript promotion.

## Paid validation

Natural public price events are registered before owned outcomes. The realized validation uses
only `default_fresh` requests with neither `sort` nor `order`; those fields would disable the
default load-balancing rule under study. Price-sorted and moving-provider-pinned requests are
admission and telemetry controls, not observations of default selection.

The first paid read is descriptive and is gated until at least 100 default attempts across 20
registered active-undercutter events exist. A later confirmatory analysis must match pre-event
default requests by model, request shape, and time of week, because natural cuts cannot be
anticipated. The outcome is selected-provider type, recovered from owned generation metadata.

## Claim boundary

Public WF-19 outputs are shadow-routing accounting, not realized flow. Paid requests observe
only our sampled selections, not market-wide provider traffic. Fixed-demand quote revenue is
not profit. Private 30-second health state, capacity, rebates, marginal cost, demand expansion,
communication, anticipation, and provider intent are not identified.
