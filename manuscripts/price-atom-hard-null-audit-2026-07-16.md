# Price-atom hard-null audit — 2026-07-16

## Why this audit was necessary

The frozen nine-date panel produced two apparently strong statistics:

1. 54.3% of author-observable models had a third-party quote exactly at the
   author price, versus 1.5% at adjacent grid levels.
2. 20.4% of isolated quote revisions landed exactly on a rival's strictly prior
   quote, versus 1.0% at adjacent grid levels.

Both adjacent-grid comparisons test whether exact prices contain mass. Neither
tests whether the mass is specific to author identity or strategic following.
Providers can draw from a common discrete price menu, leaving nearby levels empty
and creating asynchronous exact landings without observing or responding to one
another.

## Frozen data contract

- Dates: 2026-07-07 through 2026-07-15, nine distinct quote dates.
- Immutable data revision: Hugging Face dataset commit
  `600bb41fd15189c70f8f78fce8cf0a519fb8dd61`; 16/16 release artifact hashes
  matched on an independent pinned replay.
- Author identity: the shared provider-family crosswalk; only models with exactly
  one author endpoint and at least one third-party endpoint.
- Dynamic event: consecutive observations no more than 15 minutes apart, exactly
  one provider changes, and at least one lagged rival quote is observed.
- All specifications below were developed after inspecting the frozen panel and
  are therefore exploratory there. They are now fixed for the earliest 30-date
  release.

## Hard null 1: exchangeable endpoint identity

For each model, retain its complete realized price multiset. An endpoint is shared
if another endpoint has exactly the same price. Under the null, place the unique
author label uniformly among endpoint slots. If `s` of `n` endpoints are shared,
the author-shared probability is `s/n`; the sum is tested with the exact
Poisson-binomial upper tail.

| Statistic | Result |
|---|---:|
| Models / author clusters | 94 / 12 |
| Observed author at shared price | 51 (54.26%) |
| Random-endpoint expectation | 50.262 (53.47%) |
| Author-minus-random endpoint | +0.785 pp |
| Author-cluster 95% interval | [-9.05, +16.08] pp |
| Exact upper-tail p-value | 0.4657 |
| Leave-one-author-out range | [-1.87, +6.52] pp |
| Author–third-party minus third-party pair density | -0.94 pp [-8.83, +12.00] |

Conclusion: the exact atom is not author-specific. The old selected-tie statistic
also remains non-discriminating (90.0% observed, 91.9% random-label expectation,
`p=0.913`).

## Hard null 2: matched common public menu

For each isolated revision, the observed statistic is whether the new price equals
any rival price in the strictly prior snapshot. The hard null draws the same
number of quote endpoints from other models at that prior snapshot, within a
factor 1.25 of the new price. The hypergeometric probability of at least one exact
hit preserves risk-set size, local price scale, and the global frequency of every
exact menu point.

| Statistic | Result |
|---|---:|
| Events / models / movers | 196 / 18 / 15 |
| Exact lagged-rival landings | 40 (20.41%) |
| Adjacent-grid expectation | 0.96% |
| Matched common-menu expectation | 13.41% |
| Exact-minus-common-menu | +7.00 pp |
| Model-cluster 95% interval | [-23.15, +12.23] pp |
| Provider-cluster 95% interval | [-22.42, +18.24] pp |
| Leave-one-model-out range | [-10.42, +9.67] pp |
| Largest model share of events / copies | 73.47% / 85.00% |

The adjacent-grid result looks positive; the matched-menu result does not. Wider
control bands reduce the menu baseline, so the registered replication retains the
tightest factor-1.25 band rather than selecting a favorable sensitivity.

A past-only same-model sensitivity uses historical provider sets for the same SKU,
separated from the event by at least 24 hours. It retains 189 events, predicts a
6.78% menu-match rate, and gives a 14.39-point residual. The provider-cluster
interval is positive [1.90, 22.97] points, but the primary model-cluster interval
is [-0.07, 17.52] points and most model clusters contribute no variation. Its
leave-one-model-out range is [1.11, 15.55] points. This comparison is registered
as a secondary SKU-specific sensitivity, not selected over the tighter global
common-menu primary.

## Preregistered same-provider control and size--power audit

The follow-up specification was pushed in commit `adc09cd` before estimation.
Among 175 comparable events, only 6.86% reuse the provider's own cross-model
price. That rate is 5.26% among exact rival landings and 7.30% otherwise, a
-2.04-point association with model-cluster interval [-31.03, 0.93]. Removing the
12 own-menu-supported events leaves 163 revisions and raises the matched-menu
excess to 13.44 points, but the model-cluster interval remains
[-11.50, 18.51]. The control weakens a simple own-template explanation without
promoting strategic following.

The frozen-design simulation has 3.5% one-sided null promotion, but only 43.4%
interpolated power at the observed-equivalent response probability `rho=0.0809`.
In 1,250 full known-clock panels, the null never promotes, but it also never
promotes at reactive-replacement probabilities through 0.50: the global-menu
benchmark is much denser than the focal rival set. The hard-null failure is
therefore both nonidentification and low power, not evidence of no response. Full
results are in `pm5-negative-control-simulation-results-2026-07-16.md`.

A separately timestamped robustness addendum (`dc90d02`) enumerates every
model-cluster sign assignment. The one-sided exact p-value is 0.4250 for the full
196-event panel and 0.2139 for the 163-event own-menu-novel panel, so the positive
point estimates are not broadly supported across models. The same addendum freezes
an empirical calibration check. All four empirical diagnostics lie outside the
SIM2 null's 5--95% range: SIM2 produces 1,228--3,381 events, 49.0--73.2% exact
landings, and 89.1--91.3% menu probabilities, versus 196, 20.4%, and 13.4% in the
data. SIM2 is therefore a stress-test counterexample, not an empirically calibrated
model of the observed market.

## Identification result

An unrestricted asynchronous-menu model and a rival-response model can generate
the same finite snapshot panel. In the menu construction, every observed price is
a public menu point and provider-specific refresh clocks select the observed
terminal prices without rival dependence. In the reactive construction, any
chosen subset of exact landings is labeled a response while preserving the same
observations. Consequently, if `L` of `N` isolated revisions land exactly, the
share of all revisions that are exact strategic landings is sharply identified
only within `[0, L/N]`. Here that set is `[0, 40/196] = [0, 20.41%]`.

## Promotion rule and current verdict

At the earliest 30-date release:

- Author salience requires a positive endpoint-label effect supported by the
  exact upper-tail test and the author-cluster interval.
- Strategic lagged landing requires the factor-1.25 model-cluster interval to
  exclude zero and every leave-one-model-out estimate to remain positive.
- The adjacent-grid statistics remain descriptive price-atom measurements and
  cannot promote either behavioral claim.

Current verdict: **exact price atoms supported; author salience unsupported;
strategic following unsupported; common-menu observational equivalence not
rejected.**
