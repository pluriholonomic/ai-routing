# Independent-style review, round 14

Manuscript: *Displayed Price, Hidden Clearing: Fallback and Selection in AI
Inference Markets*

Target: ACM EC / TEAC

Recommendation: **6/10, weak reject.** The rewrite has a much clearer economic
object and substantially better research governance. The focal randomized
experiment, however, has not released an outcome and currently spans only two
models. The manuscript is therefore a credible design-and-measurement paper
waiting for its principal empirical result, not yet an acceptance-level EC
paper.

## What changed successfully

1. **The focal question is now coherent.** The paper asks what clears through a
   displayed provider-model menu and what clears through hidden eligibility,
   delegated selection, and fallback. This is sharper than treating every price,
   steering, entry, and welfare result as an equal contribution.
2. **The institutional analogy is appropriately layered.** An open-weight model
   is a compatibility/production standard, the provider supplies perishable
   execution, the harness originates and transforms demand, and the router is a
   delegated procurement platform. The text now explains why a DEX-aggregator
   analogy is incomplete rather than simply asserting it.
3. **H81 matches the mechanism.** Cheapest-only, explicit fallback, and full
   delegation isolate two economically interpretable margins: fallback option
   value and hidden-selection value. This is a real improvement over trying to
   infer routing from an inverse-price public share formula.
4. **The stopping-rule correction is serious and transparent.** The paper
   recognizes that the gate-hitting assignment is mechanically selected,
   removes the terminal block, conditions on the preterminal count vector, and
   uses fixed-count randomization. The full proof and simulation audit are
   present. This materially improves credibility.
5. **Claim governance is unusually strong.** The paper pins a dataset revision,
   discloses the H80 gate amendment and H81 launch leak, separates discovery
   vintages from the current acquisition cut, and refuses to label one
   cross-router snapshot as pass-through. A machine-readable registry covers all
   seven theorem labels.
6. **The theorem checks are useful but correctly bounded.** Detection,
   coarsening, revenue-accounting, and entry checks test logic and code. The
   manuscript does not misdescribe them as empirical calibration.

## Main reasons this is not yet an accept

### 1. The headline randomized outcome is still unavailable

At the pinned cut H81 has arm counts 29, 22, and 25, below the original
40-per-arm release gate. Consequently the paper can report assignment replay,
compliance, support, and a gate forecast, but no fallback, selection, cost,
latency, or completion contrast. A top empirical mechanism-design paper cannot
be accepted on the design alone when the abstract and title point to fallback
and selection.

### 2. External support is far too narrow

The randomized support contains two repeated models, ranks five and six, an
effective model count of two, and no adjacent support turnover. Even a precisely
estimated H81 contrast will identify an owned-account effect on those eligible
blocks, not a general clearing mechanism. The paper needs the preregistered
fixed-horizon replication over a broader rotating model frontier.

### 3. The main text remains accretive

The rewrite says that price atoms, Brown--MacKay cadence, steering, revenue
elasticity, cross-router equality, entry, retry feedback, and conduct screens are
secondary, but it still devotes roughly half of the main text to them. This
weakens the new focal argument. Facts 1--2 can motivate the displayed layer in a
single compact section; most null construction, steering, revenue, entry, and
conduct material belongs in appendices or a companion paper.

### 4. The public operational evidence is not causal

H82 has failed pretrends. H84 rejects its directional stale-cheap prediction and
has a nonzero backward placebo. These are useful falsifications, but they do not
establish the clearing mechanism. The prospective H83/H85 holdouts need adequate
calendar support and owned-attempt linkage.

### 5. Cross-router evidence is still one cross section

The 28/29 exact-match result supports common upstream menu coverage. It does not
identify update leadership, pass-through, temporary wedges, eligibility
differences, or allocation consequences. Contract terms such as region,
capacity, context, caching, billing, and fallback are not yet normalized. H93
must remain a descriptive coverage fact until its longitudinal gates open.

### 6. The theory contribution is not yet coupled tightly enough to the design

The delegation decomposition is an estimand identity plus randomization theorem,
which is appropriate but modest. The most interesting next theory would derive
conditions under which delegated selection increases completion net of spend
and delay, and characterize what menu, eligibility, and attempt-log fields make
that comparison welfare-relevant. The free-entry benchmark is correctly
demoted, but it remains disconnected from identified primitives.

### 7. Blinding and independence remain imperfect

Two H81 launch-block aggregates were exposed by the legacy WCV4 path, and raw
source access remains technically possible. The paper discloses both facts, but
the confirmatory analysis should be executed from a clean runner by a release
script that hashes the frozen prefix, writes a one-shot result bundle, and logs
outcome access. Independent reproduction before submission would materially
strengthen the design.

## Required path to acceptance

1. Open H81 exactly once at the original 40-per-arm gate, using the corrected
   preterminal conditional analysis; publish success, latency, spend, missingness
   bounds, randomization intervals, and model-stratified results regardless of
   sign.
2. Freeze and launch the separate 360-block, fixed-horizon, stratified
   replication across at least eight models and effective model count at least
   five; do not pool it with H81.
3. Compress the main paper to the institutional setting, measurement hierarchy,
   two displayed-layer facts, H81 design/result, and design implications. Move
   steering, revenue, entry, retry, and conduct screens to appendices or a
   companion.
4. Complete prospective H83/H85 holdouts and link them to owned attempts using
   predeclared windows; keep the discovery failures visible.
5. Accumulate H93 longitudinal support and estimate pass-through only after all
   gates open; add a contract-comparability table before interpreting a price
   wedge.
6. Run the confirmatory release in a clean environment from the immutable data
   revision and archive the code commit, input hashes, environment lock, logs,
   and output hashes.

## Decision

**Weak reject, with a credible acceptance path.** The present rewrite is real
progress: it has a coherent question, a mechanism-matched experiment, corrected
inference, complete theorem proofs, and disciplined claim boundaries. Acceptance
still depends on observing the focal H81 outcome, broadening randomized support,
and removing secondary analyses from the main narrative.
