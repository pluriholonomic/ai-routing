# Red-team review: GLM-5.2 market-share HMP validation

Date: 2026-07-22 UTC.

## Verdict

The prospective infrastructure is fit to collect after remote CI validation.
It does **not** yet justify an empirical HMP, algorithmic-collusion,
market-wide-share, provider-cost, or welfare claim. The only affirmative result
currently justified is the exact path-elasticity identity for the declared
inverse-power/softmax rule. The full ten-seed simulation rejects the proposed
sharp critical-memory screen and gives mixed learner-specific effects; it does
not validate the mechanism.

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
| MS6 mechanism transport | Prior empirical chain plus calibrated paired simulations and held-out threshold improvement | Full paired simulation; threshold loses on held-out seeds; prior live chain not open | Failed screen; not promoted | Simulation is a negative/mixed mechanism screen only. |

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

## Full simulation result and non-result

The first full remote run used the frozen 2,500-period horizon, ten paired
seeds, four learner families, five active-provider counts, five memory values,
three signal-to-noise values, and three router exponents. It produced 18,000
world rows and 9,000 unique coupled/shuffled pairs. Public GLM-5.2 quotes from
3,223 pre-cutoff snapshots calibrated the median active-to-anchor price ratio to
`0.6930`; the cost at 25% of that quote remains a scenario. Missing values are
confined to the two uncensored learning-time fields when a learner did not hit
the target; all comparisons use the frozen horizon-plus-one censoring rule.

The preregistered sharp-memory prediction failed. A hinge selected on seeds
0--5 at memory `0.95` had held-out MSE `0.112694`, versus `0.112626` for the
smooth curve (ratio `1.00060`). The singleton control also did not improve
(ratio `1.00041`). There is therefore no simulated critical-memory result.

Equal-cell estimates below first average within each seed and use a two-sided
95% t interval across the ten seed clusters. These secondary intervals are not
familywise-adjusted across learner families and outcomes, so exclusion of zero
is descriptive rather than a separately confirmed hypothesis:

| Population, coupled minus shuffled | Estimate | 95% interval | Interpretation |
|---|---:|---:|---|
| All multiple-active learners, censored learning time | `+3.12` periods | `[-60.53, 66.77]` | No average learning-speed effect. |
| All multiple-active learners, target-hit probability | `-0.0018` | `[-0.0232, 0.0196]` | No completion-rate effect. |
| UCB, censored learning time | `-34.03` periods | `[-121.53, 53.46]` | Faster point estimate, unresolved. |
| UCB, target-hit probability | `+0.0144` | `[-0.0181, 0.0470]` | Unresolved. |
| UCB, action correlation | `+0.0193` | `[0.0105, 0.0281]` | Coupling synchronizes UCB actions in this environment. |
| UCB, active-group share | `-0.000545` | `[-0.001056, -0.000034]` | Synchronization does not imply share gain. |
| Heterogeneous learners, censored learning time | `+15.51` periods | `[-73.80, 104.81]` | Wrong point-estimate sign and unresolved. |
| Heterogeneous learners, target-hit probability | `-0.0072` | `[-0.0393, 0.0248]` | No heterogeneous completion effect. |

At memory `0.99`, the post-hoc UCB target-hit contrast is positive, but it is
one of many learner-by-memory cells and the preregistered held-out threshold
test failed. It is a hypothesis for a later frozen replication, not a result.
The action-correlation result is causal for the simulated signal-order
intervention only. It neither identifies deployed provider algorithms nor
demonstrates collusion.

The label “heterogeneous” in the first artifact is too broad. Those rows pool
three separate homogeneous active-agent markets (all epsilon-greedy, all
Thompson, or all Q-learning); they are cross-family robustness, not a market
whose active providers use different algorithms simultaneously. The older
WF18 environment has genuine mixed pairs, but it is a separate study and is
not evidence for this GLM-5.2 market-share estimand. Manuscript prose must call
the new rows the **non-UCB homogeneous-family pool**.

The artifact audit found one presentation/data-shape defect: the deterministic
controlled factorial emitted the identical `K=1` singleton path twice. That
did not change any paired simulation estimate or the zero-wedge identity, but
it could double-weight the control and put duplicate points in the plot. The
generator now emits 135 unique controlled cells, has a regression test, and the
final remote artifact is being regenerated. The original line plot also hid
sampling uncertainty; the replacement uses seed-clustered 95% error bars and
writes the intervals into the JSON summary.

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
12. **Transient publication loss.** An automatic monitor reached Hugging Face's
    strict `/whoami` rate limit and failed after completing its analysis. Identity,
    repository creation, and upload now use bounded exponential retries; a fresh
    end-to-end monitor run passed publication and artifact preservation.
13. **Duplicate singleton control and uncertainty-free plot.** The controlled
    factorial emitted `K=1` twice because unilateral and all-active paths coincide,
    and its plot connected factorial means without intervals. The cell is now
    unique, and simulation panels use seed-clustered 95% t intervals. Neither
    defect changed the 9,000 unique paired intervention cells.
14. **Public Actions artifact leaked the private-data boundary.** The repository
    is public, while the first worker draft retained all of `plan-data/` after
    execution. That directory would have included request-level selected-provider
    outcomes. Before the first paid request, the worker was changed to checkpoint
    those rows directly to the access-controlled Hugging Face dataset (anonymous
    access returns HTTP 401) and retain only an outcome-free receipt in GitHub.
    The pre-request assignment artifact remains public because it contains no
    realized routing outcome.
15. **“Exactly once” was too strong.** No external inference API call and remote
    ledger write are atomic. The executable guarantee is at-most-once: the public
    assignment is the reservation, GitHub run attempts above one cannot execute,
    and a crash can create missing outcomes but not an intentional retry. The
    manuscript and code comments must not call this exactly-once execution.
16. **Persisted empty lists changed type.** A background wave reloaded from
    Parquet supplied `co_cutters` as an empty NumPy/Arrow array; boolean coercion
    made the live planner fail before assignment. List-valued persisted fields now
    use explicit normalization, with a regression fixture for the empty-array case.

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
- The v1 environment does not yet implement the full simulation wishlist in the
  design document: no historical-arrival replay, within-market mixture of active
  algorithms, provider-specific costs, binding capacities, stochastic quality,
  unilateral exploitability, router revenue, or welfare frontier. Therefore it
  is a narrow signal-order screen, not the complete Experiment C/D transport
  package.
- Ten seeds are enough to reveal that current intervals are wide; they are not a
  high-powered basis for small learner-family effects. Factorial rows sharing a
  seed are not independent replications, which is why intervals cluster on seed.
- The elasticity learning time is an observer-side recovery statistic, not
  proof that a provider internally estimates that elasticity.
- Learning time is the first entry into a 10% error band, not sustained coverage.
  It uses only all-low and all-high joint states, so coupling can alter both the
  behavior being measured and the rate at which the observer gets identifying
  visits. The frozen right-censoring rule prevents conditioning on completion,
  but it does not separate faster inference from better state coverage.
- `reward_memory` is an exponential reward-retention coefficient inside stylized
  learners, not an identified Markov order or the router's empirical memory. UCB
  counts do not decay with its effective reward sample size. A live or general
  “critical memory” theorem cannot use this parameter without a mapping result.
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
- Local audit: scoped ruff and shell syntax checks passed; after the remote-only
  failure fixes, the repository suite passed 860 tests with one pre-existing
  skip.

## Remote provenance

- Full frozen simulation: GitHub Actions run `29886232930`, source revision
  `a7911e15df6f5fd63accb3497ff22847fc3d3874`, protocol SHA-256
  `f70ca6ba7c8493781d92c52f8e6636cae2bea0a45b278efa50bfbef07091b30e`.
- Corrected monitor validation: run `29887996033`; all analysis, privacy,
  publication, dashboard, and artifact steps passed.
- Paid plan smoke test: run `29888457704` correctly failed closed with zero
  assignments and zero spend because its newest public GLM-5.2 snapshot was
  older than the frozen 30-minute freshness gate.
- First live background block: run `29889339215` froze 12 assignments across
  six arms under the same protocol hash and a worst-case aggregate quote cap of
  `$0.0023591`. Paid execution and the private Hugging Face checkpoint passed.
  Its only public execution artifact is an outcome-free receipt; provider,
  request, latency, fallback, cost, and spend outcomes remain blinded.

## Manuscript boundary

Until the fixed gate opens, the EC paper may include the exact identity, the
experimental design, and a statement that collection is prospective. It may
not describe the reduced simulation as confirmation, label any provider as
collusive, infer dumping costs, report hidden interim arm rankings, or claim a
market-wide welfare effect. After release, every sentence must map to the claim
ledger row and must report the relevant support, interval, falsification, and
concentration result in the same section.
