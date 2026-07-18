# Referee reports — "The Router Is the Demand Curve"

## Round 2 (final) — decision: ACCEPT (minor)

All four required items landed, and two of them improved the paper beyond
what the round-1 report asked for:

**R1 resolved, upgraded.** The ε-corrected corollary is exactly what was
requested: the FOC p/(p−c) = a(n−1)/n + |ε|/n is proved with the same
single-crossing argument, verified against the full profit function at
five (n, a, ε) points, and the duopoly headline "41× marginal cost at the
measured elasticity" is both more defensible and more striking than the
ceiling statement it replaces. The reviewer verifies the algebra: at
n=2, a=2, |ε|=0.05, R = 1.025 and R/(R−1) = 41. Correct. One residual
modeling choice — the inclusive-value aggregator P = (Σp^(−a))^(−1/a) for
mapping the measured token-demand elasticity into the index — should be
stated as such (minor).

**R2 resolved honestly.** The symmetric-profile coincidence of the two
conditioning rules is correct and neatly argued; the calibrated experiment
runs both variants rather than picking the favorable one.

**R3 resolved.** The echo/emergent split is now explicit and the paper
leads with the two moments that carry weight. This reviewer considers the
untargeted flow-elasticity replication the single best empirical fact in
the paper.

**R4 resolved, with the right scoping.** The calibrated steering
experiment shows ceiling convergence in 4/4 markets under the broad rule,
and — under the strict measured rule — an +81% rise in the bottom-of-book
quote in the one market where the learner occupies the cheapest region,
with escape elsewhere. The authors correctly note the unweighted market
mean understates the effect under 1/p² flow concentration, and correctly
scope the +81% to a single market (the panel has only four author-anchored
calibrated markets; this is a data limit, not a design flaw). The
bracketing framing (broad vs strict rule) is the honest way to handle the
unobserved treatment of non-cheapest cutters.

**Remaining minor items (camera-ready):** (i) state the inclusive-value
mapping assumption; (ii) figures: the a-dial curve (theory Nash + learned
prices overlaid) and the E-SIM4b per-market bars would carry §6; (iii)
appendix with the six-line proofs written out; (iv) the 30-day
recalibration already registered in the companion should be referenced as
the standing robustness commitment for the fitted θ and species margins.

**On theoretical rigor (the question this review was asked to answer):**
the economic results ARE rigorous as now stated. Theorem 1 and Corollary 1
are complete proofs at the level of an EC paper (single-crossing →
uniqueness of best response; FOC algebra; corner verification; limits);
Theorem 2's parts (i), (ii), (iv) are complete, and (iii) is an explicit
computation with a numerically certified root — all thirteen closed-form
claims are enforced by CI tests against continuum numerics. The knife-edge
and floor statements are correctly attributed to the classical logit
literature with the contribution located in the documented-rule mapping,
the measured-parameter placement, and the steering theorem. No claim in
the paper now outruns its proof or its data.

**Decision: ACCEPT with minor revisions.** The combination — a documented
allocation rule treated as a demand primitive, a markup floor that entry
cannot remove, a measured steering parameter proved to sit deep inside its
own deterrence region, and a pre-registered validated environment in which
learning agents reproduce the observed market's pathologies — is novel,
correct as stated, and of clear interest to both the EC mechanism-design
audience and the NeurIPS multi-agent-learning audience.

---

# Round 1 report (historical) — "The Router Is the Demand Curve" (v1)

*Venue standard: ACM EC / NeurIPS (economics-track). Reviewer instructed to
assess specifically whether the economic results are, or can be made,
theoretically rigorous.*

## Summary

The paper maps a documented marketplace routing rule (selection ∝ p^(−2))
onto a logit oligopoly, characterizes equilibrium (interior formula, a
duopoly knife edge at the documented exponent, an entry-proof Lerner floor
1/a), models the platform's measured penalty on recent price-cutters and
proves a deterrence threshold far above the measured value, and validates a
behaviorally calibrated multi-agent simulation against a live market panel
before running learning counterfactuals (exponent sweep; steering raises
prices 18%; learners never rediscover high-frequency undercutting).

## Assessment of theoretical rigor

**R1 (major). The knife edge is knife-edged in captivity, not just in
(a,n).** Theorem 1(ii)'s ceiling result requires w₀ = 0 *exactly*. With ANY
outside option, s_i → 0 as p_i → ∞ implies h(p) → a > 1, so an interior
best response exists for every n including n = 1, and the ceiling
equilibrium vanishes. The paper measures the end-user elasticity (−0.05)
and even flags it, but does not carry it into the theorem. This is fixable
and, I believe, *strengthens* the paper: with aggregate demand D ∝ P^ε and
inclusive-value index P, the symmetric FOC becomes p/(p−c) =
a(1−1/n) + |ε|/n, giving a finite closed-form duopoly price ≈ 41c at the
measured ε — "41× marginal cost" is a better headline than "the ceiling,"
and it makes the elasticity-wedge measurement a structural parameter of
the theorem rather than color. REQUIRED: state the ε-corrected proposition,
prove it (same single-crossing logic goes through), verify numerically, and
recast the ceiling case as the ε → 0 limit.

**R2 (major). The steering model does not match the steering measurement.**
θ = 0.17 was measured *conditional on being the cheapest quote with a
recent cut*; Theorem 2 applies the penalty to any recent cutter. If the
penalty binds only when cheapest, a deviant can cut to just above the
second-cheapest quote and escape it entirely — the deterrence region could
shrink. REQUIRED: analyze the cheapest-only variant (at minimum
numerically; ideally the same closed-form machinery applies piecewise) and
report whether θ* conclusions survive. Also state clearly that M and the
flag-refresh semantics are modeling choices fitted to a 7-day empirical
window.

**R3 (major). The validation table conflates echoes with tests.** Premium
ladders and cadences are near-mechanical consequences of fitted inputs
(species margins and hazards estimated from the same train window); passing
them is calibration hygiene, not evidence. The genuine out-of-sample
content is: (i) the adopter-atom OOS persistence, (ii) the untargeted flow
elasticity, (iii) arguably dispersion (emergent from the interaction). The
paper's headline "distance 0.019" invites over-reading. REQUIRED: annotate
each moment as fitted-input echo vs emergent, and lead with the emergent
ones. (The untargeted elasticity result is genuinely striking and
under-sold.)

**R4 (moderate). E-SIM4 runs on a stylized world.** The +18% steering
result — the paper's policy payload — is demonstrated in a 5-provider
symmetric-cost toy, not in the calibrated markets the paper spent §4–5
building. REQUIRED for the claim as stated: repeat E-SIM4 on the calibrated
markets (learner in the empirical active-undercutter slot, penalty on/off)
and report the calibrated price effect.

**R5 (moderate). Novelty placement.** Theorem 1's static structure is
Anderson–de Palma–Thisse; the paper now says so, good. But then the
contribution rests on (a) the documented-rule mapping (real, and the
knife-edge placement is a genuinely arresting fact), (b) Theorem 2 (novel
to my knowledge — platform steering as an asymmetric platform-imposed menu
cost that *supports* high prices, inverting Johnson–Rhodes–Wildenbeest),
and (c) the calibrated environment. The introduction should make this
division explicit so the paper isn't read as claiming new oligopoly
theory.

**R6 (minor).** (i) Asymmetric-cost equilibria are not characterized —
acceptable if scoped, but say so in Theorem 1 rather than §8. (ii) Δ =
0.08 ± 0.13 at a = 2 is weak collusion evidence; the paper should not lean
on Calvano Δ — its real result is that the *competitive benchmark itself*
is elevated (Nash at 0.94 with cost 0.2), which is cleaner. (iii) The 8/8
seed unanimity in E-SIM2/4 should be explained (deterministic attractors
under expected-reward training; seed variation enters only through
exploration paths). (iv) Report the patience boundary δ† to two decimals
with its formula, not "0.98–0.99".

## Assessment of the experimental program

Pre-registration with dated addenda, split-sample species, untargeted-
moment gating, deterministic seed manifests, and gate-locked
counterfactuals are above the reproducibility bar for either venue. The
LLM-agent tier is advertised but not run; either run it at confirmatory
tier or move it to future work (do not advertise built-but-unrun
capability in the contributions).

## Verdict

**Major revision.** The four REQUIRED items (R1–R4) are all executable
with the paper's existing machinery, and none looks likely to overturn the
qualitative conclusions — R1 in particular converts the weakest link
(captive demand) into a measured-parameter result. If R1–R4 land with the
signs intact and R5's framing is adopted, this is an accept: the
documented-rule mapping plus the steering theorem plus a validated
calibrated environment is a combination neither the algorithmic-collusion
literature nor the platform-steering literature currently has.
