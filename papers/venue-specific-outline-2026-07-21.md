# Venue-specific paper architecture after the full empirical audit

Date: 2026-07-21 UTC.

This outline supersedes the common claim spine in the three short drafts. The
router's documented price heuristic is a mechanism primitive for conditional
theory and simulation; it is not assumed to be the realized allocation law.
Every venue paper uses the same evidence ledger and differs in its main theorem,
empirical object, and evaluation standard.

## Common economic object

A user delegates a model request to a harness, which may delegate provider choice
to a router. Providers offer partially substitutable execution of the same
open-weight model. Substitutability is broken by latency, uptime, quantization,
tool-call fidelity, context limits, privacy, capacity, and nondeterminism. The
router filters a private eligibility set, applies a score, selects an endpoint,
and may retry. Thus the router is simultaneously a demand aggregator, a scoring
auction, and a reliability intermediary.

For provider `i`, state `x`, quote `p_i`, delivered quality `q_i`, committed
capacity `k_i`, and allocation `s_i`, write

```text
provider:  U_i = E[(p_i - c_i(x,k_i,q_i)) s_i - F_i(k_i)]
router:    R   = E[fee(p_i,s_i) - retry_cost - SLA_payment]
user:      V   = E[v(q_i) - p_i - lambda_latency L_i - lambda_fail 1{fail}]
welfare:   W   = V + sum_i U_i + R - transfers.
```

These are separate objectives. A price-weighted allocation can reduce displayed
price while lowering quality or resilience; an ad-valorem fee can make the router
prefer a high clearing price; reserved-capacity providers and spot-dependent
providers face different fixed-cost and scarcity-risk margins.

## Evidence ledger that every paper must preserve

1. **Public quote panel.** The current high-frequency panel begins 2026-07-07.
   The audited provider-type release through 2026-07-20 has 365 training
   provider-model pairs. The four labels are provider-model-period pricing
   regimes, not provider identities or structural cost types.
2. **Regime persistence.** Overall holdout persistence is 0.892 (95% CI
   [0.855, 0.920]), but active undercutters persist in only 4/20 cases (0.20;
   95% CI [0.081, 0.416]). Premium and static-discount regimes persist; active
   undercutting is transient.
3. **No dynamic-collusion result.** Active-undercutter response is 0.376 in the
   registered window versus 0.457 in the shifted timing placebo, a -0.081
   difference with cluster interval [-0.146, 0]. The one-sided excess-response
   p-value is 1.0. Typed memory is power-gated. WF17 identifies no collusion in
   any regime.
4. **Owned routing is not inverse-square flow.** The welfare audit rejects the
   statement that the public inverse-square score is the realized allocation
   rule (z=10.06 against elasticity -2). The earlier aggregate estimate is -1.19
   (SE 0.17) and is neither request-level selection nor a price experiment.
5. **Owned selection remains narrow.** In the provider-type release, 151
   delegated selections match the frozen provider regimes: 70 anchor, 73 premium,
   four active-undercutter, and four static-discounter. These raw shares reflect
   the project's model mix and cannot be called market-wide flow or a causal
   comparison.
6. **Quality and capacity do not explain the regimes yet.** Premium providers do
   not show a significant holdout throughput or latency advantage. No
   provider-model cell has a valid capacity-utilization measure. Static
   discounters have more observations below a scenario GPU-cost bound, but
   marginal cost, rebates, subsidies, and reserved capacity are unobserved.
7. **HMP property chain is not established.** In the first pinned WF18 monitor,
   excess 24-hour residual coupling is +0.0187 with one-sided circular-shift
   p=0.110. One provider pair supplies 76.7% of paired events; leave-one-unit
   estimates cross zero. Routing SNR and elasticity-wedge legs are power-gated,
   so the Holm family is incomplete.
8. **Simulation is conditional and partly negative.** Preserving common signal
   order raises high-price play in the focal two-UCB environment, but the effect
   does not survive epsilon-greedy/static mixtures. The simulation verdict is
   `mechanism_validated=false`.
9. **Adaptive-score replay is mechanical.** On 14 observed days, a training-only
   rule selects exponent 1.25 and reduces the held-out coupling proxy by 49.3%
   with +2.08% displayed-price premium and +0.006 percentage-point reliability
   change. Provider behavior, user value, costs, and equilibrium are held fixed;
   welfare is not identified.
10. **Welfare is an identified set, not a number.** Of ten decentralization
    conditions, five are unidentified, three approximately consistent, one is
    inconsistent (retry externalities are not internalized), and one is
    power-gated. Counterfactual welfare claims require declared cost/value bands
    or randomized policy outcomes.

## Conditional theory shared across venues

### T1. Inverse-power stage game

If a router actually allocates `s_i = p_i^{-a}/sum_j p_j^{-a}` and providers have
constant marginal costs, the share elasticity is `-a(1-s_i)`. Symmetric interior
pricing obeys the familiar conditional markup equation. This is a benchmark for
a router design, not an empirical statement about hidden OpenRouter clearing.

### T2. Objective conflict

With ad-valorem fees, router revenue is proportional to selected spend; with
fixed per-request fees, it is proportional to completed volume. A higher price
elasticity can therefore raise allocative cost efficiency while lowering
ad-valorem revenue. Once failure and quality enter, neither ordering is global.
The paper reports a Pareto surface over user generalized cost, router revenue,
provider viability, concentration, and failure rather than a scalar optimum.

### T3. Capacity types

Owned-data-center providers choose a fixed capacity `K_i` and then have low
short-run marginal cost; spot-dependent providers face a state-dependent
`c_i(x)` but less fixed exposure. Model authors may supply an anchor quote;
providers copying it are non-strategic only relative to the displayed-price
process. A premium can be technology rent, reliability insurance, or market
power. A discount can be lower cost, subsidy, entry investment, or dumping.
Public prices alone do not separate these cases.

### T4. Multidimensional score and implementable repair

Use an auditable score

```text
score_i = -a(n,x) log p_i + b qhat_i - d risk_i + e log committed_capacity_i
```

with exploration and caps. Estimate `qhat` and risk out of sample, pay SLA credits
for failures, and separate the router fee from price. Choose `a` on a robust
frontier subject to provider exploitability, coalition exploitability,
concentration, and reliability constraints. The 1.25 replay is a policy candidate,
not the welfare solution.

### T5. Signal coupling and memory

For independent learners receiving correlated reward innovations, common signal
order can couple exploration and sustain high-price states in the focal UCB game.
The empirical implication is an ordered property chain: residual quote coupling,
preperiod routing-SNR gradient, elasticity-specification wedge, then forward buyer
harm. Failure of an early leg blocks the collusion interpretation. Heterogeneous
learner failure is evidence that the mechanism is conditional, not universal.

## ACM EC paper

**Title:** *Displayed Prices, Hidden Clearing: Property Tests and Mechanism Design
for AI Inference Routing*.

Main contribution: a partially identified platform-mechanism model in which
public menus, owned assignments, and aggregate router statistics license
different claims. State the objective-conflict and capacity-type propositions;
derive the robust score design; use the empirical negatives to shrink the set of
plausible mechanisms. Lead with the fact that displayed inverse-square pricing is
not realized clearing. Treat H81/H95 only within their frozen release boundaries.

Acceptance bar: exact theorem assumptions, identified-set language, complete
provenance table, no conduct claim, and a quantitative Pareto frontier with
provider-type and cost-band sensitivity.

## NeurIPS paper

**Title:** *Routing Markets as Property-Tested Multi-Agent Environments*.

Main contribution: a methodology for turning a closed production router into an
auditable multi-agent learning environment. The environment must match held-out
public and owned-routing moments before counterfactuals run. Include transparent,
UCB, epsilon-greedy, and static agents; exact marginal-preserving signal
interventions; adversarial deviations; and failure-to-transport results. The
output is a set of mechanism properties, not a claim that agents reproduce live
provider algorithms.

Acceptance bar: documented API, deterministic minimal example, multiple learner
families, uncertainty across seeds, held-out calibration, and explicit separation
of simulation causality from market causality.

## ICML paper

**Title:** *Critical Memory in Coupled Pricing Learners*.

Main contribution: a finite-time learning result. For memory parameter `m`, reward
SNR, and price-gradient gap `g`, bound the time to distinguish high and low actions
under independent UCB/bandit learners. Establish whether a critical product such
as `m * SNR / g^2` separates polynomial-time discovery from metastable high-price
play. Test the scaling over UCB, epsilon-greedy, and policy-gradient baselines and
then use WF18 only as a property screen.

Current status: not acceptance-ready. The focal UCB simulation is positive, the
heterogeneous screen fails, and no finite-time theorem has yet been proved. This
paper should remain a principled negative/conditional result unless the theorem
and algorithm sweep succeed.

## Review loop

Each paper receives its own commit, compiled PDF, claim-to-artifact audit, and a
new independent review. An “accept” review is invalid if it assumes inverse-square
realized flow, calls the observational cut association randomized, identifies
welfare without user value/cost, calls regime labels provider types, or treats a
simulation intervention as live-market causality. Stop only after two venue
reviews recommend acceptance under these stricter conditions.
