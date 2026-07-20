# OpenRouter adaptive monotone policy-emulation experiment

Status: prospective; no requests from this study were sent before this file was committed.

Study ID: `openrouter-adaptive-monotone-v1`

Plan version: `adaptive-monotone-plan-v1`

Fixed horizon: first 120 launched model/shape blocks
Default collection window: 2026-07-21 00:00 UTC through 2026-08-04 03:00 UTC

## Question and estimand

Can a monotone router rule reduce router-created cross-provider price coupling and
concentration without materially increasing expected quoted cost or reducing realized
owned-request service quality?

OpenRouter does not expose an API for arbitrary allocation probabilities. The study
therefore emulates each policy. At the plan stage it freezes a public endpoint menu,
computes the policy's provider probabilities, makes a seeded provider draw, and records
the complete probability vector. At execution it sends the same neutral request shape
to the drawn exact endpoint with `only=[endpoint]` and `allow_fallbacks=false`. The
result identifies the owned-request consequences of the emulated allocation rule on
sampled menus. It does not identify OpenRouter's private rule.

The primary policy estimands are mean request success and mean bounded latency under
each policy over the fixed block population. Bounded latency equals observed generation
latency on a successful request and 90,000 ms on failure or missing generation metadata.
Secondary estimands are realized cost, requested-versus-selected endpoint agreement,
provider concentration, and quote-to-realized-cost slippage.

## Arms

Every eligible block contains exactly one task from every arm; arm inclusion probability
is one. Execution order is randomized. Within each arm the provider draw has the exact
recorded propensity.

1. `baseline_eta2`: shares proportional to public uptime times quoted request cost to
   the power -2.
2. `calibrated_eta145`: the same monotone score with price exponent 1.45, frozen from
   the pre-study exploratory live exponent estimate.
3. `independent_explore_eta2_eps10`: 90% of the baseline share plus 10% uniform,
   provider-independent exploration.
4. `historical_cone_eta125_eps10`: eta 1.25 with 10% independent exploration,
   frozen from the historical temporal-prefix selection run at Hugging Face revision
   `7189386a9c14f35ce539ce1088cf3021dddf17f5`. The July 16--20 holdout was used
   only before this paid study began and is not a paid-outcome tuning sample.
5. `cone_projected_menu_adaptive`: before outcomes, choose eta from
   {0.50, 0.75, 1.00, 1.25, 1.45, 1.75, 2.00} and exploration from
   {0, 0.05, 0.10, 0.15}. Minimize the local cross-provider price-gain norm, then HHI,
   subject to expected quoted cost no more than 2% above the eta-2 rule and public
   uptime no more than 0.2 percentage points below it on that frozen menu.

For every arm, scores are monotone decreasing in price and increasing in public uptime.
The adaptive arm responds only to the public menu frozen before paid execution. It does
not update from paid outcomes during this study.

## Population, blocking, and request shapes

The default model list is the six-model H96 list in the repository. Eligible endpoints
must expose an exact tag, positive prompt and completion prices, positive 30-minute
public uptime, and support the request shape. At most the cheapest endpoint per provider
is retained. A provider's conservative request quote must be at most $0.02. Menus need
at least three distinct providers.

Each scheduled run considers `short_chat` and `output_heavy` shapes. It draws up to
three model/shape blocks from the top 12 outcome-free information scores after a seeded
shuffle. The information score is log(1 + provider count) times the log max/min quote
ratio. The planner truncates the last run so that launched blocks cannot exceed 120.
An assignment-only preflight does not count toward the horizon; a block is launched
when its first paid attempt is written.

## Assignment and execution integrity

The assignment artifact is uploaded before any request. It records the menu hash,
policy parameters, full target distribution, provider propensity, uniform variate,
selected exact endpoint, order, quote cap, and manifest hash. Paid execution consumes
that artifact and refuses to regenerate assignments. A selected endpoint receives a
5% component-wise prompt/completion price tolerance. A stale quote outside that bound
is a failure, not an invitation to choose a different endpoint.

All paid workflows share `randomized-routing-probes`, use `cancel-in-progress=false`,
and never burst to repair missed cadence. Duplicate task IDs, a nonrectangular policy
block, invalid propensities, fallbacks, a campaign-window violation, or a budget breach
fail closed. Prompts, outputs, session IDs, and secrets are not persisted.

Default hard budgets are $0.75 per run, $5 per rolling day, and $40 for the campaign.
These are spending ceilings, not targets.

## Frozen analysis

Before 120 launched rectangular blocks, the public monitor exposes assignment integrity,
written and completed blocks, total attempts, total successes, and aggregate spend. It
does not expose arm-specific outcome means, confidence intervals, or significance.

At the first immutable dataset revision with 120 launched blocks and passing assignment
integrity:

- report arm means for success, bounded latency, and realized cost;
- report paired differences from `baseline_eta2` by block;
- form 95% percentile intervals by resampling whole blocks 2,000 times with seed
  20260721;
- report provider concentration and requested-selected agreement;
- retain every assignment in the first 120 launched blocks (intention to treat); an
  assignment with no attempt is a failed request with bounded latency 90,000 ms;
- do not pool this study with H81, H95, H96, or the prior market-measurement campaign;
- report all arms regardless of sign.

No early stopping, outcome-conditioned arm changes, model exclusions, cadence changes,
or post-hoc outcome definitions are permitted. Operational failures can motivate a new
versioned study, but they do not amend this one.

## Claim boundary

The historical replay holds provider behavior fixed. The paid study adds realized
success, latency, and cost for owned pinned requests. Together they can show a feasible
policy improvement on observed menus and sampled requests. They cannot identify user
value, provider marginal cost, total market demand, endogenous provider repricing,
cross-user routing, private router scores, dynamic equilibrium, collusion, or scalar
social welfare. Those require a later randomized policy deployment or a structural
model with additional cost and demand data.
