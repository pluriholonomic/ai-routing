# Prospective GLM-5.2 realized-routing campaign

Frozen: 2026-07-21 UTC, before the first request under study ID
`openrouter-glm52-routing-v1`.

## Motivation and claim boundary

The exploratory public panel recorded approximately 80% cumulative GLM-5.2
quote cuts by StreamLake and Novita. Under a price-only allocation, those quotes
imply a large transfer from passive providers. The existing paid panels contain
no GLM-5.2 default-route choices, so they cannot validate realized share for
this model. This new study is prospective and separate from every prior paid
campaign.

The study identifies routing and controlled-policy behavior for small owned
GLM-5.2 requests under frozen public menus. It does not observe market-wide
flow, other users, provider costs, profit, private router scores, intent,
front-running, or collusion.

## Fixed horizon and cadence

- Campaign window: 2026-07-21T21:00:00Z through 2026-08-04T21:00:00Z.
- Scheduled cadence: one independently planned block every 15 minutes.
- Model and shape: `z-ai/glm-5.2`, `short_chat`, with 96 conservative input
  tokens and eight maximum output tokens.
- Scientific stopping is the fixed calendar horizon. Outcomes, estimates,
  significance, quote states, or apparent convergence never stop or extend the
  campaign.

The theoretical maximum is 1,344 blocks, 2,688 default choices, and 13,440
total tasks. Missed or cancelled CI runs remain missed; they are not replayed or
burst-replaced.

## Assignment-first block

Every invocation fetches one public endpoint menu, collapses endpoint variants
to the cheapest compatible endpoint per provider, and requires StreamLake,
Novita, Z.AI, and at least two additional compatible providers. The plan stores
exact endpoint tags, component prices, request-shape quotes, eligibility, the
complete task list, its randomized order, quote-cap worst-case spend, and
cryptographic hashes. It is uploaded before paid execution. Execution consumes
that artifact exactly once and cannot regenerate assignments.

Every task uses a fresh hashed session. The ten within-block policies are:

| Policy | Replicates | Purpose |
|---|---:|---|
| `default_broad` | 2 | primary realized provider choices |
| `price_sorted` | 1 | documented price-sort implementation check |
| `pinned_streamlake` | 1 | StreamLake quote firmness, success, cost, latency |
| `pinned_novita` | 1 | Novita quote firmness, success, cost, latency |
| `pinned_z_ai` | 1 | model-author benchmark firmness and QoS |
| `exclude_streamlake` | 1 | randomized owned-request substitution control |
| `exclude_novita` | 1 | randomized owned-request substitution control |
| `exclude_both_cutters` | 1 | passive-provider counterfactual menu |
| `pair_only` | 1 | quality/health preference within the cutter pair |

Policy order is randomized from the immutable run seed. Exact pins disable
fallback. Price caps admit every provider intended by a policy and include a
one-percent numeric margin; the broad default cap admits the full compatible
public menu rather than only the cheapest providers.

## Primary estimand and frozen prediction

For covered successful `default_broad` tasks, let

\[
Y_{bt}=\mathbf{1}\{\text{selected provider is StreamLake or Novita}\}.
\]

The primary realized estimand is the mean of \(Y_{bt}\) over the fixed study
support. The frozen price-only prediction uses

\[
\pi_{ib}(\eta)=\frac{p_{ib}^{-\eta}}{\sum_j p_{jb}^{-\eta}},
\qquad \eta=1.6482780609377246,
\]

where prices and candidate sets come from the pre-request public block. The
primary calibration estimand is realized pair share minus the average frozen
pair prediction. The prior exploratory profile range \([1.26,2.04]\) is reported
as a sensitivity band, not as a GLM-5.2 confidence interval.

The observed pair share receives a Wilson interval and a whole-block bootstrap
interval. Calibration error uses the same whole-block bootstrap. A GLM-specific
multinomial price exponent and profile-likelihood interval are secondary.

## Support gates

Publication-strength numerical interpretation is withheld until all hold:

- at least 800 covered default choices;
- at least 100 distinct planned time blocks;
- at least seven elapsed days between first and last frozen menus; and
- at least 90% of default selections covered by their frozen public menu.

Price elasticity over time additionally requires meaningful quote movement;
without it, the panel identifies level calibration but not a temporal response
curve. Provider-specific rankings remain descriptive until at least 20 covered
observations exist in the relevant policy cell.

## Secondary controlled estimands

The randomized within-block exclusions identify how this account's success,
selected provider, latency, and realized cost change when one or both cutters
are unavailable. Pins measure only tiny-load executable firmness and QoS, not
capacity. The pair-only arm measures relative selection within the pair. Natural
quote changes are not randomized; event-time and elasticity analyses are
observational even though policies within a block are randomized.

## Isolation, privacy, and remote operation

The study uses the dedicated `OPENROUTER_PRICE_EXPERIMENT_KEY` and the shared
non-cancelling `randomized-routing-probes` execution lock. It never reads,
amends, re-runs, or pools H81 or H95 data. Assignment planning may overlap other
workflows; paid execution cannot overlap their owned randomized requests.

No prompt, completion, raw response, request body, API key, or session identifier
is retained. Only public menus, immutable assignments, selected-provider
metadata, success, tokens, cost, latency, and payload hashes/flags are stored.
GitHub Actions is the execution authority. Immutable run artifacts are ingested
into the private `t4run/openrouter-market-history` dataset; an hourly monitor
publishes aggregate tables, a time-series figure, and a private Space dashboard.
The local computer is not required.

## Budget and operational stops

Paid execution requires repository feature flags, the dedicated key, a healthy
complete target menu, an open fixed campaign window, exact manifest replay, no
duplicate task IDs, and reconstructed spend below all limits. Initial caps are
$0.10 per run, $5 per rolling 24 hours, and $50 for the campaign. The available
$500 account credit is not a spending target. Any source, manifest, privacy,
duplicate, or budget failure stops that run without adaptive replacement.
