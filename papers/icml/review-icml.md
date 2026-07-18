# ICML review — "Phase Transitions in Price-Weighted Routing Games"

*Reviewer profile: senior reviewer, learning theory / learning in games.
Scores per ICML rubric. Additionally instructed to assess whether the
paper reads in the PI's (Tarun Chitra's) characteristic style.*

## Summary

Independent tabular Q-learning is studied across a one-parameter family
of softmax-routing pricing games whose equilibrium correspondence has an
exact critical line (a(n−1) = n), with the deployed marketplace parameter
sitting on it for duopolies. Headline observations: learned prices are a
smooth decreasing function of the exponent that undershoots divergent
equilibria near criticality (vanishing profit gradient) and overshoots
interior Nash in the disciplined phase (Δ up to 0.47); a measured
history-dependent penalty on price cuts acts as non-potential reward
shaping that flips learners to the price ceiling; learners fail to
discover high-frequency undercutting and form focal ties endogenously.
Mechanism variants are evaluated with learners.

## Strengths

1. The game family is a well-chosen laboratory: deployed, documented,
   one-parameter, with exact theory to compare against (13 CI-tested
   closed forms), and the environment is validation-gated against a live
   market including an untargeted moment. As experimental methodology in
   learning-in-games, this is genuinely strong.
2. The undershoot/overshoot sign pattern around criticality (§4.2) is a
   nice, apparently novel observation with a clean mechanistic account
   (drift ∝ 1 − h(p) vanishing relative to exploration noise), and it has
   a general moral: equilibrium-correspondence analysis mispredicts
   learned play in both directions near singular parameters.
3. The steering-as-reward-shaping section connects a measured platform
   parameter to a learnability statement (the trap-state argument via
   δ^M ≪ δ†) — a concrete instance of mechanism-induced shaping "in the
   wild."

## Weaknesses (these determine my score)

1. **The paper's central claim is a learning-dynamics claim, and there is
   no learning-dynamics theory in it.** §4.2's regularization result is
   an empirical observation plus a heuristic gradient argument. For ICML,
   I expect at least one of: (i) a stochastic-approximation / ODE
   analysis of (smoothed) Q-dynamics near the critical manifold, showing
   the invariant distribution concentrates at finite prices with a rate
   in the gradient scale; (ii) a replicator or QRE-homotopy analysis
   making the "smooth dial" prediction formal (the observed curve looks
   like a logit-QRE branch — the paper even notes this — but the
   connection is left as a remark); or (iii) a finite-time bound showing
   the ceiling is unreachable in polynomial time near criticality. As
   written, the distinctively-ICML contribution is under-theorized
   relative to the venue's bar.
2. **One algorithm, one hyperparameter suite.** The claims are about
   "learning dynamics," but only ε-greedy tabular Q at Calvano's
   constants is run. The undershoot mechanism (exploration noise vs
   vanishing drift) predicts specific hyperparameter dependence
   (undershoot magnitude should scale with exploration decay rate and
   grid resolution) — this is testable and untested. Optimistic
   initialization, UCB-style exploration, and a policy-gradient method
   could each plausibly change the criticality behavior; the paper's own
   citations (Deng et al.) say deep RL differs.
3. **Substantial overlap with the companion submissions.** §§2–3 and half
   of §5 are shared infrastructure with the EC and NeurIPS papers; the
   ICML-specific delta is §4.2 plus reframing. Under concurrent-
   submission norms this needs restructuring: the ICML paper should
   *center* the dynamics analysis (theory + sweeps) and compress the
   shared material to a background section.
4. E-MECH2's learner table is promised, not shown.

## Ratings

- Soundness: 3/4 (claims are true as scoped, but the scope is narrower
  than the framing).
- Presentation: 3/4.
- Contribution: 2.5/4 for ICML specifically (the strongest results
  belong to, and are better framed by, the EC/NeurIPS versions).
- **Overall: 5 (Weak Reject / major revision).** Confidence: 4.

## What would make this an accept

Concretely: (a) a formal result for §4.2 — the natural target is a
two-timescale stochastic-approximation theorem: for the smoothed
best-response (logit-response) dynamics on the symmetric slice, show the
rest point moves continuously through the critical parameter and derive
the O(ε/(1−h)) displacement scaling the experiments suggest; (b) the
hyperparameter/algorithm sweep of weakness 2, confirming or refuting the
predicted scaling; (c) restructure to make the dynamics the paper. With
(a)–(c) this is a clear accept: the phenomenon is real, novel, and
well-instrumented; the paper just hasn't yet done the ICML-shaped work on
it.

## Style assessment (requested)

Moderate fidelity. The physics framing is present and earned, but the
prose is noticeably more restrained than the PI's characteristic register
— fewer of the practitioner asides, no opinionated footnotes, and the
market-microstructure analogies that anchor his style are largely absent
(they live in the EC version). If the intent is a uniform authorial
voice across the trilogy, this one reads as the outlier; ironically its
sober tone fits ICML conventions best.
