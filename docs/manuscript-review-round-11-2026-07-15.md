# Independent-style review, round 11

Manuscript: *Displayed Is Not Deliverable: Capacity Certificates and Quote
Firmness in Inference Routing*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **6.5/10, borderline weak reject. The empirical package is now
reproducible and safely outcome-isolated, but the central randomized and
capacity-commitment effects remain unreleased or unimplemented.**

## Evidence added since round 10

The authors completed a fresh remote run of the entire experiment registry at
commit `dea9d37` and published it through GitHub Actions run `29435729411`.
The source audit is green. The public panel now contains 2,968,449 endpoint
snapshots and 1,805 five-minute runs over nine calendar days. The descriptive
owned-policy panel excludes 245 rows from four outcome-gated studies before
reporting its 716 legacy attempts.

The Brown--MacKay screen remains internally mixed. BM3 estimates a 10.48%
slow-over-fast cadence premium within model-day (transformed 95% CI
4.33%--16.99%). BM4's frozen temporal feature set
reduces holdout MAE from 0.1179 to 0.1123 and RMSE from 0.2152 to 0.2139 across
53 reactions. BM5 improves log loss from 0.0866 to 0.0806 and Brier loss from
0.0186 to 0.0156, but lowers AUC from 0.616 to 0.592. Most importantly, BM2's
frozen target still has zero fast-responder/slow-initiator risk pairs. The
paper correctly refuses to select the Brown--MacKay mechanism.

The H88 enrollment audit is now cumulative rather than first-run only. Three
remote captures yield 24 candidate blocks, 23 valid randomized assignments,
seven low-stress, nine high-stress, and seven default assignments across eight
models and fourteen candidate providers. Seed replay and pinned compliance are
100%, and the merged audit finds no cross-study overlap. Requested-provider
dominance is 31.25%, above the frozen 20% gate, and there are zero complete
days. No success, rejection, latency, selected-provider, or cost outcome is
released.

## Strengths

1. The paper distinguishes a statistically resolved cadence-price association
   from the unobserved fast-on-slow reaction implication.
2. H84 supplies a sharp negative mechanism test rather than merely an analogy:
   next-binding endpoints are not stale and cheap.
3. H86b resolves identifier support while proving that the public capacity
   fields, not only the join key, are absent.
4. H88 is preregistered, enrolls at close prices with meaningful public stress
   separation, and publishes an auditable outcome-free support panel.
5. The authors found a cross-analysis blinding hole before this full run,
   canceled the unsafe run before publication, centralized all four study IDs,
   and added regression tests across pandas and SQL-only consumers. The final
   remote publication therefore excludes every gated outcome from legacy
   aggregates.

## Remaining reasons for rejection

1. **There is still no released prospective treatment effect.** Twenty-three
   assignments are feasibility evidence, not a policy contrast, confidence
   interval, or randomization test.
2. **The Brown--MacKay reaction estimand is unsupported.** Predictive gains do
   not substitute for zero frozen fast-after-slow exposure, and the nine-day
   hazard panel has only 36 holdout events.
3. **Public enforcement stress is not certified capacity.** Even a future H88
   success effect would validate an account-level admission heuristic, not
   physical capacity, truthful reporting, provider cost, or market welfare.
4. **The proposed institution is not intervened on.** No reserved-capacity,
   collateral, audit, or liability arm has commitment, delivered-count,
   shortfall, fallback, and spend outcomes.
5. **The strongest public event study is descriptive.** H82 has a nonzero
   pretrend, while H84's backward placebo is also nonzero. These findings
   motivate mechanisms but do not identify them.

## Acceptance threshold

The next decision-relevant revision should release the deterministic first
qualifying H88 prefix regardless of sign, release at least one independent
prospective routing study at its frozen gate, and execute a direct capacity or
liability intervention. Additional retrospective model variants on the same
nine-day public panel would not change the decision.

## Decision

**Borderline weak reject.** The reproducibility and claim boundaries are now
strong, and the negative stale-quote result plus the failed public-capacity
bridge are publishable measurement lessons. The paper still lacks the released
randomized effect and implemented commitment mechanism needed for its central
market-design prescription.
