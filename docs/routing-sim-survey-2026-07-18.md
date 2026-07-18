# Survey: building blocks for a multi-agent simulation / RL environment of the router-provider game

*2026-07-18. Five parallel research passes (model-level routers, infra-level
routers, serving simulators/traces, market MARL environments, academic
literature); repo file paths verified by fetching GitHub trees. Purpose:
identify open-source routing code we can test strategies against directly,
and the components for a provider-bidding simulation calibrated to orcap
data. Items not directly confirmed are marked unverified.*

## Headline findings

1. **OpenRouter's routing engine is closed-source, but documented precisely
   enough to reimplement in ~20 lines**: a stability filter (deprioritize
   providers with significant outages in the last 30s), then price-weighted
   load balancing with **inverse-square weighting** (a $1/M provider is 9×
   more likely to be picked first than a $3/M one), remaining providers as
   fallback order; `sort: price|throughput|latency` (`:floor`, `:nitro`)
   disables load balancing. Source: openrouter.ai/docs/features/provider-routing.
   The GitHub org (OpenRouterTeam) contains only SDKs/examples.
2. **Closest importable open proxy: LiteLLM's `router_strategy/` package**
   (Python, MIT) — the only open code whose signal set (price, latency,
   TPM/RPM load, busyness) matches OpenRouter's quote schema.
3. **No open-source router uses price to pick among competing providers.**
   Infra-level routers (vLLM production-stack, llm-d, NVIDIA Dynamo, SGLang,
   AIBrix) have rich load/KV-cache cost functions but assume cooperative
   homogeneous replicas; gateways (Portkey, Envoy AI Gateway) use static
   weights/failover. Grafting price into these cost functions is itself a
   research contribution.
4. **Open slot: nobody combines strategic provider price-setting + a real
   router policy + OpenRouter-calibrated data.** Nearest paper: PriLLM
   (Stackelberg routing game, arXiv:2511.09062, no code). Empirical anchor:
   Demirer–Fradkin–Peng–Tadelis (NBER WP 34608) — 10× same-model
   cross-provider dispersion on OpenRouter, short-run elasticity ≈ 1.

## 1. Routers / gateways (policy code)

Marketplace/provider level:

| System | Where the policy lives | Signals | Verdict |
|---|---|---|---|
| OpenRouter | closed; algorithm in docs | 1/p² price weights, 30s outage window, throughput/latency sorts | reimplement (easy; ground truth) |
| LiteLLM Router (BerriAI/litellm, MIT) | `litellm/router.py` + `litellm/router_strategy/`: `lowest_latency.py`, `lowest_cost.py`, `least_busy.py`, `lowest_tpm_rpm_v2.py`, `simple_shuffle.py`, newer `adaptive_router/`, `quality_router/` | latency-per-token + TTFT, per-token cost, TPM/RPM vs limits, in-flight | **drop-in/adapt — best match**; strategies are classes fed by an in-memory `DualCache`; push synthetic observations via `log_success_event`, call `_get_available_deployments()` |
| RouteLLM (lm-sys, Apache-2.0) | `routellm/routers/routers.py` (matrix factorization, BERT, SW-ranking) | prompt quality only | drop-in for the quality axis; not provider-level |
| Martian routerbench (MIT) | baseline `AbstractRouter` impls; production closed | quality vs cost offline | adapt (benchmark harness) |
| Portkey Gateway (TS, MIT) | `src/handlers/handlerUtils.ts` `tryTargetsRecursively()` | static weights, health | reimplement (trivial) |
| Kong AI Gateway | OSS basic `ai-proxy`; EWMA/lowest-usage LB is enterprise-closed | — | reimplement |
| Not Diamond RoRF (MIT) | pairwise random-forest router | quality | adapt |
| Helicone AI Gateway (Rust, GPL-3.0) | `ai-gateway/src/router/{strategy,latency}.rs`; P2C + Peak-EWMA | latency, weights, cost, health | reimplement (~50-line known algorithm; GPL) |
| Cloudflare/Vercel gateways | closed (ordered fallback) | — | skip |

Infra/cluster level (all Apache-2.0, none price-aware; renames post-2025:
`llm-d-inference-scheduler` → `llm-d/llm-d-router`; SGLang `sgl-router/` →
`sgl-model-gateway/`; Dynamo scoring factored into crate `lib/kv-router/`):

| System | Policy | Verdict |
|---|---|---|
| vLLM production-stack | `src/vllm_router/routers/routing_logic.py` (~753 lines): round-robin, session-hash, KV-aware (LMCache), prefix-aware `HashTrie`, disagg-prefill | drop-in for 4/6 strategies (plain dataclasses in, endpoint out) |
| llm-d router (Go) | `pkg/epp/scheduling/` + `.../plugins/scheduling/{scorer,filter,picker}/` — weighted sum of ~15 scorers (queue depth, KV util, prefix match `w·len² + (1−w)·ratio`, session/LoRA affinity, SLO headroom), YAML weights, argmax/softmax pickers | adapt or easy reimplement; richest scorer zoo; `file-discovery` mode runs without k8s |
| NVIDIA Dynamo (Rust+PyO3) | `lib/kv-router/scheduling/selector.rs`: `logit = prefill_load_scale·(prefill_blocks − overlap_credit) + decode_blocks`, temperature softmax | near drop-in (Python `KvRouter`, standalone HTTP selection service, mooncake-trace replay harness) |
| AIBrix (Go) | `pkg/plugins/gateway/algorithms/`: least-request/throughput/KV/latency, power-of-two, prefix-cache, SLO, **`vtc-basic` per-user Virtual Token Counter fairness** | reimplement; VTC is the interesting port |
| SGLang router (Rust, pip `sglang-router`) | `sgl-model-gateway/src/policies/cache_aware.rs`: two-threshold imbalance trigger → shortest queue, else prefix radix match, else min-load | drop-in via pip; simplest realistic cache-aware policy |
| Envoy AI Gateway (Go) | static weight+priority → Envoy clusters; CEL token-cost only for rate limits | reimplement ~20 lines; the one genuinely inter-provider OSS router — borrow its backend/cost schema vocabulary |

Motifs to encode as simulator primitives: (a) cache-overlap credit vs load
cost combined linearly; (b) imbalance-triggered override of cache affinity;
(c) weighted-sum-of-normalized-scores + argmax/softmax — softmax temperature
maps directly onto a logit-demand router, the same functional form as
Calvano-style demand; (d) VTC fairness counters.

## 2. Serving simulators & load traces

- **Vidur** (microsoft/vidur, MIT, MLSys'24) — trace-driven DES of one LLM
  deployment (continuous batching, vLLM/Sarathi schedulers, learned latency
  predictors; TTFT/TPOT out; ingests Azure trace CSVs). Per-provider latency
  oracle for validation runs.
- **SplitwiseSim** (mutinifni/splitwise-sim, MIT) — cluster-level DES;
  `generate_trace.py` pulls Azure traces.
- **DistServe `simdistserve/`** (Apache-2.0) — goodput-optimal placement
  optimizer (per-provider capacity choice).
- **InferSim** (alibaba/InferSim, Apache-2.0) — zero-dependency analytical
  TTFT/TPOT from model+GPU config: drop-in cheap latency function.
- **M/G/1-with-batching queueing model** (arXiv:2407.05347) — closed-form;
  reimplement as the fast inner-loop latency oracle.
- **llm-d-inference-sim** (Go) — fake vLLM endpoint with load-dependent
  latency (if the sim talks HTTP).
- Traces: **Azure LLM inference traces** 2023 (1 day) + 2024 (1 week)
  (Azure/AzurePublicDataset, CC-BY-4.0; `TIMESTAMP, ContextTokens,
  GeneratedTokens`); **BurstGPT** (HPMLL, CC-BY-4.0, ~121 days, ~10.6M rows,
  per-request model choice + failures — only trace with demand-side model
  selection); **Mooncake** FAST'25 traces (~40K requests with `hash_ids`,
  only public prefix-reuse encoding); **ServeGen** (alibaba, Apache-2.0) —
  workload generator fitted to Alibaba production, per-client `ClientPool`,
  non-Poisson bursts: best demand-side component, per-client generators map
  onto consumer agents. Or replay orcap's own captured congestion/flow panel.

## 3. Market / MARL environments

- **PettingZoo + Gymnasium** (MIT) — the API layer; `ParallelEnv` fits
  simultaneous price posting; no built-in pricing env exists (a
  router-pricing PettingZoo env is itself a contribution).
- **ASSUME** (AGPL-3.0) — electricity-market ABM with built-in MARL bidders
  and pluggable clearing; closest full-stack analog but AGPL + energy
  abstractions.
- **AuctionGym** (amzn, Apache-2.0) — repeated auctions with learning
  bidders; invert buyer-bidding to seller-posting; small enough to gut.
- **AuctionNet** (alimama, Apache-2.0, NeurIPS'24) — 48-agent auto-bidding
  benchmark; mine for bidding baselines (IQL, TD3+BC, decision transformers).
- **OpenSpiel** (Apache-2.0) — equilibrium diagnostics (CFR, NashConv/
  exploitability) on the discretized pricing game; use alongside.
- **ABIDES / ABIDES-gym** (BSD-3, archived 2025-06) — DES market kernel;
  only if event-level latency realism becomes central.
- **AI Economist** (BSD-3, archived) — two-level agents+planner pattern
  (providers + router-as-designer) as reference.
- **EconoJax** (Apache-2.0, AAMAS'25) — end-to-end JAX env+PPO template
  (100 learning agents ≈ 15 min).
- No maintained, licensed Bertrand gym exists — genuinely empty niche.

## 4. Academic anchors (code-first)

- **Calvano et al. (2020 AER)** Q-learning collusion: official Fortran at
  openICPSR E119462; replications matteocourthoud/Algorithmic-Collusion-
  Replication (MIT) and JacobSKN/replication_calvano (MIT, n>2 firms +
  asymmetric cost/quality — useful for heterogeneous providers). Metric:
  profit gain Δ = (π−π_N)/(π_M−π_N).
- **Klein (2021 RAND)** sequential pricing → Edgeworth cycles (no code) —
  relevant because providers reprice asynchronously (our pm-series result).
- **Asker–Fershtman–Pakes** (openICPSR E159401); **Abada–Lambin** (collusion
  from incomplete exploration — identification caution); **Johnson–Rhodes–
  Wildenbeest (2023 Ecta)** platform steering rules that break collusion —
  the classical "router as market designer" paper (we already test its
  cut-penalty analog in wf2); **Banchio–Skrzypacz** (EC'22).
- Deep-RL envs: **mesjou/price_simulator** (MIT, cleanly factored — best
  small env to fork); ToFeWe/qpricesim (MIT, numba sweeps);
  **pfriedric/EpisodicCollusion** (Apache-2.0, JAX, capacity-constrained —
  closest structure to GPU-limited providers); Deng–Schiffer–Bichler
  (arXiv:2406.02437): PPO/DQN converge near Nash where tabular Q colludes
  (calibrates expectations); Hansen–Misra–Pai (2021): misspecified bandits →
  supra-competitive prices (arguably the most realistic provider model).
- LLM-agent pricing: Fish–Gonczarowski–Shorrer (arXiv:2404.00806, EC'26, no
  official code); runnable: sara-fish/econ-evals-paper (MIT, collusiveness
  litmus) and luciasauer/algorithmic_pricing_llms (MIT). Also market
  division (arXiv:2410.00031), communication-induced collusion (EMNLP'24),
  heterogeneity fragility (arXiv:2603.20281), monoculture phase transition
  (arXiv:2601.01279), platform rules beat prompt guardrails 50%→5.6%
  (arXiv:2601.11369). **Microsoft Magentic-Marketplace**
  (microsoft/multi-agent-marketplace, MIT) — two-sided LLM buyer/seller
  market with platform matching layer; closest open chassis.
- Cloud pricing: Ben-Yehuda et al. (EC2 "spot" = administered reserve band —
  a provider-pricing regime to include); Kilcioglu et al. WWW'17 (flat
  utilization rationalizes posted prices — the null to beat); Feng–Li–Li
  (capacity-constrained IaaS Bertrand, no code); skypilot + spot-traces
  (live GPU price catalogs; only public preemption traces).
- LLM API market: **Demirer–Fradkin–Peng–Tadelis (NBER 34608)** calibration
  anchor; Fradkin (arXiv:2504.15440); 100T-token study (arXiv:2601.10088);
  **PriLLM (arXiv:2511.09062)** — differentiate from this; Bergemann–
  Bonatti–Smolin token-pricing screening (arXiv:2502.07736); token auctions
  (arXiv:2310.10826). Provider deviation actions: token-count misreporting
  (ICML'26, code: Human-Centric-Machine-Learning/token-pricing), metering
  fraud auditing (arXiv:2510.05181), covert quantization (arXiv:2504.04715)
  — the same behavior our eval probes now measure in the real market.

## Recommended architecture

Custom **PettingZoo `ParallelEnv`** market loop (fork mesjou/price_simulator
or EpisodicCollusion skeleton): each step providers post (price, capacity) →
demand batch arrives (ServeGen generators calibrated to Azure/BurstGPT, or
replayed orcap panel) → pluggable ROUTER policy allocates → per-provider
queues resolve latency (InferSim or M/G/1 oracle inner loop; Vidur for
validation) → rewards = revenue − serving cost. Router module three tiers:
(a) hand-rolled OpenRouter inverse-square policy (ground truth; its softmax
form makes the router a logit-demand system, so the provider game nests
Calvano's structure exactly); (b) imported LiteLLM strategies as
counterfactual designs; (c) reimplemented infra motifs (Dynamo overlap-
credit softmax, SGLang imbalance trigger, AIBrix VTC) with price grafted in
(novel). Evaluate with Calvano Δ, EconEvals collusiveness litmus, OpenSpiel
exploitability; calibrate heterogeneity/dispersion to Demirer et al. and to
our own wf13 species (fit provider strategies to observed adopter/
undercutter behavior). No existing project combines these layers — the
integration is the paper.
