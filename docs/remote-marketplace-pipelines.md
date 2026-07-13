# Remote marketplace data operations

All recurring capture and monitoring runs on GitHub-hosted Actions and writes
to the private Hugging Face dataset `t4run/openrouter-market-history`.  No
scheduled collector depends on a laptop, local cron, `tmux`, or a local data
directory remaining online.

## New remote pipelines

| Workflow | Schedule | Output | Boundary |
|---|---:|---|---|
| `marketplace-history.yml` | daily 06:19 UTC | OpenRouter top-50-plus-other model-day tokens and top-200 public attributed app-day rankings | aggregate/censored; no inference calls, app-by-model routing, or provider selection |
| `bittensor.yml` | every six hours | block-pinned Chutes subnet 64 neurons and complete validator-to-miner weight matrix | public scoring/reward allocation, not requests or delivered inference |
| `market.yml` | hourly | DeFi/open-compute sources plus recent Akash leases, retained bids, and bounded indexed bid-create events | public procurement contracts/events, not workload delivery |
| `remote-health.yml` | every six hours | latest-run status for every critical workflow plus age of the HF data sink | operational liveness, not source-level economic validity |

The remote watchdog fails if the newest terminal run failed, if the newest run
is outside its source-specific schedule SLO, or if the Hugging Face dataset has
not received a commit within 30 hours.  Its JSON report is retained as a
30-day Actions artifact.

Changes to the compactor, Bittensor collector, or aggregate-history collector
also launch a hosted smoke run on `main`. A successful compaction launches the
memo workflow through `workflow_run`; the daily schedules remain independent
fallbacks. This makes deployment verification and analysis chaining remote as
well, without requiring an operator laptop or an authenticated local CLI.
A successful memo immediately launches the full remote-health check, in
addition to the six-hour watchdog schedule.

## Required remote secrets

| GitHub Actions secret | Purpose |
|---|---|
| `HF_TOKEN` | write access to the private dataset and memo Space |
| `OPENROUTER_API_KEY` | one-token realized-routing probes and read-only documented aggregate datasets |

Optional market-source secrets and variables remain in `market.yml`.  Secrets
are passed only through job environments; collectors do not retain
authorization headers or tokens in raw evidence.

## Historical OpenRouter backfill

The app endpoint is limited to 500 account requests/day. Each full top-200
app-day normally consumes two requests. A manual collector invocation is capped
at 200 days; the automated workflow uses 20-day sub-invocations and can cover a
slightly longer interval while remaining under the daily request limit. It
performs the following non-overlapping intervals on
GitHub-hosted runners, alongside the latest closed day, and then automatically
stops backfilling:

| Scheduled UTC day | Historical interval | Maximum app requests |
|---|---|---:|
| 2026-07-13 | 2025-01-01 through 2025-05-28 | 296 |
| 2026-07-14 | 2025-05-28 through 2026-01-13 | 462 |
| 2026-07-15 | 2026-01-14 through 2026-07-12 | 360 |

Each run uses another two requests for the latest closed day, remaining below
the documented 500-request account limit. A deployment commit containing the
literal marker `[history-backfill]` also executes the current UTC day's chunk;
ordinary pushes only smoke-test the latest closed day. Manual recovery remains
available:

The July 13 run stopped on the second page of May 28 after preserving its
earlier complete days and first-page evidence. The July 14 interval therefore
replays May 28 in full. The collector retries a malformed page up to three
times, and a source day counts as complete only after every required page has
validated.

```bash
gh workflow run marketplace-history.yml \
  -f start_date=2025-01-01 -f end_date=2025-07-19

gh workflow run marketplace-history.yml \
  -f start_date=2025-07-20 -f end_date=2026-02-04

gh workflow run marketplace-history.yml \
  -f start_date=2026-02-05 -f end_date=2026-07-12
```

Both collectors execute each historical interval as bounded 20-day chunks.
Each chunk uses one model-ranking request; the app collector requests one UTC
day at a time within the chunk, preserves every raw page, rejects
date/rank/schema mismatches, and never turns an absent rank into zero usage.
Chunking avoids oversized aggregate responses and preserves completed portions
of a long backfill. The workflow pushes partial raw and curated evidence before
surfacing a degraded quality gate, so a late throttle does not discard earlier
successful chunks.

## Remote recovery jobs

The nightly compactor runs at 04:13 UTC with a 120-minute limit. The memo and
analysis publication runs at 05:13 UTC, hydrates the private dataset with eight
bounded workers, and has a 120-minute job limit. Both publish remotely; a local
HTML copy is optional and is not part of data capture, analysis durability, or
dashboard publication.

## Akash procurement capture

The legacy provider-wide open-book sweep is now an explicit diagnostic:

```bash
uv run orcap market-capture --with-akash --with-akash-open-book
```

It is not on the hourly critical path because the public endpoint returned
incomplete responses for 17 of 33 live GPU providers and took roughly 50
minutes in the 2026-07-13 live audit.  The hourly remote path instead uses:

1. the latest 50 public leases;
2. complete paginated current-state bid queries for 25 recent orders; and
3. a complete, overlapping 1,000-block `MsgCreateBid` transaction window.

The indexed event window restores losing bid IDs and prices that have already
disappeared from current state.  H76 links them to selected public lease IDs.
The output remains power-gated until it has 1,000 multi-provider orders across
30 days.

## Analyses

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h72  # public apps
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h75  # Bittensor weights/rewards
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h76  # Akash bid-to-lease choice
```

H72 requires 90 complete public-app days. H75 requires 90 complete metagraph
snapshots over at least 21 days. H76 requires 1,000 multi-provider choice sets
over at least 30 days.  These gates prevent the first live observations from
becoming headline conclusions.

## Verification commands

```bash
gh workflow list --all
gh run list --limit 40
gh workflow run remote-health.yml
gh run watch --exit-status
```

For a source-level audit, download or hydrate the HF `source_runs` table and
inspect the latest row per source.  A scheduled workflow file is not evidence
that a collector is healthy; the Actions conclusion and remote source-run row
must both exist.
