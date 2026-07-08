# H18 — Interpretable prediction of repricing events

Goal: an interpretable classifier for "will this price change over the next
window?", evaluated out-of-time with ROC-AUC (and PR-AUC — the base rate is
~2.7%), plus a conditional direction model (cut vs raise). Interpretability
first: logistic regression + shallow gradient-boosted trees, coefficient and
permutation-importance tables, calibration check.

## Two model layers

**Layer 1 (train NOW): model-level, Wayback panel 2023-26.**
Unit = consecutive snapshot pair (model, t0→t1); n≈39.5k pairs, ~1.1k positives.
Target: `changed` = listed completion price differs at t1.
Secondary target: `direction` (cut vs raise) conditional on change (n≈1.1k).

**Layer 2 (pre-registered, train at ~4-6 weeks): endpoint-level, live panel.**
Same design at 5-min/daily resolution with the H16/H17 covariates that layer 1
cannot see: utilization (peak_rpm/capacity ceiling), reject spikes, p90
latency, competitor moves in past 48h, provider-wave indicators, reversal
history. Expected to dominate layer 1 — pre-registering it now keeps the
comparison clean.

## Features (all computable at t0 — no future information)

- Lifecycle: model age (log days), created-recently flags
- History: # prior changes, days since last change, never-changed flag,
  # snapshots observed
- Price position: log price, price percentile across market at t0,
  percentile within author at t0
- Competition: # models by same author at t0, days since author's latest
  launch, # market-wide launches in prior 30d
- Demand (post-2025-07 only, missing-flagged): weekly tokens at week(t0),
  4-week token growth (rankings_weekly)
- Calendar: month index (secular drift), snapshot-density regime
- **Exposure**: gap_days (t1−t0). Reported SEPARATELY — a long gap
  mechanically raises P(change), so headline AUC is reported both with and
  without exposure features; the no-exposure number is the honest signal
  measure.

## Anti-leakage protocol

- **Temporal split**: train on pairs with t1 ≤ 2026-01-31; test on
  t1 ∈ (2026-02-01, 2026-07-07]. No random splits (history features would
  leak regime).
- All rolling features computed strictly from data ≤ t0.
- No model-identity features (no model_id one-hots) — the model must predict
  from characteristics, not memorize serial repricers; author is allowed only
  as coarse top-K categories (a real, observable trait).

## Models & evaluation

- LogisticRegression (standardized, class_weight=balanced) — the coefficient
  story.
- HistGradientBoostingClassifier (max_depth 3) — interaction ceiling.
- Report: ROC-AUC, PR-AUC vs base rate, calibration decile table,
  logit coefficients, permutation importance, and the exposure-stripped AUC.
- Direction model: same features, logistic, AUC for cut-vs-raise.
- Success bar: no-exposure ROC-AUC ≥ 0.75 with a coherent coefficient story
  (age young ⇒ more likely; recent-change ⇒ more likely; etc.). If the tree
  beats the logit by >0.05 AUC, report which interaction does it.

## Implementation

- `src/orcap/analysis/h18_predict.py`: dataset builder (DuckDB over wayback +
  models + rankings_weekly), feature matrix, temporal CV, both models,
  outputs `h18_dataset.parquet`, `h18_summary.json`, coefficient/importance
  parquets. CLI: `orcap analyze --hypothesis h18`.
- New dep: scikit-learn.
- Test: synthetic panel with planted lifecycle signal (P(change) declining in
  age) — builder + logit must recover AUC > 0.85 and the right sign.
- Results pushed to HF under analysis/; layer-2 spec pre-registered in the
  memo's phase-2 list.
