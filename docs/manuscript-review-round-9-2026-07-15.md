# Independent-style review, round 9

Manuscript: *Displayed Is Not Deliverable: Capacity Certificates and Quote
Firmness in Inference Routing*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **6.5/10, borderline weak reject. The new enforcement result
is an original and economically meaningful measurement object, but neither it
nor the randomized probes yet identifies the mechanism's welfare claim.**

## Summary

This revision adds a high-frequency study of public router enforcement to the
capacity-certificate mechanism and randomized micro-probe design. H82 retains
231 complete, isolated high-intensity rate-limit onsets from 503,321 endpoint
snapshots. Focal endpoint successful-request share falls by 2.09 percentage
points (model-day cluster-bootstrap 95% CI [-3.17, -1.11]); focal provider
share falls by 2.08 points. Matching each high onset to a low-intensity onset
in the same model using only pre-event volume, UTC hour, and calendar distance
gives -2.57 and -2.56 point contrasts. Every leave-one-provider-out endpoint
estimate remains negative, and every complete event window has a constant
posted completion price.

The paper does not overstate this evidence. All three frozen pretrend tests
fail. The matched other-provider-volume interval contains zero, and exact
raw-count accounting shows model-wide successful volume falling rather than
the focal loss being recovered by rivals. H82 is therefore labeled a
price-invariant capacity-event signature, not causal substitution,
front-running, or a welfare effect. The analysis is now frozen at its exact
last discovery timestamp, 2026-07-15 11:33:02 UTC. The freeze is transparently
identified as post-result and prevents any later observation from entering
both H82 and the separately preregistered H83 holdout.

H83 converts the conspicuous H82 pretrend into a falsifiable future-only
capacity-overshoot hypothesis: load before onset, break after onset, partial
recovery, and sticky price. It begins after the discovery cut, masks every
coefficient until sample-only gates are met, and requires release of the first
eligible cut whether the shape confirms or rejects the hypothesis. At present
it has no eligible future observations, so no outcome is exposed. The H80 and
H81 randomized routing studies also remain below their frozen 40-per-arm
release gates.

## Material improvements

1. **A market-relevant hidden-capacity margin is observed.** Successful share
   changes on a five-minute horizon while the posted money quote remains fixed.
   This is a sharper empirical motivation for capacity certificates than quote
   dispersion alone.
2. **The result is not a one-provider artifact.** It spans 22 models and 38
   providers; the largest provider supplies 15.6% of events, and every
   leave-one-provider-out endpoint estimate is negative.
3. **The main contrast survives a pre-treatment control design.** The
   high-minus-low matched endpoint contrast is -2.57 points with an interval
   excluding zero. This strengthens the descriptive regularity, though it does
   not repair endogenous onset timing.
4. **Accounting is exact and unfavorable evidence is retained.** The additive
   raw flow identity has zero snapshot residual. The average rival component
   is negative and tail-sensitive, so the paper refuses a recovered-flow claim.
5. **Discovery and confirmation are separated.** H82 is immutably capped at
   the observed discovery snapshot. H83 is future-only, coefficient-masked,
   sample-gated, and has a non-significance stopping rule.
6. **The empirical portfolio now has complementary designs.** Public
   enforcement supplies broad observational coverage; H80/H81 supply narrow
   randomized identification; H83 prospectively tests the newly discovered
   dynamics. Their populations and claims are not pooled.

## Remaining major concerns

### 1. H82 is not a causal enforcement estimate

The endpoint is already gaining share before the high rate-limit onset. Its
early-to-late pre-period placebo is +0.71 percentage points with an interval
excluding zero. This is consistent with load causing both the impending
constraint and the subsequent routing response. Matching on pre-event level,
hour, and date does not condition away the dynamic loading path. The result is
important descriptively but cannot identify substitution caused by router
enforcement.

### 2. Rival recovery and welfare are not established

The matched log rival-volume interval crosses zero. On jointly observed raw
cells, focal endpoint successes fall by 456.6 and total model successes fall by
512.2 on average. A winsorized rival component changes sign, indicating tail
sensitivity. These data do not show that the router preserved demand, improved
consumer surplus, or implemented the proposed robust allocation.

### 3. The public panel is short

H82 covers 7.66 days and seven complete calendar days, versus its frozen
28-day gate. Although event, model, provider, and concentration gates are met,
the time support does not address weekly demand cycles, provider maintenance,
or market-regime dependence. H83 appropriately requires a longer future panel.

### 4. The randomized studies are still outcome-gated

H80 has only 16 verified position-zero blocks with arm counts (5, 2, 2, 7).
H81 has six blocks with counts (3, 1, 2). These designs are the cleanest path to
selection and fallback effects, but their confidence intervals and economic
magnitudes remain intentionally unavailable.

### 5. The mechanism itself remains a design proposal

No experiment varies a collateral requirement, capacity certificate, audit
rule, or robust allocation policy. H82 measures why a deliverability margin
matters; H80/H81 measure existing-router policy value. Neither identifies the
welfare gain, incentive compatibility, or budget consequences of the proposed
mechanism.

## Required package for an accept

1. Release the deterministic earliest balanced H80/H81 prefixes only after
   every frozen arm gate passes, with randomization inference, multiplicity
   control, repeated-model support, and policy-compliance diagnostics.
2. Run H83 to its first sample-supported cut and publish it regardless of sign.
   Report loading, break, recovery, and level-loss components for endpoint and
   provider share, matched low-onset controls, cluster intervals, and
   leave-one-provider-out support.
3. Add a commitment intervention, even on a small selected market: randomize a
   binding capacity declaration or collateral/audit condition and measure
   delivered count, fallback cost, and shortfall against the existing-router
   baseline.
4. Preserve the exact flow decomposition and report whether any demand loss is
   recovered within-model, delayed beyond 60 minutes, or leaves the router.
5. Keep H82 permanently descriptive and never pool its events into H83.

## Decision

**Borderline weak reject today.** The enforcement panel is a substantial
addition: it supplies a novel, broad, provider-diverse fact about AI inference
markets that is tightly connected to the theory and more informative than a
generic price-dispersion comparison. The authors' treatment of failed
pretrends and adverse accounting is unusually credible. An accept is now
plausible, but it requires either a released randomized routing effect plus a
successful or informative H83 holdout, or a direct intervention on capacity
commitment. The current evidence identifies a hidden operational margin, not
the welfare performance of the proposed mechanism.
