# Corrected-data manuscript rerun — 2026-07-17

This note records the public-data correction propagated into the focal
inference-market manuscript. It does not unblind or query H80, H81, or H95
outcomes.

## Pinned inputs

- Public dataset revision:
  b389923ad7713bc230dd522f770aa306bf778806
- Remote repair workflow: 29558374319
- Completed pricing-event dates: 2026-07-07 through 2026-07-16
- Open support date: 2026-07-17

The repaired endpoint panel has 2,004,680 distinct listing observations from
2,013,866 exact-distinct raw records and 2,116 capture runs. The 9,186
same-listing raw variants have availability-state differences only: the audit
finds zero price conflicts and zero capability conflicts. Every completed date
has zero exact duplicate source rows. The open July 17 buffer has 256 exact
duplicates, which listing-level analysis removes and completed-day event claims
exclude.

The derived ledger contains 3,219 events through July 16. A clean chronological
rebuild produces the same 3,219-event set with zero missing or unexpected
events.

## Corrected frozen nine-day results

| Analysis | Corrected result | Manuscript consequence |
|---|---:|---|
| Completion-price changes | 313 | Replaces the stale event-ledger count |
| Changes per provider-model day | 0.04257 | Implied inverse-frequency duration 23.5 days |
| Median absolute log change | 0.095 | Replaces 0.134 |
| Share of cuts | 70.3% | Replaces the approximate two-thirds statement |
| Raw pooled kurtosis | 215.27 | Replaces 113 |
| Within-provider standardized kurtosis | 6.23 over 307 events | Retracts the earlier “between menu cost and Calvo” reading |
| PM1 repricing hazard | 7,352 pair-days, 112 events | All reported likelihood and AUC evidence is now labeled in-sample |
| Gap/GPU block | LR p = 2.04e-6; in-sample AUC 0.879 | Descriptive association only |
| Congestion block | LR p = 0.419 | No incremental support |
| Rival-move block | LR p = 8.03e-5; in-sample AUC 0.884 | No temporal-validation claim |
| Cadence-only fast-provider coefficient | -0.0854, 95% CI [-0.1454, -0.0254] | Slow providers quote 8.9% more conditionally |
| Quality-adjusted fast-provider coefficient | -0.2906, 95% CI [-0.5493, -0.0319] | Smaller 451-observation, 25-model descriptive sample |
| Brown-MacKay temporal support | 2 waves; 0 slow-initiator response comparisons | Mechanism remains unidentified |
| Brown-MacKay predictive audit | MSE gain 0.000852; cluster bootstrap CI [0.000220, 0.026124]; 2 clusters; exact sign-flip p = 0.25 | Registered verdict remains predictively indistinguishable |
| Named-rival timing identified set | 243/313 uniquely ordered; sharp set [0, 77.6%] | No positive lower bound on quote-surface response |

## Cross-router update

H93 now has two snapshots per router over 0.054 days and no price event. H94 has
one eligible prospective snapshot per router after its activation cutoff, zero
prospective price transitions, and zero matched common shocks. Of the 29
simultaneous Hugging-Face-linked provider-model pairs, 28 have identical input
and output prices, but 28 also have at least one observed contract-term conflict.
Posted-price equality is therefore not contract equivalence.

## Claim changes

The corrected data strengthen provenance but weaken two substantive readings:

1. standardized price-change kurtosis is near the Calvo numerical benchmark,
   not between the simple menu-cost and Calvo benchmarks;
2. the repricing ladder has no checked-in out-of-time validation, so the earlier
   day-split AUCs are retracted.

The main positive public-data result remains that displayed prices and
operational state are distinct layers. The paper still lacks its focal released
randomized clearing effects because H81 and H95 remain below their frozen gates.

## Post-correction live accrual

After the repaired public release, workflow `29559930551` consolidated the
newest buffered randomized probes into immutable dataset revision
`1311e5e513c62b18594b1391bf62cf802fcc8688`. Outcome-free release audit
`29560437241` reports:

- H81: 80 verified first-position blocks, counts 31/23/26, with 9/17/14
  remaining; outcomes were not queried.
- H95: 3 compliant triplets, 9 first-position blocks, 8 unique models and
  effective model count 7.36; 117 triplets remain; outcomes were not queried.
- Remote-health run `29560495633` passed against the live workflows and data
  sink.

The new `pm1_temporal_validation` module is fail-closed at 10/30 completed UTC
dates. It excludes the represented but open July 17 date and does not query the
pricing-event table before the gate. At 30 completed dates it will fit on the
first 15, score the next 15 once, use prior-close covariates and training-only
provider controls, and apply Holm correction to the four adjacent-rung paired
log-loss contrasts. Commit `1719ade` additionally freezes training-standardized
ridge logistic regression with `C=1` and no holdout tuning. The primary L3 rung
has 17 parameters; promotion requires 10 training events and nonevents per
parameter, 50 test events and nonevents, 10 train/test event dates, and 10 test
models. A failed support gate remains an insufficient-support result.

## Verification

- Ruff passed for the corrected PM2 analyzer, vintage test, and paper-rerun
  harness.
- The focused provenance/vintage suite passed: 20 tests.
- The full repository suite passed: 540 tests (warnings only).
- The manuscript compiled successfully to a 31-page PDF.
- The updated sample table, hazard table, Brown-MacKay figure, and cross-router
  figure were rendered and visually inspected.
