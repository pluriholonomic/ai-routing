# Clean confirmatory release protocol

Status: implemented before either H81 or H95 outcome gate opened.

This protocol governs the first confirmatory outcome access for the focal H81
fallback/selection experiment and the independent H95 fixed-horizon
replication. It operationalizes the release contract already stated in their
preregistrations; it does not change an estimand, hypothesis, stopping rule,
sample, or multiplicity family.

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

H81 checks assignment replay, treatment metadata, the earliest chronological
40-per-arm prefix, and its cutoff. H95 additionally reads the outcome-free
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

The H81 bundle contains the frozen preterminal fixed-count analysis, arm panel,
model panel, contrasts, candidate-support diagnostics, and summary. The H95
bundle contains its fixed 120-triplet audit, arm panel, model panel, contrasts,
and summary. The two studies are never pooled.

H81's pre-release analyzer was further frozen in commit `4d66fda`. A request
outcome is binary only when it is `succeeded`, `failed`, or `cancelled`;
`unknown`, missing, and malformed values are not silently coded as failures.
Any such value suppresses the complete-data point contrast and randomization
test and enters arm-level `[0,1]` bounds. The released contrast table also
contains Bonferroni-Newcombe 95% familywise intervals for the two primary
components and a wider intended-assignment sensitivity that reconstructs the
first arm from the block seed. Missing/noncompliant treatment records and
missing outcomes are sent to both worst-case endpoints; an unreconstructable
arm widens the contrast to `[-1,1]`. These are attrition bounds, not a
per-protocol effect.

Commit `55b5087`, also made while the H81 outcome gate was closed, replaces the
published Monte Carlo tail approximation with exact fixed-count Fisher
randomization inference. Conditional on the preterminal arm counts and total
number of successes, the three arm-success counts follow their finite
multivariate-hypergeometric law. The analyzer sums that support for the
one-sided and absolute contrast tails; the configured 100,000 permutations are
retained only as an implementation discrepancy check. A brute-force five-block
fixture enumerates all 30 assignments and agrees to machine precision. Commit
`5cc0a4a` makes the production check fail closed if the maximum exact-versus-
simulated tail discrepancy exceeds one percentage point.

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
- an unknown H81 outcome cannot become a failure or retain a point estimate;
- a noncompliant preterminal treatment record re-enters the intended-assignment
  worst-case bounds after a valid replacement opens the gate;
- the remote workflow is compaction-triggered, non-cancelling, publishing, and
  artifact-retaining.

The latest post-amendment preflight, workflow `29562343314`, ran code commit
`976468a`, pinned dataset revision
`8ce9eb75ed6ec76733a56d03b97b21ef55933345`, reported H81 counts 32/23/27 and
four of 120 H95 triplets, and queried no outcome field. The preceding compact
workflow `29561825717` passed preparation and all eight table shards. The full
repository suite after the fail-closed exact-inference audit reports 542 passes.
