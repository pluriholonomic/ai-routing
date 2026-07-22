# EC acceptance revision plan: contestable demand, costly entry, and adaptive routing

Date: 2026-07-22

Target manuscript: `papers/ec/router-is-the-mechanism.tex`

Authoritative branch state at planning time:

- clean research worktree branch: `codex/information-congestion-papers`;
- worktree head and `origin/main`: `96f794f`;
- latest substantive EC rewrite: `0b72efa`;
- rendered manuscript: `papers/ec/router-is-the-mechanism.pdf`, 11 pages;
- latest adversarial assessment: `papers/ec/review-ec-information-congestion-round-3.md`, weak reject.

The separate checkout at `/Users/tchitra/repos/ai-routing` has extensive
pre-existing tracked and untracked changes. It must not be reset, overwritten,
or used as the merge surface for this revision.

## 1. Revision decision

The current paper is the correct manuscript, but its central theorem is too
reduced-form for ACM EC. The revision should not add another independent lemma
to the existing list. It should rebuild the paper around one economic object:

> A router allocates only the contestable part of inference demand. Providers
> enter the execution market by paying capacity and integration costs; a subset
> separately pays to learn and deploy adaptive prices. The router's price rule
> determines the share return to adaptation, correlated experiments determine
> whether provider-specific returns are learnable, and bilateral contracts and
> capacity commitments determine how important public routing is to each
> provider.

This produces three distinct extensive margins that the current draft partly
conflates:

1. `n_FE`: providers entering or remaining listed in the market;
2. `k_AE`: entered providers acquiring or using adaptive pricing technology;
3. `k_W`: adaptive providers the router should expose to contestable flow.

A fourth object, `k_L`, is the number of provider-specific price effects that
can be learned to a declared accuracy from the available signal and horizon.
The paper should reserve `k*` for an explicitly named objective. It should never
use the same symbol for free entry, adaptive entry, learnability, and welfare.

The revision's positive thesis is:

> Smooth price steering can create large local share returns while costly
> entry, limited contestable flow, and correlated experimentation produce a
> small adaptive set. A router can decentralize efficient entry and exposure
> only if it separates capacity/reliability rewards from price-share rewards
> and charges for the marginal externality of correlated exposure.

The empirical section remains suggestive and property-based. Its role is to
locate observed model markets in the theory's feasible regimes, reject
incompatible explanations, and identify which primitives a router or harness
partner must reveal. It does not estimate market-wide welfare or provider
intent.

## 2. Why the present draft is not yet an accept

The round-3 review identifies the binding problem correctly:

- the congestion loss is posited rather than derived;
- the current `k*` is a planner optimum, not an equilibrium adaptive count;
- free and costly entry are mentioned only in prose;
- the proposed covariance cap has no decentralization or Sybil-resistance
  theorem;
- effective rank alone does not determine the welfare loss;
- the empirical GLM rank ladder is linear-compatible and the current bandit
  intervention has no allocation effect;
- the 108-rule structural frontier is a design screen, not a calibrated welfare
  estimate.

The solution is to derive the price-learning externality from the routing
equations, add a two-stage costly-entry game, and turn the router proposal into
an implementation result. More simulation or a larger abstract will not repair
the paper without those steps.

## 3. Unified model and timing

Use one model throughout the theory, simulations, and empirical crosswalk.

### 3.1 Participants and channels

For model market `m`, there are `N_m` potential inference providers. Provider
`i` chooses:

1. whether to enter;
2. capacity `K_i` at fixed/integration cost `F_i(K_i)`;
3. bilateral or committed harness volume `B_i` at contract price `r_i`;
4. whether to acquire adaptive pricing technology at cost `A_i`;
5. a public-router quote `p_it` and any capacity commitment.

Public router demand is `D_m^R`; bilateral or direct demand is `B_i`. A capacity
constraint is

```text
D_m^R s_i(p, alpha, x) + B_i <= K_i,
```

with shadow value `nu_i`. This separates a provider's accounting market from
the contestable routing market.

The router chooses exposure `x_i`, price exponent `eta`, score `alpha_i`,
fallback policy, and transfers or fees. Conditional first-choice share is

```text
s_i = x_i exp(alpha_i - eta log p_i)
      / sum_j x_j exp(alpha_j - eta log p_j).
```

The score can contain quality, latency, health, committed capacity, and memory.
It is not called quality unless those components are separately observed.

### 3.2 Provider payoff

The public and bilateral components are

```text
Pi_i = D_m^R s_i (p_i - c_i)
       + B_i (r_i - c_i)
       - F_i(K_i) - A_i 1{adaptive} - fees_i,
```

subject to capacity. When capacity binds, replace short-run marginal cost in
the public pricing first-order condition by `c_i + nu_i`.

Define provider-level contestability

```text
lambda_i = D_m^R s_i / (D_m^R s_i + B_i).
```

This is not identified from public OpenRouter data. It becomes observable only
with harness/provider channel logs or contract-volume bounds.

### 3.3 Timing

Use the following sequential game:

1. router announces score, fees, capacity-credit rule, and exposure policy;
2. providers enter and invest in capacity;
3. entered providers choose bilateral commitments and adaptive technology;
4. providers post prices and generate price experiments;
5. router assigns and retries requests;
6. delivery, quality, payments, and penalties settle;
7. providers update pricing rules.

The paper should solve stages 1-5 in nested reductions rather than pretending
to solve the unrestricted dynamic game at once.

## 4. Formal results to prove

### Result A: individual and group share elasticity

Retain the current score-price equivalence, but make the group form primary.
Let `G` be providers making the same local log-price move and let `S_G` be their
pre-move share. If the share-weighted score response inside the group is
`h'_G`, define `eta_G_eff = eta - h'_G`. Then prove

```text
z_i^U = -d log s_i / d log p_i
      = eta_i_eff (1 - s_i),

z_G = -d log S_G / d log p_G
    = eta_G_eff (1 - S_G).
```

For a price-only rule, a common cut transfers exactly the same total share from
the passive set to `G`; conditional passive losses are proportional to their
pre-cut shares. This is the theoretical counterpart of the WF19 shadow-share
accounting.

### Result B: revenue and profit thresholds

For a common proportional cut by `G`, prove the local identities

```text
d log revenue_G / d(cut) = z_G - 1,

d log profit_G / d(cut) = z_G - p/(p - c - nu)
```

under the symmetric-cost reduction. Therefore the price-only revenue threshold
is

```text
S_G < 1 - 1/eta_eff,
```

and the profit threshold is stricter when marginal or scarcity cost is
positive. Under equal shares, `S_G = k/n`, yielding a mechanical linear-density
ceiling. This is the exact bridge among the router exponent, market-share gain,
and the number of co-moving providers. It also explains why one active provider
and several active providers face different path elasticities.

Report revenue thresholds without cost assumptions. Report profit thresholds
only as cost/scarcity identified sets.

### Result C: correlated-experiment bias and learning time

Derive the HMP-style mechanism directly from the routing equation. For
`X_i = Delta log p_i`, a local price-only expansion gives

```text
Delta log s_i = -eta(1-s_i) X_i
                + eta sum_{j != i} s_j X_j + error_i.
```

If a provider regresses its share reward only on its own experiment, its
population coefficient contains the exact omitted-variable term

```text
eta sum_{j != i} s_j Cov(X_i, X_j) / Var(X_i).
```

For `k` equal-share perfect co-movers this recovers the group elasticity
`eta(1-k/n)`. This should replace the current assertion that effective rank by
itself creates congestion.

Then derive a finite-sample learning bound. The time required to distinguish
unilateral from path elasticity to error `epsilon` depends on:

- public-flow payoff SNR;
- conditional experiment variance `Var(X_i | X_-i)`;
- horizon or effective memory;
- number of action/price alternatives;
- desired error probability.

A generic form is

```text
T_i >= C sigma_i^2
       / [epsilon^2 Var(X_i | X_-i)] log(Actions/delta).
```

This produces a real critical-memory or critical-horizon statement: when
experiments are nearly collinear, provider-specific elasticity is slow or
impossible to learn even when the group path is easy to learn. If the algorithm
omits rival experiments, more data converges to the biased path elasticity
rather than the causal own elasticity.

Effective rank may enter only through a proved spectral bound on conditional
variation or Fisher information. If the proof requires coherence or a lower
eigenvalue assumption, state it. Do not claim that effective rank alone implies
the loss in the present Assumption 1.

### Result D: bilateral-contract separation and observational equivalence

Prove a two-part separation result.

1. If public and bilateral payoffs are separable, capacity is slack, and the
   bilateral price does not depend on the public quote, bilateral volume does
   **not** change the static public-price first-order condition.
2. Bilateral volume does change adaptive-technology adoption and learning by
   scaling the absolute public payoff, adding channel-aggregation noise, and,
   when capacity binds, changing `nu_i`.

This avoids the incorrect claim that private demand mechanically attenuates a
conditional public best response. Its effect requires fixed adaptation costs,
imperfect channel telemetry, or capacity coupling.

Prove an observational-equivalence corollary: public menus plus owned router
choices can identify a conditional effective exponent, but cannot separately
identify contestable share `lambda_i`, adaptation cost `A_i`, or capacity shadow
cost `nu_i`. Construct two economies with identical public observables and
different bilateral demand/adaptation equilibria. This makes the side-deal
interpretation a formal identified-set result rather than speculation.

### Result E: costly provider entry

Add a tractable symmetric entry benchmark before the heterogeneous simulation.
Under inverse-power routing with fixed demand and interior symmetric pricing,
per-provider public operating profit is

```text
pi_R(n) = D^R c / [eta(n-1) - n].
```

The free-entry count is the largest `n` satisfying

```text
pi_R(n) + pi_B(n) >= F(K) + A 1{adaptive} + fees.
```

This gives an explicit comparative static: a provider can remain listed because
bilateral contracts or sunk reserved capacity cover entry cost even when the
public channel is too small to justify adaptive pricing.

Add independent provider availability `rho` and serial fallback. Delivered
probability is `1-(1-rho)^n`; the planner's marginal entry value is the
incremental delivery/resilience value minus capacity, retry, monitoring, and
entry costs. Compare it with the entrant's private profit. Prove:

- excess entry when business stealing and public rents exceed incremental
  resilience/capacity value;
- insufficient entry when unpriced resilience or quality spillovers dominate;
- a Pigouvian listing charge or capacity credit equal to the wedge implements
  the efficient entry count in the benchmark.

The implementation must reward verified incremental delivered capacity, not
endpoint labels. Otherwise identity splitting creates fake entry.

### Result F: adaptive entry and the critical set

Among entered providers, adaptive pricing requires a separate fixed cost. Let
`g_i(lambda_i, z_i, p_i-c_i-nu_i)` be the expected public-channel gain from
adaptation. A provider adapts only if

```text
present value of g_i >= A_i
```

and the effect is learnable within its horizon. This produces three regimes:

1. `g_i <= A_i`: no adaptation even when mechanical share elasticity is large;
2. positive adaptation value but a binding information bound: a minority
   adaptive set;
3. positive value and independent, precise signals: adaptive entry can scale
   linearly until the group-share profit threshold binds.

The current reduced-form objective can survive only as a corollary of a proved
primitive model. If the primitive derivation yields

```text
V_n(k) = (b lambda_n - f) k/n
         - c (k/n)^2 (k/r_n)^gamma,
```

then the interior solution becomes

```text
k_AE = [(b lambda_n - f) n r_n^gamma
        / (c(2+gamma))]^(1/(1+gamma)),
```

when `b lambda_n > f`, and zero otherwise. If
`lambda_n ~ n^(-delta)` and `r_n ~ n^beta`, its exponent is

```text
(1 + gamma beta - delta)/(1 + gamma).
```

This shows two distinct routes to a vanishing adaptive fraction: sublinear
information rank or a shrinking contestable channel. Do not retain this power
law if the primitive estimation model produces a different loss. The theorem,
not the desired exponent, determines the paper.

### Result G: implementation and robust identity handling

The router mechanism should have two separable instruments:

1. an execution-contingent capacity credit or bond governing entry and
   resilience;
2. a covariance/exposure fee governing correlated adaptive flow.

Derive the marginal-externality fee that decentralizes `k_W` in the benchmark.
Then prove a robust version under covariance estimation error. Candidate
guarantee:

```text
if ||Sigma_hat - Sigma|| <= epsilon,
the robust cap/fee has welfare regret at most L epsilon
relative to the full-information benchmark,
```

subject to completion and concentration constraints.

Aggregate identities by certified economic operator and committed capacity.
Prove either exact split-proofness under perfect certification or an
approximation bound when clustering has declared false-negative mass. Price
innovation alone must not earn an immediate independence subsidy, because a
provider can manufacture noise. Use lagged holdout covariance and capacity
delivery to determine future exposure.

## 5. Empirical program

The empirical section should be organized as a sequence of property tests, each
mapped to one formal result.

| Theory object | Current evidence | New identifying experiment | Strongest permitted claim |
|---|---|---|---|
| `eta_eff`, `z_i`, `z_G` | public menus, WF19 shadow accounting, accruing owned choices | model-specific default/price-sort blocks and natural price-event choices | conditional owned-request price sensitivity |
| group share/revenue threshold | exact shadow identity; quote-revenue index | realized first-choice event panel plus cost bounds | revenue threshold; profit identified set |
| correlated-experiment bias | public quote covariance; HMP simulation negative control | prospective co-mover event study and marginal-order shuffle in simulation | HMP-consistent path bias only if all gates pass |
| contestable share `lambda` | not observed | harness/provider channel logs or bilateral-volume bounds | partial identification of public-flow exposure |
| free entry `n_FE` | provider/model entry and exit from public menus | model-release adoption panel; partner capacity certification trial | entry hazard and mechanism response, not cost without partner data |
| adaptive entry `k_AE` | frozen repricer regimes; 90% of non-GLM markets have zero active undercutters | adaptation-hazard model using preperiod SNR and contestability proxies | revealed adaptation regimes, not provider algorithms |
| welfare-optimal exposure `k_W` | simulation only | randomized `n x k x overlap x rule` owned-routing experiment | operational-surplus frontier for this account/workload |

### Experiment 1: model-specific effective exponent

Extend the current `model-specific-router-exponent-v1` analysis without changing
blinded H81/H95 studies.

- Fit model/request-shape cells separately.
- Distinguish cross-sectional price slopes from within-provider repricing slopes.
- Estimate default routing and explicit price-sort routing separately.
- Report profile likelihood and block-bootstrap intervals.
- Add provider fixed effects only when the cell has genuine within-provider
  price variation.
- Test heterogeneity with a pooled-versus-cell likelihood-ratio test and
  hierarchical partial pooling.
- Report score-price wedges as reduced-form residuals and require temporal
  cross-validation before calling them predictive.

Current planning baseline: 423 covered choices, three estimable short-chat
cells, pooled `eta` about 1.45, and no significant cross-model heterogeneity
(`p` about 0.16). GLM-5.2 is near 1.93 but has a wide interval. These numbers are
development baselines, not manuscript-ready until regenerated at one immutable
revision and reconciled with the paper audit.

Promotion gate: at least five model cells with real price support, at least
three with within-provider variation, predeclared minimum choices/blocks, and
leave-date-out stability. A cell with equal prices or no within-provider moves
must be labeled unidentified.

### Experiment 2: realized cut-to-share elasticity

Use the existing event-triggered paid infrastructure.

- Detect unilateral cuts, common cuts, raises, rank crossings, and enforcement
  events without owned outcomes.
- Freeze the exact menu and planned request waves before execution.
- Estimate realized first-choice changes for the mover, co-movers, anchors, and
  other passive providers.
- Compare the realized finite-change response with the exact price-only curve.
- Decompose deviations into current score, eligibility/fallback, and residual.
- Plot `z_G(t)`, `z_passive(t)`, and the active-group share mass for every model.
- Use raises and clock-matched no-change periods as signed/placebo controls.

The current WF19 support is one model, 84 clean shadow shocks, three movers, and
seven paid events; it is not enough for cluster-level confidence intervals.
Retain the existing minimum-model, cluster-count, concentration, and immutable
release gates.

### Experiment 3: SNR and adaptation hazard

Create a provider-model-day panel whose outcome is the next quote change or
entry into the adaptive regime. Estimate only with lagged/preperiod predictors:

- predicted mechanical share return `z_i` and group return `z_G`;
- owned-route selection support and its variance;
- public demand/model popularity proxies;
- quote noise and conditional rival-experiment variance;
- benchmark distance and margin bounds;
- provider scale/capacity category with dated provenance;
- public enforcement/capacity state;
- app/provider affinity or direct-channel proxy when available.

Estimate discrete-time hazards and a competing-risk model for cut, raise, no
change, entry, and exit. Use provider-model and clock effects, whole-model
holdouts, future leads, circular shifts, and negative-control models.

The central test is whether adaptation probability rises with lagged estimated
public payoff SNR after holding mechanical elasticity fixed. A positive result
supports a revealed-learning threshold. It does not identify UCB, communication,
or collusion.

### Experiment 4: bilateral contracts and side deals

Run this as a data-partnership track with a hard fallback boundary.

Preferred partner data from Hermes or another harness:

- hashed request and app/harness identifier;
- model and request-shape class;
- direct-versus-router channel;
- eligible providers and selected provider;
- public quote and a blinded net-price/rebate index;
- committed/reserved-capacity indicator;
- success, total latency, retries, tokens, and billed amount;
- no prompt, completion, customer identifier, or raw contract.

Preferred provider-side fields:

- OpenRouter-facing request count by model/time;
- direct/contract request count in the same bins;
- committed capacity and utilization bin;
- public quote changes and effective net-price bucket.

Primary estimands:

1. channel-specific contestability `lambda_i` or bounds;
2. app-provider fixed effects after current price and QoS controls;
3. adaptation hazard versus public-channel share;
4. public quote response when direct capacity becomes tight;
5. same provider/model performance through direct and routed channels.

If no partner provides contract volume or a net-price bound, the paper retains
Result D as an impossibility/observational-equivalence result. Own direct API
probes can compare channels but cannot establish that a side deal exists.

### Experiment 5: randomized exposure and information congestion

Preserve `experiments/information-congestion-v1` exactly. It already randomizes
eligible menu size `n`, responsive exposure `k`, high/low overlap, default versus
price-sort routing, and fresh-session replicates. Do not amend its outcomes,
cadence, or gates after accrual.

Use it to estimate:

- completion, latency, cost, fallback, and fidelity by `(n,k,overlap,rule)`;
- the finite operational-surplus response surface;
- simultaneous confidence sets for the maximizing exposure;
- whether overlap changes outcomes at fixed `n`, `k`, and price distribution;
- transport across model markets.

This experiment identifies the effect of the router's eligible set on our
requests. It does not identify market-wide adaptive entry. A v2 is justified
only after the pilot variance report and must be frozen before confirmatory
outcomes.

### Experiment 6: costly entry and capacity certification

Build a public model-release cohort panel:

- weight release time and author benchmark;
- first provider appearance, first price, and time to stable service;
- model size, memory requirement, context length, quantization availability,
  and architecture novelty;
- provider capacity category and existing model portfolio;
- entry, exit, derank, capacity ceiling, latency, and success trajectories.

Estimate entry/exit hazards and difference-in-differences around model launches
only as descriptive/quasi-experimental evidence. Public appearances do not
identify fixed entry cost.

The accept-level mechanism test is an opt-in provider trial, preferably with a
router partner:

- control: ordinary listing and allocation;
- capacity-credit arm: future exposure/payment conditional on verified
  incremental delivered capacity;
- price-only exposure arm;
- capacity-bond arm with failure penalties.

Measure provider participation, committed capacity, successful delivery,
fallback, persistence after the trial, prices, and concentration. Randomize by
provider-model cohort or switchback where interference permits. The entry
result should be stated as a mechanism response, not a universal cost estimate.

### Experiment 7: strategic and adversarial simulation

Replace the present 108-rule illustration with a preregistered environment that
directly implements the model.

Provider primitives:

- fixed entry cost;
- capacity investment and scarcity shadow cost;
- bilateral demand share;
- adaptive-technology cost;
- signal covariance and private noise;
- price, capacity, quality, and exit actions;
- heterogeneous algorithms: exact best response, UCB, Thompson, Q-learning,
  static anchor, and adversarial/Sybil strategies.

Router arms:

- inverse-power price-only;
- generalized price-quality score;
- covariance cap;
- covariance fee;
- capacity credit/bond;
- joint entry-plus-exposure mechanism;
- oracle full-information benchmark.

For every arm report:

- `n_FE`, `k_AE`, `k_L`, and `k_W` separately;
- user utility, transfers, provider profit, router revenue, and social surplus;
- completion, latency, quality, fallback, capacity utilization, concentration;
- unilateral entry/exit deviations, price deviations, pair deviations, and
  identity-splitting attacks;
- regret to the full-information mechanism under parameter uncertainty;
- transport across contestability, SNR, memory, rank, cost, and demand grids.

The simulation is promoted only if analytical equilibria are recovered in
tractable cells, every claimed equilibrium passes deviation audits, and results
survive learner and Sybil stress tests. Absolute welfare levels remain in
simulation units unless externally calibrated.

## 6. Manuscript restructuring

The 11-page paper currently presents too many loosely connected contributions.
Rebuild it around three.

### Proposed title

`Contestable Demand and Costly Entry in AI Inference Routing`

Possible subtitle: `Price Elasticity, Adaptive Learning, and Platform Design`.

### Proposed abstract structure

Use six sentences:

1. define open-weight inference as a partially substitutable execution market;
2. identify harnesses, routers, providers, and bilateral/direct channels;
3. state the costly-entry/adaptive-entry problem;
4. state the main elasticity-plus-learning theorem;
5. state the strongest empirical property test with its negative boundary;
6. state the entry/exposure mechanism and claim boundary.

Do not enumerate every dataset, theorem, interval, and negative result in the
abstract.

### Proposed section order

1. **Introduction and market fact.** Many listed providers, few repricers, and
   hidden bilateral/capacity exposure.
2. **Institution and data.** The routing stack and identification ladder.
3. **Price steering.** Individual/group elasticity, market-share incidence,
   and revenue/profit thresholds.
4. **Costly entry and adaptive learning.** Free entry, bilateral contracts,
   adaptation cost, correlated-experiment bias, and learning bound.
5. **Mechanism.** Entry credit/fee, covariance exposure fee, robust/Sybil
   guarantee.
6. **Empirical property tests.** Exponents, GLM/non-GLM adaptation, realized
   route interventions, entry cohorts, and explicit failures.
7. **Strategic validation.** Only invariant simulation results and adversarial
   audits.
8. **Conclusion.** What the market could be, what data distinguish regimes,
   and what the router can safely implement.

### Material to demote or remove

- Move the entropy/KL identity and generic robust score bound to the appendix
  unless they are used in the entry/exposure guarantee.
- Keep hidden-capacity impossibility only if it becomes part of Result D/E.
- Move absolute SM4 welfare values and the colorful objective frontier to the
  supplement.
- Keep H81/H95 only as institutional evidence about fallback; do not let them
  interrupt the central entry/elasticity argument.
- Keep the dynamic-memory exclusion paragraph, but replace it after Result C
  is proved and its empirical test is run.
- Remove any sentence treating the current GLM rank slope as evidence for
  `k=o(n)`.

### New figures

1. **Economic decomposition:** `n_FE`, `k_AE`, `k_L`, and `k_W` across public
   and bilateral channels.
2. **Elasticity/incidence:** model-by-model effective exponent and group share
   elasticity, with GLM event-time realized choices and shadow curves clearly
   separated.
3. **Adaptation phase diagram:** mechanical share return versus revealed SNR,
   with observed model markets and uncertainty.
4. **Entry/exposure frontier:** completion, cost, quality, and concentration
   under randomized exposure; no scalar welfare without value/cost bounds.

Every empirical plot must show raw support, uncertainty, and a direct statement
of whether the quantity is shadow, owned-account realized, or market-wide.

## 7. Acceptance gates

### Theory gate

All must pass before asking for another EC review:

1. correlated-experiment loss or learning limit is derived from primitives;
2. free-entry and adaptive-entry equilibria are separately characterized;
3. planner and private entry/adaptation wedges are explicit;
4. an implementable fee/credit decentralizes the benchmark target;
5. identity splitting and covariance estimation error have formal guarantees;
6. score, capacity, and bilateral-demand assumptions are stated in theorem
   language rather than only prose;
7. numerical solvers reproduce every tractable closed form and pass deviation
   audits.

### Empirical gate

The paper can remain suggestive, but it needs at least:

1. five supported model-specific routing-slope cells and genuine within-provider
   variation in at least three;
2. a released realized cut-to-share panel with adequate model/provider clusters
   and no dominant pair;
3. the randomized exposure experiment covering at least three supported menu
   sizes, preferably all four;
4. an adaptation-hazard result that transports to held-out models or a clear
   negative result narrowing the theory;
5. a public costly-entry cohort panel;
6. either one harness/provider contestability dataset or an explicit statement
   that bilateral contracting remains observationally equivalent;
7. no use of blinded H95 outcomes before its fixed horizon and no retroactive
   changes to existing preregistrations.

### Presentation gate

1. no more than three headline contributions;
2. no figure that mixes shadow and realized share without separate panels and
   labels;
3. no synthetic welfare number in the abstract or introduction;
4. every empirical estimate points to an immutable revision and code target;
5. the evidence ledger maps every abstract sentence to a theorem, released
   estimate, or explicit assumption;
6. a fresh adversarial EC review must rate mechanism completeness and technical
   novelty at least 8/10 and recommend accept or strong accept.

## 8. Execution order and code bundle

### Work package 0: freeze and reconcile

- commit the current model-specific exponent module and tests after audit;
- create a manuscript-result crosswalk at one immutable HF revision;
- preserve H81 and blinded H95 boundaries;
- add a dated amendment rather than changing any live preregistration.

### Work package 1: theory kernel

Add:

- `src/orcap/market_env/contestable_entry.py`;
- `src/orcap/market_env/adaptive_entry.py`;
- `src/orcap/market_env/entry_exposure_mechanism.py`;
- symbolic/numeric verification tests under `tests/market_env/`.

Produce machine-readable theorem tables for the symmetric price/entry solution,
group elasticity, omitted-variable bias, learning bound, Pigouvian fee, and
split-proofness stress cases.

### Work package 2: empirical estimators

Add:

- `src/orcap/analysis/adaptation_snr_hazard.py`;
- `src/orcap/analysis/provider_entry_cohorts.py`;
- `src/orcap/analysis/contestability_bounds.py`;
- a joint immutable summary joining model-specific exponent, WF19, entry, and
  exposure outputs without reading blinded studies.

### Work package 3: live experiments

- continue the existing GLM routing and information-congestion studies at their
  frozen cadence;
- add no outcome-dependent stopping;
- deploy event-wave completeness and spend reconciliation checks;
- prepare a separate, versioned harness/provider data contract;
- create a new capacity-certification study only after a partner and budget are
  explicit.

### Work package 4: simulations

- preregister the costly-entry and bilateral-demand grid;
- validate closed forms first;
- run the heterogeneous and adversarial grids remotely;
- publish full negative-control and failed-transport cells.

### Work package 5: manuscript rewrite

- rewrite `papers/ec/router-is-the-mechanism.tex` by diff, not from scratch;
- reduce the contribution list to three;
- replace Figures 1 and 3 with the new economic and empirical figures;
- regenerate the PDF and visually inspect all pages;
- update the claim ledger and artifact hashes.

### Work package 6: review loop

1. run the full test suite and evidence audit;
2. conduct an independent ACM EC review focused on primitive derivation,
   equilibrium, implementation, identity attacks, and empirical bridge;
3. incorporate every actionable weakness into a dated plan amendment;
4. repeat until the review recommends acceptance;
5. send the PDF after every completed manuscript loop.

## 9. Claim language to preserve

Allowed with present evidence:

- public price cuts create a large conditional shadow-share surface;
- default owned routing differs materially from explicit price sorting;
- model-specific effective exponents are estimable only in a few cells and are
  not yet significantly heterogeneous;
- active repricing is sparse outside GLM under the frozen classifier;
- the current GLM rank ladder is linear-compatible;
- costly entry, bilateral demand, and low public-flow SNR are observationally
  plausible explanations for many passive providers.

Not allowed without new data:

- side deals exist for a named harness/provider pair;
- a provider is dumping or colluding;
- `k_AE`, `k_W`, or `n_FE` is identified market-wide;
- the documented inverse-square rule is the proprietary default allocation law;
- a reduced-form score is quality;
- public quote revenue is profit;
- the proposed cap improves live welfare.

The intended acceptance contribution is therefore not a claim that the current
market is collusive or inefficient. It is a strategic mechanism theorem that
explains which combinations of price elasticity, signal overlap, bilateral
contracting, and costly entry can generate the observed market, together with
experiments that progressively distinguish those regimes.
