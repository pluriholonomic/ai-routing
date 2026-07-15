# Referee Report — "The Market for Machine Intelligence" (v1)

*Reviewer stance: ACM EC senior PC / AEJ:Micro referee. Recommendation at end.*

## Summary

The paper assembles an impressive novel dataset on AI inference pricing and
documents five stylized facts (administered menus, focal anchoring at the
author's price, quantity-clearing, retry amplification, flat entry), plus
conduct audits. The data construction is genuinely valuable and several
observations are new to the literature. However, in its current form the
paper is a buffet of descriptive findings with two under-identified headline
claims, and its strongest potential contributions are underdeveloped.

## Major concerns

**M1. The retry-externality estimate (Fact 4) is not identified.** The
authors regress forward request growth on current rate-limit share within
endpoint and argue mean-reversion biases phi downward. This is exactly
backwards under the paper's OWN Fact-5 machinery: demand is long-range
dependent, so bursts persist — a burst raises rl_share at t AND req at
t+30m mechanically. phi > 0 may be pure demand persistence, not retry
feedback. The conservative-bias claim is unsupportable as stated. Required:
(i) control for contemporaneous and lagged demand growth; (ii) an
instrument for rl_share that is orthogonal to own-model demand — e.g.,
provider-level rate-limiting driven by the SAME provider's OTHER models
(capacity spillover), or incident windows from the status-page feeds the
authors already collect; (iii) at minimum, a placebo at negative lags.
Without this, the paper's most original welfare claim is an artifact
candidate.

**M2. The tie atom needs a null model.** Prices sit on a coarse cent grid
(93% of quotes; the authors' own Fact 1). Independent pricing on a coarse
common grid mechanically produces exact ties, and low prices (many models
are cheap) compress the grid's support. The 46%-tie and gap-hole findings
are meaningless without the expected tie rate under independent
grid-constrained pricing. Simulate: preserve each provider's marginal price
distribution per model, break dependence, compute the tie-rate null. The
90%-at-author-price result is more robust to this critique (a specific
level, not just any tie) but the authors should report what fraction of
grid-coincidences would hit the author price by chance given its
round-number location.

**M3. The entry-law "conjecture" is numerology as written.** The point
match (0.161 vs 0.165) uses an H estimated by a different method at a
different scale than the theory requires, and the authors' own robustness
attempt (30-minute Hurst) produces H ~ 0.36 — which would predict a slope
of 0.64, wildly off. The honest content is: entry is very flat (0.15-0.17),
strongly rejecting sqrt/cube-root benchmarks. Either (a) derive the
correction properly (specify the burst-contest model, prove k* ~
n^{(2-2H)/2} under stated assumptions, and defend the relevant H horizon
theoretically), or (b) demote the conjecture to a remark. Also: the
simultaneity discussion is one sentence; instrument or bound it (model-age
or author-family instruments suggest themselves).

**M4. One paper, or three?** The venue-appropriate core is, in this
reviewer's judgment: (i) Facts 1-3 as one coherent characterization
("administered menus + focal anchor + aggregate-firm quotes"), which is
publishable descriptive economics on a novel market; and (ii) EITHER the
steering audit OR the retry externality, properly identified, as the
analytical contribution. The conduct section, welfare framework (C1-C10),
calibrated regret, adoption DiD, and umbrella tests are each two paragraphs
of an under-powered result; they dilute. Cut or move to appendix/companion.

**M5. Panel length.** Eleven days for the hazard ladder (110 events), the
conduct IRFs, and everything in Section 8 is thin for a top venue even with
pre-registration. The 3-year backfill supports Fact 1's levels/durations
but nothing dynamic. The paper would be materially stronger with 60-90 days
— several registered tests (anchor repricing, ABS pass-through) would
plausibly fire in that window. If submission timing is fixed, the dynamic
claims need explicit "early-panel" labeling in the abstract, and in-sample
AUC must be replaced by a day-split out-of-sample number.

**M6. Telemetry endogeneity.** Utilization and rate-limit measures are
router-published. If the router's reporting responds to its own routing
decisions (e.g., deranked endpoints stop reporting), several regressions
condition on outcomes. A data appendix must document the telemetry's
generating process and demonstrate robustness to reporting gaps.

## Minor

- The pinned-probe firmness numbers conflate provider rate limits on THIS
  key with market firmness; say so in the text, not only in limitations.
- JRW audit: eligibility (region, context length) unmodeled — a cheapest
  provider may be ineligible for the probe; bound the misclassification.
- "90% of ties at author price" — report the denominator (72 models) in the
  main text; it reads as universal.
- The abstract over-claims "first measurement of the retry externality"
  given M1.
- Kurtosis 3.54: report per-provider distribution, not just the pooled
  standardized figure.

## Assessment

Novel data, several genuinely new observations, transparent
pre-registration culture — but the two analytical headliners are not yet
identified (M1, M3), one central fact lacks its null (M2), and the paper's
breadth dilutes its contribution (M4). This is a strong revise-and-resubmit
at a field journal or a reject-encourage at EC in current form.

**Recommendation: MAJOR REVISION (reject and resubmit). Not accepted.**

Concrete acceptance path: fix M1 with controls+instrument+placebo; add M2's
null simulation; restructure per M4; replace in-sample AUC with day-split
OOS; re-estimate everything on the longer panel that accrues automatically.
