# The Router Is the Mechanism: Markup Floors, Steering, and the Design of AI Inference Marketplaces

*Submission draft for ACM EC. Code, data manifests, and CI-enforced proofs:
`src/orcap/` in the public repository; every number in this paper
reproduces from a committed module with recorded seeds.*

## Abstract

AI inference marketplaces sell a commodity — tokens from a fixed
open-weight model — through a router that allocates each request across
competing providers by a documented rule: selection probability
proportional to 1/price². We take the rule seriously as a *mechanism* and
ask what market it buys us. Three answers. **(i) The routing exponent is
an inverse temperature, and the market sits near a phase transition.**
Weights p^(−a) induce logit (Gibbs) demand; symmetric equilibrium is
p* = c·a(n−1)/(a(n−1)−n), which diverges along a(n−1) = n. The deployed
exponent a = 2 places every two-provider market — the modal market in our
five-minute panel of the largest live marketplace — in the condensed
phase: equilibrium at the menu ceiling, and with the *measured* end-user
elasticity (−0.05), a finite duopoly price of **41× marginal cost**. An
entry-proof markup floor 1/a survives any number of entrants: at a = 2,
free entry stops at a 100% markup, forever. **(ii) The platform's own
steering is a collusion device.** Our randomized probe panel measures the
router penalizing a cheapest quote with a recent price cut (selection
3.9% vs 23.3%, weight multiplier θ ≈ 0.17 for ~7 days). We prove this
penalty deters undercutting for every agent with effective patience below
δ† = 0.9895 — the measured θ sits five-fold inside the deterrence
threshold — and taxes a perpetual micro-adjuster's flow by ~5×. In our
calibrated, pre-registered-and-validated simulation, switching the
measured penalty on flips a learning undercutter to the price ceiling in
4/4 markets and raises the flow-dominant bottom-of-book quote by up to
81%. **(iii) The mechanism is repairable, and the objectives disagree.**
In a two-type world calibrated to observed capital structure (owned
data-center vs GPU-spot-dependent providers), welfare rises and platform
ad-valorem revenue *falls* in a — the router operator is paid to keep the
market soft. We propose and evaluate, theoretically and with learning
agents, three implementable repairs: a thickness-adaptive exponent
a*(n) = n/(ℓ*(n−1)) that pins the Lerner index at a target across market
sizes; verified-quality weighting w = q^b·p^(−a) with q measured by our
deployed evaluation probes, which undoes the quality-shading adverse
selection that price-only weights create (closed-form threshold
b* ≈ 0.6–2); and fee decoupling (per-request rather than ad valorem),
which removes the platform's incentive to prefer high prices. All
findings are for one marketplace (the largest), one buyer tier, and a
registered re-estimation window; scope is stated throughout. The lever
is the mechanism, not the conduct.

## 1. Introduction

When an intermediary both *quotes* the market and *clears* it, the
intermediary's algorithm is the demand curve. This is an old story in
market microstructure — payment for order flow, last look in FX, the
curvature of an automated market maker — and it is now the story of AI
inference. On OpenRouter, the largest open inference marketplace, a buyer
sends a request naming a model; a router selects which of n competing
providers serves it. The default selection rule is documented in one
sentence: filter recently failing providers, then choose with probability
∝ 1/price². Nothing else a provider does moves demand except through that
rule (and one measured exception we return to at length). So the game
providers play is not Bertrand, not search, not bargaining: it is pricing
against a softmax.¹

We spent four months instrumenting this market at five-minute resolution
(prices, congestion, realized flow, GPU spot books, randomized routing
probes) and this paper asks the mechanism-design question the data forces:
*is the observed price structure — rigid administered menus, a 45% atom of
providers tied exactly at the model author's price, undercutters whose
cuts appear futile, sustained 1.3–10× same-model dispersion — what the
deployed rule should produce in equilibrium?* The answer is yes, in an
uncomfortably strong sense: the deployed parameters sit in the region
where theory predicts *exactly* the observed pathologies, and the
platform's own quality-protective steering is, mathematically, the
instrument that stabilizes them.

The physics framing is not decoration. Weights p^(−a) are a Gibbs measure
over providers with energy a·log p; the exponent is an inverse
temperature. High temperature (small a) melts price competition —
allocation ignores prices, so why cut them? Low temperature (large a)
freezes allocation onto the cheapest provider — Bertrand, with its
fragility. In between, there is a *critical line* a(n−1) = n on which the
symmetric equilibrium price diverges. The deployed a = 2 puts n = 2
markets exactly on the line. One does not operate a power plant at
criticality by accident and call it a pricing strategy; but one might do
it by choosing a "reasonable-looking" load-balancing rule without solving
the game it induces. That, we will argue, is what happened — and because
the rule is *documented*, every parameter in our theory is measured or
published, not estimated from a structural model.²

**Contributions.** (1) A complete equilibrium analysis of inverse-power
routing with captive and near-captive demand: interior formula, phase
structure, an entry-proof Lerner floor, and the measured-elasticity
duopoly price of 41c (§3). The static skeleton is
Anderson–de Palma–Thisse logit pricing; the content is the mapping — the
"differentiation parameter" is a published platform constant, and its
placement is on the critical line. (2) A theory of the measured steering
penalty as a platform-imposed asymmetric menu cost: closed-form deviation
target, deterrence threshold, patience boundary, perpetual-cutter tax
(§4). To our knowledge the first steering-*supports*-collusion result
with an empirically measured steering parameter (Johnson–Rhodes–
Wildenbeest study the inverse design). (3) A behaviorally calibrated,
pre-registered, validated multi-agent environment in which every
counterfactual in this paper is run (§5); its validation gate includes an
untargeted moment — the simulated flow elasticity emerges from the router
alone and matches the panel. (4) A design section with teeth (§6–7):
two-type (data-center vs spot) welfare/revenue/viability frontier over
the exponent; a quality game showing price-only weights make shading
dominant and verified-quality weights repair it at a small, computable
b*; a thickness-adaptive exponent; fee decoupling. Each proposal is
evaluated with learning agents, not just first-order conditions.

¹ The analogy to AMM curvature is exact in spirit: an AMM designer choosing
invariant curvature trades price sensitivity against inventory risk
(Angeris–Chitra); a router choosing a trades price discipline against
allocation concentration. Both are one-parameter families of demand curves
imposed by an intermediary; both parameters are typically chosen by vibes.

² Structural IO estimates a logit differentiation parameter from data and
argues identification. Here the platform *publishes* it. This is the rare
setting where the mechanism-design counterfactual requires no demand
estimation at all: the demand curve is in the documentation.

## 2. The market and the data

OpenRouter routes buyer requests to ~90 providers serving shared
open-weight models. Our capture (public repo `orcap`) records, at 5-minute
grain: per-provider-per-model price menus; congestion telemetry
(utilization, rate-limits, latency, deranking); realized daily token flow
per provider-model (demand shares); the vast.ai GPU spot order book (the
input market for providers without owned capacity); provider capital
structure (a confidence-flagged registry: hyperscaler DC / funded
neocloud / own-silicon / small startup); and two active instruments:
(a) a **randomized routing probe panel** — hourly one-token requests under
default and pinned policies with randomized arm order, identifying the
router's realized selection behavior for our buyer tier; (b) a **daily
evaluation probe battery** — graded public benchmark items and
deterministic prompts, per pinned provider, yielding verified per-provider
quality signals (used in §7.2).

Stylized facts (established in the empirical companion under
pre-registration discipline; all replicated in the repo): four
split-sample-validated pricing species — *anchor adopters* (quote exactly
the model author's price on ≥80% of days; 25% of pairs; 83–89% OOS
persistence), *static undercutters* (median −0.41 log, near-zero
repricing), *active undercutters* (>1 change/day micro-adjusters, ~sub-1%
flow), *premium* (+0.34 log, rigid); a tie atom at the author price 3.4×
its grid-mechanical null, with author *identity* not special under a
multiset-preserving null (focality without salience); routing-level flow
elasticity −0.78 against end-user elasticity −0.05 (a 20× wedge); and the
steering fact central to §4: among position-zero default-policy
selections, a cheapest provider with a price cut in the trailing week is
chosen 3.9% of the time versus 23.3% without (θ ≈ 0.17, memory ≈ 7 days).

## 3. Equilibrium: temperature, criticality, and the markup floor

n providers post prices p_i ∈ (0, p̄] (p̄ the menu ceiling); marginal
costs c_i; a unit mass of requests arrives per epoch; the router selects
i first with probability s_i = p_i^(−a)/Σ_j p_j^(−a). Profits
π_i = s_i(p_i − c_i). With logits −a log p_i this is softmax: **the
router is a logit demand system with inverse temperature a.**

**Lemma 1.** ∂s_i/∂p_i = −(a/p_i)s_i(1−s_i): own-price share elasticity
is −a(1−s_i) — bounded by a no matter how many rivals.

**Lemma 2 (single crossing).** π_i is strictly quasiconcave on (c_i, p̄];
the best response is the unique root of h(p) ≡ a(1−s_i(p))(p−c_i)/p = 1,
or the ceiling if h(p̄) ≤ 1.

**Theorem 1 (phase structure and floor).** Symmetric costs c: (i) if
a(n−1) > n (and p̄ > p*), the unique symmetric equilibrium is
p* = c·a(n−1)/(a(n−1)−n); (ii) if a(n−1) ≤ n, it is the menu ceiling p̄ —
at a = 2, precisely n ≤ 2; (iii) for a > 1, ANY interior equilibrium —
asymmetric costs, any n, any outside option — satisfies
(p_i−c_i)/p_i > 1/a, i.e. p_i > c_i·a/(a−1), and the floor is tight as
n → ∞. *(Proofs: Appendix A; every closed form here and below is enforced
in CI against continuum numerics — 13 tests.)*

**Corollary 1 (measured elasticity).** With aggregate demand D ∝ P^ε
(inclusive-value index P, ε the end-user elasticity), the symmetric FOC is
p/(p−c) = a(n−1)/n + |ε|/n. At the measured ε = −0.05 and deployed a = 2:
duopoly p* = 41c. Captivity is the ε → 0 limit, not an assumption we need.

Three readings. *The floor is entry-proof:* Lemma 1 bounds share
elasticity by a, so no amount of entry raises the elasticity a provider
faces above a; at a = 2, markups never fall below 100%. Softmax smoothing
— adopted for uptime insurance and exploration — *is* product
differentiation, manufactured by the platform. *The critical line is
populated:* the modal market in our panel has 1–3 providers; a = 2 puts
n = 2 on the line, and the observed menus-at-ceiling behavior (premium
species, adopters at the author's list price) is the condensed phase.
*The wedge is structural:* Corollary 1 turns our measured 20× elasticity
wedge into the theorem's parameter — near-captive end-user demand is
exactly why realistic menus bind before equilibrium does.

## 4. Steering: the measured penalty is a deterrence device

Model the measured behavior as: a provider whose price is below its price
at any of the last M epochs has weight θ·w(p). (At symmetric profiles,
"any recent cutter" and the measured "cheapest with a recent cut"
coincide — any strict cut makes you cheapest; our calibrated experiments
run both variants.)

**Theorem 2.** At a symmetric profile q with rival weight W = (n−1)q^(−2):
(i) the flagged deviant's optimal cut is p_dev = c + √(c² + θ/W);
(ii) undercutting is unprofitable for a one-epoch optimizer iff θ ≤ θ*,
the unique root of v(θ*) = (q−c)/n; across calibrated configurations
θ* ∈ [0.81, 1.0] — the measured θ = 0.17 sits deep inside; (iii) a
one-time cut held forever is deterred iff δ ≤ δ† = 0.9895 (calibrated
parameters; δ^M ≤ 0.93); (iv) an agent cutting at least once per M epochs
is permanently flagged and pays share tax θ/(θ+n−1) vs 1/n — 4.9× at
measured values.

The economic reading: the penalty — presumably deployed as
bait-and-switch protection — is an *asymmetric menu cost on price cuts
only, imposed by the platform*. It converts the routing game into one
where holding high prices is robustly optimal for any realistically
patient agent, and it specifically taxes the high-frequency undercutting
technology we observe dying in the data (the registered cut-frequency
decay watch). Johnson–Rhodes–Wildenbeest designed steering to *break*
seller collusion; the deployed steering is their inverse, with a measured
parameter.³

³ A last-look analogy is exact: in FX, dealers who get cut off after
adverse quote updates learn to quote wide and stable. Here the router
plays the liquidity consumer who punishes aggressive quoting.

## 5. The calibrated environment and its validation gate

Counterfactuals about mechanisms require agents, and assuming Bertrand
agents would beg every question. Our environment fits the observed
species (margins, hazards, rationing slopes from the panel's train
window; costs as identified bands from the capital-tier registry and the
GPU book with its walk-the-book impact curve) and *must pass a
pre-registered validation gate before any counterfactual runs*: ten
moments computed by identical code on simulated and observed panels,
distance ≤ 0.04, with the moments explicitly split into calibration
echoes and genuinely emergent tests. The confirmatory run (20 seeds,
deterministic replication) passes at distance 0.019; the two emergent
moments carry the weight — **flow elasticity −0.65 ± 0.35 vs −0.78
observed with no fitted allocation parameter** (the documented rule alone
generates the measured demand response), and adopter-atom OOS persistence
0.83 vs 0.834. Learning counterfactuals then show (all pre-specified,
gated, seeded): the exponent is a price dial (uniform 1.53 → a=2 0.94 →
floor at a ≥ 8, with learning friction regularizing the critical
singularity); learners never rediscover micro-adjustment and form anchor
ties endogenously; and the steering counterfactual of §4 — penalty on
flips the learning undercutter to the ceiling in 4/4 calibrated markets
(broad rule) and raises the flow-dominant bottom-of-book quote +81% where
the strict measured conditional binds.

## 6. Heterogeneous capital and the objective frontier

Providers are not symmetric. The registry splits them into owned-capacity
types (hyperscaler DCs, own silicon; low marginal cost, high fixed cost —
the "reserved instance" world) and spot-dependent types (rent H100s on a
thin order book; marginal cost includes walking the book, +18–52% at
realistic fill sizes). Take c_L = 0.10, c_S = 0.50 (the calibrated band
endpoints), n_L = 2, n_S = 3, and solve the asymmetric FOC system
p_i/(p_i−c_i) = a(1−s_i) across a:

| a | p_L | p_S | flow-price (platform ad-valorem revenue ∝) | welfare (v−Σs·c) | spot flow share | spot profit |
|---|-----|-----|-----|-----|-----|-----|
| 1.5 | 0.99 | 1.60 | 1.25 | 1.731 | 0.42 | 0.155 |
| 2 | 0.51 | 1.10 | 0.65 | 1.802 | 0.24 | 0.049 |
| 3 | 0.27 | 0.76 | 0.30 | 1.875 | 0.06 | 0.005 |
| 4 | 0.20 | 0.67 | 0.20 | 1.895 | 0.013 | 0.001 |
| 6 | 0.15 | 0.60 | 0.15 | 1.900 | ~0 | ~0 |

**The objectives disagree, and the platform is conflicted.** Welfare
(allocative: flow sorted to low-cost capacity) is increasing in a;
ad-valorem platform revenue is *decreasing* in a — a platform charging a
percentage fee is paid to keep the market soft. And spot-dependent
viability collapses in a: the sharp-routing world is a world where only
data-center owners survive, which prices resilience at zero until the
first correlated outage. The welfare-optimal a is interior once outage
insurance is valued; the revenue-optimal a is small; the deployed a = 2
is best rationalized as revenue-serving, not welfare-serving.⁴

*Robustness (cost bands).* The welfare-increasing-in-a ordering holds at
all four corners of the identified cost bands (c_L ∈ {0.05, 0.25},
c_S ∈ {0.3, 0.7}): monotone in every case (e.g., at the adversarial
corner c_L=0.25, c_S=0.3, welfare still rises 1.721 → 1.730 across
a = 1.5 → 6.25).

*Resilience-adjusted welfare.* Add a correlated-outage term: with
probability ρ per epoch all owned capacity fails simultaneously; if the
spot fleet has exited (profit below fixed cost F_S = 0.01), those
requests are lost at value v. At ρ = 2%: welfare-adjusted values are
1.802 (a=2, spot viable) vs 1.855–1.860 (a ≥ 4, spot exited) — sharp
routing still wins, but the gap narrows fourfold; the ranking flips at
ρ ≳ 5%. The honest design statement: softness is welfare-justified as
outage insurance only for correlated-outage intensities above ~5% per
epoch; below that, the right architecture is sharp routing PLUS priced
capacity commitments (§7.4), not a soft exponent that pays every
provider an insurance premium whether or not insurance is delivered.

**E-MECH1 (the frontier with learners).** Replacing the FOC with
Q-learning agents (5 seeds/arm) confirms the ordering — learned welfare
1.66 (uniform) → 1.797 (a=2) → 1.856 (adaptive a*(n)=6.25) → 1.898
(WTA); learned flow-weighted price 1.58 → 0.68 → 0.43 → 0.40; spot-type
profit 0.64 → 0.157 → 0.011 → −0.000 (WTA drives spot types below cost)
— with one addition theory alone would not have exhibited so starkly:
**the deployed pair (a = 2 + the measured cut-penalty) is simultaneously
the worst arm on welfare (1.66, tied with uniform routing) and the best
for ad-valorem platform revenue (flow price 1.60 — the menu ceiling; all
learners at the cap).** The steering does not merely blunt the exponent's
discipline; it deletes it. The platform's deployed configuration is the
revenue-maximizing corner of the frontier we traced.

⁴ Practitioner reading: this is the routing-market version of the PFOF
debate. The intermediary's fee base is the price level; sharpening
execution quality cuts its own revenue. The fix (§7.3) is the same as in
brokerage: decouple the fee from the price.

## 7. Mechanism repairs

**7.1 Thickness-adaptive temperature.** Theorem 1 inverts: to hold the
Lerner index at target ℓ* in an n-provider market, set
a*(n) = n/(ℓ*(n−1)). At ℓ* = 0.2: a* = 10 (n=2), 7.5 (n=3), 6.25 (n=5),
→ 5.56. One line of router code; kills the critical line (no market sits
in the condensed phase); keeps softmax's exploration/insurance properties
(unlike WTA). Cost: §6's viability column — sharp temperatures starve
spot-dependent capacity, so ℓ* should embed the resilience value, or be
paired with capacity commitments (7.4).

**7.2 Verified-quality weighting.** Price-only weights create adverse
selection in *quality*: serving a quantized/degraded variant saves cost Δ
at buyer-invisible quality damage d, and under w = p^(−a) shading is
strictly dominant (share is unchanged, cost falls). Weight
w = q^b·p^(−a) instead, with q verified: shading multiplies weight by
(1−d)^b, and the symmetric all-high profile is an equilibrium iff b ≥ b*
solving (1/n)(p−c) = [(1−d)^b/((1−d)^b+n−1)](p−c+Δ). At calibrated
values (n=3, d=0.2, Δ=0.08): **b* = 0.63** — a *modest* quality exponent
suffices, and b* falls with n. The required q is not hypothetical: our
deployed evaluation probes already produce per-provider graded-accuracy
and output-consistency scores daily. [E-MECH2: learning agents choosing (price, quality) under
b ∈ {0, 0.5, 1, 2}; results below.]

**7.3 Fee decoupling.** Ad-valorem fees make the platform's objective
∝ flow-weighted price (§6). A per-request (or per-token-served) flat fee
makes platform revenue proportional to *volume*, aligning the platform
with allocative efficiency and removing its stake in the price level.
This is the one-line governance repair that makes 7.1 incentive-
compatible *for the platform*.

**7.4 Steering redesign and commitment contracts.** Replace the
asymmetric cut-penalty with (i) symmetric change-penalties (a true menu
cost — removes the directional deterrence of Theorem 2 while keeping
stability protection), or (ii) quality/uptime-conditioned steering only
(penalize serving failures, not price cuts — the stated goal without the
collusive side effect). For spot-dependent viability under sharp
temperatures: capacity-commitment contracts (the reserved-instance
analog, cf. the capacity-certified routing mechanism in the companion
repo): providers pre-commit admitted capacity at posted prices and are
penalized for reneging — converting resilience from an implicit subsidy
paid via soft routing into an explicit priced product.

## 8. Related work

Anderson–de Palma–Thisse (logit oligopoly); Calvano et al., Klein, Asker
et al., Abada–Lambin, Hansen–Misra–Pai (algorithmic pricing/collusion —
our demand system nests Calvano's, so their apparatus transfers);
Johnson–Rhodes–Wildenbeest (platform steering against collusion; we
document and analyze its deployed inverse); Demirer et al. (OpenRouter
empirics: dispersion, elasticity); PriLLM (Stackelberg routing theory, no
calibration or steering); Fish et al. (LLM pricing agents); Angeris–
Chitra (curvature as an intermediary's demand-shape choice); token-
pricing screening (Bergemann–Bonatti–Smolin); metering and covert
quantization audits (the practices §7.2 prices). None combine a
documented allocation rule, measured steering, calibrated behavioral
heterogeneity, and mechanism repairs evaluated with learning agents.

## 9. Limitations

Theory: symmetric-equilibrium characterization (the floor is the
asymmetric statement); captive baseline with measured-ε corollary;
capacity non-binding (rationing lives in the empirical companion).
Measurement: θ from one conditional slice of one buyer tier; panel short
(30-day re-estimation registered, auto-reopening); costs are identified
sets (all quantitative claims reported across bands). Simulation:
tabular Q at Calvano hyperparameters; expected-allocation training
(exact under non-binding capacity); LLM-agent tier built, not
confirmatory. The quality game's d and Δ are calibrated to our eval-probe
detection scale, not to a demand-side damage estimate.

## 10. Practitioner takeaways

For router operators: (1) publish n-adaptive temperatures, not one
exponent — a*(n) = n/(ℓ*(n−1)) is one line; (2) never penalize price
cuts asymmetrically — you are operating a cartel enforcement device;
penalize failures, not prices; (3) weight by verified quality with even a
small b — your own eval probes suffice; (4) charge flat fees if you want
to be believed about (1)–(3). For providers: under the deployed rule,
undercutting is (measurably) taxed and micro-adjustment is dominated —
the observed adopter/premium behavior is the rational response, which is
precisely the problem. For regulators: conduct-based tools will find
nothing here; every elevated price in this paper is a static Nash
equilibrium of a published rule.

## Appendix A: proofs

[Lemmas 1–2, Theorem 1(i)–(iii), Corollary 1, Theorem 2(i)–(iv): full
proofs as in the companion theory manuscript, Appendix A; single-crossing
argument, FOC algebra, corner verification, envelope monotonicity,
intermediate value; 13 CI tests (`tests/market_env/test_theory.py`)
enforce every closed form against continuum numerics.]

## Appendix B: reproducibility

Calibration bundle (train/holdout split recorded), pre-registration with
dated addenda, seed manifests with source-file fingerprints, run
directories per experiment (E-SIM1–4b, E-MECH1–2), and the live capture workflows are
all in the public repository. The validation gate and its thresholds were
frozen before the first scored run.
