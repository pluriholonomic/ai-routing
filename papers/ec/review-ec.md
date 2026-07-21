# ACM EC adversarial review

## Summary

This paper asks what can be learned about an AI inference marketplace when
posted prices are public but eligibility, capacity, fallback, provider cost, and
delivered quality are partly hidden. It formalizes the router as a
multi-attribute procurement intermediary, proves conditional results for
inverse-power and entropy-regularized routing, gives an omitted-attribute regret
identity and a hidden-capacity impossibility, and then builds a sequence of
property tests from a remotely collected market panel and owned probes.

The empirical section is unusually disciplined. Pricing regimes are stable
except for active undercutting; immediate rival response is indistinguishable
from a shifted timing placebo; public inverse-square shares fail as realized
allocation; capacity utilization and dumping are not identified; and the
current HMP-style covariance result is nominal but too concentrated and
family-incomplete to promote. The design section consequently proposes
execution-contingent capacity, generalized scoring, bounded exploration, fee
separation, and a randomized policy-frontier experiment rather than claiming a
welfare optimum from public menus.

## Strengths

1. The paper chooses the correct economic object. The router is not merely a
DEX aggregator; it is a delegated buyer operating a two-layer procurement
market with hidden admission, stochastic execution, fallback, and quality.
This materially improves the analogy and makes the information ladder useful.

2. The claim boundaries are first-class results. The paper states precisely
which objects each source identifies and prevents shadow share, owned-account
share, and realized market-wide flow from being conflated. The updated HMP
screen is handled correctly: nominal p approximately 0.05 is not promoted when
one pair contributes 87.3 percent of events and later family members are
missing.

3. The mechanism theory is compact and operational. The exact KL regret
identity explains why omitted service attributes matter; the 2-epsilon score
bound gives an auditable approximation target; and the hidden-capacity
construction shows why quote-only randomization cannot be robustly efficient.
These are simple results, but together they organize the empirical design.

4. The policy recommendation follows the evidence. A held-out replay is called
a mechanical frontier, not welfare. The proposed production experiment freezes
the score, randomizes within blocks, measures completion, latency, spend, and
blinded fidelity, and keeps scalar welfare contingent on declared value and
cost boxes.

5. Reproducibility is strong. The seven-page ACM build has no unresolved
references or layout failures, the empirical figure is generated from a
checked-in hosted-evidence snapshot, and the source revision and failed gates
are visible.

## Weaknesses

1. The strongest policy experiment is prospective. The paper does not yet
observe realized welfare, provider marginal cost, or a randomized change in the
routing score. This is not a correctness problem because the prose is careful,
but it limits the empirical contribution relative to the best EC field papers.

2. The principal theoretical identities are elegant applications of standard
entropy regularization, robust scoring, and indistinguishability arguments.
The novelty lies more in assembling them around the inference-market
information problem than in theorem depth.

3. The panel is measured in weeks, not quarters, and one platform and one owned
account dominate. A longer panel can improve precision but cannot by itself
recover private capacity or costs; the data-partnership and randomized
experiments remain necessary.

4. The paper's provider categories are useful regimes but not structural types.
The paper says this consistently. A future version could model regime
transitions jointly with capital technology, but doing so with current data
would require unsupported assumptions.

## Required changes

No correctness-critical changes. For a camera-ready version I would request:

- place the prospective policy-frontier protocol and primary estimands in a
short boxed design;
- add a one-line table connecting each theorem to the field required to
operationalize it;
- report the next frozen snapshot without changing the current result's claim
boundary.

## Score

- Soundness: 4/4
- Significance: 3/4
- Novelty: 3/4
- Reproducibility: 4/4
- Overall: 7/10, Accept
- Confidence: 4/5

## Decision

**Accept, but not strong accept.** The paper is a credible EC contribution
because it turns hidden clearing into an explicit identification and mechanism
design problem. A completed randomized mechanism experiment or a deeper
implementation theorem would move it to strong accept.
