# The Router Is the Demand Curve: Price-Weighted Routing and the Limits of Competition in AI Inference Marketplaces

*Draft 2026-07-18. Companion to "Administered Menus and Hidden Clearing"
(empirical); this paper supplies the mechanism theory and the calibrated
multi-agent environment. Code: `src/orcap/market_env/`; every number
reproduces from committed modules with recorded seeds and manifests.*

## Abstract

AI inference marketplaces route buyer traffic across competing providers of
the same model with a documented rule: selection probability proportional to
1/price². We show this rule *is* the market's demand system, and
characterize competition under the induced logit-form game. Three results.
**(1) A markup floor.** For routing weights ∝ p^(−a), every interior
equilibrium satisfies Lerner index (p−c)/p ≥ 1/a — regardless of the number
of providers or any outside option. At the documented a = 2, equilibrium
markups never fall below 100%; free entry cannot compete them away. For n
providers, symmetric equilibrium is p* = c·a(n−1)/(a(n−1)−n) when
a(n−1) > n, and the *menu ceiling* otherwise: at a = 2 with two providers —
the modal market structure in our panel — the unique symmetric equilibrium
is the highest feasible price. Replacing literal captivity with the
*measured* end-user elasticity (−0.05) gives the finite version:
equilibrium duopoly price equals **41× marginal cost**. **(2) Steering as a price elevator.** The
router's empirically measured penalty on recent price-cutters (selection
weight ×θ ≈ 0.17 for ~7 days, from our randomized probe panel) has a
closed-form deterrence threshold θ*: for all calibrated configurations
θ = 0.17 ≪ θ*, so undercutting is strictly unprofitable for any agent with
effective patience δ^M below ≈ 0.93, and a *perpetual* micro-adjuster pays a
~5× share tax. In simulation the penalty flips a learning undercutter to
the price ceiling and raises market prices 18%. **(3) A validated
environment.** We fit four behavioral pricing species (anchor adopters,
static and active undercutters, premium providers) to a live capture of the
OpenRouter marketplace under a pre-registered split-sample protocol; the
simulated market reproduces ten observed moments (distance 0.019 vs 0.04
gate) and — with no parameter targeting allocation — endogenously generates
the observed provider-level flow elasticity (−0.65 ± 0.35 simulated vs
−0.78 observed). Q-learning agents dropped into the environment converge to
supra-competitive prices (Calvano Δ up to 0.47) whose level is dial-set by
the routing exponent, and never rediscover high-frequency undercutting —
consistent with the observed bifurcation of repricing technologies.

## 1. Introduction

Routing marketplaces for AI inference (OpenRouter and peers) sell a
homogeneous good — tokens from a specific model — served by multiple
competing providers. Buyers do not choose providers; a router does.
OpenRouter documents its default: filter providers with recent outages,
then select with probability proportional to the inverse square of price.
This one sentence pins down the residual demand curve every provider faces.
The competitive question is therefore not "how do buyers search" but "what
game does the routing rule induce," and it can be answered exactly.

Our empirical companion paper documents, from a 5-minute-resolution capture
of the marketplace: same-model price dispersion sustained at 1.3–10×;
menu-cost repricing with a large atom of providers pricing *exactly* at the
model author's price; a 20× wedge between routing-level and end-user demand
elasticity; and a router that *penalizes* recent price-cutters (a
cheapest-quoting provider with a cut in the last week is selected 3.9% of
the time vs 23.3% without). This paper asks whether those facts are what
competition under price-weighted routing *should* produce — and whether the
router's design choices could themselves be the source of the observed
price elevation.

**Contributions.**

1. *Theory* (§3). For the weight class w(p) = p^(−a) we give a complete
   characterization of symmetric pricing equilibrium with captive demand:
   an interior solution p* = c·a(n−1)/(a(n−1)−n) iff a(n−1) > n, the menu
   ceiling otherwise, and a universal Lerner floor 1/a that survives free
   entry and any outside option. The documented exponent a=2 sits exactly
   at the two-provider knife edge. We then model the observed cut-penalty
   as a transient multiplicative weight tax and derive its closed-form
   deviation target, deterrence threshold θ*, patience boundary, and the
   perpetual-cutter share tax.
2. *A calibrated, validated multi-agent environment* (§4–5). Provider
   behavior is not assumed: four behavioral species are classified from
   panel data on a train window under pre-registered rules, and the
   assembled market must reproduce held-out moments before any
   counterfactual is run. The validation gate includes an untargeted
   moment: the simulated flow elasticity emerges from the router alone.
3. *Learning counterfactuals* (§6). Tabular Q-learners (Calvano et al.'s
   design, which our demand system nests exactly) show: collusion indices
   up to Δ = 0.47 under the documented router; a monotone price-level dial
   in the routing exponent; the cut-penalty raising prices 18%; and the
   non-emergence of high-frequency undercutting as an optimal reply.

**Why this matters beyond one marketplace.** Price-weighted probabilistic
allocation is the natural "fair" design for any machine-mediated
marketplace (ad exchanges, cloud brokers, agentic procurement). Our results
say such rules carry an intrinsic markup floor set by the weighting
exponent, that softening allocation to protect quality also protects
margins, and that anti-bait-and-switch steering is mathematically a
collusion device. These are design levers, not conduct — the "who is to
blame" question inverts.

## 2. Model

A market is one (model, workload). n providers post prices p_i ∈ (0, p̄]
from a menu (the ceiling p̄ is the highest feasible/observed menu price;
discreteness is irrelevant to the theory and used only in learning
experiments). Marginal cost c_i per served request; capacity non-binding
for the theory (the empirical companion treats rationing). Per epoch a unit
mass D of captive requests arrives (end-user elasticity measured at −0.05;
we treat D fixed and discuss the outside option below). The router selects
provider i first with probability

    s_i(p) = w(p_i) / Σ_j w(p_j),    w(p) = p^(−a),   a > 0.

Payoffs π_i = D·s_i·(p_i − c_i). This is a logit demand system: with
logits ℓ_i = −a·log p_i, s = softmax(ℓ); the routing exponent is inverse
temperature. OpenRouter documents a = 2.

## 3. Theory

### 3.1 Equilibrium characterization

**Lemma 1 (share elasticity).** ∂s_i/∂p_i = −(a/p_i)·s_i(1−s_i), so the
own-price elasticity of share is −a(1−s_i).

**Lemma 2 (single crossing).** π_i is strictly quasiconcave in p_i on
(c_i, p̄]: sign dπ_i/dp_i = sign[1 − h(p_i)] with
h(p) = a(1−s_i(p))(p−c_i)/p, and h is a product of positive strictly
increasing functions with h(c_i) = 0. Hence the best response is unique:
the solution of h = 1 if h(p̄) > 1, else the ceiling p̄.

**Theorem 1 (symmetric equilibrium; knife edge; markup floor).**
With symmetric costs c:
(i) If a(n−1) > n and the menu ceiling satisfies p̄ > p*, the unique
symmetric equilibrium is interior:

    p* = c · a(n−1) / (a(n−1) − n).

(If p̄ ≤ p* the ceiling binds and the equilibrium is p̄.)
(ii) If a(n−1) ≤ n, every provider's best response exceeds any rival
price: the unique symmetric equilibrium is p_i = p̄ (the menu ceiling).
At a = 2 this is precisely n ≤ 2.
(iii) *Markup floor* (a > 1; for a ≤ 1 the ceiling always obtains). In ANY
interior equilibrium — symmetric or not, any n, and with any outside
option (weights w_0 ≥ 0 added to the denominator) — the FOC reads
(p_i−c_i)/p_i = 1/(a(1−s_i)) > 1/a, hence

    p_i > c_i · a/(a−1)      for every provider, always.

As n → ∞ or as the outside option grows large, p* ↓ c·a/(a−1): the floor
is tight. At a = 2 the competitive limit of this marketplace is a 100%
markup.

*Attribution.* The static structure is classical: constant-elasticity
logit pricing with markups 1/(α(1−s)) goes back to Anderson–de Palma–
Thisse (1992); Theorem 1's content is the exact mapping of a DOCUMENTED
platform routing rule onto that system — so the "differentiation"
parameter is not a taste primitive to be estimated but a published design
choice — plus the resulting placement: a = 2 sits exactly on the duopoly
knife edge, and the floor is a design constraint (no entry policy can
undo it), not an estimate. The mechanism-design reading and Theorem 2 are,
to our knowledge, new. Asymmetric-cost equilibria are not characterized
here; all equilibrium statements are symmetric (the floor in (iii) is the
exception — it binds provider-by-provider at any interior profile).

**Corollary 1 (measured outside option; the empirical duopoly markup).**
The ceiling case is the ε → 0 limit of a finite answer. Let aggregate
demand be D = D₀·P^ε with inclusive-value index P = (Σ_j p_j^(−a))^(−1/a)
(so ∂log P/∂log p_i = s_i) and ε < 0 the end-user price elasticity. The
symmetric FOC becomes

    p/(p−c) = a(n−1)/n + |ε|/n  ≡  R,    p* = c·R/(R−1)   (R > 1).

Every routing marketplace with a > 1 and any ε < 0 has a finite symmetric
equilibrium; captivity (ε = 0) is what produces the ceiling. At the
MEASURED end-user elasticity ε = −0.05 and the documented a = 2, duopoly
gives R = 1.025 and

    p* = 41·c :

the equilibrium duopoly price is forty-one times marginal cost. (Verified
against the full profit function to 4 decimals at (n, a, ε) ∈
{(2,2,−.05), (3,2,−.05), (2,2,−.2), (5,2,−.05), (2,2,−1)}.) The
elasticity wedge measured in the companion paper is thus a structural
parameter here: the router's near-captive demand (|ε| ≪ 1) is precisely
why realistic menus bind before equilibrium does. The same FOC also
rationalizes the measured provider-level flow elasticity: theory predicts
own-price share elasticity −a(1−s) ≈ −1 at the observed share levels;
we measure −0.78 (panel) and −0.65 (simulation).

*Proof.* (i)–(ii): impose symmetry s = 1/n in Lemma 2's FOC h(p)=1 and
solve; the knife edge is h(p) < 1 for all p when a(1−1/n) ≤ 1. Corner
verification: at p_i = p̄ ∀i, Lemma 2 gives dπ/dp > 0, and global downward
deviations are ruled out by quasiconcavity. (iii): 1−s_i < 1 in the FOC;
the limit follows by s_i → 0. ∎

Numerical verification: the fixed point of the continuum best response
matches the formula to 4 decimals across (n,a) ∈ {(3,2),(4,2),(10,2),
(3,4),(2,4),(5,3)}; the ceiling obtains at (2,2),(3,1.5),(2,1); p* at
n=200 and under w_0 = 10⁶ matches the floor to 3 decimals.

**Reading.** Price-weighted routing is *soft* allocation: it deliberately
sends flow to non-cheapest providers (uptime/diversity insurance). Softness
is product differentiation: the router's smoothing manufactures the market
power that Bertrand competition in a homogeneous good would destroy. The
exponent is a policy dial with a hard floor — no amount of entry pushes
markups below 1/(a−1)·c. And the documented a=2 leaves *duopoly markets at
the menu ceiling*: the modal market in our panel has 1–3 active providers.

### 3.2 The cut-penalty (steering) mechanism

The probe panel measures: a cheapest provider with a price cut in the
trailing window is selected ~θ = 0.17 as often as predicted by the pricing
rule alone, for M ≈ 7 days. Model: a provider whose current price is below
its price at any of the last M epochs has weight θ·w(p_i).

**Theorem 2 (deterrence).** Symmetric providers at price q (interior p* or
p̄), a = 2, rival weight mass W = (n−1)q^(−2).
(i) *Optimal deviation.* A flagged deviant's best cut is

    p_dev = c + √(c² + θ/W),

(unique, by the same single-crossing argument applied to the flagged
share).
(ii) *Myopic deterrence.* The flagged deviation value v(θ) =
s_θ(p_dev)(p_dev−c) is continuous and strictly increasing with v(0)=0;
undercutting is unprofitable for a one-epoch optimizer iff θ ≤ θ*, the
unique solution of v(θ*) = (q−c)/n (θ* = 1 if v(1) is below). Calibrated
configurations give θ* ∈ [0.81, 1.0]; the measured θ = 0.17 deters with
wide margin.
(iii) *Patience boundary.* A one-time cut to p held forever, flagged for M
epochs, has present value gain
(1−δ^M)/(1−δ)·[v_θ(p) − v̄] + δ^M/(1−δ)·[v_1(p) − v̄], v̄ = (q−c)/n.
Deterrence for all p holds iff δ ≤ δ†, the root of
max_p PV(p; δ) = 0; at calibrated parameters (n=5, q=1, c=0.2, θ=0.17,
M=7) **δ† = 0.9895** (equivalently δ^M ≤ 0.929): the penalty deters
myopic and moderately patient agents (a γ=0.95 Q-learner is inside) but
not arbitrarily patient deviants.
(iv) *Perpetual-cutter tax.* An agent repricing downward at least once per
M epochs is permanently flagged: at symmetric prices its share is
θ/(θ+n−1) vs 1/n unflagged — at θ=0.17, n=5, a 4.9× share tax. The
high-frequency micro-adjustment technology is strictly dominated under the
documented steering rule.

*Proof.* (i) FOC of θp^(−2)(p−c)/(θp^(−2)+W) reduces to
Wp² − 2Wcp − θ = 0. (ii) monotone comparative statics in θ; continuity;
intermediate value. (iii) direct computation. (iv) substitute equal prices
with one weight scaled by θ. ∎ (Numerics: p_dev matches to 5 decimals;
threshold values in `output/market_env/`.)

*Remark (measured vs modeled conditioning).* The probe panel identifies θ
for the CHEAPEST quote with a recent cut; the model above penalizes any
recent cutter. At symmetric profiles the two coincide — any strict cut
makes the deviant cheapest — so Theorem 2 is invariant to the choice. They
differ only for non-cheapest cuts in asymmetric books (a premium provider
cutting into mid-book escapes the cheapest-only rule); §6 therefore runs
the calibrated steering experiment under BOTH variants, which bracket the
unobserved treatment of non-cheapest cutters. M and the flag-refresh
semantics are modeling choices fitted to the 7-day empirical window.

**Reading.** The cut-penalty is presumably quality protection — punish
bait-and-switch repricing. Mathematically it is an *asymmetric menu cost
imposed by the platform on price cuts only*, and Theorem 2 says it
converts the routing game into one where holding high prices is robustly
optimal for any realistically patient agent. It also predicts the observed
JRW-futility dynamic: undercutters should learn to stop cutting (the
registered cut-frequency-decay watch in the empirical companion). This is
the strongest form of the empirical paper's "JRW-inverse" claim: measured
steering parameters sit deep inside the deterrence region.

### 3.3 What the theory does NOT claim

No provider communication, no agreement, no intent: every elevated-price
outcome above is a *static Nash equilibrium of the game the router
defines* (or its learning analog). The policy conclusion is about mechanism
design — exponent choice, steering design, eligibility floors — not about
conduct. Costs enter only as bands; every quantitative claim is reported
across the band.

## 4. The calibrated environment

Deterministic request-level kernel (providers post quotes; router samples a
fallback order; queueing/rationing settle; exact transfer accounting) with
strategy, router, demand, and cost modules. Providers are *behavioral
species* classified from the live panel on a train window (earliest 60% of
dates) under the pre-registered wf13 rules: **adopters** (quote exactly the
model author's price ≥80% of days; 25% of provider-model pairs), **static
undercutters** (median −0.41 log below anchor, ~0 repricing), **active
undercutters** (micro-adjusters, ledger cadence >1/day), **premium**
(+0.34 log, rigid). Fitted parameters: per-species margins and hazards,
species-specific congestion-rationing slopes, AR(1) demand with intraday
shape, cost bands (owned-capacity tiers vs GPU-spot-dependent with a
walk-the-book impact curve), and the author's anchor-walk cadence.
Everything is frozen in an immutable bundle with train/holdout split
recorded; the flow-allocation side has NO fitted parameter.

## 5. Validation (E-SIM1, pre-registered)

Gate (registered before any scored run, with two dated addenda for a
target-universe definition fix and a seeding-reproducibility fix): weighted
moment distance ≤ 0.04 on ten moments computed by the same code on
simulated and observed panels; no weight-2 moment off >35%; and an
untargeted-moment gate — simulated flow elasticity must match the observed
sign and order of magnitude.

Confirmatory result (20 seeds × 56 epochs, deterministic replication
`d18b9b4a92`): distance **0.019**. The moments divide into two classes,
and we insist on the distinction:

*Echo moments* (near-mechanical consequences of fitted inputs; passing
them is calibration hygiene, not evidence): premium ladders (margins
fitted), cadences (hazards fitted), adopter in-sample atom.

*Emergent moments* (no fitted parameter targets them; these carry the
evidential weight):
- **Flow elasticity −0.65 ± 0.35 vs observed −0.78** — allocation has NO
  fitted parameter; the documented inverse-square rule alone reproduces
  the measured demand response (and Corollary 1 says why: −a(1−s̄)).
- **Adopter-atom OOS persistence 0.83 vs 0.834** — the target is the
  held-out persistence of train-classified adopters, which the simulated
  interaction (anchor walk + species responses) must regenerate.
- Dispersion (1.2 vs 1.34) — partially emergent: level depends on the
  demand/hazard/response interplay, not any single fitted input.

## 6. Learning counterfactuals (gated on §5)

*(Confirmatory tier: 8 seeds per cell, `output/market_env/esim{2,3,4}`;
screening runs replicated exactly.)*

**E-SIM3 — the exponent is a price dial.** All-Q worlds (n=3, Calvano
hyperparameters): mean converged price 1.53 (a=0, uniform routing), 1.30
(a=1; unbounded-Nash regime per Theorem 1(ii); Δ undefined there since
π_N = π_M), 0.94 (a=2; Δ = 0.08 ± 0.13, single-seed runs with longer
stability windows reach Δ = 0.47), 0.60 (a=4; Δ = 0.11 ± 0.07),
competitive floor at a ≥ 8 (Nash below the grid; Δ = 0). Learners track
the theory's comparative statics, sitting on or above Nash at every a.

**E-SIM4 — steering elevates prices.** Identical worlds ± the measured
cut-penalty (θ=0.17, M=7), 8/8 seeds each arm: without the penalty the
learner in the undercutter slot converges to 0.72 (one tick below the
interior region); with it, to the *menu ceiling* (1.60), and market mean
price rises **0.96 → 1.14 (+18%)**. Theorem 2 predicts exactly this: at
θ far below θ*, the best learnable reply is never-cut-price-high.

**E-SIM2 — species are technologies, not mistakes.** Unanimous across 8
seeds per slot: a Q-learner replacing the active undercutter does not
rediscover micro-adjustment (it parks below anchor and freezes); replacing
the static undercutter, it converges to the anchor price exactly —
endogenous tie formation at the focal point, without any author-salience
assumption. Rigid low pricing and anchor ties are attractors of the
routing game; high-frequency adjustment is not, consistent with the
empirical two-technology bifurcation and with Theorem 2(iv)'s tax on
perpetual cutters.

## 7. Related work

Calvano et al. (2020) Q-learning collusion in logit Bertrand — our demand
system nests theirs, so their apparatus (Δ, convergence rules) transfers;
Klein (2021) sequential pricing; Asker et al. (2022) learning protocols;
Abada–Lambin (2023) exploration-driven pseudo-collusion; Johnson–Rhodes–
Wildenbeest (2023) platform steering *against* collusion — our Theorem 2 is
its inverse: steering that stabilizes it; Hansen–Misra–Pai (2021) bandit
pricing. Inference-market empirics: Demirer et al. (2025) dispersion and
elasticity on OpenRouter; Fish et al. (2024) LLM pricing collusion (an
FGS-protocol LLM-agent tier exists in our codebase; running it at
confirmatory scale is future work and not claimed here). PriLLM (2025)
models a
Stackelberg routing game without calibration or the steering mechanism;
none of these combine an exactly-documented allocation rule, calibrated
behavioral heterogeneity, and platform-steering counterfactuals.

## 8. Limitations and scope

Theory assumes captive unit demand (measured end-user elasticity −0.05;
the outside-option extension in Theorem 1(iii) bounds its effect), no
capacity binding, and the documented rule rather than the (closed-source)
implementation — our probe panel verifies the rule's realized behavior for
one buyer tier only. The panel behind calibration is short (11–14 days at
freeze; 30-day re-estimation registered); costs are identified sets; the
cut-penalty θ is a single scalar from one conditional slice. Learning
results use tabular Q at Calvano hyperparameters; deep-RL and LLM-agent
tiers are built but not yet confirmatory. The species world treats author
repricing as exogenous.

## 9. Conclusion

The router is the demand curve. Its documented parameters place the
marketplace in a regime where duopoly prices sit at the menu ceiling, entry
cannot push markups below 100%, and the platform's own anti-cut steering
pays providers to keep prices high. The observed market — rigid administered
menus, an anchor-tie atom, undercutters whose cutting looks futile — is
what equilibrium under this mechanism looks like. The lever is the
mechanism, not the conduct.
