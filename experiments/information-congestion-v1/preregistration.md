# OpenRouter information-congestion experiment v1

Status: prospective. The protocol hash is frozen into every plan, assignment,
attempt aggregate, monitor, and release artifact. This study does not amend or
pool outcomes with `openrouter-glm52-market-share-hmp-v1`.

Protocol source: `config/information_congestion_v1.toml`.

## Question and primary estimand

For a frozen model menu, let `n` be the ex-ante count of compatible providers
and let `k` be the number of previously classified responsive providers exposed
to an owned request. Define

\[
 k^*_{\mathrm{obs}}(n)=\arg\max_k
 E[Y\mid do(n,k,\text{overlap},\text{rule})],
\]

where `Y` is router-observable surplus and every raw component is also reported.
The primary scaling estimand is

\[
 \log(k^*_{\mathrm{obs}}(n)/n)=a-\tau\log n+\epsilon_n.
\]

The primary null is `tau <= 0`; the economically meaningful alternative is
`tau > 0.05`. This is a finite-range exposure result. It is never described as
proof of an infinite-population limit.

## Theory consistency check

Public quote innovations estimate effective rank `r_n` and its scaling exponent
`beta`. The reduced-form congestion curvature is `gamma`. The registered
overidentifying relationship is

\[
 \tau=\gamma(1-\beta)/(1+\gamma).
\]

Rank alone cannot identify `k*`. Promotion requires both a shrinking randomized
exposure optimum and realized outcome curvature. The strong rank gate is a
one-sided upper 95% bound below `0.9`; an upper bound below one but above `0.9`
is labeled statistically sublinear but economically weak.

## Ex-ante populations and shocks

Provider eligibility is determined before study outcomes from request-shape
compatibility, positive prices, context support, and menu presence. A provider
is responsive when the pre-period contains at least the configured number of
price changes and adequate snapshot coverage. That label is a sampling stratum,
not intent or a structural provider type.

The frozen model cohort is GLM-5.2, GPT-OSS-120B, Gemma-4-31B-IT,
MiniMax-M2.7, DeepSeek-V4-Flash, DeepSeek-V4-Pro, and Kimi-K2.7-Code. All have downloadable
weights from their model authors and, in the pre-period ending 2026-07-23, at
least two adequately covered repricing providers and at least eleven positive-
price providers on the latest observed menu. The selection rule and names were
frozen before any prospective paid outcome. Model availability failures remain
in the run ledger and are not silently replaced after the start date.

Public shocks are author-price changes, provider price changes, entry/exit,
derank transitions, rate-limit spikes, capacity changes, and placebo clocks.
Shock types and response windows are assigned without owned outcomes. Provider
quote innovations are evaluated at 5m, 15m, 60m, 6h, and 24h horizons.

## Randomized paid blocks

Each plan freezes a live OpenRouter menu before requests. Feasible cells cross:

- menu size `n` in 4, 8, 12, and 20;
- responsive exposure `k` in 0, 1, 2, 3, and 5, subject to `k <= n`;
- high- versus low-overlap responsive sets when `k >= 2`;
- default versus price-sorted routing; and
- two fresh-session replicates.

The remaining `n-k` positions are sampled from the nonresponsive pool. Provider
identity is randomized within role and price strata. High/low overlap uses only
pre-period innovation correlations. Plans are immutable and uploaded before
execution. Retries never regenerate assignments.

Paid requests identify the causal effect of this project's eligible menu at
fixed public state. They do not change the market-wide number of adaptive
providers. The natural-shock panel supplies that observational bridge. A router
or provider-side randomized information intervention would be required to make
market-wide adaptation causal.

A separate six-hour quality bank spends from the frozen $75 quality envelope.
It rotates across the least-measured feasible model and, within that model, the
three least-measured compatible providers. Two outcome-free public MMLU item
IDs are frozen before eight requests: one default route and three exact pins
per item. The resulting correctness, success, latency, token, cost, and hash
fields are auxiliary outcomes; benchmark prompts and completions are not
retained. Quality outcomes cannot select the primary operational-surplus
specification or stop the campaign.

## Outcomes

The primary operational outcome is

\[
Y = v\,1\{\text{success}\}-c_{usd}
  -\lambda_L L-\lambda_F1\{\text{fallback}\}
  -\lambda_E1\{\text{failure}\}.
\]

The weights are frozen in the TOML. Success, selected provider, cost, latency,
fallback, rejection, and fidelity are always reported separately. Provider
marginal cost is not observed; full social welfare is bounded using declared
GPU-cost/utilization scenarios and is not point identified.

## Inference

Randomized arms use exact within-block randomization inference. The response
surface uses block-clustered intervals and a simultaneous confidence set for
the argmax. `tau` is estimated only when at least three supported menu sizes
have an interior optimum; the strong gate requires four size bins. Rank slopes
use calendar-block bootstrap intervals, a future temporal holdout, random
provider subsets, and leave-one-model-cohort-out checks. No model cohort may
contribute more than 25% of the primary statistic.

The seven-day pilot is restricted to operational checks and variance estimation.
It cannot select the sign, model, endpoint, or hypothesis. The confirmatory
horizon is fixed from pilot variance before confirmatory outcomes are accessed.
Collection never stops on an outcome.

## Integrity and support gates

Paid execution requires all of the following:

1. at least 95% intended capture coverage and no unexplained gap over 15m;
2. public snapshot age at most 30m;
3. exact assignment integrity and no duplicate task IDs;
4. complete assignment-attempt-spend reconciliation;
5. at least 90% exact-menu coverage;
6. no secret or request payload in public artifacts; and
7. the dedicated run, day, and campaign budget checks.

Confirmatory promotion additionally requires the TOML's block, choice, shock,
provider-pair, duration, model-cohort, and holdout thresholds. Definitions are
not relaxed if a cell accrues slowly.

## Claim boundary and release

The strongest permitted positive statement is: over the observed menu-size
range, the welfare-maximizing correlated-provider exposure grows more slowly
than menu size, consistent with the model's `k*=o(n)` regime. The study does not
identify an asymptotic limit, market-wide adaptation, provider algorithms,
provider costs, communication, intent, or collusion.

Request-level records remain in the private HF sink. Assignment-only plans,
support counts, redacted aggregates, protocol hashes, and the final signed
release are public. The final release is immutable and published regardless of
sign after the fixed horizon.
