# Independent-style review, round 8

Manuscript: *Displayed Is Not Deliverable: Capacity Certificates and Quote
Firmness in Inference Routing*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **6/10, weak reject; the identification and audit package is
now credible, but the confirmatory routing effects remain power-gated.**

## Summary

This revision combines a capacity-certificate mechanism with a measurement
design for provider-level quote firmness. Its most useful empirical object is
the three-arm decomposition of router value into fallback option value and the
incremental value of delegated selection. The revision now distinguishes the
eligible public-rank population from all candidate model-hours, proves the
corresponding non-identification statement, and reports design-based bounds for
secondary outcomes with missing accounting fields.

The prospective implementation has also improved. H80 has 16 verified
first-position blocks, and H81 has six. All assignment replays pass; all H81
treatment controls pass; no gated outcome field is released. A new H81
candidate table records both sampled ranks even when they produce no attempts.
Its first run contains two eligible candidates, one with 25 distinct positive
price providers and one with three. The earlier four H81 blocks are correctly
labeled left-truncated rather than retroactively treated as a complete funnel.

The Brown--MacKay refresh uncovered an important analysis defect. Full-panel
cadence labels used future repricing events and were unstable at a discrete
threshold: one additional NextBit event changed its class and reduced the focal
risk set from 15 to three. The authors disclose this and replace the promoted
screen with cadence labels frozen on the first 70% of events, later evaluation
waves, and complete 24-hour response windows. The corrected evaluation set has
21 waves and 124 risk pairs but no slow-initiator/fast-responder exposure. This
is a non-estimability result, not evidence of no response. The old full-panel
result remains as an explicitly outcome-adaptive sensitivity.

## Material improvements

1. **Target population is explicit.** The eligible-block treatment effect is
   no longer allowed to stand in for all ranked model-hours.
2. **Missing accounting is handled without complete-case substitution.** The
   analysis reports arm-sample and logged-propensity Horvitz--Thompson support
   bounds. A default arm with no valid public quote cap remains upper-unbounded.
3. **Repeated support is visible before outcomes.** H80 support is exactly four
   models with 25% dominance and effective model count four. H81 support is two
   models with 50% dominance and effective model count two.
4. **The funnel survives zero-attempt runs.** Candidate eligibility is now a
   separate payload-free table, so an excluded rank cannot vanish from the
   denominator.
5. **The pricing-technology screen now respects time.** Freezing the cadence
   label before the holdout removes a genuine future-information leak. The
   disclosed correction increases credibility despite weakening the result.
6. **Off-machine durability is demonstrated.** Post-amendment H80 and H81
   artifacts were consolidated into the authoritative remote dataset, and the
   chained full analysis rerun completed successfully as GitHub Actions run
   `29415372629`. The published analysis excludes all 98 outcome-blinded
   attempts from legacy policy aggregates, preserves both release gates, and
   passed the downstream remote-health check in run `29416281936`.

## Remaining major concerns

### 1. There is still no confirmatory routing effect

H80 arm counts are `(5, 2, 2, 7)` and H81 counts are `(3, 1, 2)`, versus the
fixed 40-per-arm release gates. A top empirical venue cannot evaluate magnitude,
precision, or economic importance until the deterministic earliest balanced
prefixes are released. The launch aggregates remain analyst-visible and must
remain disclosed.

### 2. H81 external support is narrow

The current six blocks repeat two models. This is acceptable for the
finite-block causal estimand but weak for market-wide interpretation. The
candidate table has only one run, so temporal eligibility turnover is not yet
estimable. Subsequent reviews should show the run-by-run funnel and adjacent
support Jaccard before showing outcomes.

### 3. The capacity mechanism is not directly tested

The experiment identifies the value of fallback and delegated selection. It
does not identify the welfare effect of collateral, audits, capacity caps, the
robust allocation, or VCG payments. The mechanism is a disciplined design
implication unless a commitment intervention is added.

### 4. Brown--MacKay is now cleaner but less informative

BM3 retains a descriptive 10.5% slow-provider premium. Frozen-label BM4 modestly
improves both MAE and RMSE, but the corrected BM2 holdout contains no focal
exposure and the panel spans only 7.53 of the required 30 days. The joint
competitive-null gate therefore fails. No collusion or algorithmic-reaction
language is warranted.

### 5. Latency remains selected on success

The 60-second request timeout supplies finite support for recorded successful
latency, but a latency contrast among successful requests is not an ITT latency
effect and not a principal-stratum estimand. The manuscript states this
correctly; tables must preserve that label.

## Required package for the next decision

1. Release only the deterministic earliest H80 and H81 prefixes meeting every
   40-per-arm gate.
2. Put assignment replay, treatment compliance, candidate eligibility,
   repeated-model support, and missingness ahead of outcome estimates.
3. Report H80's three primary and H81's two primary contrasts with the
   preregistered intervals, randomization tests, model-stratified HT estimates,
   and Holm adjustment.
4. Report the fallback-plus-selection accounting identity and its numerical
   equality to total delegation as a secondary check.
5. Keep default-arm spend bounds upper-unbounded whenever the selected provider
   can leave the captured public set.
6. Treat cross-study H80/H81 agreement as validation, not pooling, because the
   ranked-model support differs.
7. Keep the corrected Brown--MacKay screen frozen and the original full-panel
   result explicitly post-result and outcome-adaptive.

## Decision

**Weak reject today.** The paper has moved from a promising but fragile design
to a credible preregistered measurement system with unusually strong audit
boundaries. The remaining barrier is empirical rather than architectural. An
accept becomes plausible if a frozen cut precisely identifies at least one of
fallback or delegated-selection value, the effect is stable across the repeated
model support, and the mechanism section is presented as a design response
rather than as experimentally validated welfare improvement.
