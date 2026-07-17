# Independent-style review, round 20

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **7.0/10, weak reject pending the registered releases.**

## Summary judgment

The paper is now structurally and inferentially ready for its focal randomized
result. The main argument is short enough for a conference submission, the
public-price claims are bounded by their actual identifying variation, and the
H81 release code is materially stronger than in round 19. I would not reject
this version for exposition, provenance, or an avoidable analysis defect.

I still cannot recommend acceptance because the paper's title contribution is
an experiment with no released outcome. The remaining gap is empirical rather
than editorial: H81, H95, and the 30-day PM1 holdout remain below their frozen
gates.

## Material improvements since round 19

1. **Unknown outcomes are no longer failures.** The H81 analyzer now recognizes
   `succeeded`, `failed`, and `cancelled` as binary outcomes while retaining
   `unknown`, missing, and malformed values as missing. A missing binary outcome
   suppresses the complete-data point estimate and conditional randomization
   test instead of improving or worsening an arm mechanically.
2. **Outcome attrition has explicit identified sets.** Arm success means receive
   `[0,1]` worst-case bounds, which propagate to both Hájek/arm-mean and
   conditional Horvitz--Thompson contrasts. The released schema exposes missing
   counts rather than hiding them behind complete-case means.
3. **Treatment-record attrition is handled separately.** The analyzer
   reconstructs the intended first policy from each frozen randomization seed.
   A missing, mismatched, or noncompliant treatment record is retained as an
   unknown outcome in its intended arm for the sensitivity analysis. If the arm
   itself cannot be reconstructed, every affected contrast widens to `[-1,1]`.
   The paper correctly labels this as intended-assignment attrition sensitivity,
   not a per-protocol effect.
4. **The primary family now has simultaneous uncertainty.** The two registered
   directional tests retain fixed-count conditional randomization and Holm
   adjustment. The paper also supplies Bonferroni--Newcombe 95% familywise
   intervals and labels them descriptive rather than pretending they are
   inverted randomization intervals.
5. **The changes precede outcome access and are tested adversarially.** Commit
   `4d66fda` was made while H81 remained at 31/23/26. Synthetic tests replace a
   success with `unknown` and corrupt one treatment record before accruing a
   valid replacement. Both failure modes widen or suppress inference as
   promised. The complete repository suite passes 540 tests after the PM1
   amendment below.
6. **The temporal estimator now matches its support.** The primary PM1 rung has
   17 parameters, so the former 50-training-event gate was not credible and an
   unpenalized logit could separate. Commit `1719ade`, made at 10/30 completed
   dates without querying pricing outcomes, freezes training-standardized ridge
   logistic regression (`C=1`, no holdout tuning). Promotion now requires 10
   training events and nonevents per parameter, 50 test events and nonevents,
   10 train/test event dates, and 10 test models. Complete separation remains
   finite; insufficient support cannot select a smaller model post hoc.
7. **The rendered artifact is sound.** The rebuilt paper is 31 pages including
   appendices, with the main argument ending on page 13 and references on pages
   14--15. The H81 analysis is legible in the main text and proof appendix; the
   claim ledger remains readable. There are no undefined references or overfull
   boxes.

## Remaining reasons for rejection

### 1. The focal causal estimates still do not exist

At pinned revision `8ce9eb75ed6e`, H81 has 82 verified first-position blocks
with counts 32/23/27. It therefore reports no success difference, interval,
randomization p-value, or realized missingness pattern. The analysis contract is
now credible, but a credible unopened contract is not an empirical finding.

### 2. The broad-support replication is still at launch scale

H95 has four compliant triplets and 12 blocks. Its eight unique models and
effective model count 7.20 show that the sampling frame can diversify support,
but four triplets contain essentially no effect information. The fixed
120-triplet horizon and within-triplet randomization must remain unchanged.

### 3. The temporal pricing claim remains descriptive

The leakage-resistant PM1 test correctly waits for 30 completed UTC dates and
uses the first 15 for training and the next 15 once. Only 10 completed dates
were available at the pinned revision, so the paper cannot yet say that lagged
market state predicts repricing out of sample. The older nine-day ladder remains
an in-sample diagnostic. The stricter events-per-parameter gate may correctly
return insufficient support even after the calendar gate opens.

### 4. H81 transport will remain narrow even after release

H81 repeatedly samples two adjacent ranking positions with no eligible-support
turnover. Its causal result will identify the owned-account policy effect over
those blocks, not a market-wide fallback value. H95 is the appropriate transport
study, and the manuscript must not pool the two or use H81 precision to imply
H95 breadth.

## Required next empirical package

1. At the unchanged 40-per-arm H81 gate, publish exactly the preterminal prefix
   and no later observations. Lead with the assignment/support audit, then report
   both primary effects, marginal and familywise intervals, conditional
   randomization p-values with Holm adjustment, the decomposition identity,
   outcome/treatment bounds, and leave-one-model-out estimates.
2. Preserve a null, sign reversal, missingness-driven identified set, or failed
   transport check as the main result if that is what the frozen analysis
   produces. Do not replace H81 with H80 or a later enlarged prefix.
3. Continue H95 to exactly 120 written triplets. Report blocked randomization,
   model and time concentration, missing planned requests, compliance, and
   leave-one-model-out results independently of H81.
4. At 30 completed pricing dates, run PM1 once at one immutable revision and
   report the date-weighted holdout log-loss contrast, its registered sign-flip
   family, both cluster bootstraps, and leave-one-model-out sensitivity. A failed
   event/support gate is a result and must not trigger a smaller post-hoc model.
5. After these releases, replace the abstract's design-status sentence with the
   observed sign, magnitude, uncertainty, and transport boundary. Do not add a
   new observational section in lieu of the randomized result.

## Decision

This is no longer a paper in need of another conceptual rewrite. It is a paper
waiting for its preregistered evidence. The implementation and manuscript can
support acceptance if H81 produces an interpretable finite-support result and
the authors report it without sign-dependent revision. H95 and PM1 determine how
far that result can be generalized. Until at least H81 opens, my recommendation
remains weak reject.
