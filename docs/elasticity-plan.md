# Elasticity measurement program (H28-H32)

The market is a three-layer chain: **GPU capacity → provider quotes → router
allocation → end demand**. Each link has an elasticity, each with its own
identification problem, and the micro (single-quoter) and macro (quote-
distribution) levels must be modeled separately and then bridged. This plan
defines every estimand, its estimator, its identification strategy, and its
power timeline. All modules join the nightly power-gated queue.

Notation: model m, provider i, time t. Posted price p_imt, routed share
s_imt, model demand D_mt (tokens), effective paid price P_mt, GPU rent g_ct
(class c ∈ {H100, H200, B200, ...}), utilization u_imt.

---

## The simultaneity problem (why naive regressions fail here)

We have now *demonstrated* the feedback loop: providers with ~zero share cut
prices to attract flow (routing-feedback repricing), so price causes share AND
share causes price; demand causes price (H20's premise) AND price causes
demand. Every elasticity below states its identification through this loop:

- **Event-timing**: quotes move discretely (jumps at known 5-min-stamped
  times), shares/demand move continuously — short windows around quote jumps
  identify the demand-side response (high-frequency identification, as in
  monetary-shock event studies). Requires the jump to not be caused by
  within-window share news; the 5-min stamps and burst windows make the
  window tight enough.
- **Supply-side instruments** for demand elasticities: provider entry events
  (H26), provider-wide repricing waves (fleet policy, orthogonal to model-m
  demand), quantization additions, GPU-rent shocks.
- **Demand-side instruments** for supply responses: HF-hub trending shocks
  and app-adoption shocks (harness releases) that shift model demand without
  reference to any provider's cost.

---

## E1 · Router elasticity (H28) — ∂ln s_imt / ∂ln p_imt, within model

What we have: static conditional-logit estimate −1.19 ± 0.17 (H4), biased
toward zero by simultaneity (cutters are share-losers).

**H28a — event-based, daily.** For every repricing event: share impulse
response h = 1..14 days, diff-in-diff against non-moving providers on the
same model. Deliverable: elasticity by horizon ε(h) — the split between
instantaneous algorithmic routing and slow user-pinned adjustment; by
provider type and event direction (cuts vs raises asymmetry).
*Power: ~30 events with 7-day shares ≈ 2-3 weeks.*

**H28b — burst-resolution.** Same object at minute resolution from
event_bursts (request_count_30m, recent_peak_rpm per endpoint): how much of
the eventual reallocation happens within 30/60/180 minutes. This is the
sharpest routing-vs-users decomposition available anywhere.
*Power: first ~10 burst windows (~1-2 weeks at current event rates).*

**H28c — cross-model (nested upper level).** Users substitute across models:
∂ln D_mt / ∂ln(P_mt / P_m't) for capability-matched pairs (same class, e.g.
GLM-5.2 vs Kimi-k2.7 vs MiniMax-m3). Panel: rankings_weekly × price history
(2025-07→now, ~52 weeks × ~300 models), model FE + week FE, instrumented by
supply-side events. This closes the nested-logit structure: router inside
(fast, elastic), model choice outside (slow, moderate).
*Runnable NOW (historical panel).*

## E2 · Demand elasticity of token consumption (H29) — ∂ln D_mt / ∂ln P_mt

Does cheaper inference mean more inference (per model, and in aggregate)?

**H29a — the GLM-5.2 natural experiment.** The price war cut the min quote
−70% in 36h. Outcome: GLM-5.2 daily tokens vs a synthetic control built from
same-vintage launches (Kimi-k2.7-code, MiniMax-m3, hy3) that did not
experience a war. Confound handled: launch-growth curvature is absorbed by
the synthetic control's matched age profile.
*Power: 2 weeks of post-war activity data.*

**H29b — panel IV.** Model×week demand on lagged effective price, model+week
FE, price instrumented with entry events and provider-wave shocks (532
historical entries from LiteLLM + our prospective log). This is the number
that turns "competition improves pricing" (H27) into "competition increases
usage" — consumer response, not just price response.
*Runnable NOW on the historical arm; prospective arm strengthens it.*

## E3 · Quote response to demand (H30 = H20 sharpened) — ∂ln p / ∂ln D

Because quotes are sticky, the short-run supply response splits into:
- **extensive margin**: repricing hazard as a function of demand state
  (utilization, HF trending, activity growth) — the H20 hazard;
- **intensive margin**: |Δln p| conditional on repricing, vs the demand shock
  size;
- **shadow margins**: latency/reject/capacity-ceiling responses (the
  congestion channel from H16) — the true short-run supply curve is flat in
  price and steep in latency until the Ss band binds.

Estimand: expected Δln p over horizon h per unit demand shock =
hazard(D-state) × E[Δln p | reprice] + 0 (inaction region), reported per
provider type. Identification: HF-trending and app-adoption shocks as
demand instruments.
*Power: hazard fits at ~4 weeks; type-interacted at ~8.*

## E4 · GPU market elasticities (H31)

**H31a — rent response to utilization, by class.** vast.ai offer panel
(hourly, includes `rented` status): marketplace-clearing elasticity
Δln(dph_ct) on Δln(rented share_ct), daily, per class. Short-run GPU supply
is fixed, so this is a clean demand-shift trace-out within each class.
*Power: ~3-4 weeks of hourly panel (have 2 days).*

**H31b — cross-generation substitution.** Relative rents H100:H200:B200 vs
relative utilization: the substitution elasticity between GPU generations —
how quickly demand migrates when the B200 premium moves. Add H200/B200 to
the class list where index data exists (vast covers them; commercial indices
OCPI-H100/H200/B200 drop in via CSV if subscribed).
*Same timeline as H31a.*

**H31c — pass-through into token prices (existing H7).** ECM long-run β =
cost elasticity of quotes. Priors from phase-1: near zero (token deflation
2-3× faster than rents; repricing is competition-driven). The daily version
either overturns or confirms with real power at ~90 days.

## E5 · Quote reaction elasticity, micro (H32a) — ∂ln p_i / ∂ln p_j

From follow pairs (H21 formalized): within model, regress follower Δln p on
leader Δln p across events — the reaction-function slope, by provider type
and direction. The GLM-5.2 cascade suggests slope ≈ 1 at lag ≈ 0 for the
automated followers (tick-matched prices); boutiques/labs should show slope
≈ 0. Deliverable: a reaction matrix (who pegs whom, slope and lag) — the
adjacency structure of automated pricing.
*Power: 100 follow pairs ≈ 2-3 weeks at current rates.*

## Macro layer · Distributional price dynamics (H32b)

The macro object is the quote distribution F_mt(p) per model — min, p25,
median, p75, p95, share-weighted mean, and effective paid price tracked at
5-min resolution. New derived table `model_price_quantiles` (built nightly
from endpoints_snapshots; implemented with this plan).

- **Quantile-specific event studies**: how each quantile responds to entry,
  cuts, demand shocks. Phase-1 evidence says the min is the active margin
  (wars, entrants) while p95 is inert (premium quoters never move): the
  distribution compresses from below. Formalize: quantile impulse responses.
- **Micro→macro decomposition** (DFL/Oaxaca-style): each Δquantile decomposes
  into (i) within-provider repricing, (ii) composition (entry/exit), and
  (iii) reweighting (routing shares, for the weighted quantiles). This is the
  accounting bridge: it says exactly how much of "GLM-5.2 got 30% cheaper"
  came from incumbent cuts vs new entrants vs flow reallocating — connecting
  E1/E5 micro behavior to the macro price indices in H7.
*Quantile panel: NOW. Decomposition: with events, 2-4 weeks.*

## Unified accounting (the eventual model)

The reduced-form moments above calibrate one structure: nested-logit demand
(router inner nest with ε_router from H28, model choice outer nest from
H28c/H29), menu-cost quoters with type-specific Ss bands (H22) and reaction
slopes (H32a), and a capacity constraint that converts demand into congestion
before prices (H30's shadow margins), sitting on a GPU rental market with
H31's clearing elasticity. Every elasticity has a slot; the model's job is
counterfactuals: remove the router (pin flow) → how much higher are paid
prices; halve GPU rents → how much reaches users and how fast.

## Execution & gates

| module | estimand | runnable | full power |
|---|---|---|---|
| H28c, H29b | cross-model & panel-IV demand | **now** (historical) | grows |
| H32b quantile panel | F_mt functionals | **now** | — |
| H29a | GLM-5.2 war synthetic control | ~1-2 wk | 2-3 wk |
| H28a/b | router impulse responses | ~2 wk | 4-6 wk |
| H32a | reaction matrix | preliminary now | 100 pairs (~2-3 wk) |
| H31a/b | GPU clearing & substitution | ~3-4 wk | 8 wk |
| H30 | demand→quote hazard | ~4 wk | 8-12 wk |
| H31c | pass-through ECM | ~90 d | — |

All modules register in `orcap analyze` with power gates; results surface in
the memo automatically. Kill conditions: H28a elasticity indistinguishable
from H4's static estimate ⇒ simultaneity bias is small and the static number
stands; H29 demand elasticity ≈ 0 ⇒ inference demand is price-inelastic at
current margins (itself a major finding for the "cheaper compute → more AI"
thesis); H31a ≈ 0 ⇒ vast is not marginal-price-setting and commercial indices
are required.
