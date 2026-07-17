# Clean confirmatory release protocol

Status: implemented before either H81 or H95 outcome gate opened.

This protocol governs the first confirmatory outcome access for the focal H81
fallback/selection experiment and the independent H95 fixed-horizon
replication. It operationalizes the release contract already stated in their
preregistrations and their dated outcome-blind amendments. The original release
contract changes only where an amendment below explicitly corrects a reference-
experiment defect before outcome access.

## Trigger and immutable input

`.github/workflows/confirmatory-release.yml` runs in GitHub Actions after every
successful `compact` workflow and can also be dispatched manually. The job uses
a clean checkout and the checked-in `uv.lock`. H81 and H95 are processed
sequentially under a non-cancelling concurrency lock.

For each study, `src/orcap/confirmatory_release.py` resolves the private Hugging
Face dataset head once and sets `ORCAP_HF_REVISION` for the entire gate/release
transaction. Concurrent collection or publication therefore cannot mix input
revisions.

## Outcome-free preflight

Before a gate opens, the runner reads only the following columns from
`router_route_attempts`:

`source`, `event_id`, `run_ts`, `observed_at`, `study_id`, `model_id`, `policy`,
and `metadata_json`.

H81 additionally reads the outcome-free `router_decomposition_plans` columns
needed to replay the intended first policy. It checks plan/seed replay, first-row
realization, treatment fidelity, the earliest chronological 40-intended-
assignments-per-arm prefix, and its cutoff; only intended assignment defines the
gate. H95 additionally reads its separate outcome-free
eligibility-plan table and checks the first 120 valid written triplets. The
preflight writes `assignment_only_gate.json` and exits successfully when a gate
is closed. It does not select response, provider, latency, cost, token, retry, or
fallback fields.

A local invocation without `--publish` is preflight-only even after a gate
opens. It reports `ready_requires_published_first_access` and cannot call the
outcome analyzer. The only outcome-reading path is therefore the marker-first
published transaction below.

## First-access transaction

When a gate is open, the runner executes this ordered state transition:

1. Check that no published release manifest exists.
2. Check that no orphaned first-access marker exists.
3. Write a marker containing the UTC transition time, pinned dataset revision,
   code commit, `uv.lock` hash, analyzer/preregistration hashes, and the
   assignment-only gate audit.
4. Commit that marker to the private dataset repository.
5. Only after the marker commit succeeds, invoke the dedicated study analyzer,
   which may issue its first full outcome query.
6. Require the analyzer to report `outcomes_released=true`.
7. Hash every released JSON and Parquet output and publish the complete bundle
   plus `release_manifest.json` to the fixed study path.

The fixed remote paths are:

- `releases/h81-confirmatory-v1/`
- `releases/h95-confirmatory-v1/`

The release is idempotent. A completed manifest causes every later invocation to
exit without running the analyzer. A first-access marker without a manifest is
treated as evidence of an interrupted first access; later invocations fail
closed and refuse a second outcome query. Recovery must use the retained
90-day GitHub Actions artifact and a documented amendment, not an automatic
rerun.

## Released outputs and boundaries

The H81 bundle contains the frozen preterminal fixed-count ITT analysis, intended-
assignment ledger, arm panel, model panel, contrasts, candidate-support
diagnostics, and summary. The H95
bundle contains its fixed 120-triplet audit, arm panel, model panel, contrasts,
whole-triplet leave-one-model-out panel, redacted row-level primary-outcome
audit, position-by-policy panel, position-zero policy and contrast panels, and
summary. The release manifest hashes the original preregistration
and every dated amendment in that study directory. The two studies are never
pooled.

H81's pre-release analyzer was further frozen in commit `4d66fda`. A request
outcome is binary only when it is `succeeded`, `failed`, or `cancelled`;
`unknown`, missing, and malformed values are not silently coded as failures.
Any such value on an intended assignment suppresses the complete-data point
contrast and randomization test and enters arm-level `[0,1]` bounds. The released
contrast table also
contains Bonferroni-Newcombe 95% familywise intervals for the two primary
components, conditional finite-population Hoeffding--Serfling intervals simultaneous over
all three policy means, and a wider implementation-fidelity sensitivity.
Missing/noncompliant treatment records remain in the primary intended arm; a
unique binary outcome is the ITT outcome even when treatment fidelity fails.
The separate sensitivity sends untrusted implementations and missing outcomes
to both endpoints; an unreconstructable arm widens the contrast to `[-1,1]`.
These are fidelity bounds, not a complier or per-protocol effect.

Commit `55b5087`, also made while the H81 outcome gate was closed, replaced the
published Monte Carlo tail approximation with an exact finite-support
enumerator. A subsequent proof audit found that its all-three-arm reference law
was exact only under a global sharp null, whereas each registered hypothesis is
pairwise and permits an arbitrary effect in the nuisance third arm. Before
outcome access, the analyzer was therefore corrected to condition on the
nuisance-arm assignment and permute only the two contrasted policies. Given the
pair's combined success count, its positive-arm success count follows the exact
two-arm hypergeometric law. A four-block `2/2` fixture enumerates all six
pairwise assignments and agrees to machine precision. The configured 100,000
permutations now hold the nuisance arm fixed and remain an implementation check;
the production release still fails closed if the maximum exact-versus-simulated
tail discrepancy exceeds one percentage point.

The same outcome-blind amendment records two limits. First, in nuisance-effect
stress tests the corrected pairwise tests reject at 3.45% and 3.60%, while the
superseded all-arm law rejects at 5.65% and 6.70%. Second, exact Bernoulli power
at the minimum preterminal counts 39/40 reaches 80% only for effects of 25--35
percentage points at the Bonferroni 2.5% threshold, depending on the baseline.
These are design-validation and planning calculations, not H81 outcomes.

A second outcome-blind interval audit adds the design-valid confidence set.
Conditional on the stopped prefix, each policy arm is a simple random sample
without replacement from its fixed potential-outcome schedule. The
Hoeffding--Serfling
bounded-outcome inequality plus a union bound over the three policy means gives
simultaneous coverage of at least 95% without a binomial model or independent
arms. Five fixed-schedule stress tests give worst Bonferroni-Newcombe family
coverage 95.13% and worst observed coverage 99.93% for the conservative design
interval; the latter has mean contrast width about 0.76. Exact joint enumeration of the
two-test Holm family at counts 39/40/40 requires a 35-point component effect for
80% worst-terminal-policy power on the preregistered grid. These remain planning
and implementation facts, not H81 outcomes.

A third outcome-blind H81 amendment corrects post-assignment compliance
selection. Future blocks write a privacy-safe plan row containing the seed and
intended first policy before the first request; historical eligibility rows
replay the run-seed candidate shuffle and per-eligible-block RNG draws, including
blocks with no attempt row, while still older recorded blocks replay their block
seed. Any failed plan or legacy-run replay closes the assignment-integrity gate.
Missing requests, recorded-policy
mismatches, duplicates, and treatment-control failures remain in their intended
arms. The gate therefore counts assignment rather than realized treatment, and
the primary estimand is assigned-policy ITT. At the pinned provenance point all
84 current blocks pass first-row, replay, and treatment-fidelity checks, so the
32/24/28 counts are unchanged.

In 3,000 sharp-null experiments at each of five outcome-dependent compliance
strengths, the ITT estimate stays within 0.0022 of zero and its false-rejection
rate is 2.83--3.70%. The superseded filtered comparison reaches bias 1.0 and
100% false rejection while the overall retained share stays near 50%. This
validates the correction's necessity; it is not H81 outcome evidence.

H95's prerelease analyzer was first hardened in commit `f170d89` while its fixed
horizon remained 4/120 and before any H95 outcome field was queried. A second
outcome-blind proof audit found that the six-assignment local law is exact only
under the global three-policy sharp null. Each registered elementary hypothesis
is pairwise and leaves the nuisance third policy unrestricted. The production
test now conditions in every triplet on the model assigned the nuisance policy
and swaps only the two focal labels. Each triplet contributes a two-point law,
and the analyzer convolves those laws across the 120 independent triplets. A
100,000-draw conditional-swap audit is implementation-only; exact support mass
must equal one within `1e-12`, and a tail discrepancy above 0.01 stops release.
A two-triplet test agrees with all four conditional assignments.

In 5,000 fixed-schedule experiments under each mixed pairwise null, the corrected
law rejects the true elementary null at at most 4.06%, whereas the superseded
all-policy law reaches 8.12%; the same rates obtain for false rejection of the
remaining true null after Holm in the adversarial schedules. H95 also gains a
design-valid bounded-outcome interval. Each triplet contrast lies in `[-1,1]`,
has expectation equal to its triplet-average finite-population effect, and is
independent across written triplets. Hoeffding's inequality plus a union bound
over the two primary contrasts gives simultaneous 95% coverage with radius
`sqrt(2 log(4 / 0.05) / 120) = 0.27025`. Five fixed-schedule audits give worst
observed design-family coverage 99.90% and mean width 0.540, versus 95.52% and
mean width 0.290 for the descriptive Bonferroni paired-t family. The inequality,
not the simulated coverage, supplies the design guarantee.

A third outcome-blind H95 amendment makes the position-zero diagnostic a formal
secondary sensitivity. Model order is fixed before the policy shuffle, so
conditional on the realized first models and position-zero arm counts, policy
labels form a complete randomization across the 120 fixed first-block units.
Position-zero arm means are design-unbiased, pairwise Fisher tails are exact
hypergeometric tails after conditioning on nuisance membership, and
Hoeffding--Serfling intervals cover all three policy means simultaneously. The
two secondary directional tests receive Holm adjustment within a separate
secondary family and do not alter the primary family or fixed horizon.

The first model block has no earlier H95 request. In a planted-carryover audit
with zero direct policy effects, maximum absolute primary three-block bias is
0.2437 while position-zero bias is 0.00103. The sensitivity's worst observed
design-family coverage is 100%, but mean interval width is 0.810. Agreement can
support but not prove the primary no-interference interpretation; disagreement
narrows the defensible estimand to position zero. Missingness on a position-zero
row suppresses its complete-data output, while missingness confined to later
rows does not erase the separately identified first-block sensitivity.

H95 preserves the original structural intent-to-treat zeros for a missing
planned first request or noncompliant first policy. It also codes duplicate
first records and an auditable provider-control mismatch as structural zeros.
By contrast, `unknown`, missing, or malformed outcomes on a structurally valid
record are measurement missing: they suppress all complete-data point estimates,
paired intervals, design intervals, and randomization tests and enter `[0,1]`
bounds. Paired-t intervals are descriptive, and the two primary contrasts
receive both Bonferroni 95% familywise paired-t intervals and simultaneous
design-Hoeffding intervals in addition to Holm-adjusted exact conditional
one-sided tests.

Collector rows after `f170d89` record requested-order length, provider-only
count, public-provider count, and fallback state. The first four triplets lack
the two newly added length fields; their 12 first-position rows remain in the
fixed horizon as legacy-unverified, with explicit audit coverage and sensitivity
bounds. Leave-one-model-out diagnostics drop whole triplets, and six-hour
concentration is computed from distinct plans rather than block rows. Because
the three model blocks are sequential, direct-policy language additionally
requires no treatment-dependent spillover from an earlier model block. A
position-by-policy panel exposes the randomized execution-position pattern;
position-zero cells are the no-earlier-block diagnostic, not proof that later
positions are spillover-free.

These releases identify owned-account policy effects over their realized model
support. They do not identify market-wide routed share, private provider cost,
provider intent, collusion, or social welfare.

## Verification

`tests/test_confirmatory_release.py` verifies that:

- closed gates never select outcome columns;
- an open gate without publication still cannot invoke an outcome analyzer;
- the remote marker precedes the first analyzer call;
- a completed release is not rerun;
- an orphaned marker blocks a second access;
- empty/new datasets fail closed rather than raising into an ambiguous state;
- H81's gate can read only explicit assignment and plan columns, never outcome
  fields;
- a plan-only H81 block remains in its intended arm with missing request and
  treatment-fidelity flags;
- a noncompliant H81 request remains in the ITT point sample rather than changing
  the stopped-design reference experiment;
- the H81 ITT estimator remains centered and size-controlled under an outcome-
  dependent compliance adversary that breaks the superseded filtered analysis;
- an unknown H81 outcome cannot become a failure or retain a point estimate;
- a noncompliant preterminal treatment record re-enters the intended-assignment
  worst-case bounds after a valid replacement opens the gate;
- an unknown H95 outcome cannot become a failure or retain complete-data
  inference;
- H95 missing requests, noncompliant policies, duplicate rows, and auditable
  provider-control failures retain their structural intent-to-treat coding;
- exact nuisance-conditioned H95 tails match brute force, the superseded
  all-policy law is anti-conservative in mixed-null stress tests, and production
  exact-versus-simulated drift fails closed;
- H95 design-Hoeffding intervals cover the two finite-population primary
  contrasts simultaneously over fixed-schedule adversaries;
- H95 time concentration and whole-triplet leave-one-model-out gates use their
  registered units;
- the H95 position-by-policy panel exposes the sequential-block interference
  diagnostic;
- the H95 position-zero estimator is exact under its conditional randomization,
  remains centered under planted later-block carryover, and reports its wider
  simultaneous design interval;
- every dated study amendment is hashed into the first-access manifest;
- the remote workflow is compaction-triggered, non-cancelling, publishing, and
  artifact-retaining.

An earlier post-amendment preflight, workflow `29563312069`, ran code commit
`f2fd115`, pinned dataset revision
`4fd167d674f6b227b766df00505fe02da1325e63`, reported H81 counts 32/23/27 and
four of 120 H95 triplets, and queried no outcome field. The preceding compact
workflow `29561825717` passed preparation and all eight table shards; full-screen
workflow `29561010800` completed analysis and both publication steps. The full
repository suite after the H95 prerelease audit reports 551 passes. An
outcome-blind local preflight using commit `f170d89` against the same pinned
revision again found 4/120 H95 triplets, perfect plan compliance and replay,
zero missing first records, 12 legacy-unverified metadata rows, and no outcome
query. This records the pre-hardening baseline.

Scheduled H95 workflow `29564165459` checked out `f170d89` and completed
successfully at 07:49 UTC. New-head compaction `29564756681` then passed
preparation, the 551-test suite, publication, and all eight table shards.
Automatically triggered audit `29565268475` checked out paper/code head
`14ba8c6`, pinned revision
`3efd953a98108381732684508991bab2f5ee28b4`, and reported H81 counts 32/24/28
and H95 support 5/120. H95 has 15/15 first records, perfect plan compliance and
replay, 12 legacy-unverified rows, and 3/3 newly auditable rows passing. Both
outcome-query flags remain false.

Exact-head audit `29566914482` then checked out paper/code head `244c384`,
pinned revision `42334a840dc8088cc8cde441ebe3649cfa041b5e`, reproduced the same
H81 counts and H95 support, and again reported `outcomes_queried=false` for both
studies. This is the outcome-blind provenance point for the finite-population
interval and joint-Holm amendment.

Published-paper audit `29568434722` checked out head `973f900`, pinned revision
`30b430e2a095d069015f45dbf9b3fca9a4f7e1ce`, and again reported H81 counts
32/24/28, H95 support 5/120, perfect replay and compliance, and
`outcomes_queried=false` for both studies. This is the outcome-blind provenance
point for the H95 pairwise-reference-law and design-interval amendment.

Corrected-H95 audit `29569590704` checked out head `4860015`, pinned revision
`f5b822812a8266200c9b277e88578c8829338e83`, and again reported H81 counts
32/24/28, H95 support 5/120, perfect replay and compliance, and
`outcomes_queried=false` for both studies. This is the outcome-blind provenance
point for the position-zero carryover amendment.

Published position-zero audit `29570676475` checked out head `406a478`, pinned
the same revision, reproduced H81 counts 32/24/28 and H95 support 5/120, and
again reported `outcomes_queried=false` for both studies. Its 8.8 KB artifact
contained only `release_status.json` and the two `assignment_only_gate.json`
files. This is the outcome-blind provenance point for the H81 intended-
assignment ITT amendment.
