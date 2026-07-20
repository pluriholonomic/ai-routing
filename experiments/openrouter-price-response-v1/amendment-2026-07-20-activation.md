# Price-response discovery activation

Status: frozen before paid activation.

Date: 2026-07-20 UTC

Eight successful assignment-only preflights produced 336 payload-free planned
tasks and no paid outcomes. The paid discovery window is prospectively set to
2026-07-20T05:00:00Z through 2026-07-27T05:00:00Z. Execution retains the frozen
$1 per-run, $25 rolling-day, and $300 campaign caps and uses the dedicated
`OPENROUTER_PRICE_EXPERIMENT_KEY`.

The scheduled workflow carries those frozen UTC endpoints as fallbacks and is
enabled when the study-specific repository variable is either unset or true;
setting `ORCAP_PAID_PRICE_RESPONSE_ENABLED=false` is the immediate kill switch.
The existing global paid-study gate must still be true.

Outcome-free planning no longer occupies the `randomized-routing-probes`
concurrency group. Every paid execution job still uses that exact lock, so it
cannot overlap H95 or another owned OpenRouter randomized execution. H95's
cadence, horizon, assignments, outcomes, and release rules are unchanged and
the studies are never pooled.

This is a discovery activation. It estimates routing of this account's owned
requests under frozen public menus and controls; it does not identify provider
beliefs, private rewards, market-wide flow, or use of UCB.
