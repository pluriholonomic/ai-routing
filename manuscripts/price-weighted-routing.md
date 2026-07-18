# The Router Is the Demand Curve: Price Steering and Delayed Credit in AI Inference Markets

*Draft 2026-07-18. Companion to "Administered Menus and Hidden Clearing"
(empirical); this paper supplies the mechanism theory and the calibrated
multi-agent environment. Code: `src/orcap/market_env/`; every number
reproduces from committed modules with recorded seeds and manifests.*

## Abstract

Open-weight inference is a partially substitutable execution service sold by
providers through routers. We study a documented inverse-square allocation
rule and a conditional selection association for recent price cutters.
Inverse-power routing creates a classical markup floor. More importantly, a
finite cut penalty creates a **delayed-credit region**: cutting is immediately
unprofitable yet optimal after the penalty expires. In our calibrated
two-price reduction, the rational boundary is 9.24 periods. At the observed
seven-period memory, exact optimization cuts, while a primitive-action
Q-learner remains high in 19/20 seeds. Adding a payoff-equivalent commitment
option leaves the optimal value unchanged, restores the cut in 18/20 seeds,
and lowers normalized regret by 6.43 percentage points (paired 95% interval
[4.93, 7.55]). The regret effect remains beneficial in all nine registered
Q-learning parameter cells. Across four calibrated price books, its sign flips
with the rational memory boundary, although the strict transport gate fails.
An eight-step TD target does not improve on one-step Q, narrowing the result to
option-specific temporal abstraction.
Thus router memory can separate rational incentives from learned pricing, but
interventions are nonmonotone. This is a calibrated counterfactual mechanism,
not evidence of provider conduct or live-router causality.

## 1. Introduction

Routing marketplaces for AI inference (OpenRouter and peers) sell a
homogeneous good — tokens from a specific model — served by multiple
competing providers. Buyers do not choose providers; a router does.
For non-tool-calling traffic, OpenRouter documents its price-weighted default:
filter providers with recent outages, then select with probability proportional
to the inverse square of price.
This one sentence pins down the residual demand curve every provider faces.
The competitive question is therefore not "how do buyers search" but "what
game does the routing rule induce," and it can be answered exactly.

Our empirical companion paper documents, from a 5-minute-resolution capture
of the marketplace: same-model price dispersion sustained at 1.3–10×;
menu-cost repricing with a large atom of providers pricing *exactly* at the
model author's price; a large wedge between routing-share elasticity and an
external end-user demand benchmark; and a selection association consistent
with lower weight on recent cutters (a cheapest-quoting provider with a cut in
the last week is selected 3.9% of the time vs 23.3% without). This paper asks whether those facts are what
competition under price-weighted routing *should* produce — and whether the
router's design choices could themselves be the source of the observed
price elevation.

**Contributions.**

1. *Theory* (§3). We map inverse-power routing to a standard differentiated-
   products demand system and state the resulting symmetric equilibrium and
   markup floor. Our new object is dynamic: a history-dependent cut penalty
   creates an exact wedge between the immediately optimal price and the
   infinite-horizon optimum. We derive the rational memory boundary and prove
   that a feasible persistent-cut option cannot change the provider's optimal
   discounted value.
2. *A calibrated, validated multi-agent environment* (§4–5). Provider
   behavior is not assumed: four behavioral species are classified from
   panel data on a train window under pre-registered rules, and the
   assembled market must reproduce held-out moments before any
   counterfactual is run. The validation gate includes an untargeted
   moment: the simulated flow elasticity emerges from the router alone.
3. *Learning counterfactuals* (§6). A preregistered audit rejects the original
   equilibrium and state-aliasing explanations of the high-price learning
   path. A second preregistered experiment identifies delayed credit instead:
   temporal abstraction closes the implementation gap at the calibrated
   memory, but overcorrects beyond the rational cut boundary. A registered
   eight-step TD target does not improve on one-step Q, so the successful
   intervention is not generalized to every longer backup.

**Why this matters beyond one marketplace.** Price-weighted probabilistic
allocation appears in machine-mediated procurement, cloud brokerage, and ad
allocation. Our results separate two design margins. The routing exponent
governs static residual demand. Router memory governs dynamic credit
assignment: a penalty can leave a rational provider willing to cut while
preventing a primitive learner from discovering that cut. A commitment
interface can repair the latter, but may induce overcommitment when the
rational optimum changes. These are mechanism effects, not conduct labels.

## 2. Model

A market is one (model, workload). n providers post prices p_i ∈ (0, p̄]
from a menu (the ceiling p̄ is the highest feasible/observed menu price;
discreteness is irrelevant to the theory and used only in learning
experiments). Marginal cost c_i per served request; capacity non-binding
for the theory (the empirical companion treats rationing). Per epoch a unit
mass D of captive requests arrives. We treat D as fixed in the baseline and
use an external published end-user elasticity near −0.05 only as a sensitivity
benchmark below; this repository does not estimate aggregate token demand.
The router selects
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
symmetric pure-strategy equilibrium is interior:

    p* = c · a(n−1) / (a(n−1) − n).

(If p̄ ≤ p* the ceiling binds and the equilibrium is p̄.)
(ii) If a(n−1) ≤ n, every provider's best response exceeds any rival
price: the unique symmetric pure-strategy equilibrium is p_i = p̄ (the menu
ceiling).
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

**Corollary 1 (elastic-demand sensitivity).**
The ceiling case is the ε → 0 limit of a finite answer. Let aggregate
demand be D = D₀·P^ε with inclusive-value index P = (Σ_j p_j^(−a))^(−1/a)
(so ∂log P/∂log p_i = s_i) and ε < 0 the end-user price elasticity. The
symmetric FOC becomes

    p/(p−c) = a(n−1)/n + |ε|/n  ≡  R,    p* = c·R/(R−1)   (R > 1).

Elastic demand produces a finite symmetric stationary price exactly when
`a(n−1)+|ε|>n`; otherwise the menu ceiling still binds. At the external
benchmark ε = −0.05 and the documented a = 2, duopoly
gives R = 1.025 and

    p* = 41·c :

(The inclusive-value aggregator P is a modeling choice for mapping the
external token-demand elasticity into a price index; any aggregator with
∂log P/∂log p_i = s_i + o(s_i) gives the same FOC to first order.)
Conditional on this demand model, the stationary duopoly price is forty-one
times marginal cost. This is a sensitivity calculation, not an estimated
markup. (Verified
against the full profit function to 4 decimals at (n, a, ε) ∈
{(2,2,−.05), (3,2,−.05), (2,2,−.2), (5,2,−.05), (2,2,−1)}.) The
external aggregate-demand benchmark and the companion paper's routing-share
elasticity play different roles. Near-captive aggregate demand explains why
realistic menus may bind before the stationary price, while provider-level
own-price share elasticity is generated directly by the router.

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
(i) *Optimal deviation.* A flagged deviant's unconstrained best response is

    p_dev = c + √(c² + θ/W),

(unique, by the same single-crossing argument applied to the flagged share).
The best weak cut is `p_hat=min{q,p_dev}`; in every calibration below
`p_dev<q`.
(ii) *Myopic deterrence.* The flagged deviation value v(θ) =
s_θ(p_hat)(p_hat−c) is continuous and strictly increasing with v(0)=0;
undercutting is unprofitable for a one-epoch optimizer iff θ ≤ θ*, the
unique solution of v(θ*) = (q−c)/n (θ* = 1 if v(1) is below). Calibrated
configurations give θ* ∈ [0.81, 1.0]; the measured θ = 0.17 deters with
wide margin.
(iii) *Patience boundary.* A one-time cut to p held forever, flagged for M
epochs, has present value gain
(1−δ^M)/(1−δ)·[v_θ(p) − v̄] + δ^M/(1−δ)·[v_1(p) − v̄], v̄ = (q−c)/n.
Deterrence for all p holds iff δ ≤ δ†, the root of
max_p PV(p; δ) = 0. In the symmetric benchmark (n=5, q=1, c=0.2, θ=0.17,
M=7), **δ† = 0.9895**. This calculation does not apply mechanically to the
heterogeneous learned profile studied below; that profile requires its own
multi-period deviation audit.
(iv) *Perpetual-cutter tax.* An agent repricing downward at least once per
M epochs is permanently flagged: at symmetric prices its share is
θ/(θ+n−1) vs 1/n unflagged — at θ=0.17, n=5, a 4.9× share tax. This is an
allocation wedge, not by itself a dominance claim because the cutter's price
and margin also change.

*Proof.* (i) FOC of θp^(−2)(p−c)/(θp^(−2)+W) reduces to
Wp² − 2Wcp − θ = 0; projection onto the weak-cut set gives `p_hat`.
(ii) monotone comparative statics in θ; continuity;
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

**Reading.** The cut penalty is plausibly quality protection against
bait-and-switch repricing. Mathematically it is an asymmetric, platform-imposed
cost of lowering a quote. Theorem 2 identifies its one-period and symmetric-
benchmark effects. It does not establish that a heterogeneous high-price path
is an equilibrium. The next result characterizes exactly when such a path is
rational and when it reflects delayed credit for a bounded algorithm.

### 3.3 Delayed credit under history-dependent routing

Fix rivals and restrict the subject provider to a high quote `H` and a low
quote `l`. Let `u_H` be profit at `H`, `u_L` unpenalized profit at `l`, and
`u_θL` penalized profit at `l`. Suppose

    u_L > u_H > u_θL.

The low quote is best after the flag expires, but worse while flagged.

**Theorem 3 (rational memory boundary).** If quoting high resets the `M`-period
cut history, the optimal policy from an all-high history is either stay high
forever or cut immediately and remain low. The cut is optimal if and only if

    γ^M > (u_H-u_θL)/(u_L-u_θL).                              (1)

Thus the rational boundary is

    M* = log[(u_H-u_θL)/(u_L-u_θL)] / log γ.

For the audited E-SIM4 profile, `(u_H,u_θL,u_L) =
(0.1067535,0.0351280,0.1501829)` and `γ=0.95`, so `M*=9.240`: a rational
provider cuts through integer memory nine and stays high from ten onward.

**Corollary 2 (bounded-horizon wedge).** Whenever (1) holds, every receding-
horizon controller that evaluates at most `M` consecutive low periods prefers
high, because it sees only `u_θL<u_H`, while the infinite-horizon optimizer
cuts. This is the delayed-credit region.

**Theorem 4 (value-equivalent temporal abstraction).** Add a macro action that
executes `M+1` existing low actions, while retaining both primitive actions.
The augmented semi-Markov problem has exactly the same optimal value as the
primitive problem at every state.

*Proof sketch.* Once the history is all-low, low strictly dominates inserting a
high quote. Before then, high resets progress. Any eventual-cut policy is
therefore a finite wait at high followed by low forever; comparing its value to
high forever gives (1), and waiting cannot improve the preferred alternative.
For Theorem 4, primitive actions are contained in the augmented problem, while
every macro action can be unrolled into its defining primitive path with the
same discounted rewards and states. Appendix A gives the full proof.

Theorem 4 separates economic opportunity from discovery: a macro action can
change learning without changing feasible pricing paths or the provider's
optimal value. It is not a social-welfare theorem.

### 3.4 What the theory does NOT claim

No provider communication, agreement, or intent is observed. A learned price
is not a Nash equilibrium or a "learning analog" of one. The multi-period
deviation audit explicitly rejects equilibrium for the E-SIM4 ceiling path.
The policy conclusion concerns exponent choice, steering memory, and agent
interfaces—not provider conduct. Costs enter only as bands outside the
controlled two-price reduction.

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

*Emergent moments* (no allocation parameter targets them; these carry the
evidential weight):
- **Flow elasticity −0.718 ± 0.351 vs market-conditional target −1.153.** The
  documented inverse-square rule gets the sign and order of magnitude, which
  is exactly the frozen gate; it does not numerically match the point target.
- **Adopter-atom OOS persistence 0.722 ± 0.082 vs 0.834.** The simulator is
  13.4% below the held-out target and remains inside the registered tolerance.
- **Dispersion 1.991 vs 2.236.** The max/min ratio is 11.0% below the
  market-conditional target. Its level is partially emergent from the
  composition and response interaction.

Passing distance 0.0193 establishes calibration adequacy for the registered
counterfactuals, not a structural goodness-of-fit test or external validation
of the live router.

## 6. Learning counterfactuals (gated on §5)

All confirmatory designs use seeds 0--19 and immutable JSON manifests. Results
are intention-to-simulate unless their prespecified convergence gate passes.
Seed-bootstrap intervals quantify Monte Carlo variation under the frozen
simulator; they are not confidence intervals for live-market parameters or
uncertainty in the calibration inputs.

**E-SIM3 — the exponent disciplines prices, but not all policies converge.**
Across the designed exponents `a={0,1,2,4,8,32}`, mean terminal prices are
1.564, 1.247, 0.939, 0.651, 0.400, and 0.400. Every adjacent paired interval
through `4→8` is strictly negative; the arm-mean Spearman correlation is
−0.986. However, policy stability is 19/20, 20/20, 20/20, 6/20, 0/20, and
0/20. The high-exponent arms therefore support a price-discipline statement
about the frozen learning process, not a converged-equilibrium claim. The
Calvano index is secondary and weak at `a=2`; we do not use it as evidence of
collusion.

**E-SIM4 — the initial price-elevation result fails equilibrium audit.** In the
stylized five-provider world, the seven-period penalty raises the learner's
median quote from 0.725 to the 1.600 grid ceiling in 20/20 seeds; mean market
price rises from 0.960 to 1.135. But a permanent cut to 0.656 bears seven
penalized periods and then raises discounted value from 2.135 to 2.310, a gain
of 8.17%, in every seed. The ceiling path is therefore a Q-learning trap, not
an equilibrium predicted by Theorem 2.

The calibrated E-SIM4b screen reaches the ceiling in four of four broad-
penalty markets. Under cheapest-only conditioning, one bottom-of-book quote
rises from 0.400 to 0.725 times the anchor and three markets do not move. This
four-seed screen has no multi-period equilibrium audit and is exploratory; it
does not carry the paper's identification claim.

**E-SIM5 — observing penalty history is not enough.** The two-action reduction
uses the E-SIM4 high quote and best permanent cut against fixed terminal rivals.
The full state contains all `2^7=128` router histories. Exact value iteration
cuts in 20/20 profiles. A learner observing only its last action stays high in
20/20; more importantly, a learner observing the complete Markov history also
stays high in 19/20. The history-aware-minus-aliased median-price contrast is
−0.047, paired 95% interval `[−0.142,0]`. The preregistered state-aliasing gate
fails.

**E-SIM6 — delayed credit and a payoff-equivalent intervention.** We add a
`commit_low` option that executes `M+1` existing low actions. Enumerated optimal
values with and without the option agree at every state to `1e-10`, as Theorem
4 requires. At calibrated `M=7`, 18/20 option learners choose the exact action
and have at most 5% normalized regret, versus 1/20 primitive learners. The
option-minus-primitive regret contrast is −0.0643, paired 95% interval
`[−0.0755,−0.0493]`; the median-price contrast is −0.849
`[−0.944,−0.708]`.

The registered memory sweep supplies the mechanism check. Both learners
succeed at `M=1,3,5`. At `M=7,9`, the exact optimizer still cuts while primitive
learning fails, and the option succeeds in 18/20 and 16/20 seeds. At `M=12`,
above the theoretical boundary `M*=9.240`, the exact optimizer stays high;
primitive learning agrees in 20/20, whereas the option often overcommits and
adds 0.0942 normalized regret `[0.0735,0.1160]`. The intervention is therefore
effective specifically in the delayed-credit region, not universally.

**E-SIM7 — cross-market transport is partial.** Applying the same design to
all four frozen calibrated price books fails the preregistered transport gate:
only two markets are delayed-credit eligible, and primitive success there is
12/20 and 14/20 rather than at most 4/20. Nevertheless, the prespecified
rational-boundary classification aligns with all four realized effect signs.
In the two eligible books
(`M*=26.31,27.91`), exact optimization cuts and the option lowers normalized
regret by 0.178 `[0.080,0.275]` and 0.118 `[0.032,0.215]`. In the two ineligible
books (`M*=2.59,2.67`), exact optimization stays high and the option *adds*
0.155 `[0.139,0.163]` and 0.152 `[0.136,0.160]` regret. This is descriptive
theory-aligned sign transport, not confirmation of universal trap severity.

**E-SIM8 — local Q-learning robustness passes.** A preregistered `3×3` grid
over learning rate `alpha={0.05,0.15,0.30}` and exploration decay
`beta={1,2,4}×10⁻⁵` passes its composite gate in seven of nine cells. The
option's regret interval is strictly negative in all nine cells, with mean
improvements from 0.026 to 0.068; option success is 18/20 or 19/20 throughout.
The two failed cells have high learning rate and slower exploration decay:
primitive success rises to 12/20 and 6/20, violating the preregistered severity
criterion even though the option remains beneficial. The intervention is
therefore robust locally within tabular Q, while primitive failure severity is
algorithm-parameter dependent.

**E-SIM9 — an ordinary multi-step target fails.** Holding the primitive action
set and every price path fixed, an eight-step Q target yields 0/20 successful
learners, versus 1/20 for one-step Q and 18/20 for the option benchmark. Its
normalized-regret contrast relative to one-step Q is `+0.0038`, paired interval
`[0,0.0113]`. The registered gate fails. Spanning the penalty window in this TD
target is therefore insufficient; the E-SIM6 result is option-specific, not a
claim that any form of multi-step credit assignment solves the problem.

Figures `analysis/sm3_esim5_state_information.pdf`,
`analysis/sm3_esim6_delayed_credit.pdf`,
`analysis/sm3_esim7_market_transport.pdf`, and
`analysis/sm3_esim8_q_robustness.pdf` show the negative state-information test,
rational boundary, learning-success rates, regret tradeoff, cross-market sign
reversal, and hyperparameter robustness directly. Figure
`analysis/sm3_esim9_multistep_falsification.pdf` shows the negative multi-step
credit test.

**E-SIM2 — behavioral attractors (descriptive).** A learner replacing an
active undercutter generally parks at a rigid below-anchor quote; replacing a
static undercutter can converge to the anchor. This result motivates the
species representation but is not used to identify the delayed-credit
mechanism.

## 7. Related work

Calvano et al. (2020) study Q-learning in logit Bertrand competition; our
demand system nests their static allocation form, but we do not infer collusion
from high prices or a Calvano index. Klein (2021), Asker et al. (2022), and
Abada--Lambin (2023) emphasize timing, protocols, and exploration artifacts.
Johnson--Rhodes--Wildenbeest (2023) study platform steering against collusion.
Brown and MacKay (2025) show that a fast pricing algorithm with multi-period
commitment can coerce a myopic rival. Our mechanism is distinct: no provider
reacts to a rival's commitment rule; the router imposes a temporary own-cut
penalty, and the calibrated high-price path is rejected as an equilibrium.

Temporal abstraction is classical. Sutton, Precup, and Singh (1999) establish
the options/SMDP framework and option Q-learning; Theorem 4 is a specialization
used as an implementation audit, not a novelty claim. Recent work on delayed
reward and sequence compression (Han et al., 2022; Ramesh et al., 2024) studies
credit assignment algorithmically. Our contribution is to derive the delay
endogenously from a marketplace routing rule, locate the rational boundary from
calibrated economic payoffs, and show that the same temporal abstraction helps
inside—but harms beyond—that boundary.

Inference-market work studies OpenRouter dispersion and demand, LLM pricing,
and Stackelberg routing. Our empirical contribution is narrower: a reproducible
calibrated counterfactual linking public routing telemetry to a finite-state
mechanism, with negative audits retained alongside the successful result.

## 8. Limitations and scope

Theory assumes captive unit demand in the baseline (Corollary 1 supplies an
external-elasticity sensitivity), no capacity binding, and the documented
non-tool-calling price-weighted rule after eligibility filtering rather than
the closed-source implementation. The probe panel measures a
conditional selection-frequency ratio for one buyer tier; interpreting that
ratio as a multiplicative weight `θ` and the trailing window as exact router
memory is a calibrated model, not a randomized causal estimate. The panel
behind calibration is short (11–14 days at freeze); the registered 30-day
re-estimation (~2026-08-06, shared with the companion paper) is the
standing robustness commitment for the fitted θ, species margins, and
hazards — sign flips there reopen this paper's calibrated claims under the
same rule that governs the companion. Costs are identified sets; the
cut-penalty θ is a single scalar from one conditional slice. E-SIM5--6 reduce
the action set to the audited high quote and best permanent cut and hold rivals
fixed; they identify a mechanism in that finite MDP, not equilibrium in the
full provider game. The 20 seeds vary learning randomness around one calibrated
payoff profile. E-SIM8 supplies local tabular-Q hyperparameter robustness and
E-SIM7 rejects universal trap transport. E-SIM9 shows that an ordinary
eight-step target is not a substitute for the option; alternative return
operators and traces remain untested. Other learner classes and executable
open-source-router replications remain required for a broad learning claim.
The species world treats author repricing as exogenous.

## 9. Conclusion

The router is the demand curve, but its memory also shapes which long-run price
paths a bounded provider algorithm can discover. Inverse-square allocation has
a classical static markup floor; the conditional 41× figure is a demand-model
sensitivity, not an estimated market markup. The new result is dynamic. At the
calibrated seven-period cut penalty, cutting is rational but delayed credit
keeps primitive Q-learning high. A payoff-equivalent commitment option closes
that implementation gap, then overcorrects once router memory crosses the
rational boundary. An ordinary longer TD target does not reproduce the effect,
which confines the result to this action abstraction. Mechanism design must
therefore evaluate both rational
incentives and learning dynamics. None of these results establishes collusion
or actual provider conduct.

## Appendix A. Proofs

**Lemma 1.** s_i = w_i/(w_i+W_{−i}), w_i = p_i^(−a), W_{−i} = Σ_{j≠i} w_j
+ w_0. dw_i/dp_i = −(a/p_i)w_i, so ds_i/dp_i = (dw_i/dp_i)·W_{−i}/(w_i+
W_{−i})² = −(a/p_i)·s_i(1−s_i). ∎

**Lemma 2.** dπ_i/dp_i = D[s_i + (p_i−c_i)ds_i/dp_i] =
D·s_i·[1 − a(1−s_i)(p_i−c_i)/p_i] = D·s_i·[1 − h(p_i)]. On (c_i, ∞):
1−s_i(p) is strictly increasing (s_i strictly decreasing by Lemma 1) and
positive; (p−c_i)/p = 1 − c_i/p is strictly increasing and positive; hence
h is strictly increasing with h(c_i) = 0. So dπ_i/dp_i > 0 while h < 1 and
< 0 after: π_i is strictly quasiconcave, and the maximizer on (c_i, p̄] is
p̄ if h(p̄) ≤ 1, else the unique root of h = 1. ∎

**Theorem 1(i).** At a symmetric interior profile, s_i = 1/n, so h(p) = 1
reads a(1−1/n)(p−c)/p = 1, i.e. p/(p−c) = a(n−1)/n, giving the formula;
p* > c requires a(n−1) > n. It is an equilibrium by Lemma 2 (each firm's
unique best response given the others at p* is p*, since h crosses 1
exactly there); uniqueness among symmetric interior candidates is
immediate since the symmetric FOC has one solution. The symmetric corner
p̄ is not an equilibrium when p̄ > p*: h(p̄) > h(p*) = 1, so a downward
deviation is strictly profitable. ∎

**Theorem 1(ii).** With all rivals at any common q and a(n−1) ≤ n, at the
symmetric point h(q) = a(1−1/n)(q−c)/q < a(n−1)/n ≤ 1, so each firm
strictly gains by raising price; the only symmetric pure-strategy profile with no
profitable deviation is q = p̄, where quasiconcavity (Lemma 2) rules out
downward deviations globally. ∎

**Theorem 1(iii).** Any interior equilibrium satisfies each firm's FOC
h(p_i) = 1 with s_i ∈ (0,1) (any w_0 ≥ 0 only lowers s_i), so
(p_i−c_i)/p_i = 1/(a(1−s_i)) > 1/a, equivalently p_i > c_i·a/(a−1) for
a > 1. Tightness: as s_i → 0 (n → ∞ or w_0 → ∞), the FOC gives
(p−c)/p → 1/a. ∎

**Corollary 1.** With D = D₀P^ε and ∂log P/∂log p_i = s_i,
dlog π_i/dlog p_i = ε·s_i − a(1−s_i) + p_i/(p_i−c). Setting to zero at the
symmetric point s = 1/n: p/(p−c) = a(n−1)/n + |ε|/n = R. Single crossing
holds by the same monotonicity argument (each term of R(p)·(p−c)/p is
increasing), so the symmetric equilibrium is p* = cR/(R−1) whenever R > 1
and p̄ > p*. ∎

**Theorem 2(i).** The flagged deviant maximizes
g(p) = θp^(−2)(p−c)/(θp^(−2)+W) = θ(p−c)/(θ+Wp²). g′ = 0 ⇔
θ(θ+Wp²) − θ(p−c)·2Wp = 0 ⇔ Wp² − 2Wcp − θ = 0 ⇔
p = c + √(c² + θ/W) (positive root). Uniqueness by the sign pattern of g′
(positive before the root, negative after). Restricting to a weak cut
`p≤q` projects this maximizer to `p_hat=min{q,p_dev}`. ∎

**Theorem 2(ii).** v(θ) = g(p_hat(θ)) is continuous. At an interior optimum,
the envelope theorem gives v′(θ) = ∂g/∂θ = W p²(p−c)/(θ+Wp²)² > 0;
at the boundary `p_hat=q`, the same partial derivative is positive. Thus
v(0) = 0 < v̄ =
(q−c)/n. If v(1) ≤ v̄ no cut is ever profitable (θ* = 1); otherwise the
intermediate value theorem gives a unique θ* with v(θ*) = v̄, and
deterrence holds iff θ ≤ θ*. ∎

**Theorem 2(iii)–(iv).** Direct computation (PV decomposition over the
flagged window and its complement; substitution of equal prices with one
weight scaled by θ). The root δ† of max_p PV(p; δ) = 0 is certified
numerically (0.9895 at the symmetric benchmark parameters; test
`test_theorem2_patience_boundary`). ∎

**Theorem 3.** In the all-low history, low forever yields `u_L/(1−γ)`.
Inserting high gives the smaller current payoff `u_H<u_L` and places a high
quote in memory, which weakly reduces the payoff from every subsequent low
until that quote expires. Hence low is uniquely optimal in the all-low state.

Before reaching all-low, any high action resets the number of consecutive low
actions since the last high to zero. Consider a policy that eventually reaches
all-low, and let `k` be the time of its final high action. Conditional on that
time, replacing all earlier transient low actions by high weakly raises current
payoff (`u_H>u_θL`) and leaves the post-`k` state unchanged. The best policy
that cuts after `k` is therefore `k` high actions followed by low forever. Its
value is

    V_k = u_H(1−γ^k)/(1−γ) + γ^k V_cut,

where

    V_cut = [(1−γ^M)u_θL + γ^M u_L]/(1−γ).

Let `V_high=u_H/(1−γ)`. Then
`V_k−V_high=γ^k(V_cut−V_high)`. If the bracket is positive, `k=0` maximizes
value; if negative, the supremum is attained by never cutting. Finally,
`V_cut>V_high` is equivalent to

    (1−γ^M)u_θL+γ^M u_L>u_H,

which rearranges to (1). Taking logarithms yields `M*`; because `log γ<0`,
cutting is optimal for `M<M*`. ∎

**Corollary 2.** For any horizon `h≤M`, committing to low for the evaluated
horizon yields `u_θL` in every included period, whereas high yields `u_H`.
Since `u_H>u_θL`, the bounded-horizon controller stays high. When (1) also
holds, its action differs from the infinite-horizon optimum. ∎

**Theorem 4.** Let the primitive MDP have optimal value `V*` and augment it
with any option equal to a finite feasible sequence of primitive actions. The
augmented action set includes all primitive actions, so its optimal value
`V*_O≥V*`. Conversely, replace every option selected by an augmented policy
with its defining primitive sequence. The unrolled policy is feasible in the
primitive MDP and induces the same state sequence and discounted reward, so
`V*_O≤V*`. Therefore `V*_O=V*` at every state. The E-SIM6 implementation
checks this identity over all binary histories before reporting outcomes. ∎

The static closed forms are checked against continuum numerics in
`tests/market_env/test_theory.py`; the history transition, Bellman residual,
permanent-cut identity, and option-value equivalence are checked in
`tests/market_env/test_state_aliasing.py`.
