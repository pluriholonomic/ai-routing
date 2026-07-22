# Information-congestion v1 execution status

Checked 2026-07-22. Protocol SHA-256:
`28bfd5598a871894e5d2dd925ff331215810b6ccb3d25af38418f72bc05ec1af`.

## What is operational

- An hourly plan-first randomized `n x k x overlap x router-rule` workflow.
- A separate six-hour, balanced exact-pin quality workflow.
- An independent two-hour capture backstop that takes 23 five-minute samples.
- A daily outcome-blind monitor and public-shock registry.
- A marker-first, one-time confirmatory release with a strict assignment-only
  28-day preflight before any private outcome is downloaded.
- Private-HF checkpoints for attempts, grades, and spend; public artifacts hold
  assignments, hashes, support counts, aggregates, and no request payloads.

## Immutable remote-data audit

Source: private dataset `t4run/openrouter-market-history`, revision
`6d7d101713f603ca2e5aca71cfd29b29d67fddad`.

At the audited revision there are zero information-congestion assignments,
attempts, or run-ledger rows and therefore zero spend by this new study. The
most recent 24-hour public-price slice contains 112 of 288 intended five-minute
clocks (38.89%); the maximum observed gap is 39.47 minutes, and the last compacted
snapshot is 2026-07-22 04:02:43 UTC. The 95% coverage and 15-minute gap gates
correctly fail. The workflow will not send a paid request from this stale
revision.

This audit motivated the independent capture backstop. The normal and backstop
artifacts are overlaid before planning, so HF compaction lag alone will no
longer make a fresh run appear stale. The gate remains closed until the merged
remote workflows demonstrate the registered coverage on live artifacts.

## No-spend shadow validation

The final public-menu routing shadow produced:

- 7 requested and 7 live feasible model cohorts;
- 121 live provider-role rows;
- 158 feasible factorial cells;
- 32 immutable assignments in 16 cells;
- 6 model cohorts represented in the sampled assignments, with 5 represented
  in `k > 0` assignments; and
- a total worst-case quote cap of $0.0036583008.

`source_healthy=false` solely because the immutable HF history was stale at the
time of the shadow. The manifest and bundle hashes validated; execution was not
attempted.

The quality shadow selected `deepseek/deepseek-v4-flash`, providers DeepInfra,
StreamLake, and GMICloud, and two public MMLU item IDs. It produced eight exact
assignments with a total worst-case quote cap of $0.000402192. It was validated
but not executed.

## Public-shock support

After simultaneous router telemetry was clustered and same-family events
within 30 minutes were marked contaminated, the historical registry contains:

- 19,618 event rows, of which 19,597 are non-placebo;
- 116 unique clean model-event clocks;
- 116 clean clocks supporting `n=4` and `n=8`;
- 109 supporting `n=12`; and
- 46 supporting `n=20`.

Thus the public-shock count threshold is feasible, but it is not an empirical
result about `k*`. Capacity and rate-limit series are dense and currently enter
as contaminated events; they cannot mechanically satisfy the clean-shock gate.

The outcome-blind effective-rank diagnostic has 22 subset-size points from five
model cohorts, each with within-model subset-size variation. Equal cohort
weighting gives `beta=0.215` with a calendar-block bootstrap 95% interval of
`[-0.153, 0.515]`; no cohort carries more than 20% of the statistic. This clears
the registered rank-support screen but remains a descriptive mechanism input,
not evidence that the randomized optimum shrinks. No paid operational or
quality outcome exists for this study yet, so `gamma`, `tau`, and `k*` are not
estimated.

## Remaining gates

The prospective window begins 2026-07-23 and the fixed 28-day end is
2026-08-20. The release remains blocked until all of the following are true:

- capture coverage and maximum-gap gates pass;
- every registered randomized cell has at least 100 blocks;
- every registered `k` has at least 800 intended choices;
- four menu-size bins and four model cohorts are supported;
- at least ten responsive-provider pairs and seven holdout days are present;
- paid assignment-attempt-spend reconciliation is exact; and
- the released intervals pass the registered sign and economic-margin tests.

Passing those gates permits only a finite-range claim about owned eligible-menu
exposure. It does not identify an asymptotic limit, market-wide adaptation,
provider cost, full welfare, provider algorithms, communication, or collusion.
