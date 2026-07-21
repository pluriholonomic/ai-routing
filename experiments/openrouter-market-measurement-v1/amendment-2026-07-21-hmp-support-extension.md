# Market-measurement duration extension for WF-18 support

Date: 2026-07-21 UTC.

The assignment-first `openrouter-market-measurement-v1` campaign end is extended
from 2026-07-26T18:45:00Z to 2026-09-30T23:59:00Z. This amendment changes only the
calendar horizon. It does not change block selection, arms, payload handling,
assignment order, execution isolation, per-run or rolling-day limits, or any
analysis threshold.

The `$0.50` per-run, `$3.00` rolling-day, and `$20.00` campaign caps remain frozen.
The first 48 WF-18-eligible default choices cost approximately `$0.00613` in total.
At four scheduled runs per day and four `default_broad` replicates per run, the
extension is expected to reach the frozen 1,000-choice WF-18 support threshold in
roughly 60 additional days. This is a support-accrual calculation, not an effect
based stopping rule. The campaign still stops immediately on any budget, source,
manifest, duplication, privacy, or integrity failure.

WF-18 uses only delegated default policies for its primary routing SNR and
elasticity panels. The other market-measurement arms retain their original
estimands and are not relabeled as default-routing observations.
