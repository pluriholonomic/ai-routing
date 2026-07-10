# Price-event continuity baseline

The public routing-flow event analysis (H42) needs congestion observations on
both sides of a price change. `orcap capture` detects changes between its
in-process snapshots, but a new hourly process otherwise has no price from the
previous hour for its first comparison.

Use an already retained endpoint snapshot as a manual baseline:

```bash
uv run orcap capture \
  --baseline-endpoints path/to/previous-endpoints-snapshot.parquet \
  --samples 11 --interval-seconds 300
```

The baseline loader keeps the latest `run_ts` per
`(model_id, provider_name, tag, endpoint_fingerprint)` key. A changed first
snapshot therefore enters the same focused 60-second endpoint/congestion burst
path as an in-run change. The command uses only public OpenRouter quote and
endpoint-stat APIs; it does not send inference traffic.

This is an accumulation aid, not retrospective evidence: a baseline cannot
recover congestion before an already-missed event, and rolling 30-minute
request-count windows remain public flow proxies rather than individual route
logs or causal allocation data. It is intentionally not wired into a scheduled
workflow until the artifact/retention and publication policy is explicitly
approved.
