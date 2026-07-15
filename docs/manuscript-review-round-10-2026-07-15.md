# Independent-style review, round 10

Manuscript: *Displayed Is Not Deliverable: Capacity Certificates and Quote
Firmness in Inference Routing*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **6.5/10, borderline weak reject. The revision adds a sharp
mechanism rejection and a credible prospective execution design, but still has
no released randomized effect or intervention on capacity commitment.**

## What changed

The manuscript now adds three useful pieces after the H82 enforcement event
study.

First, H84 preregisters the DeFi-style stale-liquidity prediction that the next
rate-limit case should be an older, relatively cheaper quote. The result is in
the opposite direction: the case-minus-rival stale-by-cheap contrast is -0.118
(clustered 95% CI [-0.181, -0.056]) across 1,227 same-model choice sets, versus
-0.083 in the backward placebo. Quote age is null, and adding stale state does
not improve held-out conditional-choice prediction. The paper appropriately
concludes that this panel rejects the specified stale-cheap pickoff mechanism;
it does not claim that the negative coefficient causally identifies queueing.

Second, H86/H86b distinguish identifier failure from public-field failure. The
official model-ID bridge recovers 281 exact backward request/quote/provider
matches from 348 legacy attempts, but none contains the public capacity ceiling
and recent-peak fields needed to form a capacity-risk treatment. The first H87
prospective run and a top-40 support census likewise produce zero eligible
capacity pairs. Reporting this as missing treatment support rather than a null
capacity effect is methodologically correct.

Third, H88 is separately preregistered around the populated five-minute public
success and rate-limit counts. It randomizes one first-and-only request among a
price-matched low-stress provider, high-stress provider, and default routing.
The first remote run enrolls all eight evaluated models, twelve candidate
providers, and eight requests. The outcome-free artifact passes seed replay and
pinned compliance. Outcomes remain masked behind 28-day, 150-per-arm, model,
provider-diversity, concentration, compliance, and overlap gates.

## Material improvements

1. **The paper now falsifies a natural analogy instead of merely discussing
   it.** H84 is an informative negative result against stale-cheap liquidity
   pickoff in the observed public panel.
2. **Public data limitations are decomposed.** The official identifier bridge
   works, while the capacity-state variables do not. This is stronger than a
   generic claim that the join is difficult.
3. **The failed H87 design is preserved.** The authors do not redefine
   capacity around an available proxy after discovering zero support.
4. **The replacement treatment is operationally measurable.** H88's first run
   achieves 8/8 enrollment with substantial stress separation at close prices.
5. **Outcome masking is credible.** The manuscript displays only candidate
   state, assignments, replay, compliance, and distance to release gates.
6. **The Brown--MacKay comparison is appropriately bounded.** Heterogeneous
   cadence is established, but reaction-rule exposure is absent in the frozen
   holdout and the paper does not infer algorithmic collusion.

## Remaining major concerns

### 1. H88 has enrollment, not a result

One safe, three risky, and four default assignments provide no releasable arm
contrast. The current candidate-provider dominance is also 25%, above the
frozen 20% gate. Until the earliest qualifying prefix is released, H88 adds
feasibility rather than causal evidence.

### 2. Public enforcement stress is not certified capacity

Even a positive H88 low-minus-high success effect would validate an admission-
risk heuristic for the probed account and workload. It would not identify
physical capacity, marginal cost, truthful reports, other-user flow, or the
welfare gain from a capacity certificate. The paper states this clearly, but
the theory-to-data gap remains.

### 3. H84's backward placebo is nonzero

The negative forward stale-by-cheap result is robust and useful as a rejection
of the positive hypothesis. It is not a clean directional causal effect because
the backward placebo is also negative, quote spells are left-censored, and the
panel is short.

### 4. The clean randomized portfolio is still gated

H80, H81, H83, H85, and H88 expose no confirmatory outcome. The reader can
audit the designs, but cannot yet compare an identified delivery effect to the
descriptive H82 and H84 regularities.

### 5. No commitment mechanism is implemented

The formal mechanism still assumes certified or collateralized capacity,
collectable liability, and an independently assigned audit. No experiment
randomizes any of those primitives. The empirical section motivates the need
for deliverability information; it does not validate the proposed institution.

## Required package for an accept

1. Publish the deterministic earliest supported H88 prefix with the frozen
   cluster intervals, randomization inference, Holm correction, compliance,
   provider diversity, and overlap audit, regardless of sign.
2. Release at least one of H80/H81/H83/H85 at its frozen gate so the paper has a
   second prospectively identified result or informative rejection.
3. Add a direct commitment intervention: randomized reserved capacity,
   collateral, or an audit/liability condition with delivered-count,
   shortfall, fallback, and spend outcomes.
4. Preserve H84 as a discovery-sample mechanism rejection and report H85's
   future-only first cut without changing the direction or sample gates.
5. Keep the theory conditional and do not translate H88 admission success into
   market-wide welfare without provider cost, user value, and displacement
   measurements.

## Decision

**Borderline weak reject today.** The empirical program is substantially more
credible because it records a negative mechanism test, a failed data-support
bridge, and a separate randomized design that demonstrably enrolls. These are
real contributions to measurement discipline. They do not yet supply the
released prospective effect or commitment intervention needed to validate the
paper's central institutional prescription. The next review should be triggered
by a frozen release gate or a direct intervention, not another retrospective
reanalysis of the same public panel.
