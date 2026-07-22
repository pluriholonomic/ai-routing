# Red-team review: GLM-5.2 market-share HMP validation

Date: 2026-07-22 UTC.

## Verdict

The prospective infrastructure is fit to begin collection after remote CI
validation. It does **not** yet justify an empirical HMP, algorithmic-collusion,
market-wide-share, provider-cost, or welfare claim. The only affirmative result
currently justified is the exact path-elasticity identity for the declared
inverse-power/softmax rule. The reduced one-seed simulation is a diagnostic and
is mixed, so it is not evidence for the mechanism.

This is the right stopping point for inference: deploy the fixed design, accrue
the fixed horizon, and do not open outcomes early.

## Claim ledger

| Claim | Required evidence | Evidence now | Verdict | Permitted language |
|---|---|---|---|---|
| MS1 exact path identity | Algebra plus numerical property tests | Singleton wedge is exactly zero; multi-cutter wedge increases with other-cutter share in the declared rule | Passed | The wedge is an exact property of the declared routing rule. |
| MS2 public multiplicity | 28 days; 30 clean events in every multiplicity stratum; clustered/placebo analysis | Prospective count is zero at implementation time | Not tested | No live public multiplicity claim. |
| MS3 owned routing | 800 covered choices per stratum; exact menus/integrity; randomized-menu analysis | Prospective count is zero | Not tested | No realized routing or causal price claim. |
| MS4 passive incidence | MS1--MS3 plus active/anchor displacement and buyer outcomes | No released outcomes | Not tested | No incidence or welfare claim. |
| MS5 temporal memory | MS1--MS4 plus frozen lags, future leads, clock shifts, and concentration audit | No released outcomes | Not tested | No live memory or critical-memory claim. |
| MS6 mechanism transport | Prior empirical chain plus calibrated paired simulations and held-out threshold improvement | Reduced simulation only; empirical chain false by construction | Not promoted | Simulation is a mechanism screen only. |

## Why MS1 is justified

For `s_i = exp(-eta x_i + a_i) / sum_j exp(-eta x_j + a_j)`, and a set `C`
whose log prices move along one path, differentiation gives

`-d log(s_i) / d x_C = (1 - S_C)(eta - h'_C)`.

For a unilateral move it is `(1 - s_i)(eta - h'_i)`. Under the declared
price-only rule, `h'=0`, so the unilateral-minus-path wedge is
`eta(S_C-s_i)`. It is exactly zero when `C={i}`. The implementation tests both
the local identity and finite changes, validates probability conservation, and
runs the singleton negative control for every simulated learner family. This
does not establish that OpenRouter uses the declared exponent without a score,
nor that the rule describes realized market-wide allocation.

## Diagnostic simulation result and non-result

The reduced run used one seed and a 400-period horizon. It generated 1,800
world rows and 900 coupled/shuffled pairs across the expanded memory grid.
The exact singleton wedge passed and the declared-rule group wedge was
monotone. For UCB agents, coupled-minus-shuffled censored learning time averaged
`-13.66` periods, but the fraction reaching the target was `0.550` in the
coupled arm and `0.556` in the shuffled arm. Heterogeneous learners had a
`-15.04` period difference and completion rates `0.557` versus `0.493`.

Those signs are not a coherent confirmatory result: one seed gives no sampling
uncertainty, the UCB completion-rate ordering runs against a simple positive
story, and the critical-memory comparison correctly reports insufficient seed
support. No mechanism claim follows. The scheduled full run uses ten paired
seeds and evaluates a threshold/hinge model selected on training seeds against a
smooth memory curve on held-out seeds, including the `K=1` negative control.

## Design failures found and corrected before deployment

1. **No event-time measurement.** The initial detector waited for the 15-minute
   co-move window before registering an event. It could not produce the first
   post-detection wave. The ledger is now staged: a provisional immutable event can
   create only `m0`; multiplicity-final events create `m15`; final-clean events
   create later waves.
2. **Incomplete contamination screen.** The first implementation checked only
   the focal transition. The final gate now observes 60 minutes and checks all
   provider-set, author-price, endpoint-health, snapshot-gap, public derank,
   rate-limit, derankable-error, and capacity-ceiling transitions.
3. **Spurious cuts.** A decline previously qualified without two prior
   unchanged captures. That frozen precondition is now enforced and tested.
4. **Overlapping cut double counting.** Multiple cuts inside one co-move window
   previously could become one pair event and a singleton. Clustering now keeps
   the earliest qualifying focal cut and treats later cuts as co-cutters.
5. **Plan/execute race.** Job-level locking could allow two workflows to freeze
   the same due wave. One workflow-level non-cancelling queue now serializes
   detection, assignment upload, and execution.
6. **Lost reservations after failure.** A workflow that failed after a paid call
   could disappear from success-only artifact assembly. Both rolling overlay and
   nightly compaction now ingest every HMP run status; an uploaded assignment is
   an at-most-once reservation.
7. **Conditional-on-success learning time.** Averaging learning time only among
   converged cells selected on the outcome. Non-convergence is now right-censored
   at horizon plus one, and completion rates are reported separately.
8. **Ineffective Q-learning memory.** The original update did not make the
   declared memory parameter control learning. Q updates now use step size
   `1-memory`.
9. **Stylized price scale presented too strongly.** The full simulation now
   calibrates active-to-anchor relative prices from an immutable public GLM-5.2
   snapshot revision. Serving cost remains an explicit scenario at 25% of the
   low quote; it is not an estimate.
10. **Early outcome leakage.** The first monitor exposed arm and event outcome
    aggregates while counts accrued. It now publishes support and integrity
    only; all selection, cost, latency, fallback, and event response fields are
    null until the complete frozen gate passes. CI tests this invariant.
11. **Weak threshold test.** Three memory points could not support a credible
    critical-memory comparison. The fixed grid now has five points, and the full
    run selects a hinge on training seeds and scores it against a smooth curve on
    held-out seeds. This remains a simulation comparison, not proof of a phase
    transition.

## Remaining threats that cannot be engineered away

### Identification

- Natural provider repricing is endogenous. Public event studies are
  descriptive after controls and clock-shift placebos; they do not identify the
  causal effect of choosing to cut.
- `m0` is the first post-detection wave, not a pre-cut baseline. The new
  HMP-specific hourly background panel supplies a strictly prior measurement,
  but its distance to the cut can approach one hour and focal menus rotate.
  Pre/post price response remains observational; the randomized-menu contrast
  is causal only for eligible-menu composition.
- Randomized allowlists identify the effect of the project's eligible menu on
  the project's requests. They do not identify cross-user OpenRouter flow.
- OpenRouter's private eligibility and score are unobserved. Broad default
  versus explicit price sorting estimates a residual routing-score wedge; it
  does not identify its quality, capacity, or contractual components.
- Provider costs, objectives, learning rules, communications, and intent remain
  unobserved. No empirical output can be called collusion.

### Sampling and transport

- GLM-5.2 is one model market. A positive result does not automatically
  transport to Kimi, free models, closed models, or another router.
- Historical activity is concentrated in Novita and StreamLake. The 20%
  concentration and ten-pair gates may fail. If so, the result is a pair case
  study, even with a small conventional p-value.
- At-most-once reservation trades duplicate-spend bias for missingness after a
  crash. Assignment-to-attempt integrity exposes the loss and blocks release;
  it cannot recover the counterfactual outcome.
- Thirty events and 800 choices per stratum are minima, not a promise of power.
  Event clustering may require a larger count from the blinded pilot variance
  calculation.
- Free endpoints are excluded from paid inference and require their own market;
  they cannot be assigned an infinitesimal price in the elasticity regression.

### Simulation

- The intervention preserves each provider's marginal **exogenous shock**
  sequence while breaking common time ordering. It does not preserve realized
  rewards after agent actions diverge. Any paper language saying it preserves
  full endogenous reward paths would be false.
- Agents have two price actions, a stylized demand process, scenario costs, and
  simplified quality/capacity. They are mechanism probes, not fitted replicas
  of named providers.
- The elasticity learning time is an observer-side recovery statistic, not
  proof that a provider internally estimates that elasticity.
- A held-out hinge improvement supports a sharp simulation nonlinearity only.
  A live critical-memory claim still requires MS2--MS5 and must disappear or
  move in the shuffled and singleton controls.

## Operational invariants checked

- Assignment artifact is uploaded and manifest-validated before any request.
- The paid worker uses the dedicated OpenRouter experiment key and fails closed
  on study, daily, run, and campaign caps.
- Every task has one immutable protocol hash and deterministic event/wave/arm
  key.
- Failed workflow artifacts preserve reservations.
- Public monitors contain no prompt, message, response, request reference, task
  ID, or secret fields.
- Before the gate, outcome columns in aggregate Parquet and inline HTML are
  null.
- Local audit: scoped ruff and shell syntax checks passed; the repository suite
  passed 853 tests with one pre-existing skip.

## Manuscript boundary

Until the fixed gate opens, the EC paper may include the exact identity, the
experimental design, and a statement that collection is prospective. It may
not describe the reduced simulation as confirmation, label any provider as
collusive, infer dumping costs, report hidden interim arm rankings, or claim a
market-wide welfare effect. After release, every sentence must map to the claim
ledger row and must report the relevant support, interval, falsification, and
concentration result in the same section.
