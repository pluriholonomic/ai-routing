# Public-quote routing simulation monitor

## Purpose

This is a zero-spend test of a narrow proposition:

> Do changes in public OpenRouter endpoint quotes and public capability metadata change the allocation implied by OpenRouter's documented default price rule?

It is not a test of realized orders. The public API does not expose the
per-request winner, the live 30-second outage filter, provider retries, or a
reservation/route-preview decision.

## 24-hour assay

The existing hourly capture job already records endpoint quotes every five
minutes. On every third snapshot it derives the route surface, yielding a
15-minute panel (four snapshots/hour, target 96 over 24 hours) without sending
an inference request.

The `routing-simulation-v1-20260709` panel fixes 20 high-volume, multi-provider
text models selected from the 2026-07-09 weekly ranking. The fixed set avoids
mistaking composition changes in the model universe for route changes. The
operator may explicitly replace it with `ORCAP_ROUTE_PANEL_MODELS`; that makes
the output a distinct experiment and should be reported as such.

For each model, the monitor reconstructs four request shapes:

| scenario | input | max output | requested capability |
|---|---:|---:|---|
| `short_chat` | 1,000 tokens | 256 tokens | none |
| `long_context` | 32,000 | 1,024 | none |
| `tool_chat` | 2,000 | 512 | `tools` |
| `structured_chat` | 2,000 | 512 | `response_format` |

These are **workload shapes**, not benchmark prompts. Prompt text is neither
sent nor used: the public endpoint API only exposes price and capability fields
that can be used to reconstruct the observable candidate surface.

For each compatible endpoint, simulated request cost is

\[
q_{im} = p^{in}_{im} T_{in} + p^{out}_{im} T_{out} + p^{request}_{im}.
\]

Variants are reduced to the cheapest compatible quote per provider because the
public docs specify inter-provider routing but do not disclose an allocator
among multiple variants of one provider. For a group with strictly positive
quotes, the reported share proxy is

\[
\hat s_{im} = \frac{q_{im}^{-2}}{\sum_j q_{jm}^{-2}}.
\]

This is the documented default price weighting conditional on the public
candidate set, not a claim that OpenRouter will choose that endpoint on a
particular request. Any zero-cost/free quote is excluded rather than assigning
an artificial infinite weight; exclusions are recorded in
`routing_simulation_runs`.

## Decision rule after 24 hours

`orcap route-sim-report` compares only contiguous observations at most 30
minutes apart. For each `model × scenario` transition it reports total variation
distance between the before/after simulated provider-share vectors, an eligible
set change flag, a quote-change flag, and whether the highest-probability
provider changes.

The first read requires at least 80 snapshots spanning 23 hours and at least
48 contiguous `model × scenario` transitions. The target is 96 observations;
the snapshot margin allows for a late hourly CI run, while the time-span gate
prevents a large cross-section from being misread as a 24-hour experiment.

| verdict | meaning | next action |
|---|---|---|
| `insufficient_24h_coverage` | fewer than 48 comparable transitions | keep the monitor running; do not infer stability |
| `no_public_quote_induced_route_change_observed` | coverage passed and no simulated vector changed | no price-perturbation synthetic test yet; extend the window or widen the fixed panel |
| `public_quote_surface_changes_simulated_route` | at least one quote/candidate transition changed the implied vector | eligible to run the separate synthetic perturbation suite |

The last verdict means only that public quote changes have economically
meaningful implications under the documented rule. It does not validate
realized routing volume, adverse selection, preferential flow, or MEV-like
behavior.

## Operations

The capture workflow writes two curated tables:

- `routing_simulation`: provider-level quote, expected request cost, and
  `simulated_route_share` for each model/scenario/timestamp.
- `routing_simulation_runs`: coverage and exclusion ledger, including
  free/zero-cost and single-provider groups.

The scheduled `route-simulation-monitor` workflow assembles the most recent
26 hours of capture artifacts and writes `h43_routing_simulation_*` results.
It publishes a report only once the 24-hour coverage gate passes.

Run the report locally against a hydrated or artifact-assembled `data/` tree:

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap route-sim-report --out analysis
```

Do not use this table as actual provider flow. To calibrate it, the next stage
requires an authorized account-level probe panel or a privacy-preserving
OpenRouter route-decision export containing candidate sets, selected providers,
and retry outcomes.
