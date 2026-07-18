# Open-source routing and strategic-provider simulation

**Search date:** 2026-07-18
**Scope:** primary papers, official project documentation, and official GitHub repositories.
**Question:** can we test strategic inference-provider pricing and capacity policies against real open-source router code, while using this repository's historical market data for calibration and replay?

## Bottom line

Yes, but no single existing project is the complete environment.

The strongest combination is:

1. **A fast market kernel in this repository**, exposed as a
   [PettingZoo Parallel API](https://pettingzoo.farama.org/main/api/parallel/)
   environment. This is where provider agents post prices, choose admitted
   capacity, learn, and receive profit. It must run much faster than wall clock.
2. **LiteLLM as the first executable router baseline.** Its Python router
   already exposes weighted, rate-limit-aware, latency, least-busy, cost, and
   custom deployment-selection strategies. It is the shortest path from the
   existing Python code to a router we can invoke directly.
3. **llm-d Router plus llm-d Inference Sim as the main systems benchmark.**
   The router has explicit filter, scorer, and picker plugins. The GPU-free
   simulator is OpenAI-compatible, models load-sensitive latency, emits vLLM-like
   metrics, supports failure injection, and can be deployed as multiple synthetic
   providers. This is the closest open-source executable testbed to the proposed
   market.
4. **RouteLLM/LLMRouter/RouterBench as a separate demand-side layer.** These
   projects choose *which model* should answer a query. They do not model
   competition among providers serving the same open-weight model. They are
   useful for generating heterogeneous model demand and user value, but should
   not be treated as provider routers.
5. **Vidur as an offline systems-fidelity check.** It can replay traces and
   model latency/throughput without GPUs, but its public main branch has a much
   narrower routing surface and is less actively maintained than llm-d.

The research contribution is therefore not “another LLM router.” It is a
strategic market environment that wraps several real routers behind one common
allocation interface and asks how provider policies and router rules interact.

## The two routing problems must remain separate

There are two distinct decisions in an inference marketplace:

| Layer | Choice | Economic role | Useful open source |
|---|---|---|---|
| model routing | prompt or task -> model | harness chooses quality/cost frontier | RouteLLM, LLMRouter, RouterBench, FrugalGPT, BEST-Route, vLLM Semantic Router |
| provider routing | fixed model request -> deployment/provider | router procures execution from competing sellers | LiteLLM, llm-d Router, vLLM Router, Portkey |

The current `orcap.routing_simulation` is in the second layer: it fixes a model
and workload shape, then calculates a public quote-implied provider allocation.
The proposed environment should preserve that interpretation. A later harness
agent can make the first-layer model choice before the provider market clears.

This separation is supported by the recent
[RouteBalance paper and code](https://arxiv.org/abs/2606.17949), whose central
systems result is that model selection and instance load balancing are usually
optimized in isolation and can be improved by a joint assignment. RouteBalance
is an informative comparison, but its current repository is a small research
artifact rather than the best foundation for a long-lived market environment.

## What this repository already supplies

The repository is much closer to a calibrated environment than to a blank
slate:

| Existing object | Simulation use | Claim boundary |
|---|---|---|
| `routing_simulation` and `orcap.routing_simulation` | public candidates, request-shape costs, inverse-square allocation baseline | simulated public surface, not realized flow |
| `router_policy_snapshots` and `orcap.router_policy` | normalized ordered, weighted, lowest-cost, throughput, and inverse-square policies | configured account policy, not global router policy |
| `router_route_attempts` | selected provider, retry/fallback, cost, latency, tokens, outcome for owned traffic | controlled-account traffic only |
| OpenRouter endpoint/congestion panels | quote, public reliability, latency, throughput, rate limits, derank state, partial capacity fields | public operational state, not physical capacity or marginal cost |
| BM1-BM5 and price-event panels | provider cadence, quote menus, lagged rival moves, reaction-rule features | predictive/descriptive; rival observation and strategy are not identified |
| H19 provider features/types | catalog breadth, first-party status, quantization, price position, operational measures, repricing intensity | coarse behavioral types; clustering is not a structural cost model |
| app/model-token panels | model-level demand mix and shifts across applications | cannot allocate app tokens to a provider |
| mechanism and capacity-telemetry modules | allocation, collateral, capacity commitment, shortfall, profit/welfare accounting primitives | proposed mechanisms; private costs and capacity remain inputs |

The latest local H19 artifact has 70 provider rows and already distinguishes a
broad third-party infrastructure group from a smaller, mostly first-party model
author group. That makes type-conditioned simulation feasible. It does not
identify a provider's cost curve. Cost must remain a sensitivity band or come
from an explicit partner/capacity study.

## GitHub search: executable routers and simulators

Repository activity below was checked through the GitHub API on 2026-07-18.
Stars are only a rough maintenance signal, not a scientific ranking.

### Tier 1: use directly

| Project | What is executable | Why it fits | Limitation | Activity at search date |
|---|---|---|---|---|
| [LiteLLM](https://github.com/BerriAI/litellm) | Python router and OpenAI-compatible gateway; weighted, usage/rate-limit, latency, least-busy, cost, priority, retry, fallback, custom selection | fastest adapter; a custom strategy can consume agent quotes/capacity and return a provider deployment | production abstractions are deployments and limits, not strategic bids; price dynamics must be supplied by our environment | 53.9k stars; pushed 2026-07-18; MIT outside `enterprise/` |
| [llm-d Router](https://github.com/llm-d/llm-d-router) | production Go router/EPP with filter -> scorer -> picker pipeline, custom endpoint metrics, weighted-random and max-score selection | cleanest real mechanism interface; quote and capacity can be endpoint attributes; allows price, queue, cache, and latency scores to be composed | heavier Kubernetes/Envoy deployment; a true inverse-square scorer needs a small plugin | 260 stars; pushed 2026-07-18; Apache-2.0 |
| [llm-d Inference Sim](https://github.com/llm-d/llm-d-inference-sim) | GPU-free OpenAI-compatible synthetic vLLM server with streaming, load-sensitive TTFT/ITL, metrics, cache state, datasets, and failures | each process/pod can stand in for a provider with distinct service and failure profiles; can test the real llm-d router without GPUs | operates in wall clock, so it is a validation backend rather than the million-step RL kernel | 166 stars; pushed 2026-07-15; Apache-2.0 |
| [vLLM Router](https://github.com/vllm-project/router) | Rust/Python router with random, round-robin, consistent-hash, power-of-two, and cache-aware policies | strong non-price systems baselines and an independent executable implementation | no native market-price rule; strategic price experiments require an adapter or new policy | 317 stars; pushed 2026-07-13; Apache-2.0 |
| [Portkey Gateway](https://github.com/Portkey-AI/gateway) | TypeScript/edge gateway with weighted load balancing, conditional routing, fallback, retry, timeout, and circuit-breaker configurations | useful independent weighted/fallback control and already covered by the repository's normalized policy schema | no public strategic bid or arbitrary score interface comparable to llm-d; less convenient than LiteLLM for the training loop | 12.5k stars; pushed 2026-05-25; MIT |

The key llm-d extension is concrete, not aspirational. Its
[filter tutorial](https://github.com/llm-d/llm-d-router/blob/main/docs/create_new_filter.md)
documents endpoint filtering and per-request plugin state. Its
[endpoint-attribute scorer](https://github.com/llm-d/llm-d-router/blob/main/pkg/epp/framework/plugins/scheduling/scorer/endpointattribute/README.md)
normalizes an arbitrary numeric model-server metric, and its
[weighted-random picker](https://github.com/llm-d/llm-d-router/blob/main/pkg/epp/framework/plugins/scheduling/picker/weightedrandom/README.md)
samples in proportion to endpoint score. A custom `quote-scorer` can therefore
emit `q_i^-eta` and reuse the stock weighted picker. The same profile can combine
quote score with queue-depth, predicted-latency, or cache-affinity scorers.

### Tier 2: use for demand and serving fidelity

| Project | Best use here | Why not the primary market kernel | Activity at search date |
|---|---|---|---|
| [Microsoft Vidur](https://github.com/microsoft/vidur) | offline trace replay, Poisson/gamma arrivals, request-length traces, replica scheduling, latency/throughput and capacity planning | no strategic seller abstraction; public main branch has round-robin/random global routing and was last pushed in 2025 | 642 stars; MIT |
| [RouteBalance](https://github.com/AKafakA/route-balance) | joint quality/cost/latency/load benchmark over concrete instances | very new research code, tiny adoption, no declared GitHub license at search time, cluster-oriented reproduction path | 2 stars; pushed 2026-06-18 |
| [LLMRouter](https://github.com/ulab-uiuc/LLMRouter) | broad library of 16+ prompt-to-model routers and datasets | routes among models/providers for quality, not same-model strategic sellers | 2.1k stars; pushed 2026-07-13; MIT |
| [RouteLLM](https://github.com/lm-sys/RouteLLM) | preference-trained strong/weak model routing and model-demand generation | static research snapshot in practice; last push 2024; two-model quality routing only | 5.2k stars; Apache-2.0 |
| [RouterBench](https://github.com/withmartian/routerbench) | cached model outputs, costs, router evaluation, quality-cost curves | benchmark rather than a live provider allocator | 171 stars; last push 2024; MIT |
| [FrugalGPT](https://github.com/stanford-futuredata/FrugalGPT) | cascades, cost-quality data, and released generations | model/API cascade, not capacity-aware provider competition | 272 stars; last push 2025; Apache-2.0 |
| [BEST-Route](https://github.com/microsoft/best-route-llm) | query difficulty plus model and sample-count decisions | model-selection layer only | 66 stars; pushed 2026-07-02; MIT |
| [vLLM Semantic Router](https://github.com/vllm-project/semantic-router) | task/tool/complexity-conditioned demand and semantic cache experiments | chooses models/adapters rather than provider bids | 5.0k stars; pushed 2026-07-18; Apache-2.0 |
| [GuideLLM](https://github.com/vllm-project/guidellm) | Poisson/concurrent/sweep load generation against OpenAI-compatible endpoints | load generator, not a strategic market | 1.4k stars; pushed 2026-07-18; Apache-2.0 |

The [Vidur paper](https://arxiv.org/abs/2405.05465) reports less than 9% latency
estimation error over its evaluated range and makes the strongest case for a
separate systems-fidelity simulator. llm-d Inference Sim is more convenient for
executable router conformance because it is already a live OpenAI-compatible
server and its latency rises with concurrency.

### Tier 3: borrow the environment design

| Project | Design lesson | Reuse decision |
|---|---|---|
| [PettingZoo](https://github.com/Farama-Foundation/PettingZoo) | standard MARL API; Parallel API fits providers that update quotes at the same market tick | use as the public environment contract; MIT for Farama-owned code |
| [AuctionGym](https://github.com/amazon-science/auction-gym) | configurable repeated auctions, bidder policies, welfare/surplus/revenue metrics, logged counterfactual evaluation | adapt its separation of environment, bidder, mechanism, and metrics; Apache-2.0 |
| [ABIDES](https://github.com/jpmorganchase/abides-jpmc-public) | message-driven discrete-event market, heterogeneous agents, explicit latency, Gym wrapper | borrow architecture, do not take as a core dependency; JPMorgan repo is archived and its Gym API is old; BSD-3-Clause |
| [AI Economist](https://github.com/salesforce/ai-economist) | two-level planner/agent learning and welfare objectives | conceptual precedent only; official repo is archived and domain is distant |
| [RLlib MultiAgentEnv](https://docs.ray.io/en/master/rllib/multi-agent-envs.html) | scalable multi-policy training and PettingZoo wrapper | optional trainer; keep the environment independent of RLlib |

### Negative and lower-priority findings

- I did not find an official open-source implementation of the live
  provider-selection rule for OpenRouter, Cloudflare AI Gateway, Hugging Face's
  hosted Inference Providers router, Requesty, NemoRouter, TokenRouter,
  TrueFoundry AI Gateway, or Glama. Some expose clients, documentation, or
  observability, but that is not the allocation mechanism we need to test.
- [Routerly](https://github.com/Inebrio/Routerly) is a newer AGPL gateway with
  configurable cheapest/fastest/health/capability scoring. It is worth a later
  smoke comparison, but it has less research and production evidence than the
  Tier 1 projects and mixes model selection with provider selection.
- TensorZero has a rich Rust gateway and experiment stack, but its official
  GitHub repository was marked archived when checked on 2026-07-18. It should
  not become a new core dependency.
- Reverse proxies that only map model names to upstream URLs are not economic
  routers. They are useful mock infrastructure but do not add a mechanism
  comparison.

## Literature: what should transfer into the experiment

### LLM routing and systems

- [RouteLLM](https://arxiv.org/abs/2406.18665),
  [HybridLLM](https://proceedings.iclr.cc/paper_files/paper/2024/hash/b47d93c99fa22ac0b377578af0a1f63a-Abstract-Conference.html),
  [FrugalGPT](https://github.com/stanford-futuredata/FrugalGPT), and
  [BEST-Route](https://arxiv.org/abs/2506.22716) establish useful ways to map
  request features to model-level quality and cost. Their output can determine
  the request's model and gross user value before provider routing.
- [RouterBench](https://arxiv.org/abs/2403.12031) is useful because it exposes
  model outputs and costs for many prompt/model pairs. It gives the environment
  an observable quality frontier without issuing a fresh model call at every
  RL step.
- [RouteBalance](https://arxiv.org/abs/2606.17949) shows why load cannot be an
  afterthought. A price-only provider router may send too much flow to a cheap
  but congested endpoint, while a queue-only router may ignore quality and
  price. The market needs both quote and service state.
- [Vidur](https://arxiv.org/abs/2405.05465) supports a two-fidelity workflow:
  train in a fast surrogate, then validate queueing and latency conclusions in
  a calibrated serving simulator.

### Strategic pricing and platform design

- [Brown and MacKay](https://www.hbs.edu/ris/download.aspx?name=20-067.pdf)
  model firms with heterogeneous pricing frequency and algorithms that
  condition on rivals' prices. Faster firms can have lower prices and higher
  profits while raising rivals' equilibrium prices. That is a competitive
  mechanism, not automatically collusion. It motivates explicit quote clocks,
  observation delay, and linear rival-response agents.
- [Calvano, Calzolari, Denicolò, and Pastorello](https://www.ftc.gov/system/files/documents/public_events/1494697/calzolaricalvanodenicolopastorello.pdf)
  show that repeated Q-learning price setters can learn supra-competitive
  pricing with punishment and restoration phases. Their result motivates
  deviation tests and path-based diagnostics; high average price alone is not
  enough to label collusion.
- [Learning to Mitigate AI Collusion on Economic Platforms](https://proceedings.neurips.cc/paper_files/paper/2022/hash/f746974abd33c0015ca583a267dac1fd-Abstract-Conference.html)
  treats the platform's promotion or “buy box” rule as a Stackelberg POMDP and
  learns a router policy that protects consumer welfare against adaptive
  sellers. This is almost exactly the second-stage extension here: first train
  providers against fixed routers, then let the router choose score weights or
  eligibility rules as the leader.
- [AuctionGym](https://github.com/amazon-science/auction-gym) emphasizes why
  logged data alone are not enough for interactive bidding: counterfactual
  bids are unobserved, competitors adapt, and optimizing a logged proxy creates
  Goodhart problems. Historical replay is a calibration and evaluation mode,
  not a substitute for an equilibrium simulator.
- [Learn to Match with No Regret](https://proceedings.neurips.cc/paper_files/paper/2022/hash/7e0af0d1bc0ec2a90fc294be2e00447e-Abstract-Conference.html)
  supplies a planner-plus-strategic-agent formulation for Markov matching
  markets, including ridesharing. It is a useful theoretical language when the
  router controls matching under state transitions.
- [ABIDES-Gym](https://arxiv.org/abs/2110.14771) motivates an event-driven
  kernel when message latency and asynchronous actions matter. The first
  version can remain tick-based at five-minute quote epochs; Brown-MacKay timing
  experiments should later use event time within each epoch.

## Proposed environment

### Agents and timing

Start with provider agents and a fixed router. Do not make the harness, router,
and every user strategic in version 1.

At quote epoch `t`:

1. Each provider observes the public state and its private state.
2. Providers simultaneously choose quote and capacity actions.
3. A batch of requests arrives during the epoch.
4. The router creates an eligible set and selects a first provider and fallback
   sequence for each request.
5. Provider queues generate latency, success, and delivered quality.
6. Transfers, resource cost, penalties, profit, user utility, and welfare are
   recorded.
7. Public operational signals update with configurable delay.

Five-minute epochs match the capture surface. Within-epoch event time should be
optional for high-frequency reaction and last-look experiments.

### State

For provider `i`, model `m`, and epoch `t`, retain:

```text
public:  rival quotes, candidate set, reported latency/throughput,
         derank/rate-limit state, prior routed-share signal, model demand state
private: marginal-cost type or cost band, reserved capacity, queue,
         own realized requests, failures, revenue, quote clock
router:  policy, score weights, reliability beliefs, fallback rules
demand:  arrival intensity, request-length mix, tool/structured flags,
         model-level value and quality thresholds
```

The environment is a partially observable stochastic game. Providers should
not receive other providers' true capacity, costs, queues, or realized flow.
An “omniscient” state can be exposed only to a centralized critic and audit
code.

### Provider actions

Use a small continuous/discrete hybrid action:

```text
delta_log_quote       bounded price move or menu index
admitted_capacity     fraction of physical/reserved capacity offered
availability          active, degraded, or withdrawn
quote_ttl             optional stale-quote/refresh decision
quality_effort        later extension for quantization or fidelity
```

Price should be expressed as an input/output/request cost vector internally,
then collapsed to request cost only after the workload shape is known.

### Router interface

All routers should implement the same allocation contract:

```python
class RouterMechanism(Protocol):
    def reset(self, providers, seed): ...
    def eligible(self, request, public_state): ...
    def route(self, request, candidates, public_state, rng):
        """Return ordered attempts with selection probabilities and scores."""
    def observe(self, route_outcome): ...
```

Adapters:

1. `InverseSquareRouter`: exact existing public rule, `w_i=q_i^-2`.
2. `LowestCostRouter`: deterministic procurement benchmark.
3. `LiteLLMRouterAdapter`: call LiteLLM's real selection implementation or a
   custom strategy that reads the simulated provider registry.
4. `LLMDExecutableAdapter`: publish quote/capacity metrics, send requests
   through the real llm-d router, and ingest its selected endpoint.
5. `VLLMRouterAdapter`: round-robin, random, power-of-two, cache-aware controls.
6. `CapacityCertifiedRouter`: use this repository's proposed mechanism.

### Rewards and accounting

For delivered requests `y_it`, quote `p_it`, true resource cost `C_i`, reserved
capacity `k_it`, and delivery penalties `P_i`:

\[
\pi_{it}=p_{it}y_{it}-C_i(y_{it},k_{it})-P_i(\text{failure},\text{shortfall})
-r_i k_{it}.
\]

Provider agents maximize discounted profit, not routed share. Share can be a
diagnostic or an intentionally misspecified reward in a reward-hacking test.

User utility for request `r` is:

\[
u_r=V_r(\text{delivered quality})-\text{payment}_r
-\lambda_r\,\text{latency}_r-L_r\mathbf{1}\{\text{failure}\}.
\]

Closed-system social welfare must cancel transfers:

\[
W=\sum_r V_r-\sum_i C_i-\text{capacity capital cost}
-\text{failure/latency external cost}.
\]

Router fees and provider payments affect agent utilities and participation but
are transfers in global welfare unless money leaves the modeled system.

### Three operating modes

| Mode | Quotes/demand | Provider response | Valid use |
|---|---|---|---|
| historical replay | captured quote/candidate states; empirical model mix | frozen historical agents or one local perturbation | off-policy screening and router comparison conditional on history |
| calibrated counterfactual | fitted stochastic demand and provider types | all agents react and learn | equilibrium, welfare, entry, collusion, mechanism design |
| executable conformance | synthetic requests through LiteLLM/llm-d/vLLM Router | small number of scripted or learned policies | verify that surrogate router decisions and systems outcomes survive real code |

Historical replay cannot estimate the equilibrium effect of changing the
router rule while holding every historical quote fixed. Report it as a partial
equilibrium policy replay. General-equilibrium claims require the calibrated
counterfactual mode.

## Provider policy library

Every learned policy must be compared with transparent strategies:

1. **Static price taker:** fixed quote and fixed capacity.
2. **Author-price anchor:** quote the first-party/model-author reference price
   or a fixed multiplier. This captures providers that appear to copy a model
   author's list price.
3. **Cost-plus:** `p = markup * estimated marginal cost`.
4. **Undercut:** price one menu step below the cheapest rival, subject to a
   margin floor.
5. **Brown-MacKay fast reactor:** update at a provider-specific clock using a
   fitted linear function of the latest strictly prior rival move.
6. **Menu-cost/Calvo:** reprice only when the gain exceeds a threshold or a
   random quote clock opens.
7. **Capacity-aware shade:** raise price or withdraw capacity as queue load
   approaches a limit.
8. **Stale quote/last look:** leave a low public quote, then probabilistically
   reject or fade when demand arrives. This must be separately labeled because
   current public data do not identify it.
9. **Edgeworth cycle:** cut to fill spare capacity, then restore after queue or
   share crosses a threshold.
10. **Independent RL:** DQN/PPO/SAC policy over price menu and admitted capacity.
11. **Joint-profit oracle:** centralized upper bound, never called an observed
    strategy.

Fit transparent strategies before training neural policies. Behavioral cloning
from sparse quote events should output a distribution over strategy parameters,
not a claim that a named provider uses that strategy.

## Calibration plan

| Parameter | Repository evidence | Method | Required caveat |
|---|---|---|---|
| initial candidate sets and quotes | endpoint and routing-simulation snapshots | empirical bootstrap by model/scenario/date | captured public surface only |
| quote menu and change size | pricing events and PM5 menus | provider/type empirical distribution | interval-censored update time |
| quote frequency | BM1 cadence | provider/type hazard or renewal clock | observation cadence limits true frequency |
| rival-response rule | BM4 linked reactions | hierarchical regularized regression or behavioral-cloning prior | omitted common shocks; not causal strategy identification |
| provider type | H19 features, first-party/third-party tags | prespecified strata plus shrinkage; clustering only as sensitivity | costs/capitalization not observed |
| failure/fallback | owned `router_route_attempts` | model/provider/policy outcome model | controlled account only |
| service speed | public latency/throughput plus owned attempts | distribution conditional on model, provider type, and load | public measurements may be selection-biased |
| capacity | public ceilings where present, owned commitments/outcomes, llm-d/Vidur profiles | explicit low/base/high bands | no inference from financing announcements alone |
| model demand mix | app/model-token and ranking panels | day/type bootstrap or Markov transition | no provider-level app allocation |
| intraday arrivals | owned request timing or explicit synthetic Poisson/Hawkes design | fit only where arrivals are actually observed | do not infer market-wide arrivals from quote capture times |
| user value/quality | cached benchmark outcomes, eval battery, RouterBench | verifier/benchmark-specific utility mapping | benchmark quality is not universal user surplus |

Use a frozen calibration/validation split by date and model. Provider-specific
parameters need hierarchical shrinkage because many providers have few price
events. For costs, report conclusions over a cost identified set. Do not fill
missing cost with the listed GPU spot price and call it marginal inference cost.

## First experiment suite

| Experiment | Treatment | Primary estimand | What would count as support |
|---|---|---|---|
| E1 router mechanism benchmark | inverse-square, lowest cost, LiteLLM strategies, llm-d quote/load profiles, vLLM systems policies | welfare, user cost, failure, latency, provider profit, HHI | frontier and price-of-anarchy with uncertainty across held-out loads |
| E2 Brown-MacKay clock asymmetry | vary one provider's observation/update frequency holding cost/capacity fixed | profit, quote, share, rivals' prices | fast provider prices lower and earns more while rivals' prices rise; distinguish from collusion |
| E3 price elasticity and undercut race | vary inverse-price exponent and price tick/menu | markup, volatility, failure, consumer surplus | identify when stronger price weighting creates useful competition versus fragile concentration |
| E4 capacity/reserved-capital types | reserved/high-capacity vs elastic/small provider types | peak-load markup, admitted capacity, shortfall, entry profit | type differences explain price gaps after holding quality and demand fixed |
| E5 author-price anchoring | anchored, cost-plus, and reactive sellers | profit and survival across demand/load regimes | determine when reference-price copying is rational versus dominated |
| E6 stale quote and phantom liquidity | allow quote TTL and post-route rejection | attempted versus served share, adverse selection, fallback cost | cheap stale quotes attract allocations but worsen delivery and welfare |
| E7 emergent coordination | independent RL sellers under fixed routers | collusion index, deviation gain, punishment/restoration path, exploitability | supra-competitive prices plus low unilateral deviation gain and path evidence, robust across seeds/algorithms |
| E8 anti-collusion router | router leader adjusts score weights, exploration, derank, or penalties | user welfare subject to reliability and participation | Stackelberg policy improves welfare out of sample against unseen seller types |
| E9 entry and fragmentation | add providers with capacity/setup cost and cache fragmentation | welfare, price, concentration, latency | locate the point where free entry stops helping because thin flow/cache loss raises cost |
| E10 model-provider interaction | enable a harness/model router before provider routing | end-to-end quality/cost/welfare and provider investment incentives | quantify whether model substitution disciplines or weakens same-model provider competition |

### Collusion and market-power diagnostics

Do not use “prices rose” as the test. Report:

- competitive, learned, and joint-profit benchmark prices;
- normalized collusion index between competitive and joint-profit outcomes;
- one-shot and dynamic unilateral deviation gains;
- best-response exploitability or coarse-correlated-equilibrium regret;
- impulse responses to an exogenous one-provider undercut;
- punishment depth and restoration time;
- leave-one-provider-out and new-entrant response;
- robustness across RL algorithms, action grids, exploration schedules, random
  seeds, capacity types, and demand processes.

This separates Brown-MacKay competitive commitment, Edgeworth capacity cycling,
and Calvano-style learned coordination.

## Architecture and build sequence

### Phase 1: fast deterministic market kernel

- Add `src/orcap/market_env/` with immutable dataclasses for request, provider
  state/action, route attempt, and settlement.
- Implement the existing inverse-square and lowest-cost policies behind
  `RouterMechanism`.
- Implement queues, capacity, failures, costs, transfers, profit, user utility,
  and welfare without any RL dependency.
- Add deterministic scenario fixtures and accounting invariants: allocation
  sums, no capacity over-service, transfer cancellation in welfare, replay
  reproducibility.

### Phase 2: PettingZoo contract and scripted strategies

- Wrap the kernel in `InferenceMarketParallelEnv`.
- Providers act simultaneously at quote epochs; request processing is an inner
  event loop.
- Add all transparent baseline strategies and random-policy tests.
- Use PettingZoo's `parallel_api_test` and version the environment as `v0`.

### Phase 3: historical calibration and replay

- Build explicit adapters from curated tables to calibration artifacts; never
  let the environment query mutable analysis outputs ad hoc.
- Freeze train/validation/test dates, models, provider strata, and cost bands.
- Fit quote clocks, menu transitions, reaction priors, service distributions,
  and demand mix with hierarchical shrinkage.
- Publish a calibration data card and posterior/predictive checks.

### Phase 4: RL and equilibrium experiments

- Start with tabular Q-learning on a two-provider, one-model environment to
  reproduce competitive and joint-profit benchmarks.
- Add independent PPO/SAC only after scripted best responses behave correctly.
- Train across many vectorized pure-Python environments. Use RLlib as an
  optional trainer, not an environment dependency.
- Freeze evaluation seeds and compute deviation/exploitability audits after
  training.

### Phase 5: executable router conformance

- **LiteLLM first:** map each simulated provider to a local mock deployment and
  compare the real selected deployment with the surrogate adapter for weighted,
  cost, least-busy, usage, and custom quote rules.
- **llm-d second:** run multiple llm-d Inference Sim instances, publish quote and
  capacity metrics, add a `q^-eta` scorer, and compose it with queue/latency
  scorers and the stock weighted-random picker.
- **vLLM Router control:** run the same providers under round-robin,
  power-of-two, and cache-aware policies.
- Record every executable route in the existing payload-free
  `router_route_attempts` schema with a dedicated synthetic study ID.

### Phase 6: paper-quality experiment release

- Pre-register router policies, provider policy classes, cost bands, demand
  processes, seeds, estimands, and promotion gates.
- Produce one table/figure family per experiment, including negative results.
- Keep synthetic equilibrium claims separate from empirical estimates and from
  live-router conformance.

## Validation gates

1. **Accounting:** provider payments plus router transfers reconcile; welfare
   excludes internal transfers; no request is served beyond capacity.
2. **Router equivalence:** on fixed states, the surrogate and executable router
   agree on candidate eligibility and selection frequencies within Monte Carlo
   error.
3. **Queue fidelity:** llm-d/Vidur latency, failure, and throughput distributions
   match the fast kernel over a held-out grid before systems conclusions are
   promoted.
4. **Historical predictive validity:** fitted baseline strategies predict held-out
   quote/capacity actions better than provider-type and state-only nulls.
5. **Equilibrium robustness:** qualitative conclusions survive seeds, RL
   algorithms, action discretization, exploration, and random provider labels.
6. **Strategic identification:** named-provider behavior is never inferred from
   a fitted synthetic agent. Provider names are used for calibration only; the
   experiment reports type-conditioned counterfactuals.
7. **External validity:** repeat the principal router comparison under at least
   LiteLLM and llm-d, not just the in-repo inverse-square implementation.

## Practical recommendation

Build the pure-Python/PettingZoo kernel and LiteLLM conformance adapter first.
This machine already has Python 3.12 in the repository environment, which is a
good fit for PettingZoo and LiteLLM. It currently lacks Go and a visible Docker
client, so the llm-d executable suite should run in a remote Linux CI/VM with
Go, containers, and optionally Kind. Do not block environment development on
that infrastructure.

The minimal publishable loop is:

```text
historical quote/provider calibration
        -> fast multi-provider PettingZoo game
        -> scripted and RL bidding policies
        -> router/welfare/collusion comparisons
        -> LiteLLM and llm-d executable conformance
        -> held-out historical and systems validation
```

The main scientific risk is not code availability. It is calibration and claim
scope: public data observe quotes far better than marginal costs, physical
capacity, or realized market-wide flow. The environment can sharply compare
mechanisms and reveal possible strategic behavior, but it should report cost
bands and type-conditioned counterfactuals unless partner data identify those
private primitives.
