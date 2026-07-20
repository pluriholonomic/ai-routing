# Price-event discovery activation

Status: frozen before paid activation.

Date: 2026-07-20 UTC

Assignment-only planning produced 108 payload-free event-wave assignments and
zero paid outcomes before this amendment. The discovery window is
2026-07-20T04:00:00Z through 2026-07-27T04:00:00Z, with the frozen $1 per-run,
$25 rolling-day, and $60 event-campaign caps.

The scheduled workflow carries those frozen UTC endpoints as fallbacks. The
existing global paid-study gate is the kill switch and must be true. The stale
study-specific false variable is not an activation gate during this fixed,
expiring window; the Python campaign and budget gates remain authoritative.

Outcome-free base, W1, and W2 planning may run without the paid-execution lock.
Every base, W1, and W2 paid job remains in the
`randomized-routing-probes` concurrency group. Delayed or cancelled waves keep
their assignment and missed-window status; they are not relabeled or replaced.
H95 remains temporally isolated and is never queried or pooled.

The campaign remains an owned-routing event study. It can measure selection,
firmness, latency, and failure around public quote events, but not private order
flow, literal front-running, provider intent, or the provider's learning
algorithm.
