# Independent-style review, round 28

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **8.4/10, borderline / weak reject pending the registered H81
outcome release.**

## Summary judgment

This revision closes the operational concern left by round 27. The H81
intended-assignment ledger is no longer a locally tested design awaiting
deployment. A clean remote collector persisted prospective plan rows before the
request loop, published a separate outcome-free commitment, redacted outcome and
selected-provider fields from the capture log, entered the plan rows into the
durable dataset, and passed an automatic assignment-only audit at an immutable
revision.

The audit advances H81 from 84 to 92 intended first-position blocks, with counts
33 delegated-default, 31 no-fallback, and 28 explicit-price-order fallback.
Every intended assignment reconstructs and replays; every first row is observed;
all treatment metadata pass. Four blocks now carry explicit prospective
pre-request plans. The outcome gate remains closed, with deficits 7, 9, and 12.
H95 advances from five to seven of 120 triplets, but remains far from release and
fails its current time-concentration gate.

The manuscript also improves presentation by replacing a long main-text history
of outcome-blind amendments with the final reference experiment and moving the
genealogy to the appendix and release ledger. This is the right editorial choice:
the paper should be judged on its current design, while retaining a complete
audit trail for reproducibility.

I still cannot recommend acceptance because the paper's focal randomized
empirical result has not been observed. The revision is now operationally ready
for that result; readiness is not a substitute for an effect estimate.

## Evidence reviewed in this round

- Collector workflow `29572631254` at source head `c37fc6b`.
- The outcome-free two-row plan commitment and its checked-in manifest.
- Log redaction removing realized provider, outcome, latency, and cost fields.
- Compaction workflow `29572789506`: 571 tests, durable publication, and eight
  successful deterministic shards.
- Automatic confirmatory audit `29573258132` at dataset revision
  `18ea5aa245cc931d5f49b452785a175f358db240`.
- The assignment-only H81 gate artifact and its SHA-256 commitment.
- Updated H81 and H95 support panels, claim ledger, limitations, and
  reproducibility chronology.
- The compressed main-text description and unchanged full amendment ledger.

## Material improvements

### 1. Prospective plan persistence is now demonstrated, not asserted

The collector writes and closes the plan object before `_send_probe`; a failed
write aborts before the request loop. The production run produced two plan files
and two plan rows at one-third assignment probability. The independently
downloadable manifest includes hashes and schema checks but no request record or
outcome field. This is appropriate evidence for the operational claim.

### 2. The audit surface now respects the study's blinding boundary

The earlier mixed request artifact was broader than necessary for deployment
verification. The revised workflow publishes a plan-only manifest and removes
realized provider, outcome, latency, and cost from capture logs. The confirmatory
artifact below the gate contains only release status and assignment-only gate
files. This materially reduces analyst discretion and accidental leakage.

### 3. End-to-end lineage is complete

The plan commitment is tied to the exact source head and workflow run. The
compactor published it, all table shards succeeded, and the child release runner
pinned a new immutable dataset revision. The resulting gate records four
explicit prospective plans, 44 replayed historical runs, zero failed legacy
reconstructions, and `outcomes_queried=false`. This closes the specific
deployment item in round 27.

### 4. The manuscript now presents one design rather than a correction diary

The main text states the intended-assignment ITT experiment, stopped-prefix
reference law, inference family, current support, power boundary, and transport
limit. Commit-by-commit history remains available in the appendix and dated
ledger. The edit is both shorter and more credible.

## Remaining reasons for rejection

### 1. No focal randomized outcome has been released

H81 has no effect size, confidence set, Fisher tail, Holm decision, selected-
provider contrast, or realized missingness bound. The paper's central empirical
claim therefore remains a design and an accrual report. ACM EC or TEAC acceptance
requires the registered release or a reframing in which H81 is not the focal
empirical contribution.

### 2. Precision and transport remain limiting even after release

The smallest arm is 28. At the minimum gate, worst-terminal-policy 80% Holm power
requires roughly a 35-point component effect on the frozen grid, and the
model-free design interval is wide. H81 still covers two repeated models. A null
result will not establish near-equivalence or market-wide efficiency.

### 3. Plan-ledger coverage needs one sentence of careful interpretation

The gate reports plan coverage 88/92, or 95.65%, while assignment reconstruction
is 100%. This is not a failed integrity check: four earliest blocks predate the
plan/eligibility ledger and use their recorded block seeds; four later blocks
have explicit prospective plans, and the intervening historical runs are
reconstructed from eligibility RNG state. The paper should preserve this
distinction and never abbreviate 95.65% plan coverage as 100% plan persistence.

### 4. H95 remains an accrual design rather than replication evidence

Seven triplets give 21 first-position blocks over nine unique models, and all
nine auditable provider-control rows pass. However, 113 triplets remain. Four of
seven triplets fall in the largest six-hour bin, so the frozen time-transport
gate fails. No H95 outcome is available, and it cannot be pooled with H81.

### 5. Welfare, conduct, and literal front-running remain outside the identified set

Owned-account policy effects do not identify market-wide allocation, private
provider cost, router surplus, user value, cross-user ordering, collusion, or
social welfare. The paper is appropriately cautious; acceptance should not be
obtained by weakening those boundaries.

## Required acceptance package

1. Continue the frozen hourly H81 schedule without burst acceleration or support
   changes until every intended arm reaches 40.
2. Execute the marker-first release exactly once at the first eligible immutable
   revision.
3. Lead with ITT component effects and the total identity, exact pairwise Fisher
   tails, Holm decisions, design-valid and descriptive intervals, fidelity by
   arm, and measurement-missing bounds.
4. Report the terminal-block exclusion, realized preterminal counts, and the
   distinction between 95.65% plan-ledger coverage and 100% assignment
   reconstruction.
5. Treat a null as low power for modest effects; do not call it equivalence.
6. Continue H95 independently to 120 triplets and open PM1 only at its fixed
   completed-date gate.
7. Preserve the current compact main-text design and keep the full amendment
   genealogy in the appendix.

## Decision

The score rises from 8.2 to 8.4 because the intended-assignment correction is now
deployed end to end, independently auditable without outcome access, and
presented coherently. The remaining obstacle is substantive rather than
operational: the paper still lacks its focal randomized effect. The shortest path
to acceptance is the unchanged H81 release, followed by disciplined reporting at
the registered estimand and claim boundary.
