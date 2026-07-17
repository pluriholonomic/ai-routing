# Independent-style review, round 29

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **8.5/10, borderline / weak reject pending the registered H81
outcome release.**

## Summary judgment

This revision removes the last avoidable source of discretion before H81 opens.
The estimator, exact tests, uncertainty family, and one-time access transaction
were already frozen. The authors now also freeze the result table, two-panel
figure, and neutral manuscript paragraph. A fail-closed validator requires the
ITT/conditional-HT equality, exact component-sum identity, complete two-test
Holm family, one-block terminal exclusion, complete binary outcomes, and
registered treatment/outcome sensitivity fields before it will render.

The package was exercised on synthetic open-gate data. It compiled into a
legible one-page LaTeX section containing arm means, all three decomposition
contrasts, exact and Holm p-values, simultaneous design intervals, and the
finite-prefix claim boundary. The repository suite now has 573 passing tests.
Most importantly, exact-head workflow `29574825052` checked out the
presentation commit `65e1425`, pinned immutable dataset revision
`60d5a02005d`, and still reported `outcomes_queried=false`.

The same revision advances assignment-only H81 support from 92 to 94 blocks.
Counts are 34 delegated-default, 31 no-fallback, and 29 price-order fallback.
All 94 intended assignments reconstruct, replay, have a first row, and pass
treatment metadata. Six blocks have explicit prospective plans; 90 of 94 have
plan/eligibility-ledger coverage, with the four earliest blocks retaining their
recorded-seed fallback. The remaining deficits are 6, 9, and 11.

This is a real prerelease improvement, but it is not the focal empirical result.
The paper still has no randomized H81 effect estimate. I therefore remain just
below acceptance.

## Evidence reviewed

- Frozen presentation commit `65e142526962a61a3101edacb16af61caa21d46d`.
- Dated release-presentation amendment.
- `h81_release_report.py`, including validation and neutral interpretation
  rules.
- Synthetic LaTeX result table, neutral paragraph, PNG/PDF forest plot, and
  machine-readable report manifest.
- Focused 25-test result and full 573-test repository result.
- Scheduled H81 run `29573436177`.
- Compaction `29573860829`: durable publication and eight successful shards.
- Automatic gate audit `29574322884`.
- Exact-head pre-outcome audit `29574825052`.
- Checked-in assignment-only gate artifact with SHA-256
  `de9a2fd9a5db6c752868f3caca6ae66246649bf821cd469f8ee3153cc07f9e90`.

## Material improvements

### 1. Presentation discretion is frozen before the result

The renderer reports every component regardless of sign. It cannot suppress an
unfavorable contrast, replace the design interval with a narrower descriptive
one, omit the total identity, or describe nonsignificance as equivalence. The
neutral paragraph is mechanical rather than selected after seeing the result.
This is unusually strong release governance for a small owned-traffic study.

### 2. The output validator matches the theorem and stopped design

The report refuses an arm table whose counts do not sum to the preterminal
prefix, a release that excludes anything other than exactly one terminal block,
a mismatch between ITT and conditional Horvitz--Thompson estimates, or a total
contrast that is not the sum of fallback and hidden selection. These checks make
the paper-facing artifact part of the auditable statistical pipeline rather
than an informal transcription step.

### 3. The visual is appropriately conservative

Panel A presents intended-policy arm success means. Panel B presents all three
contrasts with the simultaneous finite-population design interval and the wider
treatment/outcome sensitivity bound. The plot does not imply that the
descriptive Newcombe interval is the design guarantee. It remains legible in a
single-column manuscript rendering.

### 4. Outcome-blind provenance is exact

The code, amendment, and supporting renderer are included in the first-access
hash set. The exact-head remote audit checked out that commit and queried only
assignment fields. This proves that the presentation template existed before
the focal outcome access, rather than merely being dated after the fact.

## Remaining reasons for rejection

### 1. The focal randomized outcome is still absent

H81 has no realized component estimate, design interval, Fisher tail, Holm
decision, or missingness pattern. The new package guarantees disciplined
reporting once the gate opens; it does not substitute for the result.

### 2. Precision is limited by design

At the minimum gate, a worst-terminal-policy component effect of roughly 35
percentage points is required for 80% Holm power on the frozen planning grid.
The simultaneous design interval is correspondingly wide. A null release cannot
establish equivalence or rule out economically meaningful moderate effects.

### 3. H81 transport remains narrow

The current 90 eligible rows cover two repeatedly eligible models with no
support turnover. Randomization identifies the finite stopped prefix, not a
market-wide effect. H95 is the correct independent transport study but remains
only 7 of 120 triplets and fails the current six-hour concentration gate.

### 4. Welfare and conduct remain outside the identified set

The study does not observe user value, provider marginal cost, router surplus,
cross-user ordering, or market-wide allocation. It cannot establish welfare
loss, collusion, literal front-running, or a welfare-maximizing entry count. The
manuscript is currently honest about these boundaries and should remain so.

## Required acceptance package

1. Continue the unchanged hourly H81 schedule without burst acceleration until
   each intended arm reaches 40.
2. At the first eligible immutable revision, execute the marker-first release
   exactly once.
3. Publish the already frozen table, figure, neutral paragraph, raw analysis
   tables, summary, code/environment hashes, and release manifest.
4. Report the preterminal counts and terminal policy, 90/94 current
   plan/eligibility coverage versus 100% assignment reconstruction, fidelity by
   arm, binary-outcome completeness, and treatment/outcome bounds.
5. Lead with both registered directional ITT components and their exact
   one-sided Fisher and Holm values. Report the total identity as an algebraic
   summary rather than a third primary test.
6. If either component is nonsignificant, call the result imprecise rather than
   equivalent. If the sign is negative, report it without changing the
   directional family.
7. Update the abstract and conclusion once around the realized result, while
   preserving the owned-account and finite-prefix boundary.
8. Continue H95 independently; do not pool it with H81 or stop it on a favorable
   sign.

## Decision

The score rises from 8.4 to 8.5 because the full paper-facing release is now
precommitted, tested, visually legible, and remotely proven outcome-blind. The
remaining rejection reason is singular and substantive: the focal randomized
effect has not yet been released. A clean registered H81 release, reported
through this frozen package without claim inflation, is the shortest path to an
acceptance recommendation.
