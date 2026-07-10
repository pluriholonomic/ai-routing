# Full-data audit — 2026-07-09

## Scope

The audit mirrored the authoritative `t4run/openrouter-market-history` dataset,
replayed the missing local derivations without modifying the remote dataset, and
ran `orcap analyze --allow-partial` against that repaired mirror.

## What the full rerun changed

The authoritative store contains 533 raw API captures and 384 curated endpoint
snapshots across 2026-07-07 through 2026-07-09. The published
`derived/pricing_changes` layer, however, contained only the 2026-07-07
partition. Replaying the 2026-07-08 and 2026-07-09 folds produced 59 usable
completion-price events (up from 11) and 852 all-field endpoint events.

| Result | Repaired result | Boundary |
|---|---:|---|
| H4 routed-share / price elasticity | -1.177 (SE 0.116), 3,125 observations | Daily effective-pricing data; not a clean default-router-only experiment. |
| H17 live completion-price events | 59 | Three-day live cohort; descriptive classifications only. |
| H21 follow pairs | 459; 56.4% within 24h | Clears the 100-pair readiness gate, but 59/200 price events remain below the event-study gate. |
| H37 Hawkes screen | 59/100 events | Counting cascade statistic only; no Hawkes MLE claim yet. |
| H42 quote events | 52 eligible; 5 rank-crossing cuts | The density test is still 3/40 near-threshold observations. |
| H42 flow windows | 24 quote-eligible events with balanced flow coverage; R2 3/20, R3 4/20 clean effect cohorts | Public rolling 30-minute request counts; no literal front-running or private-flow claim. |
| H20 demand-price screen | 131 models with recovered HF stats; 16 reprice model-days | Two HF snapshots and a short live event history make this preliminary. |

## Findings and root causes

1. **Derived event ledger stalled, while source data continued to arrive.** The
   scheduled compaction run on 2026-07-09 was cancelled at exactly the
   30-minute job limit during `compact + derive pricing changes`. This explains
   why raw and curated data were present but the price-event research cohort
   appeared to stop at 11 observations.

2. **The captured HF demand data was not published as a curated table.** Two
   raw `hf_stats` files contained 268 valid rows (134 per day), but
   `hf_model_stats_daily` was absent remotely. The audit reconstructed it only
   in the disposable mirror; the authoritative dataset needs a one-time raw
   recovery or a fresh `capture-hf` publication.

3. **Every historical event-burst stats request failed.** All 189 requests to
   the frontend stats endpoint returned HTTP 404. Burst code supplied stable
   model IDs, whereas the endpoint expects the versioned canonical permaslug.
   The historical response bodies contain no flow data to recover.

4. **The event-flow join had the same identifier mismatch.** Quote events use
   stable model IDs and `congestion_intraday` uses canonical permaslugs. The
   full rerun initially dropped most flow coverage until it mapped the ids via
   `models_snapshots`.

5. **The DeFi/open-compute comparator is still unpopulated.** The four
   canonical comparison tables (`market_participants`, `market_executions`,
   `market_quotes`, and `market_capacity`) are absent. H41 therefore remains
   correctly gated; no comparative liquidity, fill, or capacity claim is
   available.

## Improvements made in this checkout

- Increased the compaction job limit from 30 to 60 minutes and limited remote
  hydration to pricing-critical endpoint snapshots. The prior all-table path
  can hit the Hub file-API quota before it writes the derived ledger.
- Made H17 and H42 tolerate all-missing nullable congestion fields instead of
  aborting a full analysis.
- Mapped stable model IDs to canonical slugs for both future burst sampling and
  H42's congestion join. Future event bursts should record usable
  `event_bursts_congestion` rows instead of 404s.
- Added regression coverage for canonical identifier mapping and nullable flow
  aggregation.

## Remaining priority work

| Priority | Action | Why it matters | Completion check |
|---|---|---|---|
| P0 | Run/publish a backfill for the missed 2026-07-08 and 2026-07-09 compactions, including the raw HF-stat recovery. | Restores the authoritative price-event and H20 inputs. | `pricing_changes` has partitions for all captured days; `hf_model_stats_daily` has two historical partitions. |
| P0 | Deploy the canonical-slug burst fix and alert on non-2xx stats responses. | Restarts accumulation of balanced H42 flow windows. | `event_bursts_congestion` receives rows and source health reports no 404s. |
| P1 | Add idempotent, resumable daily folds with per-day completion manifests. | A time-limit cancellation must not leave raw data ahead of derivations. | A rerun resumes safely and reports raw/curated/derived counts per day. |
| P1 | Populate the four H41 market tables from finalized Uniswap swaps/depth, CoW settlements, and Akash/Golem offers/capacity. | Required for a real DeFi-versus-open-compute comparison. | H41 reports sources, markets, and comparable time-series metrics. |
| P1 | Expand direct-provider pricing beyond DeepInfra and preserve quote timestamps. | Needed to separate quote passthrough from stale-quote or last-look behavior. | At least several providers with repeated synchronized quotes. |
| P2 | Accumulate 20 clean R2/R3 events, 40 near-threshold observations, and 100 event times for Hawkes MLE. | Current MEV-like and Hawkes results are power-gated. | H42 and H37 gates clear with preregistered placebo/pretrend checks. |
| P2 | Extend daily effective-pricing, activity, HF, and devrel panels. | H4/H20/H29 are currently short-panel or mixed-routing evidence. | Six to eight weeks of consistent daily coverage. |

## Verification

The repaired mirror completed the full analysis after targeted H17 and H42
reruns. H41 remains intentionally gated on its absent market-source tables.
`ruff`, all tests, and `git diff --check` pass; the test suite has 30 passing
tests (the existing H18 synthetic-time warnings remain).
