# PM5 negative-control and simulation preregistration — 2026-07-16

## Status and purpose

This document freezes two post-nine-date diagnostics before their estimates are
computed. They are exploratory in the existing nine-date panel and confirmatory
only in the earliest 30-date release. Their purpose is to answer the v10 referee's
remaining restricted-menu objection without inspecting H80 outcomes.

The implementation must use the existing PM5 event definition and primary hard
null unchanged: consecutive snapshots at most 15 minutes apart, exactly one
observed mover, a strictly prior same-model rival set, a factor-1.25 global-menu
risk set, exact price equality at floating-point tolerances already in PM5, model
clustering, provider clustering, and leave-one-model-out sensitivity.

## NC1: same-provider/across-model negative control

For event `e=(model m, provider i, prior time t-, new price p)`:

1. At exactly `t-`, collect provider `i`'s quotes for models other than `m`.
   No future quote, same-model quote, provider-family alias, interpolation, or
   nearest noncontemporaneous snapshot is allowed.
2. Restrict that set to prices in `[p/1.25, 1.25p]`, matching the primary local
   price band. An event is control-comparable only if this local set is nonempty.
3. `own_menu_exact=1` when at least one retained price equals `p` exactly.
   `own_menu_novel=1` when the event is comparable and `own_menu_exact=0`.

The fixed outputs are:

- comparable-event count, own-menu exact-support rate, and model/provider
  concentration;
- own-menu exact-support rates conditional on exact same-model rival landing and
  on no exact landing, plus their difference with model- and provider-cluster
  intervals;
- the existing `exact_minus_global_menu` estimand restricted to
  `own_menu_novel=1`, with model/provider cluster intervals and the full
  leave-one-model-out range;
- a four-cell table crossing same-model rival landing with own-provider
  across-model support.

Interpretation is one-sided and fixed. A positive own-menu association is evidence
that shared provider templates can manufacture the apparent response atom; it is
not evidence of provider collusion. Strategic following survives NC1 only if the
own-menu-novel `exact_minus_global_menu` model-cluster interval excludes zero and
every leave-one-model-out estimate is positive. Missing controls cannot be coded
as novel. No threshold, provider normalization, or event filter may be changed
after the result is read.

## SIM1: event-level size and power

Use the frozen nine-date PM5 event panel at the immutable dataset revision named
in the release. For each comparable event, retain its model cluster and matched
global-menu probability `q_e` but discard its observed landing outcome.

- Null DGP: `Y_e ~ Bernoulli(q_e)` independently conditional on the frozen design.
- Reactive DGP: with response probability `rho`, set
  `Y_e ~ Bernoulli(q_e + rho(1-q_e))`.
- Fixed grid: `rho in {0, 0.05, 0.10, 0.25, 0.50}`.
- Fixed seed: `20260717`.
- Replications: 1,000 per grid point.
- Inference: model-cluster bootstrap with 2,000 draws per replication and the
  same event-weighted mean used by PM5; promotion additionally requires a
  positive leave-one-model-out minimum.

Report bias, RMSE, interval coverage at `rho=0`, lower-bound rejection rate, joint
promotion rate, and the median/5th/95th percentiles of the estimated excess.
This experiment measures finite-sample calibration and power for the exact frozen
cluster design; it does not establish that the matched-menu probabilities are the
true economic null.

## SIM2: known-clock panel falsification

Generate quote panels on a five-minute grid under an explicitly nonreactive
asynchronous-menu mechanism and a nested reactive mechanism.

- 18 models, 6 providers per model, 576 ticks per replication.
- Public price menu with 12 exact multiplicative levels.
- Provider refresh periods are fixed within a replication and drawn from
  `{6, 12, 24, 48}` ticks with independent phase offsets. Refresh clocks never
  read rival quotes in the null.
- A latent public menu state follows a persistent Markov chain and shifts the
  eligible exact menu levels; provider-model fixed effects choose among those
  levels deterministically plus a seeded idiosyncratic draw.
- In reactive variants, after a scheduled refresh, probability `rho` replaces
  the scheduled quote with a randomly selected strictly prior same-model rival
  quote. Use the same `rho` grid as SIM1.
- 250 panel replications per grid point, seed `20260717`.

Run the unchanged PM5 event extractor and factor-1.25 matched common-menu null.
Report extracted-event counts, exact-landing rate, estimated excess, model-cluster
rejection rate, and leave-one-model-out promotion rate. The primary calibration
criterion is null promotion at or below 5%. Power is informative only if that size
criterion passes. Simulation parameters and seeds are immutable after the first
result is generated; implementation bugs must be documented rather than silently
retuned.

## Claim boundary

NC1 and the simulations can show that a restricted asynchronous-menu explanation
is or is not rejected by a declared test. They cannot reveal private request
order, literal front-running, provider intent, private rebates, or welfare loss.
The H80 outcome mask and the earliest-30-date promotion gates remain unchanged.

## RB1 addendum: exact cluster sign-flip robustness

Added and committed after SIM1--SIM2 but before computing this statistic. This is
a declared robustness check and cannot replace the model-cluster bootstrap
primary. For both the full factor-1.25 panel and the own-menu-novel panel:

1. Compute event residuals `Y_e-q_e` and sum them within model cluster.
2. Enumerate every one of the `2^G` Rademacher sign assignments to the `G` cluster
   sums; do not studentize, trim clusters, or recenter at the observed estimate.
3. The one-sided exact p-value is the share of signed total sums weakly greater
   than the observed total sum. Report the two-sided symmetric p-value as
   secondary.

The sign-flip test assumes cluster-level symmetry and is not design-based for the
observational quote panel. It is included because percentile coverage in SIM1 was
91.5% with only 18 clusters. Promotion rules remain unchanged regardless of the
sign-flip result.

## CAL1 addendum: empirical calibration disclosure

Compare the actual frozen panel with the rho-zero SIM2 distribution on event
count, exact-landing share, matched-menu probability, and matched-menu excess.
Report the simulation 5th, median, and 95th percentiles. If the empirical value
lies outside the simulation 5--95% interval for either probability, SIM2 must be
described as a stress-test counterexample rather than an empirically calibrated
data-generating process. No parameter may be retuned in this release.
