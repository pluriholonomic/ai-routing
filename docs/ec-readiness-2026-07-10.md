# EC-readiness audit — 2026-07-10

## Bottom line

The project is **not submission-ready** for ACM EC. It has a credible
mechanism-design nucleus and reproducible collector/analysis infrastructure,
but it does not yet have the matched execution/capacity evidence or the
private-information welfare result needed for a central empirical-theory claim.
This document is a gate ledger, not a forecast of acceptance.

## Current candidate contribution

The defensible prospective contribution is a capacity-certified inference
routing mechanism: score allocations use reliability-weighted inverse prices,
but route only against declared, collateral-backed capacity. The DeFi link is
to firm RFQ liquidity and collateralized performance, not to a claim that an
inference router is an AMM.

The current one-period model establishes only the following under stated hard
capacity and full-collateral assumptions:

1. the inverse-price allocation comparative static;
2. capped water-fill feasibility and its entropy-regularized characterization;
3. a delivery incentive when payment is conditional on service and the
   shortfall bond covers the cost-minus-price gap;
4. no profitable hard-capacity over-report that creates an unserved assignment;
   and
5. weak delivered-request-count dominance over uncapped score allocation when
   requests have equal value.
6. conditional dominant-strategy cost reporting and individual rationality for
   a direct procurement menu with fixed hard capacity and reliability.
7. conditional max-min delivery-floor dominance over score water-filling when
   the router has a declared joint-outage support and hard commitments.
8. conditional dominant-strategy reporting and individual rationality for a
   convex capacity-reservation cost when the physical ceiling and cost
   curvature are certified and only the linear cost is private.
9. a known-primitive expected-net-welfare allocation that weakly dominates
   pure-cheapest and reliability-only rules for equal request values.
10. a conditional VCG procurement benchmark for an entire privately reported
    convex cost curve, with certified capacity and reliability eligibility.

These are useful lemmas. They do **not** establish Bayesian incentive
compatibility with jointly private capacity/curvature/reliability, an empirical
welfare estimate with heterogeneous request values/quality, or an optimal bond.

## Authoritative empirical gate audit

The following was re-run against `t4run/openrouter-market-history` on
2026-07-10. New collector code that has not yet reached the dataset is not
counted as evidence.

| Requirement | Current evidence | Status |
|---|---|---|
| Direct routed-versus-provider quote basis | H13: 247 pairs across 4 days, all DeepInfra; exact-zero output basis within numerical precision | Power-gated: needs 7 days and 3 providers |
| DeFi AMM/RFQ microstructure | H41: one DefiLlama aggregate day only | Not identified: no finalized Uniswap events/depth or market-wide CoW executions |
| Decentralized compute capacity | H41: no non-null decentralized-compute capacity in authoritative store | Not identified |
| Realized routing and capacity delivery | H48: zero route attempts, commitments, matches, or realized costs | Not identified |
| Controlled policy effect | H50 has an immutable pre-registration, epoch-assignment, and clustered-estimation contract; no owned study rows | Not identified: tooling is not evidence |
| CoW solver competition | H49 collector and local validation exist, but no published remote snapshots | Not yet accumulated; sampled snapshot only, never execution flow |
| Direct-source breadth | DeepInfra is published; Cerebras and SambaNova structured adapters are merged and locally validated | Awaiting published repetitions |
| Reproducibility | Full local suite: 145 passing tests after the H50 and QuoterV2 additions | Strong engineering evidence, not empirical power |

## Non-negotiable paper gates

### Theory

- Extend the explicit single-parameter cost type to jointly private capacity,
  curvature, and reliability, or prove an appropriate impossibility/boundary.
- Connect the capacity-reservation transfer and shortfall collateral in one
  report-and-delivery mechanism under a declared liability limit.
- Compare expected welfare with pure cheapest routing and a reliability-only
  baseline under a pre-registered heterogeneous-value welfare function and
  controlled value/cost/reliability observations. The current comparison is a
  known-primitive equal-value benchmark only.
- Estimate or externally validate a joint-outage panel and analyze limited
  liability rather than assuming fully collectible bonds or independent
  provider failures. The current max-min outage allocation is conditional on
  the supplied support, not evidence that the support is complete.

### Empirics

- Accumulate at least 6–8 weeks of coherent quote/quality panels.
- Clear H13 breadth gates with repeated, source-qualified direct prices; keep
  mapped one-to-one IDs distinguishable from literal provider IDs.
- Obtain finalized Uniswap swap/mint/burn data and a market-wide CoW
  settlement/auction source. Indexed pool state and latest-auction snapshots
  remain controls, not substitutes.
- Run a controlled, redacted routing study with provider/model/epoch
  commitments, selected attempts, allocated and served counts, and cost or
  margin fields. Register the model-epoch assignment ledger and stopping rule
  before the first epoch, then use H50's clustered treatment contrasts.
- Pre-register shocks, outcome variables, minimum event counts, inference
  clusters, negative controls, and stopping rules before dynamic estimation.

## Stop rule

Work may stop only after every gate above is supported by reproducible current
artifacts, theory claims have proofs matching their assumptions, and the paper
cleanly separates measured, power-gated, and proposed results. Until then,
collector additions and local mechanism counterfactuals are progress—not
evidence of an EC-ready paper.
