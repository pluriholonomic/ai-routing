# Independent-style review, round 7

Manuscript: *Displayed Is Not Deliverable: Capacity Certificates and Quote
Firmness in Inference Routing*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **5.5/10, weak reject; the new decomposition is promising,
but the confirmatory outcomes remain power-gated.**

## Summary

The revision studies inference routing when displayed provider prices are not
request-level commitments. It combines a capacity-certificate mechanism, a
Brown--MacKay pricing-technology screen, a fixed-order routing pilot, and two
prospective randomized experiments. H80 removes the pilot's order confound.
New H81 randomizes among cheapest-only/no-fallback, public-price-order with
fallback, and delegated default routing. A new proposition shows that a
two-arm default-versus-pinned experiment cannot identify fallback option value
separately from hidden-selection value, even under monotonicity, whereas H81
does identify both components.

This is a material improvement. The three-arm decomposition is a sharper and
more market-specific empirical contribution than the generic first-position
Horvitz--Thompson result. The collection implementation is also unusually
auditable: assignment seeds are replayed, treatment controls are checked,
outcomes are blinded until a fixed balance gate, and the earliest qualifying
prefix is frozen. However, the paper still has no confirmatory H80 or H81
outcome. The first H81 launch audit contains only two eligible model blocks.
I would not accept an empirical paper whose central identified estimands are
still blank, but the design now gives a credible path to an accept.

## What changed my assessment

1. **A genuine non-identification point.** The decomposition proposition is
   simple but economically useful: fallback and private selection are distinct
   products supplied by a router, and a default-versus-pinned comparison
   reveals only their sum.
2. **The experiment now matches that object.** H81 holds the public cheapest
   first provider fixed when turning fallback on, then holds fallback on when
   replacing the public order with delegated selection. This is substantially
   closer to the paper's hidden-eligibility thesis.
3. **Pre-outcome implementation audits are strong.** The first remote artifact
   has two complete blocks, two of two successful assignment replays, and two
   of two treatment-metadata checks. No outcome or p-value is released.
4. **Operational interference is addressed.** H80 and H81 share a non-cancelling
   concurrency lock, so delayed GitHub cron starts cannot overlap the studies.
   The amendment was recorded before H81 outcomes were released.
5. **Off-machine durability is credible.** Hourly artifacts are included in
   nightly consolidation, the remote watchdog covers both experiments, and the
   first H81 artifact reached the Hugging Face sink.

## Remaining major concerns

### 1. No identified empirical result is yet available

The H80 gate requires 40 first-position assignments in each of four arms; H81
requires 40 in each of three arms. Until the deterministic first balanced cuts
are reached, the paper has a strong design and a confounded pilot, not a new
causal result. The launch audit must not be presented as evidence about policy
performance.

### 2. H81 support is narrower than planned

Only two of the four candidate ranking positions were eligible in the first
run because H81 requires at least two displayed positive-price providers. The
paper should report the eligibility funnel, models excluded and why, temporal
turnover in support, and the estimand's target population. If the same two
models dominate every hour, nominal block count will overstate external
support even though time-block randomization remains valid.

### 3. The mechanism remains only indirectly tested

H81 identifies the value of fallback and delegated selection, not the welfare
effect of capacity certificates, collateral, audits, the robust LP, or VCG
payments. The revision tightens the motivational link but does not validate
the proposed mechanism. The paper should be framed primarily as a measurement
and identification contribution, with the capacity mechanism as a disciplined
design implication unless an actual commitment-policy experiment is added.

### 4. The hidden-selection label needs continued restraint

The delegated-versus-public-order contrast may reflect private eligibility,
latency scores, account routing, contracts, undisplayed providers, or other
state. It does not isolate a single private signal. “Hidden-selection value” is
acceptable as a treatment label only if the paper keeps this composite-channel
boundary prominent.

### 5. Missingness and repeated support need prespecified reporting

The confirmatory tables should include attempted-request success as ITT,
selected-provider and accounting missingness by arm, hourly/model clustering,
the frozen prefix cutoff, and sensitivity to repeated observations on the same
model. Spend and latency should remain secondary and should not condition the
primary sample on success.

## Required result package for the next review

1. Release exactly the first frozen H80 and H81 cuts, not the latest larger
   download.
2. Show arm counts, seed replay, treatment-metadata compliance, entropy, model
   support, and the eligibility funnel before effect estimates.
3. Report H80's three prespecified success contrasts and H81's two primary
   components with randomization p-values, Newcombe intervals, model-stratified
   Horvitz--Thompson estimates, and the prespecified Holm families.
4. Report total delegation only as H81's secondary accounting identity and
   verify numerically that the two components sum to it.
5. Give missingness bounds for spend, latency, and selected-provider outcomes;
   never interpret observed billed spend as provider cost or social welfare.
6. Compare H80's total default-versus-cheapest effect with H81's total effect
   only as a cross-study validation because model support and candidate sets
   differ.
7. Keep the Brown--MacKay result negative: cadence heterogeneity and a slow
   provider premium are present, but the competitive reaction gate fails.

## Correctness and novelty

The decomposition identity and non-identification argument are correct as
stated. Their novelty is not mathematical depth; it is the recognition that
fallback and private selection are separately priced router services and the
construction of an auditable experiment that varies them one at a time. That
combination could support a publishable market-design measurement result if
the confirmatory estimates are economically material and stable across model
and time support.

## Decision

**Weak reject today.** This revision clears the earlier design-to-estimand
objection and is now waiting on data rather than another conceptual rewrite.
An accept is plausible after the preregistered cuts if at least one component
is precisely identified, the eligibility funnel is transparent, and the paper
does not overclaim direct validation of the capacity mechanism.
