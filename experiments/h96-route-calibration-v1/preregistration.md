# H96: paid calibration of public shadow routing

Status: frozen before the first paid H96 request.

Study ID: `openrouter-route-calibration-v1`

Campaign ID: `h96-2026-07-19-two-day-pilot`

Campaign window: `[2026-07-19 01:00:00Z, 2026-07-21 01:00:00Z)`

## Question

How well do public endpoint menus and OpenRouter's documented price-routing
semantics predict the provider selected for our own requests, and how much of
the residual is associated with request shape, explicit price sorting, exact
endpoint eligibility, or session affinity?

This study calibrates a shadow router. It does not observe other users' flow,
private router health scores, request ordering, provider intent, or an exact
endpoint when generation metadata exposes only a provider display name.

## Fixed panel

Models:

1. `deepseek/deepseek-v4-pro`
2. `stepfun/step-3.7-flash`
3. `xiaomi/mimo-v2.5-pro`
4. `openai/gpt-oss-120b`
5. `deepseek/deepseek-v3.2`
6. `google/gemma-4-31b-it`

Request shapes:

| Shape | Nominal input | Conservative input cap | Maximum output | Extra eligibility |
|---|---:|---:|---:|---|
| short chat | 64 | 96 | 8 | none |
| input heavy | 2,048 | 3,072 | 16 | none |
| output heavy | 128 | 192 | 128 | none |
| required tool call | 256 | 512 | 32 | `tools`, `tool_choice` |

A model-shape block is eligible when the public endpoint response contains at
least two distinct providers with an exact endpoint `tag`, positive prompt and
completion prices, sufficient context/completion limits, and all required
parameters. Ineligible blocks remain in the candidate ledger and send no paid
requests.

## Assignment

Each eligible model-shape block contains eight assignments:

| Policy | Count | Provider controls |
|---|---:|---|
| `default_budgeted_iid` | 3 | default load balancing inside max-price menu |
| `sort_price` | 1 | `sort: price` inside the same menu |
| `pinned_cheapest` | 1 | exact cheapest endpoint tag, only/order, no fallback |
| `pinned_second` | 1 | cheapest exact tag from a second provider, no fallback |
| `default_sticky_seed` | 1 | default menu, shared sticky session |
| `default_sticky_repeat` | 1 | repeats the seed session and opening prompt |

The six non-sticky assignments are shuffled. Two positions are sampled for the
sticky pair, with seed constrained to precede repeat. Model-shape blocks are
also shuffled. The run and block seeds are retained.

Every independent assignment receives a new session ID and prompt nonce. Only
the sticky pair reuses both. Raw session IDs, prompts, completions, and API keys
are never written; a SHA-256 session hash is retained for assignment auditing.

## Public menu and budget guard

The candidate snapshot is fetched before outcomes. Expected all-in quote is

`nominal_input * prompt_price + max_output * completion_price`.

The candidate menu is sorted by that quantity. The component-wise max-price
guard is twice the maximum prompt and completion price among the three cheapest
compatible endpoints and is expressed in dollars per million tokens in the
request. This means the default arm is `budgeted default`, not unrestricted
OpenRouter default.

Before any request, the collector sums conservative task quote caps and aborts
if the total exceeds `$0.35`. During execution it refuses a next task when
realized spend plus that task's cap would exceed `$0.35`. Twelve scheduled
starts imply a maximum campaign stop loss of `$4.20`; expected spend is much
lower. Manual workflow dispatch is preflight-only and cannot add paid runs.

## Outcomes and estimands

Primary sample: successful `default_budgeted_iid` assignments.

Primary router model:

`Pr(i | C,x) proportional to quote_i(x)^(-eta)`.

The documented benchmark is `eta = 2`, but the public documentation does not
fully specify how prompt and completion prices are collapsed into one price.
We therefore freeze two eta-two implementations: the request-shape all-in quote
above and the mean prompt/completion per-token price index. A single global
`eta` is fitted to the shape-adjusted quote on chronological training runs and
evaluated on the final 30% of run timestamps once at least four runs exist.
Before four runs, metrics are explicitly in-sample. Provider fixed effects are
not primary and will require a dated amendment plus adequate provider support.

Primary metrics:

- selected-provider coverage in the compatible public menu;
- held-out negative log likelihood and multiclass Brier score;
- top-one accuracy;
- held-out comparison of the two frozen price definitions;
- fitted `eta` and likelihood-profile interval;
- selected-cost regret relative to the cheapest public compatible provider.

Secondary policy audits:

- explicit-price-sort match to the cheapest public provider;
- exact-pin success by requested provider and endpoint tag;
- billed/observed cost relative to the frozen public quote;
- sticky seed/repeat provider agreement;
- request-shape heterogeneity, reported without pooling if support is thin.

When provider metadata cannot distinguish two endpoint variants, candidates
are collapsed to the minimum all-in quote for that provider. This is a
provider-level approximation, and exact endpoint choice is marked unidentified.

## Interpretation gates

- Call inverse-square `predictively supported` only if it beats or is
  statistically indistinguishable from the fitted exponent on held-out loss
  and has adequate public-menu coverage.
- Call price sorting `validated` only for this bounded owned-probe menu and only
  when the selected provider matches the public cheapest compatible provider.
- Do not call a pin failure phantom liquidity until tag resolution, parameter
  support, error code, private health filtering, and transient outage are
  separated.
- Do not call sticky agreement strategic behavior; it is a routing/cache
  mechanism check.
- Do not convert these choice probabilities into market-wide routed share.
- No H96 result identifies front-running, cross-user ordering, or provider
  observation of incoming flow.

## Immutable outputs

- `router_calibration_candidates`: outcome-free public menu and compatibility.
- `router_calibration_assignments`: outcome-free policy/session-hash ledger.
- `router_route_attempts`: private redacted owned outcomes under the H96 study ID.
- `h96_choice_scores.parquet`: per-choice calibration scores.
- `h96_policy_audit.parquet`: sort, pin, and sticky checks.
- `h96_summary.json`: readiness, fit, held-out metrics, and claim boundary.

H81 and H95 data, code, horizons, releases, and claim boundaries remain frozen
and are not pooled with H96.
