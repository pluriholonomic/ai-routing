# ICML adversarial review

## Summary

This paper studies a finite-memory pricing penalty in an AI inference routing
game. A provider can stay at a high quote or cut persistently; the cut is
temporarily penalized by the router but eventually earns more. The paper
separates two thresholds. An exact economic threshold M-star says when
persistent cutting is rational. A finite-time threshold says when a learner
with post-readiness cut probability bounded by q can obtain a fresh length-M
support path: the conditional probability is at most T times q to the M, and
the iid expected wait is exact.

A path-equivalent commit-low option preserves the primitive optimal value while
reducing path proposal time to a linear term. In the frozen calibrated MDP,
primitive Q chooses the rational action in 1/20 seeds at M=7 versus 19/20 with
the option; paired normalized regret changes by -0.0643 with interval
[-0.0755, -0.0493]. The option overcorrects beyond the economic boundary.

The most persuasive diagnostic replays the frozen learners. Every seed visits
all 256 state-action pairs at least nine times and reaches the all-low state by
step 901. Nonetheless, 19/20 online Q learners fail, none of those failures
reaches depth five after step 100,000, and ordered batch Bellman sweeps on the
same empirically observed deterministic transitions recover the rational cut
in 20/20 seeds. Full state, ordinary eight-step TD, and universal transport
each fail separate tests.

## Strengths

1. The paper identifies a precise computational object. The result is not
merely that exploration is insufficient: aggregate state-action coverage is
complete. What fails is the late temporal ordering required for one-step
Bellman credit to propagate after downstream values separate.

2. The economic and learning boundaries have opposing implications. Below
M-star, commitment can repair a learning failure; above M-star, the same
interface induces excessive cutting. This nonmonotonicity prevents the paper
from recommending temporal abstraction as a universal optimization trick.

3. The theorem is sharp within its assumptions. The adaptive-policy union
bound is conditional on an arbitrary stopping time, the iid waiting time is
exact, and the option's expected primitive duration is linear. The SNR
corollary correctly states that better reward estimation can move readiness
but cannot change the conditional fresh-path probability.

4. The falsification ladder is unusually strong for a learning-in-games paper.
State aliasing is rejected, universal cross-market trap severity is rejected,
and an eight-step TD target fails. The post-hoc trace is clearly labeled and
reconciles every terminal Q-table to the immutable E-SIM6 artifact.

5. The connection to pricing algorithms is substantive rather than cosmetic.
Hansen--Misra--Pai show coordination through coupled scoring without explicit
memory; this paper supplies a finite-time temporal channel. Johnson--Rhodes--
Wildenbeest motivates platform history, while the calibrated router turns it
into an executable MDP.

6. Reproducibility is excellent. The mathematical identities have unit tests;
exact Bellman values and option equivalence are checked; frozen run hashes and
seeds are listed; and the figure is built directly from the frozen parquet.

## Weaknesses

1. The fresh-path theorem is elementary and conditional. It does not provide a
general sample-complexity lower bound for arbitrary replay, planning, traces,
or recurrent policies. The paper now says this explicitly, and the batch
Bellman success usefully demonstrates the boundary.

2. The main controlled experiment uses a two-action, fixed-rival, deterministic
MDP and tabular Q. Four price-book transports preserve effect signs but fail
the severe-trap confirmation gate. This limits external generality.

3. The readiness checkpoint in the trace audit is post hoc. The trace
establishes late support starvation but does not estimate a unique time when
downstream Q-values become statistically accurate.

4. The live-market bridge is only motivational. The public covariance screen
is concentrated and family-incomplete, and no paid experiment randomizes
router memory. The paper correctly avoids a live causal claim.

## Required changes

No correctness-critical changes. For a camera-ready version I recommend:

- add a prioritized replay or eligibility-trace baseline to map the gap between
one-step online Q and full batch Bellman sweeps;
- report a readiness sensitivity curve rather than only 100,000 and 200,000;
- state the theorem in the official ICML appendix style and retain the current
conditional language.

## Score

- Soundness: 4/4
- Presentation: 4/4
- Significance: 4/4
- Originality: 4/4
- Overall: 8/10, Strong Accept
- Confidence: 4/5

## Decision

**Strong accept.** The theorem alone is simple, but the complete result is not:
an economic memory boundary, a conditional finite-time barrier, a
value-preserving intervention that becomes harmful on the other side, and a
frozen replay proving that coverage is complete while update ordering fails.
This is a concrete, falsifiable contribution to reinforcement learning in
strategic environments.
