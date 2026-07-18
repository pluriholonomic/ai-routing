# The Price of Softmax: Emergent Collusion and Mechanism Design in Learned AI-Inference Routing Markets

*Submission draft for NeurIPS (main track: multi-agent learning /
economics of ML). Environment, calibration bundles, seeds, and CI-enforced
theory tests in the public `orcap` repository.*

## Abstract

Every day, a softmax decides who serves your tokens. AI inference
marketplaces route requests across competing providers of the same model
with documented selection probability ∝ 1/price² — a Gibbs measure over
providers with the routing exponent as inverse temperature. We study what
learning agents do to, and inside, this mechanism. We build a multi-agent
market environment calibrated to a five-minute-resolution capture of the
largest live marketplace: provider agents are fitted behavioral types
(validated out-of-sample under a pre-registered gate whose headline is an
*untargeted* moment — simulated demand elasticity −0.65 ± 0.35 vs −0.78
measured, with no fitted allocation parameter), and mechanisms are the
deployed rule plus counterfactuals. Findings. (1) **The exponent is a
price dial with a phase transition**: symmetric equilibrium diverges on
a(n−1) = n; the deployed a = 2 sits exactly on the two-provider critical
line. Q-learning tracks the theory's comparative statics but *regularizes
the singularity* — near the critical line the profit gradient vanishes
and ε-greedy agents undershoot the divergent equilibrium, while in the
disciplined phase they sustain supra-competitive prices (Calvano
Δ up to 0.47). (2) **The platform's measured steering penalty on price
cutters (weight ×0.17 for ~7 days) is a learned-collusion device**: we
prove it deters undercutting for any agent with effective patience below
δ† = 0.9895, and empirically it flips a learning undercutter to the price
ceiling in 4/4 calibrated markets, raising the flow-dominant
bottom-of-book quote up to +81%. Learners also never rediscover
high-frequency undercutting and form price ties at the market's focal
anchor endogenously — reproducing, unprompted, the two most striking
regularities of the real panel. (3) **Mechanisms can be repaired, and
objectives disagree**: with heterogeneous provider capital (data-center
vs GPU-spot cost types), welfare rises in the exponent while ad-valorem
platform revenue falls; a thickness-adaptive exponent, verified-quality
weighting (threshold b* = 0.63, implementable with our deployed
evaluation probes), and flat fees realign the mechanism. The environment,
theory tests, and all run manifests are released.

## 1. Introduction

Multi-agent learning research has shown that independent Q-learners can
learn supra-competitive pricing in stylized logit markets (Calvano et
al., 2020). Two things have been missing: a *deployed* mechanism whose
demand system is known exactly rather than assumed, and calibration
discipline that makes the simulated market answerable to a real one. AI
inference routing supplies both. The router's documented rule — selection
∝ p^(−2) — *is* a logit demand system; there is no demand estimation
step, no structural assumption to argue about. And because we operate a
live capture of the marketplace (prices at 5-minute grain, realized
flows, randomized routing probes), the environment can be validated the
way a forecast is validated: against moments it was not fit to.

This inverts the usual algorithmic-collusion setup in a productive way.
Instead of asking "can learners collude in a market we invented?", we
ask: *given the mechanism actually deployed, what do learning providers
converge to — and does that match the actual market?* The answer, in
brief: they converge to the actual market. High prices where theory says
the mechanism protects them; no high-frequency undercutting (the
mechanism taxes it); ties at the focal anchor price (the mechanism makes
them an attractor). The observed market's "pathologies" are the
mechanism's equilibria, learned.

**Contributions.**
1. *An environment with a validation gate* (§3): behavioral provider
   species fitted on a train window under pre-registered rules; a
   confirmatory 20-seed run must reproduce ten panel moments (weighted
   distance 0.019 ≤ 0.04) including two genuinely emergent ones before
   any counterfactual is trusted. We release the environment, bundles,
   and manifests.
2. *Theory the experiments are answerable to* (§4): the phase structure
   p* = c·a(n−1)/(a(n−1)−n) with critical line a(n−1) = n; an
   entry-proof markup floor 1/a; the measured-elasticity duopoly price
   41c; and a steering theorem with closed-form deterrence threshold —
   thirteen closed forms, all CI-tested against continuum numerics.
3. *Learning results* (§5): the exponent dial and its learning-
   regularized phase transition; non-emergence of micro-adjustment;
   endogenous focal ties; the steering flip (+81% bottom-of-book in
   calibrated markets); Calvano Δ on the deployed mechanism.
4. *Mechanism evaluation with learners* (§6): welfare/revenue/viability
   frontier over temperatures with heterogeneous cost types; the quality
   game (price-only weights → learned shading; verified-quality weights
   with b ≥ b* → learned quality); adaptive-temperature and fee-
   decoupling repairs.

## 2. Setting

n providers post prices p_i from a menu; the router allocates each
request with probability s_i ∝ q_i^b·p_i^(−a) (deployed: b = 0, a = 2;
plus an outage filter and a measured penalty ×θ ≈ 0.17 for ~7 days on
recent price cutters, identified from our randomized probe panel:
cheapest-with-recent-cut selected 3.9% vs 23.3%). Profit
π_i = s_i(p_i − c_i). Marginal costs come from a capital-structure
registry: owned-data-center types at low c, GPU-spot-dependent types at
high c including a measured walk-the-book impact (+18–52%). With logits
b·log q − a·log p, the router is softmax: **a is inverse temperature; the
market is a Gibbs ensemble over providers.**

## 3. The environment and its gate

Agents are the four pricing species classified from the live panel on a
train window (earliest 60% of dates) under split-sample-validated rules:
anchor adopters (price ≡ the model author's price; 25% of provider-model
pairs; 83–89% OOS level-persistence), static undercutters (−0.41 log,
rare hazard-driven repricing), active undercutters (myopic one-tick
best-responders; >1 change/day in the ledger), premium (+0.34 log,
rigid). Demand replays the panel's AR(1)-with-diurnal-shape process;
costs are identified bands; the author's anchor follows its observed
repricing cadence. **Gate (pre-registered, two dated addenda):** ten
moments computed by the same code on simulated and observed panels;
weighted distance ≤ 0.04; explicit split into calibration echoes and
emergent tests. Confirmatory result: distance 0.019; the emergent moments
carry the evidence — flow elasticity **−0.65 ± 0.35 vs −0.78 observed**
(no allocation parameter fitted anywhere: the documented softmax alone
reproduces the measured demand response), and adopter-atom OOS
persistence 0.83 vs 0.834. Counterfactuals are code-gated on this pass.

## 4. Theory (the backbone)

**Phase structure.** Single-crossing of h(p) = a(1−s)(p−c)/p gives unique
best responses; symmetric equilibrium p* = c·a(n−1)/(a(n−1)−n) when
a(n−1) > n, the menu ceiling otherwise. The deployed a = 2 puts n = 2
markets exactly on the critical line. Own-price share elasticity is
bounded by a (Lemma 1), so **no amount of entry pushes the Lerner index
below 1/a**: at a = 2, a 100% markup floor, forever. With the measured
end-user elasticity ε = −0.05 the duopoly equilibrium is finite: 41×
marginal cost. **Steering.** The measured cut-penalty has closed-form
optimal deviation c + √(c² + θ/W); deterrence threshold θ* ∈ [0.81, 1]
(measured θ = 0.17 is 5× inside); patience boundary δ† = 0.9895; a
perpetual cutter pays a 4.9× share tax. All closed forms are enforced in
CI against continuum numerics (13 tests).

## 5. Learning results

**5.1 The dial and the regularized transition.** All-Q markets (n = 3,
Calvano hyperparameters, expected-allocation rewards — exact under
non-binding capacity): converged mean price 1.53 (uniform), 1.30 (a=1),
0.94 (a=2; Δ = 0.08 ± 0.13, up to 0.47 with longer stability windows),
0.60 (a=4), floor at a ≥ 8. On a finer grid at the n=3 critical point
a = 1.5: learners reach 1.10, not the divergent 1.6 — near criticality
the profit gradient toward higher prices vanishes (h → 1) and ε-greedy
exploration cannot climb it; at a = 2.5 they hold 0.88 against Nash 0.5
(Δ = 0.31). Learned price is a smooth, strictly decreasing function of
temperature⁻¹: **bounded rationality regularizes the phase transition —
the dial is robust even where the equilibrium correspondence is not.**

**5.2 What learners do NOT learn.** Substituted into any species slot
(8/8 seeds unanimous): the learner never reproduces high-frequency
micro-adjustment (it parks below the anchor and freezes) — consistent
with the theory's perpetual-cutter tax and with the observed bifurcation
of repricing technologies in the panel; and with no static undercutter
present, it converges to the anchor price *exactly* — endogenous tie
formation at the focal point, with no salience assumption. The two most
striking regularities of the real market (rigid quotes, the tie atom)
are attractors of the learning dynamics under the deployed mechanism.

**5.3 Steering flips learners to the ceiling.** With the measured penalty
(θ = 0.17, M = 7) switched on: stylized world — the learning undercutter
jumps from 0.72 to the menu ceiling 1.60, market mean +18% (8/8 seeds).
Calibrated markets (17–26 providers, learner in the real
most-undercutting slot): ceiling in **4/4 markets** under the broad rule;
under the strictly-measured cheapest-only conditional the penalty binds
exactly at the bottom of the book — where it binds, the bottom-of-book
(flow-dominant) quote rises **+81%**; where the learner is not cheapest
it escapes, as theory predicts. The two variants bracket the unobserved
rule.

## 6. Mechanism evaluation with learners

**6.1 The objective frontier (two cost types).** Owned-capacity (c=0.10,
×2) vs spot-dependent (c=0.50, ×3): as a rises, equilibrium welfare rises
(flow sorts to cheap capacity: 1.73 → 1.90), ad-valorem platform revenue
*falls* (1.25 → 0.11), and spot-type profits go to zero (viability —
resilience — collapses). A platform on percentage fees is paid to keep
the market soft; welfare wants it sharp; resilience wants it interior.
[E-SIM6 traces the same frontier with Q-learners across
{uniform, a = 1, 2, 4, 6.25, 32, deployed-pair a=2+penalty}; run manifest
in repo.] **6.2 The quality game.** Add a binary quality action: shading
saves Δ = 0.08 at hidden damage d = 0.2. Under the deployed price-only
weights, shading is dominant; under verified-quality weights q^b·p^(−a),
high quality is an equilibrium iff b ≥ b* = 0.63 (closed form). Learners
confirm the bifurcation [E-SIM7: b = 0 → shading; b ≥ 1 → quality]. The
verification signal is not hypothetical: our deployed daily evaluation
probes (graded public benchmarks + deterministic-output hashes per
pinned provider) produce exactly the q this mechanism needs. **6.3
Repairs.** Thickness-adaptive temperature a*(n) = n/(ℓ*(n−1)) pins
markups at ℓ* and abolishes the critical line in one line of code; flat
per-request fees decouple platform revenue from the price level;
steering should penalize failures, not price cuts.

## 7. Related work

Calvano et al. (2020) and successors (Klein; Asker et al.; Abada–Lambin;
Hansen–Misra–Pai; Deng et al.) on learned pricing; our demand system
nests Calvano's exactly, with the differentiation parameter *published by
the platform* rather than assumed. Johnson–Rhodes–Wildenbeest: platform
steering against collusion — we measure and analyze its deployed inverse.
Demirer et al.: OpenRouter empirics. PriLLM: routing-game theory without
calibration or steering. Fish et al.: LLM pricing agents (an LLM-agent
tier exists in our environment; not part of this paper's claims).
Angeris–Chitra: intermediary-chosen demand curvature — the router
exponent is the routing-market analog of AMM curvature. Multi-agent
environment suites (PettingZoo ecosystems): none provide a calibrated,
validation-gated market environment tied to a live mechanism.

## 8. Limitations, ethics, reproducibility

*Limitations.* Tabular Q at Calvano hyperparameters (deep-RL tier is
future work; prior work suggests PPO converges nearer Nash, which would
strengthen, not weaken, the mechanism-comparison ordering); expected-
allocation training (exact only under non-binding capacity); theory is
symmetric-equilibrium (the floor is the asymmetric statement); steering θ
from one buyer tier's probes; short panel behind calibration (registered
30-day re-estimation with automatic claim-reopening). *Ethics/impact.*
This paper analyzes and criticizes a deployed mechanism using only public
data, documented rules, and our own paid probes; no provider conduct is
alleged — every elevated price is a Nash equilibrium of a published rule.
The mechanism repairs are constructive and implementable; the analysis
could in principle inform a provider's pricing, but everything it would
learn ("don't undercut") the mechanism already teaches. *Reproducibility.*
Public repo; pre-registration with dated addenda; frozen calibration
bundles with train/holdout splits; per-run manifests (commit, bundle
hash, seeds, source fingerprints); 46 tests including 13 theorem-
verification tests; validation gate frozen before the first scored run.

## Appendix

A: proofs (single-crossing; FOC algebra; corner verification; envelope
and IVT arguments for the steering threshold; patience-boundary root
certification). B: environment API and calibration bundle schema. C: full
run tables for E-SIM1–7 with per-seed outcomes.
