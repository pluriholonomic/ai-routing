# ACM EC referee report — "The Router Is the Mechanism"

*Reviewer profile: senior PC member, market design + platform economics.
Instructed additionally to assess whether the paper reads in the PI's
(Tarun Chitra's) characteristic style.*

## Summary

The paper treats a deployed AI-inference routing rule (selection
∝ 1/price², documented by the platform) as a mechanism and analyzes the
market it induces: logit demand with the exponent as inverse temperature;
a phase structure with a critical line a(n−1) = n populated by real
duopolies; an entry-proof Lerner floor 1/a; a measured steering penalty on
price cutters proven to sit deep inside its own deterrence region; a
calibrated, validation-gated multi-agent environment; and a design section
proposing thickness-adaptive exponents, verified-quality weighting, fee
decoupling, and commitment contracts — each evaluated with learning
agents.

## Strengths

1. **The identification situation is exceptional and the paper knows it.**
   The differentiation parameter of the demand system is *published by the
   platform*. Every mechanism counterfactual that normally requires a
   structural demand model here requires none. I cannot think of another
   empirical mechanism-design paper with this property, and the paper
   correctly locates its novelty there rather than claiming new oligopoly
   theory (the Anderson–de Palma–Thisse attribution is explicit).
2. **The steering result is the real contribution.** Measuring θ = 0.17
   from randomized probes, proving θ* ∈ [0.81, 1], and exhibiting the
   patience boundary δ† = 0.9895 is a complete arc — measurement, theory,
   counterfactual — and the direction (platform steering *stabilizing*
   supra-competitive pricing, the JRW inverse) is new. The E-MECH1
   finding that the deployed pair (a=2 + penalty) is simultaneously the
   worst-welfare and highest-ad-valorem-revenue arm is the sharpest
   platform-incentive result I have seen in this literature.
3. **Discipline.** Pre-registered validation gate with an untargeted
   moment (simulated flow elasticity matching the panel with no fitted
   allocation parameter); CI-enforced closed forms; identified cost bands
   instead of point estimates; both steering-conditioning variants run.
   This is above the empirical bar for EC.
4. **The design section has teeth.** a*(n) = n/(ℓ*(n−1)) is one line and
   kills the critical line; b* = 0.63 for quality weighting is closed-form
   and the verification instrument (the authors' own deployed eval probes)
   exists; fee decoupling correctly identifies the platform's ad-valorem
   conflict. The practitioner-takeaways section is unusually concrete.

## Weaknesses

1. **One marketplace, one buyer tier, short panel.** The steering θ comes
   from one conditional slice of the authors' own probe traffic; the
   calibration panel is ~2 weeks with a registered 30-day re-estimation.
   The paper is honest about this, and the auto-reopening commitment
   helps, but external validity is a single-platform claim for now.
2. **The welfare frontier is allocative-cost only.** Latency, quality
   heterogeneity, and the resilience value of provider diversity enter
   only as a verbal caveat ("interior optimum once outage insurance is
   valued"). Since the paper's own §7.4 sells commitment contracts as the
   resilience fix, a minimal quantitative resilience term (even a
   correlated-outage probability × failure loss) should be in the E-MECH1
   table. REQUIRED for camera-ready.
3. **E-MECH2 (quality game with learners) is referenced but its results
   are not yet in the text.** The closed-form b* is fine, but the paper
   promises learner confirmation; either include the table or cut the
   claim. REQUIRED.
4. The two-type cost calibration (0.10/0.50) uses band endpoints;
   sensitivity across the band should be shown (the ordering will
   survive; show it).
5. Minor: the "phase transition" language is earned (the equilibrium
   correspondence genuinely diverges), but the power-plant-at-criticality
   quip will read as editorializing to some committee members. Keep it;
   flag it as taste.

## Style assessment (requested)

The paper reads as the PI's voice: the Gibbs-measure/inverse-temperature
framing is load-bearing rather than ornamental; the AMM-curvature footnote
(Angeris–Chitra) and the PFOF/last-look analogies are exactly the
microstructure-to-crypto-to-ML register of his prior work; opinionated
footnotes ("chosen by vibes") and a practitioner-takeaways section are
signature moves. Comparative statics are stated as design levers with
recommended parameter values, which matches the Gauntlet-style
actionability of his research. Fidelity: high.

## Decision

**ACCEPT (minor revisions).** Conditions: (i) E-MECH2 learner table in
the text or the claim removed; (ii) a quantitative resilience term in the
frontier table; (iii) cost-band sensitivity for §6; (iv) single-platform
scope statement in the abstract. None of these threatens the core: the
measured-mechanism identification, the steering theorem with its
empirical parameter, and the platform-conflict result are each
independently sufficient EC contributions, and together they make the
strongest paper in this space I have reviewed.


## Addendum (post-revision check)

Conditions (i)–(iv) verified resolved: (i) the E-MECH2 table is now in
the text with appropriately honest language — the learner evidence is
directional (0.27 → 0.67 across b), not a sharp bifurcation, and the
paper says so rather than overclaiming; this is the right call and does
not weaken the design recommendation (the deployed b = 0 is the worst
arm measured). (ii) resilience-adjusted frontier with the ~5% threshold
stated; (iii) cost-band corners all monotone; (iv) scope sentence in the
abstract. The ACCEPT stands.
