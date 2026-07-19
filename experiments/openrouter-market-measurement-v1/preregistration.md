# OpenRouter market measurement v1

Status: frozen before the first paid execution

Study ID: `openrouter-market-measurement-v1`

## Purpose

This campaign measures three objects that the public quote panel cannot identify:

1. **choice competition**: how owned requests are allocated when the eligible
   provider set, price cap, ordering rule, or router sort rule changes;
2. **executable liquidity**: whether a quoted endpoint accepts a small synchronized
   batch at its posted price, and how success and latency change with concurrency;
3. **quality-adjusted generalized cost**: whether provider-level price and latency
   differences for the same model are accompanied by differences on a small paired,
   public, automatically graded task set.

The campaign is an owned-traffic audit. It does not observe market-wide flow,
cross-user request order, private router scores, provider costs, capacity stocks,
or provider intent. It cannot by itself establish front-running or collusion.

## Isolation and relation to prior studies

- H81 is immutable and is never queried, rerun, amended, or pooled here.
- H95 remains blinded until its fixed 120-triplet horizon. This campaign never
  reads H95 assignments or outcomes and is not pooled with H95.
- The campaign uses the dedicated `OPENROUTER_PRICE_EXPERIMENT_KEY`, a distinct
  study ID, fresh hashed sessions, and the shared `randomized-routing-probes`
  concurrency lock. The lock prevents temporal overlap with H95 and the existing
  paid calibration workflows.
- Existing public price-response and price-event studies remain separate. Their
  estimands may later be compared descriptively, but their assignments are not
  treated as randomized observations from this campaign.

## Assignment-first protocol

Every run has a plan job and, optionally, an execution job.

1. The plan job downloads only the authoritative spend ledger and public endpoint
   menus.
2. It freezes candidate rows, scores eligible model-shape blocks using only the
   public menu, creates all assignments, and hashes candidates, assignments, and
   the run summary into one immutable manifest.
3. The immutable bundle is uploaded before any paid request.
4. Execution consumes exactly that uploaded bundle. It never regenerates or
   changes assignments.
5. Duplicate task IDs already present in the spend ledger cause a hard failure.

Manual workflow dispatch is no-spend by default. A paid manual canary requires the
explicit `execute_paid=true` input and all repository gates below.

## Sampling frame and block selection

The default sampling frame is the configured hot-model list, with the same
`short_chat` compatibility checks used by the route-calibration collector. A block
is eligible when at least three distinct providers have positive prompt and
completion prices, exact endpoint tags, and sufficient context/output capacity.

The run selects at most one block. The public-only information score is

\[
  S_b = \log(1+n_b)\,\log(p^{\max}_b/p^{\min}_b),
\]

where prices are conservative request quote caps. Ties are resolved by the frozen
run seed. This prioritizes menus with both choice and price dispersion without
using paid outcomes.

## Arms

### A. Competition and router-rule arms

Within the chosen block, assignments include:

| Policy | Replicates | Intervention |
|---|---:|---|
| `default_broad` | 4 | default routing, broad rectangular price cap |
| `price_sorted` | 2 | broad cap plus router `sort=price` |
| `capped_top2` | 2 when separable | rectangular cap admitting exactly two cheapest providers |
| `ordered_ab` | 1 | cheapest endpoint ordered before second-cheapest |
| `ordered_ba` | 1 | reverse order |
| `leave_cheapest_out` | 2 | broad cap, cheapest endpoint excluded |
| `pinned_a` | 1 | exact cheapest endpoint, no fallback |
| `pinned_b` | 1 | exact second-cheapest endpoint, no fallback |

Primary descriptive estimands are policy-level success, selected-provider shares,
selection concentration, latency, cost, and paired changes relative to
`default_broad`. These are controlled-policy effects on owned requests, not global
market shares.

### B. Memory arms

`default_sticky_seed` and `default_sticky_repeat` share a hashed session while
using distinct inert nonces. Their order is frozen in the plan. The estimands are
same-provider persistence and the change relative to independent default requests.
This diagnoses session/path dependence; it does not reveal the router's internal
memory state.

### C. Executable-liquidity arms

The cheapest and second-cheapest exact endpoints each receive synchronized pinned
batches at concurrency levels 1, 2, and 4. Every request has fallback disabled.
The batch estimands are:

- success and measurement-missing rates;
- median and tail latency;
- realized cost relative to the frozen quote cap;
- an executable-depth lower bound equal to successful requests in the batch.

This is a tiny owned-load stress test. It does not estimate total provider capacity.

### D. Paired quality arms

Two MMLU items are selected deterministically from the versioned public item pool.
For each item, the same model is sent under `default_broad`, `quality_pinned_a`, and
`quality_pinned_b`. Temperature is zero and the output cap comes from the item.
Only extracted answers, correctness, output hashes, token counts, latency, cost,
status, and selected provider are retained. Prompt and completion text are discarded.

Quality-adjusted generalized cost is reported as a vector, not a scalar welfare
claim: `(accuracy, success, latency, realized cost)`. Monetary conversion of quality
or latency requires an externally declared value-of-quality/value-of-time and is
therefore sensitivity analysis only.

## Budget and stop rules

Paid execution requires all of:

- `ORCAP_PAID_PRICE_STUDIES_ENABLED=true`;
- `ORCAP_MARKET_MEASUREMENT_ENABLED=true`;
- a dedicated key;
- an open campaign interval;
- source-health and nonempty-plan gates;
- run, rolling-24-hour, and campaign quote-cap checks.

Initial deployment limits are intentionally small: `$0.50` per run, `$3` per
rolling day, and `$20` for the first campaign. Quote caps, rather than expected
cost, are checked before requests are sent. The campaign stops on any budget breach,
manifest mismatch, missing source, duplicate task, privacy-contract violation, or
monitor integrity failure. Raising a limit requires a new dated amendment; it does
not silently modify this frozen protocol.

## Analysis and reporting

The recurring monitor reads only this study's tables from a pinned Hugging Face
dataset revision. It writes run health, policy, liquidity, memory, and quality
panels plus a compact HTML dashboard and machine-readable claim-boundary report.

No significance star is treated as evidence of market-wide welfare, capacity,
front-running, or collusion. Confirmatory causal language is limited to the owned
request controls randomized in this protocol. Provider- or model-specific ranking
is suppressed below the preregistered minimum of 20 realized observations per cell.

## Remote evidence path

GitHub Actions is the execution authority. Run artifacts are immutable and retained
in Actions, then assembled by nightly `compact.yml`, uploaded to the private
`t4run/openrouter-market-history` Hugging Face dataset, and deterministically
compacted. The monitoring workflow downloads a pinned dataset revision, publishes
aggregate outputs back to the dataset, preserves a CI artifact, and refreshes the
private `t4run/openrouter-memo` Space. No local computer is required after deployment.
