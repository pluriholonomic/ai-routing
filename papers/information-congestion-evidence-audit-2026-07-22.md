# Information Congestion and Router Objectives: Frozen Evidence Audit

Date: 2026-07-22
Public-data revision: `f4023bdad64b6ad468741a5a3b1f3afb7af40dd0`
Rule: theorem, public-quote diagnostics, owned-request estimates, and structural
simulation are separate evidence classes. A result is not promoted by agreement
across classes unless its own support gate passes.

## Executive verdict

The information-congestion theorem is a clean conditional result. If the
effective rank of the provider signal system satisfies (r_n\asymp n^\beta),
and congestion loss is

\[
  c(k/n)^2(k/r_n)^\alpha,
\]

then the interior optimum obeys

\[
  k^*\asymp (n r_n^\alpha)^{1/(1+\alpha)}
  = n^{(1+\alpha\beta)/(1+\alpha)}.
\]

Thus (k^*=o(n)) when \(\beta<1\), while (k^*=\Theta(n)) when
\(\beta=1\). The fixed-\(n\) numerical check recovers those exponents to within
0.006 on the registered grid.

The present empirical data do **not** establish the proposed GLM/non-GLM split.
GLM-5.2 is linear-rank-compatible at 1, 6, and 24 hour innovation horizons. The
broader non-GLM census is sparse rather than linear-density. The only non-GLM
market with enough active-pricer support for a rank ladder has a low-rank
in-sample factor that fails temporal transport. The correct empirical result is
therefore a finite-menu property test: public quotes identify substantial
inverse-price shadow-share transfer to a small GLM-5.2 active set, but they do
not identify the congestion regime or \(k^*\).

## Authoritative inputs

The frozen Hugging Face snapshot contains 3,182,780 endpoint observations,
3,274 snapshots, 321 model identifiers, and 72 provider labels from
2026-07-07 02:46:09 UTC through 2026-07-22 04:02:43 UTC. The paid-model census
used below excludes `:free` models. The audit finds 71 paid markets with stable
menu support and 2 markets with at least three pre-holdout active undercutters.

The public-data integrity run executes only public modules. It never queries
prospective owned-request outcomes. The first full run found three missing gate
sections; after restoring those frozen TOML sections, H91, H92, and WCV6 reran
successfully on the same immutable revision. The second full run completed all
29 registered modules with zero failures at 2026-07-22 14:30:19 UTC. Its manifest
is `/private/tmp/paper-rerun-f4023bda-v3/paper_integrity_rerun_manifest.json`;
the path is ephemeral, while the input revision and artifact hashes are frozen.

The owned-request figures below come from public aggregate monitor artifacts,
not blinded request-level logs:

- GLM routing monitor source:
  `1115055e7f5da2946c3741e2f54d56532598e61f+live-actions-overlay`.
- Market-share HMP monitor source: `5f971826101856bc869135969e85b95475bcdfeb`.
- Score-memory monitor source:
  `be897761219394bf63f042e4b634c00f0aa6b5cd+live-actions-overlay`.

## GLM-5.2: shadow allocation is large; congestion is not identified

The frozen pre-holdout classifier selects three active undercutters among a
median menu of 25: Novita, StreamLake, and Inceptron. The classification requires
at least two pre-holdout price changes and a median quote below the author/menu
benchmark. It is not a provider-intent label.

Under the public inverse-price rule, holding all other quotes fixed, the
post-split shadow-share transfer is:

| Active set | Actual shadow share | Benchmark-price counterfactual | Passive-to-active transfer |
|---:|---:|---:|---:|
| 1 of 25 | 11.36% | 2.64% | 8.72 pp |
| 2 of 25 | 22.81% | 5.82% | 16.99 pp |
| 3 of 25 | 27.61% | 8.99% | 18.62 pp |

These are deterministic public-quote allocations. They are not realized route
shares, provider revenue, or a causal effect of repricing.

The effective-rank ladder does not support a sublinear GLM claim:

| Innovation horizon | Estimated \(\beta\) | Block-bootstrap 95% interval | Conditional \(k^*\) exponent, \(\alpha=1\) |
|---:|---:|---:|---:|
| 1 hour | 0.967 | [0.516, 1.219] | 0.984 |
| 6 hours | 1.098 | [0.714, 1.317] | 1.049 |
| 24 hours | 1.121 | [0.809, 1.326] | 1.061 |

With only \(k=2,3\) rank points, these intervals are deliberately wide. The
result is linear-compatible at every horizon and cannot distinguish a limiting
exponent just below one from one.

## Non-GLM markets: sparse activity, not \(\Omega(n)\)

Across 70 non-GLM paid markets, the cross-market regression of active-pricer
count on menu size gives a log-count scaling exponent of 0.219 with a
model-bootstrap 95% interval [0.068, 0.378]. Ninety percent of markets have zero
active undercutters under the same frozen classifier, and the median active
density is zero. This is a heterogeneous finite-market census, not a within-
market asymptotic estimate, but it plainly does not support a linear-density
claim.

Only `openai/gpt-oss-120b` supports a three-provider rank ladder. Its fitted
rank exponent is -0.009, but its leading factor explains about 95% in training
and only 50% (two-provider set) or 33% (three-provider set) in the holdout. That
is evidence against a stable common factor; it is consistent with in-sample
overfit or a changing market.

## Owned routing: direct rule effects are accruing

The latest aggregate GLM-5.2 routing panel contains 36 covered default choices
over 18 blocks and 0.647 days. The fitted public-price exponent is 1.735 with a
profile interval [0.31, 3.16]. The frozen rule predicts 13.60% combined share for
the focal active pair; the pair is selected 2/36 times, or 5.56%, with Wilson
95% interval [1.54%, 18.14%]. The observed-minus-predicted difference is -8.04
percentage points. With so little support, the interval includes both a severe
shortfall and approximate calibration.

Within 15 complete paired blocks, explicit price sorting selects the cheapest
provider 80 percentage points more often than default routing; the block
bootstrap interval is [60, 100] points. This is the sharpest direct owned-route
contrast, but the preregistered gate still requires 800 choices, 100 blocks, and
7 days. The result is accruing rather than confirmatory.

The HMP monitor has 120 assignments, attempts, and covered choices with complete
menu coverage and assignment integrity. It has no qualifying public multiplicity
event, so only the exact price-path identity (MS1) is passed. The score-memory
monitor has 26 choices in 13 blocks over 0.55 days and is also accruing.

## Revenue and welfare diagnostics

H91 reproduces the pooled cross-sectional quantity-share elasticity of -1.104
(clustered SE 0.079) and finds it equivalent to the zero-cost revenue FOC within
a 0.25 margin. But the within-provider/model estimate is -0.605 (SE 0.196),
while the between estimate is -1.184; the between-minus-within gap is -0.579
with p=0.0031. Only 68 listed-price events are available, 10.5% of listed
provider/model entities vary price, and within-price variation is below the
registered gate. The pooled unit elasticity is therefore an accounting and
sorting fact, not a provider first-order condition.

H92 verifies to numerical precision that

\[
  \log s_i = \log e_i - \log p_i + \log P,
\]

where \(s_i\) is token share and \(e_i\) is public price-times-token revenue
share. The quantity-share coefficient -1.104 is exactly the revenue-share
coefficient -0.104 minus one. Revenue-share price neutrality cannot by itself
identify residual demand or profit maximization.

WCV6's bounded unilateral counterfactual places the observed proxy-weighted
provider revenue gap at 1.87--1.97% under the registered demand scenarios; the
combined elasticity/bootstrap envelope is 1.65--2.03%. This remains conditional
on treating the public elasticity as causal and on the bounded logit extension.
Router revenue is not point identified because take rates, end-user prices, and
the market demand curve are not observed.

## Structural simulations

SM3 holds total provider count fixed. For rank exponents
\(\beta\in\{0,.25,.5,.75,1\}\), its estimated \(k^*\) exponents are
0.498, 0.620, 0.745, 0.876, and 1.005, versus theoretical values 0.5, 0.625,
0.75, 0.875, and 1.0. This validates the algebra and integer optimization only.

The paired bandit signal-order intervention is a useful negative control. Low-
rank coupling can move simulated action correlation, but the mean active-share
effect is on the order of tenths of a percentage point or less. The declared
learner does not produce a material allocation-level congestion effect.

SM4 gives ten declared provider technologies bounded best responses under 108
router rules. The inverse-square price-only baseline yields welfare 137.29,
router fee revenue 5.99, and quality-adjusted successes 111.52 in simulation
units. The welfare-selected rule yields welfare 208.44 and quality-adjusted
successes 149.96 but lower router revenue 4.88 and eight viable providers. The
router-revenue rule yields revenue 7.78 but welfare 83.99 and negative user
utility. Selected rules have zero unilateral grid regret, while bounded
same-type pair deviations remain profitable. These are structural conflicts and
mechanism-susceptibility examples, not calibrated market effects or evidence of
collusion.

## Claim ledger for the three papers

| Claim | Status | Paper-safe language |
|---|---|---|
| Conditional minority threshold | Supported as theorem | State assumptions and exact exponent. |
| GLM-5.2 has \(k^*=o(n)\) | Not supported | GLM has a small active set and large public-rule shadow transfer; its rank ladder is linear-compatible. |
| Non-GLM has \(k=\Omega(n)\) | Contradicted by current census | Non-GLM active repricing is sparse; no within-market asymptotic claim. |
| Active repricing captures passive shadow share | Supported mechanically | Public inverse-price counterfactual only, not realized flow. |
| Price is the full live router score | Rejected as a maintained assumption | Owned default choices deviate from cheapest routing; reduced-form non-price score still underpowered. |
| Unit share elasticity proves revenue maximization | Rejected | Pooled coefficient is an accounting-compatible cross-section; within response differs and is power-gated. |
| Covariance-aware caps improve live welfare | Simulation only | A mechanism proposal requiring calibration and randomized evaluation. |
| Provider collusion | Not identified | Report pairwise deviation incentives or correlated responses, never conduct. |

## Manuscript consequence

The ACM EC paper should lead with the conditional information externality and
the conflict among router objectives, using GLM as a bounded public-quote
property test. The ICML paper should study finite-time learning and explicitly
report that the current fixed-\(n\) bandit environment does not transport the
theorem into allocation effects. The NeurIPS paper should present the audited
multi-agent environment and objective frontier, not claim that its agents are
estimates of live provider algorithms.

No venue draft should state the desired GLM/non-GLM asymptotic contrast as a
finding until a larger within-market rank ladder, temporal transport, and owned
allocation gate all pass.
