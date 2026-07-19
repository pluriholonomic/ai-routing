# Archival record: OpenRouter provider-routing documentation

Source: https://openrouter.ai/docs/features/provider-routing
Fetched and verified: 2026-07-18
Wayback snapshot: http://web.archive.org/web/20251121200046/https://openrouter.ai/docs/features/provider-routing

Verbatim quotes (section "Price-Based Load Balancing (Default Strategy)"):

1. "Prioritize providers that have not seen significant outages in the
   last 30 seconds."
2. "For the stable providers, look at the lowest-cost candidates and
   select one weighted by inverse square of the price."
3. Worked example: a $1/M-token provider is "9x more likely to be first
   routed to ... than Provider C because (1/3^2 = 1/9) (inverse square
   of the price)."
4. "Use the remaining providers as fallbacks."

These four sentences are the demand-system primitive for all theory in
papers/{ec,neurips,icml} and src/orcap/market_env/. The same page
documents the overrides treated as counterfactual arms: `sort: price`
(winner-take-all), `:floor` / `:nitro` shortcuts (disable load
balancing).
