# Simulated provider-pricing methodology

## Purpose

This layer uses the zero-spend `routing_simulation` panel to describe how
publicly posted inference-provider quotes position a provider **under the
simulation's documented inverse-square price rule**. It is a useful interim
methodology while realized selection, request outcomes, and provider costs are
not yet observable.

It does **not** estimate provider profit, realized demand, router allocation,
customer welfare, output quality, or strategic intent.

## Unit of analysis

For every saved public endpoint snapshot, fixed `model × workload-shape ×
provider` market, expected request cost is

\[
q_i = p^{in}_i T_{in} + p^{out}_i T_{out} + p^{request}_i.
\]

Among publicly eligible providers with positive quotes, the simulation uses

\[
\hat{s}_i = \frac{q_i^{-2}}{\sum_j q_j^{-2}}.
\]

The workload shapes are fixed before collection. There are no prompts, model
outputs, purchases, or route-preview calls in this panel.

## Estimands

H66 publishes three outputs.

| Output | Measure | Valid interpretation |
|---|---|---|
| `h66_simulated_pricing_panel` | quote markup to cheapest eligible provider, simulated share/rank, and mechanical slope | public quote-implied competitive position |
| `h66_simulated_pricing_events` | contiguous public quote changes and the associated simulated-share movement | descriptive repricing consequences conditional on the model |
| `h66_simulated_pricing_scorecard` | provider-level aggregation of position and public quote events | descriptive comparison over a common fixed panel; scenario rows and de-duplicated shocks are both reported |

The own-price elasticity is analytical, not empirical:

\[
\frac{\partial \log \hat{s}_i}{\partial \log q_i}=-2(1-\hat{s}_i).
\]

It is incorrect to regress `simulated_route_share` on `expected_quote_usd` and
describe the fitted coefficient as observed demand elasticity: the dependent
variable was generated from the price rule.

The report also records a conservative *public operational frontier*. A
provider is marked dominated only if a peer is no more expensive, has no lower
reported 30-minute uptime, no higher exact-matched public p90 latency, no
lower exact-matched public p90 throughput, and is strictly better on at least
one field. A missing operational metric yields `unknown`; this is not
output-quality measurement. The capture joins these frontend performance
metrics only on exact canonical model and provider names; ambiguous aliases
remain unjoined. H66 repeats the same strict join at analysis time against the
retained model map and congestion snapshots, so pre-enrichment historical
simulation rows can gain only an auditable exact match.

`simulated_quote_revenue_index = q_i \hat{s}_i` is retained only as a
fixed-unit-demand counterfactual. It is not observed revenue. With a separate,
explicit marginal-cost assumption \(c_i\), the static thought experiment
\((q_i-c_i)D\hat{s}_i\) has an optimum at \(q_i=2c_i\), but no current data
identify \(c_i\), \(D\), or actual router weights. It may be used only as a
cost-band sensitivity analysis.

`simulated_top_provider` means membership in the maximum simulated-share tier
and may include exact public-price ties. `simulated_unique_leader` and
`n_simulated_unique_leader_gains` are the corresponding tie-aware unique-winner
fields. Legacy `leader` naming remains only for backward-compatible outputs and
must not be used to claim a unique routing winner.

## Event method

For each provider in a `model × scenario`, compare consecutive observations no
more than 30 minutes apart. Report a quote event only when its expected quote
changes. Retain whether the public eligible-provider set is identical on both
sides. Separate scenario rows can share one underlying provider quote shock,
so summaries report both rows and de-duplicated `model × provider × time`
shocks; they are not independent observations.

These events can identify whether public repricings *would* change a
price-weighted allocation. They cannot establish quote spoofing, routing
capture, MEV, adverse selection, or a provider's intent. Those hypotheses need
actual selected-provider and outcome telemetry.

## Coverage gates and next data improvements

The H66 scorecard remains `insufficient_temporal_coverage` until it contains
at least 80 snapshots spanning 23 hours. A provider-behavior comparison needs
at least seven consecutive days after that first gate. The report explicitly
shows operational-metric completeness and excludes ambiguous duplicate provider
rows instead of averaging them.

Priority data upgrades:

1. Collect redacted account-level OpenRouter generation metadata: selected
   provider, fallback chain, cost, latency, tokens, and outcome code.
2. Attach a pre-specified payload-free quality result (deterministic verifier,
   tool success, or bounded feedback) to controlled requests.
3. Ingest Cloudflare, Portkey, or LiteLLM metrics-only logs as a replication
   surface where owned traffic already exists.
4. Add provider-side cost/capacity only when the hardware, utilization,
   throughput, and mapping assumptions are explicit; GPU spot quotes alone do
   not identify an inference provider's marginal cost.

Run locally after assembling capture artifacts:

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h66 --out analysis
```
