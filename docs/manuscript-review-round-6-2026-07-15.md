# Independent-style review, round 6

Manuscript: *Displayed Is Not Deliverable: Capacity Certificates and Quote
Firmness in Inference Routing*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **5/10, borderline reject; invite resubmission after the
prospective experiment.**

## Summary

The paper studies provider-level inference routing when public prices do not
certify request-level execution. It combines: (i) capacity-capped score
routing and a max-min outage allocation; (ii) a restricted finite-slot
VCG-plus-audit mechanism for capacity, cost, and reliability reports; and (iii)
a micro-probe measurement design comparing delegated default routing with
three provider-pinned policies. A 24-hour pilot contains 96 matched four-policy
blocks. Default succeeds substantially more often, but always runs first. The
authors therefore preregister and deploy a random-order first-position design.

The problem is timely and the displayed-versus-deliverable distinction is
valuable. The paper is unusually disciplined about claim boundaries. In its
current form, however, the most novel empirical claim is not yet causally
identified, while the identified experimental theorem is a standard
Horvitz--Thompson argument. The mechanism and the live experiment also test
different policy contrasts. I would not accept the current version at a top
venue, but a completed prospective result could change the recommendation.

## Strengths

1. **A sharp market object.** Provider-level execution eligibility is distinct
   from model selection, public price measurement, and conventional API
   benchmarking. The paper articulates this distinction clearly.
2. **Credible negative evidence.** The Brown--MacKay screen does not turn 274
   sparse price changes into a claim of algorithmic response or collusion. The
   failed reaction-rule gate is informative and honestly reported.
3. **A meaningful pilot fact.** The 17.7--31.3 percentage-point success gaps are
   large, matched within tens of seconds, and robust to hourly clustering. Even
   without causal status, they show that a public provider quote is not a firm
   offer for this account and workload.
4. **Good experimental instinct.** Using only randomized first-position
   attempts is a clean way to survive arbitrary within-block carryover. Logged
   seeds and probabilities make the assignment auditable.
5. **Formal restraint.** The paper states that observed spend is not provider
   cost, the pilot is not market-wide welfare, and neither probe data nor quote
   reactions establish front-running.

## Major concerns

### 1. The prospective result is not yet present

The pilot has perfect default/order confounding and changes fallback rights at
the same time as provider selection. The confidence intervals establish a
descriptive gap, not a policy effect. The randomized v2 design is the correct
repair, but a running experiment is not a result. At minimum, the paper needs
the preregistered first cut: 40 first-position observations per policy and 160
valid blocks, with the assignment audit, exact or design-based inference, and
the prespecified multiplicity correction.

### 2. Mechanism and experiment do not yet meet

The mechanism compares capacity-certified allocation with uncapped score
routing. The live experiment compares OpenRouter default routing with pinned
public quotes. No observed policy uses certified commitments, the robust LP,
collateral, audits, or VCG transfers. Consequently, the experiment validates
the motivation for the price-only separation theorem, not the proposed
mechanism's welfare or delivery advantage. The paper must either make this a
measurement paper with the mechanism as a design implication, or implement a
controlled capacity/reliability policy contrast. At present it is a strong
motivation attached to an untested mechanism.

### 3. The main identification theorem is methodologically standard

First-position inverse-probability estimation under random permutation is
correct and useful here, but not a new experimental-design theorem. The
novelty must rest on the market measurement and its empirical result. The
paper should avoid presenting the Horvitz--Thompson calculation as the primary
technical novelty and instead explain how hidden eligibility changes the
economic interpretation of public quotes and provider competition.

### 4. Support is narrow

The pilot covers four hot models, one API account, a deterministic one-token
`pong` request, and one day. It measures admission and fallback value, not
content quality. The prospective study should report model-specific effects,
time stability, provider-rank heterogeneity, and whether the effect survives
excluding account-level 429s. Any extrapolation beyond the study support
would be premature.

### 5. Cost and welfare need missingness discipline

The reported cheapest/default threshold mixes a 96-block success contrast with
94 complete-accounting cost pairs. This is acceptable as a descriptive
secondary statistic only if the missing accounting rate and bounds are shown.
For v2, the primary success ITT is clean; spend, latency, and selected-provider
analyses need explicit missing-data rules. The full value frontier is not
social welfare because output quality and provider production cost are absent.

### 6. Theory contribution is restricted and partly assembled from standard tools

The capped water-fill, robust LP dominance, VCG pivot argument, and proper
score are individually standard. The finite-liability boundary and their
composition are useful, but the finite report grid, external subsidy, sentinel
collateral, objective audit, and opt-out assumptions do substantial work. I
would accept this package as a focused restricted mechanism paper only if the
authors establish a sharper connection to a new inference-market constraint or
prove a nontrivial optimality/approximation result beyond feasibility.

## Required revision for a plausible accept

1. Freeze and report the first v2 cut at the preregistered sample gate.
2. Verify every seed and position, show arm balance and order entropy, and
   retain all first-position failures as ITT outcomes.
3. Report model-stratified estimates, randomization p-values, 95% intervals,
   and Holm-adjusted inference for the three default-versus-pinned contrasts.
4. Use later positions only to test carryover/order effects; do not combine
   them with position zero unless a carryover model is prespecified.
5. Give missingness rates and worst-case or transparent complete-accounting
   bounds for cost, latency, and selected-provider fields.
6. Reconcile the paper's center: either add a controlled capacity-certified
   policy experiment, or narrow the contribution to quote firmness and hidden
   eligibility while moving the full mechanism to a companion paper.
7. Position the empirical discovery—not the generic HT identity—as the novelty,
   and compare directly with opaque-service markets, supply uncertainty, and
   marketplace interference designs.

## Correctness and reproducibility

I found no fatal error in the formal statements under their printed
assumptions. The value-frontier identity and rescue decomposition are correct.
The paper's audit-scale result remains conditional on the finite type space and
external funding. The repository has executable analysis, a prospective
protocol, auditable random seeds, generated figures, and passing tests. These
are substantial positives, but they do not substitute for the missing
prospective sample.

## Decision

**Borderline reject at present.** The manuscript is much closer to a top-venue
paper than the earlier public-shadow work, but acceptance should depend on the
randomized result and on a tighter link between that result and the mechanism.
The next review should be triggered by the preregistered v2 cut, not by further
rhetorical revision of the fixed-order pilot.
