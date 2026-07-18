# Pre-registration: simulation validation moments (E-SIM1 gate)

*Registered 2026-07-18, before any E-SIM1 run. Code:
`src/orcap/market_env/{calibration,moments}.py`. Companion protocol:
docs/strategic-routing-simulation-execution-plan-2026-07-18.md (WP0 gates,
stop/go rules) — this document supplies its calibration-conformance
thresholds for the species-world validation.*

## Design

Indirect inference: the simulated market (fitted behavioral species ×
inverse-square router × replay demand) is scored by `moments.compute_moments`
— the SAME code that produced the observed targets from the real panel via
`moments.observed_trajectory` (daily grain, author-anchored markets,
standard variant). Calibration (`calibration.fit`) reads ONLY the earliest
60% of panel dates; the bundle records the split.

## Frozen observed targets (computed 2026-07-18, train window)

| Moment | Target | Weight | Notes |
|---|---|---|---|
| dispersion_max_min_ratio | 1.34 | 1 | mean over model-days |
| dispersion_sd_log_price | 0.068 | 1 | |
| adopter_atom_share | 0.834 | 2 | OOS persistence of train-classified adopters (n=409 provider-days) — sim epochs are post-classification, so OOS is the correct analog |
| premium_ladder_below_static | −0.406 | 1 | median log rel to anchor |
| premium_ladder_adopter | 0.0 | 2 | |
| premium_ladder_above | +0.344 | 1 | |
| cadence_adopter | 0.0 /day | 0.5 | daily grain (simulator epoch grain) |
| cadence_below_active | 0.444 /day | 1 | daily grain; ledger grain is 1.14/day — grain documented to prevent apples-to-oranges |
| cadence_below_static | 0.0 /day | 0.5 | |
| cadence_above | 0.02 /day | 0.5 | |
| flow_elasticity | −0.78 | 0 (gate) | see below |

## Pass criteria (E-SIM1)

1. **Fitted moments:** weighted mean squared relative error
   (`moment_distance`) ≤ 0.04 (≈ average 20% relative error at weight 1),
   with NO single weight-2 moment off by more than 35%.
2. **Elasticity gate (not fitted):** no calibration parameter targets flow
   allocation; the simulated flow elasticity must have the SAME SIGN as the
   observed train-window value (−0.78, identical estimator) and lie within
   one order of magnitude of it. Honesty note, recorded before running: the
   temporal-holdout window flips this sign under the same thin spec
   (+0.84 on ~40% of a short panel); the full-panel estimate with better
   controls is −1.15. The gate therefore references the train-window value
   under the identical estimator, and the elasticity claim inherits the
   panel-length caveat until the 30-day vintage re-estimation.
3. **Free parameters:** menu-cost κ, hazard scale, and demand noise σ may be
   tuned ONLY against the fitted-moment distance (coarse grid); tuning
   against the elasticity gate is prohibited.
4. **Seeds:** 20 seeds; pass criteria apply to the cross-seed mean; report
   the cross-seed sd.

## Consequences

- PASS → E-SIM2 (learner substitution), E-SIM3 (router temperature sweep),
  E-SIM4 (cut-penalty counterfactual) are unlocked as pre-specified.
- FAIL → no counterfactual results may be reported; diagnose, amend THIS
  file with a dated addendum stating what changed and why, and re-run.
- Any post-hoc moment addition/removal or threshold change requires a dated
  addendum before the affected run.

## Addendum 2026-07-18 (before the first scored E-SIM1 run)

The first smoke run (3 seeds, 20 epochs, unscored) exposed a definitional
mismatch, corrected before any pass/fail run: the composition-sensitive
targets (dispersion, premium ladder, cadences) were computed on the GLOBAL
panel, while the simulation covers only the 4 calibrated markets. Scoring a
4-market sim against global targets is apples-to-oranges. Correction —
mechanical, not threshold-motivated: targets are now computed by
`moments.conditional_targets` on the SAME market universe (train window,
identical code); the adopter-atom target keeps its global OOS value (a
within-pair property, composition-robust); the simulator's exogenous
anchor-walk hazard is set to the OBSERVED author daily repricing cadence in
those markets rather than the adopter ledger cadence. Thresholds (0.04
distance, 35% weight-2 cap, elasticity sign/order gates) are UNCHANGED. The
smoke run's diagnostic values are recorded in
output/market_env/esim1/fc402118b0 and it does not count as a scored run.
