# OpenRouter price-response study v1

Status: deployment-frozen, paid activation disabled pending H95 isolation and
two successful no-spend preflights.

## Question and unit

For owned requests, how does OpenRouter's realized provider choice change with
the public candidate menu and with documented routing controls? The unit is one
planned request within a model-by-request-shape block. This study does not
observe other customers' requests, private router scores, provider costs, or
provider intent.

## Assignment

Before outcomes, a public endpoint snapshot is frozen and hashed. Compatible
endpoints require positive prompt/completion prices, sufficient context and
output limits, and required tool parameters. Endpoint variants collapse to the
cheapest eligible endpoint per provider. Within each eligible block, the fixed
arm counts are:

- six fresh-session bounded-default requests;
- two default requests under an exactly separable top-two rectangular cap;
- two default requests under an exactly separable top-one rectangular cap;
- two requests using documented price sorting;
- one request in each of the two endpoint-order permutations; and
- one exact endpoint pin for each of the two cheapest distinct providers.

Nonseparable price caps are omitted and recorded; they are not approximated.
Assignments are deterministically shuffled from the recorded seed. The plan
artifact includes hashes of candidates, assignments, and the summary and must
upload before the execution job begins. Execution cannot regenerate a plan.

## Outcomes and estimands

The primary outcome is the selected provider reported by owned generation
metadata. Secondary outcomes are success, fallback, cost, tokens, and latency.
The primary estimand is the inverse-price choice exponent in fresh bounded
default arms, conditional on the frozen public menu. Secondary estimands are
default-versus-price-sort agreement, cap-induced selection shifts, endpoint
order asymmetry, and pin compliance. All estimates are intention-to-treat by
planned task; failures and missing generation metadata remain explicit.

## Gates and inference

A numeric live exponent is withheld until there are at least 200 covered
choices, 100 blocks, five models, five selected providers, 90% candidate-menu
coverage, log-price-ratio IQR at least 0.05, and no provider above 60% of
choices. The primary interval is profile likelihood with a whole-block
bootstrap audit. Predictive reporting includes log loss, Brier score, top-one
accuracy, and cost regret.

The canary is limited to one model, one shape, a $1 maximum conservative cap,
and requires 100% plan integrity, at least 90% selected-provider metadata
coverage, and no payload leakage before promotion. Discovery and any future
confirmation use disjoint study IDs and fixed chronological prefixes.

## Budget, privacy, and stop rules

Paid execution additionally requires a dedicated key, repository feature flag,
code-enforced UTC campaign window, and run/day/campaign caps. The deployment
defaults are $1/run, $25/rolling day, and $300/campaign. The actual campaign
dates remain unset until H95 is released or a separate account is available.
No prompt, completion, request body, session identifier, API key, or raw
response is retained. Scientific stopping never depends on an effect estimate.
