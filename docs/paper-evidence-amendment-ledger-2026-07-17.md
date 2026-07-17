# Paper evidence and amendment ledger

Frozen: 2026-07-17 UTC. This ledger is part of the paper release audit. It
records analysis changes that affect identification, stopping, outcome access,
or promoted claims. It is not a substitute for the original protocols.

## Authoritative evidence cut

- Dataset: private Hugging Face dataset `t4run/openrouter-market-history`.
- Outcome-free randomized-design revision:
  `42334a840dc8088cc8cde441ebe3649cfa041b5e`.
- Corrected public-input revision:
  `b389923ad7713bc230dd522f770aa306bf778806`.
- Endpoint panel: 2,004,680 distinct provider-model listings from 2,116 capture
  runs and 11 UTC dates from 2026-07-07 through 2026-07-17. The corresponding
  exact-distinct raw-record count is 2,013,866; 9,186 same-listing variants are
  availability-only and contain no price or capability conflict.
- H80 outcome-free support: 156 verified first-position blocks with arm counts
  37, 43, 38, and 38; 100% assignment replay; outcomes masked.
- H81 outcome-free support: 84 verified first-position blocks with arm counts
  32, 24, and 28; 100% assignment replay and treatment-metadata compliance;
  outcomes masked.
- H81 external support: two repeated models, 74 eligibility rows, ranks five
  and six, effective model count two, and zero adjacent-run support turnover.
- H81 has remaining arm deficits 8, 16, and 12. Calendar forecasts are omitted
  because recent scheduling and eligibility failures make the short-run accrual
  rate nonstationary.
- Cross-router catalog: one simultaneous cross section only. Of 29 HF-linked
  exact provider-model pairs, 28 have identical input and output prices (Wilson
  95% interval `[0.8282, 0.9939]`). There are zero repeated snapshots and zero
  price events at this cut.
- H94 prospective support: zero snapshots after the 04:30:20 UTC activation
  cutoff and therefore zero eligible transitions, common shocks, or simulated
  route switches.
- H95 outcome-free support: five planned triplets, 15 first-position blocks,
  nine distinct models, effective model count 7.76, and perfect plan compliance
  and replay. All 15 first requests are recorded; the first four triplets predate
  the new row-level provider-order length fields and their 12 rows are explicitly
  legacy-unverified. The newest triplet's three records are auditable and all
  pass, giving 20% coverage and a 100% conditional pass rate. Three of five
  triplets fall in the largest six-hour bin, so
  the early support does not pass the registered time-transport gate. No outcome
  was queried. Model blocks are sequential; policy-position randomization handles
  position-only drift, while direct-policy interpretation additionally requires
  no treatment-dependent cross-model carryover. The release now preserves a
  position-by-policy diagnostic for that assumption.

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
- Clean release run `29556911017` completed remotely from commit `7c7c279` at
  05:16 UTC. It pinned dataset revision `08a2a183`, reproduced H81 counts
  30/23/25 and H95 support 1/120, wrote 90-day assignment-only artifacts, and
  explicitly reported `outcomes_queried=false` for both studies.
- Fresh consolidation run `29561825717` completed from commit `b77a39b` with
  preparation and all eight table shards passing. Its automatically triggered
  release audit `29562343314` checked out paper/analysis commit `976468a`, pinned
  revision `8ce9eb75`, reproduced H81 counts 32/23/27 and H95 support 4/120,
  and explicitly reported `outcomes_queried=false` for both studies.
- Full-screen run `29561010800` completed all analyses and both HF publication
  steps. New-head preflight `29563312069` then checked out `f2fd115`, pinned
  revision `4fd167d6`, reproduced H81 counts 32/23/27 and H95 support 4/120,
  and again reported `outcomes_queried=false` for both studies.
- The first hardened scheduled H95 run, `29564165459`, checked out `f170d89`
  and completed successfully at 07:49 UTC. New-head compaction `29564756681`
  passed preparation, the 551-test suite, dataset publication, and all eight
  table shards. Automatically triggered release audit `29565268475` checked out
  `14ba8c6`, pinned revision `3efd953a`, proved a fifth valid triplet, and kept
  both outcome-query flags false. Subsequent clean checkouts continue to record
  expanded treatment metadata without depending on the local computer.
- Exact-paper-head audit `29565662719` checked out `d61a6b2`, reproduced the
  same immutable revision and counts, and again reported
  `outcomes_queried=false` for H81 and H95.
- Corrected-paper exact-head audit `29566914482` checked out `244c384`, pinned
  revision `42334a84`, reproduced H81 counts 32/24/28 and H95 support 5/120,
  and again reported `outcomes_queried=false` for both studies. This is the
  outcome-blind provenance point for the finite-population interval amendment.

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
| 2026-07-17 05:01 / `d5345e5` | H94 | Red-team audit found that primary transitions respected the activation cutoff but elapsed-time, snapshot, and simulated-route summaries still read the unfiltered discovery panel | Zero post-cutoff snapshots and zero prospective events existed | A shared fail-closed prospective filter now governs every gate, derived frame, and simulated outcome; regression tests exclude all-discovery panels and prevent bridging the first future snapshot to discovery. No empirical result changed. |
| 2026-07-17 05:16 / `7c7c279`, run `29556911017` | H81/H95 | Installed and exercised a clean remote first-access transaction after successful compaction | Both gates closed; outcome fields unqueried | At a gate, the job first commits an immutable access marker, then runs the dedicated analyzer once, hashes the bundle, and publishes it. A completed manifest is idempotent; an orphan marker refuses automatic re-access. This changes release governance, not the estimand or stopping rule. |
| 2026-07-17 05:20 / `93ad8ff` | H81/H95 | Red-team audit found that non-publishing mode would have invoked an analyzer after a future gate opened | Both real gates still closed; no outcome queried | Non-publishing mode is now permanently preflight-only, including at an open gate. Only the remote marker-first publication transaction can invoke an outcome analyzer. A synthetic-open-gate regression test enforces this boundary. |
| 2026-07-17 / `4d66fda` | H81 | Pre-release missingness audit found that `unknown` or malformed outcomes were silently coerced to failure and that the two primary intervals were marginal only | H81 remained below 40 per arm; no dedicated outcome query occurred | Binary outcomes are now explicit; incomplete outcomes suppress point/randomization inference and enter `[0,1]` bounds. Intended arms are reconstructed from seeds for worst-case treatment/outcome attrition bounds, and the two primary intervals receive Bonferroni familywise adjustment. Unknown-outcome and noncompliance adversaries plus the full 539-test suite pass. |
| 2026-07-17 / `1719ade` | PM1 temporal holdout | Pre-release audit found that the 17-parameter primary rung could pass with only 50 training events and that unpenalized logistic fits could separate | Only 10/30 completed dates existed; the event table and holdout remained unqueried | Every rung now uses training-standardized ridge logistic regression with fixed `C=1` and no holdout tuning. Promotion requires 10 training events and nonevents per primary parameter, 50 test events and nonevents, 10 train/test event dates, and 10 test models. Separation and low-support regression tests pass; the full suite has 540 passes. |
| 2026-07-17 07:12 / run `29562343314` | H81/H95 | Clean post-amendment gate audit after eight-shard consolidation | Both gates closed; `outcomes_queried=false` | Revision `8ce9eb75` contains 82 H81 blocks (32/23/27) and four H95 triplets (12 blocks, eight models). This updates accrual only; no effect estimate exists. |
| 2026-07-17 / `55b5087` | H81 | Pre-release audit found avoidable Monte Carlo error in the primary Fisher tails even though binary outcomes and fixed counts admit finite exact enumeration | H81 remained below 40 per arm; no outcome was queried | Published p-values now sum the multivariate-hypergeometric support exactly. The 100,000-draw permutation is retained only as an audit check; a 30-assignment brute-force fixture agrees to machine precision and the full suite has 541 passes. |
| 2026-07-17 / `5cc0a4a` | H81 | Red-team follow-up found that the exact-versus-Monte-Carlo discrepancy was reported but could not stop a bad release | H81 remained below 40 per arm; no outcome was queried | Exact support mass must equal one within `1e-12`, and a production release fails closed if the 100,000-draw tail differs by more than 0.01. The production-setting regression and full 542-test suite pass. |
| 2026-07-17 / pairwise-Fisher amendment | H81 | A second proof audit found that permuting all three labels tests a global sharp null and is not exact for either registered pairwise null when the nuisance third policy has an effect | H81 remained 32/24/28 at revision `3efd953a`; the clean gate reported `outcomes_queried=false` | Each test now conditions on the nuisance-arm assignment and sums the two-arm hypergeometric law. In 2,000 nuisance-effect experiments per null, corrected size is 3.45%/3.60% versus 5.65%/6.70% for the superseded law. Exact 39/40 Bernoulli scenarios show that 80% power requires a 25--35 percentage-point effect at the Bonferroni threshold; nonsignificance cannot establish equivalence. |
| 2026-07-17 / design-interval amendment | H81 | Interval audit found that descriptive Newcombe intervals do not by themselves match the conditional finite-population theorem, and marginal Bonferroni power does not describe the joint Holm family | H81 remained 32/24/28 at revision `42334a84`; exact-head run `29566914482` reported `outcomes_queried=false` | The release now adds a Hoeffding--Serfling confidence set simultaneous over the three fixed potential-outcome means and exact joint-Holm planning power for all minimum-count terminal arms. Worst simulated Bonferroni-Newcombe family coverage is 95.13%; worst design-family coverage is 99.93%, with mean width about 0.76. Worst-terminal 80% joint power requires a 35-point component effect on the fixed grid. |
| 2026-07-17 07:31 / run `29563312069` | H81/H95 deployment | Verify the exact-inference manuscript/code head on the live remote release path | Both gates closed; `outcomes_queried=false` | Head `f2fd115` pinned revision `4fd167d6`; H81 remained 32/23/27 and H95 remained 4/120. This is deployment evidence, not an effect estimate. |
| 2026-07-17 / `f170d89` | H95 | Prerelease audit found silent unknown-to-failure coercion, simulation-only tails despite a finite exact law, missing row-level provider-control lengths, marginal normal intervals, and unimplemented time/leave-one-model-out transport gates | H95 remained 4/120; the outcome-blind preflight selected assignment metadata only and reported `outcomes_queried=false` | Structural missing/noncompliant requests remain ITT zeros, but unknown compliant outcomes now suppress complete-data inference and enter `[0,1]` bounds. Fisher tails convolve the six assignments per triplet exactly, with a fail-closed 100,000-draw audit. Future rows carry provider-control lengths; the 12 legacy rows remain flagged in the horizon. Paired-t familywise intervals, distinct-triplet time concentration, whole-triplet LOMO, row-level outcome audit, and adversarial tests are implemented; the full suite has 551 passes. |
| 2026-07-17 / H95 pairwise-interval amendment | H95 | A second proof audit found that the six-assignment law is exact for the global three-policy sharp null but not either pairwise elementary null when the nuisance policy has an effect; paired-t intervals also did not state design-only uncertainty | Exact-head audit `29568434722` checked head `973f900` at revision `30b430e2`; H95 remained 5/120 and reported `outcomes_queried=false` | Each test now conditions on the nuisance-policy assignment and convolves two focal-label swaps per triplet. Mixed-null stress tests give 4.06% worst corrected true-null rejection versus 8.12% for the superseded law. A simultaneous bounded-outcome Hoeffding interval adds a 0.270 radius at 120 triplets; worst simulated family coverage is 99.90% with mean width 0.540, versus 95.52% and 0.290 for descriptive paired-t intervals. |
| 2026-07-17 / H95 position-zero amendment | H95 | Sequential model blocks leave the primary direct-policy interpretation conditional on no treatment-dependent carryover; the existing position panel was diagnostic but did not define an identified first-block estimand | Exact-head audit `29569590704` checked head `4860015` at revision `f5b82281`; H95 remained 5/120 and reported `outcomes_queried=false` | A separate secondary estimator uses the randomized first model block only. Conditional arm means are design-unbiased, pairwise tails are hypergeometric, and Hoeffding--Serfling intervals are simultaneous over the three means. Planted later-block carryover creates 0.2437 primary bias but only 0.00103 position-zero bias; mean position-zero interval width is 0.810. The sensitivity does not change the primary family or prove actual interference. |
| 2026-07-17 / H81 intended-assignment amendment | H81 | The prior gate and point sample filtered on post-assignment treatment metadata, so arm-dependent compliance could invalidate the fixed-count reference experiment and create a selected per-protocol comparison | Exact-head audit `29570676475` checked head `406a478` at revision `f5b82281`; H81 remained 32/24/28, all 84 rows passed replay and treatment fidelity, and `outcomes_queried=false` | The gate now counts every pre-request plan or historical seed-replayed intended assignment. Missing, mismatched, duplicate, and noncompliant requests remain in their randomized arms; the primary estimand is assigned-policy ITT and fidelity is diagnostic. A sharp-null adversary leaves ITT bias below 0.0022 and rejection at 2.83--3.70%, while the superseded filtered comparison reaches bias one and 100% false rejection at the same approximate retention rate. Current counts are unchanged. |
| 2026-07-17 07:49 / run `29564165459` | H95 deployment | First scheduled collector run on the hardened metadata commit | Workflow succeeded on head `f170d89`; artifact not yet in the pinned revision; no outcome log inspected | Verifies remote deployment only. The manuscript retains 4/120 until compaction and an assignment-only gate audit prove another valid plan. |
| 2026-07-17 08:06 / compaction `29564756681`, audit `29565268475` | H81/H95 | Fold the first hardened H95 artifact and verify the paper head remotely | Both gates closed; `outcomes_queried=false` | Head `14ba8c6` pinned revision `3efd953a`. H81 advanced to 84 blocks (32/24/28). H95 advanced to 5/120 with 15/15 first records, perfect replay/compliance, 12 legacy rows, and 3/3 newly auditable rows passing. This is assignment and deployment evidence only. |
| 2026-07-17 10:11 / collector `29572631254`, compaction `29572789506`, audit `29573258132` | H81/H95 deployment | Verify the intended-assignment plan ledger prospectively without exposing the mixed request artifact or capture outcomes | Both gates closed; `outcomes_queried=false` | Head `c37fc6b` published a separate two-row outcome-free plan commitment with redacted logs. Compaction passed 571 tests, publication, and eight shards. The automatic audit pinned revision `18ea5aa2`: H81 advanced to 92 blocks (33/31/28), four explicit pre-request plans, 100% reconstruction/replay/first-row/fidelity, and a passing integrity gate; H95 advanced to 7/120. This closes deployment, not either outcome gate. |
| 2026-07-17 10:51 / `65e1425`, audit `29574825052` | H81 release presentation | Freeze the result table, forest plot, neutral paragraph, and algebraic release validator before the one-time outcome access | Gate closed at 94 blocks (34/31/29); `outcomes_queried=false` | Compaction `29573860829` published revision `60d5a020`. The template reports every sign, refuses equivalence language, validates ITT/HT and component-sum identities, and is included in the marker code hashes. The synthetic package renders and the full suite has 573 passes. |
| 2026-07-17 / `6017dae` | Theory suite | Detection, revenue-accounting, coarsening, and entry propositions received finite numerical/property checks | No empirical outcome used | The checks validate algebra and implementation only; they are not market calibration or causal evidence. |

## H81 stopping-time correction

Let `T` be the first block for which all three arm counts reach 40. The policy
assigned at block `T` is mechanically the last arm to hit 40. Including that
block while pretending all labels are independent one-third draws gives the
wrong conditional reference distribution and can bias time-varying outcomes.

The corrected confirmatory sample is blocks `1,...,T-1`. Conditional on `T`,
the terminal policy, and the preterminal count vector, these labels are uniform
over fixed-count intended assignments. Arm means are therefore the conditional
intention-to-treat Horvitz-Thompson means with probabilities `n_p/(T-1)`.
Treatment realization and metadata never filter these labels; future blocks
write the seed and intended first policy before the request, and historical
blocks replay the same seed. For each pairwise null,
randomization inference additionally conditions on the nuisance-arm assignment
and permutes only the two contrasted labels. A 20,000-draw validation at the
actual gate finds corrected bias indistinguishable from zero for all three
contrasts; the fixed-count global sharp-null test rejects at 5.05% in 2,000
experiments (Monte Carlo standard error 0.49 percentage points). Under a large
nuisance-policy effect, the registered pairwise tests reject at 3.45% and 3.60%.
Exact minimum-count power reaches 80% only for large 25--35 percentage-point
effects at the conservative familywise threshold.

## Claim consequences for the rewrite

1. H81 is the focal randomized ITT design, but no causal outcome is yet
   reportable; the current outcome-free intended-assignment counts are 33, 31,
   and 28, with 100% first-row, reconstruction, replay, and treatment-fidelity
   support and four explicit prospective plans.
2. H80 is a separate replication and must retain both its original 40-per-arm
   history and its later 500-per-arm promotion rule.
3. H82 is descriptive because its frozen pretrends fail.
4. H84 rejects one stale-cheap prediction but does not reject adverse selection
   as a class.
5. H93 is a cross-sectional equality fact only; no pass-through or reaction
   result exists yet.
6. H94 is active only for post-04:30:20 UTC snapshots and has no prospective
   result yet. H95 has seven of 120 planned triplets and no released outcome.
   Its exact inference and transport implementation are frozen, but its first
   12 rows remain transparently legacy-unverified for the newly added provider-
   control length fields.
   PM1 is result-blind at 10/30 completed dates and now has a fixed ridge
   estimator plus an events-per-parameter promotion gate.
7. No current design identifies literal front-running, provider intent,
   market-wide routed share, social welfare, or the welfare-maximizing entry
   count.

Machine-readable counterparts are generated by
`scripts/build_paper_evidence_audit.py` as
`analysis/paper_gate_genealogy.parquet`,
`analysis/paper_evidence_assignment.parquet`, and
`analysis/paper_release_manifest.json`.
