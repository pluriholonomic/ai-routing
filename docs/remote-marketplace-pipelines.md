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

## Required remote secrets

| GitHub Actions secret | Purpose |
|---|---|
| `HF_TOKEN` | write access to the private dataset and memo Space |
| `OPENROUTER_API_KEY` | one-token realized-routing probes and read-only documented aggregate datasets |

Optional market-source secrets and variables remain in `market.yml`.  Secrets
are passed only through job environments; collectors do not retain
authorization headers or tokens in raw evidence.

## Historical OpenRouter backfill

The app endpoint is limited to 500 account requests/day.  Each full top-200
app-day normally consumes two requests, so one workflow run is capped at 200
days.  Backfill with non-overlapping dispatches on separate quota days:

```bash
gh workflow run marketplace-history.yml \
  -f start_date=2025-01-01 -f end_date=2025-07-19

gh workflow run marketplace-history.yml \
  -f start_date=2025-07-20 -f end_date=2026-02-04

gh workflow run marketplace-history.yml \
  -f start_date=2026-02-05 -f end_date=2026-07-12
```

The model-ranking request covers each whole interval in one API call.  The app
collector requests one UTC day at a time, preserves each raw page, rejects
date/rank/schema mismatches, and never turns an absent rank into zero usage.

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
