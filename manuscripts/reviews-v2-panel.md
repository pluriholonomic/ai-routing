# Additional referee reports — v2 (independent personas)

*Commissioned after the author-reviewer's ACCEPT was challenged as
structurally biased. Two further reports, different priors.*

## Referee B (empirical econometrician)

**B1 — FATAL for Fact 3 as written: the probe design confounds policy with
order.** The v1 probe protocol always sends the default-policy request
first, then pinned cheapest, second, random — in that order, within the same
model-hour block, on the same API key. The policy x within-block-position
cross-tabulation is near-degenerate (default at position 0, cheapest at 1,
second at 2, random at 3). Any within-block rate-limit accumulation from the
authors' own earlier requests loads directly onto later policies. Therefore:
(i) the "anti-last-look" gradient (cheapest 80% / second 67% / random 76%)
is unidentified — position 2 rejecting most is equally consistent with a
burst limiter; (ii) the pinned rejection LEVELS are upper bounds
contaminated by self-inflicted throttling; (iii) only two probe statistics
survive: the default-policy selection shares (position 0, uncontaminated)
and the existence of nonzero pinned rejection. The steering audit (Section
6) survives because it uses only position-0 selections; Fact 3's
request-level paragraph does not. The authors' own infrastructure has
apparently already moved to a randomized crossover with first-position
estimands — the paper must wait for that data or drop the gradient claim.

**B2 — Process.** A single author-supplied review recommending acceptance is
not peer review. This report exists because the process was challenged;
venues should treat the v2 "accept" as void.

**B3 — Panel length, again, harder.** With Fact 3's request-level evidence
reduced by B1, the paper leans more on the 11-day quote panel. The tie null
and anchor levels are cross-sectionally solid; the hazard ladder's OOS story
(0.64, gap channel only) is honest but thin. I would require the re-run on
the accrued panel BEFORE acceptance, not at camera-ready.

**Recommendation: REJECT in current form; encourage resubmission with the
randomized-crossover probe data and a >=60-day panel.**

## Referee C (OR / stochastic systems)

**C1 — Retry IV exclusion.** The capacity-spillover instrument shifts
rate-limiting via the provider's OTHER models; users observing provider-wide
throttling plausibly REROUTE (cross-provider substitution) rather than retry
the same endpoint. The IV then estimates a local effect that mechanically
excludes the relevant margin; the tight null bound may reflect the
instrument, not the externality. The registered incident-window design is
better; until then the paper correctly demotes the result, but the abstract
should not cite the IV bound as if it bounds the externality generally.

**C2 — Horizon consistency.** The paper measures H = 0.835 (multi-scale
counts) for the entry remark but H ~ 0.36 (deseasonalized 30-min) elsewhere,
and uses LRD delay scaling W ~ (1-rho)^{-5.25} in the welfare discussion.
Pick a horizon per application and defend it; as written, H is whichever
value fits the sentence.

**C3 — Tie null: acceptable and, as constructed, conservative in the
authors' favor on one axis (the deviation pool includes the tie atom, so
the null re-manufactures some ties) but the snapping rule assumes the cent
grid globally; report sensitivity to the dime grid where quotes are coarser.**

**Recommendation: MAJOR REVISION. The measurement core (Facts 1-2, steering
audit) is publishable; Fact 3 must be rebuilt on the crossover design;
retry/entry framing needs the discipline in C1-C2.**

## Meta-decision

Two of three referees do not accept. The v2 "accept" is set aside. Required
for resubmission: (1) randomized-crossover probe data with first-position
estimands replacing all v1 pinned statistics; (2) panel re-estimation at
>=60 days; (3) horizon-consistent H usage; (4) abstract rewritten to the
surviving claims. Items (1) and (2) are on automatic accrual; the
resubmission gate is calendar time plus the registered analyses — no new
degrees of freedom.
