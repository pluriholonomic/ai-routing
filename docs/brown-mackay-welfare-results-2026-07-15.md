# Brown-MacKay and welfare-validation results — 2026-07-15

## Bottom line

The data contain a statistically resolved *cadence price gradient*, but not the
reaction pattern needed to select Brown-MacKay as the mechanism. Fast
repricers quote about 9.2% less within model-day, equivalent to a 10.1%
slow-over-fast premium. However, fast providers do not move more after slow
rivals than in the equal pre-event placebo window. Brown-MacKay therefore
remains a power-gated competitive null, not a causal conclusion.

The C1-C10 welfare conjunction is not satisfied in the observable study
domain: five conditions are unidentified, three are only approximately
consistent, C7 retry internalization is inconsistent with the market contract,
and C8 fidelity monitoring is power-gated. This is not an estimate of global
welfare loss.

## Authoritative data freeze

- 2,062,359 endpoint-snapshot rows, 1,684 runs, 9 days.
- 3,191 all-field price-change rows; 274 positive completion-price changes
  used by Brown-MacKay, spanning 7.53 days.
- 377,382 public routing-simulation rows over 6 days.
- 744 raw owned-route records; 616 unique source/event attempts; 534 with an
  observed selected provider.
- No registered H50 manifest/assignment, capacity commitment/outcome, router
  flow aggregate, decision-event experiment, or H54 audit-assignment table.

## Brown-MacKay sequence

| Test | Result | Verdict |
|---|---|---|
| BM1 pricing technology | 69 quoting providers; 19 repriced; 50 had no observed update; 10 intraday, 6 daily, 3 weekly | 7.53/30 days; inactive means left-censored, not proven slow |
| BM2 reactions | 115 independent waves, 1,324 risk pairs; fast-after-slow n=15, post 6.7%, pre-placebo 13.3%, uplift -6.7 pp, bootstrap CI [-20, 0] pp | wrong sign and 15/30 focal pairs; power-gated |
| BM3 cadence premium | cadence-only beta -0.0964, clustered SE 0.0281, CI [-0.1515, -0.0413], 5,501 observations/127 models; slow-over-fast premium 10.1% | statistically resolved association, not causal |
| BM3 quality-complete | beta -0.3818, SE 0.1323, CI [-0.6410, -0.1226], 423 observations/23 models; premium 46.5% | selected-subsample upper sensitivity; not the headline causal estimate |
| BM4 reaction rule | MAE 0.1499 to 0.1439, but RMSE 0.2478 to 0.2485 after cadence/reaction features | mixed predictive evidence |
| BM5 hazard horse race | state-only log loss 0.0865/AUC 0.617; strategic 0.0801/AUC 0.594 | log loss improves, discrimination worsens; joint BM gate fails |

The 10.1% cadence-only premium is close to the Brown-MacKay daily-versus-fast
retail benchmark, but numerical similarity is not identification. The live
window mechanically labels providers without a recent move as inactive, and
technology adoption, costs, fidelity, and private discounts remain endogenous.

## Other pricing-model evidence

- PM1's daily repricing hazard improves from the state-dependent L3 model to
  strategic L5 in sample (LR p=0.00177), but the panel is only 9/30 days and
  has 110 daily events.
- PM6 classifies 42.1% of cuts as punish-and-revert and 41.1% as
  initiator-withdrawn. This near tie makes punishment language unsafe without
  a regime model and causal counterfactual.
- PM5 finds 47.4% of non-minimum observations exactly tied at the minimum;
  71.4% of single-mover ties form by downward moves and 86.8% break by a
  downward move. That is more competitive than a simple upward-restoration
  story, despite strong author-price focality.
- Collusion, literal front-running, and common pricing delegation remain
  unidentified.

## Routing and owned-probe evidence

The updated public share-price elasticity is -1.0103 (SE 0.0984), which differs
from -2 by z=10.06. This rejects equality with the advertised inverse-square
proxy on the public token-allocation panel; it does **not** reveal the realized
default-router selection rule.

Owned probes are useful but not randomized:

| Policy | Attempts | Success | Mean cost | Mean latency |
|---|---:|---:|---:|---:|
| OpenRouter default | 328 | 98.8% | $0.0000305 | 1,178 ms |
| Pinned cheapest | 96 | 80.2% | $0.0000106 | 1,347 ms |
| Pinned random | 96 | 76.0% | $0.0000188 | 1,284 ms |
| Pinned second | 96 | 66.7% | $0.0000083 | 2,289 ms |

These contrasts strongly motivate H50, but workload, model, provider, and time
composition can explain them. No causal policy or welfare claim is permitted
until the manifest and randomized model-epoch assignments exist.

## Welfare and regret screens

The cadence-neutral sensitivity has two deliberately separate estimates:

- cadence-only coefficient: weighted price -7.03%, demand +0.37% to +0.51%,
  spend -6.69% to -6.55%; provider surplus varies from roughly -7% to -70%
  across the assumed cost ratios;
- quality-complete coefficient: weighted price about -25.2% and spend about
  -24%, treated only as a selected-subsample upper sensitivity.

Neither is structural Bertrand welfare. User value, fidelity losses, retry and
delay externalities, private costs, transfers, and capacity response are absent.

The calibrated one-shot provider-regret screen has median normalized regret
104%; only 12.8% of provider/cost scenarios are within 5% of the fitted best
response. Token-weighted user price-only regret is 19.9%. These large values
reject the fitted isoelastic one-shot model as an equilibrium description more
readily than they diagnose collusion; misspecified allocation, unobserved
quality/cost, capacity constraints, and private discounts are all live
alternatives.

## Remaining promotion gates

- Brown-MacKay: 30 panel days (7.53 now) and at least 30 fast-after-slow risk
  pairs (15 now). The 80-wave gate is cleared.
- Public quote pulse: 193 hours clears the 168-hour span gate; 48/80
  independent cut episodes remain.
- Realized routing: 534/2,000 unique selected-provider attempts and 0/1,000
  quote-linked attempts.
- Causal routing: zero H50 manifests, assignments, or randomized effects.
- Capacity: zero commitments, cost curves, or epoch outcomes.
- Fidelity: zero H54 registered audit assignments or certificates.
- Pre-selection/front-running experiment: zero visible, blinded, or decoy
  decision events (target 200 per arm).

The executable report is `analysis/welfare_validation_panel.html`; the final
machine-readable verdict is `analysis/welfare_conjecture_verdict.json`.
