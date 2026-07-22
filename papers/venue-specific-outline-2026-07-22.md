# Venue architecture after the information-congestion audit

Date: 2026-07-22

This outline is the common architecture for the current ACM EC, ICML, and
NeurIPS submissions. It supersedes the 21 July price-score outline. The three
papers share evidence and claim boundaries but make different primary
contributions. Agreement across theory, public data, owned probes, and
simulation is not treated as transport unless the corresponding gate passes.

## Common market object

A user delegates a model request to a harness; the harness may delegate provider
selection to a router; inference providers sell execution for the named model.
Execution is only partly substitutable because quantization, sampling, context,
tool support, latency, reliability, privacy, and capacity affect the delivered
product. The router is therefore simultaneously a demand aggregator, a scoring
mechanism, and a reliability intermediary.

For provider technology \(\xi_i=(c_i,K_i,F_i,\rho_i,L_i,q_i)\), quote \(p_i\),
allocation \(s_i\), and router fee \(f\), keep four objectives separate:

\[
\begin{aligned}
U_i &= \mathbb E[(p_i-c_i)s_i-F_i(K_i)],\\
U_R &= \mathbb E[f(p,s)-\text{retry cost}-\text{SLA credits}],\\
U_U &= \mathbb E[v(q_i)-p_i-\lambda_L L_i-\lambda_F 1\{\text{fail}\}],\\
W   &= U_U+U_R+\sum_i U_i-\text{transfers}.
\end{aligned}
\]

A price-only rule, welfare rule, router-revenue rule, and quality-first rule
need not select the same provider or equilibrium. Reserved-capacity providers,
spot-dependent startups, anchor resellers, model authors, and custom-quality
providers face different fixed and marginal incentives.

## Shared theoretical spine

### Individual price-score elasticity

For the declared soft allocation

\[
s_i(p,\alpha)=\frac{p_i^{-a}e^{\alpha_i}}
{\sum_jp_j^{-a}e^{\alpha_j}},
\]

the non-price score is the effective-price transformation
\(p_i^{\mathrm{eff}}=p_i e^{-\alpha_i/a}\). If
\(\alpha_i=h_i(\log p_i)\), the own-price elasticity is
\(-(1-s_i)(a-h_i')\). This is a mechanism identity, not an empirical statement
that a live router clears with the public formula.

### Information-congestion threshold

Let the effective rank of provider signals be

\[
r_n=\frac{(\operatorname{tr}\Sigma_n)^2}
{\operatorname{tr}(\Sigma_n^2)}.
\]

Under the declared planner objective

\[
V_n(k)=\frac{bk}{n}-c\left(\frac{k}{n}\right)^2
\left(\frac{k}{r_n}\right)^\alpha,
\]

the continuous optimizer is

\[
k_n^\circ=\left(\frac{bnr_n^\alpha}{c(2+\alpha)}\right)^{1/(1+\alpha)}.
\]

If \(r_n\asymp n^\beta\), then
\(k_n^*=\Theta(n^{(1+\alpha\beta)/(1+\alpha)})\). The efficient adaptive
fraction vanishes for \(\beta<1\) and can remain constant for \(\beta=1\).
The congestion loss is an assumption requiring realized-outcome calibration.

### Temporal memory and finite-horizon response

If provider \(i\) needs a fresh run of \(M_i\) actions and its conditional cut
probability is at most \(q_i\), then within horizon \(T\):

\[
\mathbb E[K_T]\le\sum_i\min\{1,Tq_i^{M_i}\}.
\]

Under inverse-power routing, local total-variation reallocation is bounded by
the product of this response probability and the mechanical elasticity. In the
homogeneous case, memory

\[
M\ge\frac{\log(Tn/k_n^*)}{\log(1/q)}
\]

caps expected finite-horizon exposure at \(k_n^*\). Direct covariance-aware
caps are preferable when signal groups are observable; a memory barrier can
exclude efficient adaptation.

## Frozen empirical and simulation facts

- Public revision: `f4023bdad64b6ad468741a5a3b1f3afb7af40dd0`.
- Public panel: 3,182,780 endpoint rows, 3,274 snapshots, 321 model IDs, 72
  provider labels, 7--22 July 2026.
- Paid-model support: 71 stable markets after free-route exclusions.
- GLM-5.2: three pre-holdout active undercutters in a median 25-provider menu.
  Their inverse-price shadow share is 27.61% versus 8.99% after benchmark reset,
  an 18.62 percentage-point transfer from passive quotes.
- GLM-5.2 rank slope: 0.967, block-bootstrap interval [0.516, 1.219] at one
  hour; linear-compatible at one, six, and 24 hours.
- Non-GLM: 90% of 70 markets have zero active undercutters; log active-count
  slope 0.219 with interval [0.068, 0.378]. The only three-provider ladder fails
  temporal transport.
- Owned GLM intervention: 15 complete blocks; explicit price sorting raises
  cheapest-provider selection by 80 points, interval [60, 100]. The registered
  800-choice, 100-block, seven-day, 90%-coverage gate is not passed.
- HMP monitor: 120 covered assignments/attempts/choices with full assignment
  integrity but no qualifying multiplicity event. No collusion or buyer-harm
  claim runs.
- SM3: fitted optimizer exponents differ from theory by at most 0.006. The
  paired bandit signal-order intervention has active-share effects near zero,
  with all seed-clustered intervals containing zero.
- SM4: 108 rules and ten declared provider technologies; 104 equilibria
  converge. The price-only baseline has welfare 137.29 and router revenue 5.99.
  The welfare selection has welfare 208.44 and revenue 4.88. The revenue
  selection has revenue 7.78, welfare 83.99, and negative user utility. Selected
  rules have zero unilateral grid regret but profitable bounded pair deviations.

The requested empirical statement that GLM has \(k^*=o(n)\) and non-GLM has
\(k=\Omega(n)\) is not supported. Every paper states the positive bounded result:
GLM has a small active set with a large public-rule transfer; current rank is
linear-compatible; non-GLM active adaptation is sparse. The theorem remains
conditional.

## ACM EC submission

**Primary question:** How should a router internalize price manipulation,
correlated adaptation, hidden quality, capacity, and conflicting participant
objectives?

**Main results:** score-price equivalence; price elasticity; conditional
information-congestion threshold; hidden-capacity impossibility; objective
conflict; exact welfare/accounting identities; robust mechanism program.

**Empirical role:** bounded property tests narrow the mechanism class. GLM
shadow transfer quantifies the exposed price surface; the paid price-sort arm
shows that the action interface matters; the asymptotic contrast is rejected.

**Mechanism recommendation:** execution-contingent capacity commitments,
out-of-sample quality and reliability, SLA credits, an operator-neutral
exploration floor, covariance-aware exposure caps, and fees separated from
selected spend. Publish a Pareto menu rather than one undocumented scalar score.

**Acceptance risk:** the congestion loss is reduced form and the public panel
does not identify welfare, cost, or equilibrium. The paper must be judged as a
conditional mechanism-design contribution with unusually explicit empirical
boundaries, not as a structural estimate.

## ICML submission

**Primary question:** How do router memory and signal rank change the finite-time
learnability of profitable price paths and the number of responsive providers?

**Main results:** rational memory boundary; exponential fresh-path bound;
temporal-statistical crossover; responsive-provider and routed-share bounds;
information-congestion scaling; logarithmic memory exposure rule;
path-equivalent option with value preservation.

**Simulation role:** primitive Q-learning fails at intermediate memory despite
full state-action coverage; batch Bellman backups recover the optimum; the
commitment option repairs the gap and overcorrects beyond the rational boundary.
SM3 is a deliberately negative cross-sectional transport test.

**Empirical role:** WF20 and the owned price-sort arm are external property
tests, not calibration of memory. They reject the proposed regime split and
leave live router memory unidentified.

**Acceptance risk:** the cross-sectional planner is reduced form and broadens an
otherwise tight temporal-credit paper. The claim ledger must keep the late-credit
theorem primary and the market evidence as falsification.

## NeurIPS submission

**Primary question:** What evidence should an inference-market multi-agent
environment require before promoting a simulated mechanism claim?

**Main artifact:** deterministic request-level environment with provider-private
observations, exact settlement, capacity, fallback, stable random substreams,
pluggable router policies, heterogeneous learners, and deviation oracles.

**Evaluation:** five-level property ladder; exact marginal-preserving signal
interventions; E0 price-score surface; E1 learner-coupling falsification; E2
static-hardening versus learning-regret reversal; E3 information-congestion null
transport and multiobjective provider-technology equilibria.

**Mechanism recommendation:** use the environment to report objective-specific
frontiers, technology stress, unilateral and coalition deviation gains, and
failed transport gates. Do not fit unobserved costs or score parameters from
public quotes.

**Acceptance risk:** the benchmark suite is custom and learner coverage remains
finite. The contribution is the audited environment plus refusal standard, not
state-of-the-art policy performance.

## Shared promotion rules

1. Public inverse-price shares are shadow allocations, never market share.
2. Effective-rank slopes are finite-menu diagnostics, never asymptotic
   estimates without a longer within-market ladder.
3. Owned-choice effects describe one account and workload.
4. A positive pair deviation is susceptibility, never evidence of collusion.
5. Simulator welfare is conditional on declared costs, values, and technologies.
6. The GLM/non-GLM asymptotic contrast remains rejected until rank transport,
   owned allocation, and realized-outcome gates all pass.
