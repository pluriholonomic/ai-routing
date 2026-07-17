# Independent-style review, round 18

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **6.5/10, reject with a credible resubmission path.**

## What improved

1. **The public-input provenance is now auditable.** The manuscript pins repaired
   revision b389923, distinguishes listing observations from exact-distinct raw
   records, discloses the historical overlap bug, and reports an exact
   3,219-of-3,219 chronological event rebuild.
2. **Incorrect descriptive statistics were not preserved.** The price-change
   frequency, size, cut share, and kurtosis were recomputed from the corrected
   ledger. The standardized kurtosis changes from 3.54 to 6.23, and the paper
   explicitly retracts the earlier structural reading.
3. **Unsupported validation language was removed.** The checked-in hazard module
   produces in-sample AUC only. The paper retracts the earlier day-split AUC
   claims and labels the entire nine-day ladder descriptive and power-gated.
4. **The Brown-MacKay audit is internally consistent again.** Prose and figure
   now use 313 price events, 243 linked reactions, two frozen waves, two
   predictive clusters, and an exact sign-flip p-value of 0.25.
5. **Cross-router equality is better bounded.** The paper now reports the second
   catalog snapshot, the single prospective H94 snapshot per router, and the
   observed contract-term conflicts that prevent treating equal token prices as
   equal contracts.

## Remaining reasons for rejection

### 1. The focal causal result is still absent

H81 and H95 remain below their frozen release gates. The manuscript's organizing
claim is a randomized decomposition of fallback and delegated selection, but it
still reports no effect size, interval, missingness bound, or model sensitivity
for either primary contrast.

### 2. The main public-price evidence is short and in-sample

The corrected nine-day hazard ladder is useful descriptive market
microstructure, but it cannot support a general statement about state-dependent
or strategic repricing. The registered 30-day vintage and a genuine temporal
validation remain necessary.

### 3. The price-atom section is larger than its identifying content

The section correctly concludes that public menus cannot distinguish scheduled
refreshes from rival-triggered response. For a focal hidden-clearing paper, the
long simulation and sharp-bound development still consumes too much main-text
space relative to the unreleased clearing experiment.

### 4. The manuscript remains long for the current result density

The corrected PDF is 30 pages before a released focal result. A conference
version should move most price-atom simulations, the revenue-share accounting
theorem, and extended proof audits to an online appendix once H81/H95 are
available.

## Acceptance conditions

1. Release H81 at its unchanged 40-per-arm gate and report both primary
   contrasts with design-based inference and worst-case missingness bounds.
2. Complete H95 separately and report all transport gates and leave-one-model-out
   diagnostics, whether positive or null.
3. Run the frozen 30-day public-data vintage and add a genuine time-based
   validation whose implementation and output are both checked in.
4. Compress the main paper around the realized clearing decomposition; retain
   the corrected public-price and cross-router evidence as mechanism-motivating
   support.

## Decision

The correction lowers the numerical score because it removes a purported
out-of-sample result, but it materially improves trustworthiness. The paper now
states what the current data actually identify. Its remaining blocker is the
missing focal randomized evidence, not another prose pass.
