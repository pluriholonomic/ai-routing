# HMP signal-coupling study v1

Status: support thresholds and ordered claims frozen before the first
support-ready WF-18 release. Public-price monitoring is intentionally visible
during accrual; this is not a blinded first-outcome-access design.

Date: 2026-07-21 UTC.

The dated implementation amendment records the first underpowered monitoring
estimate and the conformance fixes made before remote deployment. A future
release marker freezes the immutable source revision and promotion decision; it
does not pretend that public quote outcomes were previously unseen.

## Question

Do inference-provider quote experiments exhibit a Hansen--Misra--Pai-style
learning signature in which routing-information precision predicts residual
cross-provider price coupling, researcher-measured demand misspecification, and
future buyer harm or persistent premium pricing?

This study does not identify provider algorithms, beliefs, communication,
agreement, intent, marginal cost, or market-wide flow. `collusion_identified`,
`provider_algorithm_identified`, and `communication_identified` are frozen to
false.

## Ordered hypotheses

1. **SC1 residual coupling.** Benchmark-relative quote innovations are more
   coupled than circular clock-preserving provider shifts.
2. **SC2 SNR gradient.** Preperiod owned-routing SNR predicts subsequent
   residual pair coupling.
3. **SC3 elasticity distortion.** More-coupled pairs have a larger difference
   between an owned-choice model omitting rival price and a relative-price
   model.
4. **SC4 forward consequence.** Coupling and the elasticity wedge predict an
   untouched future premium transition or worse buyer outcomes.
5. **SC5 mechanism simulation.** Breaking common reward-signal ordering while
   preserving marginal signals attenuates SC1--SC4 in a calibrated environment.

The gatekeeping order is SC1, SC2, SC3, SC4. A later positive leg cannot rescue
an earlier failed leg.

## Chronological design

Order complete UTC dates and allocate the first 25% to nuisance calibration,
the next 50% to the mechanism test, and the final 25% to forward outcomes.
Minimum spans are 14, 28, and 14 complete days. Frozen WF-16 labels are treated
as provider-model-period states, not immutable provider traits. Outcome-period
states are never fed back into residualization or SNR estimation.

## Primary variables

For provider `i`, model `m`, and quote event `t`, define

```text
x_imt = log(price_imt / author_benchmark_mt)
a_imt = Delta x_imt - fitted nuisance expectation.
```

The nuisance fit uses calibration data only and includes model, provider,
hour-of-day, day-of-week, author-price change, provider cadence, and public
model-day quote activity. It does not use later coupling or buyer outcomes.

The SC1 primary statistic is equally weighted mean residual pair covariance in
24-hour same-model windows. Secondary windows are 1 hour, 6 hours, and 7 days.
The primary null circularly shifts each provider-model event sequence while
preserving timestamps, update counts, and residual marginals. There are 2,000
frozen permutations.

## Owned-routing SNR and elasticity

Only delegated default policies enter the primary owned-choice panel. Pinned
requests measure executable firmness and are never interpreted as delegated
selection. Candidate menus are expanded to one row per eligible provider and
joined one-to-one with frozen assignments and attempts.

Preperiod routing SNR is the absolute fitted selection signal from relative
price divided by residual selection noise, cross-fitted by date. The primary
SC2 coefficient relates later provider-pair covariance to earlier pair SNR.

The SC3 diagnostic compares

```text
omitted:    logit Pr(i over j) = controls + beta_o log(p_i)
controlled: logit Pr(i over j) = controls + beta_r log(p_i / p_j)
wedge:      beta_o - beta_r.
```

This is a researcher-estimated specification wedge, not a provider-belief
estimate. Randomized cap, order, exclusion, and sort arms identify effects of
this project's routing controls, not the causal effect of provider prices.

## Economic outcomes

The author price is a focal benchmark, not marginal cost. SC4 reports price
relative to the author, generalized buyer cost relative to successful pinned
providers, success, latency, fallback, and concentration separately. Provider
margin and total surplus are bounded over declared serving-cost scenarios.
Coupled price cuts with improved buyer outcomes are evidence against the
collusive-welfare interpretation.

## Support and inference

The confirmatory release requires 28 mechanism days, 20 models, 30 public price
experiments, 20 provider-pair-model clusters, 1,000 covered delegated choices,
20 price-changing pairs, and 200 choices per elasticity cohort. No provider pair
may contribute more than 20% of the primary statistic.

SC1 uses circular-shift randomization inference. SC2 uses model-day clustered
intervals with whole-pair and whole-model leave-one-out audits. SC3 uses a
provider-pair/model-day block bootstrap. Paid router-policy arms retain their
original finite-population randomization inference. Holm correction applies to
the frozen SC1--SC4 family.

## Falsification

Required checks are author-anchor inclusion/exclusion, prompt/completion/request
shape prices, price-increase placebos, different-model pairs, lag reversal,
provider-identity shuffles, removal of author/enforcement event windows,
fixed-frequency subsampling, leave-one-leader/provider/model-out audits, and
synthetic null/planted-effect recovery.

## Promotion language

- SC1 only: `excess residual quote synchronization`.
- SC1--SC2: `HMP-consistent SNR comparative static`.
- SC1--SC3: add `researcher-measured elasticity distortion`.
- SC1--SC4: add `associated future buyer harm or premium transition`.
- SC1--SC5 robust to heterogeneous agents: `empirical properties and calibrated
  causal simulation jointly support the proposed mechanism`.

None of these permits a claim of literal collusion, communication, intent, or
deployed HMP/UCB algorithm use.
