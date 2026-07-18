# Shared outline: three venue papers from the ai-routing research program

*2026-07-18. Step 1 of the submission plan. One results core, three
venue-specific papers (papers/neurips, papers/icml, papers/ec), each written
in the PI's (Tarun Chitra's) style: physics-flavored mechanism analysis
(softmax = Gibbs measure, routing exponent = inverse temperature, knife
edge = phase transition), AMM-curvature and market-microstructure analogies
(Angeris–Chitra curvature; last look; PFOF), theorem–comparative-statics–
practitioner-takeaway structure, opinionated footnotes.*

## The results core (shared across all three)

**Empirics** (from the live orcap capture; companion paper):
- 5-min per-provider price panel; four split-sample-validated behavioral
  species (anchor adopters 25%, static undercutters −0.41 log, active
  micro-adjusters >1 change/day, premium +0.34 log); OOS persistence 83-89%.
- Tie atom at the author's price 45% (3.4× grid null); identity not special
  (multiset-preserving null) — focality without salience.
- Routing flow elasticity −0.78 vs end-user −0.05 (the 20× wedge).
- Randomized probe panel: default policy firmness 99.3%; JRW-inverse
  steering: cheapest+recent-cut selected 3.9% vs 23.3% (θ≈0.17, M≈7d).
- GPU spot book: walk-the-book impact +18–52%; capital-tier registry
  (owned-DC / neocloud / own-silicon / startup) — cost bands, not points.
- Eval-probe pipeline (daily): graded MMLU/GSM8K + greedy-output hashes per
  pinned provider — the verified-quality instrument the mechanism section
  needs.

**Theory** (all closed forms CI-tested):
- T1: routing weight p^(−a) ⇒ logit demand; interior symmetric equilibrium
  p* = c·a(n−1)/(a(n−1)−n); PHASE TRANSITION at a(n−1)=n (documented a=2 ⇒
  duopoly at the menu ceiling); entry-proof Lerner floor 1/a.
- C1: with measured end-user elasticity ε=−0.05: p*(duopoly) = 41c.
- T2: cut-penalty θ deters undercutting (deviation target c+√(c²+θ/W);
  θ*∈[0.81,1] ≫ 0.17; patience boundary δ†=0.9895; perpetual-cutter 4.9×
  share tax). Steering = platform-imposed asymmetric menu cost.
- T3 (new, two-type): owned-capacity (c_L) vs spot-dependent (c_S incl.
  book impact) providers; asymmetric FOC system; comparative statics in a:
  welfare ↑ (sorting), platform revenue ↓, spot-type profit ↓ 0 (exit).
- T4 (new, quality): price-only weights make quality-shading dominant;
  quality-weighted w = q^b·p^(−a) restores high quality iff b ≥ b*
  (closed-form threshold; b*≈0.6–2 at calibrated params).
- T5 (new, design): thickness-adaptive exponent a*(n) = n/(ℓ*(n−1)) holds
  the Lerner index at target ℓ* across market thickness.

**Simulation** (validated environment; all runs seeded+manifested):
- E-SIM1: species world passes pre-registered gate (distance 0.019);
  untargeted flow elasticity −0.65±0.35 vs −0.78 observed.
- E-SIM2: learners never rediscover micro-adjustment; endogenous ties.
- E-SIM3 (+fine grid): exponent is a price dial; learning friction
  regularizes the phase transition.
- E-SIM4/4b: steering flips learner to ceiling; calibrated markets:
  ceiling 4/4 (broad rule), +81% bottom-of-book where the measured
  conditional binds.
- E-SIM6 (new): mechanism frontier with two-type learners — welfare /
  revenue / spot-viability across {uniform, a=1,2,4, adaptive 6.25, WTA,
  deployed a=2+cut-penalty}.
- E-SIM7 (new): quality game — learned hi-quality share vs b; b=0
  (deployed) vs b ≥ b*.

**Mechanism improvements (step-2 requirement; the design section)**
1. Thickness-adaptive exponent a*(n) (T5): kills the duopoly ceiling
   without WTA fragility; report welfare/revenue/viability from E-SIM6.
2. Verified-quality weighting w = q^b p^(−a) with q from the eval-probe
   pipeline (T4 + E-SIM7): repairs adverse selection the price-only rule
   creates; b* is measurable and small.
3. Steering redesign: replace the cut-penalty (price-elevating, T2) with
   quality/uptime-conditioned steering; or make the penalty symmetric
   (penalize raises equally) — removes the asymmetric menu cost.
4. Objective frontier: platform fee ∝ flow-weighted price ⇒ revenue-max
   platform prefers LOW a (high prices) — an explicit incentive
   misalignment between router operator and users; propose fee redesign
   (per-request flat fee decouples platform revenue from price level).
5. Practical constraints: reserved/committed capacity (capital tiers) —
   sharpening a starves spot-dependent providers (resilience loss);
   interior welfare optimum once outage insurance is priced; commitment
   contracts (reserved-instance analog) as the mechanism that lets
   high-marginal-cost providers survive sharp routing.

## Venue splits

**NeurIPS — "The Price of Softmax: Emergent Collusion and Mechanism
Design in Learned AI-Inference Routing Markets."** Frame: multi-agent
learning in a deployed softmax allocation mechanism. Emphasis: the
validated environment as a benchmark artifact; Q-learning outcomes
(price dial, non-emergence of micro-adjustment, steering counterfactuals,
E-SIM6/7 mechanism comparison); theory as the analytical backbone;
reproducibility checklist; broader impact.

**ICML — "Phase Transitions in Price-Weighted Routing Games: Learning
Dynamics at the Knife Edge."** Frame: learning dynamics in a
temperature-parameterized game family. Emphasis: the phase structure
(a(n−1)=n), how ε-greedy Q regularizes the transition (undershoot near the
edge, overshoot in the disciplined region), convergence/attractor
analysis, the steering MDP as reward shaping, calibration as the
experimental grounding.

**EC — "The Router Is the Mechanism: Markup Floors, Steering, and the
Design of AI Inference Marketplaces."** Frame: mechanism design with
measured parameters. Emphasis: full theory (T1–T5) with proofs; empirical
identification (probe panel, species); the design section as the payload
(adaptive exponent, verified-quality weights, fee decoupling, commitment
contracts); welfare/revenue/quality objective analysis; practitioner
takeaways.

## Review protocol (steps 4–5)

One top-reviewer report per venue, venue rubric (NeurIPS/ICML: scores
1–10 + confidence, soundness/presentation/contribution; EC: summary,
strengths/weaknesses, accept conditions), each also assessing whether the
paper reads in the PI's style (physics framing, microstructure analogies,
practitioner orientation, opinionated-but-precise prose). Iterate until
2/3 accept.
