# Paper evidence and amendment ledger

Frozen: 2026-07-17 UTC. This ledger is part of the paper release audit. It
records analysis changes that affect identification, stopping, outcome access,
or promoted claims. It is not a substitute for the original protocols.

## Authoritative evidence cut

- Dataset: private Hugging Face dataset `t4run/openrouter-market-history`.
- Revision: `08a2a183d6df275b5614310b6205695dafbd929b`.
- Endpoint panel: 3,344,470 rows, 2,116 runs, and 11 UTC dates from 2026-07-07
  through 2026-07-17.
- H80 outcome-free support: 156 verified first-position blocks with arm counts
  37, 43, 38, and 38; 100% assignment replay; outcomes masked.
- H81 outcome-free support: 78 verified first-position blocks with arm counts
  30, 23, and 25; 100% assignment replay and treatment-metadata compliance;
  outcomes masked.
- H81 external support: two repeated models, 74 eligibility rows, ranks five
  and six, effective model count two, and zero adjacent-run support turnover.
- H81 outcome-free forecast: 10, 17, and 15 additional assignments are needed
  by arm. Under uniform continued assignment and the observed 1.89-block/hour
  cadence, the simulated mean time to gate is 29.2 hours and the 90th percentile
  is 34.8 hours; scheduler and eligibility failures are not modeled.
- Cross-router catalog: one simultaneous cross section only. Of 29 HF-linked
  exact provider-model pairs, 28 have identical input and output prices (Wilson
  95% interval `[0.8282, 0.9939]`). There are zero repeated snapshots and zero
  price events at this cut.
- H94 prospective support: zero snapshots after the 04:30:20 UTC activation
  cutoff and therefore zero eligible transitions, common shocks, or simulated
  route switches.
- H95 outcome-free support: one planned triplet, three first-position blocks,
  three distinct models, perfect plan compliance and replay, ten candidate rows,
  and nine eligible rows. No outcome was queried.

Local `analysis/` outputs that were not rebuilt from this revision are not
authoritative evidence for the rewrite.

## Remote collection state at freeze

- H81 `decomposition-probes` completed successfully at 2026-07-17 03:54 UTC.
- H80 `probes` completed successfully at 2026-07-17 03:47 UTC.
- The first `router-catalogs` run completed successfully at 03:31 UTC. It is a
  newly activated hourly workflow, so only one run existed before the pinned
  cut; the next nominal schedule is minute 47 of each hour.
- `compact` completed successfully at 03:38 UTC. Hourly jobs buffer GitHub
  artifacts and the consolidated workflow uploads them to Hugging Face; a
  dataset revision can therefore lag a successful collector until the next
  fold.
- `marketplace-history` briefly received a malformed or missing app-rankings
  payload at 03:30 UTC. The endpoint subsequently returned HTTP 200 with the
  expected `data` and `meta` structure, and replay run `29555163723` completed
  capture, quality checks, and Hugging Face upload successfully. The data sink
  remained fresh throughout; this was a transient source response, not evidence
  loss.
- H95 run `29555584388` completed successfully at 04:46 UTC after the protocol
  freeze and uploaded its eligibility and attempt telemetry. No workflow log,
  request outcome, selected provider, cost, or latency was inspected; the
  fixed 120-triplet outcome gate remains closed.

These workflows run on GitHub-hosted runners and do not depend on the local
computer remaining online.

## Incidents and amendments

| UTC / commit | Study | Event | Outcome state | Consequence |
|---|---|---|---|---|
| 2026-07-15 09:47 / `8835d6f` | H80 | Prospective four-arm protocol and 40-per-arm stopping rule introduced | No H80-v2 observations yet | This is the original H80 gate. |
| 2026-07-15 10:25 / `3bd2d03` | H81 | Three-arm fallback/selection protocol and 40-per-arm stopping rule introduced | Before first H81 request | This is the original H81 gate. |
| 2026-07-15 10:34 / `d187440` | H80/H81 | Earliest-balanced-prefix output masking added | Before confirmatory release | Later rows cannot replace the first qualifying cut. |
| 2026-07-15 / recorded in H81 protocol | H81 | Legacy WCV4 analysis printed aggregates from the first two H81 blocks | Two launch-block aggregates became analyst-visible | H81 is preregistered but not fully analyst-blinded. Cross-study outcome filters and regression tests were added. |
| 2026-07-16 07:14 / `d96012a` | H80 | Promotion threshold raised from 40 to 500 per arm | All-position aggregates visible; first-position gate unopened | This is a post-outcome, pre-original-gate conservative replication amendment, not the original preregistration. |
| 2026-07-17 / `6017dae` | H81 | Pre-gate analyzer changed from outcome derivation plus masking to an assignment-only SQL query and an early return | Dedicated H81 outcomes still masked | Pre-gate public execution no longer reads outcome, cost, latency, provider, token, or fallback fields. Raw-source analyst access remains technically possible. |
| 2026-07-17 04:06 / `6017dae` | H81 | Proof audit found that the earliest-balanced-prefix rule is an assignment-dependent stopping time | No confirmatory H81 outcome released | The gate-hitting terminal block is excluded. Inference conditions on the preterminal arm counts and permutes their fixed label multiset. The 40-per-arm release threshold and hypotheses are unchanged. |
| 2026-07-17 / `6017dae` | H93 | Remote DuckDB run failed because `run_ts` was ambiguous in the latest-model join | Cross-sectional data already public | The join is now explicitly qualified; a two-vintage regression test verifies that only the latest model mapping is used. The rerun reproduces the one-cross-section 28/29 result and confirms that every longitudinal gate remains closed. |
| 2026-07-17 04:30 / `6017dae` | H94 | Longitudinal cross-router pass-through protocol activated prospectively | One earlier discovery cross section known; no eligible future transition observed | Only snapshots after 04:30:20 UTC are eligible; the 03:30 cross section is excluded from all gates and events. |
| 2026-07-17 04:44 / `00351dd` | H95 | Fixed 120-triplet protocol, collector, analyzer, and remote workflow frozen | Before first H95 inference request | H95 is independent of H81, uses exact within-triplet arm balance, and never pools outcomes with H81. |
| 2026-07-17 04:46 / run `29555584388` | H95 | First prospective remote workflow completed and preserved telemetry | Outcomes not queried or inspected | Confirms remote operation and prospective activation only; no effect or completion-rate result is available. |
| 2026-07-17 04:52 / dataset `08a2a183` | H81/H95 | Outcome-free refresh records H81 counts 30/23/25 and the first compliant H95 triplet | Dedicated analyzers queried assignment and support fields only | Updates accrual and transport support without releasing any policy outcome. |
| 2026-07-17 05:01 / working tree | H94 | Red-team audit found that primary transitions respected the activation cutoff but elapsed-time, snapshot, and simulated-route summaries still read the unfiltered discovery panel | Zero post-cutoff snapshots and zero prospective events existed | A shared fail-closed prospective filter now governs every gate, derived frame, and simulated outcome; regression tests exclude all-discovery panels and prevent bridging the first future snapshot to discovery. No empirical result changed. |
| 2026-07-17 / `6017dae` | Theory suite | Detection, revenue-accounting, coarsening, and entry propositions received finite numerical/property checks | No empirical outcome used | The checks validate algebra and implementation only; they are not market calibration or causal evidence. |

## H81 stopping-time correction

Let `T` be the first block for which all three arm counts reach 40. The policy
assigned at block `T` is mechanically the last arm to hit 40. Including that
block while pretending all labels are independent one-third draws gives the
wrong conditional reference distribution and can bias time-varying outcomes.

The corrected confirmatory sample is blocks `1,...,T-1`. Conditional on `T`,
the terminal policy, and the preterminal count vector, these labels are uniform
over fixed-count assignments. Arm means are therefore the conditional
Horvitz-Thompson means with probabilities `n_p/(T-1)`, and randomization tests
permute the observed label multiset. A 20,000-draw validation at the actual gate
finds corrected bias indistinguishable from zero for all three contrasts; the
fixed-count sharp-null test rejects at 5.05% in 2,000 experiments (Monte Carlo
standard error 0.49 percentage points).

## Claim consequences for the rewrite

1. H81 is the focal randomized design, but no causal outcome is yet reportable;
   the current outcome-free counts are 30, 23, and 25.
2. H80 is a separate replication and must retain both its original 40-per-arm
   history and its later 500-per-arm promotion rule.
3. H82 is descriptive because its frozen pretrends fail.
4. H84 rejects one stale-cheap prediction but does not reject adverse selection
   as a class.
5. H93 is a cross-sectional equality fact only; no pass-through or reaction
   result exists yet.
6. H94 is active only for post-04:30:20 UTC snapshots and has no prospective
   result yet. H95 has one of 120 planned triplets and no released outcome.
7. No current design identifies literal front-running, provider intent,
   market-wide routed share, social welfare, or the welfare-maximizing entry
   count.

Machine-readable counterparts are generated by
`scripts/build_paper_evidence_audit.py` as
`analysis/paper_gate_genealogy.parquet`,
`analysis/paper_evidence_assignment.parquet`, and
`analysis/paper_release_manifest.json`.
