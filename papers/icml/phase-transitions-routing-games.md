# Phase Transitions in Price-Weighted Routing Games: Learning Dynamics at the Knife Edge

*Submission draft for ICML. Environment, calibration bundles, seeds, and
CI-enforced theory tests in the public `orcap` repository.*

## Abstract

We study independent Q-learning in a one-parameter family of pricing
games induced by softmax request routing — the mechanism deployed, with a
published parameter, by AI inference marketplaces (selection probability
∝ p^(−a); deployed a = 2). The family has an exact phase structure:
symmetric equilibrium price p* = c·a(n−1)/(a(n−1)−n) diverges on the
critical line a(n−1) = n, an entry-proof markup floor 1/a holds
everywhere, and the deployed parameter places two-provider markets
exactly at criticality. Our object of study is the *interaction of
learning dynamics with this phase structure*. Empirically (all runs
seeded, manifested, and gated behind a pre-registered validation of the
environment against a live market panel — including an untargeted moment,
demand elasticity −0.65 ± 0.35 simulated vs −0.78 measured): (1) learned
prices are a smooth, strictly decreasing function of a that tracks the
equilibrium correspondence away from criticality but **regularizes the
singularity** — near the critical line the profit gradient toward higher
prices vanishes at rate governed by h(p) → 1 and ε-greedy Q cannot climb
it, so learners undershoot divergent equilibria and overshoot interior
Nash (Δ = 0.31 at a = 2.5); (2) a measured history-dependent steering
penalty (weight ×0.17 on recent price cutters, ~7-epoch memory)
restructures the learning problem — we prove it deters cutting for any
discount below δ† = 0.9895 and observe it flip learners from
bottom-of-book pricing to the menu ceiling in 4/4 calibrated markets
(+81% on the flow-dominant quote where the measured conditional binds);
(3) learners systematically fail to discover the high-frequency
micro-adjustment strategy present in the real market (a 4.9× share tax
under the deployed steering makes it dominated), and converge to exact
price ties at the market's focal anchor without any salience assumption —
the real market's two most distinctive regularities are attractors of the
learning dynamics. We further evaluate candidate mechanisms with learning
agents: a thickness-adaptive exponent removing criticality, and a
verified-quality weighting whose closed-form threshold b* = 0.63
separates learned quality-shading from learned quality provision. The
results position deployed routing rules as a natural laboratory where
learning theory, mechanism design, and live-market validation meet.

## 1. Introduction

Learning in games meets its cleanest applied test where a mechanism is
(i) deployed at scale, (ii) documented exactly, and (iii) instrumented.
AI inference routing is such a mechanism: a softmax over provider prices
with a published exponent decides, request by request, who serves each
call to a shared open-weight model. The exponent is an inverse
temperature; the induced game is logit Bertrand — the very testbed of the
algorithmic-collusion literature (Calvano et al., 2020) — except that
here the demand system is not a modeling choice: it is the product
documentation.¹

This paper treats the routing exponent as the control parameter of a
game family and asks how independent learners behave across it,
especially at its singular points. The family has a critical line
a(n−1) = n where the symmetric equilibrium correspondence diverges to
the menu ceiling; the deployed parameter sits on it for duopolies. Away
from statistical mechanics analogies, this is a concrete learning
question: what does ε-greedy tabular Q do when the stage game's best-
response dynamics point toward an equilibrium at infinity along a
vanishing gradient?

**Contributions.** (1) A complete characterization of the game family's
phase structure with CI-verified closed forms, including an entry-proof
elasticity bound (share elasticity ≤ a) and a measured-elasticity finite
version of the critical divergence (duopoly p* = 41c at the marketplace's
measured outside elasticity). (2) A calibrated environment with a
pre-registered validation gate; behavioral species fitted from a live
panel; counterfactuals code-locked behind the gate. (3) The learning
phenomenology of the phase structure: smooth regularization of the
singularity; overshoot (supra-Nash, Δ up to 0.47) in the disciplined
phase; undershoot at criticality; mechanistic explanation via the
vanishing gradient of h. (4) Steering as reward shaping: a measured
penalty parameter, a deterrence theorem with a patience boundary, and
its empirical effect on learned play in calibrated markets. (5)
Mechanism evaluation with learners: adaptive temperature; quality
weighting with a closed-form learnability threshold.

¹ The router's softmax makes "inverse temperature" literal, not
metaphorical: allocation is a Gibbs measure with energy a·log p. The
phase-transition language below is the exact behavior of the equilibrium
correspondence, not an analogy.

## 2. The game family

n providers; prices p_i ∈ (0, p̄]; router selects i with probability
s_i = p_i^(−a)/Σ p_j^(−a); profit π_i = s_i(p_i − c_i). Lemma 1:
own-price share elasticity −a(1−s_i) ∈ (−a, 0). Lemma 2 (single
crossing): best responses are unique — root of h(p) = a(1−s)(p−c)/p = 1
or the ceiling. Theorem 1: interior symmetric equilibrium
p* = c·a(n−1)/(a(n−1)−n) iff a(n−1) > n, ceiling otherwise; Lerner floor
1/a in any interior equilibrium (any n, any outside option); with
measured outside elasticity ε: p/(p−c) = a(n−1)/n + |ε|/n (duopoly at
deployed parameters: 41c). Theorem 2 (steering): penalty ×θ for M epochs
after a cut ⇒ optimal deviation c + √(c²+θ/W); deterrence iff θ ≤ θ*
(∈ [0.81, 1] at calibrated configurations, measured θ = 0.17); patience
boundary δ† = 0.9895; perpetual-cutter share tax θ/(θ+n−1) vs 1/n.
Proofs in Appendix A; 13 closed forms CI-tested.

## 3. Environment and validation

(As in the companion papers; summarized.) Provider agents are behavioral
species fitted on the live panel's train window (adopters / static
undercutters / active undercutters / premium; split-sample validated);
demand replays the panel's AR(1)-diurnal process; costs are identified
bands from a capital-structure registry and the GPU spot book. The
pre-registered gate requires ten moments to match (distance ≤ 0.04,
achieved 0.019, 20 seeds, deterministic replication), with the evidential
weight on two emergent moments: untargeted flow elasticity (−0.65 ± 0.35
vs −0.78) and out-of-sample adopter-atom persistence (0.83 vs 0.834).
Learning experiments use expected-allocation rewards (exact under
non-binding capacity; the request-level kernel supplies sampling noise in
the validation runs) and Calvano hyperparameters (α = 0.15, γ = 0.95,
exponentially decaying ε), with convergence defined by greedy-policy
stability.

## 4. Learning across the phase diagram

**4.1 The dial.** Converged mean prices (n = 3, 8 seeds/point):
uniform 1.53; a = 1: 1.30; a = 2: 0.94; a = 4: 0.60; a ≥ 8: grid floor.
Learned price is smooth and strictly decreasing in a — the mechanism's
comparative statics survive bounded rationality everywhere.

**4.2 At criticality.** For n = 3 the critical point is a = 1.5. There,
theory says the symmetric equilibrium is the ceiling (1.6); learners
reach 1.098 ± small. Mechanism: near criticality dπ/dp ∝ 1 − h(p) with
h → 1, so the drift toward the ceiling is arbitrarily weak relative to
exploration noise; tabular Q with decaying ε performs a random walk on a
nearly flat profit landscape and settles far below the divergent
equilibrium. Conversely at a = 2.5 (interior Nash 0.5) learners hold
0.877 — supra-Nash by Δ = 0.31: in the disciplined phase the landscape
has curvature and the classic Calvano reward-punishment channel operates.
**Learning friction regularizes the equilibrium correspondence:
undershoot where it diverges, overshoot where it is interior.** We view
this as the paper's most transferable observation: mechanism analysis
that stops at the equilibrium correspondence mispredicts learned play in
*both directions*, in a sign pattern that a vanishing-gradient argument
predicts.

**4.3 What is not learned.** Substituting a learner into each behavioral
slot (8/8 seeds unanimous): micro-adjustment (>1 reprice/day) never
emerges — under the deployed steering it carries a 4.9× share tax and is
dominated (Theorem 2(iv)); the learner instead parks at a rigid
below-anchor price. With no static undercutter present, the learner
converges to the anchor price *exactly*: endogenous tie formation. The
real market's tie atom (45% of same-model pairs, 3.4× its mechanical
null) and its bifurcation into rigid-vs-micro-adjusting technologies are
thus both attractors of learning under the deployed mechanism — an
out-of-sample style of validation we find more convincing than moment
matching: the environment reproduces *qualitative regularities it was
never told about.*

**4.4 Steering as reward shaping.** The measured penalty is a
history-dependent, asymmetric transformation of the reward: cuts move the
agent into a taxed state for M epochs. Effect on learned play: stylized
world — learner jumps 0.72 → ceiling (8/8 seeds), market +18%.
Calibrated markets — ceiling 4/4 under the broad rule; under the
strictly-measured cheapest-only conditional, the effect concentrates at
the book's bottom: +81% on the flow-dominant quote where the learner is
cheapest, escape otherwise (both variants reported; they bracket the
unobserved rule). The penalty converts "undercut" from the greedy action
into a trap state; a γ = 0.95 learner (δ^M ≈ 0.70 ≪ δ† = 0.9895) can
never profit from entering it.

## 5. Mechanism evaluation with learning agents

**5.1 Objective frontier under cost heterogeneity.** Two calibrated cost
types (owned-capacity 0.10 ×2; spot-dependent 0.50 ×3). Theory FOCs and
learner runs [E-MECH1] agree on the ordering: welfare ↑ in a (better
cost-sorting), ad-valorem platform revenue ↓ in a, spot-type viability
↓ 0 (the resilience cost of sharp routing). The deployed (a = 2,
ad-valorem fee) pair is revenue-serving, not welfare-serving; a
thickness-adaptive a*(n) = n/(ℓ*(n−1)) pins markups and removes the
critical line. **5.2 Quality learnability threshold.** Binary quality
action; shading saves Δ = 0.08 at hidden damage d = 0.2. Weight
q^b·p^(−a): all-high-quality is an equilibrium iff b ≥ b* = 0.63 (closed
form). Learners bifurcate exactly [E-MECH2]: b = 0 (deployed) → learned
shading; b ≥ 1 → learned quality. The q signal exists operationally (our
deployed daily evaluation probes: graded benchmarks and greedy-output
hashes per provider).

## 6. Related work

Algorithmic pricing and collusion: Calvano et al.; Klein (sequential
moves); Asker et al. (learning protocols); Abada–Lambin (exploration-
driven pseudo-collusion); Hansen–Misra–Pai (misspecified bandits); Deng–
Schiffer–Bichler (deep RL nearer Nash). Our departure: the demand system
is deployed and documented, the environment is validation-gated against a
live market, and the phase-structure/learning interaction is the object.
Steering: Johnson–Rhodes–Wildenbeest (anti-collusive steering design) —
we analyze the measured inverse. Mechanism/learning interfaces: reward
shaping, potential-based equivalences; the cut-penalty is a naturally
occurring non-potential shaping with measured parameters. Marketplace
empirics: Demirer et al. (OpenRouter). Softmax/temperature in games:
logit QRE (McKelvey–Palfrey) — our learners' smooth dial echoes QRE
comparative statics, but the regularization sign pattern at criticality
is, to our knowledge, undocumented.

## 7. Limitations

Tabular Q with one hyperparameter suite (Calvano's), chosen for
comparability; a systematic hyperparameter/algorithm sweep (optimism,
UCB, PPO) is the natural next step and prior evidence suggests deep RL
lands nearer Nash — which would sharpen, not reverse, §4.2's contrast.
Expected-allocation rewards; symmetric-equilibrium theory; steering θ
measured for one buyer tier; short calibration panel with a registered
30-day re-estimation that automatically reopens claims on sign flips.

## Reproducibility statement

Public repository with: frozen calibration bundles (train/holdout
recorded), pre-registration documents with dated addenda, per-run
manifests (commit, bundle hash, seed tree, source fingerprints),
46 tests including 13 enforcing every closed form in §2 against continuum
numerics, and the live-capture workflows that generated the panel.

## Appendix A: proofs.  Appendix B: run tables (E-SIM1–4b, E-MECH1–2).
