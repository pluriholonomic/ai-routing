# NeurIPS adversarial review

## Summary

The paper introduces a request-level multi-agent environment for strategic AI
inference routing and, more importantly, a property ladder for deciding which
simulator conclusions transport to a live market. Provider agents choose quote,
admitted capacity, and availability. Router plugins determine attempted order;
the kernel settles capacity, reliability, fallback, payments, costs, user
utility, and welfare with stable common-random-number substreams. The parallel
API exposes public quotes and own settlement while hiding rival technology.

Two studies demonstrate the methodology. First, a marginal-preserving signal
order intervention raises buyer price by 0.118 in a focal UCB/UCB game but has
effect -0.00047 across heterogeneous learners. Second, a hardened adaptive
router sharply reduces one-shot quote, fade, sybil, unilateral, and
two-provider attacks, yet has 9.68 times the normalized post-UCB exploitability
of inverse-square routing. Public data provide only nominal, concentrated
signal coupling, so neither simulator result is promoted to provider conduct.

## Strengths

1. The scientific contribution is the refusal mechanism. Many multi-agent
market papers verify accounting and then treat calibrated agents as behavioral
truth. Here claims must pass information fidelity, held-out properties,
adversarial strategy diversity, and prospective transport. The paper shows
that these gates change conclusions, not just presentation.

2. The environment models the right operational details. Attempt costs accrue
on failed inference, installed-capacity cost survives withdrawal, capacity
clips attempts, and fallback changes both latency and resource cost. The exact
identity welfare equals user utility plus provider profit is enforced at the
request level without assuming nonbinding capacity.

3. Intervention fidelity is excellent. The signal treatment preserves every
provider's finite-sample signal multiset exactly and changes only common and
temporal ordering. Paired seeds preserve structural randomness. This makes the
focal causal statement clean inside the simulator while leaving transport
appropriately separate.

4. Negative results are informative and central. Heterogeneous learners erase
the HMP-style price effect. Static hardening succeeds while adaptive learning
fails its frozen normalized gate. The paper explains the denominator issue and
reports absolute gains rather than tuning away the failure.

5. The artifact is now usable without repository archaeology. The parallel API
has a tested four-epoch example, an observation-contract guide, deterministic
JSON replay, custom-router instructions, an environment card, and focused
tests. The broader market-environment suite covers capacity, fallback,
information boundaries, adversarial deviations, and stable random substreams.

6. The work is ethically careful. Paid probes are assignment-first and
budget-capped; public releases exclude request-level rows; provider regimes are
not allegations; and the paper does not claim collusion, dumping, or literal
front-running.

## Weaknesses

1. The environment is domain-specific rather than a broad MARL benchmark.
That is a deliberate strength for settlement fidelity, but it means the paper
needs external adapters before standard PPO or population-based libraries can
be run without glue code.

2. The strategic policy set is still finite: UCB, epsilon-greedy, tabular Q,
static species, and scripted deviations. It does not establish robustness to
deep recurrent policies or unrestricted history-dependent coalitions.

3. The hardened-router result is mixed and the normalized metric is unstable
near zero profit. The paper reports this correctly, but readers should not
interpret the candidate mechanism as deployable.

4. Live transport is intentionally incomplete. Public prices and owned probes
do not identify market-wide demand, cost, value, or capacity. The contribution
is a standard for evaluating such claims, not a validated live welfare model.

## Required changes

No changes are required for acceptance. Useful additions would be a thin
PettingZoo adapter, one standard policy-gradient baseline, and performance
benchmarks at larger provider counts. These are extension requests rather than
repairs to the current claims.

## Score

- Quality: 4/4
- Clarity: 4/4
- Significance: 4/4
- Originality: 4/4
- Overall: 8/10, Strong Accept
- Confidence: 4/5

## Decision

**Strong accept.** The paper offers both a substantive inference-market
environment and a general methodological contribution: empirical transport
gates that can falsify attractive simulator narratives. The two negative
studies demonstrate that the ladder is load-bearing, and the executable
artifact supports the claims actually made.
