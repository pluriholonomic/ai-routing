# A welfare framework for AI inference routing

*Registered 2026-07-16. Synthesis of three literature sweeps (contract theory /
principal-agent; queueing-game welfare; collusion theory — full reports in
session transcripts) plus the empirical base (memo, CBH, pm-series). This
document fixes: the field combination, the planner and agent optimization
problems, the decentralization conjecture (when selfish = efficient), and the
collusion manifestation map with discriminating statistics.*

## 1. The field combination

No single literature models this market. Five components, each owning a layer:

| Component | Owns | Core imports |
|---|---|---|
| **Queueing-game welfare economics** | the physical layer + planner problem | Naor tolls; Mendelson-Whang IC priority pricing (first-best!); Chao-Wilson menus; Kleinrock conservation; Joskow-Tirole missing money; Halfin-Whitt scaling; LRD corrections (Norros) |
| **Asynchronous pricing games** (Brown-MacKay; Maskin-Tirole) | the quoting layer's equilibrium concept | frequency asymmetry = commitment; kinked-demand focal-price MPE; menu-cost hazard = the frequency technology |
| **Common agency + delegated shopping** (Bernheim-Whinston; Inderst-Ottaviani; Hagiu-Jullien; Edelman-Wright) | the router/harness incentive chain | contribution-schedule efficiency *on the contractible manifold only*; steering with kickbacks; search diversion; price coherence |
| **Multitask moral hazard + certification** (Holmstrom-Milgrom; Diamond; Lizzeri) | the quality/integrity layer | measured-vs-unmeasured task substitution; router as delegated monitor; coarse pass/fail disclosure |
| **Repeated games with imperfect monitoring + algorithmic commitment** (Athey-Bagwell-Sanchirico; Green-Porter; Salcedo; Calvano; JRW) | conduct | rigidity as optimal collusion; router steering rules as (de)stabilizers |

Glue: an **aggregative / mean-field structure** — each provider best-responds
to the router's weight functional and an aggregate load field, not to named
rivals (Weintraub-Benkard-Van Roy oblivious equilibrium; Maglaras-Zeevi for
capacity scaling).

## 2. Primitives

Users θ ~ F: value v(θ), delay cost c(θ), rejection loss ℓ(θ) ≤ v(θ), quality
sensitivity q(θ). Harnesses choose retry/burst policy σ_h; effective arrivals
are long-range dependent (measured Fano ~1000, Hurst H ≈ 0.84), so delay obeys
W ~ (1-ρ)^{-H/(1-H)} ≈ (1-ρ)^{-5.25}, not the M/M/1 (1-ρ)^{-1}. Providers i:
capacity μ_i (cost k(μ_i)), marginal cost c_i, hidden fidelity a_i (quality),
sticky posted price p_i (adjustable at attention-cost dates ψ), tier menu
(priority/standard/batch/free), rationing rate r_i. Router: allocation x,
admission/deferral A, fee τ, rebates b, monitoring M, disclosure D, derank
state (reputation weight). Author: candidate anchor price p0 (the selected-tie
match is mechanically non-discriminating; across all author-observable markets,
third-party exact matches at p0 exceed adjacent dime-grid placebos by 53.3 points,
pending the frozen 30-date replication).

## 3. The planner problem

max over {x, A, μ, a, tiers, scheduling}:

    W = ∫ v(θ)(1 - r(θ)) λ(θ) dF          (completed value)
      - ∫ c(θ) D(θ) λ(θ) dF               (delay costs)
      - ∫ ℓ(θ) r(θ) λ(θ) dF               (rejection losses)
      - Σ_i [k(μ_i) + c_i X_i]            (capacity + serving costs)
      - ∫ q(θ)(1 - a_i(θ)) λ(θ) dF        (quality-degradation losses)

s.t. LRD queueing law, stability, Kleinrock conservation within provider,
retry feedback λ_eff = λ0 (1 + g(r, σ_h)).

Planner FOCs: (P1) Gcμ scheduling (tiers = its coarse implementation);
(P2) Naor-generalized admission: serve now iff v(θ) ≥ c_i + E_i where E_i =
marginal delay + rejection externality; (P3) Beckmann routing: equalize
c_i + E_i + quality wedge across used providers; (P4) capacity: k'(μ_i) =
scarcity value, with LRD implying buffers ~ load^H (super-square-root —
independently rationalizing measured overcapacity).

## 4. Agent problems

- **User θ** (chooses tier m, volume): max [v(θ) - P_m] λ (1 - r_m) - c(θ) W_m λ
  - ℓ(θ) r_m λ, with beliefs about unobservable quality — IR binds on beliefs.
- **Harness**: max (s - P) Q_h(retention(quality_{lagged})); joins router iff
  fee ≤ switching cost + failover value. Retries are free beyond price paid —
  the unpriced margin.
- **Router**: max Σ_i (τ p_i + b_i) x_i Q - m·M - reputational liability(D, M),
  choosing (x, τ, b, M, D). Its best-execution duty is unverifiable
  (Macey-O'Hara) — no binding no-steering constraint exists.
- **Provider i**: max [p_i - c(a_i)] x_i(p, ℓ(a_i, load), r_i; derank state) Q
  - k(μ_i) - ψ·1{reprice}, hidden action a_i, capacity constraint, derank
  dynamics weight_{t+1} = h(weight_t, r_i, W_i).
- **Author**: max (p0 - c0) q0 + λ_adopt · Adoption(Σ x_i Q) — no royalty
  channel; p0 is a Stackelberg anchor trading margin against adoption.

Binding constraints (from the contract sweep): provider fidelity IC corners at
a_min absent monitoring (multitask: fidelity substitutes for measured
latency/price); downward-adjacent tier IC (Chao-Wilson screening rents);
harness participation (fee = switching cost + failover value; the 20x
elasticity wedge means provider rebate competition transfers to the router,
not users). Slack: user IR (large surplus), provider price FOC except at
attention dates (hence anchor-following as the zero-attention heuristic).

## 5. The Decentralization Conjecture

**Selfish optimization attains W\* iff C1-C10 hold.** Grouped, with current
empirical status where measurable:

**Mechanism conditions**
- **C1 Tier prices = externality differences** (Mendelson-Whang under the
  Gcμ order, computed under LRD delay laws). n=4 tiers loses only O(1/n²)
  (Wilson) — coarseness is second-order. *Status: untested (the Chao-Wilson
  calibration test, pre-registered).*
- **C2 Router objective = aggregate user surplus + Pigouvian internalization.**
  A near-monopoly router controlling most flow self-internalizes the routing
  externality (atomic splittable ⇒ Wardrop planner for free); it must also do
  Naor admission (reject when v < c + E). Fill-rate or GMV objectives break
  the admission margin; competing routers give atomic-splittable PoA ≤ 3/2
  (affine) but unbounded near saturation. *Status: unknown — the neutrality
  audit (probes) is the test; note the anti-intuition: router concentration is
  allocatively GOOD here.*
- **C3 No missing money** (Joskow-Tirole): the sticky price is a hard cap, so
  first-best capacity needs scarcity rents from elsewhere: state-contingent
  priority premia + the shadow value of avoided deranking (an implicit
  capacity payment in reputation currency) + committed-throughput contracts.
  *Status: overcapacity observed ⇒ the deranking penalty currently ≥ missing
  money; testable — capacity should comove with derank-rule severity, not
  posted price.*
- **C4 Value-ordered rationing** (Chao-Wilson/Wilson): throttle free first,
  then batch, then standard, then priority; random within-tier 429s are a
  FIRST-ORDER loss (misordered service), unlike tier coarseness. *Status:
  tier ordering holds (free rationed hardest, conditional on cost — measured);
  within-tier ordering unknown; anonymous rate-limiting suggests partial
  violation.*

**Structure conditions**
- **C5 No pivotal provider** (Allen-Hellwig limit / Acemoglu-Ozdaglar bounds:
  allocative efficiency ≥ 5/6 even under oligopoly with zero latency at zero
  flow). *Status: plausible off-peak; pivotality in shortage states untested.*
- **C6 Entry margin**: business stealing over identical models ⇒ excess entry
  in N (Mankiw-Whinston); harmless iff per-provider fixed costs are small
  relative to capacity costs. *Status: 70 providers, flat entry-demand slope
  (CBH-14) — consistent with cheap listing; waste concentrated in duplicated
  fixed costs if any.*
- **C7 Retry internalization — the novel wedge.** Free retries amplify demand
  exactly in shortage states (positive feedback with no Naor analog: balking
  is replaced by retrying). First-best needs priced retries or enforced
  backoff, with all supporting prices computed under LRD (Poisson-calibrated
  tolls are badly underscaled at W ~ (1-ρ)^{-5.25}). *Status: violated —
  retries are free everywhere; magnitude unmeasured (retry-storm share of
  shock amplification is measurable from the congestion panel).*

**Information/contract conditions**
- **C8 Fidelity monitoring** (multitask + Diamond): allocation weight on
  measured (p, latency) with unmeasured quality drives a_i → a_min; remedy is
  router-as-delegated-monitor. Lizzeri predicts a monopoly certifier issues
  coarse pass/fail badges and keeps the rent; only certifier competition
  yields fine disclosure. *Status: no attestation exists (I-layer); outside
  audits already find ~1/3 endpoint divergence.*
- **C9 No kickback steering / wary harnesses** (Inderst-Ottaviani +
  Edelman-Wright): the zero visible spread is the EQUILIBRIUM DISGUISE, not
  proof of neutrality — competition through commissions migrates margin into
  hidden rebates, and price coherence (measured: 99.6% parity) blocks the
  disciplining arbitrage while inflating posted prices for everyone. *Status:
  unobserved dimension — instrument provider-router compensation (rebates,
  preferential rate limits); the R2 scorecard row is hereby downgraded from
  'no extraction' to 'no extraction via spread.'*
- **C10 No common delegation** (Bernheim-Whinston 1985): providers delegating
  pricing to a common vendor or the router implements joint monopoly in ONE
  SHOT — no repetition needed. *Status: unknown; vendor-overlap dyadics are
  the test (RealPage legal line: shared algorithms on nonpublic data).*

**The conjecture, stated once:** the decentralized market is approximately
efficient on the routing and scheduling margins (C2 partially, C1/C4 tier
structure, second-order coarseness losses, PoA-bounded competition), while
its first-order welfare risks are exactly four: the router's objective (C2
admission margin), quality shaving absent certification (C8), hidden
origination-side steering (C9), and unpriced retries under long-memory demand
(C7) — with capacity adequacy (C3) currently rescued by an improvised
reputation-based capacity market that no one designed.

## 6. How collusion shows up

Five margins (full map with objectives in the collusion sweep). Each row:
collusive object → competitive twin → discriminating statistic (module).

1. **Price level**: SPPE supra-competitive p̂ → Brown-MacKay commitment /
  AFP asynchronous learners → margin vs residual-demand-elasticity benchmark;
  B-M twin rejected where exact ties (B-M ⇒ strict dispersion); AFP twin
  rejected where cut-IRFs show reactivity (pm6).
2. **Rigidity/ties**: Athey-Bagwell-Sanchirico pooling — *rigidity IS optimal
  collusion under private costs* → menu costs / anchor-copying → pass-through
  at LARGE cost shocks: (S,s) pierces, ABS pooling survives with ties intact
  (test fires on the next hardware-cost transition); tie propensity invariant
  in N ⇒ collusion, declining ⇒ copying (cbh2/pm5).
3. **Leadership/excitation**: Mouraviev-Rey sequential-move + Maskin-Tirole
  kinked-demand focal MPE (matches our data cell: no sawtooth, 66%
  raise-following = restoration) → B-M fast-follower / common cost shocks →
  Hawkes cross-excitation α_ij vs baseline after cost conditioning (pm3);
  follow-lag tightening over time = Byrne-de Roos learning curve.
4. **Focal anchoring**: Knittel-Stango equilibrium selection at p0 + Bos-
  Harrington umbrella (core ties at p0, fringe below at full utilization) →
  p0 as cost/certification sufficient statistic → re-tie speed after
  exogenous p0 moves (pm9, armed); core-slack/fringe-full utilization
  cross-section; dyadic vendor-overlap tests.
5. **Rationing/quantity**: Athey-Bagwell share favors implemented as
  coordinated 429s under rigid prices → independent capacity management →
  r_it = f(util) + γ(share deficit) + η(rival refusals): γ, η > 0 = collusion
  cell. *Theoretical prior: ABSENT (Sannikov-Skrzypacz impossibility at high
  frequency) — so a positive finding here would be major.*

**The router is both the cheapest detector and a potential hub** (Harrington
2018 dual role): it observes fills, holds the enforcement instrument
(deranking), and — per Johnson-Rhodes-Wildenbeest (Ecta 2023) — its own
steering rule is a collusion parameter: lowest-price-wins steering does NOT
destabilize collusion (the cartel ties and shares prominence — our 46% tie
rate is partly an equilibrium object of the router's tie-breaking), while
dynamic persistent-prominence-for-past-undercutting steering provably does.
JRW is simultaneously a test (do past undercutters gain persistent weight? —
answerable from realized-routing probes) and the remedy.

Audit statistics adopted: Calvano IRF with persistence check (pm6, running);
calibrated regret per provider (Hartline et al. 2024-25 — computable from
quotes + allocations; threat-free collusion evades IRF screens, so run both);
Assad both-adopt overlay on every statistic.

## 7. New tests this framework adds (pre-registered here)

1. Pass-through at large cost shocks (ABS vs menu-cost) — fires on the next
   GPU-generation price transition.
2. JRW steering audit: persistent-prominence response to past undercutting,
   from router_route_attempts.
3. Calibrated-regret statistic per provider.
4. Adoption diff-in-diff (Brown-MacKay technology stage): when a provider
   turns algorithmic, do RIVAL price levels rise?
5. Dispersion horse race: gap floor vs cadence-gap (B-M commitment) against
   gap floor vs pinned-share (loyal flow).
6. Retry-externality measurement: retry-storm share of demand amplification
   in shortage windows (congestion panel + probe retry telemetry).
7. Kickback instrumentation (C9): provider-router compensation in non-price
   dimensions — rate-limit asymmetries by provider, rebate disclosures,
   preferential-placement audits.
8. Capacity ~ derank-severity comovement (C3's implicit capacity market).
9. Tie-level margin vs fringe utilization (Bos-Harrington umbrella
   cross-section).
10. Merger amplification (B-M): conditional pre-registration — provider M&A
    price effects increasing in market algorithmic saturation.
