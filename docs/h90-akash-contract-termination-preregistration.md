# H90 preregistration: transparent compute contract choice and termination

**Study ID:** `akash-contract-termination-v1`  
**Frozen at:** 2026-07-16 01:15 UTC  
**Confirmatory capture start:** the second successful Akash capture whose
snapshot time is at or after 2026-07-16 01:15 UTC  
**Fixed confirmatory calendar cutoff:** 2026-08-15 01:15 UTC

## Question

Akash exposes a public reverse-procurement choice set, an accepted lease, a
native-denomination payment channel, and an on-chain lease-close reason. Does
selecting a bid above the lowest public bid predict a more durable contract,
as would be consistent with the buyer paying for non-price provider quality?

This is a transparent-compute comparator for the inference-routing paper. It
does not observe a model request, output quality, container readiness, resource
usage, provider marginal cost, buyer value, or a delivery shortfall. A
provider-initiated close is an observable contract termination, not by itself
proof of non-delivery or default.

The public fields and lifecycle semantics are documented by Akash:

- [Deployments and lifecycle](https://akash.network/docs/learn/core-concepts/deployments/)
- [Providers and leases](https://akash.network/docs/learn/core-concepts/providers-leases/)
- [Provider lease management](https://akash.network/docs/providers/operations/lease-management/)

## Information frozen before aggregate close-reason analysis

Before this document was written, we had inspected:

- support totals for the first seven capture days;
- the H76 bid-choice support and selected-price summaries; and
- one manually selected closed lease block to confirm that
  `akash.market.v1.EventLeaseClosed` contains an immutable lease ID and a
  machine-readable reason.

We had not computed the aggregate reason distribution, linked close reasons to
choice sets, fitted a termination model, or compared close incidence by price
rank. The pre-cutoff observations are therefore an exploratory calibration
sample and are never pooled into the confirmatory estimand.

## Source contract

The collector records four public objects separately:

1. the lease list and escrow-payment state returned by the Akash network API;
2. complete bounded `MsgCreateBid` event windows for recent selected orders;
3. the block-pinned accepted lease ID; and
4. the exact `EventLeaseClosed` emitted in the close block, including its
   source-defined reason.

Every lease snapshot must retain the Akash block height and time at which the
lease list was observed. Every close row must retain the close block height,
transaction index, message index, lease ID, raw reason, and raw block-result
payload pointer. The collector fails closed for a bounded close-block window
if any requested block result is malformed.

## Confirmatory cohort

A lease enters the confirmatory cohort only if all conditions hold:

1. its first observed lease snapshot is the second or a later successful
   snapshot at or after the confirmatory capture start;
2. its `created_at` block is strictly greater than the preceding successful
   snapshot height and no greater than its first-observed snapshot height;
3. its accepted bid is linked exactly to a complete bounded bid-create event
   choice set for the same owner, deployment sequence, group, order, provider,
   and bid sequence;
4. the choice set contains at least two distinct providers and one native price
   denomination;
5. exactly one accepted bid is marked;
6. every retained bid has a nonnegative price and complete pagination/event
   coverage; and
7. the lease is observed through at least 300 blocks after creation or has an
   exact close event within 300 blocks.

Condition 2 creates a prospective inception cohort instead of treating a
recent-list endpoint as a complete historical census. A missing close event is
not imputed. A lease that disappears before 300-block follow-up without an
exact close event is excluded and counted as incomplete follow-up.

The analysis freezes the earliest chronological cohort satisfying the rules
through the fixed calendar cutoff. Later revisions cannot replace it.

## Exposure

For choice set \(j\), let \(p_j^*\) be the accepted native bid price and
\(p_j^{\min}\) the lowest retained native bid. The primary exposure is

```text
selected_above_lowest = 1[p*_j > pmin_j].
```

The secondary continuous exposure is
`log1p(selected_price_premium_to_lowest)`. Tied-lowest accepted bids are in the
lowest-price group. No USD conversion or cross-denomination comparison is
used.

## Outcomes and competing risks

The primary outcome is an exact provider-initiated lease close within 300
blocks of `created_at`, identified only from the source-defined close reason.

Secondary outcomes are:

1. escrow/insufficient-funds close within 300 blocks;
2. the union of provider-initiated and escrow-driven close within 300 blocks;
3. owner-initiated close within 300 blocks; and
4. contract duration in blocks, censored at 300.

Owner close is a competing event for the primary outcome, not a successful
delivery label. Unknown reasons remain their own category and are never folded
into provider or escrow closure.

## Estimands and tests

The primary estimand is the 300-block cumulative-incidence risk difference:

```text
Pr(provider close by 300 | selected above lowest)
  - Pr(provider close by 300 | selected lowest).
```

The analysis reports group risks with Wilson intervals, the risk difference
with a selected-provider cluster bootstrap interval, and a two-sided
provider-cluster permutation p-value. The permutation shuffles the binary
price-rank exposure within native denomination and source day; strata with no
exposure variation do not contribute.

Secondary cause-specific models use the continuous premium with native-price
denomination and source-day fixed effects and standard errors clustered by
selected provider. If either exposure group has fewer than ten primary events,
the regression is suppressed and only exact counts, Wilson intervals, and a
design-based upper bound are reported.

Holm correction covers the three directional close outcomes: provider,
escrow, and their union. Owner close and duration are diagnostics outside that
family. Every test is two-sided.

## Fixed release and power rule

No close-reason aggregate, incidence estimate, interval, coefficient, or
p-value from the confirmatory cohort is released before 2026-08-15 01:15 UTC.
Before then the analyzer may publish only:

- snapshot and source-day coverage;
- eligible choice-set counts;
- provider and denomination counts;
- price-rank exposure counts;
- exact-ID linkage and follow-up completeness; and
- close-event parser/replay integrity.

At the fixed cutoff, the earliest eligible cohort is released regardless of
sign or event count. The release is labelled underpowered unless it contains at
least 500 eligible leases, 20 selected providers, exposure shares between 10%
and 90%, at least 95% exact close-event coverage among observed closes, and at
least ten primary events in each exposure group. Failure of a power threshold
does not extend the window or change the estimand.

## Exploratory calibration sample

The immutable pre-cutoff sample may be analyzed immediately, but every artifact
must be labelled `exploratory_pre_preregistration`. It is useful for validating
the close-reason parser, measuring event support, and sizing the future study.
It cannot supply the confirmatory H90 result.

## Claim boundary

H90 can establish whether public procurement price rank predicts an observable
on-chain contract-termination reason in a transparent compute market. It
cannot establish why a provider or buyer closed, whether a workload ever
started, whether compute was delivered, the direction of selection on latent
quality, provider cost or profit, buyer welfare, an inference-routing effect,
or a causal effect of paying a higher price.
