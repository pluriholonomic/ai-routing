# Strategic routing simulation protocol

## Contents

1. Purpose and scientific object
2. Economic state and timing
3. Router mechanisms
4. Provider strategies and learning
5. Calibration and historical replay
6. H96 paid router calibration
7. Experiment families
8. Statistical protocol
9. Welfare accounting
10. Coordination diagnostics
11. Artifact contract
12. Failure modes and claim language

## 1. Purpose and scientific object

The simulator studies a repeated procurement and dispatch market. A harness or
application generates inference jobs. A router screens providers, maps public
and private state into a choice distribution and fallback order, and charges
the user. Providers post token prices, admit some demand, supply perishable
capacity, and may update asynchronously. A model is a reproducible technology
and compatibility standard, not a strategic seller unless its author also
operates an endpoint.

The simulator answers counterfactual questions such as:

- Which router objective produces the best delivered welfare under strategic
  provider responses?
- When does inverse-price routing create winner-take-most load or unstable
  undercutting?
- How do reserved and elastic capacity types price and ration differently?
- Can delayed quote updates, last look, or admission generate stale-quote or
  phantom-liquidity costs?
- Under what information and learning conditions do supra-competitive paths
  arise, survive deviation, and respond to a price cut?

It does not recover private OpenRouter state or actual provider algorithms.

## 2. Economic state and timing

Use an epoch only when within-epoch request order is economically irrelevant.
Use event time for quote latency, last look, racing, queue state, or
front-running-style timing.

At epoch or event `t`, define:

- demand state `x_t`: model, request shape, input/output length, user value,
  quality requirement, deadline, and failure loss;
- provider type `theta_i`: marginal-resource-cost band, committed capacity,
  elastic capacity option, service distribution, reliability, and capital
  cost;
- public action `a_it`: prompt/completion quote, admitted fraction, advertised
  availability, and optional service tier;
- private provider state: remaining capacity, queue, cost shock, and private
  signal if the experiment permits one;
- router state: candidate eligibility, public health, private recent failures,
  cache affinity, policy parameters, and retry budget;
- history `h_t`: only the information explicitly exposed to each agent.

Recommended event order:

1. Draw common demand, cost, availability, and service shocks from frozen
   subseeds.
2. Reveal each agent's permitted information.
3. Allow scheduled provider quote/admission updates.
4. Form the router's eligible set and choice probabilities.
5. Draw the first provider and fallback order without replacement.
6. Apply admission, capacity, latency, and technical success.
7. Settle payment, resource cost, utility, profit, and welfare.
8. Update public and private histories.

Changing this order changes the game. Register any change before execution.

## 3. Router mechanisms

Every router implements candidate eligibility, route probabilities, fallback
ordering, and any provider-score update. Compare at least:

| Mechanism | Allocation primitive | Main failure mode |
|---|---|---|
| Inverse-price | `q_i p_i^-eta` | high price elasticity, capacity race |
| Lowest cost | deterministic cheapest | winner-take-all, fragility |
| Reliability weighted | health or success score times price weight | score manipulation, incumbency |
| Random eligible | uniform control | ignores price/quality |
| Least busy / P2C | observed load or sampled queues | requires queue observability |
| Capacity certified | score with verifiable capacity/admission | audit and reporting incentives |
| Welfare oracle | feasible outcome optimizer | informationally demanding upper bound |

For token-priced requests use expected all-in quote

`p_i(x) = input_tokens * prompt_price_i + output_tokens * completion_price_i`

plus any request, cache, image, or tool fee the scenario actually uses. Do not
rank a long-input request using output price alone.

The inverse-square rule is a documented public approximation. H96 estimates
whether it predicts owned default selections conditional on the public menu;
private health filtering means even a good fit is not a structural recovery.

## 4. Provider strategies and learning

Minimum deterministic strategy controls:

- static quote and capacity;
- cost plus markup;
- author/list-price anchor;
- discrete undercut;
- myopic best response;
- joint-profit oracle as a diagnostic, not a behavioral model.

Behavioral species may be fitted to quote paths, but named-provider
classification is descriptive. Sample strategies from provider-type
distributions for counterfactuals.

For learning agents, define the Markov game explicitly:

- observation vector and missing state;
- joint or independent action timing;
- discrete/continuous quote and admission action sets;
- reward, discount factor, and episode boundary;
- replay or on-policy algorithm;
- exploration schedule measured in environment transitions;
- training and evaluation seeds;
- exploitability or unilateral-deviation evaluator.

Use the ladder: tabular benchmark, discrete independent learner, continuous
learner, memory/recurrent learner, then router-as-leader. Do not use deep RL to
mask a failure to recover a two-provider exact benchmark.

## 5. Calibration and historical replay

Calibrate only estimable objects:

| Primitive | Preferred source | Fallback |
|---|---|---|
| Quote menu and step sizes | endpoint snapshots and price changes | empirical bootstrap |
| Repricing clock | provider-model price-event panel | provider-type hazard |
| Rival response | strictly prior reaction panel | own-state-only model |
| Candidate routing | H96 owned default choices | eta sensitivity grid |
| Failure/fallback/latency | owned route attempts | provider-type band |
| Demand regimes | model activity/rankings with known window | Poisson/NegBin sensitivity |
| Cost | linked GPU SKU, throughput, commitment | identified set |
| Capacity | provider-approved or transparent allocation data | low/base/high band |
| User value/quality | benchmark or application-specific evaluations | declared sensitivity band |

Use time splits and grouped holdouts. Measure held-out likelihood, calibration,
or moment error against a simple baseline. A coefficient is not a valid
simulator primitive merely because its in-sample p-value is small.

Historical replay freezes exogenous states while allowing treatment policies
to act. It identifies a counterfactual inside the model, not a causal effect in
the historical market. Preserve the original state and version every mapping.

## 6. H96 paid router calibration

### Design

The finite campaign uses six open-weight, multi-provider model IDs, four
request shapes, six four-hour blocks per day, two days, and eight requests per
eligible model-shape block. Maximum nominal count is 2,304 owned requests.

The four shapes are short chat, input-heavy, output-heavy, and required tool
call. For each shape, eligibility checks context, completion length, positive
input/output prices, exact endpoint tag, and required tool parameters.

Each block freezes its public endpoint snapshot before any request. The public
menu determines a component-wise max-price guard. Paid execution refuses to
start if the sum of conservative task caps exceeds the per-run stop loss.

### Arms

| Arm | Count/block | Purpose |
|---|---:|---|
| budgeted default IID | 3 | estimate default choice probabilities |
| explicit price sort | 1 | validate public price-order semantics |
| exact cheapest pin | 1 | test endpoint eligibility and quote firmness |
| exact second pin | 1 | test non-cheapest endpoint eligibility |
| sticky seed | 1 | establish session-selected provider |
| sticky repeat | 1 | estimate cache/session affinity |

Independent requests use unique sessions and prompt nonces. The sticky pair
alone shares both. Exact pins use endpoint `tag` in `provider.order` and
`provider.only` with fallback disabled. Tool calls require parameters.

### Estimation

Collapse duplicate endpoint variants to provider-level minimum all-in quote
when the generation record exposes only provider name. Flag the exact endpoint
as unidentified. For independent default choices estimate

`Pr(i | C,x) proportional to exp(alpha_i) * quote_i(x)^(-eta)`.

Start with `eta=2`, then fit one global exponent on training runs. Add provider
effects only after each included provider has adequate choice and availability
support. Evaluate chronologically held-out runs.

Primary realism metrics:

- selected-provider coverage in the public compatible set;
- held-out negative log likelihood and Brier score;
- top-one choice accuracy and total-variation distance;
- eta-two comparison using both request-shaped all-in quote and the mean
  prompt/completion price index, because the public composite is underspecified;
- fitted `eta` with resampling at the run/block level;
- selected-cost regret relative to public cheapest compatible quote;
- explicit-sort cheapest-provider match;
- pin success/failure and billed-to-quote ratio;
- sticky seed-repeat provider agreement relative to IID coincidence.

Do not interpret sticky agreement as strategic conduct. Do not interpret a pin
failure as phantom liquidity until API errors, parameter incompatibility,
private health, and tag-resolution failures are separated.

## 7. Experiment families

Use the registered E-series rather than inventing labels ad hoc:

- E0: analytical and accounting recovery;
- E1/E-MECH: router mechanism frontier;
- E2: Brown-MacKay asynchronous observation/update clocks;
- E3: routing price sensitivity and tick size;
- E4: reserved versus elastic provider capacity;
- E5: author/list-price anchoring;
- E6: stale quote, last look, fallback, and phantom-liquidity mechanisms;
- E7: learning and emergent coordination diagnostics;
- E8: Stackelberg welfare-optimizing router;
- E9: entry, fragmentation, and cache effects;
- E10: model choice separated from provider procurement.

Existing E-SIM1 through E-SIM9 results and gates remain governed by their
frozen files. New work receives a new registry entry or dated amendment; never
retrofit an old experiment ID after observing a result.

## 8. Statistical protocol

Screen with few seeds only to catch implementation failures. Confirm with the
registered number of training seeds, held-out evaluation seeds, calibration
draws, demand regimes, and grouped holdouts.

Use paired effects under common random numbers. Resample at the independent
seed/calibration-draw level. Report mean, median, percentile and studentized
intervals where stable, sign-flip or randomization tests when justified, and
Holm correction within preregistered families.

Decompose uncertainty into demand/service shocks, learning seeds, calibration,
cost/capacity identified sets, and router-approximation error. A sign that
changes inside the frozen cost/capacity band is a boundary result, not a robust
finding.

## 9. Welfare accounting

For request `r` served by provider `i`, use a declared decomposition such as:

- user utility = delivered value - payment - latency disutility - failure loss;
- provider profit = payment - variable resource cost - capacity/capital cost;
- router surplus = router fee - routing/settlement cost - any paid guarantees;
- harness surplus = harness fee/value - acquisition and orchestration cost;
- welfare = delivered value - real resource, latency, capital, and failure
  costs.

Payments between modeled agents cancel from welfare. Avoid double counting a
router fee as both resource loss and transfer. Report distributional outcomes
even when total welfare is unchanged.

Revenue maximization and welfare maximization differ when market power changes
demand, reliability, capacity investment, entry, or service quality. State the
participation, budget-balance, reliability, and capacity constraints for any
router optimization problem.

## 10. Coordination diagnostics

Calculate at least:

- competitive and joint-profit price benchmarks;
- provider and joint profit lift;
- unilateral deviation gain and approximate exploitability;
- response impulse to an exogenous rival cut;
- punishment depth and recovery duration;
- memory/observation ablation;
- concentration, failure, latency, and capacity effects;
- robustness to unseen strategies and calibration draws.

Price correlation, synchronized repricing, high markup, or high HHI alone do
not identify collusion. In live data, public quote-following can arise from a
common cost or reference-price anchor. In the simulator, mechanism labels are
valid only relative to the controlled information and payoff structure.

## 11. Artifact contract

Every immutable run bundle should contain:

```text
manifest.json
scenario.toml or scenario.json
calibration_revision.txt
source_fingerprint.json
assignment_or_seed_ledger.parquet
episode_or_epoch_outcomes.parquet
agent_actions.parquet
mechanism_metrics.parquet
uncertainty.json
gate_report.json
claim_boundary.md
```

The manifest records commit, dirty status, timestamps, Python/dependency
versions, experiment ID, preregistration/amendment paths, treatments, seeds,
horizon, calibration draws, and output hashes. Never overwrite a run directory.

H96 additionally keeps public candidate and assignment tables separate from
private owned-attempt outcomes. Persist no prompts, completions, API keys, or
raw session IDs.

## 12. Failure modes and claim language

| Observation | Allowed statement | Disallowed statement |
|---|---|---|
| quote-only inverse-square shares | public shadow allocation | routed market share |
| H96 owned default selections | route choices for our bounded probes | all-user flow |
| fitted provider species | behavioral initialization by class | named provider strategy |
| historical replay effect | model counterfactual on archived states | historical causal effect |
| learner high-price path | simulated supra-competitive path | provider collusion |
| failed confirmatory gate | bounded/negative result | tuned replacement claim |
| welfare under bands | conditional welfare frontier | identified live welfare |

Stop and report a blocked claim when the required choice set, realized
selection, service outcome, private order, cost/capacity mapping, or independent
assignment unit is absent. Improving prose cannot repair missing identification.
