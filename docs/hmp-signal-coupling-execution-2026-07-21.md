# HMP signal-coupling execution report

Date: 2026-07-21 UTC.

## What is running

WF-18 is implemented as a fixed-rule remote monitor plus a separate one-time
support-gated release workflow. Both freeze an immutable Hugging Face dataset
revision. The monitor reruns after successful compaction and weekly; it publishes
only aggregate tables and a self-contained HTML dashboard. The owned request risk
set is deleted before publication. Remote health treats a 30-hour-old monitor as
stale.

The release workflow cannot publish unless the assignment-only sample screen and
the full outcome-aware support gate both pass. It computes the release candidate,
checks concentration and claim boundaries, hashes the exact summary into an
immutable promotion marker, and only then publishes. Public prices are observable
during accrual, so the marker freezes promotion and publication rather than
pretending to be first outcome access.

## First pinned monitoring result

Source revision:
`aeb7f165669888514548170606fd3a29b1d0fb5f`.

The panel spans 2026-07-07 through 2026-07-19. It contains 686 completion-price
events across 44 models and 10 providers. The chronological mechanism window has
6 days, 253 events, 35 models, 19 realized provider-pair/model clusters, and 48
covered delegated choices.

The primary 24-hour residual-coupling statistic is `0.01659`. Relative to 2,000
clock-preserving circular shifts, the excess is `0.01874`, with one-sided
`p = 0.10995`; the null 95% interval is `[-0.03056, 0.02444]`. This does not reject
the null. The largest provider pair supplies 76.7% of paired events, above the
frozen 20% cap. Leave-one-provider/model estimates range from `-0.00051` to
`0.06132`, so the sign is not influence-robust.

The 1-hour, 6-hour, and 168-hour descriptive covariances are `0.06002`, `0.06297`,
and `0.03886`. The apparent signal is strongly lead-lag asymmetric: the two frozen
directions are `-0.01639` and `0.13135`. Removing public enforcement windows leaves
only seven pair-model clusters. These are diagnostics, not additional discoveries.

SC2 is power-gated because no owned-routing provider/model cell has enough
leave-date-out preperiod choices. SC3 has 165 potential pair/model cohorts but zero
with the frozen 200-choice minimum. The SC1--SC4 Holm family is therefore
incomplete and no claim can promote. The current result is, at most, weak and
concentrated evidence of residual quote synchronization; it is not evidence of
HMP learning, tacit collusion, communication, intent, or a deployed UCB algorithm.

## Simulation result

The exact marginal-preserving signal-order intervention behaves as predicted in
the focal two-UCB-agent environment: for positive common correlation, SNR at least
2, and router exponent 5, coupled signals raise exploration coupling, all-high
play, and mean buyer price. In the one-seed smoke grid the mean buyer-price effect
is `+0.12975`, positive in 72.2% of focal cells.

The result does not transport robustly. Across epsilon-greedy and static-agent
mixtures, the mean buyer-price effect is `+0.00343` and is positive in only 52.8%
of cells. The executable verdict is therefore `mechanism_validated=false` until
the full seed grid and heterogeneous-strategy screen pass.

## Exact blockers

The frozen release gate currently fails four objects:

- 6 of 28 required mechanism days;
- 19 of 20 realized provider-pair/model clusters;
- 48 of 1,000 covered delegated choices; and
- 76.7% versus at most 20% maximum provider-pair event share.

Models, public price experiments, and price-changing pair support already pass.
The recurring market-measurement collector continues to create assignment-first
owned default choices independently of this laptop. Its calendar horizon is
extended through 2026-09-30 without increasing the `$20` campaign cap; at the
present 16 eligible choices/day cadence, the 1,000-choice gate should be reached
around late September. The release workflow should not be manually dispatched
until the monitor reports all support checks true.

## Reproduction

```bash
ORCAP_HF_REVISION=aeb7f165669888514548170606fd3a29b1d0fb5f \
  uv run orcap analyze --hypothesis wf16 \
  --out data/analysis/hmp-signal-coupling-v1

ORCAP_HF_REVISION=aeb7f165669888514548170606fd3a29b1d0fb5f \
  uv run orcap analyze --hypothesis wf18 \
  --out data/analysis/hmp-signal-coupling-v1

uv run python -m orcap.market_env.experiments_signal_coupling \
  --out data/analysis/hmp-signal-coupling-v1/simulation
```
